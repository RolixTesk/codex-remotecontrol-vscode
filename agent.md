# AGENT.md — VS Code Codex Live Session Remote Bridge

> Handoff date: 2026-10-05
> Owner environment: Windows 11 + VS Code + WSL2
> Primary objective: allow the user to start a Codex task in the official VS Code Codex extension, leave the computer, and later use ChatGPT on a phone to inspect, steer, continue, interrupt, and approve actions in the **same live Codex conversation/session**, without creating a second independent agent or losing the original execution state.

## 1. Operating principle

Do **not** over-engineer this project. Prefer the smallest experiment that can prove or disprove the central hypothesis. Avoid unrelated refactors, frameworks, databases, dashboards, public services, or architectural abstractions until the live-session bridge itself is proven.

The first milestone is not “build a polished ChatGPT plugin.” The first milestone is:

> Prove that the Codex process started by the official VS Code extension can be observed and controlled through a bridge while VS Code remains attached, without creating another persistent writer for the same thread.

If this cannot be achieved safely, stop and document the blocker before building a remote UI.

## 2. User requirement

The user explicitly rejects these substitutes:

- Remote desktop / RustDesk / RDP.
- Codex CLI + tmux as the primary workflow.
- Starting an independent Codex Companion session that merely edits the same project.
- Closing VS Code so that mobile Remote can take over an inactive thread.
- Creating a second app-server that independently resumes the same thread.
- “Read-only status viewer” without the ability to steer/continue/approve.

Required behavior:

```text
Desktop VS Code
  -> official Codex extension
  -> live thread T / active turn U
  -> Codex is executing work

User leaves desktop

Phone ChatGPT
  -> custom ChatGPT plugin / MCP tool
  -> local bridge
  -> SAME live app-server / SAME thread T
  -> inspect current state
  -> send follow-up / steer active turn
  -> start next turn after completion
  -> interrupt if requested
  -> handle approval requests if technically possible

User returns to desktop

VS Code still shows the same conversation and state.
```

## 3. Current technical facts

### 3.1 Codex App Server exposes relevant protocol methods

The current OpenAI Codex source contains App Server protocol methods including:

```text
thread/read
thread/items/list
thread/turns/list
turn/start
turn/steer
turn/interrupt

remoteControl/enable
remoteControl/disable
remoteControl/status/read
remoteControl/pairing/start
remoteControl/pairing/status
remoteControl/client/list
remoteControl/client/revoke
```

`remoteControl/*` is marked experimental.

Important source location:

```text
openai/codex
codex-rs/app-server-protocol/src/protocol/common.rs
```

This proves that Remote functionality exists at the App Server layer even if the VS Code UI does not expose it.

### 3.2 VS Code Codex can be pointed at another executable

The official Codex repository includes a debug wrapper and documents the VS Code setting:

```json
{
  "chatgpt.cliExecutable": "/path/to/codex-wrapper"
}
```

OpenAI's repository uses this setting in `scripts/debug-codex.sh` to make the extension launch a custom Codex executable.

This is the preferred initial interception point.

### 3.3 Active writer ownership is a real blocker

Current Codex issues show that an active VS Code-owned thread can reject a second app-server / mobile Remote resume with:

```text
thread-store conflict:
thread <id> already has an active writer
```

Relevant upstream reports include Codex GitHub issues #40973, #50103, #41849, #37403, and related reports.

Therefore:

- Do not solve this by starting another app-server and calling `thread/resume`.
- Do not delete/bypass the thread writer lock.
- Do not kill the active VS Code-owned app-server merely to hand off control.
- The bridge should, if possible, route commands through the existing owner.

### 3.4 VS Code extension execution location matters

VS Code can run extensions in local, web, or remote Extension Hosts. With WSL/SSH/Dev Containers, workspace extensions may run remotely while UI extensions run locally.

Any bridge extension must explicitly determine where it runs and where the Codex binary/app-server actually runs.

