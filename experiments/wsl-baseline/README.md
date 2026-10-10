# Remote-WSL disposable workspace

This separate workspace prevents the Remote-WSL compatibility check from reopening
the Windows-host test conversation. Create a fresh chat through the official
Codex extension. Do not resume a chat owned by another window.

`baseline.txt` contains `WSL_BASELINE_OK`. All test outputs in this directory are
ignored. The controller observes the UI-created app-server; it never starts a
replacement app-server or removes writer locks.
