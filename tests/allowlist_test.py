from collections.abc import Callable
from unittest import mock

import tests.main_test
from tests.main_test import cache_function  # noqa: F401
from tests.main_test import test_a_run_first  # noqa: F401


def test_b_run_second(cache_function: Callable):  # noqa: F811
    '''Run second, after env is dirtied.'''
    # We want to mock the network call for this test case
    with mock.patch.object(
        tests.main_test, 'expensive_network_call', return_value=8, autospec=True
    ) as mock_network_call:
        assert cache_function() == 1
        assert not mock_network_call.called
