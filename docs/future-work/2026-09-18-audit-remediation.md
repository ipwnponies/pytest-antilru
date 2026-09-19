# Close out the remaining audit findings

This document is a self-contained implementation prompt. A session can pick it up without reading the
triage discussion that produced it.

**Status:** ready. Nothing blocks it.

Six commits, executed in one session, in the order given. This closes audit findings 1, 6, 7 and 9 in
`docs/audit-2026-09-13.md`, the unresolved sub-issue recorded under finding 4, and the convention note
in finding 8. Findings 2 and 3 already shipped in commit `e7d8451`; findings 4 and 5 are closed
without code changes.

## How to run this

Stop after every commit and wait for review before starting the next one. The work is serial: each
commit changes code the next one builds on, so a rejected design at commit 3 invalidates commits 4
and 5 as written.

At each checkpoint, report:

1. The commit message.
2. The diff, or a summary of it if it is long.
3. The result of `make test`, including which of the 19 pytest environments passed.

Do not batch commits. Do not proceed past a checkpoint without an explicit go-ahead. If review
changes a design decision, say which later commits it affects before continuing.

Each commit must pass the full matrix on its own. That is what makes them independently revertible,
and it is the reason for the ordering below rather than a single large change.

## Why this order

Commit 1 is the regression guard for commit 3. It pins `@functools.cache` behaviour before the
wrapper that provides it gets rewritten.

Commit 2 is independent and small. It goes before commit 3 so it does not get tangled in that
commit's closure rewrite.

Commit 4 simplifies the function body commit 3 rewrites, so it cannot come earlier.

Commit 6 records outcomes, so it comes last, once every outcome is known.

## Background

Three measured facts drive the design in commit 3. All three were verified, not reasoned about.

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
than a recording wrapper, which turns the leak from a correctness problem into a cosmetic one.

The flag must be a module global read at call time, not a value captured in the wrapper's closure.
That is what makes a stale wrapper object, held in some module's globals by a `from` import, obey the
current session's mode instead of the mode in force when it was created.

## Commit 1: cover `@functools.cache`

Closes audit finding 9. Tests and documentation only; no change to `pytest_antilru/main.py`.

### Why

`functools.cache` is covered by the plugin today, but nothing in the repository says so and nothing
locks it in. Searching `README.md`, `docs/architecture.md`, `AGENTS.md`, `CHANGELOG.md` and `tests/`
for `functools.cache` returns no matches.

Coverage is a consequence of how CPython implements it:

```python
def cache(user_function, /):
    'Simple lightweight unbounded cache.  Sometimes called "memoize".'
    return lru_cache(maxsize=None)(user_function)
```

`lru_cache` is resolved from the `functools` module globals on every call, so replacing the
`functools.lru_cache` attribute also changes what `functools.cache` uses. That source is identical on
Python 3.9 and 3.13, verified.

It is an implementation detail, not a documented contract. If `functools.cache` is ever reimplemented
in C, or binds `lru_cache` at definition time instead of resolving it per call, the plugin silently
stops covering `@cache`. No test fails today, and the user would see test pollution return with no
signal. `functools.cache` was added in Python 3.9, this package's minimum supported version, and it
is the idiom most new code reaches for.

### The test

`tests/main_test.py` already parametrizes a fixture over the two decorator forms:

```python
@pytest.fixture(params=[cache_me_lru_cache, cache_me_empty_decorator_call])
def cache_function(request):
```

Add a third module-level cached function using `@functools.cache` and add it to that `params` list.
It then inherits `test_a_run_first`, `test_b_run_second`, and the teardown-ordering probe in
`tests/conftest.py` with no new test functions.

`tests/main_test.py` currently imports with `from functools import lru_cache`. Import `functools` and
use `@functools.cache`, or add `from functools import cache`. Either works; pick whichever reads
consistently with the surrounding module.

### Verify the knock-on effect

