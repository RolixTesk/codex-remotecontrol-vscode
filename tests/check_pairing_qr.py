#!/usr/bin/env python3
"""Offline pairing-page checks using synthetic codes in temporary directories."""

import html
from html.parser import HTMLParser
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pair_remote import write_pairing_page
import qrcode


class Page(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.images, self.links, self.tags, self.text = [], [], [], []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "img":
            self.images.append(dict(attrs))
        elif tag == "a":
            self.links.append(dict(attrs)["href"])

    def handle_data(self, data):
        self.text.append(data)


def check_pairing_url(value, pairing):
    url = urlsplit(value)
    assert url.scheme == "https" and url.netloc == "chatgpt.com" and url.path == "/codex/pair"
    assert parse_qs(url.query) == {"pairing_code": [pairing["pairingCode"]]}


def check_page(folder, remote, pairing):
    page_file = folder / "pairing.html"
    content = page_file.read_text()
    page = Page(content)
    text = " ".join(page.text)
    assert folder.stat().st_mode & 0o777 == 0o700
    assert page_file.stat().st_mode & 0o777 == 0o600
    assert remote["serverName"] in text and pairing["manualPairingCode"] in text
    assert "script" not in page.tags
    assert html.escape(remote["serverName"]) in content and html.escape(pairing["manualPairingCode"]) in content
    assert page.links == [] and "a" not in page.tags
    assert "项目：" not in text and "作用范围" not in text and "后端" not in text
    assert "有效期" in text or "过期" in text
    assert "2023-11-14 22:13:20 UTC" in text
    assert len(page.images) == 1
    assert page.images[0]["src"] == "pairing.svg" and "二维码" in page.images[0]["alt"]
    svg_file = folder / "pairing.svg"
    assert svg_file.stat().st_mode & 0o777 == 0o600
    svg = ElementTree.parse(svg_file).getroot()
    assert svg.tag == "{http://www.w3.org/2000/svg}svg"
    assert any(node.get("d") for node in svg.iter("{http://www.w3.org/2000/svg}path"))


def main():
    with tempfile.TemporaryDirectory(prefix="codex-pairing-qr-check-") as temp:
        folder = Path(temp) / "pairing"
        remote = {"serverName": "Synthetic <script>host</script>& name"}
        pairing = {"pairingCode": "SYNTHETIC_CODE /?&+中文", "manualPairingCode": "SYNTHETIC_<script>MANUAL</script>&",
                   "expiresAt": 1700000000}
        with patch.object(qrcode, "make", wraps=qrcode.make) as make:
            assert write_pairing_page(folder, remote, pairing) is True
            check_pairing_url(make.call_args.args[0], pairing)
            check_page(folder, remote, pairing)
            # Existing world-readable files must become private when overwritten.
            for name in ("pairing.html", "pairing.svg"):
                (folder / name).chmod(0o644)
            assert write_pairing_page(folder, remote, pairing) is True
            check_pairing_url(make.call_args.args[0], pairing)
            check_page(folder, remote, pairing)
    print("PASS pairing page: actual SVG encodes official pairing URL; no link/project/scope paragraph; host/manual/UTC expiry, escaping and private files")


if __name__ == "__main__":
    main()
