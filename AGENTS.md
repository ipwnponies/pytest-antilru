# Agent Instructions

See `README.md` for what this plugin does, its compatibility matrix, and the Poetry→uv lockfile migration status.

## Preferred Make Targets

Prefer the repo's `make` targets when they exist. They are the stable abstraction for local setup, testing, and builds even if the underlying tool changes from `uv` to something else later.

```bash
make venv
make test
make build
```

Use `make publish` only when the user explicitly asks to publish a release, because it performs `uv publish`.

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

`tests/allowlist_test.py` reuses `main_test.py`'s `test_a_run_first` but defines its own
`test_b_run_second` with the opposite assertion: an allowlisted module should *keep* its cached
value. `tox.ini` runs this pair under three configs, but only `pytest_lru_cache_allowlist_no_match.ini`
actually exercises that assertion — the other two configs hit a `pytest.skip()` guard (empty
allowlist, or an allowlist that already covers `tests.main_test`).

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