`tests/allowlist_test.py` imports `cache_function` from `tests/main_test.py`, so adding a parameter
changes that module's parametrization too. The new function lives in `tests.main_test`, the same
module as the existing two, so the allowlist assertions should behave identically. Confirm this
rather than assuming it: `tox.ini` runs `tests/allowlist_test.py` under three separate ini configs.

### Documentation

- `README.md`, in the "What gets busted" section: state that `@functools.cache` is covered alongside
  `@lru_cache`.
- `docs/architecture.md`: add a short passage explaining that `functools.cache` is reached through
  the same attribute patch, quoting the CPython source above, and naming the dependency on that
  implementation detail as the reason the regression test exists.

## Commit 2: reset the registry when the patch is installed

Closes the one surviving claim of audit finding 6.

`CACHED_FUNCTIONS` is never reset. Across two pytest sessions in one interpreter, the second session's
teardowns keep calling `cache_clear()` on wrappers registered by the first. Add
`CACHED_FUNCTIONS.clear()` at install, in `pytest_load_initial_conftests`, before the patch goes in.

One line plus a test.

The other two claims in finding 6 were measured and rejected, so do not act on them. Weak references
would drop nothing: `cache_user_function` records the same object that is simultaneously bound to a
module global or class attribute, so the defining namespace already holds it. Measured `held only by
CACHED_FUNCTIONS: 0 of 3`. The linear teardown cost is real but negligible, timed at 12.5 microseconds
per teardown for 200 entries.

## Commit 3: capture the real `lru_cache` once, switch modes instead of unpatching

Closes audit finding 1 and the unresolved sub-issue under finding 4. This is the commit that changes
user-visible behaviour; review it hardest.

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

## Commit 4: let the runtime decide which decorator form was used

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

Measured on Python 3.9 and 3.13:

| call | type returned | has `cache_clear` | `__wrapped__` |
| --- | --- | --- | --- |
| `lru_cache(f)` | `_lru_cache_wrapper` | yes | `f` |
| `lru_cache()` | `function` | no | absent |
| `lru_cache(128)` | `function` | no | absent |
| `lru_cache(maxsize=None)` | `function` | no | absent |
| `lru_cache(maxsize=f)` | `_lru_cache_wrapper` | yes | `f` |

The last row is why this uses `result.__wrapped__` and not `args[0]`. CPython treats
`lru_cache(maxsize=f)` as the bare form, so `args[0]` would raise `IndexError`. `lru_cache` finishes
with `update_wrapper(wrapper, user_function)`, so `__wrapped__` is the user function and
`__module__` is copied from it. Either could serve `cache_user_function`, which only reads
`__module__`; `__wrapped__` is chosen because it keeps the helper's two arguments meaning what their
names say.

This deletes the `Ellipsis` sentinels, the kwargs rebuild, the silent discard, the `logging.warning`,
and the `import logging` if nothing else uses it. Bad keyword arguments now raise `TypeError` from
CPython at the point of the call, under test, which is the behaviour the plugin should never have
suppressed.

It also deletes `tests/main_test.py::test_lru_cache_unknown_kwargs`, which asserts the warning that
no longer exists. Replace it with a test asserting that an unknown keyword argument raises
`TypeError`.

Optional, and not required: `cache_user_function`'s first parameter becomes redundant once both call
sites could pass the wrapper for both arguments. Collapsing it would simplify the helper but changes
a signature that `tests/cache_user_function_test.py` covers directly. Leave it unless the resulting
code is clearly better, and raise it at the checkpoint rather than deciding alone.

## Commit 5: register the ini option in `pytest_addoption`

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

## Commit 6: retire the consumed prompts and record the outcomes

Documentation only. No behaviour change.

### Delete `docs/future-work-allowlist-boundary-match.md`

It was the implementation prompt for audit finding 3. The work shipped in commit `e7d8451`, which
added `is_module_covered` to `pytest_antilru/main.py`, along with `tests/cache_user_function_test.py`,
the `tests/pytest_lru_cache_allowlist.ini` fixture correction, and the README and CHANGELOG entries.
Finding 2's `__module__` guard rode along with it, as that document specified. The prompt has been
consumed.

