"""White-box tests for the pytest hooks in pytest_antilru/main.py, driven directly rather than
through a real pytest session, since the suite cannot use pytest.Pytester while pytest 3-5 are in
the matrix (see docs/future-work/2026-09-13-pytester-rewrite.md).
"""
import contextlib
import functools
from unittest import mock

from pytest_antilru import main


class FakeParser:
    '''Stand-in for pytest's Parser, just enough to satisfy pytest_load_initial_conftests.'''

    def addini(self, *args, **kwargs):
        pass


class FakeEarlyConfig:
    '''Stand-in for pytest's Config, just enough to satisfy pytest_load_initial_conftests.'''

    def getini(self, name):  # pylint: disable=unused-argument
        return []


@contextlib.contextmanager
def installed():
    '''Drive a real pytest_load_initial_conftests install and guarantee functools.lru_cache and
    main._recording are restored to their pre-install values afterward, even if the test body
    raises. Saving and restoring must happen through plain assignment, not monkeypatch: install
    sets these globals directly (not through monkeypatch), and pytest's monkeypatch fixture undoes
    its own setattr calls in its own teardown, which runs after this generator's finally block has
    already run, so a monkeypatch-based restore here would be silently overwritten.
    '''
    original_lru_cache = functools.lru_cache
    original_recording = main._recording
    install = main.pytest_load_initial_conftests(FakeEarlyConfig(), FakeParser(), args=[])
    next(install)
    try:
        yield
    finally:
        functools.lru_cache = original_lru_cache
        main._recording = original_recording


def test_install_resets_stale_registry(monkeypatch):
    '''A second in-process install must not keep clearing wrappers from a prior session.'''
    monkeypatch.setattr(main, 'CACHED_FUNCTIONS', [mock.sentinel.stale_wrapper])

    with installed():
        assert main.CACHED_FUNCTIONS == []


def test_second_install_does_not_self_recurse(monkeypatch):
    '''A wrapper leaked by a crashed session must not make the next session recurse forever.

    Regression test for audit finding 1: old_lru_cache used to be re-read from functools.lru_cache
    at install time, so a second install captured the first session's own wrapper as "the real
    thing" and called itself forever.
    '''
    # This test drives real installs, which clear CACHED_FUNCTIONS; isolate it from the registry
    # the actual plugin populated during this session's own collection.
    monkeypatch.setattr(main, 'CACHED_FUNCTIONS', [])
    original_lru_cache = functools.lru_cache
    original_recording = main._recording

    try:
        first_install = main.pytest_load_initial_conftests(FakeEarlyConfig(), FakeParser(), args=[])
        next(first_install)  # first session installs and is never restored, simulating a crash

        second_install = main.pytest_load_initial_conftests(FakeEarlyConfig(), FakeParser(), args=[])
        next(second_install)

        @functools.lru_cache
        def cached():
            return mock.sentinel.value

        assert cached() is mock.sentinel.value  # would hit RecursionError before this fix
    finally:
        # Restore to the true pre-test state, not to whatever the first (deliberately leaked)
        # install left behind.
        functools.lru_cache = original_lru_cache
        main._recording = original_recording


def test_pass_through_when_not_recording(monkeypatch):
    '''Once recording is off, the wrapper delegates to the real lru_cache and records nothing, for
    both the bare (@lru_cache) and parameterized (@lru_cache()) decorator forms.'''
    monkeypatch.setattr(main, 'CACHED_FUNCTIONS', [])

    with installed():
        main._recording = False

        @functools.lru_cache
        def bare():
            return object()

        @functools.lru_cache()
        def parameterized():
            return object()

        first_bare_call = bare()
        first_parameterized_call = parameterized()
        assert bare() is first_bare_call, 'still behaves like a normal lru_cache'
        assert parameterized() is first_parameterized_call, 'still behaves like a normal lru_cache'
        assert main.CACHED_FUNCTIONS == [], 'not recorded while _recording is False'


def test_unconfigure_restores_real_lru_cache(monkeypatch):
    '''pytest_unconfigure restores the attribute even though pytest_collection already flips the
    recording flag off, so a wrapper is never left installed once configuration tears down.'''
    monkeypatch.setattr(main, 'CACHED_FUNCTIONS', [])

    with installed():
        assert functools.lru_cache is not main._REAL_LRU_CACHE

        main.pytest_unconfigure(config=None)

        assert functools.lru_cache is main._REAL_LRU_CACHE
