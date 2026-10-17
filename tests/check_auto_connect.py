#!/usr/bin/env python3
"""Offline automatic connection checks with real private pairing records."""

import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import remote_backend as remote


def scenario(initial="disabled", clients=True, saved=True, pending=False, other=False):
    temp = tempfile.TemporaryDirectory(prefix="codex-auto-check-")
    root = Path(temp.name)
    socket = root / "runs/current/control.sock"
    socket.parent.mkdir(parents=True)
    (socket.parent / "process.json").write_text(json.dumps({"childPid": 101}))
    record = root / "phone-pairing.json"
    if saved:
        record.write_text(json.dumps({"installationId": "installation-a", "environmentId": "environment-a", "paired": True}))
    if pending:
        folder = socket.parent / "pairing"
        folder.mkdir()
        (folder / "state.json").write_text(json.dumps({"childPid": 101, "pairing": {
            "pairingCode": "SYNTHETIC_PRIVATE_CODE", "expiresAt": 9999999999}}))
    state = {"status": initial, "installationId": "installation-a"}
    calls = []

    def call(path, method, params=None):
        calls.append((str(path), method, params))
        if method == "status":
            return {"result": {"initialized": True, "childPid": 101}}
        if method == "remoteControl/status/read":
            return {"result": {**state, "environmentId": "environment-a" if state["status"] == "connected" else None}}
        if method == "remoteControl/client/list":
            assert params == {"environmentId": "environment-a", "limit": 1}
            return {"result": {"data": [{"clientId": "SYNTHETIC_CLIENT_SECRET"}] if clients else [], "nextCursor": None}}
        if method == "remoteControl/enable":
            assert params == {"ephemeral": True}
            state["status"] = "connected"
            return {"result": dict(state)}
        raise AssertionError(f"Unexpected Remote operation: {method}")

    def wait(path, desired, seconds):
        assert str(path) == str(socket) and desired == "connected"
        return {**state, "environmentId": "environment-a"}

    target = {"socket": str(socket), "childPid": 101}

    def run(action="auto-connect"):
        with patch.object(remote, "PROJECT", root), patch.object(remote, "call", side_effect=call), \
                patch.object(remote, "wait_remote_status", side_effect=wait), \
                patch.object(remote, "check_other_connections", side_effect=remote.UserError("Another backend connected") if other else None):
            return remote.operate(action, target)

    return temp, root, record, state, calls, run


def main():
    temp, root, record, state, calls, run = scenario()
    with temp:
        report = run()
        assert report["status"] == "connected", "A previously paired phone must automatically start Remote"
        assert report["paired"] is True
        assert [m for _, m, _ in calls].count("remoteControl/enable") == 1
        assert json.loads(record.read_text())["paired"] is True
        assert record.stat().st_mode & 0o777 == 0o600
        assert "SYNTHETIC_" not in json.dumps(report) + record.read_text()
        calls.clear()
        run()
        assert not any(m == "remoteControl/enable" for _, m, _ in calls), "An existing connection must be reused"
    print("PASS saved pairing: authorized phone reconnects, private record omits codes/client IDs, connected backend reused")

    for saved, clients in ((False, False), (True, False)):
        temp, _, record, _, calls, run = scenario(saved=saved, clients=clients)
        with temp:
            report = run()
            assert report["paired"] is False and report["status"] == "disabled"
            assert not any(m == "remoteControl/enable" for _, m, _ in calls)
            if record.exists():
                assert json.loads(record.read_text())["paired"] is False, "Revocation must invalidate the recorded authorization"
    print("PASS no phone: missing or revoked authorization never starts Remote")

    temp, _, record, _, calls, run = scenario(initial="connected", saved=False)
    with temp:
        assert run()["paired"] is True
        assert json.loads(record.read_text()) == {"installationId": "installation-a", "environmentId": "environment-a", "paired": True}
        assert not any(m == "remoteControl/enable" for _, m, _ in calls)
    temp, _, _, state, calls, run = scenario()
    with temp:
        state["installationId"] = "installation-b"
        assert run()["paired"] is False
        assert not any(m in ("remoteControl/client/list", "remoteControl/enable") for _, m, _ in calls)
    print("PASS upgrade/identity: existing authorized connection is remembered; another installation cannot reuse the record")

    temp, _, record, state, calls, run = scenario(saved=False)
    with temp:
        assert run("connect")["status"] == "connected"
        assert json.loads(record.read_text())["paired"] is False, "Manual startup alone does not prove a phone was paired"
        state["status"] = "disabled"
        calls.clear()
        assert run()["paired"] is True
        assert any(m == "remoteControl/client/list" for _, m, _ in calls)
        assert [m for _, m, _ in calls].count("remoteControl/enable") == 1
    print("PASS migration: manual startup remembers the environment; later automatic startup verifies actual authorization")

    temp, _, record, _, _, run = scenario(initial="connected", clients=False, saved=False, pending=True)
    with temp:
        report = run()
        assert report["paired"] is False and report["pairingPending"] is True
        assert json.loads(record.read_text())["paired"] is False
    temp, _, _, _, calls, run = scenario(other=True)
    with temp:
        try:
            run()
        except remote.UserError:
            pass
        else:
            raise AssertionError("Another connected backend must block automatic switching")
        assert not any(m == "remoteControl/enable" for _, m, _ in calls)
    print("PASS pairing/ownership: an unclaimed code is not authorization; another owner blocks auto-start")


if __name__ == "__main__":
    main()
