#!/usr/bin/env python3
"""Check the VSIX contains only the intended runtime assets and README."""

import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("extension/extension.js", "extension/backend.js", "scripts/deploy_backend.py",
          "scripts/remote.py", "scripts/pair_remote.py", "scripts/probe_live.py",
          "wrapper/codex-wrapper", "wrapper/control.py", "wrapper/protocol.py")
DOCS = ("doc/README.md", "doc/commands.md")


def main():
    source = json.loads((ROOT / "package.json").read_text())
    archive = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / f"{source['name']}-{source['version']}.vsix"
    expected = {"[Content_Types].xml", "extension.vsixmanifest", "extension/package.json",
                "extension/readme.md", *("extension/" + name for name in (*ASSETS, *DOCS))}
    with ZipFile(archive) as package:
        names = package.namelist()
        assert len(names) == len(expected) and set(names) == expected, "Unexpected or missing VSIX assets"
        for name in (*ASSETS, *DOCS):
            assert package.read("extension/" + name) == (ROOT / name).read_bytes(), f"Stale asset: {name}"
        assert package.read("extension/readme.md") == (ROOT / "README.md").read_bytes(), "Stale README"
        manifest = json.loads(package.read("extension/package.json"))
        for key in ("name", "publisher", "version", "engines", "main", "extensionKind", "contributes", "capabilities"):
            assert manifest[key] == source[key], f"Stale manifest: {key}"
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (archive.parent / "SHA256SUMS").write_text(f"{digest}  {archive.name}\n")
    print(f"PASS VSIX: {len(expected)} entries, exact runtime assets, no local config/credentials/tests/cache")
    print(digest)


if __name__ == "__main__":
    main()
