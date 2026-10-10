# VS Code Codex 同会话手机控制 — 阶段计划

日期：2026-10-05。Phase A–H 沿用 [agent.md §9](../../agent.md) 的名称；Phase I 以后为后续阶段。Immediate tasks 的原执行顺序和结果保留在下方映射中。

## Goal

手机通过官方内置 Remote 操作 VS Code 的同一 live conversation / app-server；桌面继续同步，保持原 writer。实现采用透明 wrapper、私有 socket 和最小 CLI。

## Current Phase

**Phase A–E、G–J 已完成。** 用户已补充确认 H 阶段人工验证和 J 阶段实际项目接入成功；H 不再标注范围限制。Phase F 已被内置 Remote 路径替代。

**Phase K 已完成：实现介质考查。** 推荐后续主交付为轻量 VS Code 配套插件（VSIX），保留已有 Python wrapper/CLI；详见 [实现介质考查](implementation-medium.md)。

**Phase L 进行中，0.1.2补丁已安装，等待必要UI验收。** 用户报告连接后进度任务一直存在、其他命令被busy阻止，根因是等待通知关闭把已完成后台操作保持为busy。修复及5组受影响回归已完成，VSIX和Windows/Remote-WSL两侧运行文件一致。最新只读快照为原项目唯一writer1399、Remote=disabled；此前PID6606/connected属于历史快照。当前不代替用户重载窗口或重复H/J测试。

**Phase M 已规划：自动维护接入配置。** 延续现有PID/thread/socket自动发现，自动定位官方升级后的binary并维护稳定wrapper配置；具体范围与架构结论见下方，不在本次故障修复中提前实现。

连接状态记录仅表示读取时的快照，不保证连接持续在线。`evidence/daily-entry.json`中的wsl-baseline/PID110302属于早期Phase I记录。

## Next Step

等当前Codex任务结束，在原窗口运行Developer: Reload Window，打开原聊天，再运行Codex Remote: 连接当前项目；保持成功通知未关闭，运行Codex Remote: 查看连接状态，确认进度结束且不再被busy阻止。无需再次启用接入或重新配对。此步骤完成后再推进Phase M。

## Phase overview

| Phase | 内容                    | 状态                                       | 已交付 / 下一项                                                   |
| ----- | ----------------------- | ------------------------------------------ | ----------------------------------------------------------------- |
| A     | Baseline 环境与进程拓扑 | complete                                   | 固定版本、启动方式、测试目录和 writer 记录                        |
| B     | 透明 wrapper 与 parity  | complete                                   | 原参数/环境/目录/输出透传，UI 读写、命令及重开通过                |
| C     | 协议观察与脱敏          | complete                                   | 真实 JSONL、thread/turn 生命周期、脱敏 fixture                    |
| D     | 本地同进程请求复用      | complete                                   | thread/read、一次 harmless steer、原 writer 保持                  |
| E     | 内置 Remote 与手机控制  | complete                                   | 同进程注册/配对，手机任务、活跃 Steer、停止、桌面同步             |
| F     | 自定义 MCP 插件         | superseded                                 | Phase E 已满足目标，按 agent.md §7 采用内置认证路径              |
| G     | 手机审批                | complete                                   | 原审批 request/resolved 对应，无重复 stdio 回复，写入成功         |
| H     | Remote-WSL 兼容         | complete                                   | 自动观察及用户补充人工验收完成，范围限制已解除                    |
| I     | 日常连接入口            | complete                                   | list/connect/pair/status/disconnect、安装及真实连接               |
| J     | 实际日常项目接入        | complete                                   | 用户确认实际项目接入验证成功                                      |
| K     | 实现介质考查            | complete                                   | 推荐 VS Code 配套插件 + 现有 Python 运行组件                      |
| L     | 最小 VS Code 配套插件   | in_progress — 0.1.2 installed, UI pending | 通知/busy修复与受影响检查通过，两侧已安装，待原窗口加载与状态确认 |
| M     | 自动维护接入配置        | planned                                    | 保留自动发现，维护官方升级后的binary路径与稳定wrapper配置         |

## Completed phases

