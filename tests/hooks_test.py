"""White-box tests for the pytest hooks in pytest_antilru/main.py, driven directly rather than
through a real pytest session, since the suite cannot use pytest.Pytester while pytest 3-5 are in
the matrix (see docs/future-work/2026-09-13-pytester-rewrite.md).
"""
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


def test_install_resets_stale_registry(monkeypatch):
    '''A second in-process install must not keep clearing wrappers from a prior session.'''
    monkeypatch.setattr(main, 'CACHED_FUNCTIONS', [mock.sentinel.stale_wrapper])

    install = main.pytest_load_initial_conftests(FakeEarlyConfig(), FakeParser(), args=[])
    try:
        next(install)
        assert main.CACHED_FUNCTIONS == []
    finally:
        # Undo the monkeypatch this hook installs; pytest_collection normally does this.
        main.functools.lru_cache = main.old_lru_cache
