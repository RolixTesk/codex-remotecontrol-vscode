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
         "scripts/remote_backend.py", "scripts/pair_remote.py", "scripts/control_client.py") + tuple(
    "scripts/vendor/qrcode/" + name for name in (
        '__init__.py',
        'base.py',
        'constants.py',
        'exceptions.py',
        'LUT.py',
        'main.py',
        'util.py',
        'compat/__init__.py',
        'compat/etree.py',
        'compat/png.py',
        'image/__init__.py',
        'image/base.py',
        'image/pure.py',
        'image/svg.py',
        'image/styles/__init__.py',
        'image/styles/moduledrawers/__init__.py',
        'image/styles/moduledrawers/base.py',
        'image/styles/moduledrawers/svg.py'
    )
) + ("scripts/vendor/qrcode/LICENSE", "scripts/vendor/README.md")


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
              "controller": str(base / "scripts/remote_backend.py"),
              "installed": all((base / name).is_file() for name in FILES)
              and (base / "wrapper/codex-wrapper.local.json").is_file()}
    if backup.exists():
        result["backup"] = json.loads(backup.read_text())
    return result


def official_executable(official):
    arch = {"x86_64": "linux-x86_64", "aarch64": "linux-aarch64"}.get(platform.machine())
    if arch is None:
        raise ValueError("Unsupported Linux architecture")
    executable = official / "bin" / arch / "codex"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError("Official extension's Linux Codex executable is missing")
    return executable


def validate_setting(previous):
    if (not isinstance(previous, dict) or type(previous.get("wasSet")) is not bool
            or (previous["wasSet"] and previous.get("value") is not None
                and not isinstance(previous.get("value"), str))):
        raise ValueError("Invalid original CLI setting")


def install(source, official, previous):
    executable = official_executable(official)
    validate_setting(previous)
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
    (base / "scripts/remote.py").unlink(missing_ok=True)
    return info()


def maintain(source, official, previous):
    """Refresh an existing managed installation without enabling or changing settings."""
    validate_setting(previous)
    base, backup_path = locations()
    wrapper = str(base / "wrapper/codex-wrapper")
    if not previous["wasSet"] or previous.get("value") != wrapper:
        return dict(info(), managed=False, updated=False, binaryChanged=False)
    if not backup_path.exists():
        raise ValueError("Managed CLI is configured but its original-setting backup is missing")
    backup = json.loads(backup_path.read_text())
    if backup.get("managedValue") != wrapper:
        raise ValueError("Original-setting backup does not match the managed CLI")
    config_path = base / "wrapper/codex-wrapper.local.json"
    config = json.loads(config_path.read_text())
    executable = str(official_executable(official))
    binary_changed = config.get("realExecutable") != executable
    # Read all source and installed assets before writing; preserve unrelated configuration.
    assets = {name: (source / name).read_bytes() for name in FILES}
    changed = {name: data for name, data in assets.items()
               if not (base / name).is_file() or (base / name).read_bytes() != data}
    for name, data in changed.items():
        atomic_write(base / name, data, 0o700 if name == "wrapper/codex-wrapper" else 0o600)
    legacy_cli = base / "scripts/remote.py"
    removed_cli = legacy_cli.exists()
    legacy_cli.unlink(missing_ok=True)
    if binary_changed:
        config["realExecutable"] = executable
        atomic_write(config_path, (json.dumps(config, indent=2) + "\n").encode())
    return dict(info(), managed=True, updated=bool(changed) or binary_changed or removed_cli, binaryChanged=binary_changed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("info", "install", "maintain"))
    parser.add_argument("--extension-root", type=Path)
    args = parser.parse_args()
    try:
        if args.action in ("install", "maintain"):
            if args.extension_root is None:
                parser.error(f"{args.action} requires --extension-root")
            operation = install if args.action == "install" else maintain
            value = operation(Path(__file__).resolve().parents[1], args.extension_root, json.load(sys.stdin))
        else:
            value = info()
        print(json.dumps(value))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
