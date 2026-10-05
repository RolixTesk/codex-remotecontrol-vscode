# Request reuse implementation — 2026-10-05

`python3 tests/check_control.py` — delegated agent, all 7 groups passed with a fake JSONL app-server. `python3 tests/check_wrapper.py` — observation-mode regression passed once after the change. No real app-server was started by these checks.

- Same child PID; VS Code initializes once, bridge does not initialize/resume.
- Bridge-owned string IDs have private response delivery; VS Code frames/notifications remain intact.
- Server approval request keeps original ID; exactly one VS Code answer forwarded. This is a synthetic request, not a real approval acceptance.
- Partial VS Code frame cannot be split by bridge bytes.
- Disallowed start/resume, unknown thread, stale turn rejected before write.
- Steering on the observed active turn reaches same child; Remote changes require strict ephemeral=true.
- Controller disconnect leaves child alive; child exit clears pending/socket; malformed frames pass unchanged.

Real read/steer/Remote proof awaits one UI reload and a UI-started disposable turn.

## Ephemeral helper regression

The first real read passed, but probe stopped before any write because an ephemeral helper appeared active before the user turn. After diagnosis, check_control.py and the focused check_probe.py both passed once: helper frames still reach VS Code, helpers are not control targets on future wrapper launches, and the probe selects only the same child PID's actual writer. The updated probe works with the current running wrapper without reloading it.
# Native pairing extension

The existing test sub-agent ran only the affected offline checks:

- `python3 tests/check_control.py`: same-child pairing start/status, unique private response IDs, credential isolation from VS Code, invalid parameters rejected before writing upstream.
- `python3 tests/check_probe.py`: mocked connecting → connected/disabled, temporary errored while restoring disabled, connection error and bounded timeout.
- `uv run --offline --no-project --with qrcode==8.2 python tests/check_pair_remote.py`: four groups passed for private QR files (directory 0700, files 0600), sanitized output, exact saved PID/thread reuse, failure restoration, and changed-writer rejection. No real Codex or network was used.

The running wrapper has not loaded the added pairing methods yet. Live phone pairing awaits manual reload and scan; these offline checks do not establish mobile routing.
