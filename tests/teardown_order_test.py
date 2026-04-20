from functools import lru_cache

import pytest

EXPECTED_CACHED_VALUE = None
TEARDOWN_CACHED_VALUE = None


@lru_cache
def cached_value():
    return object()


@pytest.fixture(autouse=True)
def assert_cache_visible_during_teardown():
    '''Assert teardown still sees the cached object from the active test.'''
    global TEARDOWN_CACHED_VALUE

    yield

    if EXPECTED_CACHED_VALUE is None:
        return

    TEARDOWN_CACHED_VALUE = cached_value()
    assert (
        TEARDOWN_CACHED_VALUE is EXPECTED_CACHED_VALUE
    ), 'fixture teardown should still see the object cached during the test body'


def test_a_populates_cache():
    '''Populate the cache and record the object teardown should still observe.'''
    global EXPECTED_CACHED_VALUE

    # Capture the cached result so fixture teardown can assert it is still present.
    EXPECTED_CACHED_VALUE = cached_value()


def test_b_clears_cache_after_teardown():
    '''Verify the previous test kept its cache through teardown but not into this test.'''
    global EXPECTED_CACHED_VALUE

    assert (
        TEARDOWN_CACHED_VALUE is EXPECTED_CACHED_VALUE
    ), 'the prior test should keep its cached value until fixture teardown runs'
    assert (
        cached_value.cache_info().currsize == 0
    ), 'the plugin should clear the previous test cache before this test starts'
    EXPECTED_CACHED_VALUE = None
