# Future work: adopt `pytester`, and the unpatch bug that blocks it

Status: deferred, not scheduled. Nothing here is a fix for a bug users can hit today.

This document covers two things that are inseparable:

1. Adopting the `pytester` fixture so the plugin can be tested through real pytest runs.
2. Fixing audit finding 1, which is currently dormant and becomes a hard blocker the moment
   `pytester` is adopted.

They are written up together because doing 1 without 2 produces a test suite that crashes.

## Why adopt `pytester`

The plugin's job is to change what happens across a whole pytest session: patch
`functools.lru_cache` before conftest import, clear caches at every test teardown, restore the
original at the end of collection. Today's tests in `tests/` exercise the helper functions and the
hooks directly. They cannot cover the parts that only exist as session behaviour, for example:

- which exit paths reach `pytest_collection` and therefore restore the original
- interaction with the `lru_cache_disabled` ini setting as pytest actually parses it
- hook ordering against other plugins
- the teardown loop firing once per test across a real run

`pytester` gives an inner pytest run per test, so those become ordinary assertions.

## Why it is blocked

### The version constraint

The `pytester` fixture requires **pytest >= 6.2**, not >= 6. Verified by installing each release and
checking for the fixture in `_pytest.pytester`:

| pytest | `pytester` fixture present |
| --- | --- |
| 6.0.2 | no |
| 6.1.2 | no |
| 6.2.5 | yes |

`tox.ini` currently has envs `py39-pytest{3,4,5,6}`, and `pyproject.toml` declares
`pytest>=3`. Adopting `pytester` unconditionally means raising the floor to `pytest>=6.2` and
dropping the `pytest3`, `pytest4`, `pytest5` envs. Note that the `pytest6` env resolves to the newest
6.x, which is 6.2.5, so that one env would survive a `>=6.2` floor unchanged.

### The `testdir` alternative, and why it is not taken

`testdir` is the legacy spelling and it does span the entire current matrix (pytest 3 through 9), but
its relationship to `Pytester` changes partway through:

| pytest | what `Testdir` is | `pytester` fixture | `--runpytest` default |
| --- | --- | --- | --- |
| 3.10.1 | the primary implementation in `_pytest/pytester.py`, with its own `runpytest` | no | `inprocess` |
| 5.4.3 | same, `runpytest` dispatching on `self._method` | no | `inprocess` |
| 6.1.2 | same | no | `inprocess` |
| 6.2.5 | a facade; `runpytest` is `return self._pytester.runpytest(...)` | yes | `inprocess` |
| 7.0.0 | the same facade, relocated to `_pytest/legacypath.py` | yes | `inprocess` |

`Pytester` is introduced in 6.2 and `Testdir` becomes a thin wrapper over it at that point, differing
mainly in returning `py.path.local` instead of `pathlib.Path`. Before 6.2, `Testdir` is its own
implementation and does not delegate to anything.

What does hold across every version checked is `default="inprocess"` on the `--runpytest` option. That
is the property that matters here, and it is why `testdir` is exposed to the finding 1 crash on old
pytest as well, independently of the delegation.

So the blocker is a choice, not a physical constraint. We could write these tests today against
`testdir` and keep supporting pytest 3. We are choosing not to depend on a deprecated fixture for new
test code. Whoever picks this up should know it was a judgement call and can be revisited.

A third option, not evaluated in depth: a version-gated test module that uses `pytester` where
available and skips below 6.2. That keeps the support floor but leaves the oldest envs untested,
and it collides with the `--fail-under 100` coverage gate in `tox.ini`, which would see the skipped
module's lines as uncovered.

## The bug that adoption triggers

Full write-up with repro and measured exit paths: `docs/audit-2026-09-13.md`, finding 1.

Short version. Two defects in `pytest_antilru/main.py` compound:

- `old_lru_cache` is a module-level global (line 10), assigned on every patch install (lines 30-31).
  It is not captured in the `lru_cache_wrapper` closure, so the wrapper reads it live at call time
  (lines 43 and 53).
- The original is only restored in `pytest_collection` (line 75). Several pytest exit paths never
  reach that hook: a conftest that raises on import, a usage error, `-h`, `--markers`. Measured; a
  normal run, `--collect-only`, `--version`, and a no-tests-found run all do restore correctly.

Consequence: a session that exits before collection completes leaves `functools.lru_cache` pointing
at `lru_cache_wrapper` for the rest of the interpreter's life. A second session in that same process
runs line 31 and stores the already-installed wrapper as `old_lru_cache`. The wrapper now calls
itself:

```text
INTERNALERROR>   File "pytest_antilru/main.py", line 53, in lru_cache_wrapper
INTERNALERROR>     wrapper = old_lru_cache(**kwargs)
INTERNALERROR>   [Previous line repeated 903 more times]
INTERNALERROR> RecursionError: maximum recursion depth exceeded
```

### Why it is dormant today

It needs two pytest sessions in one interpreter. Every current way this plugin is used starts a fresh
process per session: the `pytest` CLI, `tox`, and `pytest-xdist` workers. `tests/` contains no
`pytester`, `testdir`, or `runpytest` usage, so the repo's own suite cannot reach it either. Audit
finding 1 was downgraded from Critical to Medium on that basis.

### Why adoption makes it live

`pytester.runpytest()` defaults to `--runpytest=inprocess`, which routes through `inline_run` to
`main()` in the current interpreter. Testing a failing inner run is a normal thing for a plugin test
suite to do. One inner run that errors during collection poisons the next inner run in the same
process. The same is true of `testdir` at every version, because of the shared `inprocess` default
above, so switching spellings does not avoid it.

## The agreed fix

Three changes to `pytest_antilru/main.py`, all inside `pytest_load_initial_conftests`:

1. Do not save the original unconditionally. Only save when `functools.lru_cache` is not already our
   wrapper. Detect that with an `_antilru_patched` marker attribute set on `lru_cache_wrapper`, not
   by identity against a global.
2. Bind the original into the closure of `lru_cache_wrapper` as a local, rather than having the
   wrapper read a module global at call time. This is what makes a leaked patch merely stale instead
   of self-recursive.
3. Leave the `pytest_collection` restore where it is, as best-effort cleanup.

On point 3, an earlier draft of the audit suggested moving the restore to `pytest_unconfigure`, which
pytest always runs. That was rejected. Moving it changes how long the patch is installed, which is
the subject of audit finding 4 (caches created after collection are never busted). That is a separate
design decision about the plugin's intended scope and should not be made as a side effect of a
crash fix. Once points 1 and 2 are in, a leaked patch is harmless, so the weaker restore is
acceptable.

## Regression test

Do not write the regression test for this fix with `pytester`. That would make the fix depend on the
migration, which is the wrong order, and it forces the version floor before we have decided to raise
it.

Write it as a direct unit test instead: call `pytest_load_initial_conftests` twice with stub
`early_config` and `parser` objects, without restoring `functools.lru_cache` in between, and assert
that the second install does not produce a self-recursive wrapper. That reproduces the exact
mechanism without needing an inner pytest run.

Keep the `pytester`-based session tests for the migration itself, once the floor is raised.

## Sequencing

1. Fix finding 1 with the direct unit test above. Independent of everything else here.
2. Decide whether to raise the floor to `pytest>=6.2`, or to accept `testdir`.
3. If the floor is raised: update `pyproject.toml` dependencies and drop the `pytest3`, `pytest4`,
   `pytest5` envs from `tox.ini`.
4. Add the `pytester`-based session tests.

Step 1 is worth doing whether or not steps 2 through 4 ever happen, because it is small and it
removes the coupling.
