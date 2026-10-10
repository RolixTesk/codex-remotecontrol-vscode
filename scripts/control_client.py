"""Call the private control socket belonging to the existing Codex backend."""

import json
from pathlib import Path
import socket
import time

PROJECT = Path(__file__).resolve().parents[1]


def call(path, method, params=None):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(35)
        conn.connect(str(path))
        request = {"method": method}
        if params is not None:
            request["params"] = params
        conn.sendall(json.dumps(request).encode() + b"\n")
        with conn.makefile("rb") as f:
            return json.loads(f.readline())


def result(reply):
    if "error" in reply:
        raise RuntimeError("Codex request failed")
    return reply["result"]


def wait_remote_status(path, desired, seconds):
    deadline = time.monotonic() + seconds
    while True:
        status = result(call(path, "remoteControl/status/read"))
        if status["status"] == desired:
            return status
        if status["status"] == "errored" and desired == "connected":
            raise RuntimeError("Remote connection failed")
        if time.monotonic() >= deadline:
            raise TimeoutError("Native Remote status did not settle")
        time.sleep(.2)
