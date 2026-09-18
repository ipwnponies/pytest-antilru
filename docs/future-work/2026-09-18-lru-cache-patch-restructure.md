# Restructure the `lru_cache` patch around a mode flag

This document is a self-contained implementation prompt. A session can pick it up without reading the
audit discussion that produced it.

**Status:** ready, once
[`2026-09-18-functools-cache-coverage.md`](2026-09-18-functools-cache-coverage.md) has landed. That
work adds the `@functools.cache` regression test, which is the guard for the rewrite in commit 2
here.

Four commits, all in `pytest_antilru/main.py`. Each must pass the full `tox` matrix on its own. They
are ordered by dependency: commit 1 is independent and goes first so it does not get tangled in
commit 2's closure rewrite; commit 3 simplifies the function body commit 2 rewrites, so it cannot
come earlier.

This closes audit findings 1, 6 and 7 in `docs/audit-2026-09-13.md`, the unresolved sub-issue
recorded under finding 4, and the convention note in finding 8.

## Background

Three facts drive the design. All three were measured.

### The patch leaks on some exit paths

The patch is installed in `pytest_load_initial_conftests` and removed after `pytest_collection`
yields. Several pytest exit paths never reach `pytest_collection`, so the patched
`functools.lru_cache` survives for the rest of the interpreter's life:

| exit path | patch installed | `pytest_collection` restores | `pytest_unconfigure` runs |
| --- | --- | --- | --- |
| normal run | yes | yes | yes |
| `--collect-only` | yes | yes | yes |
| no tests found | yes | yes | yes |
| `-h` | yes | no | yes |
| usage error (unknown option) | yes | no | no |
| conftest raises on import | yes | no | no |
| `--version` | no | not applicable | not applicable |

`pytest_unconfigure` is strictly better than `pytest_collection`, and is still not complete. Do not
plan around it being complete.

### A leaked patch makes the next in-process session recurse forever

`old_lru_cache` is a module-level global, reassigned on every install:

```python
global old_lru_cache
old_lru_cache = functools.lru_cache
```

A second pytest session in the same interpreter runs that line while the wrapper from the first
session is still installed, so `old_lru_cache` becomes the wrapper. The wrapper then calls itself:

```
INTERNALERROR>     wrapper = old_lru_cache(**kwargs)
```

This is dormant today because the suite never runs two sessions in one interpreter. It becomes a hard
blocker the moment `pytester` is adopted, which is why
`docs/future-work/2026-09-13-pytester-rewrite.md` insists on `runpytest_subprocess`.

### Restoring the attribute cannot reach every name bound to the wrapper

`functools.lru_cache = old_lru_cache` rebinds one attribute on one module. A module that ran
`from functools import lru_cache` during collection holds its own reference to the wrapper object in
its globals, and the restore cannot reach it. Its runtime `lru_cache(...)` calls keep registering. A
module that ran `import functools` does a fresh attribute lookup, gets the restored original, and
does not register.

Verified with two modules differing only in import style, both creating a cache at runtime during the
same test: `from_import currsize: 0` (cleared) and `attr_access currsize: 1` (not cleared).

So the real predicate is not "was the cache created before the restore" but "did this call site's
name resolution reach the wrapper object". Two otherwise identical modules behave differently based
on a stylistic choice, and unlike the plugin's other documented gaps, this one lands on code that
follows PEP 8.

### The design that follows

Stop removing the patch to stop recording. Keep one wrapper installed and switch what it does.

Recording is controlled by a module-level flag rather than by the presence of the patch. When the
flag is off, the wrapper delegates straight to the real `lru_cache` and is behaviourally transparent.
The attribute is still restored, at `pytest_unconfigure`, to keep the good-citizen property on the
paths that reach it. On the two paths that do not, what leaks is a transparent pass-through rather
than a recording wrapper, which turns finding 1's leak from a correctness problem into a cosmetic
one.

The flag must be a module global read at call time, not a value captured in the wrapper's closure.
That is what makes a stale wrapper object, held in some module's globals by a `from` import, obey the
current session's mode instead of the mode in force when it was created.

## Commit 1: reset the registry when the patch is installed

Closes the one surviving claim of audit finding 6.

