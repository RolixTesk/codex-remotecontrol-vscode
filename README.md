# Codex Live Remote

在手机 ChatGPT 中继续使用 VS Code 的 Codex，查看进度、发送消息、引导或停止任务、处理审批，桌面同步显示结果。

一次连接对应一个 Codex 实例，手机可选择其中的聊天。启动远程控制前只需启动 Codex，无需打开某个会话或项目。

支持 Windows 本地 VS Code + WSL Codex，以及 Remote-WSL 窗口。需要已安装并登录官方 Codex 扩展，WSL 中有 Python 3；当前不支持 Windows 原生 Codex 接入。

## 安装与首次使用

在 VS Code 扩展视图点击 `…` → **从 VSIX 安装…**，选择 `codex-live-remote-0.1.7.vsix`。Windows 窗口安装到本地，Remote-WSL 窗口安装到 WSL。

1. 按 `Ctrl+Shift+P`，运行 **Codex Remote: 配置远程控制**。
2. 等当前任务结束，运行 **Developer: Reload Window**。
3. 启动 Codex，运行 **Codex Remote: 启动远程控制**。
4. 添加手机时运行 **Codex Remote: 配对手机**，用手机扫码或输入配对码，再选择聊天。

配对页会自动尝试在浏览器打开。浏览器未打开时，点击通知中的 **复制网页链接**，粘贴到电脑浏览器即可查看。

## 日常使用

插件随 VS Code 启动，无需另行打开。Codex 启动后运行 **启动远程控制**；有多个实例时按提示选择。已有配对的手机无需再次配对。

点击状态栏或运行 **查看远程控制状态** 查询最近结果。运行 **停止远程控制** 结束手机连接，桌面任务继续执行；切换实例前先停止原实例的远程控制。重载或重开窗口后需要再次启动远程控制。

官方 Codex 升级后的配置会自动更新；收到更新提示时，在任务结束后重载窗口。需要手动修复时运行 **配置远程控制**。

卸载前运行 **恢复 Codex 启动设置（卸载前）**，等任务结束后重载，再卸载插件。恢复的是首次配置前的设置。

完整操作说明见 [使用文档](doc/README.md) 和 [命令说明](doc/commands.md)。

## CLI 入口

在 WSL 终端运行，无需切换到某个项目目录：

```sh
codex-remote list
codex-remote connect
codex-remote pair --open
codex-remote status
codex-remote disconnect
```

多个实例时，从 `list` 中选择进程 ID，加 `--pid <ID>`。未安装短命令时可运行 `python3 /此项目/scripts/remote.py <命令>`。

## 实现方式

本插件通过官方 Codex 的 Remote 功能，将手机 ChatGPT 连接到 VS Code 已启动的 Codex，复用官方的登录、配对和远程控制能力。