Useful VS Code command during testing:

```text
Developer: Show Running Extensions
```

Do not assume Windows paths when the Codex process is actually running inside WSL.

## 4. Preferred architecture

Start with this architecture:

```text
                  phone
                    |
              ChatGPT plugin
                 / MCP
                    |
        authenticated bridge API
                    |
          local Bridge Controller
                    |
        +-----------+-----------+
        |                       |
  protocol/event store      approval state
        |
  Codex stdio proxy / wrapper
        |
  original Codex app-server
        |
 official VS Code Codex extension
        |
 SAME thread / SAME writer
```

The wrapper is not another Codex client that resumes the thread. It should be a transparent transport/interception layer around the exact Codex executable started by the official extension.

### Critical invariant

There should initially be **one persistent Codex App Server process and one thread writer**.

The proxy may multiplex requests only if that can be done without violating App Server's request/response semantics.

## 5. First implementation hypothesis: transparent executable wrapper

Use `chatgpt.cliExecutable` to point the official extension at a wrapper executable/script.

The wrapper should:

1. Receive every argument passed by VS Code.
2. Launch the real Codex executable with the same arguments/environment.
3. Proxy stdin from VS Code -> real Codex.
4. Proxy stdout from real Codex -> VS Code **byte-for-byte**.
5. Never write debug output to stdout.
6. Send diagnostics only to stderr or a separate log file.
7. Record enough JSON-RPC/App Server traffic to identify:
   - initialization,
   - thread IDs,
   - turn IDs,
   - notifications,
   - server requests such as approvals.
8. Initially perform **no message injection**.

The first pass is observation-only because protocol corruption would break the official extension.

If the traffic is newline-delimited JSON, parse only after confirming framing. Do not assume framing before capture.

## 6. Second implementation hypothesis: controlled message injection

Only after transparent proxying is stable:

- maintain a JSON-RPC request ID namespace for bridge-generated requests;
- route matching responses back to the bridge rather than VS Code;
- forward all VS Code-generated traffic normally;
- duplicate selected server notifications to the bridge event store;
- ensure server->client requests/approvals retain their original request IDs and exactly one side answers them.

Candidate remote operations:

```text
bridge.list_threads
bridge.get_live_thread
bridge.read_thread
bridge.get_active_turn
bridge.start_turn       -> turn/start
bridge.steer_turn       -> turn/steer
bridge.interrupt_turn   -> turn/interrupt
bridge.pending_approvals
bridge.answer_approval
```

Do not implement all of these at once. The first write test should be one harmless `turn/steer` against a disposable test thread.

## 7. Alternative experiment: built-in Remote Control

Because `remoteControl/*` exists in the same App Server protocol, test whether enabling Remote **on the VS Code-owned app-server itself** avoids the second-writer problem.

Do not assume success. Current upstream reports show mobile Remote can still create/resume through another app-server and hit the active-writer conflict.

Questions to answer experimentally:

```text
1. Can remoteControl/enable be sent to the exact app-server already owned by VS Code?
2. Does this register that existing server as the remote host?
3. When the phone opens the active thread, does the request get routed to the existing writer or does another app-server still try thread/resume?
4. Can the phone operate as a follower/remote client without acquiring a second writer?
5. Are approvals routed back through the original server?
```

If built-in Remote works directly through the existing writer, prefer it over a custom ChatGPT MCP control protocol.

## 8. ChatGPT plugin / MCP role

The ChatGPT plugin is a **control surface**, not the owner of Codex state.

It may eventually expose a small tool set such as:

```yaml
tools:
  - get_status
  - list_live_sessions
  - read_live_session
  - send_followup
  - steer_active_turn
  - interrupt_active_turn
  - list_pending_approvals
  - answer_approval
```

The plugin must communicate with the local bridge through an authenticated mechanism. Do not expose unauthenticated Codex control endpoints to the public internet.

Do not build the plugin first. Build it only after local bridge control is proven.

