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
from xml.etree import ElementTree

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


def check_backend_discovery():
    with tempfile.TemporaryDirectory(prefix="codex-backend-discovery-check-") as temp:
        root = Path(temp)
        runs = root / "runs"
        graph = {}
        for name, pid, meta_pid, initialized, active, cwd in [
            ("empty", 101, 101, True, False, "/synthetic launch directory"),
            ("busy", 202, 202, True, True, "/synthetic busy directory"),
            ("uninitialized", 303, 303, False, False, "/synthetic launch directory"),
            ("stale", 404, 909, True, False, "/synthetic launch directory"),
            ("dead", 505, 505, True, False, "/synthetic launch directory"),
        ]:
            run = runs / name
            run.mkdir(parents=True)
            path = run / "control.sock"
            path.touch()
            meta = {"childPid": meta_pid, "cwd": cwd}
            (run / "process.json").write_text(json.dumps(meta))
            graph[str(path)] = (name, {"initialized": initialized, "childPid": pid,
                                      "threads": [], "activeTurns": {"unread-thread": "turn"} if active else {}})

        def request(path, method, params=None):
            assert method == "status", "backend discovery queried a chat"
            name, status = graph[str(path)]
            if name == "dead":
                raise OSError("synthetic unavailable socket")
            return {"result": status}

        with patch.object(remote, "call", side_effect=request):
            found = remote.discover(runs)
            assert {item["childPid"] for item in found} == {101, 202}
            empty = next(item for item in found if item["childPid"] == 101)
            assert empty == {"socket": str(runs / "empty/control.sock"), "childPid": 101,
                             "cwd": "/synthetic launch directory", "active": False}
            busy = next(item for item in found if item["childPid"] == 202)
            assert busy["cwd"] == "/synthetic busy directory" and busy["active"] is True
            assert "threadId" not in busy and "workspace" not in busy
            try:
                remote.select(found)
            except remote.UserError as error:
                assert "--pid" in str(error)
            else:
                raise AssertionError("multiple backends selected implicitly")
            assert remote.select(remote.discover(runs, pid=202)) == busy

            (root / "wrapper").mkdir()
            (root / "wrapper/codex-wrapper.local.json").write_text(json.dumps({"captureRoot": str(runs)}))
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(remote, "PROJECT", root), \
                    patch.object(remote.Path, "cwd", side_effect=AssertionError("default list inspected current directory")), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                assert remote.main(["list", "--pid", "202"]) == 0
            assert json.loads(stdout.getvalue()) == [{"childPid": 202, "cwd": "/synthetic busy directory", "active": True}]
            assert stderr.getvalue() == ""
    print("PASS backend discover/list: initialized process without chats, metadata/PID checks, no thread/writer reads, explicit PID, no current-directory filter")


