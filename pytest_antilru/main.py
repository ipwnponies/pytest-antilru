# Please don't use this, it's inconsistent and will be monkey-patched left and right.
# We're only importing it to update functools module's reference
import functools
import logging
from functools import wraps  # pylint: disable=ungrouped-imports

import pytest

# Captured at import, before any patch can exist. Re-reading functools.lru_cache at install
# time is what makes a second in-process session wrap our own wrapper and recurse.
_REAL_LRU_CACHE = functools.lru_cache

CACHED_FUNCTIONS = []
_recording = False


def is_module_covered(module: str, disabled_modules) -> bool:
    """Match on module-path boundaries: app.util covers app.util and app.util.helpers, not app.utilities."""
    return any(module == module_path or module.startswith(module_path + '.') for module_path in disabled_modules)


def cache_user_function(user_function, wrapper, lru_cache_disabled_modules: bool):
    if lru_cache_disabled_modules:
        # __module__ may be missing or None, e.g. for C-implemented methods. Treat as
        # uncovered, don't crash.
        module = getattr(user_function, '__module__', None) or ''
        if is_module_covered(module, lru_cache_disabled_modules):
            CACHED_FUNCTIONS.append(wrapper)
    else:
        CACHED_FUNCTIONS.append(wrapper)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_load_initial_conftests(early_config, parser, args):  # pylint: disable=unused-argument
    """Monkey patch lru_cache, before any module imports occur."""
    parser.addini('lru_cache_disabled', 'Allowlist of module prefixes to apply disable lru_cache on', type='linelist')
    lru_cache_disabled_modules = early_config.getini('lru_cache_disabled')

    # Reset in case a prior in-process session left wrappers registered.
    CACHED_FUNCTIONS.clear()

    global _recording
    _recording = True

    @wraps(_REAL_LRU_CACHE)
    def lru_cache_wrapper(maxsize=Ellipsis, typed=Ellipsis, **kwargs):
        """Wrap lru_cache decorator, to track which functions are decorated.

        Reads the _recording module global on every call, rather than closing over its value, so a
        wrapper object kept alive by a `from functools import lru_cache` binding still obeys the
        current session's mode instead of the mode in force when it was created.
        """

        if kwargs:
            logging.warning('Unexpected kwargs, maybe an update in functools.lru_cache')

        # When decorator is called without params, user function is first arg (maxsize)
        if callable(maxsize) and typed is Ellipsis:
            user_function = maxsize
            wrapper = _REAL_LRU_CACHE(user_function)
            if _recording:
                cache_user_function(user_function, wrapper, lru_cache_disabled_modules)
            return wrapper

        # Apply lru_cache params (maxsize, typed)
        kwargs = {}
        if maxsize is not Ellipsis:
            kwargs['maxsize'] = maxsize
        if typed is not Ellipsis:
            kwargs['typed'] = typed
        wrapper = _REAL_LRU_CACHE(**kwargs)

        # Mimicking lru_cache: https://github.com/python/cpython/blob/v3.7.2/Lib/functools.py#L476-L478
        @wraps(wrapper)
        def decorating_function(user_function):
            """Wraps the user function, which is what everyone is actually using. Including us."""
            _wrapper = wrapper(user_function)
            if _recording:
                cache_user_function(user_function, _wrapper, lru_cache_disabled_modules)
            return _wrapper

        return decorating_function

    # Monkey patch the wrapped lru_cache decorator
    functools.lru_cache = lru_cache_wrapper

    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_collection(session):
    yield
    # Stop recording rather than unpatching. A wrapper object a module bound by name during
    # collection (e.g. `from functools import lru_cache`) survives this and stays installed there;
    # reading this flag at call time is what makes it fall back to plain lru_cache behaviour anyway.
    global _recording
    _recording = False


def pytest_unconfigure(config):  # pylint: disable=unused-argument
    """Restore the real lru_cache attribute.

    This reaches more pytest exit paths than pytest_collection's restore, though still not all of
    them. Whatever wrapper object survives on the paths neither reaches can no longer self-recurse,
    since it always calls _REAL_LRU_CACHE rather than whatever functools.lru_cache happens to be at
    call time.
    """
    functools.lru_cache = _REAL_LRU_CACHE


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_teardown():
    """Call cache_clear on every cache_function, after every test run.

    This hook is intended to run after all hooks and hook wrappers. This is why it's a try-first hookwrapper, and the
    implementation is after returning from yield. This shifts pytest hook registration to pick this first and also make
    it last to unwrap.
    """
    yield

    for function in CACHED_FUNCTIONS:
        function.cache_clear()
