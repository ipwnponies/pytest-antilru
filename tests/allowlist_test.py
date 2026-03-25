from collections.abc import Callable
from unittest import mock

import pytest

import tests.main_test
from tests.main_test import cache_function  # noqa: F401
from tests.main_test import test_a_run_first  # noqa: F401


def test_b_run_second(cache_function: Callable, pytestconfig):  # noqa: F811
    '''Run second, after env is dirtied.'''
    disabled_modules = pytestconfig.getini('lru_cache_disabled')
    if not disabled_modules:
        pytest.skip('allowlist assertions require a non-empty lru_cache_disabled config')

    if any('tests.main_test'.startswith(module_prefix) for module_prefix in disabled_modules):
        pytest.skip('allowlist assertions only apply when tests.main_test is not covered')

    # We want to mock the network call for this test case
    with mock.patch.object(
        tests.main_test, 'expensive_network_call', return_value=8, autospec=True
    ) as mock_network_call:
        assert cache_function() == 1
        assert not mock_network_call.called
