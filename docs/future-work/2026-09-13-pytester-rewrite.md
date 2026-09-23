# Future work

Changes that are blocked on something other than effort. Each entry records the trigger condition,
so the work can be picked up when the blocker clears rather than rediscovered from scratch.

## Rewrite the test suite on `pytest.Pytester`

**Trigger:** dropping pytest 3, 4, and 5 from the [`tox.ini`](../../tox.ini#L5-L12) envlist.

**Status:** blocked. Not started.

### Why it is blocked

`pytest.Pytester` is the "run pytest inside pytest" fixture. It lets a single test function write a
temporary test module and ini file, run pytest against them, and assert on the outcome.

Pytester and its predecessor do not cover our matrix:

- `pytester` was introduced in pytest 6.2.
- `testdir`, the older py.path-based equivalent, was removed in pytest 9. Verified empirically:
  under pytest 9.0.3, `_pytest.pytester` exposes `pytester` but no `testdir` and no `Testdir`.

So no single API spans pytest 3 through 9. Writing against both is two code paths testing one
behaviour, which costs more than it saves.

Note that Pytester does not run a *different* pytest version in the inner run. `runpytest_subprocess`
invokes `sys.executable -m pytest` in the same environment, so the harness and the code under test
are always the same pytest version. A modern harness cannot be used to exercise pytest 3.

Of the current envlist, only `py39-pytest{3,4,5}` lack `pytester`. `pytest==6` resolves to 6.2.5, so
the `pytest6` env already has it.

### What it unlocks

The current suite encodes each scenario as a combination of module-level global state and a
hand-ordered `tox.ini` invocation. Pytester replaces all of it with self-contained test functions:

- [`tox.ini`](../../tox.ini#L44-L67) hardcodes seven pytest invocations: six scoped to explicit node
  IDs plus one whole-directory run, with the `main_test.py` pair run forward and then, at the end of
  the block, in reverse. Test ordering becomes an argument to `runpytest`, inside the test that depends
  on it.
- [`CACHED_RESULTS_FROM_TEST`](../../tests/main_test.py#L10),
  [`CACHED_RESULTS_DURING_TEARDOWN`](../../tests/main_test.py#L11),
  [`EXPECTED_CACHED_VALUE`](../../tests/teardown_order_test.py#L5), and
  [`ENABLE_HOOKWRAPPER_PROBE`](../../tests/teardown_order_test.py#L7) carry state between tests. Each
  scenario becomes one function with no cross-test state.
- Each `lru_cache_disabled` config variant needs its own
  `-c` [`tests/pytest_lru_cache_allowlist.ini`](../../tests/pytest_lru_cache_allowlist.ini)
  invocation. These become `pytester.makeini(...)` calls, parametrizable like any other fixture.
- [`tests/allowlist_test.py`](../../tests/allowlist_test.py) carries `pytest.skip()` guards purely so
  one file survives three configs. The guards disappear.

It also makes scenarios writable that are awkward today: plugin-disabled baselines, `--collect-only`
behaviour, and asserting that `functools.lru_cache` is correctly restored after collection.

Sketch:

```python
# tests/conftest.py
pytest_plugins = ['pytester']
```

```python
def test_cache_busted_between_tests(pytester):
    pytester.makepyfile("""
        from functools import lru_cache

        @lru_cache
        def f():
            return object()

        def test_a():
            f()

        def test_b():
            assert f.cache_info().currsize == 0
    """)
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)
```

### Constraints to respect when doing the work

**Use `runpytest_subprocess`, not `runpytest_inprocess`.** This plugin patches `functools.lru_cache`
process-globally in
[`pytest_load_initial_conftests`](../../pytest_antilru/main.py#L24) and accumulates decorated
functions in the module-level [`CACHED_FUNCTIONS`](../../pytest_antilru/main.py#L9) list. An
in-process inner run shares both with the outer run, so the
outer teardown would call `cache_clear()` on functions registered by the inner run. That is exactly
the cross-contamination class this plugin exists to prevent, and it would make the suite's results
untrustworthy.

The inner run's own install also clears `CACHED_FUNCTIONS` before repopulating it, so it silently
wipes whatever the outer run had already recorded during its own collection. The outer run's
teardown then clears nothing for those caches for the rest of the outer session, with no error or
warning. This is not merely a crash risk: it is silent, permanent loss of cache-busting for the
outer session.

**Subprocess runs are invisible to `coverage run`.** [`tox.ini`](../../tox.ini#L63-L64) enforces
`coverage report --fail-under 100` on both [`pytest_antilru`](../../pytest_antilru) and
[`tests`](../../tests). Subprocess coverage needs
either `COVERAGE_PROCESS_START` plus a `.pth` hook, or coverage 7.4+ `[run] patch = subprocess`.
Budget for this; it is not free.

**Do not gate the new file with a module-level skip.** A module-level `pytestmark = skipif(...)`
still executes the module body, so in an env without `pytester` the function bodies go uncovered and
[`coverage report --fail-under 100 --include 'tests/*'`](../../tox.ini#L64) fails. If the new suite
has to coexist with old-pytest envs during a transition, give it a dedicated `testenv` with its own
`coverage run` instead, or exclude it with `collect_ignore` in a conftest.

### The decision that is actually being deferred

Two end states are viable, and the trigger picks between them:

1. **Drop pytest 3/4/5, go all in.** Rewrite on Pytester, delete the module-level global state in
   [`tests/main_test.py`](../../tests/main_test.py) and
   [`tests/teardown_order_test.py`](../../tests/teardown_order_test.py), delete the skip guards in
   [`tests/allowlist_test.py`](../../tests/allowlist_test.py), and collapse the
   [`tox.ini`](../../tox.ini#L44-L67) commands block to a single pytest invocation. This is the payoff
   and the reason the work is worth doing at all.
2. **Keep pytest 3/4/5, carry two suites.** Add a Pytester suite in a dedicated tox env for new
   scenarios, and leave the existing ordered suite as the only coverage for old pytest. This is
   available today but has a real ongoing cost: two ways to express the same assertion, and
   contributors have to know which one to reach for.

Option 2 is not recommended as a permanent state. If the compatibility policy is not ready to change,
the honest answer is to leave the suite as it is and revisit when it is.

[`pyproject.toml`](../../pyproject.toml) already declares `pytest>=3`, so narrowing that floor is a
support-policy decision and belongs in [`CHANGELOG.md`](../../CHANGELOG.md) as a breaking change when
it happens.
