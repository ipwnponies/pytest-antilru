# Please don't use this, it's inconsistent and will be monkey-patched left and right.
# We're only importing it to update functools module's reference
import functools
import logging
from functools import wraps  # pylint: disable=ungrouped-imports

import pytest

CACHED_FUNCTIONS = []


@pytest.hookimpl(hookwrapper=True)
def pytest_collection(session):  # pylint: disable=unused-argument
    """Monkey patch lru_cache, before any module imports occur."""

    # Gotta hold on to this before we patch it away
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
            CACHED_FUNCTIONS.append(_wrapper)
            return _wrapper

        return decorating_function

    # Monkey patch the wrapped lru_cache decorator
    functools.lru_cache = lru_cache_wrapper

    yield

    # Be a good citizen and undo our monkeying
    functools.lru_cache = old_lru_cache


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):  # pylint: disable=unused-argument
    """Call cache_clear on every cache_function, after every test run."""
    for function in CACHED_FUNCTIONS:
        function.cache_clear()

    yield
