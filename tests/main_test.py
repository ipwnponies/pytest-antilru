import sys
from functools import lru_cache
from unittest import mock


def expensive_network_call() -> int:
    # Pretend this is an expensive network call.
    # You want to cache this for performance but you want to run tests with different responses as well.
    return 1


@lru_cache()
def cache_me() -> int:
    return expensive_network_call()


def test_a_run_first() -> None:
    assert cache_me() == 1


def test_b_run_second() -> None:
    # We want to mock the network call for this test case
    with mock.patch.object(sys.modules[__name__], 'expensive_network_call', return_value=2) as mock_network_call:
        assert cache_me() == 2
        assert mock_network_call.called
