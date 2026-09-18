# Lock in `functools.cache` coverage, and clear the stale future-work docs

This document is a self-contained implementation prompt. A session can pick it up without reading the
audit discussion that produced it.

**Status:** ready. Nothing blocks it.

**Ordering:** this work lands before
[`2026-09-18-lru-cache-patch-restructure.md`](2026-09-18-lru-cache-patch-restructure.md). The
regression test in commit 1 is the guard for that restructure, which rewrites the wrapper the test
exercises. Landing the test afterwards would mean rewriting the wrapper with no coverage of
`functools.cache` in place.

Two commits. Neither touches `pytest_antilru/main.py`.

## Commit 1: cover `@functools.cache`

Closes audit finding 9 in `docs/audit-2026-09-13.md`.

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
`functools.lru_cache` attribute also changes what `functools.cache` uses.

That is an implementation detail, not a documented contract. If `functools.cache` is ever
reimplemented in C, or binds `lru_cache` at definition time instead of resolving it per call, the
plugin silently stops covering `@cache`. No test fails today, and the user would see test pollution
return with no signal. `functools.cache` was added in Python 3.9, which is this package's minimum
supported version, and it is the idiom most new code reaches for.

### The test

`tests/main_test.py` already parametrizes a fixture over the two decorator forms:

```python
@pytest.fixture(params=[cache_me_lru_cache, cache_me_empty_decorator_call])
def cache_function(request):
```

Add a third module-level cached function using `@functools.cache` and add it to that `params` list.
It then inherits `test_a_run_first`, `test_b_run_second`, and the teardown-ordering probe in
`tests/conftest.py` with no new test functions.

Note that `tests/main_test.py` currently imports with `from functools import lru_cache`. Import
`functools` and use `@functools.cache`, or add `from functools import cache`. Either works; pick
whichever reads consistently with the surrounding module.

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

## Commit 2: retire the stale future-work documents

Housekeeping only. No behaviour change.

### Delete `docs/future-work-allowlist-boundary-match.md`

It was the implementation prompt for audit finding 3. The work shipped in commit `e7d8451`, which
added `is_module_covered` to `pytest_antilru/main.py`, along with `tests/cache_user_function_test.py`,
the `tests/pytest_lru_cache_allowlist.ini` fixture correction, and the README and CHANGELOG entries.
Finding 2's `__module__` guard rode along with it, as that document specified. The prompt has been
consumed.

### Delete `docs/future-work-pytester-migration.md`

It covered two things. Both have moved elsewhere.

Its `pytester` adoption half duplicates `docs/future-work/2026-09-13-pytester-rewrite.md`, which
landed on master in commit `5c0c25d` and is the more thorough treatment. It carries the
`runpytest_subprocess` constraint, the subprocess-coverage warning, and the two end states the
trigger picks between.

Its audit finding 1 half is superseded by
[`2026-09-18-lru-cache-patch-restructure.md`](2026-09-18-lru-cache-patch-restructure.md), which fixes
finding 1 as a consequence of the wrapper restructure rather than as a prerequisite for adopting
`pytester`.

Before deleting, check whether `docs/future-work/2026-09-13-pytester-rewrite.md` should gain a
sentence noting that finding 1 is handled separately, so a future reader of the pytester work is not
left believing the crash is still latent.

### Correct `docs/audit-2026-09-13.md`

The audit's own status lines and its "Suggested sequencing" section are now wrong in two ways.

Findings 2 and 3 are shipped. Mark both closed and cite `e7d8451`.

The sequencing section asserts blockers that do not exist. It claims findings 6 and 7 are "blocked
until finding 1's implementation lands". Finding 1 was never implemented: commit `5c0c25d` recorded
the `pytester` rewrite as future work, and `pytest_antilru/main.py` still reassigns `old_lru_cache` on
every install and still restores only in `pytest_collection`. Rewrite the section so it reflects the
two prompt documents in `docs/future-work/` and states plainly that nothing is blocked.

Also record the measurement below, which corrects a claim made during triage. It matters because the
restructure's design depends on it.

`pytest_unconfigure` was assumed to run on every exit path. It does not:

| exit path | patch installed | `pytest_unconfigure` runs |
| --- | --- | --- |
| normal run | yes | yes |
| `--collect-only` | yes | yes |
| no tests found | yes | yes |
| `-h` | yes | yes |
| usage error (unknown option) | yes | no |
| conftest raises on import | yes | no |
| `--version` | no | not applicable |

So moving the restore from `pytest_collection` to `pytest_unconfigure` improves coverage from four
exit paths to five, and does not reach six. The residual leak is acceptable only because the
restructure leaves a pass-through wrapper behind rather than a recording one.

### Convention

New future-work documents go in `docs/future-work/` and are named `<date>-<slug>.md`, following
`2026-09-13-pytester-rewrite.md`. The two flat `docs/future-work-*.md` files predate that convention,
which is a second reason to remove them rather than leave a split layout.

## Verification

Run `make test`, which runs the full `tox` matrix.

Expect one pre-existing failure unrelated to this work. The `project_tests` environment fails in
`pre-commit`:

```
ModuleNotFoundError: No module named 'lib2to3'
```

That comes from `autopep8` inside the pre-commit cache, not from repository code. All 19 pytest
environments should pass. If any of them fails, that failure is yours.

Coverage is gated at 100 percent for both `pytest_antilru` and `tests`, enforced by two separate
`coverage report --fail-under 100` invocations in `tox.ini`. A new cached function in
`tests/main_test.py` is exercised by the existing parametrized tests, so it should not open a gap,
but confirm rather than assume.

`tox.ini` also runs the `main_test.py` pair in forward and then reverse order, and
`tests/teardown_order_test.py` with the hookwrapper probe in `tests/conftest.py` locks in the
teardown ordering invariant. Both must still pass.

## Changelog

Commit 1 is user-visible: it promises coverage that was previously accidental. Add an entry under
`## Unreleased`. Commit 2 is internal documentation and needs no entry.
