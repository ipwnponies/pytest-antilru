# Agent Instructions

See `README.md` for what this plugin does, its compatibility matrix, and the Poetry→uv lockfile migration status.
See `docs/architecture.md` for how the plugin intercepts `functools.lru_cache`, why each hook was chosen, and which cases the interception window does not cover.

## Preferred Make Targets

Prefer the repo's `make` targets when they exist. They are the stable abstraction for local setup, testing, and builds even if the underlying tool changes from `uv` to something else later.

```bash
make venv
make test
make build
```

Use `make publish` only when the user explicitly asks to publish a release, because it performs `uv publish`.

**Release process gap:** there is no CI workflow that tags, builds, or publishes a release — `.github/workflows/` contains only `test.yaml` (test matrix, runs on every push/PR). Cutting a release is entirely manual:

1. Move `## Unreleased` entries in `CHANGELOG.md` into a new dated version section, bump `version` in `pyproject.toml`, commit.
2. `git tag -a vX.Y.Z -m "..."` on the commit that lands on `master`, then `git push origin vX.Y.Z`.
3. `make publish` (`uv build && uv publish`).

`uv publish` needs PyPI credentials (`UV_PUBLISH_TOKEN` env var, or `--token`/`--username`+`--password` flags) — nothing in this repo documents where that token comes from or sets it up (no `.pypirc`, no CI secret, no `uv publish --trusted-publishing` config). Confirm with the repo owner how those credentials are supplied locally before running `make publish`.

## uv-Managed Commands

If you need a Python command that does not already have a `make` target, run CLIs installed from this repo's `pyproject.toml` through `uv run` instead of invoking them directly.

```bash
uv run <command> [args...]
```

Examples:

```bash
uv run python
uv run pytest

uv run black .
uv run tox
uv run pre-commit run --all-files
```

## Python Package Builds

Build distribution artifacts with `make build`.

```bash
make build
```

Right now `make build` delegates to `uv build`. Use the `make` target instead of `python -m build` so agents do not need to guess which packaging tool is active in this repo.

## Testing Gotchas

`tests/main_test.py` follows a `test_a_run_first` / `test_b_run_second` naming convention: `test_a`
warms the cache, `test_b` asserts it was busted. `tox.ini` deliberately runs this pair forward, then
in reverse order, to prove cache-busting works regardless of execution order — don't reorder the
`tox.ini` commands without preserving that check.

Both of those shapes exist because the suite cannot use `pytest.Pytester` while pytest 3, 4, and 5
are in the matrix. Before adding another ordered-invocation scenario, read
`docs/future-work/2026-09-13-pytester-rewrite.md`.

`tests/allowlist_test.py` reuses `main_test.py`'s `test_a_run_first` but defines its own
`test_b_run_second` with the opposite assertion: an allowlisted module should *keep* its cached
value. `tox.ini` runs this pair under three configs, but only `pytest_lru_cache_allowlist_no_match.ini`
actually exercises that assertion — the other two configs hit a `pytest.skip()` guard (empty
allowlist, or an allowlist that already covers `tests.main_test`, per `tests/pytest_lru_cache_allowlist.ini`).
The guard calls `pytest_antilru.main.is_module_covered` directly, the same function
`cache_user_function` uses, so it can't disagree with the plugin about what's covered.

## Plugin Internals Gotcha

In `pytest_antilru/main.py`, `pytest_runtest_teardown` is registered with `tryfirst=True` as a
hookwrapper specifically so its own cache-clearing code (after `yield`) runs last, once every other
teardown hookwrapper and fixture has finished. That's why a cached value stays visible through a
test's own fixture teardown but is gone by the next test — `tests/teardown_order_test.py` and its
hookwrapper probe in `tests/conftest.py` lock in that ordering. Don't drop `tryfirst` or reorder this
hook without re-verifying against both.

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var
