# Progress

- 2026-10-05：已阅读 agent.md，恢复/建立顺序计划；未修改 VS Code 设置。

- Immediate task 1 完成：读取本机扩展 manifest/启动代码、运行 bundled --version、保存原设置和 Windows/WSL 进程初始快照。
- Immediate task 2 进行中：已准备 experiments/baseline；等待人工创建真实官方扩展测试聊天。
- 未实现 wrapper、未修改设置、未启动额外 app-server、未实现 MCP。

- 按用户要求，规划文件迁移到 .planning/2026-10-05-live-session-bridge/；根目录不保留规划记录。

- 用户报告 baseline 完成，并授权后续测试使用子 agent。保存 baseline-test.json；限定读取 disposable 会话记录，无原始会话文本进入项目。
- baseline 与单 writer 有证据；活跃快照、审批 UI、窗口重开仍待补齐，未宣称全部兼容验收通过。
- Immediate task 3 开始，仅透明字节转发。

- 已实现 wrapper/codex-wrapper：标准库、双向字节透传、独立私有原始流文件、测试 cwd 外 exec、无帧解析和注入；bundled --version 透传为 codex-cli 0.160.0。
- 已授权子 agent 编写 fake-child 集成检查，仅维护 tests/check_wrapper.py，不操作真实 app-server。

- Immediate task 3 完成：tests/check_wrapper.py 的 fake-child 集成检查由子 agent 全部通过；未重复运行。
- Immediate task 4 进行中：User chatgpt.cliExecutable 已配置为 wrapper Linux path；原完整设置备份留在私有 Linux state 目录，项目只记录路径/哈希。其他设置字节保持不变。
- 不自动重载窗口；等待用户对 official UI 做 parity。未进行实际协议解析、请求注入或 MCP。

- 用户报告 parity 完成：baseline 文件 BASELINE_OK、wrapper 文件 WRAPPER_OK、PARITY_RUNNING/PARITY_DONE、exit 0、无审批、重开无异常。Immediate task 4 完成。
- 捕获存在两次 wrapper 启动，第一次随窗口关闭 SIGHUP 退出（-1），第二次目前仍存活；没有 captureErrors。只分析这两份私有 test 捕获。
- Immediate task 5 开始；审批 request shape 待捕获。

- Immediate task 5 完成：真实 fixture 56 records；两个流全部有效且匹配。子 agent 的 check_protocol.py 全部通过。未知 method 可能在 summary 中泄漏任意文本的问题已修复为白名单统计；合成 sentinel 确认不会泄漏。
- 已从 bundled 0.160.0 生成相关静态 schemas：steer 必须 threadId + expectedTurnId + input，Remote enable/disable 支持 ephemeral 参数；未运行真实 app-server。
- Immediate task 6 开始；现有 app-server 无 control listener，因此复用需要在 wrapper 内路由，不启动 daemon。

- 最小控制路由实现完成（control.py），仅测试 cwd 启用私有 Unix socket；5个上游方法，无 thread/start/resume 与 approval answer。
- 子 agent 的 check_control.py 7组stub集成检查通过；观察模式 check_wrapper.py 回归通过。Ephemeral整数1误判已修为严格boolean；已验证。
- 尚无真实bridge RPC，阶段6未宣称完成。旧进程仍运行观察版，需要人工重载才能加载新代码。
- 已准备一次性 probe_live.py：先read/核对锁归属，之后只steer UI开启的活跃turn，应用marker成功后再测试ephemeral Remote并恢复disabled。

- 一次性 live probe 已启动，等待最多900秒的UI重载/活跃turn；不是daemon，无新app-server。命令 python3 scripts/probe_live.py --wait 900。后续读取工具session输出与evidence/live-probe.json，先检查结果再决定是否重跑，绝不盲目重试steer。
- 当前一次性probe工具session_id=7642（可用write_stdin读取）；真实read/steer/Remote结果尚待UI触发。

- 用户报告长命令完成、exit0、没有追加指令。读取session7642：read成功后wait-for-active-turn AssertionError退出，故未发steer。
- 实际捕获有ephemeral内部turn先活跃约3秒，正式turn随后活跃约132秒；错误目标的thread/read返回ephemeral=true且无writer锁。仅2个bridge thread/read，steer/Remote写计数0。
- Immediate task 6 完成：真实thread/read经过原wrapper31325 -> app-server31334，初始唯一实际writer=31334；UI任务正常完成。
- 修复probe改选实际lock owner匹配的active turn；同时下一次wrapper启动会排除ephemeral线程。当前旧运行实例无需重载，probe的owner过滤即生效。

- 聚焦回归通过：check_control.py 的ephemeral helper透传/排除；check_probe.py 的writer目标选择。仅运行这两个检查一次，没有重跑wrapper/protocol全套。
- 准备第二次 bounded probe，只重做只读锚定与第一个尚未发生的steer；不需重载或新建聊天，用户在原聊天开启30秒新turn即可。

- 修复后的启动前只读锚定再次安全中止：metadata cwd在工具执行后变成 /mnt/d/works，而config为 /mnt/d/Works；实际samefile=true，原writer=31334，仍无写请求。该失败不涉及新的人工UI操作。
- 目录边界改用文件系统samefile，而非字符串/盲目lowercase：probe、未来control注册及wrapper capture cwd保持同一实际目录语义。
- store undefined session_id的小编排错误已确认：退出进程没有session ID，不再调用store。

- 目录身份回归3项各运行一次全部通过；没有扩大验证。当前第三次probe已通过真实只读锚定，继续等待原聊天新turn；工具session_id=5826，限时900秒。前两次均无写请求，所以本次steer仍是首个写实验。

- session5826成功结束：steer accepted/applied，同一thread/turn，writer前后为PID31334；用户确认同一VSCode聊天收到并执行，bridge-steer.txt=STEER_OK。Immediate task7完成。
- 同一PID31334的Remote status/ephemeral enable/disable均成功：disabled->connecting->disable响应disabled。紧随的read曾短暂读到connecting；本轮最终只读核查已确认disabled。没有手机pairing，不能宣称Remote手机复用writer成功。Immediate task8的API测试完成。

- 用户确认真实steering已收到并执行：30秒命令exit0，随后STEER_OK。同进程本地可写里程碑已汇报，Immediate task9完成。
- 单独观察native Remote注册：4.09秒内connected、有environmentId，前后PID/writer均31334，finally恢复disabled。证据native-remote-registration.json。
- 最小pairing入口及scripts/pair_remote.py已准备；QR URL依据已安装官方webview，凭据只写私有Linux state。新增wait_remote_status修正disable后的暂态读数。子agent对控制路由与状态等待的离线检查通过。
- 下一人工步骤仅需baseline窗口Reload Window并重开原测试聊天。尚未生成真实配对凭据/扫码，未实现MCP。
- 子agent的check_pair_remote.py四组离线检查通过：私有QR权限、无凭据泄漏、保存PID/thread严格复用、失败恢复与writer变更拒绝。未启动真实Codex或重复live steer。
- 已更新live-probe.json的UI确认与finalVerifiedStatus，不抹除原即时connecting结果。Rust tag具体源码路径404，当前结论以bundled生成schemas和真实RPC为准。
