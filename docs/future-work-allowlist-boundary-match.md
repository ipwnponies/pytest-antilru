# Future work: match `lru_cache_disabled` on module boundaries

This document is a self-contained implementation prompt. A session can pick it up without reading the
audit discussion that produced it. It covers audit finding 3 from `docs/audit-2026-09-13.md`, and it
carries finding 2's one-line guard along with it because both change the same line.

## The bug

`pytest_antilru/main.py:16`:

```python
if user_function.__module__.startswith(module_path):
```

`startswith` is a raw string comparison. It has no concept of a module boundary, so an allowlist entry
matches any module whose dotted path merely begins with those characters.

| module | allowlist entry | current | wanted |
| --- | --- | --- | --- |
| `app.utilities` | `app.util` | matches | no match |
| `app.util` | `app.util` | matches | matches |
| `app.util.helpers` | `app.util` | matches | matches |
| `application` | `app` | matches | no match |
| `apps.core` | `app` | matches | no match |
| `tests.main_test` | `tests.main` | matches | no match |

The error is one-directional. `startswith` never misses a real prefix, it only over-matches. The
effect is cache busting in modules the user did not list, which reads as the plugin ignoring the
config.

### Verified reproduction

With `lru_cache_disabled = app.util` in `pytest.ini`, an `@lru_cache` function defined in
`app/utilities.py`, and two tests that both call it:

```
E       AssertionError: cache was wrongly busted: prefix over-match
E       assert 2 == 1
1 failed, 1 passed
```

`app.utilities` is not inside `app.util`, so the cache should have survived into the second test.

### Why the fix matches the documented contract

`README.md` already describes containment, not string prefixes. It says that listing `my_module.util`
disables caching for "any usage of `lru_cache` in a file inside `my_module.util`". Containment is what
this change implements, so the code is moving toward the documented behavior rather than away from it.

## Design decisions already made

These were settled during triage. Do not relitigate them; implement them.

### Use two string comparisons, not a regex

```python
module == module_path or module.startswith(module_path + '.')
```

A regex was considered and rejected. Allowlist entries are user configuration strings, not patterns.
Passing them to `re` unescaped turns the user's dots into wildcards, which introduces a brand new
over-match: `re.match('app.util(\\.|$)', 'appXutil')` succeeds. Correcting that requires
`re.escape`, at which point the regex does exactly what two string operations already do, costs an
import, and reads worse. A trailing-dot variant, `(module + '.').startswith(module_path + '.')`, is
behaviorally identical but needs a comment to explain the trick, so it saves nothing.

All three candidates were checked against the table above and against `appXutil`, a bare `app`, and an
empty module name. The two-comparison form and the escaped regex agree on every case.

Glob or regex patterns in `lru_cache_disabled` would be a feature, not a bug fix. They would also turn
every existing config into a pattern overnight. Keep them out of this change.

### Fold finding 2's guard into the same line

Finding 2 is the unguarded `.__module__` access on the same statement. A callable whose `__module__`
is `None` raises `AttributeError: 'NoneType' object has no attribute 'startswith'` during collection,
which aborts the entire run with exit code 2. It was triaged Low with no known trigger, on the
condition that its guard rides along with this change rather than being scheduled on its own.

Read the module once, defensively:

```python
module = getattr(user_function, '__module__', None) or ''
```

`getattr` covers method descriptors and method-wrappers, which lack the attribute entirely. The `or ''`
covers `None`.

### Severity is Medium, and the release is a patch

Medium, not High. The bug is unreachable unless `lru_cache_disabled` is non-empty, because an empty
allowlist takes the `else` branch at `main.py:19-20` and never reads line 16. It also needs a naming
collision between a listed entry and a sibling module. The impact is confined to tests.

The release is a patch bump. The buggy raw-prefix behavior was never documented anywhere; the README
documents containment. Semver measures backwards compatibility against the published contract, and
this change moves the code onto that contract. There is precedent in this repository: release 2.0.1
was a patch and its changelog entry reads "`lru_cache_disabled` now applies to `@lru_cache` (no
parentheses) form; previously only the `@lru_cache()` path was filtered" — the same class of change,
altering which modules get busted under an unchanged config.

The honest risk is that somebody wrote a short entry and leaned, knowingly or not, on it catching a
sibling module. That is what the changelog entry below is for. It is not a reason for a major bump.

### The `functools.partial` limitation is acknowledged, not fixed

A `functools.partial` is an instance of the `partial` class, so attribute lookup for `__module__`
falls through to the class, and `functools.partial` is defined in `functools`. Every partial ever
constructed therefore reports `'functools'`, regardless of where it was built.

The consequence is the opposite error from the prefix bug. With `lru_cache_disabled = app.util` and
`cached = lru_cache(partial(_fetch, 5))` written in `app/util.py`, the plugin compares `'functools'`
against `'app.util'`, finds no match, and never registers the wrapper. The cache is never cleared,
even though the user asked for it to be. Verified: the same file passes cleanly with no allowlist set
and fails with `assert 1 == 2` once `app.util` is listed.

