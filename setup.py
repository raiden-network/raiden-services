#!/usr/bin/env python

"""The setup script."""

import re
from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()


def get_egg_or_req(req):
    match = re.search('#egg=([^#@]+)', req, re.U | re.I)
    return (match and match.group(1)) or req


with open('requirements.txt') as req_file:
    requirements = list({
        get_egg_or_req(requirement)
        for requirement in req_file
        if requirement.strip() and not requirement.lstrip().startswith('#')
    })

setup_requirements = ['pytest-runner']

test_requirements = ['pytest']

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
    packages=find_packages(exclude=['tests']),
    setup_requires=setup_requirements,
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/raiden-network/raiden_libs',
    version='0.1.15',
    zip_safe=False,
)
