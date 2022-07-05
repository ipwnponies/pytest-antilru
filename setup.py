from io import open
from os import path

from setuptools import find_packages
from setuptools import setup

THIS_DIRECTORY = path.abspath(path.dirname(__file__))
with open(path.join(THIS_DIRECTORY, 'README.md'), encoding='utf-8') as f:
    README = f.read()


setup(
    name='pytest-antilru',
    license='MIT',
    version='1.1.1',
    description='Bust functools.lru_cache when running pytest to avoid test pollution',
    long_description=README,
    long_description_content_type='text/markdown',
    url='https://github.com/ipwnponies/pytest-antilru',
    packages=find_packages(exclude=['tests']),
    install_requires=['pytest', 'pytest<5; python_version<"3"'],
    entry_points={'pytest11': ['antilru = pytest_antilru.main']},
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Framework :: Pytest',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
)
