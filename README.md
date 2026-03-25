# pytest-antilru

![supported python versions](https://img.shields.io/pypi/pyversions/pytest-antilru)
![license](https://img.shields.io/github/license/ipwnponies/pytest-antilru.svg)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)

[![Build Status](https://github.com/ipwnponies/pytest-antilru/actions/workflows/test.yaml/badge.svg)](https://github.com/ipwnponies/pytest-antilru/actions/workflows/test.yaml?query=branch%3Amaster)
[![Coverage Status](https://img.shields.io/coveralls/github/ipwnponies/pytest-antilru.svg)](https://coveralls.io/github/ipwnponies/pytest-antilru?branch=master)

<details>
    <summary>More badges</summary>

![latest version available on PyPI](https://img.shields.io/pypi/v/pytest-antilru)
![pypi wheels](https://img.shields.io/pypi/wheel/pytest-antilru.svg)
![PyPI download count](https://img.shields.io/pypi/dm/pytest-antilru)

![open issues](https://img.shields.io/github/issues/ipwnponies/pytest-antilru)
![number of files](https://img.shields.io/github/directory-file-count/ipwnponies/pytest-antilru)
![code size](https://img.shields.io/github/languages/code-size/ipwnponies/pytest-antilru)
![repo size](https://img.shields.io/github/repo-size/ipwnponies/pytest-antilru)

</details>

Caching expensive function calls with `functools.lru_cache` is simple and great performance optimization.
It works so well that it'll even speed up your unit test runs!
Too bad it violated test isolation and caches the wrong values under test conditions, introducing test pollution
(persisted state between test runs).
This package will bust the `lru_cache` between test runs, avoiding test pollution and helping you keep your sanity.

Imagine you mock a network call out and your application ends up caching these mocked results:

```python
def expensive_network_call() -> int:
    # Pretend this is an expensive network call.
    # You want to cache this for performance but you want to run tests with different responses as well.
    return 1


@lru_cache()
def cache_me() -> int:
    return expensive_network_call()
```

Now you have test pollution:

```python
def test_a_run_first() -> None:
    assert cache_me() == 1


def test_b_run_second() -> None:
    # We want to mock the network call for this test case
    with mock.patch.object(sys.modules[__name__], 'expensive_network_call', return_value=2) as mock_network_call:
        assert cache_me() == 2
        assert mock_network_call.called
```

On your next test run, it doesn't matter what you
mock, the results are already cached. Now trying running those two test out-of-order sequence and tell me how it goes.

## Dependencies

Since this is a `pytest` plugin, you need to be using `pytest` to run your tests.

## Compatibility

Current releases (`>=2.0`) support Python `>=3.8`.
If you need Python `<3.8`, use an older `pytest-antilru` release line instead.

The supported pytest bands for current releases are:

- Python 3.8: pytest `>=3,<8.4` (the highest installable release is 8.3.5)
- Python 3.9: pytest `>=3,<9`
- Python 3.10+: pytest `>=3,<10`

Pytest 9 is tested only on Python 3.10+.

The `tox` matrix in [tox.ini] and CI exercise these compatibility bands, including Python 3.14 coverage.

While we aim to support a wide range of Python and pytest combinations, pytest only allows its latest releases to support new interpreters:
they do not patch older releases to work with newer Python versions.
See [tox.ini] for the full envlist of what is being tested, and see the existing allowlist docs in the [`lru_cache_disabled`](#lru_cache_disabled) section for compatibility-related configuration guidance.

If you experience issues, please check for compatibility between your python and pytest target versions.
Open an issue once these are verified.

## Installation

Simply install this in the same python environment that `pytest` uses and the rest is magic.

```sh
pip install pytest-antilru
```

## Development setup

The runtime support for this package remains Python >=3.8.
For local contributor workflows, we recommend Python >=3.14 with `uv`.

Recommended setup after cloning:

```sh
make setup
```

This does two things for contributors:
- installs the project dev environment with `uv sync`
- installs git hooks with `pre-commit install --install-hooks`

If you prefer the raw commands:

```sh
uv sync
uv run pre-commit install --install-hooks
```

If you only want the project dev environment without git hook installation:

```sh
make venv
```

Poetry remains supported for legacy workflows, but is deprecated in favor of `uv`.
When dependencies change, `make lock` runs both `uv` and `poetry` lock commands.

Legacy Poetry commands:

```sh
poetry lock
poetry sync
```

## Configuration

Add this where ever [your pytest configurations](https://docs.pytest.org/en/stable/reference/customize.html) live.

### `lru_cache_disabled`

`lru_cache_disabled` is an allowlist of module paths to disable `lru_cache` for.
This allows you to target disable caching for specific modules that are causing test pollution.

The default behaviour of `pytest-antilru` is to disable `lru_cache` everywhere.
However, this can interfere with other dependencies that are reliant on `lru_cache` behaviour to behave correctly
within the same test run.

```ini
[tool.pytest.ini_options]
lru_cache_disabled = '''
    my_module.util
    my_module.client_lib.database
    '''
```

In this example, any usage of `lru_cache` in a file inside `my_module.util` or `my_module.client_lib.database`
will be disabled.
All other instances will continue to be cached within a test run.

## How to test the software

```sh
make test
```

This validates the pre-commit checks with `pre-commit run --all-files`, but it does not install git hooks for you.
Run `make setup` once on a new clone so local commits are checked before push.

---

## Credits and references

This project was a re-engineering of a similar project a colleague of mine wrote.
That project was not intended to be open-source and rather than go though all the hoops and hurdles to sanitize it,
I've written it from the ground up such that it's kosher to open-source (given that it's such as small project).
