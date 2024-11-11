import sys
from collections.abc import Callable
from functools import lru_cache
from unittest import mock

import pytest

from pytest_antilru import main


def expensive_network_call():
    # Pretend this is an expensive network call.
    # You want to cache this for performance but you want to run tests with different responses as well.
    return 1


@lru_cache
def cache_me_lru_cache():
    return expensive_network_call()


@lru_cache()
def cache_me_empty_decorator_call():
    return expensive_network_call()


@pytest.fixture(params=[cache_me_lru_cache, cache_me_empty_decorator_call])
def cache_function(request):
    yield request.param


def test_a_run_first(cache_function: Callable):
    '''Run this test first, to pollute the test environment.'''
    assert cache_function() == 1


def test_b_run_second(cache_function: Callable):
    '''Run second, after env is dirtied.'''
    # We want to mock the network call for this test case
    with mock.patch.object(
        sys.modules[__name__], 'expensive_network_call', return_value=2, autospec=True
    ) as mock_network_call:
        assert cache_function() == 2
        assert mock_network_call.called


def test_lru_cache_unknown_kwargs():
    '''Test that warning is emitted when new kwargs are added to lru_cache.

    Let's hope somene reports the warning and we can get to patching.
    '''
    with mock.patch.object(main.logging, 'warning', wraps=main.logging.warning) as spy:
        lru_cache(new_feature=1)(expensive_network_call)

        assert spy.called


class TestParameters:
    @lru_cache(1337, typed=True)
    def cache_me_lru_cache_explicit_param(self):
        return mock.sentinel.default_param

    def test(self):
        assert self.cache_me_lru_cache_explicit_param() == mock.sentinel.default_param

    @pytest.mark.skipif(sys.version_info < (3, 9), reason='cache_parameters added to Python 3.9')
    def test_explicit_parameters(self):  # pragma: no cover <python39
        '''Test the lru_cache parameters are wrapped correctly.'''
        assert self.cache_me_lru_cache_explicit_param.cache_parameters() == {
            'maxsize': 1337,
            'typed': True,
        }

    @pytest.mark.skipif(sys.version_info < (3, 9), reason='cache_parameters added to Python 3.9')
    def test_default_parameters(self, cache_function: Callable):  # pragma: no cover <python39
        '''Test the default parameter is wrapped correctly.'''

        assert cache_function.cache_parameters() == {
            'maxsize': 128,
            'typed': False,
        }
