# Protocol observation — bundled Codex 0.160.0

真实捕获先于解析实现。两次 wrapper 启动共 185 个 stdin frame、434 个 stdout frame：LF-delimited JSON object、无 jsonrpc header、无尾部残帧；185/185 请求均有匹配响应。原始捕获仅存私有 WSL state，项目 fixture 完全脱敏。

- initialize id 是 string；后续 VS Code request id 是 provider:request 的 string namespace。
- 官方扩展没有发 initialized 通知，实际操作仍成功；桥不额外初始化。
- 新会话：thread/start -> result.thread.id；重开：thread/resume -> 同一 thread.id。
- turn/start -> result.turn.id；turn/started 与 turn/completed 带 params.threadId + params.turn.id。
- 模型输出：item/agentMessage/delta，含 delta、itemId、threadId、turnId。
- 命令输出：item/commandExecution/outputDelta；命令生命周期 item/started、item/completed。
- thread/status/changed 能辅助判断 live/idle，不能仅从列表推断 writer ownership。
- 未出现 turn/steer、turn/interrupt 或 server approval requests，因此其真实操作结果和审批形状尚待实验。
- UI 自动 remoteControl/status/read，两次均 disabled。

56 条结构 fixture 见 tests/fixtures/observed.jsonl。字符串默认替换，ID 使用关联别名，未知键名也替换；只保留协议字段、方法与有限类型/status enum。两个方向只有各自顺序，不能推断跨流精确时序。

check_protocol.py 由子 agent 检查通过：UTF-8 分块、完整/不完整 EOF、错误消息不回显输入、12 组请求响应、2 组 thread/turn 生命周期、合成凭据文本与字段名均未泄漏。

## Request reuse boundary

本机 app-server --listen 默认 stdio://；当前 PID 27558 的 Unix sockets 均无路径、没有 listener。因此不运行 app-server proxy/daemon，也不附加另一个 writer。下一步在已证明透明的 wrapper 中加入私有本地 socket：完整帧串行写入现有 stdin，bridge 生成独立 request ID，只拦截自己请求的 response；其他 traffic 原样给 VS Code，server approval request/response 仍完全由 VS Code 负责。

相关生成 schema 见 selected-protocol-schemas.json。turn/steer 必需 expectedTurnId；Remote enable/disable 支持 ephemeral=true。

Sources: installed extension source/captures; bundled CLI generated schema; [upstream transport](https://github.com/openai/codex/blob/main/codex-rs/app-server/src/transport.rs).
