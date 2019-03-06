# pytest-antilru

[![Build Status]](https://travis-ci.com/ipwnponies/pytest-antilru)

[Build Status]: https://travis-ci.com/ipwnponies/pytest-antilru.svg?branch=master

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

This project is currently only python 3 compatible.
Python 2.7 support could be added but py27 EOL is just around the corner.
It's unclear how many existing projects would benefit from this.
If you have no choice but to write new py27 code, I guess using this to reduce test pollution would be net
*less-badness* in the world.
Open an issue and it can be added.

## Installation

Simply install this in the same python environment that `pytest` uses and the rest is magic.

```sh
pip install pytest-antilru`
```

## How to test the software

```sh
make test
```

----

## Credits and references

This project was a re-engineering of a similar project a colleague of mine wrote.
That project was not intended to be open-source and rather than go though all the hoops and hurdles to sanitize it,
I've written it from the ground up such that it's kosher to open-source (given that it's such as small project).
