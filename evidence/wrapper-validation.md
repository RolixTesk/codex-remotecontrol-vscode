# Transparent wrapper validation — 2026-10-05

Command: `python3 tests/check_wrapper.py`
Runner: delegated wrapper_tests agent; all checks passed. Only fake executables in TemporaryDirectory were used; captures removed with the temp directory. No real app-server or UI session was started by the checks.

- Args including spaces and Unicode, inherited environment sentinel, cwd.
- Byte-for-byte binary stdout (about 512 KiB) and raw stdin/stdout capture.
- stderr stays separate and exact.
- stdin EOF, exit 0 and 23.
- Interactive streaming with stdin still open.
- SIGTERM forwarded: child's handler exits 29; default termination remains -15.
- Non-disposable cwd and --version: direct exec preserves PID, no capture.
- Private run directories mode 0700, files 0600.
- Actual bundled `--version` passthrough: codex-cli 0.160.0.

VS Code parity is pending. These checks do not prove official UI startup, thread resume, actual approvals or Windows/WSL window close/reopen behavior. Follow experiments/baseline/README.md.
