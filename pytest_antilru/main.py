# Please don't use this, it's inconsistent and will be monkey-patched left and right.
# We're only importing it to update functools module's reference
import functools
import logging
from functools import wraps  # pylint: disable=ungrouped-imports

import pytest

CACHED_FUNCTIONS = []
old_lru_cache = None


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_load_initial_conftests(early_config, parser, args):  # pylint: disable=unused-argument
    """Monkey patch lru_cache, before any module imports occur."""
    parser.addini('lru_cache_disabled', 'Allowlist of module prefixes to apply disable lru_cache on', type='linelist')
    lru_cache_disabled_modules = early_config.getini('lru_cache_disabled')

    # Gotta hold on to this before we patch it away
    global old_lru_cache
    old_lru_cache = functools.lru_cache

    @wraps(functools.lru_cache)
    def lru_cache_wrapper(maxsize=Ellipsis, typed=Ellipsis, **kwargs):
        """Wrap lru_cache decorator, to track which functions are decorated."""

        if kwargs:
            logging.warning('Unexpected kwargs, maybe an update in functools.lru_cache')

        # User function is passed directly to decorator (skip decorator params)
        if callable(maxsize) and typed is Ellipsis:
            user_function = maxsize
            wrapper = old_lru_cache(user_function)
            CACHED_FUNCTIONS.append(wrapper)
            return wrapper

        # Apply lru_cache params (maxsize, typed)
        kwargs = {}
        if maxsize is not Ellipsis:
            kwargs['maxsize'] = maxsize
        if typed is not Ellipsis:
            kwargs['typed'] = typed
        wrapper = old_lru_cache(**kwargs)

        # Mimicking lru_cache: https://github.com/python/cpython/blob/v3.7.2/Lib/functools.py#L476-L478
        @wraps(wrapper)
        def decorating_function(user_function):
            """Wraps the user function, which is what everyone is actually using. Including us."""
            _wrapper = wrapper(user_function)
            if lru_cache_disabled_modules:
                for module_path in lru_cache_disabled_modules:
                    if user_function.__module__.startswith(module_path):
                        CACHED_FUNCTIONS.append(_wrapper)
                        break
            else:
                CACHED_FUNCTIONS.append(_wrapper)
            return _wrapper

        return decorating_function

    # Monkey patch the wrapped lru_cache decorator
    functools.lru_cache = lru_cache_wrapper

    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_collection(session):
    yield
    # Be a good citizen and undo our monkeying
    functools.lru_cache = old_lru_cache


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):  # pylint: disable=unused-argument
    """Call cache_clear on every cache_function, after every test run."""
    for function in CACHED_FUNCTIONS:
        function.cache_clear()

    yield
