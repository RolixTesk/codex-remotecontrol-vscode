# Findings

- 项目初始只有 agent.md；无相关历史记忆命中。
- Wrapper 必须在 baseline 活跃测试会话捕获之后实现。

- 扩展 26.930.51102；VS Code 1.140.0；bundled Linux Codex 0.160.0。
- Windows host + WSL app-server 是当前组合；并不是 Remote-WSL extension host。
- cliExecutable 为 application scope，目前未设置。
- 静态启动代码证实 JSONL reader、initialize id=字符串 1、请求 id=provider:request。真实协议捕获仍待 task 5。
- preliminary baseline 与可丢弃会话活跃验收分开记录；两个现存 app-server 分别来自 VS Code 和 Desktop。

- Disposable thread 01a10a32-56b2-7ca1-b19a-bdc80d426fa4；PID 21761 是唯一打开其 writer-lock 的进程。
- 用户的“测试完成”有文件、任务完成事件与原始工具标记支持；活跃时拓扑未及时采集。

- 上游 scripts/debug-codex.sh 仍演示 cliExecutable wrapper。当前 common.rs 源码已读取；未来实验仍以本机 0.160.0 为准。
- 原始流只保存在 WSL HOME 下的私有 state 目录，不放入 /mnt/d 项目目录。

- 透传检查包括约 512 KiB 输出、二进制输入、分离 stderr、非零返回码、stdin EOF、open-stdin streaming、handler/default SIGTERM，全部通过。
- 官方扩展没有 cliExecutable change 自动重启钩子，需要人工 Reload Window。原 runCodexInWindowsSubsystemForLinux 值保持 true。

- 当前 wrapper PID 27549 -> real app-server PID 27558；前次 PID 24831 -> 24840，窗口重开后被替换，符合正常 baseline 生命周期。

- 两次捕获：119/351 与 66/83（stdin/stdout）个有效 JSONL 完整帧；全部请求响应匹配。没有 initialized 通知但扩展正常工作，后续不得自行补握手。
- thread/start、thread/resume、turn/start 与 streaming lifecycle 已确认；未捕获 steer/interrupt/审批。
- 官方扩展自行 remoteControl/status/read，两个启动均返回 disabled。
- test app-server 无具名 Unix listener；默认 stdio 无法直接附加控制连接，不启新 app-server/daemon。

- schema 的 ephemeral Remote enable/disable 可避免更改持久配置；先进行同进程只读复用验证，再写 steer，之后才 Remote 实验。

- stub 验证：只有VSCode初始化一次；bridge响应不泄漏到VSCode；server approvals原ID/唯一VSCode答复保留；partial client帧不会被注入打断；controller断连不杀child；child退出清理socket与pending。真实审批仍待测试。
- /proc/<testpid>/fdinfo 的 writer fd 含 advisory lock，live probe 将比只检查open fd更严格，要求唯一实际lock owner为原child。

- 实际VSCode会在同一app-server、同一cwd创建短暂ephemeral helper turn，不能把activeTurns的首项当用户会话。应选择持有该thread writer lock的正式turn；ephemeral内部turn无需writer，缺锁不是协议冲突。

- Windows /mnt/d挂载目录的大小写别名在session metadata里可能不同；路径边界应比较samefile，不能简单lowercase（Linux不同大小写可能是不同目录）。

