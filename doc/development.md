# 开发说明

本文说明 Codex Live Remote 的运行路径、配置和构建方式。用户操作见 [命令说明](commands.md)。

## 连接模型

官方 VS Code 扩展持有 app-server，thread 表示聊天，turn 表示任务。Remote 作用于所选 app-server，连接无需项目或已加载聊天。插件复用原进程，不启动第二个 app-server、不调用 thread/resume、不转移聊天 writer。

插件后端枚举私有 `control.sock`，读取本地 status 和相邻 `process.json`，仅接纳 initialized=true 且 childPid 一致的后端。多个后端由用户选择 PID；另一个后端正在连接时不会静默切换。

## 完整实现路径

1. 官方扩展读取 `chatgpt.cliExecutable`，启动稳定路径中的 `wrapper/codex-wrapper app-server ...`。
2. wrapper 以原参数、环境和目录启动官方扩展自带的 Codex binary，转发 stdio、stderr、信号和退出状态。日常 bridge 模式只保留私有 socket 和进程元数据，不捕获聊天流量。
3. `wrapper/control.py` 观察官方客户端的 initialize 和协议生命周期，复用这个 app-server 的 stdin。原客户端请求继续透传；桥接请求使用独立 ID，桥接回复只返回给 socket 调用者。
4. 插件命令经过 `extension/backend.js` 调用 `scripts/remote_backend.py`，通过 stdin JSON 传递操作、PID 和是否打开配对页，stdout 返回 JSON 结果。Windows 宿主用显式 `wsl.exe -d <distro> --exec` 执行 Linux Python；Ubuntu 本地与 Remote-WSL 宿主直接执行 Python，原样使用 Linux 路径。argv 不经 shell 重解析，配置快照经 stdin JSON 传递。
5. `scripts/control_client.py` 通过私有 socket 发送 JSONL，后端 worker 在操作前后校验后端身份，并调用原生 Remote 的 status/read、ephemeral enable/disable、pairing/start/status 和只读 client/list。
6. 官方 app-server 使用已有 ChatGPT 登录建立官方 Remote 连接。手机经 ChatGPT 的配对授权和原生 Remote 协议操作聊天，结果同步回原 VS Code 客户端。
7. `scripts/pair_remote.py` 将配对响应保存到私有文件，并使用内置 qrcode 生成本地 SVG/HTML。二维码指向官方配对 URL；浏览器与通知复用同一生成页面。

控制接口限制在读取、活跃 turn 引导及 Remote 操作，不提供聊天创建/resume或审批应答。steer 要求已观察到的 active turn 和 expectedTurnId。输入帧串行写入；桥接回复与超时后的迟到回复都不会进入官方客户端。原审批请求保留 ID，仍由官方客户端和原生 Remote 处理。

每次操作前后检查初始化状态及 childPid/metadata。只有本次新启用的 Remote 会在失败时清理，清理前再次核对身份；未知写请求不重放。

## 激活与配置

插件声明 `onStartupFinished`，在窗口启动后注册命令、显示状态栏并维护受管理的接入。默认开启 `codexRemote.autoConnect`：立即检测一次，之后每 5 秒检测官方扩展激活状态及 initialized 后端。该事件不保证两个插件的激活顺序，后台检测不主动激活官方扩展、不自动首次安装或重启 Codex。

只有当前 Global 设置仍指向托管 wrapper、仅一个后端可选且官方 `remoteControl/client/list` 确认有授权客户端时，内部 `auto-connect` 动作才复用原连接流程。client/list 只允许 `environmentId` 与 `limit=1`，不开放 revoke。多个实例交由手动命令选择，自动成功只更新状态栏，不弹通知或常驻进度。

`phone-pairing.json` 位于稳定运行目录，权限 0600，仅保存 installationId、environmentId 和 paired 布尔值。connect/pair/status 记住环境，自动检测再向当前登录的原后端确认授权；申请二维码不表示授权。配对码尚在有效期时继续只读检查，确认授权后记住结果。每次后端启动仍重新查询官方列表，撤销的设备不会触发自动启动；不读取或复制登录凭据。旧版未留下环境记录时，手动启动一次即可迁移，无需重新配对。

每个 PID 自动尝试一次；失败可能涉及未知写结果，不自动重放。等待扫码期间只重复授权查询。手动停止或恢复启动设置会暂停本窗口自动连接，手动启动/配对/配置可恢复，重开窗口恢复默认策略。自动动作复用 busy 互斥，销毁时清理计时器。

稳定运行文件位于 `~/.local/share/codex-remotecontrol/vscode/`。首次配置由 VS Code 配置 API 将 Global `chatgpt.cliExecutable` 指向稳定 wrapper，原值保存在 `settings-before-plugin.json`；恢复命令仅在当前设置仍等于受管理 wrapper 时还原它。

自动维护在激活及 connect/pair 前执行，只接纳 Global 设置仍指向 stable wrapper 且 backup.managedValue 匹配的安装。它从当前宿主的官方扩展路径定位 Linux binary，更新变化资产和 realExecutable，保留其他配置字段及首次备份。无变化不写文件，外部或已恢复设置不自动启用。

