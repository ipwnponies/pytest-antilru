import functools

import pytest

CALL_COUNT = 0


def create_late_cached_func():
    global CALL_COUNT

    @functools.lru_cache
    def late_func():
        global CALL_COUNT
        CALL_COUNT += 1
        return CALL_COUNT

    return late_func


LATE_FUNC = None


def test_a_warm_late_cache(pytestconfig):
    global LATE_FUNC
    if not pytestconfig.getini('lru_cache_always_record'):
        pytest.skip('late_import_test requires lru_cache_always_record enabled')
    LATE_FUNC = create_late_cached_func()
    res1 = LATE_FUNC()
    assert res1 == 1
    res2 = LATE_FUNC()
    assert res2 == 1  # cached within test


def test_b_verify_late_cache_cleared(pytestconfig):
    global LATE_FUNC
    if not pytestconfig.getini('lru_cache_always_record'):
        pytest.skip('late_import_test requires lru_cache_always_record enabled')
    assert LATE_FUNC is not None
    # Because always_record is enabled, late_func was registered into CACHED_FUNCTIONS and cleared on teardown
    assert LATE_FUNC.cache_info().currsize == 0, 'Late-imported cache should be cleared between tests'
    res = LATE_FUNC()
    assert res == 2