## 9. Testing strategy

### Phase A — Baseline capture

Record:

```text
VS Code version
official Codex extension version
bundled Codex binary path
codex --version
Windows vs WSL execution location
actual app-server command line
CODEX_HOME if overridden
relevant chatgpt.* settings
```

Create a disposable test project and disposable Codex conversation.

### Phase B — Wrapper transparency

Acceptance:

```text
VS Code Codex starts normally through wrapper.
New conversation works.
Existing inactive conversation opens.
Codex can read/write a test file.
A simple command can be approved/executed.
Streaming output remains normal.
Closing/reopening VS Code behaves exactly as baseline.
Wrapper logs protocol metadata without leaking to stdout.
```

Any behavioral difference is a blocker.

### Phase C — Protocol observation

Identify:

```text
thread creation/resume message
threadId
turnId
turn/start
turn/steer if generated by VS Code UI
turn/interrupt
notifications for model output/tool execution
approval request/response shape
```

Build a redacted protocol fixture for automated parser tests.

### Phase D — Local injection

Against a disposable conversation:

```text
1. Start a long but harmless task in VS Code.
2. Bridge obtains threadId + active turnId.
3. Inject one turn/steer request.
4. Confirm VS Code UI shows/reflects the steering result.
5. Confirm no second writer appears.
6. Confirm the original app-server remains the lock owner.
```

If `turn/steer` cannot be multiplexed safely, investigate whether the extension exposes a command/API that can submit the action instead.

### Phase E — Built-in Remote experiment

With wrapper instrumentation active, send:

```text
remoteControl/status/read
remoteControl/enable
remoteControl/pairing/start
```

Pair a phone only on a disposable test thread.

Observe whether the phone talks to the same app-server or triggers a second owner/resume path.

### Phase F — Local MCP plugin

Only after Phase D or E proves writable control:

```text
ChatGPT -> MCP -> bridge -> live thread
```

Start with read/status tools, then add one write tool.

### Phase G — Approval relay

Test only with a harmless command such as creating/removing a disposable file.

Verify:

```text
approval becomes pending in bridge
phone sees pending approval
phone decision maps to original request
VS Code receives consistent final state
no duplicate approval response is sent
```

### Phase H — WSL compatibility

Repeat the successful minimal path in a VS Code Remote-WSL window.

Verify where these run:

```text
bridge extension
wrapper
real Codex binary
socket/API endpoint
logs
```

Do not assume localhost on Windows == localhost inside WSL for every transport choice.

## 10. VS Code extension development workflow

For a custom helper extension:

```text
npm install
npm run compile/watch
F5
```

F5 should launch an **Extension Development Host**, a separate VS Code instance containing the development extension.

Use official VS Code extension integration testing with:

```text
@vscode/test-electron
```

Automated tests should cover the helper extension's own commands, configuration, bridge IPC, process discovery, and parser behavior.

Do not attempt to automate every Codex UI interaction initially. The official Codex extension is an external dependency and some compatibility checks should remain black-box/manual until the protocol bridge is stable.

For remote/WSL validation, package the development extension as VSIX and install that VSIX into the VS Code window connected to WSL. Use `Developer: Show Running Extensions` to confirm the actual Extension Host.

## 11. Compatibility test matrix

Minimum matrix:

```text
A. Windows local workspace
   - official Codex extension only
   - Codex extension + wrapper
   - Codex extension + wrapper + bridge helper

B. WSL workspace
   - official Codex extension baseline
   - wrapper/bridge installed on correct side
   - same live-thread tests

C. Codex compatibility
   - extension-bundled Codex version
   - version immediately before/after an extension update when feasible
```

Do not claim compatibility based only on `codex --version`. Test actual thread creation, active turn steering, approval, interruption, and recovery.

## 12. Automated tests to write early

Keep these independent of the real Codex service where possible:

