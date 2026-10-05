#!/usr/bin/env python3
"""Check local pairing artifacts and calls offline, without real processes or secrets."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pair_remote


def main():
    with tempfile.TemporaryDirectory(prefix="codex-pair-remote-check-") as temp:
        root = Path(temp)
        project, private = root / "project", root / "private"
        (project / "wrapper").mkdir(parents=True)
        (project / "evidence").mkdir()
        captures, workspace = private / "captures", root / "workspace"
        captures.mkdir(parents=True)
        workspace.mkdir()
        (project / "wrapper/codex-wrapper.local.json").write_text(json.dumps({
            "captureRoot": str(captures), "captureCwd": str(workspace),
        }))
        anchor = {"socket": str(captures / "run" / "control.sock"),
                  "childPid": 101, "threadId": "synthetic-thread"}
        secrets = ["SYNTHETIC_PAIRING_SECRET", "SYNTHETIC_MANUAL_SECRET", "SYNTHETIC_HOST_SECRET"]
        remote = {"status": "connected", "serverName": secrets[2], "environmentId": "synthetic-environment"}
        pairing = {"pairingCode": secrets[0], "manualPairingCode": secrets[1], "expiresAt": 123456}

        def run(action, fail_pairing=False, writer=101):
            def request(path, method, params=None):
                assert path == anchor["socket"]
                if method == "status":
                    return {"result": {"childPid": anchor["childPid"]}}
                if method == "thread/read":
                    assert params == {"threadId": anchor["threadId"], "includeTurns": False}
                    return {"result": {"thread": {"id": anchor["threadId"], "cwd": str(workspace), "ephemeral": False}}}
                if method == "remoteControl/status/read":
                    return {"result": {"status": "connected" if action == "status" else "disabled"}}
                if method in ("remoteControl/enable", "remoteControl/disable"):
                    assert params == {"ephemeral": True}
                    return {"result": {"status": "connecting" if method.endswith("enable") else "disabled"}}
                if method == "remoteControl/pairing/start":
                    assert params == {"manualCode": True}
                    if fail_pairing:
                        raise RuntimeError(secrets[0])
                    return {"result": dict(pairing)}
                if method == "remoteControl/pairing/status":
                    assert params == {"pairingCode": secrets[0]}
                    return {"result": {"claimed": True}}
                raise AssertionError(f"unexpected method {method}")

            output = io.StringIO()
            with patch.object(pair_remote, "PROJECT", project), \
                    patch.object(pair_remote, "locate", return_value=dict(anchor)) as locate, \
                    patch.object(pair_remote, "call", side_effect=request) as calls, \
                    patch.object(pair_remote, "owners", side_effect=lambda thread: [writer]
                                 if thread == anchor["threadId"] else []) as owners, \
                    patch.object(pair_remote, "wait_remote_status", side_effect=lambda path, desired, seconds:
                                 dict(remote) if desired == "connected" else {"status": "disabled"}) as wait, \
                    redirect_stdout(output):
                code = pair_remote.main(action)
            report = json.loads((project / "evidence/native-remote-pairing.json").read_text())
            assert json.loads(output.getvalue()) == report
            assert all(secret not in output.getvalue() for secret in secrets), "credential reached stdout"
            for file in project.rglob("*"):
                if file.is_file():
                    assert all(secret not in file.read_text() for secret in secrets), "credential reached project file"
            return code, report, calls, locate, owners, wait

        code, report, calls, locate, owners, wait = run("start")
        assert code == 0 and report["completed"] and report["sameChild"] and report["writerPids"] == [101]
        assert calls.call_args_list == [
            call(anchor["socket"], "status"),
            call(anchor["socket"], "thread/read", {"threadId": anchor["threadId"], "includeTurns": False}),
            call(anchor["socket"], "remoteControl/status/read"),
            call(anchor["socket"], "remoteControl/enable", {"ephemeral": True}),
            call(anchor["socket"], "remoteControl/pairing/start", {"manualCode": True}),
            call(anchor["socket"], "status"),
        ]
        locate.assert_called_once_with(captures, workspace)
        wait.assert_called_once_with(anchor["socket"], "connected", 45)
        folder = private / "pairing"
        assert folder.stat().st_mode & 0o777 == 0o700
        for name in ("state.json", "pairing.svg", "pairing.html"):
            assert (folder / name).stat().st_mode & 0o777 == 0o600
        state = json.loads((folder / "state.json").read_text())
        assert state == dict(anchor, remote=remote, pairing=pairing)
        assert "svg" in (folder / "pairing.svg").read_text()
        assert secrets[1] in (folder / "pairing.html").read_text()
        print("PASS start only enables/pairs existing child; offline artifacts private; stdout/project contain no credentials")

        code, report, calls, locate, owners, wait = run("status")
        assert code == 0 and report["claimed"] and report["childPid"] == state["childPid"]
        locate.assert_not_called()
        wait.assert_not_called()
        assert calls.call_args_list == [
            call(state["socket"], "status"),
            call(state["socket"], "thread/read", {"threadId": state["threadId"], "includeTurns": False}),
            call(state["socket"], "remoteControl/status/read"),
            call(state["socket"], "remoteControl/pairing/status", {"pairingCode": state["pairing"]["pairingCode"]}),
            call(state["socket"], "status"),
        ]
        assert all(args == call(state["threadId"]) for args in owners.call_args_list)
        print("PASS status reuses saved socket/PID/thread/pairing code without enable or rediscovery")

        code, report, calls, _, _, wait = run("start", fail_pairing=True)
        assert code == 1 and not report["completed"] and report["restoredDisabled"]
        assert [args.args[1] for args in calls.call_args_list][-2:] == ["remoteControl/pairing/start", "remoteControl/disable"]
        assert wait.call_args_list == [call(anchor["socket"], "connected", 45), call(anchor["socket"], "disabled", 5)]
        print("PASS failure after enabling restores disabled without leaking failure credentials")

        code, report, calls, _, _, wait = run("start", writer=202)
        assert code == 1 and not report["completed"]
        assert calls.call_args_list == [call(anchor["socket"], "status")]
        wait.assert_not_called()
        print("PASS changed writer is rejected before Remote enable/pairing")


if __name__ == "__main__":
    main()
