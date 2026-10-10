#!/usr/bin/env python3
"""Offline fake-child check for separate app-server launch and workspace scopes."""

import json
import os
from pathlib import Path
import select
import shutil
import signal
import socket
import subprocess
import tempfile

from check_control import encoded, read_line, socket_reply, wait_for


FAKE_SERVER = r'''#!/usr/bin/env python3
import json
import os
import sys

threads = {}
for raw in sys.stdin.buffer:
    message = json.loads(raw)
    method, params = message["method"], message.get("params", {})
    result = {"childPid": os.getpid(), "launchCwd": os.getcwd()}
    if method == "thread/start":
        thread = {"id": params["threadId"], "cwd": params["cwd"], "ephemeral": False}
        threads[thread["id"]] = thread
        result["thread"] = thread
    elif method == "thread/read":
        result["thread"] = threads[params["threadId"]]
    raw = (json.dumps({"id": message["id"], "result": result}) + "\n").encode()
    while raw:
        raw = raw[os.write(1, raw):]
'''


def main():
    source = Path(__file__).resolve().parents[1] / "wrapper"
    with tempfile.TemporaryDirectory(prefix="codex-wsl-scope-check-") as temp:
        root = Path(temp)
        for name in ("codex-wrapper", "control.py", "protocol.py"):
            shutil.copyfile(source / name, root / name)
        wrapper = root / "codex-wrapper"
        wrapper.chmod(0o700)
        child = root / "fake-app-server"
        child.write_text(FAKE_SERVER)
        child.chmod(0o700)
        launcher, workspace, other = root / "launcher", root / "workspace", root / "other"
        for directory in (launcher, workspace, other):
            directory.mkdir()

        for explicit_launch in (True, False):
            launch = launcher if explicit_launch else workspace
            capture_root = root / ("split-captures" if explicit_launch else "default-captures")
            config = {"realExecutable": str(child), "captureCwd": str(workspace),
                      "captureRoot": str(capture_root), "control": True}
            if explicit_launch:
                config["launchCwd"] = str(launch)
            wrapper.with_suffix(".local.json").write_text(json.dumps(config))
            process = subprocess.Popen([str(wrapper), "app-server"], cwd=launch,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True)
            try:
                socket_path = wait_for(lambda: next(capture_root.glob("*/control.sock"), None),
                                       "expected launch scope did not create control socket")

                def call(method, params=None):
                    request = {"method": method}
                    if params is not None:
                        request["params"] = params
                    with socket.socket(socket.AF_UNIX) as conn:
                        conn.settimeout(5)
                        conn.connect(str(socket_path))
                        conn.sendall(encoded(request))
                        return socket_reply(conn)

                def vscode(request):
                    process.stdin.write(encoded(request))
                    process.stdin.flush()
                    return json.loads(read_line(process.stdout))

                child_pid = call("status")["result"]["childPid"]
                child_identity = {"childPid": child_pid, "launchCwd": str(launch)}
                assert vscode({"id": 1, "method": "initialize"}) == {"id": 1, "result": child_identity}
                for request_id, thread_id, directory in [
                    (2, "workspace-thread", workspace), (3, "launch-thread", launcher),
                    (4, "other-thread", other),
                ]:
                    thread = {"id": thread_id, "cwd": str(directory), "ephemeral": False}
                    assert vscode({"id": request_id, "method": "thread/start", "params": {
                        "threadId": thread_id, "cwd": str(directory),
                    }}) == {"id": request_id, "result": dict(child_identity, thread=thread)}
                assert call("status")["result"] == {"initialized": True, "childPid": child_pid,
                                                     "threads": ["workspace-thread"], "activeTurns": {}}
                reply = call("thread/read", {"threadId": "workspace-thread"})
                assert reply["id"].startswith("__codex_bridge__/")
                assert reply["result"] == dict(child_identity, thread={
                    "id": "workspace-thread", "cwd": str(workspace), "ephemeral": False,
                })
                for thread_id in ("launch-thread", "other-thread"):
                    assert "error" in call("thread/read", {"threadId": thread_id})
                assert not select.select([process.stdout], [], [], .05)[0], "private read leaked to VS Code"
                metadata = json.loads((socket_path.parent / "process.json").read_text())
                assert metadata["cwd"] == str(launch) and metadata["childPid"] == child_pid
                process.stdin.close()
                process.stdin = None
                stdout, stderr = process.communicate(timeout=5)
                assert stdout == stderr == b"" and process.returncode == 0
                assert not socket_path.exists()
                print("PASS " + ("separate launch/workspace cwd" if explicit_launch else "default launchCwd")
                      + ": real child cwd retained; only workspace thread is controllable")
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()


if __name__ == "__main__":
    main()
