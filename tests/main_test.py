import sys

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


@lru_cache()
def cache_me():
    return expensive_network_call()


def test_a_run_first():
    assert cache_me() == 1


def test_b_run_second():
    # We want to mock the network call for this test case
    with mock.patch.object(sys.modules[__name__], 'expensive_network_call', return_value=2) as mock_network_call:
        assert cache_me() == 2
        assert mock_network_call.called
