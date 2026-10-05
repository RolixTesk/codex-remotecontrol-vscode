# Baseline — 2026-10-05

## Installed extension (Immediate task 1 complete)

- VS Code: 1.140.0（正在运行的 Code.exe ProductVersion）。
- 官方扩展: openai.chatgpt 26.930.51102。
- 安装目录: C:\Users\RolixTesk\.vscode\extensions\openai.chatgpt-26.930.51102-win32-x64。
- bundled Linux binary: `bin/linux-x86_64/codex`，`codex-cli 0.160.0`。
- bundled Windows binary: `bin/windows-x86_64/codex.exe`（当前启动路径未使用）。
- `chatgpt.cliExecutable` 存在：string/null、default null、scope application、restricted true。不能假设 workspace settings 可覆盖它。
- 扩展 package.json 无 extensionKind；本次进程证据表明由 Windows host 经 WSL 启动 app-server，Developer: Show Running Extensions 待 UI 确认。

## Observed launch topology (preliminary, NOT disposable baseline acceptance)

Windows Code.exe PID 15264 -> wsl.exe PID 26252 / forwarding process PID 26632 -> WSL relay -> Linux codex PID 19458。进程号为快照值。

```text
WSL distro: Ubuntu2404LTSC
cwd: /mnt/d/Works/codex-remotecontrol-vscode
real executable: /mnt/c/Users/RolixTesk/.vscode/extensions/openai.chatgpt-26.930.51102-win32-x64/bin/linux-x86_64/codex
argv: -c features.code_mode_host=true app-server --analytics-default-enabled
CODEX_HOME: child environment unset; effective default $HOME/.codex
```

启动源码 `KN` 选择 cliExecutable 或 bundled path；`gKt` 用 wsl.exe 启动同一可执行文件，保留参数并增加 PATH、RUST_LOG=warn、CODEX_INTERNAL_ORIGINATOR_OVERRIDE=codex_vscode。`startCodexProcess` 创建 pipe stdin/stdout/stderr，发送 initialize（id 字符串 "1"、experimentalApi=true），JSONL reader 消费 stdout。VS Code 请求 id 采用 provider:request 形式。以上是静态源码结论，尚非真实 wire capture。

另有 Codex Desktop 的 WSL app-server PID 8406，binary/cwd/CODEX_HOME 与扩展进程不同。只证明独立 app-server 存在，尚未观察它是否持有任何相同 thread。没有打开/修改其会话、没有注入请求或改锁。

## Manual acceptance still required (Immediate task 2 in progress)

- 在 experiments/baseline 建立新的可丢弃聊天；活跃 turn 中采集进程快照。
- 记录新会话、文件读写、命令执行、审批（如出现）、输出流。
- 记录该测试会话 inactive 后重新打开，以及关闭/重新打开测试窗口的行为。
- 此前不得推进 wrapper 实现及配置；协议捕获/脱敏在其后。

## Sources

- 本机 package.json / out/extension.js（摘录见 installed-launch-source.md）。
- https://learn.chatgpt.com/docs/developer-settings?surface=ide — cliExecutable 设置。
- https://learn.chatgpt.com/docs/app-server — JSONL stdio 协议。本机 wire framing 仍待捕获确认。

## Disposable baseline result

用户于 2026-10-05 报告测试已完成。会话 source=vscode、originator=codex_vscode、cli_version=0.160.0，cwd=experiments/baseline。任务开始 11:53:54、完成 11:57:30（北京时间）；测试文件读回 BASELINE_OK，工具输出标记见 baseline-test.json。测试窗口 app-server PID 21761 持有此 thread 的 writer-lock fd；扫描 /proc 未发现其他进程打开相同 lock。

限制：进程快照是在任务完成后采集，没有活跃期间即时拓扑；仍存活的 writer 是可用于后续对照的 baseline。审批是否出现、流式 UI 显示与 inactive/关闭重开行为暂无独立证据，留在 parity 人工验收清单中，不宣称已通过。
