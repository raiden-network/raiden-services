#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

requirements_replacements = {
    (
        'git+https://github.com/matrix-org/'
        'matrix-python-sdk.git@9ccbaa1#egg=matrix_client'
    ): 'matrix-client',
}

requirements = list(set(
    requirements_replacements.get(requirement.strip(), requirement.strip())
    for requirement in open('requirements.txt') if not requirement.lstrip().startswith('#')
))

setup_requirements = ['pytest-runner', ]

test_requirements = ['pytest', ]

setup(
    author="Brainbot Labs Est.",
    author_email='contact@brainbot.li',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
    ],
    description="Useful tools for Raiden and services.",
    install_requires=requirements,
    long_description=readme,
    include_package_data=False,
    keywords='raiden_libs',
    name='raiden_libs',
    packages=find_packages(exclude=['tests', ]),
    setup_requires=setup_requirements,
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/raiden-network/raiden_libs',
    version='0.1.1',
    zip_safe=False,
)