- 本地可写复用已获真实UI与文件证据，原app-server/唯一writer不变，无第二app-server resume。
- 内置Remote enable返回connecting，disable已最终确认disabled；状态read可能滞后于disable回复，需要明确最终核查，不能把立即接受等同稳定关闭。手机路由/审批还未证明。
- 进一步等待注册：同PID31334从connecting到connected用时4.09秒，environmentId非空，实际writer保持[31334]，随后恢复disabled。
- bundled 0.160.0 schema：pairing/start参数manualCode:boolean；响应pairingCode、manualPairingCode、environmentId、expiresAt；pairing/status接受pairingCode，返回claimed:boolean。
- 已安装官方webview的codex-mobile-setup-dialog-7ac2c387446d.js使用https://chatgpt.com/codex/pair?pairing_code=构造手机配对QR。常规官方文档从Desktop app开始配对；本实验直接对VSCode原app-server的experimental API配对，仍需实际手机证据。
- 只补pairing/start/status白名单及私有二维码脚本；uv缓存qrcode==8.2仅用于本地SVG，不新增wrapper运行依赖/HTTP服务。运行中的wrapper需人工reload加载新增方法。
- baseline新窗口52607已初始化且有control socket，但仅收到原thread/read；原thread writer仍在根目录窗口48024。不能让新app-server resume原聊天。Phase E可用新的UI disposable thread独立证明手机到其现有owner，不必复测已完成的steer；为此pair脚本支持显式精确thread ID，保留全部原cwd/writer检查。
- 手机实际任务只新增1个completed turn，内含2条有序独立userMessage；第二条到达时sleep30 command尚未completed，同一服务器随后输出PHONE_DONE并写两个marker。唯一writer始终在前后核查为52607。用户先称Queue，后修正为Steer，真实记录一致，不保留UI标签不一致的推论。
- 900秒只读phone观察器在人工操作前超时，不能声称其捕获活跃lock快照；原wrapper持续捕获的turn/item事件与completed command aggregatedOutput提供同服务器活跃追加证据，配合前后实际writer核查证明native路径。
- native可写控制已成立，按agent.md §7采用其内置认证/配对，不额外实现MCP。当前作用域仍仅baseline，日常项目/Remote-WSL适配尚未宣称完成。
- 原VSCode请求多次approvalPolicy=never；真实审批测试需明确切换测试聊天权限，不能假设现配置会弹审批。
- 已验证真实native手机审批：1个原item/commandExecution/requestApproval对应1个serverRequest/resolved，VSCode stdin没有审批响应，手机审批后指定文件正确且turn completed。native内部决策payload不在stdio捕获中，因此结论限定为请求/解决关联及无重复stdio回复；用户UI确认补足手机操作与VSCode同步。
- 当前Windows本地窗口+WSL Codex的手机读取/任务/活跃引导/停止/审批/VSCode同步均通过。Linux Python wrapper不是Windows原生exe；Windows-native不支持，Remote-WSL另行最小验收。
- Remote-WSL已有Microsoft扩展0.104.3及旧server1.139.1，WSL侧没有openai.chatgpt。通过官方code CLI安装固定26.930.51102，将自动安装与客户端1.140.0匹配的server。使用独立wsl-baseline目录，避免另一窗口resume已验证聊天。
- Remote-WSL app-server实际cwd继承VSCode安装目录；可选launchCwd用于临时匹配捕获，captureCwd仍限定thread工作区。此launch匹配不区分其他同启动目录窗口，因此只供当前唯一Remote-WSL测试窗口使用，收尾已恢复原配置。不能宣称日常多窗口隔离已实现。
- WSL手机最终协议为两个turn：初始审批/30秒命令completed，后续输入独立起turn；60秒等待命令已输出DONE/exit0，然后turn interrupted。用户UI反馈全部正常，但协议不证明WSL活跃Steer或运行中命令中断。原合并观察失败报告保留，事后只读报告以准确范围证明下一turn、审批、turn停止及原唯一writer保持；不要求重测。

