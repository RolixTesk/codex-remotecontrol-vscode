#!/usr/bin/env python3
"""Offline checks for bounded Remote status waits using mocked replies and time."""

from pathlib import Path
import sys
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import control_client


def main():
    for desired, states in [("disabled", ["connecting", "disabled"]),
                            ("connected", ["connecting", "connected"]),
                            ("disabled", ["errored", "disabled"])]:
        replies = [{"result": {"status": state}} for state in states]
        with patch.object(control_client, "call", side_effect=replies) as request, \
                patch.object(control_client.time, "monotonic", return_value=10), \
                patch.object(control_client.time, "sleep") as sleep:
            assert control_client.wait_remote_status("synthetic.sock", desired, 5) == {"status": desired}
            assert request.call_args_list == [call("synthetic.sock", "remoteControl/status/read")] * 2
            sleep.assert_called_once_with(.2)

    with patch.object(control_client, "call", return_value={"result": {"status": "errored"}}), \
            patch.object(control_client.time, "monotonic", return_value=10), \
            patch.object(control_client.time, "sleep") as sleep:
        try:
            control_client.wait_remote_status("synthetic.sock", "connected", 5)
        except RuntimeError:
            pass
        else:
            raise AssertionError("errored connection was not rejected")
        sleep.assert_not_called()

    with patch.object(control_client, "call", return_value={"result": {"status": "connecting"}}), \
            patch.object(control_client.time, "monotonic", side_effect=[10, 12]), \
            patch.object(control_client.time, "sleep") as sleep:
        try:
            control_client.wait_remote_status("synthetic.sock", "disabled", 1)
        except TimeoutError:
            pass
        else:
            raise AssertionError("unsettled Remote state did not time out")
        sleep.assert_not_called()
    print("PASS mocked Remote transitions to disabled/connected, errored connection, bounded timeout")


if __name__ == "__main__":
    main()
