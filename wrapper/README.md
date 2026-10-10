# Transparent wrapper

## Daily connection mode

Use `mode: "bridge"` for daily use. It preserves the original executable, arguments,
environment and cwd, intercepts app-server stdio, and creates a private control socket
without recording stdin/stdout or argv. Non-app-server invocations directly exec the
real executable. Only non-ephemeral threads loaded by VS Code are eligible; the CLI
selects their actual workspace and verifies the original sole writer.

```json
{
  "mode": "bridge",
  "realExecutable": "/absolute/path/to/bundled/codex",
  "captureRoot": "/home/user/.local/state/codex-remotecontrol/captures"
}
```

`captureRoot` is also the socket/metadata directory in daily mode. `captureCwd`,
`launchCwd` and `control` are experiment options; bridge mode does not need them.
The current Linux wrapper path is already configured in VS Code User Settings as
`chatgpt.cliExecutable`. Reload the intended idle window, then open its Codex chat.

Run from a WSL project terminal (`python3 /path/to/scripts/remote.py` also works):

```sh
codex-remote list                       # all loaded project chats and their owner PIDs
codex-remote connect                    # current directory's owner, ephemeral Remote
codex-remote pair --open                # new device: private manual-code page
codex-remote status
codex-remote disconnect                 # leaves the chat/app-server running
codex-remote connect --workspace /path/to/project --pid 12345
```

Install the short command once by linking the executable `scripts/remote.py` into
`~/.local/bin/codex-remote` (already installed in this environment). With optional
offline SVG QR generation, use:

```sh
uv run --no-project --with qrcode==8.2 python scripts/remote.py pair --open --workspace /path/to/project
```

Pairing produces `pairing.html`, optional `pairing.svg`, and `state.json` in that
owner's private run directory (0700, files 0600). Credentials never appear in CLI
output or project reports. Without qrcode the page still supports manual pairing.
`--open` opens the local page via the Windows default browser in WSL.

Remote is an app-server-wide switch. Project selection is not a phone-side access
filter. Multiple owners for one project require `--pid`; the CLI refuses to enable
another visible owner while one is connecting/connected. It does not automatically
disable another window, resume a thread, send approvals, or reconnect after reload.
Unknown write outcomes are reported without replaying the request. A failed setup
restores disabled state only when it enabled that connection itself.

The configured bundled binary path is version-specific: update `realExecutable`
when the official extension changes its install directory. Windows-host + WSL
Codex and Remote-WSL are supported; Windows-native execution is not.

## Scoped experiment mode

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

With no `mode: "bridge"`, set `control: true` for a disposable experiment. A Unix socket named
`control.sock` is created in each private capture directory (socket mode 0600,
directory 0700). It accepts one JSONL request per connection and uses the same
child process and stdio; it does not launch another app-server. The local `status`
method reports initialized state, loaded disposable threads and observed active turns.

Remote-WSL starts the app-server with the Extension Host's cwd, which may differ
from the workspace. In that bounded test configuration, set `launchCwd` to the
observed process cwd and keep `captureCwd` as the target chat's workspace. The
wrapper preserves the original process cwd; its control socket admits only
threads whose cwd matches `captureCwd`. Launch-cwd matching can also capture other
windows started from that same directory, so use this configuration only while
the disposable WSL window is the sole Remote-WSL window and restore it afterward.

Upstream calls are limited to `thread/read`, `turn/steer`, Remote status /
ephemeral enable / ephemeral disable, and pairing start / status. Pairing start
requires `manualCode: true`; pairing status takes the issued `pairingCode`.
Steering requires an observed active turn
and `expectedTurnId`. Thread creation/resume and approval answers are not exposed.
The local control socket never answers server approval requests. Original requests
continue to VS Code; native Remote can resolve them through the same app-server.
Bridge response IDs
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
then was restored to `disabled`. Subsequent phone tests proved task creation, active
steering, interruption and approval on the original writer, with matching VS Code UI.
The results are in `evidence/native-phone-live-result.json`,
`evidence/native-phone-interrupt.json` and `evidence/native-phone-approval.json`.
For a loaded disposable chat, run:

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
Start selects the successful steering thread recorded in the private live-probe
`activeRead` response. Other restored disposable chats may remain loaded in the
same app-server; each selected thread must still have that process as its sole writer.
For a fresh UI-created disposable chat, `start --thread-id <observed-id>` selects
that exact thread with the same cwd and writer checks. It never acquires a writer
for a chat held by another window.

After phone pairing, `python3 scripts/probe_phone.py --wait 900` observes one phone
task and active follow-up on the saved pairing thread. It sends only status and
read requests, verifies unchanged writer ownership, and checks fresh
`phone-native.txt` / `phone-steer.txt` markers. Successful steering requires two
ordered user messages in one new completed turn; two queued turns do not count.

Windows-host/WSL execution and Remote-WSL compatibility are verified. The user
completed additional manual validation of active steering and interruption during
a running command, and confirmed daily-project use succeeded. Phase H and J are
accepted in `evidence/manual-acceptance.json`. Earlier observer reports are retained
as historical records.

This Python wrapper uses Linux signals and a Unix socket; Windows-native execution
is unsupported. Phone approval uses built-in Remote; no custom approval relay,
helper extension or MCP is needed for the verified route. Outside the matched
launch directory, the wrapper only execs the real binary. The temporary Remote-WSL
configuration and both ephemeral Remote switches were restored after the experiment.
Daily bridge mode is the later follow-up above; existing observation-mode wrappers
exit when their windows reload/close.