官方扩展路径来自 `vscode.extensions.getExtension('openai.chatgpt').extensionPath`，不猜测安装目录或版本。Ubuntu 本地通常位于 `~/.vscode/extensions/`；部署组件按当前架构选择 `bin/linux-x86_64/codex` 或 `bin/linux-aarch64/codex`。本地配置、路径定位及后端发现只使用文件和私有 socket，不读取登录凭据。未登录时也可开发和检查这些入口；启用官方 Remote 与申请配对需要登录。

维护不重启原进程，更新启动路径后可能需要用户在任务结束时重载。Windows 与 WSL 的官方扩展版本可能不同但共享稳定 Linux 配置。

## 数据与界面

控制 socket 和配对文件为 0600，私有目录为 0700。配对码、账号凭据和聊天流量不进入日志、仓库或发布包。复制按钮只复制本机配对 HTML 的 file URI，WSL 使用 wsl.localhost；二维码编码官方手机配对 URL。

通知和 clipboard 交互不延长后端操作锁，复制不会重新申请配对码。状态栏显示最近一次操作或查询结果；connected 表示 Remote 通道已启动，不表示手机已完成授权。

命令和界面文字从用户当前要做的决定出发，只说明实际效果、必要选择和恢复动作。连接范围在产品介绍中集中说明，协议和开发理由保留在本文及代码注释。

## 构建和测试

需要 Node.js/npm、Python 3 和 Linux/WSL 运行环境。运行 `npm ci`，再运行 `npm run package`；VSIX 和 SHA256SUMS 输出到 `dist/`。打包检查核对 manifest、全部运行资产与文档，拒绝额外或缺失文件。

受影响的离线检查：

```sh
node tests/check_extension.js
python3 tests/check_auto_connect.py
python3 tests/check_control.py
python3 tests/check_control_client.py
python3 tests/check_daily_remote.py --backend-lifecycle
python3 tests/check_deploy_backend.py
python3 tests/check_pairing_qr.py
```

仅检查 Ubuntu 查找路径可运行 `node tests/check_extension.js --linux-only` 和 `python3 tests/check_deploy_backend.py --linux-only`。这些检查不调用在线 Remote。

测试使用临时目录、fake app-server 和 Node mock；开发过程记录、验收数据、捕获和本地配置均不属于公开源码或 Release 资产。源码不依赖这些本地文件，VSIX 使用单文件白名单。

## Marketplace 发布

发布者 ID 为 `RolixTesk`，扩展标识为 `RolixTesk.codex-live-remote`。Marketplace 中必须有同一 ID 的发布者并授予发布账号权限；GitHub 昵称和登录不代替 Marketplace 发布者身份。

运行 `npm run package` 生成发布包。打包使用正常仓库、许可证和资源检查，将 README 相对链接重写到仓库的 `master` 分支。项目采用根目录 `LICENSE` 中的 Unlicense，打包时 `vsce` 将它命名为 `extension/LICENSE.txt`；内置 qrcode 保留上游 BSD 许可。

在 [Marketplace 管理页](https://marketplace.visualstudio.com/manage/publishers/)选择 `RolixTesk`，点击 **New extension → Visual Studio Code** 上传 VSIX。已有同一扩展时选择 **Update**。如已在本机配置好发布凭据，也可用 `npx vsce publish --packagePath dist/codex-live-remote-0.1.11.vsix` 上传已检查的同一产物。

更改 publisher 会更改扩展标识。升级时先卸载旧 `rolix.codex-live-remote`，保留原启动配置和恢复备份，再安装新包；不能同时运行两份扩展。此过程不需要恢复再重新配置 wrapper。发布要求见 [官方发布说明](https://code.visualstudio.com/api/working-with-extensions/publishing-extension)。

## 支持边界

当前支持 Ubuntu 本地 VS Code、Windows 本地 VS Code 通过 WSL 运行 Codex，以及 Remote-WSL，最低 VS Code 版本为 1.118。Python wrapper 使用 Linux 信号及 Unix socket，不支持 Windows 原生 codex.exe。原生 Remote 接口仍可能随官方版本改变，升级时应检查受影响的协议和资产。

当前 Remote 主机名取系统名称，没有插件自定义入口；不通过修改系统主机名或引入额外启动隔离实现改名。

## 终端版与 CLI

本插件只提供 VS Code 命令。Python worker 是这些命令的内部实现，不提供独立用户 CLI；升级维护会移除旧安装中的 `scripts/remote.py`。多实例选择在 VS Code 中完成，worker 只接收所选 PID 并校验原进程身份。

官方 Codex 已提供原生 `codex remote-control`（含 start、stop、pair 和 JSON 输出），TUI 可连接 app-server。终端使用这条官方路径，本项目不另行开发 TUI 版本。参见 [官方命令说明](https://learn.chatgpt.com/docs/developer-commands?surface=cli)；本项目的私有 JSONL socket 与官方 app-server socket 协议不同。
