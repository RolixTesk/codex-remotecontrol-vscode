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