def operation(initial, action="connect", failure=None, other_connected=False, identity_change=None):
    with tempfile.TemporaryDirectory(prefix="codex-daily-operation-check-") as temp:
        root = Path(temp)
        project, runs = root / "project", root / "runs"
        (project / "wrapper").mkdir(parents=True)
        path = runs / "one" / "control.sock"
        path.parent.mkdir(parents=True, mode=0o700)
        path.touch()
        (path.parent / "process.json").write_text(json.dumps({"childPid": 101, "cwd": str(root)}))
        (project / "wrapper/codex-wrapper.local.json").write_text(json.dumps({"captureRoot": str(runs)}))
        other_path = runs / "two" / "control.sock"
        if other_connected:
            other_path.parent.mkdir()
            other_path.touch()
            (other_path.parent / "process.json").write_text(json.dumps({"childPid": 202, "cwd": str(root)}))
        state, calls = {"status": initial, "statusReads": 0, "enabled": False}, []
        secrets = ("SYNTHETIC_PAIRING_SECRET", "SYNTHETIC_MANUAL_SECRET", "SYNTHETIC_HOST_SECRET")

        def request(socket_path, method, params=None):
            calls.append((str(socket_path), method, params))
            if str(socket_path) == str(other_path):
                assert method in ("status", "remoteControl/status/read"), "wrote to another owner"
                return {"result": {"initialized": True, "childPid": 202, "threads": [], "activeTurns": {}} if method == "status" else {"status": "connected"}}
            assert str(socket_path) == str(path)
            if method == "status":
                state["statusReads"] += 1
                pid, initialized = 101, True
                if identity_change is not None:
                    stage, kind = identity_change
                    changed = state["statusReads"] >= 2 if stage == "before" else state["enabled"]
                    if changed:
                        if kind == "child":
                            pid = 909
                        elif kind == "metadata":
                            (path.parent / "process.json").write_text(json.dumps({"childPid": 909, "cwd": str(root)}))
                        else:
                            initialized = False
                return {"result": {"initialized": initialized, "childPid": pid,
                                   "threads": [], "activeTurns": {}}}
            if method == "remoteControl/status/read":
                return {"result": {"status": state["status"], "serverName": secrets[2]}}
            if method in ("remoteControl/enable", "remoteControl/disable"):
                assert params == {"ephemeral": True}
                if method.endswith("enable") and failure == "enable":
                    raise OSError(secrets[0])
                if method.endswith("enable"):
                    state["enabled"] = True
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

        folder = path.parent / "pairing"
        if action == "status":
            folder.mkdir(mode=0o700)
            (folder / "state.json").write_text(json.dumps({"childPid": 101, "pairing": {"pairingCode": secrets[0]}}))
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(remote, "PROJECT", project), patch.object(remote, "call", side_effect=request), \
                patch.object(remote, "wait_remote_status", side_effect=wait), \
                patch.object(remote.Path, "cwd", side_effect=AssertionError("operation inspected current directory")), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = remote.main([action, "--pid", "101"])
        assert all(secret not in stdout.getvalue() + stderr.getvalue() for secret in secrets)
        report = json.loads(stdout.getvalue()) if stdout.getvalue() else None
        if report is not None:
            assert report["action"] == action and report["childPid"] == 101
            assert not {"workspace", "cwd", "threadId"}.intersection(report)
            assert sum(method == "status" for _, method, _ in calls) >= 3, "operation skipped before/after identity checks"
        artifacts = ({p.name: (p.stat().st_mode & 0o777, p.read_text()) for p in folder.iterdir()}
                     if folder.exists() else {})
        mode = folder.stat().st_mode & 0o777 if folder.exists() else None
        return code, report, calls, artifacts, mode, state["status"]


