import json
import os
import subprocess
import sys
from pprint import pprint
from typing import List

import requests
from flask import Flask, request

ALL_SERVICE_NAMES = [
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
]

REPOS = {
    "latest": {
        "master": {
            "source": "/root/raiden-services",
            "deployment": "/root/raiden-services/deployment",
        }
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
    print_to_stderr("Received request at '/'. Ignoring!")
    print_to_stderr(json.dumps(data))

    return "OK"


# See https://docs.docker.com/docker-hub/webhooks/
@app.route("/dockerhub", methods=["get", "post"])
def dockerhub():
    data = request.json or {}
    print_to_stderr("Received request at '/dockerhub'.")
    print_to_stderr(json.dumps(data))

    callback_url = data.get("callback_url")
    push_data = data.get("push_data", {})
    tag = push_data.get("tag")

    deploy_config = REPOS.get(tag)

    if deploy_config:
        try:
            update(ALL_SERVICE_NAMES, **deploy_config["master"])

            if callback_url:
                requests.post(url=callback_url, json={"state": "success"})

            if callback_url:
                requests.post(url=callback_url, json={"state": "success"})
            return "OK"

        except ImageUpdateError:
            print_to_stderr("Error updating local images via docker registry!")
        except Exception as e:
            print_to_stderr(
                f"Fatal Error while updating images: Unhandled exception encountered: {e}"
            )
            raise
        finally:
            if callback_url:
                requests.post(url=callback_url, json={"state": "error"})
    return "OK"


def update(container_names: List[str], source: str, deployment: str) -> None:
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
        subprocess.check_output(["git", "reset", "--hard", "origin/master"])
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
