# Same live app-server milestone — 2026-10-05

The central local hypothesis is proved for Windows VS Code host + WSL bundled Codex 0.160.0.

- Official extension starts through the wrapper, creates/reads/writes/streams normally and survives window close/reopen (user-confirmed parity).
- Real JSONL traffic provides thread/turn IDs; redacted fixtures and parser checks are recorded.
- Bridge thread/read and exactly one harmless turn/steer were routed through the existing stdio connection. No bridge thread/resume or turn/start was sent.
- Wrapper PID 31325 and app-server PID 31334 remained the same; the selected thread's unique actual advisory writer lock owner was PID 31334 before/after steering.
- Steering response matched expectedTurnId. The original task completed with exit0, then Codex created bridge-steer.txt with STEER_OK. User confirmed receipt/execution in the same VS Code chat.
- Native Remote status/read and ephemeral enable/disable were accepted by the same process. enable returned connecting. disable returned disabled; immediate status read briefly remained connecting, but final audit confirmed disabled.
- A separate bounded registration observation reached connected in 4.09 seconds with a nonempty environmentId. PID 31334 and its unique writer remained unchanged; Remote was again restored to disabled. See native-remote-registration.json.

## Outstanding acceptance

Native phone routing to this same writer is not proven. Remote was restored to disabled. Pairing, real approvals, interruption, next-turn submission, Windows-native and Remote-WSL execution have not been verified. MCP has not been implemented. Prefer the built-in authenticated route if it can keep the same live owner, before adding an external control layer.

The native pairing entry is prepared and requires one manual reload of the disposable VS Code window before use. Pairing credentials and offline QR artifacts will remain in private Linux state, not project evidence.

## Validation

See wrapper-validation.md, protocol-observation.md, control-validation.md and live-probe.json. Stub tests establish the wrapper's own routing behavior; real captures, writer-lock checks, test file and user UI confirmation establish this live-session result. Scope selection was corrected using ephemeral/writer checks and actual directory identity on Windows mounts.
