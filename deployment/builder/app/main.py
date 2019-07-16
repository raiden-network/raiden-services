import os
import subprocess
import sys
from pprint import pprint

from flask import Flask, request


REPOS = {
    "raiden-network/raiden-services": {
        "master": {
            "source": "/root/raiden-services",
            "deployment": "/root/raiden-services/deployment",
        },
        "names": [
            "pfs-ropsten",
            "pfs-rinkeby",
            "pfs-kovan",
            "pfs-goerli",
            "pfs-ropsten-with-fee",
            "pfs-rinkeby-with-fee",
            "pfs-kovan-with-fee",
            "pfs-goerli-with-fee",
            "ms-ropsten",
            "ms-rinkeby",
            "ms-kovan",
            "ms-goerli",
            "msrc-ropsten",
            "msrc-rinkeby",
            "msrc-kovan",
            "msrc-goerli",
        ],
    }
}

app = Flask(__name__)


class BuildError(Exception):
    """Couldn't build/update our images."""


@app.route("/", methods=["get", "post"])
def main():
    data = request.json or {}
    repo = data.get("repository", {}).get("full_name", "")
    branch = data.get("ref", "").replace("refs/heads/", "")
    branch_config = REPOS.get(repo)
    if branch_config and branch in branch_config:
        try:
            res = update(branch, branch_config["names"], **branch_config[branch])
        except BuildError:
            print("Error building", file=sys.stderr)
        except Exception as e:
            print(f"Fatal Error while updating images: Unhandled exception encountered: {e}")
            raise
        else:
            pprint(
                {
                    "repo": repo,
                    "branch": branch,
                    "head_commit": data["head_commit"],
                    "pusher": data["pusher"],
                    "build_result": res,
                },
                stream=sys.stderr,
            )
        finally:
            return "OK"


def _print(s):
    print(s, file=sys.stderr)


def update(branch, container_names, source, deployment, **kw):
    _print(f"Changing working directory to {deployment}")
    try:
        os.chdir(deployment)
    except FileNotFoundError as e:
        _print(f"Could not change to directory {deployment} - Not found!")
        raise BuildError from e

    _print("Pulling containers containers: docker pull")
    try:
        subprocess.run(["docker-compose", "pull"], check=True)
    except subprocess.SubprocessError as e:
        _print(f"Pulling new images from docker registry failed: {e}")
        raise BuildError from e

    _print(f"Restarting containers: docker restart: {container_names}")
    try:
        subprocess.run(["docker-compose", "restart"] + container_names, check=True)
    except subprocess.SubprocessError as e:
        _print(f"Restarting containers {container_names} failed: {e}")
        raise BuildError from e
