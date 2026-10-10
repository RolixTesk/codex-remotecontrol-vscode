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
    return {str(path.relative_to(root)): (
        path.read_bytes() if path.is_file() else None,
        path.stat().st_mode & 0o777, path.stat().st_ino, path.stat().st_mtime_ns,
    ) for path in root.rglob("*")}


def expect_failure(callback):
    try:
        callback()
    except (OSError, ValueError):
        return
    raise AssertionError("invalid deployment unexpectedly succeeded")


def check_maintenance():
    with tempfile.TemporaryDirectory(prefix="codex-maintain-backend-check-") as temp:
        root = Path(temp)
        source, old_official, official = (root / name for name in ("source 中文", "official-old", "official-new"))
        for name in deploy_backend.FILES:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        shutil.copyfile(ROOT / "scripts/deploy_backend.py", source / "scripts/deploy_backend.py")
        for extension in (old_official, official):
            binary = extension / "bin/linux-x86_64/codex"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\nexit 0\n")
            binary.chmod(0o700)
        home = root / "home"
        home.mkdir()
        with patch.object(deploy_backend.Path, "home", return_value=home), \
                patch.object(deploy_backend.platform, "machine", return_value="x86_64"):
            installed = deploy_backend.install(source, old_official, {"wasSet": True, "value": "/original CLI"})
            base, backup_file = deploy_backend.locations()
            managed = {"wasSet": True, "value": installed["wrapper"]}
            config_file = base / "wrapper/codex-wrapper.local.json"
            config = json.loads(config_file.read_text())
            config.update(mode="capture", captureRoot=str(root / "custom captures 中文"),
                          retainedOption={"nested": ["unchanged", 123]})
            config_file.write_text(json.dumps(config, indent=4) + "\n")
            backup_file.write_text(json.dumps(json.loads(backup_file.read_text()), indent=4) + "\n\n")
            backup_bytes = backup_file.read_bytes()
            (base / "scripts/remote.py").write_text("stale runtime asset\n")
            (base / "scripts/vendor/qrcode/base.py").unlink()
            shutil.rmtree(old_official)

            maintained = deploy_backend.maintain(source, official, managed)
            assert maintained["installed"]
            assert json.loads(config_file.read_text()) == dict(config, realExecutable=str(binary))
            assert backup_file.read_bytes() == backup_bytes, "maintenance rewrote the original backup"
            for name in deploy_backend.FILES:
                asset = base / name
                assert asset.read_bytes() == (source / name).read_bytes()
                assert asset.stat().st_mode & 0o777 == (0o700 if name == "wrapper/codex-wrapper" else 0o600)

            stable = snapshot(home)
            deploy_backend.maintain(source, official, managed)
            assert snapshot(home) == stable, "same-version maintenance wrote unchanged files"
            command = subprocess.run([
                sys.executable, "-S", str(source / "scripts/deploy_backend.py"), "maintain",
                "--extension-root", str(official),
            ], input=json.dumps(managed), check=True, capture_output=True, text=True, timeout=5,
                env={key: value for key, value in dict(os.environ, HOME=str(home), PYTHONDONTWRITEBYTECODE="1").items()
                     if key not in ("PYTHONPATH", "PYTHONHOME")})
            assert json.loads(command.stdout)["installed"] and command.stderr == ""
            assert snapshot(home) == stable, "maintain CLI wrote unchanged files"

            for previous in ({"wasSet": False, "value": None}, {"wasSet": True, "value": None},
                             {"wasSet": True, "value": "/external CLI"},
                             {"wasSet": False, "value": installed["wrapper"]}):
                deploy_backend.maintain(root / "missing source", root / "missing official", previous)
                assert snapshot(home) == stable, "unmanaged/restored CLI changed existing deployment"
                empty_home = root / "empty-home"
                empty_home.mkdir(exist_ok=True)
                with patch.object(deploy_backend.Path, "home", return_value=empty_home):
                    deploy_backend.maintain(root / "missing source", root / "missing official", previous)
                    assert snapshot(empty_home) == {}, "unmanaged CLI created deployment files"

            for invalid_backup in (None, json.dumps({
                "wasSet": True, "value": "/original CLI", "managedValue": "/another managed wrapper",
            }).encode()):
                if invalid_backup is None:
                    backup_file.unlink()
                else:
                    backup_file.write_bytes(invalid_backup)
                before = snapshot(home)
                expect_failure(lambda: deploy_backend.maintain(source, official, managed))
                assert snapshot(home) == before, "invalid backup changed deployment"
                backup_file.write_bytes(backup_bytes)

            config_bytes = config_file.read_bytes()
            config_file.unlink()
            before = snapshot(home)
            expect_failure(lambda: deploy_backend.maintain(source, official, managed))
            assert snapshot(home) == before, "missing config changed deployment"
            config_file.write_bytes(config_bytes)
            binary.chmod(0o600)
            before = snapshot(home)
            expect_failure(lambda: deploy_backend.maintain(source, official, managed))
            assert snapshot(home) == before, "invalid current official binary changed deployment"
    print("PASS maintenance: deleted old official path replaced, runtime assets refreshed, config fields and backup bytes preserved")
    print("PASS maintenance: unmanaged/restored CLI reads only; invalid backup/config/binary writes nothing; same-version API/CLI writes nothing")


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
                assert installed["installed"]
                assert "scripts/vendor/qrcode/__init__.py" in deploy_backend.FILES
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
                    assert "--pid" in command.stdout and "--workspace" not in command.stdout and command.stderr == ""
                    assert snapshot(home) == stable, "--help changed deployment"
                    isolated_qr = subprocess.run([
                        sys.executable, "-S", "-c", """
import sys
from pathlib import Path
from xml.etree import ElementTree
sys.path.insert(0, sys.argv[1])
from pair_remote import write_pairing_page
folder = Path(sys.argv[2])
assert write_pairing_page(folder, {"serverName": "Offline host"}, {
    "pairingCode": "SYNTHETIC_PAIRING_CODE", "manualPairingCode": "SYNTHETIC_MANUAL_CODE",
    "expiresAt": 1700000000,
}) is True
import qrcode
assert Path(qrcode.__file__).is_relative_to(Path(sys.argv[1]) / "vendor")
svg = ElementTree.parse(folder / "pairing.svg").getroot()
assert svg.tag == "{http://www.w3.org/2000/svg}svg"
assert any(node.get("d") for node in svg.iter("{http://www.w3.org/2000/svg}path"))
assert all((folder / name).stat().st_mode & 0o777 == 0o600 for name in ("pairing.svg", "pairing.html"))
""", str(base / "scripts"), str(root / "isolated-qr")], check=True,
                        capture_output=True, text=True, cwd=root, timeout=5,
                        env={key: value for key, value in dict(os.environ, PYTHONDONTWRITEBYTECODE="1").items()
                             if key not in ("PYTHONPATH", "PYTHONHOME")})
                    assert isolated_qr.stdout == isolated_qr.stderr == ""
                    assert snapshot(home) == stable, "QR generation changed deployed assets"
                backup_file.unlink()
                stable = snapshot(home)
                expect_failure(lambda: deploy_backend.install(source, official, {
                    "wasSet": True, "value": installed["wrapper"],
                }))
                assert snapshot(home) == stable, "managed path without backup was overwritten"
    print("PASS deployment assets/permissions and stable CLI imports; info reads only")
    print("PASS bundled QR generates SVG in isolated Python -S without external dependencies")
    print("PASS unset/null/string backups preserved on repeat enable; missing backup refuses managed configuration")
    print("PASS source/binary failures leave existing deployment unchanged")
    check_maintenance()


if __name__ == "__main__":
    main()