There is no fix. Nothing on a partial records its construction site. The nearest candidate,
`p.func.__module__`, is a heuristic that fails on the common case: `partial(os.path.join, '/tmp')`
built inside a user module reports `posixpath`.

Wrapping a partial in `lru_cache` is rare. This is recorded so the next person does not rediscover it,
and it is deliberately out of scope. Do not add code for it, and do not add it to `README.md` or
`CHANGELOG.md`. Leave it in `docs/audit-2026-09-13.md` and in this document.

## What to change

### 1. `pytest_antilru/main.py:13-20`

```python
def cache_user_function(user_function, wrapper, lru_cache_disabled_modules: bool):
    if lru_cache_disabled_modules:
        module = getattr(user_function, '__module__', None) or ''
        for module_path in lru_cache_disabled_modules:
            if module == module_path or module.startswith(module_path + '.'):
                CACHED_FUNCTIONS.append(wrapper)
                break
    else:
        CACHED_FUNCTIONS.append(wrapper)
```

The `else` branch is unchanged and must stay unchanged. It is the default path and it never touches
`__module__`.

### 2. `tests/pytest_lru_cache_allowlist.ini`

Change the entry from `tests.main` to `tests.main_test`.

This is not an accommodation of the fix, it is a correction. `tests.main` names nothing: there is no
`tests/main/` package and no `tests/main.py`, only `tests/main_test.py`. The commit that introduced
this file (`6f6493e`) describes the config as "functionally equivalent" to the default run, which is
only true if it matches `tests.main_test`. It currently does so by accident, through the raw-prefix
bug being fixed here.

### 3. `tests/allowlist_test.py:17`

```python
if any('tests.main_test'.startswith(module_prefix) for module_prefix in disabled_modules):
```

This skip guard does its own matching, independent of the plugin. Left alone, it would keep skipping
in configurations where the plugin no longer matches, and the skip would hide the disagreement. Mirror
whatever `cache_user_function` does:

```python
if any(
    'tests.main_test' == module_prefix or 'tests.main_test'.startswith(module_prefix + '.')
    for module_prefix in disabled_modules
):
```

### 4. New regression test

Add a parametrized unit test that calls `pytest_antilru.main.cache_user_function` directly with a stub
callable and asserts whether the wrapper was registered. Cover, at minimum: exact match, submodule
match, the sibling over-match that regresses this bug (`app.utilities` against `app.util`), a
top-level over-match (`application` against `app`), a non-match, and a `__module__` of `None`.

Do not write this with `pytester`. Running a nested pytest session in-process trips audit finding 1,
the unpatch leak, which is documented as deferred in `docs/future-work-pytester-migration.md` and is
not fixed yet.

`CACHED_FUNCTIONS` is a module-level list and the `pytest_runtest_teardown` hook iterates it calling
`cache_clear()` on every entry. A test that appends a stub to the real list will break the teardown of
every later test in the session. Isolate it:

```python
monkeypatch.setattr(main, 'CACHED_FUNCTIONS', [])
```

### 5. `README.md`, the `lru_cache_disabled` section

The existing prose already describes containment and stays correct. Add an explicit statement of the
matching rule so this is documented rather than implied: an entry matches a module with exactly that
path, or any module beneath it, and `my_module.util` does not match `my_module.utilities`.

### 6. `AGENTS.md`, the Testing Gotchas section

The paragraph on `tests/allowlist_test.py` refers to "an allowlist that already covers
`tests.main_test`". Update it for the new ini value and the mirrored guard.

### 7. `CHANGELOG.md`, under `## Unreleased`

```markdown
### Fixed

- `lru_cache_disabled` now matches on module-path boundaries. An entry `app.util` matches `app.util`
  and `app.util.helpers`, but no longer matches `app.utilities` or `application`. Configs relying on
  the old raw-string prefix match must list the full module path.
```

## How to verify

The coverage gate is `--fail-under 100` for both the package and the tests, so the new test file has
to be fully exercised.

Run the four allowlist invocations in `tox.ini` and confirm all still pass:

- `tests/pytest_lru_cache_allowlist.ini` against `tests/main_test.py`, which asserts the cache is
  busted. This is the one that breaks if step 2 is skipped.
- the default empty config against `tests/allowlist_test.py`, which hits the empty-allowlist skip.
- `tests/pytest_lru_cache_allowlist.ini` against `tests/allowlist_test.py`, which hits the covered
  skip.
- `tests/pytest_lru_cache_allowlist_no_match.ini` against `tests/allowlist_test.py`, which runs the
  real assertions.

All three branches of the skip guard must remain reachable, or the tests coverage gate fails.

Then run the full `make test`.

## Sequencing

Steps 1 through 4 belong in one commit; they are a single behavior change plus its test. Steps 5
through 7 are the documentation for that change and can ride in the same commit. Nothing here depends
on audit findings 1, 4, 5, 6, 7, or 8, and nothing here should touch them.