### Phase A — Baseline capture

**Status:** complete

- 确认 VS Code 1.140.0、官方扩展26.930.51102、bundled Codex 0.160.0，以及 `chatgpt.cliExecutable` 和实际 app-server 启动方式。
- baseline UI 任务及唯一 writer 拓扑已记录；早期缺少的活跃快照由后续 parity/控制实验补充。
- 对应 Immediate tasks 1–2。

### Phase B — Wrapper transparency

**Status:** complete

- wrapper 保持原 argv、环境、cwd、stderr、退出码及信号行为；观察模式不注入协议。
- 用户确认文件读写、命令、streaming、关闭重开与 baseline 一致；离线透传检查通过。
- 对应 Immediate tasks 3–4；实现：`wrapper/codex-wrapper`。

### Phase C — Protocol observation

**Status:** complete

- 真实捕获确认 JSONL、请求 ID、thread/start/resume、turn 生命周期；后续记录补足 Steer、停止和审批事件。
- 原始流只存项目外的 Linux 私有目录；脱敏 fixture 和解析检查保留在 `tests/`、`evidence/`。
- 对应 Immediate task 5。

### Phase D — Local injection

**Status:** complete

- 私有 socket 复用原 stdio，隔离 bridge 响应 ID；不重复 initialize，不 resume 聊天。
- thread/read 及一次无害 turn/steer 实验成功，用户确认追加执行，原唯一 writer 保持。
- 对应 Immediate tasks 6–7；证据：`evidence/live-probe.json`。

### Phase E — Built-in Remote experiment

**Status:** complete

- 对原 app-server 执行 ephemeral enable/status/disable，确认注册成功；手机实际配对及控制成功。
- Windows 本地窗口 + WSL Codex 已证明手机发起任务、同一活跃 turn 引导、命令运行期间停止与 VS Code 同步。
- 对应 Immediate tasks 8–9及手机追加验收。依据持续捕获/事后核查的结论不伪称完整活跃 lock 采样；过期观察器的失败报告保留。
- 证据：`evidence/native-phone-live-result.json`、`native-phone-interrupt.json`。

### Phase F — Local MCP plugin

**Status:** superseded

- 原计划对应 Immediate task 10。Phase E 已证明内置认证的 Remote 可复用现有 writer，按 agent.md §7 采用该路径。
- 此阶段已被替代，不是待实现的欠项；当前后续计划不包含 MCP。

### Phase G — Approval relay

**Status:** complete

- 用内置 Remote 完成真实手机审批，无自定义审批 relay。
- 一个原 commandExecution 审批请求对应一个 resolved；VS Code stdin 无重复审批答复，文件写入及桌面结果由用户确认。
- native 内部 decision payload 不在 stdio 中，结论限于请求/解决关联和无重复 stdio 回复。
- 证据：`evidence/native-phone-approval.json`。

### Phase H — WSL compatibility

**Status:** complete

- Remote-WSL 的 Extension Host / binary / cwd 已确认；重载后同聊天恢复、原 owner 内置 Remote 配对成功。
- 手机审批、后续 turn、活跃 turn 引导、运行中命令停止及 UI 同步已验收。
- 2026-10-05 用户补充确认已人工验证，明确要求解除此前 H 阶段范围限制；本阶段 complete，不再排补测。
- 验收来源为既有协议观察及用户补充人工确认，见 `evidence/manual-acceptance.json`。既有 observer 报告作为历史记录保留。

### Phase I — Daily connection entry

**Status:** complete

- 用户选择日常连接入口；旧计划编号11–14统一归入此阶段。
- bridge 模式不依赖进程 launch cwd、不录原始协议/argv；按 UI 已加载聊天的真实项目目录和唯一 writer 选择 owner。
- CLI 提供 `list/connect/pair/status/disconnect`；多 owner 需明确 PID，已有其他可见连接时拒绝静默切换。配对页/凭据仅存私有目录，二维码可选。
- 新增6组离线检查及3项受影响旧检查通过；已安装 `~/.local/bin/codex-remote`，备份原配置并启用 bridge。
- 用户重载后，实际 `wsl-baseline` 的 connect/status 均成功，writer仍110302，环境注册与原配对一致；本轮未重做手机功能测试。
- 交付：`scripts/remote.py`、README；证据：`evidence/daily-entry.json`。