`CACHED_FUNCTIONS` is never reset. Across two pytest sessions in one interpreter, the second session's
teardowns keep calling `cache_clear()` on wrappers registered by the first. Add
`CACHED_FUNCTIONS.clear()` at install, in `pytest_load_initial_conftests`, before the patch goes in.

One line plus a test. Do this first, while the surrounding function is still the code the audit
describes.

The other two claims in finding 6 were measured and rejected, so do not act on them. Weak references
would drop nothing: `cache_user_function` records the same object that is simultaneously bound to a
module global or class attribute, so the defining namespace already holds it. Measured `held only by
CACHED_FUNCTIONS: 0 of 3`. And the linear teardown cost is real but negligible, timed at 12.5
microseconds per teardown for 200 entries.

## Commit 2: capture the real `lru_cache` once, switch modes instead of unpatching

Closes audit finding 1 and the unresolved sub-issue under finding 4.

Capture the real implementation once, at plugin module import, before any patch can exist:

```python
# Captured at import, before any patch can be installed. Re-reading functools.lru_cache at
# install time is what makes a second in-process session wrap our own wrapper and recurse.
_REAL_LRU_CACHE = functools.lru_cache
```

Remove the `old_lru_cache` global and its reassignment.

Add a module-level recording flag. Set it true at install in `pytest_load_initial_conftests`. Set it
false after `pytest_collection` yields, in place of the current attribute restore. Read it inside the
wrapper on every call:

```python
def lru_cache_wrapper(*args, **kwargs):
    if not _recording:
        return _REAL_LRU_CACHE(*args, **kwargs)
    ...
```

Add `pytest_unconfigure` to restore `functools.lru_cache = _REAL_LRU_CACHE`.

Keep `pytest_collection` as a hookwrapper; only its post-yield body changes. The interception window
must not move. Recording still starts at `pytest_load_initial_conftests` and still ends when
collection finishes. This commit changes which call sites the window applies to, not where its edges
are.

### What this changes for users

It narrows behaviour. Modules that imported `lru_cache` by name currently get their runtime-created
caches registered and cleared, by accident. After this commit they do not, which makes them agree
with modules that use `functools.lru_cache`. The documented rule in `README.md` and
`docs/architecture.md` becomes true rather than approximately true.

That is a removal of working behaviour, so it belongs in a minor release, not a patch. Say so in
`CHANGELOG.md`.

Update the "Name binding, and why some runtime caches are recorded anyway" passage in
`docs/architecture.md`, including its import-style table. That passage documents the asymmetry this
commit removes, so leaving it would be actively wrong.

### Tests

- A second install in the same interpreter does not produce a self-recursive wrapper. Call
  `pytest_load_initial_conftests` twice and assert a subsequent `lru_cache` call returns rather than
  hitting the recursion limit.
- With recording off, a `lru_cache` call through the still-installed wrapper does not append to
  `CACHED_FUNCTIONS`, and the returned cache behaves like a normal `lru_cache`.
- `pytest_unconfigure` restores `functools.lru_cache` to the real implementation.

## Commit 3: let the runtime decide which decorator form was used

Closes audit finding 7.

The current wrapper reimplements `lru_cache`'s own argument parsing. It defaults `maxsize` and
`typed` to `Ellipsis`, because `None` is a legal `maxsize` and a `None` default could not distinguish
"not passed" from "passed as `None`". It then rebuilds a kwargs dict. On the way it does this:

```python
if kwargs:
    logging.warning('Unexpected kwargs, maybe an update in functools.lru_cache')
...
kwargs = {}
```

Anything beyond `maxsize` and `typed` is dropped, so the call degrades to plain defaults instead of
raising the `TypeError` the real `lru_cache` would raise. The warning goes to the root logger, so it
never appears in pytest's warnings summary and cannot be filtered with `-W`. A typo like
`lru_cache(max_size=128)` passes under test and fails in production.

Forward the arguments verbatim and discriminate on what comes back:

