#!/usr/bin/env python3
"""Check the VSIX contains only the intended runtime assets and README."""

import hashlib
import json
from pathlib import Path
import sys
from xml.etree import ElementTree
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from deploy_backend import FILES

ASSETS = ("extension/extension.js", "extension/backend.js", "scripts/deploy_backend.py", *FILES)
DOCS = ("doc/README.md", "doc/commands.md", "doc/development.md")


def main():
    source = json.loads((ROOT / "package.json").read_text())
    archive = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / f"{source['name']}-{source['version']}.vsix"
    expected = {"[Content_Types].xml", "extension.vsixmanifest", "extension/package.json",
                "extension/readme.md", "extension/LICENSE.txt",
                *("extension/" + name for name in (*ASSETS, *DOCS))}
    with ZipFile(archive) as package:
        names = package.namelist()
        assert len(names) == len(expected) and set(names) == expected, "Unexpected or missing VSIX assets"
        for name in (*ASSETS, *DOCS):
            assert package.read("extension/" + name) == (ROOT / name).read_bytes(), f"Stale asset: {name}"
        readme = (ROOT / "README.md").read_text()
        repository = source["repository"]["url"].removesuffix(".git")
        for name in DOCS:
            readme = readme.replace(f"]({name})", f"]({repository}/blob/master/{name})")
        assert package.read("extension/readme.md") == readme.encode(), "Stale README or broken Marketplace links"
        assert package.read("extension/LICENSE.txt") == (ROOT / "LICENSE").read_bytes(), "Stale license"
        manifest = json.loads(package.read("extension/package.json"))
        assert manifest == source, "Stale package manifest"
        xml = ElementTree.fromstring(package.read("extension.vsixmanifest"))
        ns = {"v": "http://schemas.microsoft.com/developer/vsx-schema/2011"}
        metadata = xml.find("v:Metadata", ns)
        identity = metadata.find("v:Identity", ns)
        assert identity.attrib["Publisher"] == source["publisher"]
        assert identity.attrib["Id"] == source["name"] and identity.attrib["Version"] == source["version"]
        assert metadata.find("v:License", ns).text == "extension/LICENSE.txt"
        properties = {p.attrib["Id"]: p.attrib["Value"] for p in metadata.findall("v:Properties/v:Property", ns)}
        assert properties["Microsoft.VisualStudio.Services.Links.Source"] == source["repository"]["url"]
        assert properties["Microsoft.VisualStudio.Services.Links.Support"] == source["bugs"]["url"]
        assert properties["Microsoft.VisualStudio.Services.Links.Learn"] == source["homepage"]
        assert properties["Microsoft.VisualStudio.Code.Engine"] == source["engines"]["vscode"]
        assets = {p.attrib["Type"]: p.attrib["Path"] for p in xml.findall("v:Assets/v:Asset", ns)}
        assert assets["Microsoft.VisualStudio.Services.Content.License"] == "extension/LICENSE.txt"
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (archive.parent / "SHA256SUMS").write_text(f"{digest}  {archive.name}\n")
    print(f"PASS VSIX: {len(expected)} entries, exact runtime assets, Marketplace publisher/license/links, no local config/credentials/tests/cache")
    print(digest)


if __name__ == "__main__":
    main()