### Phase J — 实际日常项目接入

**Status:** complete

- 2026-10-05 用户确认“J阶段已验证成功”，实际日常项目接入完成。
- 验收结论依据用户人工确认，见 `evidence/manual-acceptance.json`；不重复发送测试任务或要求再次确认。

## Product direction

### Phase K — 实现介质考查

**Status:** complete

- 检查现有 wrapper/CLI、官方扩展的配置和公开 command，以及 VS Code 插件的承载/安装方式。
- 比较独立 CLI、独立桌面 GUI、VS Code 配套插件、ChatGPT/MCP 插件。
- 已输出推荐形态、保留的既有后端、最小 UI/打包范围和 Windows/WSL 落点，见 [implementation-medium.md](implementation-medium.md)。
- 结论：VS Code 配套插件为产品主入口；现有 CLI 是本地运行核心及备用入口，手机继续使用内置 Remote。独立桌面 GUI 无法省去 wrapper 接入，当前不选用。

## Planned phase

### Phase L — 最小 VS Code 配套插件

**Status:** in_progress

- 用轻量 Node/JavaScript 插件包装既有 CLI，提供当前项目选择、连接、配对、状态和断开入口，以及一个状态栏项。
- 补齐实际宿主调用：Remote-WSL 在 Linux 调用后端；Windows本地窗口通过明确发行版的wsl.exe调用后端，不启动新app-server。
- 管理稳定 wrapper/config 路径，定位官方 binary；备份/更新/恢复 cliExecutable，空闲时才提示必要重载。普通 deactivate 不当作卸载操作。
- 只检查新增插件层的选择、调用、宿主、配置恢复与本地VSIX安装；不重测 H/J，不改已经验证的协议路由。
- 交付本地 VSIX 和使用/恢复说明。详细最小范围见介质考查文档。

执行项：

- [X] 稳定后端部署/共享配置备份，明确Windows/WSL发行版和路径调用。
- [X] 最小VSCode命令/项目与owner选择/状态栏/恢复配置。
- [X] 新增层离线检查、真实隔离Extension Host检查、本地VSIX打包及两侧安装。
- [X] 通知未关闭导致busy阻塞的0.1.2修复、延迟通知回归、精确内容打包与两侧更新。
- [X] doc命令说明、README文档入口、VSIX文档白名单及精确内容检查。
- [X] 必要UI验收：确认插件命令加载、状态和恢复入口；不重测H/J。

恢复入口已通过离线检查和真实宿主命令注册检查，不要求在当前工作窗口实际恢复/卸载来重复验证。本次0.1.2修改正在运行的插件代码，需要在空闲时加载补丁；UI只验证连接通知保留时仍能查询状态，旧0.1.1的connected记录不作为补丁验收。

### Phase M — 自动维护接入配置

**Status:** planned

- 已确认的架构：官方插件连接app-server，一个后端可以管理多个聊天thread；一次请求对应turn，工具命令可产生临时进程。PID不是聊天ID，重载后的owner必须重新发现。
- 区分Windows原生、Windows插件跨WSL启动Linux后端、Remote-WSL中Linux插件直接启动后端。当前使用第二种；沿用既有显式发行版及--exec传输，不凭binary所在目录猜插件宿主。
- scripts/remote.py已有自动发现私有socket、真实项目thread和唯一writer，保留这一能力；多个owner继续明确选择，不增加第二app-server或独立daemon。
- 稳定wrapper路径首次启用后保留；在配套插件激活或连接入口定位当前官方扩展binary，更新受管理的版本路径。只在配置仍归本插件管理时维护，保留首次恢复备份，不覆盖用户改用的外部CLI或自行重新启用已恢复的接入。
- 复用原官方进程的登录与原生Remote认证；不把读取进程内存、复制登录token或持久保存临时配对码作为自动接入方案。当前实例的stdio入口通过wrapper复用，单凭PID/凭据不能附加。
- 升级时仅做受影响的路径/配置回归；必要UI重载等任务空闲后人工操作。不会自动重启writer或重复手机功能验收。
- Windows原生wrapper仍属可选事项；当前版本支持Unix/WebSocket传输不等于现有stdio进程已经开放控制端点，不为本阶段另建监听服务。

