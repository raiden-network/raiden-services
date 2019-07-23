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
            "ms-goerli-backup",
            "msrc-ropsten",
            "msrc-rinkeby",
            "msrc-kovan",
            "msrc-goerli",
            "msrc-goerli-backup",
        ],
    }
}

app = Flask(__name__)


class ImageUpdateError(Exception):
    """Couldn't build/update our images."""


def print_to_stderr(s):
    print(s, file=sys.stderr)


@app.route("/", methods=["get", "post"])
def main():
    data = request.json or {}
    repo = data.get("repository", {}).get("full_name", "")
    branch = data.get("ref", "").replace("refs/heads/", "")
    branch_config = REPOS.get(repo)
    if branch_config and branch in branch_config:
        try:
            res = update(branch, branch_config["names"], **branch_config[branch])
        except ImageUpdateError:
            print_to_stderr("Error updating local images via docker registry!")
        except Exception as e:
            print_to_stderr(f"Fatal Error while updating images: Unhandled exception encountered: {e}")
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


def update(branch, container_names, source, deployment, **kw):
    print_to_stderr(f"Changing working directory to {source}")
    try:
        os.chdir(source)
    except FileNotFoundError as e:
        print_to_stderr(f"Could not change to directory {source} - Not found!")
        raise ImageUpdateError from e

    print_to_stderr("Fetching latest changes: git fetch")
    try:
        subprocess.check_output(["git", "fetch", "--all"])
    except subprocess.SubprocessError as e:
        print_to_stderr(f"Fetching latest changes failed: {e}")
        raise ImageUpdateError from e

    print_to_stderr("Resetting branch: git reset")
    try:
        subprocess.check_output(["git", "reset", "--hard", f"origin/{branch}"])
    except subprocess.SubprocessError as e:
        print_to_stderr(f"Resetting branch failed: {e}")
        raise ImageUpdateError from e

    print_to_stderr(f"Changing working directory to {deployment}")
    try:
        os.chdir(deployment)
    except FileNotFoundError as e:
        print_to_stderr(f"Could not change to directory {deployment} - Not found!")
        raise ImageUpdateError from e

    print_to_stderr("Pulling containers containers: docker pull")
    try:
        subprocess.run(["docker-compose", "pull"], check=True)
    except subprocess.SubprocessError as e:
        print_to_stderr(f"Pulling new images from docker registry failed: {e}")
        raise ImageUpdateError from e

    print_to_stderr(f"Restarting containers: docker restart: {container_names}")
    try:
        subprocess.run(["docker-compose", "restart"] + container_names, check=True)
    except subprocess.SubprocessError as e:
        print_to_stderr(f"Restarting containers {container_names} failed: {e}")
        raise ImageUpdateError from e
