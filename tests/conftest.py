from collections.abc import Callable

import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):  # pylint: disable=unused-argument
    yield

    if not getattr(item.module, 'ENABLE_HOOKWRAPPER_PROBE', False):
        return

    if item.module.HOOKWRAPPER_EXPECTED_CACHED_VALUE is None:
        return

    item.module.HOOKWRAPPER_TEARDOWN_CACHED_VALUE = item.module.cached_value()
    assert (
        item.module.HOOKWRAPPER_TEARDOWN_CACHED_VALUE is item.module.HOOKWRAPPER_EXPECTED_CACHED_VALUE
    ), 'hookwrapper teardown should still see the object cached during the test body'


@pytest.fixture
def assert_cache_visible_during_teardown(cache_function: Callable):
    '''Shared teardown assertion helper for cache-ordering tests.

    These tests need to assert behavior after the test body returns but before
    pytest finishes teardown, so the assertion cannot live entirely inside an
    individual test function.
    '''
    yield

    from tests.main_test import CACHED_RESULTS_DURING_TEARDOWN
    from tests.main_test import CACHED_RESULTS_FROM_TEST

    teardown_result = cache_function()
    # Persist the value seen during fixture teardown so the next test can assert
    # that the previous test kept its cache through teardown.
    CACHED_RESULTS_DURING_TEARDOWN[cache_function] = teardown_result
    assert (
        teardown_result is CACHED_RESULTS_FROM_TEST[cache_function]
    ), 'fixture teardown should still see the object cached during the test body'