执行项：

- [ ] 自动定位当前官方binary并维护managed config，保留现有socket/owner发现。
- [ ] 验证扩展升级、外部CLI设置与精确恢复备份这几个受影响场景。
- [ ] 交付更新入口与升级后的最小使用说明。

## Optional backlog — undecided

这些事项未排入执行；不把它们视为必须完成的阶段。

| 事项                 | 状态      | 原因与启动条件                                                 |
| -------------------- | --------- | -------------------------------------------------------------- |
| Windows 原生 wrapper | undecided | 当前使用 Linux Python/Unix socket；仅在需要完全脱离 WSL 时考虑 |
| 自动重连             | undecided | 目前窗口重开后手动 connect；仅在明确需要持续连接时评估         |

## Immediate tasks mapping

执行顺序未改变：1–2 → Phase A；3–4 → B；5 → C；6–7 → D；8–9 → E；10 → F（按 §7 替代）。后续审批、WSL、日常入口分别为 G、H、I。

## Boundaries

- 复用用户所选项目的原 owner；不启第二个 writer、不删除锁、不自行 resume/接管聊天。
- Native Remote 开关作用于整个 app-server；项目选择不是手机端的项目访问隔离。
- 不创建 daemon、HTTP 服务或公网控制端点；UI/account 步骤需要人工完成。
- Phase 状态表示已交付和已有证据，不保证历史 PID/连接持续在线。

## Errors Encountered

- 0.1.1等待showInformationMessage/showErrorMessage关闭导致busy长期不释放：延迟通知回归在旧实现200ms内复现；0.1.2解除通知与操作锁关联，5组检查通过，已打包并安装。
- npm打包跨用户继续消息后工具session不可恢复（Unknown process id 38471）：确认原进程已退出、0.1.2产物存在，直接对现有VSIX做精确内容检查通过；未重跑打包或旧功能测试。
- 读取extension/package.json失败：本项目manifest实际位于根package.json，已按实际结构更新版本及pack脚本。
- 2026-10-10“无已加载聊天”提示实际由缺少wrapper接入引起：UserSetting已unset，旧binary路径失效、两个旧socket拒绝连接。当前聊天真实存在/唯一writer1114；已更新稳定配置和单个UserSetting并保留原writer，待空闲UI重载。无法判定该setting为何被移除，未归因于扩展升级。
- Phase L 0.1.0 Windows连接报wslpath路径反斜杠丢失：Node execFile虽无shell，WSL --仍经过默认Linux shell。已真实复现并修两共享入口为--exec；真实Windows Node回归、0.1.1精确内容检查和两侧更新均完成，待必要UI重载确认。
- 本次文档 patch 两行缺少 diff 前缀，整批校验失败未写入；修正格式后提交。旧 VS Code 安装资源路径已不存在，未据其推断配置路由，介质判断采用当前官方扩展源码和 VS Code 官方 API 文档。
- 早期工作目录未初始化 Git；Phase L 当前已核实存在初始提交 `0cc6377`，本轮不 stash/commit，保留既有变更和 agent.md。
- Live probe 起初选中了 ephemeral helper turn；改为按唯一实际 writer 筛选，错误定位期间未发 Steer。
- Windows挂载路径大小写别名导致字符串比较误拒绝；改用 samefile。
- 多个聊天恢复导致旧定位假设不成立；改为精确已加载 thread / 原 owner 选择，不猜选。
- 原聊天 writer 位于另一个未包装窗口；定位阶段拒绝，改用正确窗口的 UI 测试聊天，没有新进程 resume 绕过。
- 手机观察器先超时，WSL 合并 observer 首 turn 后结束；失败报告保留，持续捕获的事后结论明确范围，不覆盖为完整 live 成功。
- 日常文档一次 apply_patch 上下文不匹配；整批未写入，核对实际文本后修正。
