# Architecture

How `pytest-antilru` intercepts `functools.lru_cache`, what that covers, and what it does not.

## Purpose

`functools.lru_cache` persists across tests. A value cached in one test is still cached in the next,
so mocks applied later have no effect and tests become order-dependent. This plugin clears those
caches after every test so that state does not leak between tests.

The goal is limited to that. The plugin does not disable caching, and it does not change how
`lru_cache` behaves outside a pytest session.

## Mechanism

The plugin works by replacing `functools.lru_cache` with a wrapper for part of the pytest run. The
wrapper delegates to the real `lru_cache`, so caching behaves normally, and additionally records the
cache object it just created. A teardown hook then clears every recorded cache after each test.

Three hooks, in `pytest_antilru/main.py`:

| hook | what it does |
| --- | --- |
| `pytest_load_initial_conftests` | saves the real `lru_cache`, installs the wrapper |
| `pytest_collection` (after yield) | restores the real `lru_cache` |
| `pytest_runtest_teardown` (after yield) | calls `cache_clear()` on every recorded cache |

Recording happens in `cache_user_function`, which appends to the module-level `CACHED_FUNCTIONS`
list. Both decorator forms route through it: `@lru_cache` with no parentheses, where the user
function arrives as the first positional argument, and `@lru_cache()` with parentheses, where the
wrapper returns a decorating function first.

### Why the patch is installed in `pytest_load_initial_conftests`

The wrapper only records caches that are created while it is installed, so it has to be installed
before any application code is imported. `pytest_load_initial_conftests` is the earliest practical
hook, and it is marked `tryfirst` to run ahead of other plugins that use the same hook.

This was a fix for a concrete problem: pytest-django calls `django.setup()` from
`pytest_load_initial_conftests`, which imports application modules through `AppConfig.ready`. Before
the fix, those imports happened before the patch was installed and their caches were never recorded.

### Why the patch is removed at the end of collection

The plugin restores `functools.lru_cache` so that it is not left monkey-patched any longer than
necessary. The restore was originally at the end of `pytest_load_initial_conftests` and was moved to
the end of collection, because restoring before test modules were imported was too early to record
anything useful.

## The interception window

Collection is the phase where pytest imports test modules, and therefore transitively imports the
application code those test modules import. The patch is installed for that whole phase, so every
`lru_cache` applied during those imports is recorded.

That is the case the plugin is built for: a `@lru_cache` decorator on a module-level function, in a
module that is reachable by importing your tests.

### `functools.cache` is covered too

`functools.cache` is not a separate cache implementation. CPython defines it as:

```python
def cache(user_function, /):
    'Simple lightweight unbounded cache.  Sometimes called "memoize".'
    return lru_cache(maxsize=None)(user_function)
```

`lru_cache` is resolved from the `functools` module globals on every call, so replacing the
`functools.lru_cache` attribute also changes what `functools.cache` uses. This is an implementation
detail rather than a documented contract: if `functools.cache` is ever reimplemented without calling
through `lru_cache` at call time, this plugin would silently stop covering it. `tests/main_test.py`
carries a regression test against this specifically because of that fragility.

## What is not covered

A cache is only recorded if the call that creates it reaches the wrapper. Two situations where it
does not.

### Modules first imported during test execution

If application code imports inside a function body, that module is not imported during collection. It
is imported the first time that function runs, which is during a test, after the patch has been
removed. Its module-level `@lru_cache` decorators are applied against the real `lru_cache` and are
never recorded.

Function-body imports are usually a workaround for a circular import, or a way to defer an optional
or slow dependency. PEP 8 asks for imports at the top of the module, and code that follows that is
covered normally. This is a known gap and is not planned for a fix.

### `lru_cache` applied at runtime rather than as a decorator

```python
class Client:
    def __init__(self, conn):
        self._lookup = functools.lru_cache(self._lookup_uncached)
```

The call happens when the object is constructed, which for most tests is during the test rather than
during collection. The same applies to any memoizing factory or helper that calls `lru_cache` at
runtime.

### Consequence

In both cases the cache keeps its values across tests. Nothing is raised and nothing is logged, so a
test polluted by one of these caches looks exactly like a test polluted by no plugin being installed
at all. When debugging suspected cache pollution with this plugin active, check for these two
patterns first.

## Name binding, and why some runtime caches are recorded anyway

Restoring the patch rebinds the attribute `functools.lru_cache`. It cannot reach names that were
bound to the wrapper object elsewhere.

A module that ran `from functools import lru_cache` during collection holds its own reference to the
wrapper in its globals. The restore does not touch that reference. If such a module calls
`lru_cache(...)` at runtime, the call still reaches the wrapper and the cache is still recorded. A
module that ran `import functools` instead performs a fresh attribute lookup on every call, gets the
restored original, and its runtime caches are not recorded.

Two modules that are otherwise identical therefore behave differently, based only on import style:

| module, imported during collection | runtime `lru_cache(...)` call | recorded |
| --- | --- | --- |
| `from functools import lru_cache` | resolves to the wrapper, via the binding made at import | yes |
| `import functools` | resolves to the restored original | no |

This is an artifact of how monkey-patching interacts with `from X import Y`, not a designed feature.
Do not rely on it. The guarantee is the one stated above: caches created during collection are
recorded.

## The allowlist

By default every recorded cache is cleared. The `lru_cache_disabled` ini option narrows that to the
modules listed, based on the decorated function's `__module__`. See `README.md` for the option's
semantics.

The allowlist filters what is recorded, not what is intercepted. The patch is installed and removed
at the same points regardless of the option's value.
