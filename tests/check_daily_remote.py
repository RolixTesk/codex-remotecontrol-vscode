#!/usr/bin/env python3
"""Offline daily-mode checks: fake stdio child and mocked Remote calls only."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
from unittest.mock import patch

from check_control import encoded, read_line, socket_reply, wait_for

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import remote


FAKE_SERVER = r'''#!/usr/bin/env python3
import json
import os
import sys

def emit(value):
    data = (json.dumps(value, ensure_ascii=False) + "\n").encode()
    while data:
        data = data[os.write(1, data):]

identity = {"childPid": os.getpid(), "cwd": os.getcwd(), "argv": sys.argv[1:], "env": os.environ["CHECK_VALUE"]}
if "app-server" not in sys.argv:
    emit(identity)
    sys.exit(0)
threads, answers = {}, 0
for raw in sys.stdin.buffer:
    message = json.loads(raw)
    method, params = message.get("method"), message.get("params", {})
    if method == "test/raw":
        os.write(1, raw)
        continue
    if method == "test/approval":
        emit({"id": 404, "method": "item/commandExecution/requestApproval", "params": {"command": "true"}})
        continue
    if method is None and message["id"] == 404:
        answers += 1
        emit({"method": "test/approved", "params": {"answers": answers, "decision": message["result"]}})
        continue
    result = dict(identity)
    if method == "thread/start":
        thread = {"id": params["threadId"], "cwd": params["cwd"], "ephemeral": params.get("ephemeral", False)}
        threads[thread["id"]] = thread
        result["thread"] = thread
    elif method == "test/unloaded":
        emit({"method": "thread/started", "params": {"thread": {"id": "unloaded", "cwd": params["cwd"]}}})
        continue
    elif method == "thread/read":
        result["thread"] = threads[params["threadId"]]
    emit({"id": message["id"], "result": result})
'''


def check_wrapper():
    with tempfile.TemporaryDirectory(prefix="codex-daily-wrapper-check-") as temp:
        root = Path(temp)
        source = Path(__file__).resolve().parents[1] / "wrapper"
        for name in ("codex-wrapper", "control.py", "protocol.py"):
            shutil.copyfile(source / name, root / name)
        wrapper, child = root / "codex-wrapper", root / "fake-child"
        wrapper.chmod(0o700)
        child.write_text(FAKE_SERVER)
        child.chmod(0o700)
        launch, project_a, project_b = root / "launch", root / "project-a", root / "project-b"
        for directory in (launch, project_a, project_b):
            directory.mkdir()
        captures = root / "runs"
        config = {"mode": "bridge", "realExecutable": str(child), "captureRoot": str(captures)}
        wrapper.with_suffix(".local.json").write_text(json.dumps(config))
        env = dict(os.environ, CHECK_VALUE="SYNTHETIC_ENV_SECRET")
        args = ["app-server", "SYNTHETIC_ARGV_SECRET", "space 测试"]
        process = subprocess.Popen([str(wrapper), *args], cwd=launch, env=env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
        try:
            path = wait_for(lambda: next(captures.glob("*/control.sock"), None), "daily socket missing")

            def control(method, params=None):
                request = {"method": method}
                if params is not None:
                    request["params"] = params
                with socket.socket(socket.AF_UNIX) as conn:
                    conn.settimeout(5)
                    conn.connect(str(path))
                    conn.sendall(encoded(request))
                    return socket_reply(conn)

            def vscode(message):
                process.stdin.write(encoded(message))
                process.stdin.flush()
                return json.loads(read_line(process.stdout))

            child_pid = control("status")["result"]["childPid"]
            identity = {"childPid": child_pid, "cwd": str(launch), "argv": args, "env": env["CHECK_VALUE"]}
            assert vscode({"id": 1, "method": "initialize"}) == {"id": 1, "result": identity}
            for number, thread, cwd, ephemeral in [(2, "thread-a", project_a, False),
                                                  (3, "thread-b", project_b, False),
                                                  (4, "ephemeral", project_a, True)]:
                reply = vscode({"id": number, "method": "thread/start", "params": {
                    "threadId": thread, "cwd": str(cwd), "ephemeral": ephemeral,
                }})
                assert reply["id"] == number and reply["result"]["thread"]["cwd"] == str(cwd)
            process.stdin.write(encoded({"id": 5, "method": "test/unloaded", "params": {"cwd": str(project_a)}}))
            process.stdin.flush()
            assert json.loads(read_line(process.stdout))["method"] == "thread/started"
            assert control("status")["result"]["threads"] == ["thread-a", "thread-b"]
            for thread in ("thread-a", "thread-b"):
                reply = control("thread/read", {"threadId": thread})
                assert reply["id"].startswith("__codex_bridge__/")
                assert reply["result"]["childPid"] == child_pid and reply["result"]["thread"]["id"] == thread
            for thread in ("ephemeral", "unloaded"):
                assert "error" in control("thread/read", {"threadId": thread})
            assert not select.select([process.stdout], [], [], .05)[0], "private response leaked"
            raw = b'{  "id": 6, "method": "test/raw", "text": "SYNTHETIC_STDIN_SECRET" }\r\n'
            process.stdin.write(raw)
            process.stdin.flush()
            assert read_line(process.stdout) == raw
            approval = vscode({"id": 7, "method": "test/approval"})
            assert approval == {"id": 404, "method": "item/commandExecution/requestApproval", "params": {"command": "true"}}
            assert vscode({"id": 404, "result": "accept"}) == {"method": "test/approved", "params": {"answers": 1, "decision": "accept"}}
            assert {p.name for p in path.parent.iterdir()} == {"process.json", "control.sock"}
            process.stdin.close()
            process.stdin = None
            stdout, stderr = process.communicate(timeout=5)
            assert stdout == stderr == b"" and process.returncode == 0
            metadata = json.loads((path.parent / "process.json").read_text())
            assert metadata["mode"] == "bridge" and "argv" not in metadata
            serialized = json.dumps(metadata)
            assert all(secret not in serialized for secret in ("SYNTHETIC_ENV_SECRET", "SYNTHETIC_ARGV_SECRET", "SYNTHETIC_STDIN_SECRET"))
            assert {p.name for p in path.parent.iterdir()} == {"process.json"}
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()

        config["captureRoot"] = str(root / "non-app-runs")
        wrapper.with_suffix(".local.json").write_text(json.dumps(config))
        fallback = subprocess.Popen([str(wrapper), "--version"], cwd=project_b, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = fallback.communicate(timeout=5)
        assert fallback.returncode == 0 and stderr == b""
        assert json.loads(stdout) == {"childPid": fallback.pid, "cwd": str(project_b),
                                      "argv": ["--version"], "env": env["CHECK_VALUE"]}
        assert not Path(config["captureRoot"]).exists()
    print("PASS daily wrapper: no captureCwd/raw logs/argv; cwd/env/frames, two projects, private replies/approvals, exec fallback")


def check_discovery():
    with tempfile.TemporaryDirectory(prefix="codex-daily-discovery-check-") as temp:
        root = Path(temp)
        runs, workspace, other = root / "runs", root / "project", root / "other"
        workspace.mkdir()
        other.mkdir()
        alias = root / "project-alias"
        alias.symlink_to(workspace, target_is_directory=True)
        graph = {}
        for name, pid, meta_pid, threads in [
            ("one", 101, 101, ["good", "other", "ephemeral", "wrong-owner", "shared-owner"]),
            ("two", 202, 202, ["second"]), ("stale", 303, 909, ["stale"]),
            ("dead", 404, 404, []),
        ]:
            run = runs / name
            run.mkdir(parents=True)
            (run / "control.sock").touch()
            (run / "process.json").write_text(json.dumps({"childPid": meta_pid}))
            graph[str(run / "control.sock")] = (pid, threads, name)

        def request(path, method, params=None):
            pid, threads, name = graph[str(path)]
            if name == "dead":
                raise OSError("synthetic unavailable socket")
            if method == "status":
                return {"result": {"initialized": True, "childPid": pid, "threads": threads, "activeTurns": {"good": "turn"}}}
            assert method == "thread/read"
            tid = params["threadId"]
            return {"result": {"thread": {"id": tid, "cwd": str(other if tid == "other" else alias), "ephemeral": tid == "ephemeral"}}}

        owner_map = {"good": [101], "other": [101], "ephemeral": [101],
                     "wrong-owner": [909], "shared-owner": [101, 202], "second": [202]}
        with patch.object(remote, "call", side_effect=request) as calls, \
                patch.object(remote, "owners", side_effect=lambda tid: owner_map.get(tid, [])):
            found = remote.discover(runs, workspace)
            assert [(t["childPid"], t["threadId"]) for t in found] == [(101, "good"), (202, "second")]
            assert found[0]["active"]
            try:
                remote.select(found)
            except remote.UserError as error:
                assert "--pid" in str(error)
            else:
                raise AssertionError("multiple owners selected implicitly")
            assert remote.select(remote.discover(runs, workspace, 202))["threadId"] == "second"
            assert remote.discover(runs, other)[0]["threadId"] == "other"
            assert all(item.args[1] in ("status", "thread/read") for item in calls.call_args_list)
    print("PASS discover: samefile workspace, unique owner, stale/dead/ephemeral rejection, explicit PID selection")


def operation(initial, action="connect", failure=None, other_connected=False, writer_changes=False):
    with tempfile.TemporaryDirectory(prefix="codex-daily-operation-check-") as temp:
        root = Path(temp)
        project, workspace, runs = root / "project", root / "workspace", root / "runs"
        (project / "wrapper").mkdir(parents=True)
        workspace.mkdir()
        path = runs / "one" / "control.sock"
        path.parent.mkdir(parents=True, mode=0o700)
        path.touch()
        (path.parent / "process.json").write_text(json.dumps({"childPid": 101}))
        (project / "wrapper/codex-wrapper.local.json").write_text(json.dumps({"captureRoot": str(runs)}))
        other_path = runs / "two" / "control.sock"
        if other_connected:
            other_path.parent.mkdir()
            other_path.touch()
            (other_path.parent / "process.json").write_text(json.dumps({"childPid": 202}))
        state, calls = {"status": initial, "owners": 0}, []
        secrets = ("SYNTHETIC_PAIRING_SECRET", "SYNTHETIC_MANUAL_SECRET", "SYNTHETIC_HOST_SECRET")

        def request(socket_path, method, params=None):
            calls.append((str(socket_path), method, params))
            if str(socket_path) == str(other_path):
                assert method in ("status", "remoteControl/status/read"), "wrote to another owner"
                return {"result": {"initialized": True, "childPid": 202, "threads": [], "activeTurns": {}} if method == "status" else {"status": "connected"}}
            assert str(socket_path) == str(path)
            if method == "status":
                return {"result": {"initialized": True, "childPid": 101, "threads": ["thread"], "activeTurns": {}}}
            if method == "thread/read":
                assert params == {"threadId": "thread", "includeTurns": False}
                return {"result": {"thread": {"id": "thread", "cwd": str(workspace), "ephemeral": False}}}
            if method == "remoteControl/status/read":
                return {"result": {"status": state["status"], "serverName": secrets[2]}}
            if method in ("remoteControl/enable", "remoteControl/disable"):
                assert params == {"ephemeral": True}
                if method.endswith("enable") and failure == "enable":
                    raise OSError(secrets[0])
                state["status"] = "connecting" if method.endswith("enable") else "disabled"
                return {"result": {"status": state["status"]}}
            if method == "remoteControl/pairing/start":
                assert params == {"manualCode": True}
                if failure == "pair":
                    raise OSError(secrets[0])
                return {"result": {"pairingCode": secrets[0], "manualPairingCode": secrets[1], "expiresAt": 123456}}
            if method == "remoteControl/pairing/status":
                assert params == {"pairingCode": secrets[0]}
                return {"result": {"claimed": True}}
            raise AssertionError(f"unexpected method {method}")

        def wait(socket_path, desired, seconds):
            assert str(socket_path) == str(path)
            if desired == "connected" and failure == "wait":
                raise TimeoutError(secrets[0])
            state["status"] = desired
            return {"status": desired, "serverName": secrets[2]}

        def owners(thread):
            assert thread == "thread"
            state["owners"] += 1
            return [202] if writer_changes and state["owners"] > 1 else [101]

        folder = path.parent / "pairing"
        if action == "status":
            folder.mkdir(mode=0o700)
            (folder / "state.json").write_text(json.dumps({"childPid": 101, "pairing": {"pairingCode": secrets[0]}}))
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(remote, "PROJECT", project), patch.object(remote, "call", side_effect=request), \
                patch.object(remote, "owners", side_effect=owners), \
                patch.object(remote, "wait_remote_status", side_effect=wait), \
                patch.dict(sys.modules, {"qrcode": None, "qrcode.image": None, "qrcode.image.svg": None}), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = remote.main([action, "--workspace", str(workspace), "--pid", "101"])
        assert all(secret not in stdout.getvalue() + stderr.getvalue() for secret in secrets)
        report = json.loads(stdout.getvalue()) if stdout.getvalue() else None
        artifacts = ({p.name: (p.stat().st_mode & 0o777, p.read_text()) for p in folder.iterdir()}
                     if folder.exists() else {})
        mode = folder.stat().st_mode & 0o777 if folder.exists() else None
        return code, report, calls, artifacts, mode, state["status"]


def check_operations():
    for initial in ("connected", "connecting", "disabled"):
        code, report, calls, _, _, _ = operation(initial)
        assert code == 0 and report["status"] == "connected"
        writes = [method for _, method, _ in calls if method not in ("status", "thread/read", "remoteControl/status/read")]
        assert writes == (["remoteControl/enable"] if initial == "disabled" else [])
    code, _, calls, _, _, _ = operation("disabled", other_connected=True)
    assert code == 1 and all(method in ("status", "thread/read", "remoteControl/status/read") for _, method, _ in calls)
    print("PASS connect: connected/connecting reuse, disabled-only enable, other connected owner blocks switching")

    code, report, calls, files, mode, _ = operation("disabled", action="pair")
    assert code == 0 and report["qrAvailable"] is False
    assert mode == 0o700 and set(files) == {"state.json", "pairing.html"}
    assert all(file_mode == 0o600 for file_mode, _ in files.values())
    assert "SYNTHETIC_MANUAL_SECRET" in files["pairing.html"][1]
    assert "SYNTHETIC_PAIRING_SECRET" in files["state.json"][1]
    assert "https://chatgpt.com/codex/pair?" in files["pairing.html"][1]
    code, report, calls, _, _, _ = operation("connected", action="status")
    assert code == 0 and report["pairingClaimed"] is True
    assert all(method in ("status", "thread/read", "remoteControl/status/read", "remoteControl/pairing/status") for _, method, _ in calls)
    code, report, calls, _, _, status = operation("connected", action="disconnect")
    assert code == 0 and report["childPid"] == 101 and status == "disabled"
    assert [method for _, method, _ in calls if method not in ("status", "thread/read", "remoteControl/status/read")] == ["remoteControl/disable"]
    print("PASS pair/status/disconnect: private manual page without qrcode, no credential output, reads only, original writer retained")

    for initial, failure, expected in [
        ("disabled", "pair", ["remoteControl/enable", "remoteControl/pairing/start", "remoteControl/disable"]),
        ("connected", "pair", ["remoteControl/pairing/start"]),
        ("connecting", "wait", []),
        ("disabled", "enable", ["remoteControl/enable", "remoteControl/disable"]),
    ]:
        code, _, calls, _, _, _ = operation(initial, action="pair", failure=failure)
        assert code == 1
        writes = [method for _, method, _ in calls if method not in ("status", "thread/read", "remoteControl/status/read")]
        assert writes == expected, "failure retried a write or disabled a preexisting connection"
        assert len({path for path, method, _ in calls if method in writes}) <= 1
    code, _, calls, _, _, _ = operation("disabled", writer_changes=True)
    assert code == 1 and all(method in ("status", "thread/read") for _, method, _ in calls)
    print("PASS failures: only newly enabled connection restored, unknown writes never retried, changed owner refuses writes")


def check_page():
    with tempfile.TemporaryDirectory(prefix="codex-daily-page-check-") as temp:
        root = Path(temp)
        folder = root / "pairing"
        folder.mkdir(mode=0o700)
        (folder / "pairing.svg").write_text("SYNTHETIC_OLD_QR")
        with patch.dict(sys.modules, {"qrcode": None, "qrcode.image": None, "qrcode.image.svg": None}):
            assert remote.write_pairing_page(folder, {"serverName": "SYNTHETIC_HOST_SECRET"}, {
                "pairingCode": "SYNTHETIC_PAIRING_SECRET", "manualPairingCode": "SYNTHETIC_MANUAL_SECRET",
            }) is False
        assert not (folder / "pairing.svg").exists()
        page = folder / "pairing.html"
        assert page.stat().st_mode & 0o777 == 0o600

        windows_path = "\\\\wsl.localhost\\Ubuntu\\private\\O'Brien $HOME\\pairing.html"
        with patch.dict(remote.os.environ, {"WSL_DISTRO_NAME": "synthetic"}), \
                patch.object(remote.subprocess, "run", side_effect=[
                    subprocess.CompletedProcess([], 0, stdout=windows_path + "\n"),
                    subprocess.CompletedProcess([], 0),
                ]) as run:
            remote.open_page(page)
            assert run.call_args_list[0].args[0] == ["wslpath", "-w", str(page)]
            assert run.call_args_list[1].args[0] == [
                "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
                "-NoProfile", "-NonInteractive", "-Command",
                "Start-Process -FilePath '" + windows_path.replace("'", "''") + "'",
            ]
        with patch.dict(remote.os.environ, {"WSL_DISTRO_NAME": ""}), \
                patch.object(remote.webbrowser, "open", return_value=True) as browser:
            remote.open_page(page)
            browser.assert_called_once_with(page.as_uri())

        (root / "wrapper").mkdir()
        (root / "wrapper/codex-wrapper.local.json").write_text(json.dumps({"captureRoot": str(root / "runs")}))
        target = {"childPid": 101}
        report = {"pairingPage": str(page), "status": "connected"}
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(remote, "PROJECT", root), \
                patch.object(remote, "discover", return_value=[target]), \
                patch.object(remote, "operate", return_value=report) as operate, \
                patch.object(remote, "open_page", side_effect=OSError("SYNTHETIC_PAIRING_SECRET")), \
                patch.object(remote, "call", side_effect=AssertionError("browser failure attempted Remote rollback")), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            assert remote.main(["pair", "--workspace", str(root), "--open"]) == 0
        operate.assert_called_once_with("pair", target)
        assert json.loads(stdout.getvalue()) == report and "手动打开" in stderr.getvalue()
        assert "SYNTHETIC_PAIRING_SECRET" not in stdout.getvalue() + stderr.getvalue()
    print("PASS private page: stale QR removed; mocked WSL/Linux opener; browser failure keeps successful connection")


if __name__ == "__main__":
    check_wrapper()
    check_discovery()
    check_operations()
    check_page()
