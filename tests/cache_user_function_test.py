from unittest import mock

import pytest

from pytest_antilru import main


class StubCallable:
    '''Stand-in for a decorated user function, so tests don't rely on real lru_cache machinery.'''

    def __init__(self, module):
        self.__module__ = module


@pytest.mark.parametrize(
    ('module', 'disabled_modules', 'expect_registered'),
    [
        ('app.util', ['app.util'], True),
        ('app.util.helpers', ['app.util'], True),
        ('app.utilities', ['app.util'], False),
        ('application', ['app'], False),
        ('other.module', ['app.util'], False),
        (None, ['app.util'], False),
    ],
    ids=['exact_match', 'submodule_match', 'sibling_over_match', 'top_level_over_match', 'non_match', 'none_module'],
)
def test_cache_user_function_boundary_matching(monkeypatch, module, disabled_modules, expect_registered):
    '''Allowlist entries match on module-path boundaries, not raw string prefixes.'''
    monkeypatch.setattr(main, 'CACHED_FUNCTIONS', [])

    user_function = StubCallable(module)
    wrapper = mock.sentinel.wrapper
    main.cache_user_function(user_function, wrapper, disabled_modules)

    assert (wrapper in main.CACHED_FUNCTIONS) is expect_registered
