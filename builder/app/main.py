import os
import subprocess
import sys
from pprint import pprint

from flask import Flask, request


REPOS = {
    'raiden-network/raiden-pathfinding-service': {
        'master': {
            'source': '/data/raiden-pathfinding-service',
            'deployment': '/data/services-dev',
        },
    },
}

app = Flask(__name__)


@app.route("/", methods=['get', 'post'])
def main():
    data = request.json or {}
    repo = data.get('repository', {}).get('full_name', '')
    branch = data.get('ref', '').replace('refs/heads/', '')
    branch_config = REPOS.get(repo)
    pprint(repo)
    pprint(branch)
    if branch_config and branch in branch_config:
        res = build(branch, **branch_config[branch])
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


def build(branch, source, deployment, **kw):
    try:
        os.chdir(source)
        subprocess.check_output(["git", "fetch", "--all"])
        subprocess.check_output(["git", "reset", "--hard", f"origin/{branch}"])

        os.chdir(deployment)
        subprocess.check_output(["docker-compose", "build"])
        subprocess.check_output(["docker-compose", "down"])
        subprocess.check_output(["docker-compose", "up", "-d"])
    except:
        return False
    return True
