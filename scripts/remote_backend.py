#!/usr/bin/env python3
"""Internal JSON worker for the VS Code extension's Remote commands."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import webbrowser

from pair_remote import private_json, write_pairing_page
from control_client import PROJECT, call, result, wait_remote_status


class UserError(Exception):
    """A message written here, safe to show without upstream response data."""


def discover(root, pid=None):
    found = []
    for path in sorted(root.glob("*/control.sock")):
        try:
            status = result(call(path, "status"))
            meta = json.loads((path.parent / "process.json").read_text())
            if (not status["initialized"] or meta["childPid"] != status["childPid"]
                    or (pid is not None and status["childPid"] != pid)):
                continue
            found.append({"socket": str(path), "childPid": status["childPid"],
                          "cwd": meta["cwd"], "active": bool(status["activeTurns"])})
        except (OSError, ValueError, KeyError, RuntimeError):
            continue
    return found


def select(found):
    if not found:
        raise UserError("未找到可连接的 Codex。请打开 Codex 面板后重试；首次启用接入后请先重载窗口。")
    pids = sorted({item["childPid"] for item in found})
    if len(pids) != 1:
        raise UserError("发现多个 Codex。请重新运行命令并选择实例。")
    return found[0]


def validate(target):
    status = result(call(target["socket"], "status"))
    meta = json.loads((Path(target["socket"]).parent / "process.json").read_text())
    pid = target["childPid"]
    if not status["initialized"] or status["childPid"] != pid or meta["childPid"] != pid:
        raise UserError("Codex 已关闭或重新启动。请重新运行命令并选择实例。")


def check_other_connections(target):
    # Keep a second owner from replacing the existing Remote connection.
    path = Path(target["socket"])
    for other in path.parent.parent.glob("*/control.sock"):
        if str(other) == str(path):
            continue
        try:
            status = result(call(other, "status"))
            remote = result(call(other, "remoteControl/status/read"))
        except (OSError, ValueError, KeyError, RuntimeError):
            continue
        if remote["status"] in ("connecting", "connected"):
            raise UserError(f"另一个 Codex（{status['childPid']}）已连接。请先断开，再连接此实例。")


def remember_phone(remote, paired=None):
    if not remote.get("installationId") or not remote.get("environmentId"):
        return
    path = PROJECT / "phone-pairing.json"
    record = {key: remote[key] for key in ("installationId", "environmentId")}
    previous = json.loads(path.read_text()) if path.exists() else {}
    if paired is None:
        paired = previous.get("paired", False) if all(previous.get(k) == v for k, v in record.items()) else False
    record["paired"] = paired
    private_json(path, record)


def has_paired_phone(target, remote):
    path = PROJECT / "phone-pairing.json"
    record = json.loads(path.read_text()) if path.exists() else {}
    environment = remote.get("environmentId") or (
        record.get("environmentId") if record.get("installationId") == remote.get("installationId") else None)
    if not environment or not remote.get("installationId"):
        return False
    clients = result(call(target["socket"], "remoteControl/client/list", {
        "environmentId": environment, "limit": 1,
    }))
    paired = bool(clients["data"])
    validate(target)
    remember_phone(dict(remote, environmentId=environment), paired)
    return paired


def operate(action, target):
    validate(target)
    path = target["socket"]
    folder = Path(path).parent / "pairing"
    remote = result(call(path, "remoteControl/status/read"))
    enabled_here = False
    report = {"action": action, "childPid": target["childPid"]}
    try:
        if action == "auto-connect":
            report["paired"] = has_paired_phone(target, remote)
            state_path = folder / "state.json"
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            report["pairingPending"] = (state.get("childPid") == target["childPid"]
                                        and state.get("pairing", {}).get("expiresAt", 0) > time.time())
        if action in ("connect", "pair", "auto-connect") and (action != "auto-connect" or report["paired"]):
            if remote["status"] == "disabled":
                check_other_connections(target)
                enabled_here = True
                result(call(path, "remoteControl/enable", {"ephemeral": True}))
            elif remote["status"] not in ("connecting", "connected"):
                raise UserError("Remote 当前连接异常；查看 status，明确断开后再连接。")
            remote = wait_remote_status(path, "connected", 45)
            if action == "pair":
                pairing = result(call(path, "remoteControl/pairing/start", {"manualCode": True}))
                folder.mkdir(mode=0o700, exist_ok=True)
                private_json(folder / "state.json", {"childPid": target["childPid"], "pairing": pairing})
                report["qrAvailable"] = write_pairing_page(folder, remote, pairing)
                report.update(pairingPage=str(folder / "pairing.html"), expiresAt=pairing["expiresAt"])
        elif action == "disconnect":
            if remote["status"] != "disabled":
                result(call(path, "remoteControl/disable", {"ephemeral": True}))
                remote = wait_remote_status(path, "disabled", 5)
        elif action == "status" and (folder / "state.json").exists():
            state = json.loads((folder / "state.json").read_text())
            if state["childPid"] == target["childPid"] and remote["status"] == "connected":
                try:
                    report["pairingClaimed"] = result(call(path, "remoteControl/pairing/status", {
                        "pairingCode": state["pairing"]["pairingCode"],
                    }))["claimed"]
                except RuntimeError:
                    report["pairingStatus"] = "expired-or-unavailable"
        validate(target)
        if action in ("connect", "pair", "status"):
            remember_phone(remote)
        report["status"] = remote["status"]
        return report
    except Exception:
        if enabled_here:
            try:
                validate(target)
                result(call(path, "remoteControl/disable", {"ephemeral": True}))
                wait_remote_status(path, "disabled", 5)
                print("连接未完成，已恢复 Remote 关闭状态。", file=sys.stderr)
            except Exception:
                print("恢复关闭状态未确认；请对同一 PID 运行 status，确认后再操作。", file=sys.stderr)
        raise


def open_page(page):
    if os.environ.get("WSL_DISTRO_NAME"):
        windows_path = subprocess.run(["wslpath", "-w", str(page)], check=True,
                                      capture_output=True, text=True).stdout.strip()
        powershell = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
        command = "Start-Process -FilePath '" + windows_path.replace("'", "''") + "'"
        subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", command],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif not webbrowser.open(Path(page).as_uri()):
        raise UserError("没有找到可用的浏览器。")


def main(request=None):
    try:
        if request is None:
            request = json.load(sys.stdin)
        action = request["action"]
        if action not in ("list", "connect", "pair", "status", "disconnect", "auto-connect"):
            raise UserError("未知远程控制操作。")
        config = json.loads((PROJECT / "wrapper/codex-wrapper.local.json").read_text())
        found = discover(Path(config["captureRoot"]), request.get("pid"))
        if action == "list":
            print(json.dumps([{k: v for k, v in item.items() if k != "socket"} for item in found],
                             ensure_ascii=False, indent=2))
        else:
            report = operate(action, select(found))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            if action == "pair" and request.get("open"):
                try:
                    open_page(report["pairingPage"])
                except Exception:
                    print("配对页已生成，浏览器未打开；请手动打开上面的 pairingPage。", file=sys.stderr)
        return 0
    except UserError as exc:
        print(str(exc), file=sys.stderr)
    except Exception as exc:
        print(f"操作未完成（{type(exc).__name__}）。请检查窗口和配置；写请求结果可能未知，请先查询状态。",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
