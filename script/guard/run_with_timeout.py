#!/usr/bin/env python3
"""把**一次命令执行**套上可判定的时限（跨平台、纯 stdlib），使"卡死"变成一次可继续的失败。

要治的失效
----------
任务"频繁中断"里最常见的一种不是命令失败，而是**命令不返回**：没有进度输出、工具层也不给
失败信号，于是整轮停在那里直到人工介入——现场一清理，前面的成果全丢，下次从零重来。

判据（`specs/general/collab.adoc`「操作超时与超时后的处置」）要求的是：**每一次操作自带可判定
的时限**、到点后**先排查**、**再换手段继续**、**不得把超时未完成的操作写成已完成**。
本文件把前半段做成可执行的抓手——把命令跑起来、盯着墙钟，到点**终止该次执行**并把
**已产出的输出**一并带出（那是排查"它停在哪一步"的直接证据）。

用法
----
    python3 script/guard/run_with_timeout.py --timeout 600 -- <命令> [参数...]
    python3 script/guard/run_with_timeout.py --timeout 600 --stdout 文件 -- mvn -B test
    timeout 600 python3 script/guard/run_with_timeout.py -- <命令>   # 双保险

退出码：命令自身的退出码原样透传；超时为 **124**（与 GNU `timeout` 同值，便于脚本判定）；
用法错误为 2。**超时不是"跳过该步"的许可**：调用方须按规范先排查、再换手段继续。

为什么用 Python 而不是 `timeout`/`gtimeout`
-------------------------------------------
`timeout` 是 GNU coreutils 的、macOS 上默认没有（只有装了 coreutils 才有 `gtimeout`），
而本集合的脚本一律按 `python3` 跑（见 `specs/stack/python.adoc`）——取本机已有的解释器，
不为一个时限再引入一个环境前提（判据同 `specs/general/ci-cd.adoc`「校验链完整」）。
"""

import argparse
import os
import signal
import subprocess
import sys
import threading
import time

TIMEOUT_EXIT_CODE = 124


def _reader(stream, sink, lock, max_bytes):
    """后台读线程：把子进程输出**边产边落盘**——超时终止时已产出的输出才是排查依据。"""
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            with lock:
                if sink is not None:
                    sink.write(chunk)
                    sink.flush()
    except (ValueError, OSError):
        pass
    finally:
        try:
            stream.close()
        except OSError:
            pass


def _terminate(proc, grace=5.0):
    """先请它自己退，宽限期后强杀（进程组一并杀，避免留下孤儿占着管道）。"""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if proc.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), sig)
            else:  # Windows 没有进程组信号，退化为 terminate/kill
                proc.kill() if sig is signal.SIGKILL else proc.terminate()
        except (ProcessLookupError, PermissionError, OSError):
            pass
        deadline = time.time() + grace
        while time.time() < deadline and proc.poll() is None:
            time.sleep(0.05)


def run(command, timeout, stdout_path=None, quiet=False):
    """跑一条命令并盯时限；返回退出码（超时为 `TIMEOUT_EXIT_CODE`）。"""
    sink = open(stdout_path, "wb") if stdout_path else None
    lock = threading.Lock()
    extra = {}
    if os.name == "posix":
        extra["start_new_session"] = True  # 让整棵进程树可被一并终止
    try:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, **extra)
    except FileNotFoundError as exc:
        print("命令不存在：%s（%s）" % (command[0], exc), file=sys.stderr)
        if sink:
            sink.close()
        return 127
    threads = []
    for stream in filter(None, [proc.stdout]):
        t = threading.Thread(target=_reader, args=(stream, sink, lock, 0), daemon=True)
        t.start()
        threads.append(t)

    start = time.time()
    timed_out = False
    while True:
        if proc.poll() is not None:
            break
        if timeout and (time.time() - start) >= timeout:
            timed_out = True
            _terminate(proc)
            break
        time.sleep(0.1)
    for t in threads:
        t.join(timeout=2.0)
    elapsed = time.time() - start
    if sink:
        sink.close()

    if timed_out:
        print("TIMEOUT 命令超过 %.1f 秒仍未返回，已终止（时限 %.1f 秒）：%s"
              % (elapsed, timeout, " ".join(command)), file=sys.stderr)
        print("  已产出的输出见 %s" % (stdout_path or "标准输出（与命令输出同流）"), file=sys.stderr)
        print("  处置：按 specs/general/collab.adoc「操作超时与超时后的处置」先排查、再换手段继续；"
              "不得把超时未完成的操作写成已完成", file=sys.stderr)
        return TIMEOUT_EXIT_CODE
    if not quiet:
        print("用时 %.1fs，退出码 %s" % (elapsed, proc.returncode))
    return proc.returncode


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="给一次命令执行套上可判定的时限（跨平台、纯 stdlib）")
    parser.add_argument("--timeout", type=float, default=None,
                        help="时限（秒）；缺省取环境变量 OPERATION_TIMEOUT，再缺省 600")
    parser.add_argument("--stdout", default=None, help="把子进程输出同时落盘到该文件")
    parser.add_argument("--quiet", action="store_true", help="只在超时/出错时输出")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="命令与参数（放在 `--` 之后）")
    args = parser.parse_args(argv)

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("用法错误：没有给出要跑的命令（写成 `-- <命令> [参数...]`）", file=sys.stderr)
        return 2
    timeout = args.timeout
    if timeout is None:
        env_value = os.environ.get("OPERATION_TIMEOUT")
        try:
            timeout = float(env_value) if env_value else 600.0
        except ValueError:
            print("环境变量 OPERATION_TIMEOUT 不是数值：%r" % env_value, file=sys.stderr)
            return 2
    if timeout <= 0:
        print("时限须为正数：%s" % timeout, file=sys.stderr)
        return 2
    return run(command, timeout, args.stdout, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
