# Transparent wrapper

`codex-wrapper` uses Python 3's standard library. Observation mode launches the configured real
Codex with the original arguments, environment, cwd and stderr. In the disposable
workspace it copies stdin/stdout bytes and saves a separate capture of each stream.
Outside that workspace, and for commands such as `--version`, it directly execs
the real binary. It does not parse frames, inject requests or open an endpoint.

Local paths and the optional experiment switch are in `codex-wrapper.local.json` beside the executable:

```json
{
  "realExecutable": "/absolute/path/to/bundled/codex",
  "captureCwd": "/absolute/path/to/experiments/baseline",
  "captureRoot": "/home/user/.local/state/codex-remotecontrol/captures",
  "control": false
}
```

Raw captures may contain authentication traffic. They stay outside the project,
in a Linux directory created with mode 0700; stream files use 0600. Do not attach
or commit raw captures. Protocol redaction follows actual VS Code parity testing.

For the current Windows-host/WSL configuration, `chatgpt.cliExecutable` must point
to the wrapper's Linux path. It is an application setting; configure it in User
Settings rather than assuming workspace scope. The baseline original value was
unset. Delete this one setting and reload the window to restore bundled execution.

Set `control: true` for the next disposable experiment. A Unix socket named
`control.sock` is created in each private capture directory (socket mode 0600,
directory 0700). It accepts one JSONL request per connection and uses the same
child process and stdio; it does not launch another app-server. The local `status`
method reports initialized state, loaded disposable threads and observed active turns.

Upstream calls are limited to `thread/read`, `turn/steer`, Remote status /
ephemeral enable / ephemeral disable, and pairing start / status. Pairing start
requires `manualCode: true`; pairing status takes the issued `pairingCode`.
Steering requires an observed active turn
and `expectedTurnId`. Thread creation/resume and approval answers are not exposed.
Server requests and their replies remain owned by VS Code. Bridge response IDs
are consumed locally, including late replies after a controller timeout; uncertain
requests are not automatically retried.

Control mode forwards complete original JSONL frames, serializing input writes
to prevent a bridge request from splitting a VS Code frame. The raw captures now
contain the combined app-server input and all app-server output, including bridge
responses. VS Code receives all traffic except responses to bridge-owned IDs.

`scripts/probe_live.py --wait 900` is a bounded one-shot experiment: read the loaded
thread and verify its writer, wait for a UI-started turn, steer it to create a
disposable marker, then test ephemeral Remote and restore disabled state. It writes
only a sanitized project report; full replies remain in the private state directory.
It never resumes a thread or sends `turn/start`. Observe its result before repeating
a write request. A positive RPC response alone is not proof of visible UI behavior.

The same app-server's native Remote reached `connected` and registered an environment,
then was restored to `disabled`. Phone routing to its existing writer still needs verification.
After reloading the disposable window and reopening its existing chat, run:

```sh
uv run --no-project --with qrcode==8.2 python scripts/pair_remote.py start
python3 scripts/pair_remote.py status
python3 scripts/pair_remote.py disable
```

The start action leaves ephemeral Remote enabled while the phone pairs. It writes
`pairing.html`, `pairing.svg`, and `state.json` with mode 0600 in the private Linux
state directory beside `captures/`, and emits only a sanitized report. `qrcode` is
used only for the offline SVG artifact. No HTTP listener or extra app-server is started.
If setup fails after enable, the script restores `disabled`. Status and disable
stay anchored to the exact original PID/thread. Do not attach pairing artifacts.

Only Windows-host/WSL execution is implemented. Windows-native / Remote-WSL parity,
mobile pairing, a helper extension, approval relay and MCP remain unverified or unimplemented.