```text
wrapper argv passthrough
environment passthrough
stdout transparency
stderr/log separation
JSON-RPC framing/parser
request ID routing
VS Code request vs bridge request ownership
server notification fan-out
approval request state machine
disconnect/reconnect cleanup
malformed frame handling
bridge authentication
```

Create protocol fixtures from sanitized real captures rather than inventing the whole protocol from memory.

## 13. Human/manual preparation required

The agent may ask the user to perform only actions that genuinely require UI/account access.

Likely manual actions:

```text
- Ensure official OpenAI/Codex VS Code extension is installed and logged in.
- Keep one disposable VS Code project for destructive testing.
- Temporarily set `chatgpt.cliExecutable` to the wrapper path.
- Reload VS Code when requested.
- Open Developer: Show Running Extensions when validating local vs WSL placement.
- Pair the ChatGPT mobile app if built-in Remote pairing reaches that stage.
- Install/connect the custom ChatGPT plugin/MCP when the bridge is ready.
- Confirm approval prompts on the phone during final tests.
```

The agent should provide exact click paths/commands when each manual action becomes necessary. Do not require the user to manually inspect protocol logs if the agent can parse them.

## 14. Safety / recovery

Before tests:

```text
- use a disposable repo or clean Git working tree;
- commit/stash important work;
- record original VS Code setting for chatgpt.cliExecutable;
- keep wrapper uninstall/disable path trivial;
- never delete Codex writer-lock files;
- never modify production conversation JSONL directly;
- never expose raw local bridge endpoints without authentication.
```

A wrapper failure must be recoverable by removing one VS Code setting and reloading the window.

## 15. Immediate tasks for the agent

Execute in this order:

```text
1. Inspect the currently installed official Codex extension:
   - version
   - installation location
   - bundled Codex binary
   - package.json settings
   - whether chatgpt.cliExecutable is present
   - how it launches app-server.

2. Capture baseline process topology while one disposable Codex chat is active.

3. Implement the smallest transparent wrapper.
   No MCP.
   No remote service.
   No UI.

4. Configure chatgpt.cliExecutable to the wrapper and prove parity with baseline.

5. Capture/redact App Server protocol traffic.

6. Determine whether a bridge-generated App Server request can be multiplexed through the existing process without breaking VS Code.

7. Specifically test a harmless turn/steer.

8. Separately test remoteControl/status/read and remoteControl/enable on the same app-server.

9. Report results before building a ChatGPT plugin.

10. Only if writable live-session control is proven, implement the minimal authenticated MCP layer.
```

## 16. Definition of success

Minimum success:

```text
- VS Code starts and owns one live Codex thread.
- No second app-server resumes the thread as a writer.
- Bridge can identify the live thread and current turn.
- Bridge can send at least one legitimate steering/follow-up action to that live thread.
- VS Code remains functional and reflects the updated state.
```

Full success:

```text
- Phone ChatGPT can inspect the same live conversation.
- Phone can steer an active turn or submit the next turn.
- Phone can interrupt.
- Phone can handle an approval request.
- Returning to VS Code continues the same conversation without handoff/restart.
- Works in both Windows-local and the user's WSL development workflow, or limitations are precisely documented.
```

## 17. Upstream references to inspect

Search the current upstream source/issues before coding because the interfaces are experimental and change quickly.

Important items:

```text
OpenAI Codex repository
- codex-rs/app-server-protocol/src/protocol/common.rs
- scripts/debug-codex.sh
- issue #40973   VS Code-owned thread vs Android Remote active-writer conflict
- issue #50103   VS Code / Remote WSL active-writer contention
- issue #41849   stale app-server ownership after Remote-SSH reconnect
- issue #37403   Remote Control vs active CLI writer
- issue #36604   chatgpt.cliExecutable scope behavior

VS Code documentation
- Testing Extensions
- Extension Host
- Supporting Remote Development and GitHub Codespaces
```

Do not rely on old assumptions: inspect the exact installed extension and bundled Codex build before implementing protocol details.
