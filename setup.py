#!/usr/bin/env python3

try:
    from setuptools import setup, find_packages
except ImportError:
    from distutils.core import setup

import subprocess
import distutils
import os
from setuptools import Command
from setuptools.command.build_py import build_py

DESCRIPTION = 'Raiden Monitoring Service observes state of the channels'
' on behalf of the nodes that are offline.'
VERSION = open('monitoring_service/VERSION', 'r').read().strip()

REQ_REPLACE = {
    'git+https://github.com/matrix-org/matrix-python-sdk.git': 'matrix-client'
}


def read_requirements(path: str):
    assert os.path.isfile(path)
    ret = []
    with open(path) as requirements:
        for line in requirements.readlines():
            line = line.strip()
            if line[0] in ('#', '-'):
                continue
            if line in REQ_REPLACE.keys():
                line = REQ_REPLACE[line]
            ret.append(line)

    return ret


def read_version_from_git():
    try:
        import shlex
        git_version, _ = subprocess.Popen(
            shlex.split('git describe --tags'),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        ).communicate()
        git_version = git_version.decode()
        if git_version.startswith('v'):
            git_version = git_version[1:]

        git_version = git_version.strip()
        # if this is has commits after the tag, it's a prerelease:
        if git_version.count('-') == 2:
            _, _, commit = git_version.split('-')
            if commit.startswith('g'):
                commit = commit[1:]
            return '{}+git.r{}'.format(VERSION, commit)
        elif git_version.count('.') == 2:
            return git_version
        else:
            return VERSION
    except BaseException as e:
        print('could not read version from git: {}'.format(e))
        return VERSION


class CompileContracts(Command):
    description = 'compile contracts into bytecode using solc'
    contracts_dir = '/home/xoza/src/raiden/raiden/smart_contracts/'
    compiled_dir = 'compiled'
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def available_contracts(self, contracts_dir):
        return [os.path.join(contracts_dir, x)
                for x in os.listdir(contracts_dir)
                if x.endswith('.sol')]

    def run(self):
        assert os.path.isfile(self.compiled_dir) is False
        if os.path.isdir(self.compiled_dir) is False:
            os.mkdir(self.compiled_dir)
        solc = distutils.spawn.find_executable('solc')
        if not solc:
            self.announce('solc not found!', level=distutils.log.ERROR)
            return -1
        command = ['solc', '--combined-json', 'abi,bin']
        command += self.available_contracts(self.contracts_dir)
        command += ['-o', 'compiled', '--overwrite']
        subprocess.check_call(command)


class BuildPyCommand(build_py):
    def run(self):
        self.run_command('compile_contracts')
        build_py.run(self)


config = {
    'version': read_version_from_git(),
    'scripts': [],
    'name': 'raiden-monitoring-service',
    'author': 'Brainbot Labs Est.',
    'author_email': 'contact@brainbot.li',
    'description': DESCRIPTION,
    'url': 'https://github.com/raiden-network/microraiden/',

    #   With include_package_data set to True command `py setup.py sdist`
    #   fails to include package_data contents in the created package.
    #   I have no idea whether it's a bug or a feature.
    #
    #    'include_package_data': True,

    'license': 'MIT',
    'keywords': 'raiden ethereum blockchain',
    'install_requires': read_requirements('requirements.txt'),
    'extras_require': {'dev': read_requirements('requirements-dev.txt')},
    'packages': find_packages(exclude=['test']),
    'package_data': {'microraiden': ['data/contracts.json',
                                     'webui/js/*',
                                     'webui/index.html',
                                     'webui/microraiden/dist/umd/microraiden.js',
                                     'VERSION']},
    'classifiers': [
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
    ],
    'cmdclass': {
        'compile_contracts': CompileContracts,
        'build_py': BuildPyCommand,
    },
}


setup(**config)
