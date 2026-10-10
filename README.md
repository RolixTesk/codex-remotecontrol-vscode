# Codex Live Remote

在 VS Code 官方 Codex 扩展的同一 app-server 上启用内置 Remote。手机继续操作原聊天，桌面保持连接。

以 VS Code 配套插件交付，现有 Python wrapper/CLI 是运行组件。支持 Windows 本地窗口 + WSL Codex，以及 Remote-WSL 窗口；需要官方 Codex 扩展和 WSL 内的 Python 3。

完整使用说明见 [文档目录](doc/README.md)，每条命令的作用和配置影响见 [命令说明](doc/commands.md)。

## 插件安装和使用

打开 VS Code 的扩展视图，点击 `…` → **从 VSIX 安装…**，选择 `codex-live-remote-0.1.2.vsix`。Remote-WSL 窗口应安装到 WSL 侧；Windows 本地窗口安装到本地侧。

在要连接的项目窗口按 `Ctrl+Shift+P`，依次运行：

1. **Codex Remote: 启用 / 更新接入**。部署稳定后端，备份并更新官方 CLI 设置。
2. 等当前任务结束，运行 **Developer: Reload Window**，在官方 Codex 面板打开原聊天。
3. **Codex Remote: 连接当前项目**。已有配对可直接连接；添加手机时运行 **Codex Remote: 配对手机**，按打开的页面完成配对。

**Codex Remote: 查看连接状态** 更新状态栏；点击状态栏也会查询。**Codex Remote: 断开当前项目** 关闭连接。多根工作区或多个会话进程时会要求选择目标；激活插件不会自动连接或重载。状态栏显示最近一次操作结果，不持续轮询。

后台操作完成后，进度任务立即结束，可继续运行其他命令；成功、失败或配对通知保留在通知栏时也不会占用操作锁。配对通知中的“打开配对页”按钮仍可使用。

手机在 ChatGPT 的 Codex / Remote 中选择主机，打开桌面的同一聊天。切换窗口前先断开原连接。连接开关作用于整个 app-server，项目选择用于定位 owner，不是手机访问项目的隔离边界。

后端安装到 WSL 的 `~/.local/share/codex-remotecontrol/vscode/`，接入前配置备份也在这里，Windows/WSL 两侧共享。配对页和凭据继续只放 Linux 私有 state；手动码无需额外依赖，安装可选 `qrcode` 后可显示二维码。

卸载前运行 **Codex Remote: 恢复接入前配置（卸载前）**，等任务结束后重载，再卸载插件。恢复的是插件首次启用前的值；若原来已有实验 wrapper，会恢复该 wrapper。需要直接恢复官方 bundled Codex 时，移除 User Settings 的 `chatgpt.cliExecutable` 并重载。当前设置若已被其他操作更改，恢复命令会提示并保留它。

本地构建：`npm ci`，然后 `npm run package`，产物在 `dist/`。插件只依赖 Node/VS Code 原生能力；npm 依赖用于开发打包。

## CLI 备用入口

日常命令在 WSL 终端运行。当前开发环境已安装 `codex-remote`；进入要控制的项目目录：

```sh
codex-remote list
codex-remote connect
codex-remote status
codex-remote disconnect
```

首次配对或添加手机时运行 `codex-remote pair --open`。私有页面提供手动配对码；安装了可选 `qrcode` 时也显示二维码。手机在 ChatGPT 的 Codex / Remote 中配对、选择主机，再打开桌面的同一聊天。已有配对通常可直接 `connect`。

从其他目录操作时加 `--workspace /项目目录`。同项目有多个窗口时，先看 `list`，再加 `--pid <childPid>`。同时只连接一个可见 owner；切换窗口前先 `disconnect`。连接开关作用于整个 app-server，项目参数用于选择 owner，不是手机访问项目的隔离边界。

日常模式不保存原始协议、消息或启动参数。配对码只存项目外的 Linux 私有目录，不打印到终端。重载/关闭窗口会结束临时连接；再次打开聊天后手动 `connect`。

未安装短命令时可运行 `python3 /此项目/scripts/remote.py <命令>`。配置和可选二维码用法见 [wrapper/README.md](wrapper/README.md)。

## 已验证行为

已在 Windows 本地窗口 + WSL Codex 验证：手机 ChatGPT 通过内置 Remote 读取、发起任务、引导活跃任务、停止和批准命令。VS Code 同步显示消息与结果，原 app-server 保持唯一 writer。

验证版本：VS Code 1.140.0、官方扩展 26.930.51102、Codex 0.160.0。

Remote-WSL 的重载恢复、手机配对、活跃引导、运行中命令停止、审批、后续任务和 UI 同步已通过验收，用户已补充人工验证。实际日常项目接入也已由用户确认成功，见 [人工验收记录](evidence/manual-acceptance.json)。Windows 原生运行此 wrapper 不受支持。

实现包含轻量 JavaScript 配套插件、Python 标准库 wrapper、私有 Unix socket 和日常 CLI。手机认证、配对和审批使用原 app-server 的内置 Remote，无额外服务、MCP 插件或第二个恢复聊天的进程。

- [配置、配对与恢复](wrapper/README.md)
- [验证结果及限制](evidence/milestone-report.md)
- [日常入口安装和检查状态](evidence/daily-entry.json)
- [任务进度](.planning/2026-10-05-live-session-bridge/task_plan.md)
- [实现介质考查](.planning/2026-10-05-live-session-bridge/implementation-medium.md)

阶段计划：Phase A–E、G–K 已完成，F 已由内置 Remote 替代。Phase L 正在交付最小配套插件和本地 VSIX，新增层的检查与安装状态见任务进度。Phase M 已规划自动维护官方升级后的binary路径与稳定接入配置，尚未实现。H/J 的人工验收不重复。

前期实验的原始协议保存在项目外的 Linux 私有目录，不能上传或提交。日常 `bridge` 模式只保留进程元数据和控制 socket。移除 VS Code User Settings 中的 `chatgpt.cliExecutable` 并重载窗口，可恢复官方 bundled Codex。

`evidence/daily-entry.json` 保存前一阶段日常连接成功的记录，不代表当前持续在线。接入使用已验证版本的 `chatgpt.cliExecutable` 调试设置与 experimental Remote 协议；官方扩展升级后运行“启用 / 更新接入”更新 binary 路径，再在空闲时重载。自动重连、Windows 原生 wrapper 和跨版本兼容性尚未提供。
