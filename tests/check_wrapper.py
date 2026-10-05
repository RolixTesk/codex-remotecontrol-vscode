#!/usr/bin/env python3
"""Run isolated wrapper checks with a fake child; no real Codex or VS Code."""

import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time


FAKE_CHILD = r'''#!/usr/bin/env python3
import json
import os
import signal
import sys
from pathlib import Path

Path(os.environ["CHECK_REPORT"]).write_text(json.dumps({
    "argv": sys.argv[1:], "cwd": os.getcwd(), "pid": os.getpid(),
    "environment": os.environ["CHECK_VALUE"],
}))

def write_all(fd, data):
    while data:
        data = data[os.write(fd, data):]

mode = os.environ["CHECK_MODE"]
if mode in ("signal", "signal-default"):
    def stop(signum, frame):
        write_all(2, b"received SIGTERM\n")
        sys.exit(29)
    if mode == "signal":
        signal.signal(signal.SIGTERM, stop)
    write_all(1, b"READY\n")
    while True:
        signal.pause()
elif mode == "stream":
    while data := os.read(0, 4096):
        write_all(1, data)
else:
    data = sys.stdin.buffer.read()
    write_all(1, b"\x00\xffheader\r\n" + data + bytes(range(256)) * 1024)
    write_all(2, b"stderr only\x00\xfe\n")
    sys.exit(23 if mode == "nonzero" else 0)
'''


def read_exact(pipe, length):
    """Require output before stdin closes; fail instead of blocking forever."""
    data = b""
    deadline = time.monotonic() + 5
    while len(data) < length:
        remaining = deadline - time.monotonic()
        assert remaining > 0, "stdout did not stream while stdin remained open"
        assert select.select([pipe], [], [], remaining)[0], "stdout streaming timeout"
        chunk = os.read(pipe.fileno(), length - len(data))
        assert chunk, "unexpected stdout EOF"
        data += chunk
    return data


def main():
    source = Path(__file__).resolve().parents[1] / "wrapper" / "codex-wrapper"
    with tempfile.TemporaryDirectory(prefix="codex-wrapper-check-") as temp:
        root = Path(temp)
        wrapper = root / "codex-wrapper"
        shutil.copyfile(source, wrapper)
        wrapper.chmod(0o700)
        child = root / "fake-codex"
        child.write_text(FAKE_CHILD)
        child.chmod(0o700)
        capture_cwd = root / "workspace"
        capture_cwd.mkdir()
        capture_alias = root / "workspace-alias"
        capture_alias.symlink_to(capture_cwd, target_is_directory=True)
        other_cwd = root / "other"
        other_cwd.mkdir()

        def start(name, mode="normal", argv=None, cwd=None, capture_scope=None):
            capture = root / name
            report = root / f"{name}-report.json"
            wrapper.with_suffix(".local.json").write_text(json.dumps({
                "realExecutable": str(child), "captureCwd": str(capture_scope or capture_cwd),
                "captureRoot": str(capture),
            }))
            env = dict(os.environ, CHECK_MODE=mode, CHECK_REPORT=str(report),
                       CHECK_VALUE="spaces / unicode 测试 / $literal")
            process = subprocess.Popen(
                [str(wrapper), *(argv or ["app-server", "--literal=spaces here", "测试"])],
                cwd=cwd or capture_cwd, env=env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            return process, capture, report

        def verify_capture(capture, process, stdin, stdout, code):
            runs = list(capture.iterdir())
            assert len(runs) == 1, "expected exactly one capture directory"
            run = runs[0]
            assert (run / "stdin.bin").read_bytes() == stdin, "stdin capture differs"
            assert (run / "stdout.bin").read_bytes() == stdout, "stdout capture differs"
            metadata = json.loads((run / "process.json").read_text())
            assert metadata["wrapperPid"] == process.pid
            assert metadata["exitCode"] == code
            assert metadata["captureErrors"] == []
            assert "transportError" not in metadata
            assert run.stat().st_mode & 0o777 == 0o700
            assert all(path.stat().st_mode & 0o777 == 0o600 for path in run.iterdir())

        payload = bytes(range(256)) * 1024 + b"\r\npartial frame\x00\xff"
        expected = b"\x00\xffheader\r\n" + payload + bytes(range(256)) * 1024
        for name, mode, code, scope in [
            ("normal", "normal", 0, capture_cwd), ("nonzero", "nonzero", 23, capture_cwd),
            ("alias-scope", "normal", 0, capture_alias),
        ]:
            process, capture, report = start(name, mode, capture_scope=scope)
            try:
                stdout, stderr = process.communicate(payload, timeout=10)
                assert process.returncode == code
                assert stdout == expected, "stdout was not byte-for-byte transparent"
                assert stderr == b"stderr only\x00\xfe\n", "stderr mixed with stdout"
                details = json.loads(report.read_text())
                assert details["argv"] == ["app-server", "--literal=spaces here", "测试"]
                assert details["cwd"] == str(capture_cwd)
                assert details["environment"] == "spaces / unicode 测试 / $literal"
                assert details["pid"] != process.pid, "capture branch did not launch child"
                verify_capture(capture, process, payload, stdout, code)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        print("PASS argv/environment/cwd, binary stdout, stderr separation, capture, EOF, exit 23")
        print("PASS captureCwd symlink alias captures the same workspace")

        process, capture, _ = start("stream", "stream")
        streamed = b""
        try:
            for chunk in [bytes(range(256)) * 16, b"\x00\xff\r\n" * 1024]:
                process.stdin.write(chunk)
                process.stdin.flush()
                assert read_exact(process.stdout, len(chunk)) == chunk
                streamed += chunk
                assert process.poll() is None, "stream child exited before stdin EOF"
            process.stdin.close()
            process.stdin = None
            remaining, stderr = process.communicate(timeout=10)
            assert remaining == b"" and stderr == b"" and process.returncode == 0
            verify_capture(capture, process, streamed, streamed, 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        print("PASS interactive binary streaming while stdin remains open")

        for mode, code, expected_stderr in [
            ("signal", 29, b"received SIGTERM\n"),
            ("signal-default", -signal.SIGTERM, b""),
        ]:
            process, capture, _ = start(mode, mode)
            try:
                assert read_exact(process.stdout, 6) == b"READY\n"
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=10)
                assert process.returncode == code, "child SIGTERM exit was not preserved"
                assert stdout == b"" and stderr == expected_stderr
                verify_capture(capture, process, b"", b"READY\n", code)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        print("PASS SIGTERM forwarding, handler exit 29 and default signal exit -15")

        for name, argv, cwd, scope in [
            ("other-cwd", ["app-server"], other_cwd, capture_cwd),
            ("non-app-server", ["--version"], capture_cwd, capture_cwd),
            ("missing-scope", ["app-server"], capture_cwd, root / "missing-workspace"),
        ]:
            process, capture, report = start(name, argv=argv, cwd=cwd, capture_scope=scope)
            try:
                stdout, stderr = process.communicate(payload, timeout=10)
                assert process.returncode == 0 and stdout == expected
                assert stderr == b"stderr only\x00\xfe\n"
                details = json.loads(report.read_text())
                assert details["pid"] == process.pid, "fallback did not exec real executable"
                assert details["argv"] == argv and details["cwd"] == str(cwd)
                assert not capture.exists(), "fallback unexpectedly captured traffic"
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
        print("PASS outside/missing capture cwd and non-app-server exec without capture")


if __name__ == "__main__":
    main()
