#!/usr/bin/env python3
"""Exercise the private control socket against one isolated fake app-server."""

import json
import os
from pathlib import Path
import select
import shutil
import signal
import socket
import subprocess
import tempfile
import time


FAKE_SERVER = r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

initializations = 0
log = open(os.environ["CHECK_RECEIVED"], "ab", buffering=0)

def emit(message):
    raw = (json.dumps(message, ensure_ascii=False) + "\n").encode()
    while raw:
        raw = raw[os.write(1, raw):]

for raw in sys.stdin.buffer:
    log.write(raw)
    try:
        message = json.loads(raw)
    except (ValueError, UnicodeError):
        os.write(1, raw)
        continue
    if not isinstance(message, dict):
        os.write(1, raw)
        continue
    method, params = message.get("method"), message.get("params", {})
    result = {"childPid": os.getpid()}
    if method == "initialize":
        initializations += 1
        result["initializations"] = initializations
    elif method == "thread/start":
        ephemeral = params.get("ephemeral") is True
        result["thread"] = {"id": "helper-thread" if ephemeral else "test-thread", "cwd": os.environ["CHECK_THREAD_CWD"]}
        if ephemeral:
            result["thread"]["ephemeral"] = True
    elif method == "thread/read":
        if params.get("hold"):
            continue
        result.update(thread={"id": params["threadId"]}, initializations=initializations)
        if isinstance(message["id"], str) and message["id"].startswith("__codex_bridge__/"):
            emit({"method": "test/notice", "params": {"threadId": "test-thread", "text": "你好"}})
    elif method == "turn/steer":
        result["turnId"] = params["expectedTurnId"]
    elif method == "test/echo":
        result["text"] = params["text"]
    elif method == "test/approval":
        emit({"id": 404, "method": "item/commandExecution/requestApproval",
              "params": {"threadId": "test-thread", "turnId": "test-turn", "command": "true"}})
        continue
    elif method is None and message.get("id") == 404:
        emit({"method": "test/approved", "params": {"decision": message["result"]}})
        continue
    elif method == "remoteControl/pairing/start":
        result.update(pairingCode="SYNTHETIC_PAIRING_CODE", token="SYNTHETIC_PAIRING_TOKEN")
    elif method == "remoteControl/pairing/status":
        result.update(status="paired", pairingCode=params["pairingCode"])
    elif method and method.startswith("remoteControl/"):
        result["status"] = "enabled" if method == "remoteControl/enable" else "disabled"
    emit({"id": message["id"], "result": result})
    if method == "thread/start":
        emit({"method": "turn/started", "params": {"threadId": result["thread"]["id"],
              "turn": {"id": "helper-turn" if ephemeral else "test-turn"}}})
    if method == "test/exit":
        sys.exit(7)