def check_operations():
    for initial in ("connected", "connecting", "disabled"):
        code, report, calls, _, _, _ = operation(initial)
        assert code == 0 and report["status"] == "connected"
        assert set(report) == {"action", "childPid", "status"}
        writes = [method for _, method, _ in calls if method not in ("status", "remoteControl/status/read")]
        assert writes == (["remoteControl/enable"] if initial == "disabled" else [])
    code, _, calls, _, _, _ = operation("disabled", other_connected=True)
    assert code == 1 and all(method in ("status", "remoteControl/status/read") for _, method, _ in calls)
    print("PASS connect: connected/connecting reuse, disabled-only enable, other connected owner blocks switching")

    code, report, calls, files, mode, _ = operation("disabled", action="pair")
    assert code == 0 and report["qrAvailable"] is True
    assert mode == 0o700 and set(files) == {"state.json", "pairing.html", "pairing.svg"}
    assert all(file_mode == 0o600 for file_mode, _ in files.values())
    assert "SYNTHETIC_MANUAL_SECRET" in files["pairing.html"][1]
    assert "SYNTHETIC_PAIRING_SECRET" in files["state.json"][1]
    code, report, calls, _, _, _ = operation("connected", action="status")
    assert code == 0 and report["pairingClaimed"] is True
    assert all(method in ("status", "remoteControl/status/read", "remoteControl/pairing/status") for _, method, _ in calls)
    code, report, calls, _, _, status = operation("connected", action="disconnect")
    assert code == 0 and report["childPid"] == 101 and status == "disabled"
    assert set(report) == {"action", "childPid", "status"}
    assert [method for _, method, _ in calls if method not in ("status", "remoteControl/status/read")] == ["remoteControl/disable"]
    code, report, calls, _, _, status = operation("disabled", action="disconnect")
    assert code == 0 and status == "disabled"
    assert all(method in ("status", "remoteControl/status/read") for _, method, _ in calls)
    print("PASS pair/status/disconnect: bundled QR/private files, no credential output, status reads only, disabled disconnect reuses state")

    for initial, failure, expected in [
        ("disabled", "pair", ["remoteControl/enable", "remoteControl/pairing/start", "remoteControl/disable"]),
        ("connected", "pair", ["remoteControl/pairing/start"]),
        ("connecting", "wait", []),
        ("disabled", "enable", ["remoteControl/enable", "remoteControl/disable"]),
    ]:
        code, _, calls, _, _, _ = operation(initial, action="pair", failure=failure)
        assert code == 1
        writes = [method for _, method, _ in calls if method not in ("status", "remoteControl/status/read")]
        assert writes == expected, "failure retried a write or disabled a preexisting connection"
        assert len({path for path, method, _ in calls if method in writes}) <= 1
    print("PASS failures: only newly enabled connection restored, unknown writes never retried or sent to another backend")


def check_backend_identity_changes():
    for stage in ("before", "after"):
        for kind in ("child", "metadata", "initialized"):
            code, report, calls, _, _, _ = operation("disabled", identity_change=(stage, kind))
            assert code == 1 and report is None
            writes = [method for _, method, _ in calls
                      if method not in ("status", "remoteControl/status/read")]
            assert writes == ([] if stage == "before" else ["remoteControl/enable"]), \
                "changed backend received a write, rollback or replay"
            if stage == "before":
                assert all(method == "status" for _, method, _ in calls)
    print("PASS backend identity changes: changed child/metadata/initialization before action refuses writes; after action refuses rollback or replay")


def check_page():
    with tempfile.TemporaryDirectory(prefix="codex-daily-page-check-") as temp:
        root = Path(temp)
        folder = root / "pairing"
        folder.mkdir(mode=0o700)
        (folder / "pairing.svg").write_text("SYNTHETIC_OLD_QR")
        assert remote.write_pairing_page(folder, {"serverName": "SYNTHETIC_HOST_SECRET"}, {
            "pairingCode": "SYNTHETIC_PAIRING_SECRET", "manualPairingCode": "SYNTHETIC_MANUAL_SECRET",
            "expiresAt": 1700000000,
        }) is True
        svg = folder / "pairing.svg"
        assert svg.stat().st_mode & 0o777 == 0o600
        assert ElementTree.parse(svg).getroot().tag == "{http://www.w3.org/2000/svg}svg"
        page = folder / "pairing.html"
        assert page.stat().st_mode & 0o777 == 0o600
        assert "SYNTHETIC_MANUAL_SECRET" in page.read_text() and "2023-11-14 22:13:20 UTC" in page.read_text()

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
            assert remote.main(["pair", "--open"]) == 0
        operate.assert_called_once_with("pair", target)
        assert json.loads(stdout.getvalue()) == report and "手动打开" in stderr.getvalue()
        assert "SYNTHETIC_PAIRING_SECRET" not in stdout.getvalue() + stderr.getvalue()
    print("PASS private page: bundled SVG/manual code/UTC expiry and private files; mocked WSL/Linux opener; browser failure keeps successful connection")


if __name__ == "__main__":
    if "--backend-lifecycle" in sys.argv:
        check_backend_discovery()
        check_backend_identity_changes()
        check_operations()
        check_page()
        raise SystemExit(0)
    check_wrapper()
    check_backend_discovery()
    check_backend_identity_changes()
    check_operations()
    check_page()
