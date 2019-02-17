from setuptools import find_packages
from setuptools import setup


long_description = '''Caching with functools.lru_cache is great for performance. It works so well that it'll even
speed up your unit test runs. All you need to sacrifice in return is test isolation and your sanity.

Imagine, you mock some things out and a function caches those results. On your next test run, it doesn't matter what you
mock, the results are already cached. Now trying running those two test out-of-order sequence and tell me how it goes.
'''

setup(
    name='myproject',
    version='0.1.0',
    description='Bust functools.lru_cache when running pytest to avoid test pollution',
    long_description=long_description,
    packages=find_packages(exclude=('tests/*')),
    install_requires=[
        'six',
    ],
    entry_points={"pytest11": ["name_of_plugin = pytest_antilru"]},
    classifiers=[
        "Framework :: Pytest",
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
)
