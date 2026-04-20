import sys
from collections.abc import Callable
from functools import lru_cache
from unittest import mock

import pytest

from pytest_antilru import main

CACHED_RESULTS_FROM_TEST = {}
CACHED_RESULTS_DURING_TEARDOWN = {}


def expensive_network_call():
    # Pretend this is an expensive network call.
    # You want to cache this for performance but you want to run tests with different responses as well.
    return mock.sentinel.default_network_call


@lru_cache
def cache_me_lru_cache():
    return expensive_network_call()


@lru_cache()
def cache_me_empty_decorator_call():
    return expensive_network_call()


@pytest.fixture(params=[cache_me_lru_cache, cache_me_empty_decorator_call])
def cache_function(request):
    '''Exercise the same cache lifecycle assertions for both lru_cache decorator forms.'''
    # Initialize cross-test state for this cached function so test_b can compare
    # what test_a stored during its body with what the fixture later saw in teardown.
    CACHED_RESULTS_FROM_TEST.setdefault(request.param, None)
    CACHED_RESULTS_DURING_TEARDOWN.setdefault(request.param, None)
    yield request.param


def test_a_run_first(cache_function: Callable, assert_cache_visible_during_teardown):
    '''Populate the cache so teardown and the next test can observe its lifecycle.'''
    result = cache_function()
    # Capture the cached result so fixture teardown can assert it is still present.
    CACHED_RESULTS_FROM_TEST[cache_function] = result
    assert (
        result is mock.sentinel.default_network_call
    ), 'the unpatched test should cache the default network-call sentinel'


def test_b_run_second(cache_function: Callable, assert_cache_visible_during_teardown):
    '''Verify cache state is reset between tests while preserving teardown access.'''
    assert (
        CACHED_RESULTS_DURING_TEARDOWN[cache_function] is CACHED_RESULTS_FROM_TEST[cache_function]
    ), 'the prior test should keep its cached value until fixture teardown runs'
    assert (
        cache_function.cache_info().currsize == 0
    ), 'the plugin should clear the previous test cache before this test starts'

    with mock.patch.object(
        sys.modules[__name__], 'expensive_network_call', return_value=mock.sentinel.patched_network_call, autospec=True
    ) as mock_network_call:
        result = cache_function()
        CACHED_RESULTS_FROM_TEST[cache_function] = result
        assert (
            result is mock.sentinel.patched_network_call
        ), 'after cache reset, this test should observe the patched network-call sentinel'
        assert mock_network_call.called, 'the patched network function should be exercised'


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
