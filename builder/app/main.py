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
        'name': 'pfs-ropsten',
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
        res = build(branch, branch_config['name'], **branch_config[branch])
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


def build(branch, container_name, source, deployment, **kw):
    try:
        _print(f'Switching to {source}')
        _print(f'Container name = {container_name}')
        os.chdir(source)
        _print(f'git fetch')
        subprocess.check_output(["git", "fetch", "--all"])
        _print(f'git reset')
        subprocess.check_output(["git", "reset", "--hard", f"origin/{branch}"])

        _print(f'Switching to {deployment}')
        os.chdir(deployment)
        _print(f'docker build')
        subprocess.check_output(["docker-compose", "build"])
        _print(f'docker down')
        subprocess.check_output(["docker-compose", "stop", container_name])
        _print(f'docker up')
        subprocess.check_output(["docker-compose", "up", "-d"])
    except Exception as e:
        _print(str(e))
        return False
    return True