'''


def encoded(message):
    return (json.dumps(message, ensure_ascii=False) + "\n").encode()


def wait_for(predicate, message):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError(message)


def read_line(pipe):
    result = b""
    deadline = time.monotonic() + 5
    while not result.endswith(b"\n"):
        remaining = deadline - time.monotonic()
        assert remaining > 0 and select.select([pipe], [], [], remaining)[0], "VS Code stdout timed out"
        data = os.read(pipe.fileno(), 1)
        assert data, "unexpected VS Code stdout EOF"
        result += data
    return result


def socket_reply(conn):
    raw = b""
    while not raw.endswith(b"\n"):
        data = conn.recv(65536)
        if not data:
            return None
        raw += data
    return json.loads(raw)


def main():
    source = Path(__file__).resolve().parents[1] / "wrapper"
    with tempfile.TemporaryDirectory(prefix="codex-control-check-") as temp:
        root = Path(temp)
        for name in ("codex-wrapper", "control.py", "protocol.py"):
            shutil.copyfile(source / name, root / name)
        wrapper = root / "codex-wrapper"
        wrapper.chmod(0o700)
        child = root / "fake-app-server"
        child.write_text(FAKE_SERVER)
        child.chmod(0o700)
        workspace = root / "workspace"
        workspace.mkdir()
        workspace_alias = root / "workspace-alias"
        workspace_alias.symlink_to(workspace, target_is_directory=True)
        received = root / "received.bin"
        capture_root = root / "captures"
        wrapper.with_suffix(".local.json").write_text(json.dumps({
            "realExecutable": str(child), "captureCwd": str(workspace),
            "captureRoot": str(capture_root), "control": True,
        }))
        process = subprocess.Popen([str(wrapper), "app-server"], cwd=workspace,
                                   env=dict(os.environ, CHECK_RECEIVED=str(received), CHECK_THREAD_CWD=str(workspace_alias)),
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
        pending = None
        try:
            socket_path = wait_for(lambda: next(capture_root.glob("*/control.sock"), None),
                                   "control socket was not created")
            assert socket_path.stat().st_mode & 0o777 == 0o600

            def call(method, params=None):
                request = {"method": method}
                if params is not None:
                    request["params"] = params
                with socket.socket(socket.AF_UNIX) as conn:
                    conn.settimeout(5)
                    conn.connect(str(socket_path))
                    conn.sendall(encoded(request))
                    return socket_reply(conn)

            def send(message):
                process.stdin.write(encoded(message))
                process.stdin.flush()

            def read_message():
                return json.loads(read_line(process.stdout))

            def no_stdout():
                assert not select.select([process.stdout], [], [], 0.05)[0], "bridge response leaked to VS Code"

            status = call("status")["result"]
            child_pid = status["childPid"]
            assert not status["initialized"] and status["threads"] == []
            assert "error" in call("thread/read", {"threadId": "test-thread"})
            send({"id": 10, "method": "initialize"})
            initialized = read_message()
            assert initialized == {"id": 10, "result": {"childPid": child_pid, "initializations": 1}}
            send({"id": 9, "method": "thread/start", "params": {"cwd": str(workspace), "ephemeral": True}})
            assert read_message() == {"id": 9, "result": {
                "childPid": child_pid, "thread": {"id": "helper-thread", "cwd": str(workspace_alias), "ephemeral": True}}}
            assert read_message() == {"method": "turn/started", "params": {
                "threadId": "helper-thread", "turn": {"id": "helper-turn"}}}
            assert call("status")["result"] == {"initialized": True, "childPid": child_pid,
                                                "threads": [], "activeTurns": {}}
            send({"id": 11, "method": "thread/start", "params": {"cwd": str(workspace)}})
            assert read_message() == {"id": 11, "result": {
                "childPid": child_pid, "thread": {"id": "test-thread", "cwd": str(workspace_alias)}}}
            assert read_message() == {"method": "turn/started", "params": {
                "threadId": "test-thread", "turn": {"id": "test-turn"}}}
            assert call("status")["result"] == {"initialized": True, "childPid": child_pid,
                                                "threads": ["test-thread"],
                                                "activeTurns": {"test-thread": "test-turn"}}
            print("PASS ephemeral helper remains visible to VS Code but is excluded from control threads/turns")
            print("PASS thread cwd symlink alias registers in the same disposable workspace")
            print("PASS only VS Code initializes; status observes the same loaded child/thread/turn")

            reply = call("thread/read", {"threadId": "test-thread"})
            assert reply["id"].startswith("__codex_bridge__/")
            assert reply["result"] == {"childPid": child_pid, "thread": {"id": "test-thread"}, "initializations": 1}
            assert read_message() == {"method": "test/notice", "params": {"threadId": "test-thread", "text": "你好"}}
            no_stdout()
            send({"id": 12, "method": "thread/read", "params": {"threadId": "test-thread"}})
            assert read_message() == {"id": 12, "result": reply["result"]}
            print("PASS independent bridge ID response is private; VS Code response/notification remain intact")

            before = received.read_bytes()
            for method, params in [
                ("initialize", {}), ("thread/resume", {"threadId": "test-thread"}),
                ("turn/start", {"threadId": "test-thread"}),
                ("approval/answer", {"id": 404}),
                ("thread/read", {"threadId": "unknown-thread"}),
                ("thread/read", {"threadId": "helper-thread"}),
                ("turn/steer", {"threadId": "helper-thread", "expectedTurnId": "helper-turn", "input": [{"type": "text", "text": "hello"}]}),
                ("turn/steer", {"threadId": "test-thread", "expectedTurnId": "wrong-turn", "input": [{"type": "text", "text": "hello"}]}),
                ("turn/steer", {"threadId": "test-thread", "expectedTurnId": "test-turn", "input": []}),
                ("remoteControl/enable", {}), ("remoteControl/disable", {"ephemeral": False}),
                ("remoteControl/enable", {"ephemeral": 1}),
                ("remoteControl/enable", {"ephemeral": True, "extra": True}),
                ("remoteControl/pairing/start", {}),
                ("remoteControl/pairing/start", {"manualCode": False}),
                ("remoteControl/pairing/start", {"manualCode": 1}),
                ("remoteControl/pairing/start", {"manualCode": True, "extra": True}),
                ("remoteControl/pairing/status", {}),
                ("remoteControl/pairing/status", {"pairingCode": ""}),
                ("remoteControl/pairing/status", {"pairingCode": None}),
                ("remoteControl/pairing/status", {"pairingCode": 123}),
                ("remoteControl/pairing/status", {"pairingCode": True}),
                ("remoteControl/pairing/status", {"pairingCode": "SYNTHETIC_PAIRING_CODE", "extra": True}),
                ("remoteControl/pairing/status", []),
            ]:
                assert "error" in call(method, params), f"unexpectedly allowed {method} {params}"
            assert received.read_bytes() == before, "rejected controller request reached child"
            steer = call("turn/steer", {"threadId": "test-thread", "expectedTurnId": "test-turn",
                                        "input": [{"type": "text", "text": "harmless test"}]})
            assert steer["result"] == {"childPid": child_pid, "turnId": "test-turn"}
            for method in ("remoteControl/status/read", "remoteControl/enable", "remoteControl/disable"):
                reply = call(method, None if method.endswith("read") else {"ephemeral": True})
                assert reply["result"]["childPid"] == child_pid
            no_stdout()
            print("PASS writer/turn guards, same-child steering, strict ephemeral Remote gate")

            pairing = call("remoteControl/pairing/start", {"manualCode": True})
            assert pairing["id"].startswith("__codex_bridge__/")
            assert pairing["result"] == {"childPid": child_pid, "pairingCode": "SYNTHETIC_PAIRING_CODE",
                                        "token": "SYNTHETIC_PAIRING_TOKEN"}
            paired = call("remoteControl/pairing/status", {"pairingCode": pairing["result"]["pairingCode"]})
            assert paired["id"].startswith("__codex_bridge__/") and paired["id"] != pairing["id"]
            assert paired["result"] == {"childPid": child_pid, "status": "paired",
                                       "pairingCode": "SYNTHETIC_PAIRING_CODE"}
            no_stdout()
            print("PASS pairing stays on same child with private IDs/credentials; invalid parameters never reach child")

            send({"id": 13, "method": "test/approval"})
            approval = read_message()
            assert approval == {"id": 404, "method": "item/commandExecution/requestApproval",
                                "params": {"threadId": "test-thread", "turnId": "test-turn", "command": "true"}}
            answer = {"id": 404, "result": "accept"}
            send(answer)
            assert read_message() == {"method": "test/approved", "params": {"decision": "accept"}}
            assert received.read_bytes().splitlines().count(encoded(answer).rstrip(b"\n")) == 1
            print("PASS server approval keeps original ID and receives exactly one VS Code answer")

            partial = encoded({"id": 14, "method": "test/echo", "params": {"text": "partial frame 测试"}})
            process.stdin.write(partial[:19])
            process.stdin.flush()
            reply = call("thread/read", {"threadId": "test-thread"})
            assert read_message()["method"] == "test/notice"
            process.stdin.write(partial[19:])
            process.stdin.flush()
            assert read_message() == {"id": 14, "result": {"childPid": child_pid, "text": "partial frame 测试"}}
            assert received.read_bytes().splitlines().count(partial.rstrip(b"\n")) == 1
            no_stdout()
            print("PASS bridge request cannot split a partial VS Code JSONL frame")

            for raw in (b'{invalid JSON\x00\xff}\n', b'["nonobject", 1]\n', b'null\n'):
                process.stdin.write(raw)
                process.stdin.flush()
                assert read_line(process.stdout) == raw, "malformed/nonobject frame bytes changed"
                assert received.read_bytes().endswith(raw)
            with socket.socket(socket.AF_UNIX) as disconnected:
                disconnected.connect(str(socket_path))
                disconnected.sendall(encoded({"method": "status"}))
            assert call("status")["result"]["childPid"] == child_pid and process.poll() is None
            print("PASS malformed/nonobject VS Code bytes preserved; controller disconnect keeps child alive")

            pending = socket.socket(socket.AF_UNIX)
            pending.settimeout(5)
            pending.connect(str(socket_path))
            pending.sendall(encoded({"method": "thread/read", "params": {"threadId": "test-thread", "hold": True}}))
            wait_for(lambda: b'"hold": true' in received.read_bytes(), "pending bridge request not sent")
            send({"id": 15, "method": "test/exit"})
            assert read_message() == {"id": 15, "result": {"childPid": child_pid}}
            pending_result = socket_reply(pending)
            assert pending_result is None or "error" in pending_result
            process.wait(timeout=5)
            assert process.returncode == 7 and not socket_path.exists()
            assert process.stderr.read() == b""
            messages = [json.loads(line) for line in received.read_bytes().splitlines()
                        if line.startswith(b'{"')]
            assert sum(m.get("method") == "initialize" for m in messages) == 1
            assert sum(m.get("method") == "turn/steer" for m in messages) == 1
            bridge_ids = [m["id"] for m in messages if isinstance(m.get("id"), str)
                          and m["id"].startswith("__codex_bridge__/")]
            assert len(bridge_ids) == len(set(bridge_ids))
            print("PASS child exit preserves exit code, resolves pending connection, removes socket")
        finally:
            if pending is not None:
                pending.close()
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()


if __name__ == "__main__":
    main()
