# Live session bridge — Immediate tasks

日期：2026-10-05。按 agent.md §15 严格顺序执行。

## Phases
1. complete — 检查已安装扩展、配置声明及 app-server 启动方式。
2. complete — 测试会话完成及 writer 拓扑已记录；缺少活跃期间快照，后续 parity 补齐。
3. complete — 实现最小透明 wrapper（仅观察，无注入）。
4. complete — 配置 wrapper 并人工确认与 baseline 行为一致。
5. complete — 捕获协议、脱敏、根据真实帧编写解析检查。
6. complete — 最小本地请求复用；先以 thread/read 检查同一 app-server。
7. complete — 第一个写实验只做当前 disposable turn 的 harmless steer。
8. complete — 同进程内置 Remote status/ephemeral enable，随后恢复 disabled。
9. complete — 已汇报同进程steer及Remote API结果，MCP 暂不实现。
10. pending — 优先验证内置Remote手机路由；若不能复用writer，再实现最小认证MCP。

## Native Remote follow-up
in_progress — 原PID31334的Remote已达到connected并注册环境，恢复disabled。最小pairing入口已实现，等待测试窗口人工reload后生成配对码并验证手机路由。

## Next Step
人工在baseline测试窗口执行Developer: Reload Window并重开原测试聊天；随后代理生成私有配对二维码，人工扫码确认。

## Boundaries
不操作现有生产会话，不启第二个 writer，不删除锁；UI/account 步骤需人工完成。

## Errors Encountered
- 工作目录不是 Git 仓库；记录现状，保留 agent.md，不做 stash/commit。

- Live probe 初次错误：扩展 ephemeral 内部 turn 先于正式 turn 活跃，探针按第一个active条目选择，在writer检查主动中止。仅2个只读请求，无steer/Remote写。改为唯一实际writer归属过滤，不盲目重试。

- 第二个探针启动前错误：Windows挂载目录别名 Works/works 为同一inode，metadata变为小写；按字符串比较的assert误拒绝。改为samefile核对实际目录，不触碰writer。
