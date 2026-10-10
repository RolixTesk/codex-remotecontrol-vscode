#!/usr/bin/env python3
"""Generate a private phone-pairing page for official Codex Remote."""

from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode

# Ship the SVG encoder with both the source CLI and deployed backend.
sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f)


def write_pairing_page(folder, remote, pairing):
    """Keep the QR and manual code in a local private pairing page."""
    folder.mkdir(mode=0o700, exist_ok=True)
    url = "https://chatgpt.com/codex/pair?" + urlencode({"pairing_code": pairing["pairingCode"]})
    import qrcode
    import qrcode.image.svg
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathFillImage, border=4)
    fd = os.open(folder / "pairing.svg", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as f:
        image.save(f)
    expiry = datetime.fromtimestamp(pairing["expiresAt"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    content = ("<!doctype html><meta charset=utf-8><title>Codex Remote 手机配对</title>"
               "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
               "<style>body{font:20px system-ui;max-width:700px;margin:3em auto;padding:0 1em}"
               "img{width:380px;max-width:100%;background:white}</style>"
               "<h1>配对手机</h1><p>在手机 ChatGPT 的 Codex / Remote 中扫描下方二维码"
               "或输入配对码，确认账号和主机。</p>"
               f"<p>主机：{html.escape(remote['serverName'])}</p>"
               + "<img src=pairing.svg alt=配对二维码>"
               + f"<p>手动配对码：{html.escape(pairing.get('manualPairingCode') or '未提供')}</p>"
               f"<p>有效期至：{html.escape(str(expiry))}</p>"
               "<p>配对后在手机选择此主机，再选择要操作的聊天。"
               "要继续桌面任务，请打开桌面正在使用的聊天。</p>")
    fd = os.open(folder / "pairing.html", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return True
