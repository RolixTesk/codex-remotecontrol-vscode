#!/usr/bin/env python3
"""Offline deployment checks confined to temporary homes, sources, and fake binaries."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy_backend


def snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mode & 0o777)
            for path in root.rglob("*") if path.is_file()}


def expect_failure(callback):
    try:
        callback()
    except (OSError, ValueError):
        return
    raise AssertionError("invalid deployment unexpectedly succeeded")


def main():
    with tempfile.TemporaryDirectory(prefix="codex-deploy-backend-check-") as temp:
        root = Path(temp)
        source, official = root / "source 中文 space'", root / "official 中文 space'"
        for name in deploy_backend.FILES:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        binary = official / "bin/linux-x86_64/codex"
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o700)

        for index, previous in enumerate([
            {"wasSet": False, "value": None}, {"wasSet": True, "value": None},
            {"wasSet": True, "value": "/old CLI space'中文"},
        ]):
            home = root / f"home-{index}"
            home.mkdir()
            with patch.object(deploy_backend.Path, "home", return_value=home), \
                    patch.object(deploy_backend.platform, "machine", return_value="x86_64"):
                before = snapshot(home)
                assert deploy_backend.info()["installed"] is False
                assert snapshot(home) == before, "info created deployment state"
                installed = deploy_backend.install(source, official, previous)
                base, backup_file = deploy_backend.locations()
                assert installed["installed"] and len(deploy_backend.FILES) == 6
                for name in deploy_backend.FILES:
                    assert (base / name).read_bytes() == (source / name).read_bytes()
                    assert (base / name).stat().st_mode & 0o777 == (0o700 if name == "wrapper/codex-wrapper" else 0o600)
                assert base.stat().st_mode & 0o777 == 0o700
                assert all((base / directory).stat().st_mode & 0o777 == 0o700 for directory in ("scripts", "wrapper"))
                config_file = base / "wrapper/codex-wrapper.local.json"
                config = json.loads(config_file.read_text())
                assert config["mode"] == "bridge" and config["realExecutable"] == str(binary)
                assert config["captureRoot"] == str(home / ".local/state/codex-remotecontrol/captures")
                assert config_file.stat().st_mode & 0o777 == backup_file.stat().st_mode & 0o777 == 0o600
                expected_backup = dict(previous, managedValue=installed["wrapper"])
                assert json.loads(backup_file.read_text()) == expected_backup

                stable = snapshot(home)
                assert deploy_backend.info() == installed
                assert snapshot(home) == stable, "info changed deployment files"
                deploy_backend.install(source, official, {"wasSet": True, "value": installed["wrapper"]})
                assert json.loads(backup_file.read_text()) == expected_backup, "repeat enable replaced original backup"

                stable = snapshot(home)
                missing_asset = source / deploy_backend.FILES[-1]
                asset_data = missing_asset.read_bytes()
                missing_asset.unlink()
                expect_failure(lambda: deploy_backend.install(source, official, previous))
                assert snapshot(home) == stable, "missing source changed existing deployment"
                missing_asset.write_bytes(asset_data)
                binary.chmod(0o600)
                expect_failure(lambda: deploy_backend.install(source, official, previous))
                assert snapshot(home) == stable, "invalid official binary changed deployment"
                binary.chmod(0o700)

                if index == 0:
                    command = subprocess.run([sys.executable, installed["cli"], "--help"],
                                             check=True, capture_output=True, text=True, timeout=5,
                                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
                    assert "--workspace" in command.stdout and command.stderr == ""
                    assert snapshot(home) == stable, "--help changed deployment"
                backup_file.unlink()
                stable = snapshot(home)
                expect_failure(lambda: deploy_backend.install(source, official, {
                    "wasSet": True, "value": installed["wrapper"],
                }))
                assert snapshot(home) == stable, "managed path without backup was overwritten"
    print("PASS six assets/permissions and stable CLI imports; info reads only")
    print("PASS unset/null/string backups preserved on repeat enable; missing backup refuses managed configuration")
    print("PASS source/binary failures leave existing deployment unchanged")


if __name__ == "__main__":
    main()