### Delete `docs/future-work-pytester-migration.md`

It covered two things, and both have moved elsewhere. Its `pytester` adoption half duplicates
`docs/future-work/2026-09-13-pytester-rewrite.md`, which landed in commit `5c0c25d` and is the more
thorough treatment: it carries the `runpytest_subprocess` constraint, the subprocess-coverage
warning, and the two end states the trigger picks between. Its finding 1 half is superseded by
commit 3 of this document.

Check whether `docs/future-work/2026-09-13-pytester-rewrite.md` should gain a sentence noting that
finding 1 is now fixed, so a future reader of the pytester work is not left believing the crash is
still latent.

### Delete this document

It is consumed once commits 1 through 5 have landed.

### Correct `docs/audit-2026-09-13.md`

Mark findings 1, 2, 3, 6, 7, 8 and 9 closed, each citing the commit that closed it. Findings 2 and 3
shipped in `e7d8451`; the rest ship in this session.

Rewrite the "Suggested sequencing" section. As written it asserts blockers that do not exist: it
claims findings 6 and 7 are "blocked until finding 1's implementation lands". Finding 1 was never
implemented. Commit `5c0c25d` recorded the `pytester` rewrite as future work, and nothing touched
`old_lru_cache` or the `pytest_collection` restore. Replace the section with a record of what
shipped.

Record the exit-path measurement from the Background section above. It corrects a claim made during
triage, where `pytest_unconfigure` was assumed to run on every exit path. It does not: five of six
paths against four for `pytest_collection`. The restore is improved, not made complete, and the
residual leak is acceptable only because commit 3 leaves a pass-through wrapper behind rather than a
recording one.

### Convention

New future-work documents go in `docs/future-work/` and are named `<date>-<slug>.md`, following
`2026-09-13-pytester-rewrite.md`. The two flat `docs/future-work-*.md` files predate that convention,
which is a second reason to remove them rather than leave a split layout.

## Constraints

**Run the full matrix at every checkpoint.** `make test` runs `tox` across 19 pytest environments,
from pytest 3 to pytest 9 across Python 3.9 to 3.13. Commits 2 through 5 change the core wrapper, so
a plain `pytest` run proves very little.

**Expect one pre-existing failure.** The `project_tests` environment fails in `pre-commit` with
`ModuleNotFoundError: No module named 'lib2to3'`, raised by `autopep8` inside the pre-commit cache.
That is environmental and not caused by repository code. Every one of the 19 pytest environments must
pass; any failure there is yours. Report it as pre-existing at each checkpoint rather than silently
ignoring it.

**Coverage is gated at 100 percent** for both `pytest_antilru` and `tests`, by two separate
`coverage report --fail-under 100` invocations in `tox.ini`. Every new branch needs a test. The
pass-through branch added in commit 3 is easy to miss.

**Do not disturb the teardown ordering invariant.** `pytest_runtest_teardown` is a `tryfirst`
hookwrapper specifically so its cache-clearing code, after the `yield`, runs last. A cached value
stays visible through a test's own fixture teardown and is gone by the next test.
`tests/teardown_order_test.py` and the hookwrapper probe in `tests/conftest.py` lock this in.

**Do not reorder the `tox.ini` commands block.** It runs the `main_test.py` pair forward and then in
reverse, deliberately, to prove cache busting works regardless of execution order.

**Python 3.9 is the floor**, per `pyproject.toml`. Bare `@lru_cache` without parentheses is available
from 3.8, so the return-value discrimination in commit 4 is safe across the supported range.

## Changelog

Commits 1, 2 and 3 are user-visible. Commit 3 removes behaviour that works today, which makes this a
minor release rather than a patch. Commit 4's switch from a silently-swallowed warning to a real
`TypeError` is worth an entry. Commit 5 is internal, and commit 6 is documentation.
