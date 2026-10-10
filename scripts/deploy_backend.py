#!/usr/bin/env python3
"""Install the VSIX's existing Python components at a stable Linux path."""

import argparse
import json
import os
from pathlib import Path
import platform
import sys
import tempfile

FILES = ("wrapper/codex-wrapper", "wrapper/control.py", "wrapper/protocol.py",
         "scripts/remote.py", "scripts/pair_remote.py", "scripts/probe_live.py")


def atomic_write(path, data, mode=0o600):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".deploy-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            os.fchmod(stream.fileno(), mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def locations():
    base = Path.home() / ".local/share/codex-remotecontrol/vscode"
    return base, base / "settings-before-plugin.json"


def info():
    base, backup = locations()
    result = {"wrapper": str(base / "wrapper/codex-wrapper"),
              "cli": str(base / "scripts/remote.py"),
              "installed": all((base / name).is_file() for name in FILES)
              and (base / "wrapper/codex-wrapper.local.json").is_file()}
    if backup.exists():
        result["backup"] = json.loads(backup.read_text())
    return result


def install(source, official, previous):
    arch = {"x86_64": "linux-x86_64", "aarch64": "linux-aarch64"}.get(platform.machine())
    if arch is None:
        raise ValueError("Unsupported Linux architecture")
    executable = official / "bin" / arch / "codex"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("Official extension's Linux Codex executable is missing")
    if (not isinstance(previous, dict) or type(previous.get("wasSet")) is not bool
            or (previous["wasSet"] and previous.get("value") is not None
                and not isinstance(previous.get("value"), str))):
        raise ValueError("Invalid original CLI setting")
    # Read everything before replacing any installed asset.
    assets = {name: (source / name).read_bytes() for name in FILES}
    base, backup_path = locations()
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    wrapper = str(base / "wrapper/codex-wrapper")
    config_path = base / "wrapper/codex-wrapper.local.json"
    current = json.loads(config_path.read_text()) if config_path.exists() else {}
    config = {"mode": "bridge", "realExecutable": str(executable),
              "captureRoot": current.get("captureRoot", str(Path.home() / ".local/state/codex-remotecontrol/captures"))}
    backup = json.loads(backup_path.read_text()) if backup_path.exists() else None
    if previous.get("value") == wrapper:
        if backup is None:
            raise ValueError("Managed CLI is configured but its original-setting backup is missing")
    else:
        backup = {"wasSet": previous["wasSet"], "value": previous.get("value"), "managedValue": wrapper}
    for name, data in assets.items():
        atomic_write(base / name, data, 0o700 if name == "wrapper/codex-wrapper" else 0o600)
    atomic_write(config_path, (json.dumps(config, indent=2) + "\n").encode())
    atomic_write(backup_path, (json.dumps(backup) + "\n").encode())
    return info()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("info", "install"))
    parser.add_argument("--extension-root", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "install":
            if args.extension_root is None:
                parser.error("install requires --extension-root")
            value = install(Path(__file__).resolve().parents[1], args.extension_root, json.load(sys.stdin))
        else:
            value = info()
        print(json.dumps(value))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
