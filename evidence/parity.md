# Official VS Code parity — 2026-10-05

用户确认：

- baseline.txt 读回 BASELINE_OK。
- wrapper-parity.txt 写入、读回 WRAPPER_OK。
- Python 输出 PARITY_RUNNING / PARITY_DONE，退出码 0。
- 无审批。
- 重开窗口无异常。

私有捕获显示两次启动：wrapper 24831 -> app-server 24840；关闭时 SIGHUP 退出（-1）。重开后 wrapper 27549 -> app-server 27558 仍存活。captureErrors 为空；详细 thread 与 writer 归属在协议观察阶段核对。

审批未验证，不能推断 approval relay 可用。此结果覆盖 Windows VS Code host 经 WSL 运行 bundled 0.160.0；不宣称 Windows-native / Remote-WSL 全部兼容。
