#!/usr/bin/env python3
"""One bounded experiment on the disposable VS Code-owned process; never resume a thread."""

import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "wrapper"))
from protocol import same_directory
STEER_TEXT = ("这是同一 live turn 的桥接测试。继续完成原任务；完成后只在当前测试目录"
              "创建 bridge-steer.txt，写入 STEER_OK，并在最终回复中确认收到这条 steering。")


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
        raise RuntimeError("Request failed; inspect private probe evidence")
    return reply["result"]


def wait_remote_status(path, desired, seconds):
    deadline = time.monotonic() + seconds
    while True:
        status = result(call(path, "remoteControl/status/read"))
        if status["status"] == desired:
            return status
        if status["status"] == "errored" and desired == "connected":
            raise RuntimeError("Native Remote connection failed; inspect private evidence")
        if time.monotonic() >= deadline:
            raise TimeoutError("Native Remote status did not settle")
        time.sleep(.2)


def owners(thread_id):
    found = set()
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            for fd in (proc / "fd").iterdir():
                try:
                    if os.readlink(fd).endswith(f"/thread-writer-locks/{thread_id}.lock"):
                        if "lock:" in (proc / "fdinfo" / fd.name).read_text():
                            found.add(int(proc.name))
                except OSError:
                    pass
        except OSError:
            pass
    return sorted(found)


def active_writer_turn(status):
    for thread_id, turn_id in status["activeTurns"].items():
        if owners(thread_id) == [status["childPid"]]:
            return thread_id, turn_id
    return None


def probe(wait_seconds):
    config = json.loads((PROJECT / "wrapper/codex-wrapper.local.json").read_text())
    root, cwd = Path(config["captureRoot"]), Path(config["captureCwd"])
    deadline = time.monotonic() + wait_seconds
    evidence, private, stage = {}, {}, "wait-for-wrapper"
    target = None
    report = PROJECT / "evidence/live-probe.json"
    secret_report = root.parent / "live-probe.private.json"

    def save():
        report.write_text(json.dumps(evidence, indent=2) + "\n")
        fd = os.open(secret_report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(private, f)

    try:
        while time.monotonic() < deadline:
            for run in sorted(root.iterdir(), reverse=True):
                path = run / "control.sock"
                if not path.exists():
                    continue
                try:
                    status = result(call(path, "status"))
                except (OSError, RuntimeError, ValueError):
                    continue
                candidates = [t for t in status["threads"] if owners(t) == [status["childPid"]]]
                if status["initialized"] and candidates:
                    target = (run, path, status, candidates[0])
                    break
            if target is not None:
                break
            time.sleep(1)
        if target is None:
            raise TimeoutError("No instrumented disposable VS Code window")
        run, path, status, thread_id = target
        meta = json.loads((run / "process.json").read_text())
        pid = status["childPid"]
        assert pid == meta["childPid"]
        ppid = int(next(s for s in (Path("/proc") / str(pid) / "status").read_text().splitlines()
                        if s.startswith("PPid:")).split()[1])
        assert ppid == meta["wrapperPid"]
        stage = "read"
        reply = call(path, "thread/read", {"threadId": thread_id, "includeTurns": False})
        private["read"] = reply
        thread = result(reply)["thread"]
        assert thread["id"] == thread_id and same_directory(thread["cwd"], cwd)
        assert owners(thread_id) == [pid]
        evidence.update(childPid=pid, wrapperPid=ppid, readPassed=True,
                        initialWriterPids=[pid], captureRun=run.name)
        save()
        print("PASS same-process thread/read and sole writer", flush=True)

        stage = "wait-for-active-turn"
        active = None
        while time.monotonic() < deadline:
            status = result(call(path, "status"))
            assert status["childPid"] == pid
            active = active_writer_turn(status)
            if active is not None:
                break
            time.sleep(0.5)
        if active is None:
            raise TimeoutError("No active disposable turn")
        thread_id, turn_id = active
        reply = call(path, "thread/read", {"threadId": thread_id, "includeTurns": False})
        private["activeRead"] = reply
        active_thread = result(reply)["thread"]
        assert (same_directory(active_thread["cwd"], cwd) and active_thread.get("ephemeral") is not True
                and owners(thread_id) == [pid])
        marker = cwd / "bridge-steer.txt"
        before_mtime = marker.stat().st_mtime_ns if marker.exists() else -1
        stage = "steer"
        reply = call(path, "turn/steer", {
            "threadId": thread_id, "expectedTurnId": turn_id,
            "input": [{"type": "text", "text": STEER_TEXT}],
        })
        private["steer"] = reply
        assert result(reply)["turnId"] == turn_id
        evidence["steerAccepted"] = True
        save()
        print("PASS steering accepted on existing active turn", flush=True)

        stage = "steer-result"
        applied = False
        while time.monotonic() < deadline:
            status = result(call(path, "status"))
            if (marker.exists() and marker.stat().st_mtime_ns > before_mtime
                    and marker.read_text().strip() == "STEER_OK"
                    and thread_id not in status["activeTurns"]):
                applied = True
                break
            time.sleep(1)
        assert applied and status["childPid"] == pid and owners(thread_id) == [pid]
        evidence.update(steerApplied=True, finalWriterPids=[pid], uiReflection="pending human confirmation")
        save()
        print("PASS steering file/result and unchanged writer", flush=True)

        stage = "remote"
        before = call(path, "remoteControl/status/read")
        private["remoteBefore"] = before
        remote = {"before": result(before)["status"]}
        evidence["remote"] = remote
        if remote["before"] == "disabled":
            try:
                enabled = call(path, "remoteControl/enable", {"ephemeral": True})
                private["remoteEnable"] = enabled
                remote["enableAccepted"] = "result" in enabled
                if "result" in enabled:
                    remote["enabledStatus"] = enabled["result"]["status"]
                else:
                    remote["enableErrorCode"] = enabled["error"].get("code")
            finally:
                disabled = call(path, "remoteControl/disable", {"ephemeral": True})
                private["remoteDisable"] = disabled
                remote["disableAccepted"] = "result" in disabled
                after = call(path, "remoteControl/status/read")
                private["remoteAfter"] = after
                remote["after"] = result(after)["status"]
                final = wait_remote_status(path, "disabled", 5)
                private["remoteFinal"] = final
                remote.update(finalVerifiedStatus=final["status"], restoredDisabled=True)
        else:
            remote["skippedEnable"] = "Existing Remote state preserved"
        evidence.update(completed=True, remoteSameChild=result(call(path, "status"))["childPid"] == pid)
        save()
        print("Remote experiment finished; sanitized report saved", flush=True)
    except Exception as exc:
        evidence.update(completed=False, failedStage=stage, failureType=type(exc).__name__)
        save()
        print(f"Probe stopped at {stage} ({type(exc).__name__}); no automatic request retry", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait", type=int, default=600, help="Total bounded wait in seconds")
    probe(parser.parse_args().wait)
