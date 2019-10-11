import json
import os
import subprocess
import sys

import requests
from flask import Flask, request

app = Flask(__name__)


def print_to_stderr(s: str) -> None:
    print(s, file=sys.stderr)


@app.route("/", methods=["get", "post"])
def main() -> str:
    data = request.json or {}
    print_to_stderr("Received request at '/'. Ignoring!")
    print_to_stderr(json.dumps(data))

    return "OK"


# See https://docs.docker.com/docker-hub/webhooks/
@app.route("/dockerhub", methods=["get", "post"])
def dockerhub() -> str:
    print_to_stderr("Received request at '/dockerhub'.")
    data = request.json
    print_to_stderr(json.dumps(data))
    callback_url = data["callback_url"]
    state = "error"

    try:
        tag = data["push_data"]["tag"]
        os.chdir("/deployment")
        subprocess.check_output(["./update.sh", tag])
        state = "success"
    except subprocess.CalledProcessError as ex:
        print_to_stderr(ex.output)
        raise
    finally:
        requests.post(url=callback_url, json={"state": state})

    return "OK"
