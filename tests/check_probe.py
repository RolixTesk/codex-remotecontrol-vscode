#!/usr/bin/env python3
"""Check active writer selection with synthetic IDs and mocked ownership only."""

from pathlib import Path
import sys
import tempfile
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import probe_live
from protocol import same_directory


def main():
    status = {"childPid": 101, "activeTurns": {
        "helper-thread": "helper-turn", "real-thread": "real-turn",
    }}
    with patch.object(probe_live, "owners", side_effect=lambda thread: {
        "helper-thread": [], "real-thread": [101],
    }[thread]) as owners:
        assert probe_live.active_writer_turn(status) == ("real-thread", "real-turn")
        assert owners.call_args_list == [call("helper-thread"), call("real-thread")]

    with patch.object(probe_live, "owners", return_value=[]):
        assert probe_live.active_writer_turn({"childPid": 101, "activeTurns": {
            "helper-thread": "helper-turn",
        }}) is None

    with patch.object(probe_live, "owners", return_value=[202]):
        assert probe_live.active_writer_turn({"childPid": 101, "activeTurns": {
            "other-thread": "other-turn",
        }}) is None

    with patch.object(probe_live, "owners") as owners:
        assert probe_live.active_writer_turn({"childPid": 101, "activeTurns": {}}) is None
        owners.assert_not_called()
    print("PASS helper-first selection chooses the sole same-child writer; helper/other writer/empty are rejected")

    with tempfile.TemporaryDirectory(prefix="codex-directory-check-") as temp:
        root = Path(temp)
        directory = root / "Workspace"
        directory.mkdir()
        alias = root / "workspace-alias"
        alias.symlink_to(directory, target_is_directory=True)
        other = root / "workspace"
        other.mkdir()
        missing = root / "missing"
        assert same_directory(directory, alias) and same_directory(alias, directory)
        assert not same_directory(directory, other), "case folding joined different directories"
        for first, second in [(missing, directory), (directory, missing),
                              (None, directory), (directory, None), (None, None)]:
            assert not same_directory(first, second)
    print("PASS directory aliases share identity; case-different inodes/missing/None remain outside scope")

    for desired, states in [("disabled", ["connecting", "disabled"]),
                            ("connected", ["connecting", "connected"]),
                            ("disabled", ["errored", "disabled"])]:
        replies = [{"result": {"status": state}} for state in states]
        with patch.object(probe_live, "call", side_effect=replies) as request, \
                patch.object(probe_live.time, "monotonic", return_value=10), \
                patch.object(probe_live.time, "sleep") as sleep:
            assert probe_live.wait_remote_status("synthetic.sock", desired, 5) == {"status": desired}
            assert request.call_args_list == [call("synthetic.sock", "remoteControl/status/read")] * 2
            sleep.assert_called_once_with(.2)

    with patch.object(probe_live, "call", return_value={"result": {"status": "errored"}}), \
            patch.object(probe_live.time, "monotonic", return_value=10), \
            patch.object(probe_live.time, "sleep") as sleep:
        try:
            probe_live.wait_remote_status("synthetic.sock", "connected", 5)
        except RuntimeError:
            pass
        else:
            raise AssertionError("errored connection was not rejected")
        sleep.assert_not_called()

    with patch.object(probe_live, "call", return_value={"result": {"status": "connecting"}}), \
            patch.object(probe_live.time, "monotonic", side_effect=[10, 12]), \
            patch.object(probe_live.time, "sleep") as sleep:
        try:
            probe_live.wait_remote_status("synthetic.sock", "disabled", 1)
        except TimeoutError:
            pass
        else:
            raise AssertionError("unsettled Remote state did not time out")
        sleep.assert_not_called()
    print("PASS mocked Remote transitions to disabled/connected, errored connection, bounded timeout")


if __name__ == "__main__":
    main()
