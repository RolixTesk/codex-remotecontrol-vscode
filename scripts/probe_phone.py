#!/usr/bin/env python3
"""Observe one phone-originated task and steer on the paired VS Code-owned thread."""

import argparse
import json
from pathlib import Path
import time

from probe_live import PROJECT, call, owners, result
from protocol import same_directory


def includes_phone_steer(turn):
    messages = [json.dumps(item, ensure_ascii=False) for item in turn["items"]
                if item.get("type") == "userMessage"]
    return any("PHONE_NATIVE_OK" in first and any("PHONE_STEER_OK" in later
               for later in messages[index + 1:]) for index, first in enumerate(messages))


def probe(wait_seconds):
    config = json.loads((PROJECT / "wrapper/codex-wrapper.local.json").read_text())
    root, cwd = Path(config["captureRoot"]), Path(config["captureCwd"])
    anchor = json.loads((root.parent / "pairing/state.json").read_text())
    path, pid, thread_id = anchor["socket"], anchor["childPid"], anchor["threadId"]
    report_file = PROJECT / "evidence/native-phone-live.json"
    report = {"completed": False, "childPid": pid, "activeObserved": False,
              "phoneTaskApplied": False, "phoneSteerApplied": False}
    markers = {"phone-native.txt": "PHONE_NATIVE_OK", "phone-steer.txt": "PHONE_STEER_OK"}
    before = {name: (cwd / name).stat().st_mtime_ns if (cwd / name).exists() else 0 for name in markers}
    stage = "initial-read"

    def save():
        report_file.write_text(json.dumps(report, indent=2) + "\n")

    try:
        state = result(call(path, "status"))
        assert state["childPid"] == pid and thread_id in state["threads"] and owners(thread_id) == [pid]
        assert thread_id not in state["activeTurns"]
        thread = result(call(path, "thread/read", {"threadId": thread_id, "includeTurns": True}))["thread"]
        assert same_directory(thread["cwd"], cwd) and thread.get("ephemeral") is not True
        initial_turns = {t["id"] for t in thread["turns"]}
        report["initialWriterPids"] = [pid]
        report["initialTurnCount"] = len(initial_turns)
        assert result(call(path, "remoteControl/status/read"))["status"] == "connected"
        save()
        print("READY observing paired phone test; no turn/start, resume or steer is injected", flush=True)
        deadline = time.monotonic() + wait_seconds
        stage = "phone-task-and-steer"
        while time.monotonic() < deadline:
            state = result(call(path, "status"))
            assert state["childPid"] == pid and owners(thread_id) == [pid]
            if thread_id in state["activeTurns"]:
                report["activeObserved"] = True
            applied = {}
            for name, value in markers.items():
                marker = cwd / name
                applied[name] = (marker.exists() and marker.stat().st_mtime_ns > before[name]
                                 and marker.read_text().strip() == value)
            report.update(phoneTaskApplied=applied["phone-native.txt"], phoneSteerApplied=applied["phone-steer.txt"])
            save()
            if all(applied.values()) and thread_id not in state["activeTurns"]:
                break
            time.sleep(1)
        else:
            raise TimeoutError("Phone task or steering marker was not observed")
        stage = "final-read"
        thread = result(call(path, "thread/read", {"threadId": thread_id, "includeTurns": True}))["thread"]
        new_turns = [t for t in thread["turns"] if t["id"] not in initial_turns]
        report["newTurnCount"] = len(new_turns)
        report["steeringInSameTurn"] = any(includes_phone_steer(turn) for turn in new_turns)
        assert new_turns and report["steeringInSameTurn"]
        assert all(t["status"] == "completed" for t in new_turns)
        assert result(call(path, "status"))["childPid"] == pid and owners(thread_id) == [pid]
        report.update(finalWriterPids=[pid], remoteStatus=result(call(path, "remoteControl/status/read"))["status"],
                      sameChild=True, completed=True)
        save()
        print("PASS phone task and active-turn steering on the unchanged unique writer", flush=True)
        return 0
    except Exception as exc:
        report.update(failedStage=stage, failureType=type(exc).__name__)
        save()
        print(f"Phone probe stopped at {stage} ({type(exc).__name__}); no automatic write retry", flush=True)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait", type=int, default=600)
    raise SystemExit(probe(parser.parse_args().wait))
