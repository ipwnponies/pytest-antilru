import sys

from pytest_antilru import main

try:
    from functools import lru_cache
except ImportError:
    try:
        from backports.functools_lru_cache import lru_cache
    except ImportError:
        from functools32 import lru_cache

try:
    from unittest import mock
except ImportError:
    import mock


def expensive_network_call():
    # Pretend this is an expensive network call.
    # You want to cache this for performance but you want to run tests with different responses as well.
    return 1


@lru_cache
def cache_me_default_param():
    return expensive_network_call()


def test_a_run_first():
    '''Run this test first, to pollute the test environment.'''
    assert cache_me_default_param() == 1


def test_b_run_second():
    '''Run second, after env is dirtied.'''
    # We want to mock the network call for this test case
    with mock.patch.object(
        sys.modules[__name__], 'expensive_network_call', return_value=2, autospec=True
    ) as mock_network_call:
        assert cache_me_default_param() == 2
        assert mock_network_call.called


def test_lru_cache_unknown_kwargs():
    '''Test that warning is emitted when new kwargs are added to lru_cache.

    Let's hope somene reports the warning and we can get to patching.
    '''
    with mock.patch.object(main.logging, 'warning', wraps=main.logging.warning) as spy:
        lru_cache(new_feature=1)(expensive_network_call)

        assert spy.called
