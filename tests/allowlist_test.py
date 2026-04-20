from collections.abc import Callable
from unittest import mock

import pytest

import tests.main_test
from tests.main_test import cache_function  # noqa: F401
from tests.main_test import test_a_run_first  # noqa: F401


def test_b_run_second(cache_function: Callable, pytestconfig):  # noqa: F811
    """Run second and prove allowlisted modules keep their cached value."""
    disabled_modules = pytestconfig.getini('lru_cache_disabled')
    if not disabled_modules:
        pytest.skip('allowlist assertions require a non-empty lru_cache_disabled config')

    if any('tests.main_test'.startswith(module_prefix) for module_prefix in disabled_modules):
        pytest.skip('allowlist assertions only apply when tests.main_test is not covered')

    with mock.patch.object(
        tests.main_test, 'expensive_network_call', return_value=8, autospec=True
    ) as mock_network_call:
        assert (
            cache_function() is mock.sentinel.default_network_call
        ), 'allowlisted modules should keep returning the cached pre-patch value'
        assert (
            not mock_network_call.called
        ), 'the patched network function should stay unused when the cache is preserved'
