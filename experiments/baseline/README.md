# Disposable baseline workspace

此目录仅用于官方 VS Code Codex 的 baseline 与 wrapper parity 测试。
当前不含 wrapper、MCP 或 bridge。

Baseline 首个测试提示：

```text
这是一次性 baseline 测试。只操作当前目录。读取 README.md，创建 baseline.txt，写入 BASELINE_OK 并读回。然后运行 python3 -u -c "import time; print('BASELINE_RUNNING', flush=True); time.sleep(180); print('BASELINE_DONE', flush=True)"。如需审批就等待我批准。执行完成后报告读回内容和命令结果。不要访问其他项目，不要联网，不要建立后台进程。
```

新会话、文件读写、命令执行、审批（仅如实际出现）、流式输出及窗口重开行为都需先记录 baseline，之后用 wrapper 重复。

Wrapper parity 提示（透明转发完成后用官方扩展新聊天执行）：

```text
这是透明 wrapper 的一次性 parity 测试。只操作当前目录。读取 baseline.txt；创建 wrapper-parity.txt 写入 WRAPPER_OK，并读回。然后运行 python3 -u -c "import time; print('PARITY_RUNNING', flush=True); time.sleep(15); print('PARITY_DONE', flush=True)"。如需审批就等待我批准。完成后报告文件内容及命令结果。不要访问其他项目，不要联网，不要建立后台进程。
```

UI 验收顺序：

1. 在这个测试窗口运行 Developer: Reload Window；确认 Codex 正常启动，先打开先前已完成的 baseline 聊天。
2. 新建聊天并发送以上 parity 提示；审批仅如实际出现时允许本次，注意输出是否正常。
3. 完成后关闭这个测试窗口，重新打开同一文件夹，再打开 parity 聊天，确认历史可见。
4. 回报“parity 完成”，并说明审批是否出现、流式输出/重开是否异常。不要复制原始协议日志。

配置与原始捕获由 agent 处理。这里的 UI 检查不能用独立子 agent 会话替代。

同进程请求复用测试（agent 的一次性 probe 已准备）：

1. 只重载这个测试窗口：Developer: Reload Window；先打开已完成的 parity 聊天，使同一thread被该app-server加载。
2. 新建聊天并发送以下提示。probe会先做只读检查，再发送一条额外 steering；不需要人工复制thread ID或解析日志。

```text
这是同一 live turn 的请求复用实验。只操作当前测试目录。读取 baseline.txt，然后运行 python3 -u -c "import time; print('LIVE_RUNNING', flush=True); time.sleep(120); print('LIVE_DONE', flush=True)"。完成后报告命令结果，并处理运行中收到的追加指令。不要联网，不要建立后台进程，不要访问其他项目。
```

3. 实验结束后告诉agent：是否在这同一个VS Code聊天中看到追加steering与STEER_OK最终确认，UI是否异常。未收到追加指令时直接报告，不要自行创建bridge-steer.txt。

probe 只运行一次且有时限；原始回复留在私有state，项目evidence/live-probe.json仅含脱敏结果。Remote enable为ephemeral测试，结束时恢复原disabled状态，不进行手机pairing。

首次 live probe 的目标筛选已修复：扩展的 ephemeral helper turn 没有 writer lock，不能选为用户 turn。确认首次从未发 steer / Remote 写请求。

第二次实验无需重载、无需新建聊天：在刚才已完成的同一测试聊天发送：

```text
继续一次性 live steering 测试。只在当前目录运行 python3 -u -c "import time; print('LIVE_RUNNING', flush=True); time.sleep(30); print('LIVE_DONE', flush=True)"；完成后报告结果，并处理运行中收到的追加指令。不要联网，不要建立后台进程，不要访问其他项目。
```

probe将跳过没有writer lock的helper，自动发送一次steering。不要自行创建 bridge-steer.txt。完成后反馈UI是否显示追加指令和STEER_OK确认。