```python
result = _REAL_LRU_CACHE(*args, **kwargs)

# lru_cache has two forms. Applied bare, lru_cache(fn) returns the finished cache
# wrapper, which carries cache_clear. Called with options, lru_cache(maxsize=128)
# returns a decorating function with no cache_clear, which must still be applied
# to the user function.
if hasattr(result, 'cache_clear'):
    cache_user_function(result.__wrapped__, result, lru_cache_disabled_modules)
    return result

@wraps(result)
def decorating_function(user_function):
    wrapper = result(user_function)
    cache_user_function(user_function, wrapper, lru_cache_disabled_modules)
    return wrapper

return decorating_function
```

`lru_cache` finishes with `update_wrapper(wrapper, user_function)`, so `result.__wrapped__` is the
user function and `result.__module__` is copied from it. Either can serve `cache_user_function`,
which only reads `__module__`. `__wrapped__` is chosen here because it keeps the helper's two
arguments meaning what their names say. Using `args[0]` instead would be wrong for the legal but
unusual `lru_cache(maxsize=fn)` spelling.

This deletes the `Ellipsis` sentinels, the kwargs rebuild, the silent discard, the `logging.warning`,
and the `import logging` if nothing else uses it. Bad keyword arguments now raise `TypeError` from
CPython at the point of the call, under test, which is the behaviour the plugin should never have
suppressed.

It also deletes `tests/main_test.py::test_lru_cache_unknown_kwargs`, which asserts the warning that
no longer exists. Replace it with a test asserting that an unknown keyword argument raises
`TypeError`.

Optional, and not required by this commit: `cache_user_function`'s first parameter becomes redundant
once both call sites can pass the wrapper for both arguments. Collapsing it would simplify the helper
but changes a signature that `tests/cache_user_function_test.py` covers directly. Leave it unless the
resulting code is clearly better.

## Commit 4: register the ini option in `pytest_addoption`

Closes audit finding 8, which is a convention note rather than a defect.

`parser.addini('lru_cache_disabled', ...)` currently sits inside `pytest_load_initial_conftests`.
Registration belongs in `pytest_addoption`. Move the line into a new `pytest_addoption(parser)` hook
and leave the `early_config.getini('lru_cache_disabled')` read where it is.

Both consequences the audit originally claimed for this were measured and are false, so do not repeat
them in the commit message. `pytest --help` already lists `lru_cache_disabled (linelist)` with its
help text, confirmed against a `-p no:antilru` control, and a duplicate `addini` raises nothing:
`_pytest/config/argparsing.py` does a plain dict assignment. `pytest_addoption` runs before
`pytest_load_initial_conftests`, so the `getini` read continues to work. The only reason to make this
change is convention, and that is reason enough. Say exactly that.

## Constraints

**Run the full matrix.** `make test` runs `tox` across 19 pytest environments, from pytest 3 to
pytest 9 across Python 3.9 to 3.13. This work changes the core wrapper, so a plain `pytest` run
proves very little.

**Expect one pre-existing failure.** The `project_tests` environment fails in `pre-commit` with
`ModuleNotFoundError: No module named 'lib2to3'`, raised by `autopep8` inside the pre-commit cache.
That is environmental and not caused by repository code. Every one of the 19 pytest environments must
pass; any failure there is yours.

**Coverage is gated at 100 percent** for both `pytest_antilru` and `tests`, by two separate
`coverage report --fail-under 100` invocations in `tox.ini`. Every new branch needs a test. The
pass-through branch added in commit 2 is easy to miss.

**Do not disturb the teardown ordering invariant.** `pytest_runtest_teardown` is a `tryfirst`
hookwrapper specifically so its cache-clearing code, after the `yield`, runs last. A cached value
stays visible through a test's own fixture teardown and is gone by the next test.
`tests/teardown_order_test.py` and the hookwrapper probe in `tests/conftest.py` lock this in.

**Do not reorder the `tox.ini` commands block.** It runs the `main_test.py` pair forward and then in
reverse, deliberately, to prove cache busting works regardless of execution order.

**Python 3.9 is the floor**, per `pyproject.toml`. Bare `@lru_cache` without parentheses is available
from 3.8, so the return-value discrimination in commit 3 is safe across the supported range.

## Changelog

Commit 1 and commit 2 are user-visible. Commit 2 in particular removes behaviour that works today,
which makes this a minor release rather than a patch. Commits 3 and 4 change internals; commit 3's
switch from a silently-swallowed warning to a real `TypeError` is worth an entry.