- 日常入口现有缺口：captureCwd/launchCwd 是实验进程范围，无法可靠用于多项目日常选择；真正 project cwd 来自已加载 thread/read，必须据此选择原 owner。
- 已安装扩展没有公开 Remote 配对 command；沿用当前私有 socket 加薄 CLI，不新增 helper extension。
- 当前 Windows-host/WSL bundled Linux Codex 0.160.0 二进制 SHA256 相同；保留现有 realExecutable 路径即可，扩展升级后的路径更新仍手动配置。
- 两次实验的 private Remote 注册 environmentId 相同。连接和重新配对分开：已配对设备可先 connect，只有需要新设备时 pair，不假设每次都需新配对。
- 系统 Python 未安装 qrcode；日常配对页可用标准库生成手动码和官方链接，qrcode 可选用于本地 QR。所有凭据仅存 Linux 私有目录，stdout 不打印码/链接。
- 新 CLI 对当前运行 socket 的一次只读 list 返回空列表：现在没有可见、已加载的被包装会话。日常配置安装后必须人工重载目标 VS Code 项目窗口并打开聊天，不能自行起 app-server 或 resume 替代这个步骤。
- 用户就绪后原 UI 已加载聊天的 owner 为110302；三个聊天来自baseline/wsl-baseline且均由同一writer持有。新wsl-baseline聊天包含“连接入口就绪”输入，日常入口基于thread实际cwd识别成功，未用进程launch cwd猜项目。
- 实际bridge实例没有stdin.bin/stdout.bin，process.json没有argv。connect和后续status均为connected，writer仍[110302]；新Remote environment与之前已配对的WSL environment相同，未重新发pairing/start。本轮只确认日常入口连接/状态，不宣称再次做手机UI功能验收。
- 2026-10-05 用户补充确认 H 阶段已人工验证、要求去掉范围限制，并确认 J 阶段验证成功。当前验收状态按此更新，先前 protocol/observer 记录保留为历史事实，不追加测试。
- 实现介质考查：现有 wrapper 必须在官方扩展启动时接入，独立 GUI 不能直接附加其已有 stdio。官方包的 cliExecutable 为 application/restricted 配置；已安装扩展 command 中没有 Remote enable/pairing 入口，源码中也未找到对应公开方法。
- VS Code 官方文档确认插件可提供命令/工作区选择/状态 UI，可打包为 VSIX；Workspace Extension 在 WSL 端执行，UI Extension 在本机端执行。Node 子进程/Unix socket 不会自动跨宿主转发，介质选择必须明确 Windows/WSL 调用路径。
- 本地官方 activate(Ytr)不返回控制API；Windows WSL启动逻辑选择首个Ubuntu发行版而非简单等于默认发行版，配套插件必须对齐实际distro，不能靠默认值猜选。
- Phase K 决策：后续主交付建议为 VS Code workspace 配套插件（JavaScript/原生API、命令/QuickPick/状态栏、本地VSIX），保留Python后端及CLI；Windows本地侧需wsl.exe适配，Remote-WSL侧直接执行。没有第二个app-server、独立GUI或ChatGPT/MCP需求。
- 打包的必要改动限资源/配置稳定定位及官方binary定位/恢复设置；不把当前项目目录下的local config作为随版本变动的产品配置，不重写协议/owner路由。介质比较和下一Phase L范围记录于implementation-medium.md。
- Phase L实现方案：在VSIX中直接包含现有scripts/wrapper，标准库deploy_backend.py复制必要文件至WSL HOME稳定目录，保持原目录布局即可复用PROJECT/config定位，无需改已验证后端。接入前UserSetting备份存同一Linux私有目录，避免Windows与WSL插件各自globalState导致恢复值相互覆盖。
- 当前Node22.23.2/npm10.9.8可用；官方包路径/现有bridge配置可用。打包不新增前端运行依赖，vsce仅作为开发打包工具。
- 新增部署/插件离线检查首次通过，无产品缺陷；覆盖unset/null/string精确恢复、跨宿主再次enable保留首backup、路径参数数组、取消选择、重复点击及配对页备用打开。
- 当前Windows UserSetting接入已切至稳定Linux wrapper；修改前完整JSONC与原值均备份于私有Linux目录，未重载。共享首backup原值为仓库wrapper而不是unset，因此restore先恢复原wrapper；完全恢复官方bundled仍可移除单个cliExecutable设置。
- 重新核实实际VSCode程序将resources放在07f806f999版本子目录；当前目录存在Git初始提交0cc6377，早期“非Git仓库”的记录属于历史状态。
- vsce4自动将.vscodeignore中的父目录negation扩展为目录/**；白名单必须只写明确文件，不能额外!scripts/!wrapper。已用13条目精确archive断言防止本地配置、缓存、测试或凭据被带入包。
- 真实隔离Windows Extension Host可加载workspace插件并注册六个命令；Windows/Remote-WSL安装均完成。此检查证明插件承载，不替代当前工作窗口的必要UI连接/状态确认；完整手机能力继续沿用H/J验收。
- 实际Windows路径错误源于WSL二次解析：wsl.exe --默认使用Linux shell，会去掉Windows路径反斜杠；本机wsl.exe --help明确--exec在不用默认Linux shell时执行命令。修复linuxPath和python两个共享调用点为--exec，保持既有显式发行版和Node argv数组。旧mock只检查Node没shell，未覆盖WSL真实语义，本次补真实Windows进程回归。
- 已真实对照执行同一路径：旧--退出1，stderr为C:UsersRolixTesk.vscodeextensionsrolix.codex-live-remote-0.1.0；--exec退出0，返回/mnt/c/Users/RolixTesk/.vscode/extensions/rolix.codex-live-remote-0.1.0。微软基本命令文档也指向本机wsl --help作为完整选项来源：https://learn.microsoft.com/en-us/windows/wsl/basic-commands 。该对照无配置/会话写入。
- 2026-10-10当前环境实查：Windows官方扩展26.1007.21434，当前binary --version为0.162.0-alpha.17.2，首版旧26.930.51102 Windows目录已删除；WSL侧旧扩展仍在。Windows UserSetting没有chatgpt.cliExecutable，runCodexInWindowsSubsystemForLinux=true；没有其他profile/workspace配置覆盖证据。
- 当前项目聊天01a10a2b-0cb9-7202-a2ba-aff66f937b3c来自codex_vscode，其session cwd为本项目；实际writer唯一PID1114，运行新官方binary，parent1113不是wrapper。两个现存control.sock记录的child/wrapper均已退出，连接ECONNREFUSED。因此“没有已加载聊天”实际是没有可访问的wrapper实例，不代表官方聊天未加载。其他项目thread只用于核对同owner，不记录消息/内容。
- 新官方扩展仍支持application级cliExecutable；源码只在runCodexInWindowsSubsystemForLinux变化时自动Reload，本次不改该设置。已有部署入口能更新binary路径并按当前unset状态备份，不需改协议、重建插件或启动新app-server。
- 已恢复当前接入：managed binary更新至26.1007.21434，Windows UserSetting恢复稳定wrapper；旧settings/config/backup仅保存Linux私有recovery，不含聊天记录。比较恢复前后证明除单个cliExecutable外其余settings完全相同，实际writer仍1114，配置要在空闲UI重载后生效。setting为何被移除未知，不能断言是官方升级清除。
- 2026-10-10后续只读核查：wrapper6597 → 官方app-server6606，当前原项目thread已加载，唯一writer=[6606]，initialized=true、loadedThreadCount=1、Remote=connected。配置恢复已生效，不再等待重载；不据此宣称再次完成手机功能或状态栏视觉验收。
- 当前宿主是Windows Extension Host启动WSL Linux Codex：Windows exthost日志记录openai.chatgpt侧栏和rolix.codex-live-remote连接命令激活，WSL /proc未发现Linux Extension Host。它与Remote-WSL的Linux Extension Host直接启动Linux Codex不同。三种模式都采用客户端/后端/thread模型，但启动路径和IPC宿主不同。
- 官方扩展以单个连接对象持有app-server子进程；聊天对应协议thread，单次任务对应turn。同一后端可管理多个thread，不能把threadId当作PID；此前PID1114同时持有两个项目thread就是实际观察。工具命令可另起临时子进程，不意味着聊天各有独立后端。官方说明：https://developers.openai.com/codex/app-server ；宿主说明：https://code.visualstudio.com/api/advanced-topics/extension-host 。
- scripts/remote.py已经自动发现私有control.sock、已加载thread、项目目录和实际writer；单owner无需反复填写PID，多owner必须选择。减少重复配置的候选是保留稳定wrapper设置并自动维护官方binary版本路径，尚未实现自动维护。登录/配对凭据由原官方进程使用，复制凭据不能替代原stdio控制入口。
- 当前0.162.0-alpha.17.2的app-server --help支持stdio、Unix socket和WebSocket，以及daemon/proxy子命令；这不代表当前stdio实例自动暴露控制socket。PID6606的Unix socket fd没有命名监听路径。可用传输必须结合实际启动参数验证，不能一概断言Codex只支持stdio，也不能仅凭PID/凭据附加当前实例。本轮未启动daemon、独立app-server或新控制监听。
- 2026-10-10插件busy故障：extension.js在withProgress/action内部await成功通知和配对提示，catch内部await错误通知，finally才释放busy。VSCode通知Promise等待关闭/选择，因此后端已connected仍可长期占用全插件操作锁；现有mock立即返回通知Promise，遗漏了真实交互生命周期。修复范围为前端通知等待方式及延迟通知回归，不改后端互斥、IPC、writer或Remote协议。
- VSCode官方API明确showInformationMessage/showErrorMessage的Thenable在选择动作或dismiss时resolve；withProgress显示到任务Promise完成为止。与已定位代码路径一致：https://code.visualstudio.com/api/references/vscode-api#window 。补丁将普通通知直接显示，配对按钮异步处理且捕获打开页面失败，使通知交互不延长busy生命周期。
- 0.1.2已完成精确VSIX检查（13条目、九个runtime asset与source一致），Windows和Remote-WSL注册版本均为0.1.2，安装runtime与包逐字节一致。原工具打包session在用户继续后失效，但现有产物直接检查通过，不重复打包或后端测试。最新原项目writer=[1399]、Remote=disabled；不能把历史6606/connected说成当前状态，当前插件代码是否已加载仍需UI确认。
- doc命令说明按extension.js、backend.js、remote.py、deploy_backend.py及manifest核对，覆盖六条插件命令和五条CLI命令。README与doc的11个相对链接检查通过；VSIX追加两份文档后15条目精确检查通过，运行组件未改，既有H/J不重测。
