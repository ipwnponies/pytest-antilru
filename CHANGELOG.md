# Changelog

## Unreleased

## [1.1.0] - 2022-01-29

Added support for python 3.8+.
Python 3.8 functools.lru_cache added support for using as a plain decorator.

```py
@lru_cache()
def oldway():
  ...

@lru_cache
def newway():
  ...
```

## [1.0.5] - 2019-04-10

[1.0.5]: https://github.com/ipwnponies/pytest-antilru/releases/tag/v1.0.5

Literally no change since 1.0.0.
This release is for versioning reasons with the original, to-be-deprecated internal package.

## [1.0.0] - 2019-04-10

[0.2.1]: https://github.com/ipwnponies/pytest-antilru/releases/tag/v1.0.0

No changes in this release, this is going gold!

## [0.2.1] - 2019-03-13

[0.2.1]: https://github.com/ipwnponies/pytest-antilru/releases/tag/v0.2.1

### Changed

* Minor code quality improvements

## [0.2.0] - 2019-03-12

[0.2.0]: https://github.com/ipwnponies/pytest-antilru/releases/tag/v0.2.0

### Added

* Python 2.7 support for both `functools32` and `backports.functools_lru_cache`
* Added to pypi

## 0.1.0 - Unreleased

### Added

* Initial release
* TravisCI setup
* Python 3
* Project boilerplate
