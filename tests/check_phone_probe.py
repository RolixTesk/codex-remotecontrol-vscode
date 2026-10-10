#!/usr/bin/env python3
"""Check phone observation offline with synthetic turns, markers, and ownership."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import probe_phone


def scenario(mode):
    with tempfile.TemporaryDirectory(prefix="codex-phone-probe-check-") as temp:
        root = Path(temp)
        project, workspace = root / "project", root / "workspace"
        captures = root / "private" / "captures"
        (project / "wrapper").mkdir(parents=True)
        (project / "evidence").mkdir()
        captures.mkdir(parents=True)
        workspace.mkdir()
        (project / "wrapper/codex-wrapper.local.json").write_text(json.dumps({
            "captureRoot": str(captures), "captureCwd": str(workspace),
        }))
        anchor = {"socket": str(captures / "run/control.sock"),
                  "childPid": 101, "threadId": "synthetic-phone-thread",
                  "pairing": {"pairingCode": "SYNTHETIC_PRIVATE_PAIRING_CODE"}}
        folder = captures.parent / "pairing"
        folder.mkdir()
        (folder / "state.json").write_text(json.dumps(anchor))
        old_turn = {"id": "old-turn", "status": "completed", "items": []}
        task_message = {"type": "userMessage", "content": [{"type": "text", "text": "Create PHONE_NATIVE_OK"}]}
        steer_message = {"type": "userMessage", "content": [{"type": "text", "text": "Now create PHONE_STEER_OK"}]}
        new_turns = ([{"id": "new-turn", "status": "completed", "items": [task_message, steer_message]}]
                     if mode != "queue" else [
                         {"id": "new-task-turn", "status": "completed", "items": [task_message]},
                         {"id": "new-queued-turn", "status": "completed", "items": [steer_message]},
                     ])
        counters = {"status": 0, "read": 0, "owner": 0}
        clock = [0]

        def request(path, method, params=None):
            assert path == anchor["socket"]
            if method == "status":
                index = counters["status"]
                counters["status"] += 1
                return {"result": {"childPid": 101, "threads": [anchor["threadId"]],
                                   "activeTurns": {anchor["threadId"]: "new-turn"} if index == 1 else {}}}
            if method == "thread/read":
                assert params == {"threadId": anchor["threadId"], "includeTurns": True}
                turns = [old_turn] if counters["read"] == 0 else [old_turn, *new_turns]
                counters["read"] += 1
                return {"result": {"thread": {"cwd": str(workspace), "ephemeral": False, "turns": turns}}}
            if method == "remoteControl/status/read":
                return {"result": {"status": "connected"}}
            raise AssertionError(f"observer attempted non-read method: {method}")

        def owners(thread):
            assert thread == anchor["threadId"]
            counters["owner"] += 1
            return [202] if mode == "changed-writer" and counters["owner"] == 2 else [101]

        def advance(seconds):
            assert seconds == 1
            clock[0] += seconds
            (workspace / "phone-native.txt").write_text("PHONE_NATIVE_OK\n")
            (workspace / "phone-steer.txt").write_text("PHONE_STEER_OK\n")

        output = io.StringIO()
        with patch.object(probe_phone, "PROJECT", project), \
                patch.object(probe_phone, "call", side_effect=request) as calls, \
                patch.object(probe_phone, "owners", side_effect=owners), \
                patch.object(probe_phone.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(probe_phone.time, "sleep", side_effect=advance) as sleep, \
                redirect_stdout(output):
            code = probe_phone.probe(5)
        report_text = (project / "evidence/native-phone-live.json").read_text()
        report = json.loads(report_text)
        assert "SYNTHETIC_PRIVATE_PAIRING_CODE" not in report_text + output.getvalue()
        assert all(item.args[1] in {"status", "thread/read", "remoteControl/status/read"}
                   for item in calls.call_args_list)
        return code, report, calls, sleep


def main():
    code, report, calls, sleep = scenario("same-turn")
    assert code == 0 and report["completed"]
    assert report["sameChild"] and report["initialWriterPids"] == report["finalWriterPids"] == [101]
    assert report["activeObserved"] and report["phoneTaskApplied"] and report["phoneSteerApplied"]
    assert report["newTurnCount"] == 1 and report["steeringInSameTurn"]
    assert report["remoteStatus"] == "connected"
    sleep.assert_called_once_with(1)
    print("PASS same-child completed turn with two user messages and both fresh markers")

    code, report, calls, sleep = scenario("changed-writer")
    assert code == 1 and not report["completed"]
    assert report["failedStage"] == "phone-task-and-steer" and report["failureType"] == "AssertionError"
    assert [item.args[1] for item in calls.call_args_list] == [
        "status", "thread/read", "remoteControl/status/read", "status",
    ]
    sleep.assert_not_called()
    print("PASS changed writer is rejected immediately; observer sends only read methods")

    code, report, calls, sleep = scenario("queue")
    assert code == 1 and not report["completed"]
    assert report["phoneTaskApplied"] and report["phoneSteerApplied"]
    assert report["newTurnCount"] == 2 and report["steeringInSameTurn"] is False
    assert report["failedStage"] == "final-read" and report["failureType"] == "AssertionError"
    print("PASS markers split across two queued turns do not prove same-turn steering")

    assert not probe_phone.includes_phone_steer({"items": [{"type": "userMessage", "content": [
        {"type": "text", "text": "Create PHONE_NATIVE_OK and PHONE_STEER_OK"},
    ]}]})
    print("PASS a single user message containing both markers does not count as steering")


if __name__ == "__main__":
    main()
