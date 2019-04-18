import os
import subprocess
import sys
from pprint import pprint

from flask import Flask, request


REPOS = {
    'raiden-network/raiden-services': {
        'master': {
            'source': '/data/raiden-services',
            'deployment': '/data/services-dev',
        },
        'names': [
            'pfs-ropsten', 'pfs-rinkeby', 'pfs-kovan', 'pfs-goerli',
            'ms-ropsten', 'ms-rinkeby', 'ms-kovan', 'ms-goerli',
            'msrc-ropsten', 'msrc-rinkeby', 'msrc-kovan', 'msrc-goerli',
        ],
    },
}

app = Flask(__name__)


@app.route("/", methods=['get', 'post'])
def main():
    data = request.json or {}
    repo = data.get('repository', {}).get('full_name', '')
    branch = data.get('ref', '').replace('refs/heads/', '')
    branch_config = REPOS.get(repo)
    if branch_config and branch in branch_config:
        res = build(branch, branch_config['names'], **branch_config[branch])
        if res:
            pprint(
                {
                    'repo': repo,
                    'branch': branch,
                    'head_commit': data['head_commit'],
                    'pusher': data['pusher'],
                    'build_result': res,
                },
                stream=sys.stderr,
            )
        else:
            print("Error building", file=sys.stderr)
    return "OK"


def _print(s):
    print(s, file=sys.stderr)


def build(branch, container_names, source, deployment, **kw):
    try:
        _print(f'Switching to {source}')
        _print(f'Container names = {container_names}')
        os.chdir(source)
        _print('git fetch')
        subprocess.check_output(["git", "fetch", "--all"])
        _print('git reset')
        subprocess.check_output(["git", "reset", "--hard", f"origin/{branch}"])

        _print(f'Switching to {deployment}')
        os.chdir(deployment)
        _print('docker build')
        subprocess.check_output(["docker-compose", "build"])
        for name in container_names:
            _print(f'docker down: {name}')
            subprocess.check_output(["docker-compose", "stop", name])
        _print('docker up')
        subprocess.check_output(["docker-compose", "-f", "docker-compose.yml", "up", "-d"])
    except Exception as e:
        _print(str(e))
        return False
    return True
