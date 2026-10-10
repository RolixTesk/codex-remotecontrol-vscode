#!/usr/bin/env python3
"""Connect a phone to a project's existing VS Code Codex owner."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import webbrowser

from pair_remote import private_json, write_pairing_page
from probe_live import PROJECT, call, owners, result, wait_remote_status
from protocol import same_directory


class UserError(Exception):
    """A message written here, safe to show without upstream response data."""


def discover(root, workspace=None, pid=None):
    found = []
    if not root.exists():
        return found
    for path in sorted(root.glob("*/control.sock")):
        try:
            status = result(call(path, "status"))
            meta = json.loads((path.parent / "process.json").read_text())
            if (not status["initialized"] or meta["childPid"] != status["childPid"]
                    or (pid is not None and status["childPid"] != pid)):
                continue
            for tid in status["threads"]:
                try:
                    thread = result(call(path, "thread/read", {"threadId": tid, "includeTurns": False}))["thread"]
                except (OSError, ValueError, KeyError, RuntimeError):
                    continue
                if (thread["id"] != tid or thread.get("ephemeral") is True
                        or (workspace is not None and not same_directory(thread["cwd"], workspace))
                        or owners(tid) != [status["childPid"]]):
                    continue
                found.append({"socket": str(path), "childPid": status["childPid"],
                              "threadId": tid, "workspace": thread["cwd"],
                              "active": tid in status["activeTurns"]})
        except (OSError, ValueError, KeyError, RuntimeError):
            continue
    return found


def select(found):
    if not found:
        raise UserError("没有找到此项目已加载的 VS Code 聊天。请重载该窗口并打开或新建聊天，再运行 list。")
    pids = sorted({item["childPid"] for item in found})
    if len(pids) != 1:
        raise UserError(f"此项目有多个 owner：{pids}。先运行 list，再用 --pid 明确选择窗口。")
    # Remote is process-wide; any loaded project thread identifies the same owner.
    return found[0]


def validate(target):
    status = result(call(target["socket"], "status"))
    tid, pid = target["threadId"], target["childPid"]
    if (not status["initialized"] or status["childPid"] != pid
            or tid not in status["threads"] or owners(tid) != [pid]):
        raise UserError("所选聊天的原 owner 已变化。请重新运行 list；本次未切换到其他进程。")
    thread = result(call(target["socket"], "thread/read", {"threadId": tid, "includeTurns": False}))["thread"]
    if (thread["id"] != tid or thread.get("ephemeral") is True
            or not same_directory(thread["cwd"], target["workspace"])):
        raise UserError("所选聊天的项目目录已变化。请重新运行 list。")


def check_other_connections(target):
    # Both verified hosts registered the same environment: connect one owner at a time.
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
            raise UserError(f"另一个窗口 PID {status['childPid']} 已连接 Remote。先用 list 找到其项目并 disconnect，再连接此窗口。")


def operate(action, target):
    validate(target)
    path = target["socket"]
    folder = Path(path).parent / "pairing"
    remote = result(call(path, "remoteControl/status/read"))
    enabled_here = False
    report = {"action": action, "childPid": target["childPid"], "workspace": target["workspace"]}
    try:
        if action in ("connect", "pair"):
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
                report["qrAvailable"] = write_pairing_page(folder, remote, pairing, target["workspace"])
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
        report["status"] = remote["status"]
        return report
    except Exception:
        if enabled_here:
            try:
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "connect", "pair", "status", "disconnect"))
    parser.add_argument("--workspace", type=Path, help="项目目录；操作默认当前目录，list 默认列出全部项目")
    parser.add_argument("--pid", type=int, help="同项目多个窗口时明确选择原 app-server PID")
    parser.add_argument("--open", action="store_true", help="配对后用默认浏览器打开私有页面（仅 pair）")
    args = parser.parse_args(argv)
    if args.open and args.action != "pair":
        parser.error("--open 只用于 pair")
    try:
        workspace = args.workspace
        if args.action != "list" and workspace is None:
            workspace = Path.cwd()
        if workspace is not None and not workspace.is_dir():
            raise UserError("--workspace 必须是现有项目目录。")
        config = json.loads((PROJECT / "wrapper/codex-wrapper.local.json").read_text())
        found = discover(Path(config["captureRoot"]), workspace, args.pid)
        if args.action == "list":
            print(json.dumps([{k: v for k, v in item.items() if k != "socket"} for item in found],
                             ensure_ascii=False, indent=2))
        else:
            report = operate(args.action, select(found))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            if args.open:
                try:
                    open_page(report["pairingPage"])
                except Exception:
                    print("配对页已生成，浏览器未打开；请手动打开上面的 pairingPage。", file=sys.stderr)
        return 0
    except UserError as exc:
        print(str(exc), file=sys.stderr)
    except Exception as exc:
        print(f"操作未完成（{type(exc).__name__}）。请检查窗口和配置；写请求结果可能未知，不要自动重试。",
              file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
