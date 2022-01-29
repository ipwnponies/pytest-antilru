import sys

from pytest_antilru import main

try:
    from functools import lru_cache
except ImportError:
    try:
        from backports.functools_lru_cache import lru_cache
    except ImportError:
        from functools32 import lru_cache


def expensive_network_call():
    # Pretend this is an expensive network call.
    # You want to cache this for performance but you want to run tests with different responses as well.
    return 1


@lru_cache(128, False)
def cache_me_lru_cache_explicit_param():
    return expensive_network_call()


@lru_cache
def cache_me_default_param():
    return expensive_network_call()


class TestLruCacheExplicitParam:
    @staticmethod
    def test_a_run_first():
        '''Run this test first, to pollute the test environment.'''
        assert cache_me_lru_cache_explicit_param() == 1

    @staticmethod
    def test_b_run_second(mocker):
        '''Run second, after env is dirtied.'''
        # We want to mock the network call for this test case
        mock_network_call = mocker.patch.object(
            sys.modules[__name__], 'expensive_network_call', return_value=2, autospec=True
        )

        assert cache_me_lru_cache_explicit_param() == 2
        assert mock_network_call.called


class TestLruCacheDefaultParam:
    @staticmethod
    def test_a_run_first():
        '''Run this test first, to pollute the test environment.'''
        assert cache_me_default_param() == 1

    @staticmethod
    def test_b_run_second(mocker):
        '''Run second, after env is dirtied.'''
        # We want to mock the network call for this test case
        mock_network_call = mocker.patch.object(
            sys.modules[__name__], 'expensive_network_call', return_value=2, autospec=True
        )

        assert cache_me_default_param() == 2
        assert mock_network_call.called


def test_lru_cache_unknown_kwargs(mocker):
    '''Test that warning is emitted when new kwargs are added to lru_cache.

    Let's hope somene reports the warning and we can get to patching.
    '''
    spy = mocker.spy(main.logging, 'warning')
    lru_cache(new_feature=1)(expensive_network_call)

    assert spy.called
