#!/usr/bin/env python3
"""Pair a phone to the existing disposable VS Code app-server, without a daemon."""

import argparse
import html
import json
import os
from pathlib import Path
from urllib.parse import urlencode

from probe_live import PROJECT, call, owners, result, wait_remote_status
from protocol import same_directory


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f)


def write_pairing_page(folder, remote, pairing, workspace=None):
    """Keep codes and the official pairing link in a local private page."""
    folder.mkdir(mode=0o700, exist_ok=True)
    url = "https://chatgpt.com/codex/pair?" + urlencode({"pairing_code": pairing["pairingCode"]})
    has_qr = False
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        (folder / "pairing.svg").unlink(missing_ok=True)
    else:
        image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=4)
        fd = os.open(folder / "pairing.svg", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            image.save(f)
        has_qr = True
    heading = "连接当前 VS Code 会话" if workspace is not None else "连接当前 VS Code 测试会话"
    context = (f"<p>项目：{html.escape(str(workspace))}</p>" if workspace is not None else "")
    content = ("<!doctype html><meta charset=utf-8><title>VS Code live session pairing</title>"
               "<style>body{font:20px system-ui;max-width:700px;margin:3em auto}img{width:380px}</style>"
               f"<h1>{heading}</h1>{context}<p>在手机 ChatGPT 的 Codex / Remote 中输入下方配对码"
               "（有二维码时也可扫码），确认账号和主机。</p>"
               f"<p>主机：{html.escape(remote['serverName'])}</p>"
               + ("<img src=pairing.svg alt=配对二维码>" if has_qr else "")
               + f"<p>手动配对码：{html.escape(pairing.get('manualPairingCode') or '未提供')}</p>"
               f"<p><a href=\"{html.escape(url, quote=True)}\">打开 ChatGPT 配对</a></p>"
               "<p>配对后选择此主机，打开 VS Code 中的同一聊天。</p>")
    fd = os.open(folder / "pairing.html", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return has_qr


def locate(root, cwd, thread_id, launch_cwd=None):
    for run in sorted(root.iterdir(), reverse=True):
        path = run / "control.sock"
        if not path.exists():
            continue
        try:
            status = result(call(path, "status"))
        except (OSError, ValueError, RuntimeError):
            continue
        threads = [t for t in status["threads"] if t == thread_id and owners(t) == [status["childPid"]]]
        meta = json.loads((run / "process.json").read_text())
        if (status["initialized"] and len(threads) == 1
                and meta["childPid"] == status["childPid"]
                and same_directory(meta["cwd"], launch_cwd if launch_cwd is not None else cwd)):
            return {"socket": str(path), "childPid": status["childPid"], "threadId": threads[0]}
    raise RuntimeError("No loaded disposable thread with its original unique writer")


def main(action, thread_id=None):
    config = json.loads((PROJECT / "wrapper/codex-wrapper.local.json").read_text())
    root, cwd = Path(config["captureRoot"]), Path(config["captureCwd"])
    folder = root.parent / "pairing"
    folder.mkdir(mode=0o700, exist_ok=True)
    anchor_file = folder / "state.json"
    report_file = PROJECT / "evidence/native-remote-pairing.json"
    report = {"action": action, "completed": False}
    anchor = None
    enabled_here = False
    try:
        if action == "start":
            if thread_id is None:
                prior = json.loads((root.parent / "live-probe.private.json").read_text())
                thread_id = prior["activeRead"]["result"]["thread"]["id"]
            anchor = locate(root, cwd, thread_id, config.get("launchCwd"))
        else:
            anchor = json.loads(anchor_file.read_text())
        path, pid, thread_id = anchor["socket"], anchor["childPid"], anchor["threadId"]
        assert result(call(path, "status"))["childPid"] == pid and owners(thread_id) == [pid]
        thread = result(call(path, "thread/read", {"threadId": thread_id, "includeTurns": False}))["thread"]
        assert same_directory(thread["cwd"], cwd) and thread.get("ephemeral") is not True
        report["childPid"] = pid
        if action == "start":
            assert result(call(path, "remoteControl/status/read"))["status"] == "disabled"
            enabled_here = True
            result(call(path, "remoteControl/enable", {"ephemeral": True}))
            remote = wait_remote_status(path, "connected", 45)
            pairing = result(call(path, "remoteControl/pairing/start", {"manualCode": True}))
            anchor.update(remote=remote, pairing=pairing)
            private_json(anchor_file, anchor)
            write_pairing_page(folder, remote, pairing)
            report.update(status=remote["status"], environmentRegistered=bool(remote.get("environmentId")),
                          pairingIssued=True, expiresAt=pairing["expiresAt"], awaitingPhone=True)
        elif action == "status":
            report["status"] = result(call(path, "remoteControl/status/read"))["status"]
            report["claimed"] = result(call(path, "remoteControl/pairing/status", {
                "pairingCode": anchor["pairing"]["pairingCode"],
            }))["claimed"]
        else:
            result(call(path, "remoteControl/disable", {"ephemeral": True}))
            report["status"] = wait_remote_status(path, "disabled", 5)["status"]
        report.update(writerPids=owners(thread_id), sameChild=result(call(path, "status"))["childPid"] == pid)
        assert report["writerPids"] == [pid] and report["sameChild"]
        report["completed"] = True
    except Exception as exc:
        report["failureType"] = type(exc).__name__
        if action == "start" and enabled_here:
            try:
                result(call(anchor["socket"], "remoteControl/disable", {"ephemeral": True}))
                report["restoredDisabled"] = wait_remote_status(anchor["socket"], "disabled", 5)["status"] == "disabled"
            except Exception as cleanup:
                report["cleanupFailureType"] = type(cleanup).__name__
    report_file.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0 if report["completed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "status", "disable"))
    parser.add_argument("--thread-id", help="Exact UI-created disposable thread for a fresh pairing experiment")
    args = parser.parse_args()
    raise SystemExit(main(args.action, args.thread_id))
