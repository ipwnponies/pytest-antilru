# Architecture

How `pytest-antilru` intercepts `functools.lru_cache`, what that covers, and what it does not.

## Purpose

`functools.lru_cache` persists across tests. A value cached in one test is still cached in the next,
so mocks applied later have no effect and tests become order-dependent. This plugin clears those
caches after every test so that state does not leak between tests.

The goal is limited to that. The plugin does not disable caching, and it does not change how
`lru_cache` behaves outside a pytest session.

## Mechanism

The plugin works by installing one wrapper in place of `functools.lru_cache` for the whole pytest
session. The wrapper always delegates to the real `lru_cache`, captured once at import as
`_REAL_LRU_CACHE`, so caching behaves normally. Whether it additionally records the cache object it
just created is controlled by a module-level recording flag, read fresh on every call rather than
captured once. A teardown hook then clears every recorded cache after each test.

Four hooks, in `pytest_antilru/main.py`:

| hook | what it does |
| --- | --- |
| `pytest_load_initial_conftests` | installs the wrapper, turns recording on |
| `pytest_collection` (after yield) | turns recording off |
| `pytest_unconfigure` | restores the real `lru_cache` attribute |
| `pytest_runtest_teardown` (after yield) | calls `cache_clear()` on every recorded cache |

Recording happens in `cache_user_function`, which appends to the module-level `CACHED_FUNCTIONS`
list. Both decorator forms route through it: `@lru_cache` with no parentheses, where the user
function arrives as the first positional argument, and `@lru_cache()` with parentheses, where the
wrapper returns a decorating function first.

### Why the patch is installed in `pytest_load_initial_conftests`

The wrapper only records caches that are created while recording is on, so it has to be installed
before any application code is imported. `pytest_load_initial_conftests` is the earliest practical
hook, and it is marked `tryfirst` to run ahead of other plugins that use the same hook.

This was a fix for a concrete problem: pytest-django calls `django.setup()` from
`pytest_load_initial_conftests`, which imports application modules through `AppConfig.ready`. Before
the fix, those imports happened before the patch was installed and their caches were never recorded.

### Why recording stops at the end of collection, rather than unpatching

Earlier versions of this plugin removed the patch entirely at the end of collection, by rebinding
`functools.lru_cache` back to the real implementation. That had two problems.

First, restoring an attribute cannot reach a name a module already bound to the wrapper by running
`from functools import lru_cache` during collection; see the next section. Second, and more serious,
a second pytest session in the same interpreter (for example, a `pytester` inner run) would capture
whatever `functools.lru_cache` currently was, at that second session's install, into what the wrapper
treats as "the real implementation". If the first session's patch had leaked (many pytest exit paths
never reach `pytest_collection`; see the exit-path table in
`docs/future-work/2026-09-18-audit-remediation.md`), the second session captured the first session's
own wrapper as real, and every cache lookup recursed into it forever.

The fix keeps one wrapper installed for the life of the process and switches what it does instead of
removing it. `_REAL_LRU_CACHE` is captured once, at module import, before any patch can exist, so a
later install never re-reads a possibly-already-patched `functools.lru_cache`. `pytest_collection`
now turns the recording flag off rather than restoring the attribute, and `pytest_unconfigure`
restores the attribute, as a best-effort cleanup on the exit paths it reaches. That is more paths than
`pytest_collection` reaches, though still not all of them; what can survive on the paths neither
reaches is a wrapper that can no longer self-recurse, because it never reads `functools.lru_cache` to
find "the real implementation" in the first place.

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

## Name binding no longer matters

Earlier versions of this plugin stopped recording by rebinding the attribute `functools.lru_cache`
back to the real implementation. That could not reach a name a module had already bound to the
wrapper by running `from functools import lru_cache` during collection: such a module's runtime
`lru_cache(...)` calls kept reaching the wrapper and kept being recorded, while a module that ran
`import functools` instead got the restored original on every call and was not. Two modules that
were otherwise identical behaved differently, based only on import style.

Recording is now controlled by a module-level flag, read fresh on every call rather than captured in
the wrapper's closure. Once `pytest_collection` turns it off, every surviving wrapper stops recording
on its very next call, regardless of which name resolution path reached it or when that wrapper
object was created. The guarantee from "What is not covered" is exact now, not approximate: a cache
is recorded if and only if it is created while recording is on, from install in
`pytest_load_initial_conftests` (before collection starts, so `pytest-django`'s `django.setup()`
imports are covered too; see above) through the end of collection.

## The allowlist

By default every recorded cache is cleared. The `lru_cache_disabled` ini option narrows that to the
modules listed, based on the decorated function's `__module__`. See `README.md` for the option's
semantics.

The allowlist filters what is recorded, not what is intercepted. The patch is installed and removed
at the same points regardless of the option's value.
