# Please don't use this, it's inconsistent and will be monkey-patched left and right.
# We're only importing it to update functools module's reference
import functools
from functools import wraps  # pylint: disable=ungrouped-imports

import pytest

if not hasattr(functools, 'lru_cache'):  # pragma: no cover
    # Several py2 backport packages
    try:
        import backports.functools_lru_cache as functools
    except ImportError:
        # functools32 py2 backport
        try:
            import functools32 as functools
        except ImportError:
            raise AssertionError('Cannot use pytest-antilru, no lru_cache installed!')


CACHED_FUNCTIONS = []


@pytest.hookimpl(hookwrapper=True)
def pytest_collection(session):  # pylint: disable=unused-argument
    """Monkey patch lru_cache, before any module imports occur."""

    # Gotta hold on to this before we patch it away
    old_lru_cache = functools.lru_cache

    @wraps(functools.lru_cache)
    def lru_cache_wrapper(*args, **kwargs):
        """Wrap lru_cache decorator, to track which functions are decorated."""

        # Apply lru_cache params (maxsize, typed)
        decorated_function = old_lru_cache(*args, **kwargs)

        # Mimicking lru_cache: https://github.com/python/cpython/blob/v3.7.2/Lib/functools.py#L476-L478
        @wraps(decorated_function)
        def decorating_function(user_function):
            """Wraps the user function, which is what everyone is actually using. Including us."""
            wrapper = decorated_function(user_function)
            CACHED_FUNCTIONS.append(wrapper)
            return wrapper

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
