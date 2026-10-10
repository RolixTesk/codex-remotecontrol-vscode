# Same live app-server milestone — 2026-10-05

The central local hypothesis is proved for Windows VS Code host + WSL bundled Codex 0.160.0.

- Official extension starts through the wrapper, creates/reads/writes/streams normally and survives window close/reopen (user-confirmed parity).
- Real JSONL traffic provides thread/turn IDs; redacted fixtures and parser checks are recorded.
- Bridge thread/read and exactly one harmless turn/steer were routed through the existing stdio connection. No bridge thread/resume or turn/start was sent.
- Wrapper PID 31325 and app-server PID 31334 remained the same; the selected thread's unique actual advisory writer lock owner was PID 31334 before/after steering.
- Steering response matched expectedTurnId. The original task completed with exit0, then Codex created bridge-steer.txt with STEER_OK. User confirmed receipt/execution in the same VS Code chat.
- Native Remote status/read and ephemeral enable/disable were accepted by the same process. enable returned connecting. disable returned disabled; immediate status read briefly remained connecting, but final audit confirmed disabled.
- A separate bounded registration observation reached connected in 4.09 seconds with a nonempty environmentId. PID 31334 and its unique writer remained unchanged; Remote was again restored to disabled. See native-remote-registration.json.

## Native phone: Windows host + WSL Codex

Native phone writes and active steering are proved. Two distinct phone user inputs belong to one new completed turn; the second input reached app-server 52607 before the running sleep command completed. Both phone marker files are correct, and the actual unique writer is 52607 before/after. User confirmed Steer mode. See native-phone-live-result.json and native-phone-input-audit.json.

The bounded phone observer expired before the human action; native-phone-timeout.json retains that failure. The result comes from the same app-server's continuing stdio capture and post-test writer audit, without claiming a live lock sample during that command. One initial python command failed with exit127; python3 succeeded with exit0 and both output markers.

Phone interruption is proved by native-phone-interrupt.json: a read-only observer saw the active turn become interrupted, with the original process and unique writer PID 52607 preserved throughout observation. The user confirmed phone Stop succeeded before the final command output, and VS Code showed the phone messages and normal stopped state.

Real phone approval is proved by native-phone-approval.json: the original item/commandExecution/requestApproval was followed by exactly one matching serverRequest/resolved, the test file contains PHONE_APPROVAL_OK, and the turn completed on unchanged app-server/writer PID 52607. No approval response passed through VS Code stdin; the phone decision returned over the native channel. The user confirmed the phone approval card, successful write and consistent VS Code result. This establishes the observed request/resolution and absence of duplicate stdio replies; it does not capture the internal native decision payload.

## Remote-WSL acceptance

The same official extension version is installed on WSL with Codex 0.160.0 and
VS Code Server 1.140.0. A separate wsl-baseline workspace avoids resuming the
Windows-host chat through another writer. See wsl-preparation.json.

The Remote-WSL UI-created baseline chat exists with source=vscode and sole writer
PID 79931. Its parent is a Linux VS Code Extension Host, PID 79883. The app-server
inherits the VS Code installation cwd, whereas the thread uses wsl-baseline; this
explains why the original process-cwd guard chose exec passthrough. A minimal
optional launchCwd now selects the process for capture while captureCwd continues
to bound controllable threads. The original argv and cwd are preserved. This
bounded test loaded the change through a normal window reload. Launch-directory matching is
not a general per-window selector: other Remote-WSL windows with that same launch
cwd could also be captured, so this test configuration was temporary and has been
restored. See wsl-launch-topology.json and wsl-scope-validation.json.

Remote-WSL reload recovery is verified by wsl-wrapper-recovery.json: the same UI
thread reopened on wrapper 87836 / official app-server 87840 after old writer
79931 exited, with sole writer 87840 and the original process cwd preserved.
Native Remote on this exact WSL-owned server reached connected and the phone
claimed the pairing. The original writer remained 87840; see
native-remote-pairing-wsl.json.

The protocol records phone command approval, file writes, a subsequent turn and
turn interruption on the same writer. One original approval request has one
matching resolution, with no approval reply on VS Code stdin. Both expected file
markers are correct. See native-phone-wsl-result.json.

On 2026-10-05 the user additionally confirmed manual validation and explicitly
accepted Phase H without its earlier scope restriction. Remote-WSL active-turn
steering and interruption while a command runs are accepted from that manual
confirmation. The user also confirmed Phase J daily-project use succeeded.
See manual-acceptance.json. No tasks were repeated by the agent.

Earlier observer/capture reports retain their original observations, including
the incomplete combined observer; the later manual acceptance is recorded
separately rather than rewriting those reports.

## Experiment closeout before daily entry

The built-in authenticated route reuses the official extension's original writer;
MCP is unnecessary for this verified route under agent.md §7. No helper extension,
public endpoint, daemon or second thread writer was introduced.

At experiment closeout, both disposable processes' ephemeral Remote switches
were disabled, while their chats and writers remained intact. The wrapper configuration was restored byte for
byte from its pre-WSL backup, removing launchCwd and returning capture scope to
baseline. See native-remote-windows-cleanup.json and native-remote-wsl-cleanup.json.
The already-running WSL test wrapper ends when that window closes. Raw captures
and pairing credentials remain in private Linux state outside the project.

## Current delivery

The daily CLI subsequently added workspace/owner selection, connect, pairing,
status and disconnect; bridge mode does not record raw streams or argv. Its
installation and live connection are recorded in daily-entry.json. The user
accepted actual daily-project use in manual-acceptance.json.

Windows-native execution is unsupported by this Linux Python/Unix-socket wrapper.
Automatic reconnection and cross-version compatibility are not implemented.

## Validation

See wrapper-validation.md, protocol-observation.md, control-validation.md and live-probe.json. Stub tests establish the wrapper's own routing behavior; real captures, writer-lock checks, test file and user UI confirmation establish this live-session result. Scope selection was corrected using ephemeral/writer checks and actual directory identity on Windows mounts.
