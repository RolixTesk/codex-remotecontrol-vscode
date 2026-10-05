# First live request probe — diagnosis

Same-process read succeeded: wrapper PID 31325, app-server PID 31334; read response matched requested disposable thread, and the initial sole actual advisory writer lock belonged to PID 31334. UI command also completed normally according to the user.

The extension then created both a persistent user thread and an ephemeral internal thread. The internal turn appeared active first, had no writer lock, and completed about 3 seconds later; the user turn remained active about 132 seconds. The probe selected the first active dictionary entry, read it, then stopped at its writer assertion.

Capture confirms **zero turn/steer and zero Remote write requests**. No injection outcome is uncertain; nothing was sent. The error was target selection, not second-writer contention or failed steering transport.

Fix: select only active turns whose unique actual writer lock owner is the original app-server PID; verify ephemeral=false before writing. The wrapper will also exclude ephemeral threads on future launches. Probe-side filtering works with the existing running wrapper, so another window reload is unnecessary.
