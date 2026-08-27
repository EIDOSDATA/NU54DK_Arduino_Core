#!/usr/bin/env python3
"""! @brief Full Zephyr ELF의 pyOCD source breakpoint를 NU54DK에서 자동 검증합니다. """

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Sequence


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


class DebugHilFailure(RuntimeError):
    """! @brief M8 debugserver 또는 GDB 계약 위반을 나타냅니다. """


## @brief 파일 SHA-256을 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


## @brief probe를 소비하지 않고 GDB server log의 준비 표식을 기다립니다.
def wait_for_server(log_path: Path, process: subprocess.Popen[bytes], timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise DebugHilFailure(f"debugserver가 조기에 종료됐습니다: {process.returncode}")
        if log_path.is_file() and b"GDB server listening on port" in log_path.read_bytes():
            return
        time.sleep(0.1)
    raise DebugHilFailure("debugserver 준비 시간이 초과됐습니다.")


## @brief M8 debug HIL 실행 인자를 구성합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--probe-id", required=True)
    parser.add_argument("--breakpoint", default="setup")
    parser.add_argument("--gdb-port", type=int, default=3333)
    parser.add_argument("--server-timeout", type=float, default=15.0)
    parser.add_argument("--result", type=Path)
    return parser.parse_args(arguments)


## @brief pyOCD debugserver와 batch GDB로 source breakpoint 도달을 검증합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    manifest_path = args.manifest.resolve()
    if not manifest_path.is_file():
        raise DebugHilFailure(f"build manifest가 없습니다: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    context = manifest.get("context", {})
    elf_record = manifest.get("artifacts", {}).get("elf", {})
    elf = Path(str(elf_record.get("path", ""))).resolve()
    if not elf.is_file() or file_sha256(elf) != elf_record.get("sha256"):
        raise DebugHilFailure("Full Zephyr ELF가 없거나 manifest SHA-256과 다릅니다.")

    zephyr_build = Path(str(context.get("zephyr_build_dir", ""))).resolve()
    ncs_root = Path(str(context.get("ncs_root", ""))).resolve()
    toolchain_root = Path(str(context.get("toolchain_root", ""))).resolve()
    west = toolchain_root / "opt" / "bin" / "Scripts" / "west.exe"
    python = toolchain_root / "opt" / "bin" / "python.exe"
    gdb = (
        toolchain_root
        / "opt"
        / "zephyr-sdk"
        / "gnu"
        / "arm-zephyr-eabi"
        / "bin"
        / "arm-zephyr-eabi-gdb.exe"
    )
    for executable in (west, python, gdb):
        if not executable.is_file():
            raise DebugHilFailure(f"debug 실행 파일이 없습니다: {executable}")

    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(
        (
            str(toolchain_root / "opt" / "bin"),
            str(toolchain_root / "opt" / "bin" / "Scripts"),
            str(toolchain_root / "mingw64" / "bin"),
            environment.get("PATH", ""),
        )
    )
    environment["ZEPHYR_BASE"] = str(ncs_root / "zephyr")
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"

    result_path = args.result.resolve() if args.result else manifest_path.parent / "m8-debug-result.json"
    server_log = result_path.with_name("m8-debugserver.log")
    server_log.parent.mkdir(parents=True, exist_ok=True)
    server_command: list[str | Path] = [
        west,
        "-z",
        ncs_root / "zephyr",
        "debugserver",
        "-d",
        zephyr_build,
        "-r",
        "pyocd",
        "--no-rebuild",
        "--dev-id",
        args.probe_id,
        "--gdb-port",
        str(args.gdb_port),
    ]
    with server_log.open("wb") as stream:
        server = subprocess.Popen(
            [str(value) for value in server_command],
            cwd=ncs_root,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_for_server(server_log, server, args.server_timeout)
            gdb_command: list[str | Path] = [
                gdb,
                "-q",
                "-batch",
                elf,
                "-ex",
                "set pagination off",
                "-ex",
                f"target remote localhost:{args.gdb_port}",
                "-ex",
                "monitor reset halt",
                "-ex",
                f"break {args.breakpoint}",
                "-ex",
                "continue",
                "-ex",
                "info breakpoints",
                "-ex",
                "frame",
                "-ex",
                "disconnect",
            ]
            result = subprocess.run(
                [str(value) for value in gdb_command],
                cwd=manifest_path.parent,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=30.0,
            )
        finally:
            server.terminate()
            try:
                server.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5.0)

    print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    expected = f"Breakpoint 1, {args.breakpoint} () at"
    if result.returncode != 0 or expected not in result.stdout:
        raise DebugHilFailure(
            f"GDB source breakpoint가 확인되지 않았습니다: return_code={result.returncode}"
        )
    reset = subprocess.run(
        [str(python), "-m", "pyocd", "reset", "-t", "nrf54l", "-u", args.probe_id],
        cwd=ncs_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if reset.returncode != 0:
        raise DebugHilFailure(f"debug 후 target reset이 실패했습니다: {reset.stdout}")

    summary = {
        "schema_version": 1,
        "runner": "pyocd",
        "probe_id": args.probe_id,
        "gdb_port": args.gdb_port,
        "elf": elf.as_posix(),
        "elf_sha256": file_sha256(elf),
        "breakpoint": args.breakpoint,
        "breakpoint_hit": True,
        "source_line_visible": "m8_upload.ino" in result.stdout,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    result_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"M8_DEBUG_HIL_PASS breakpoint={args.breakpoint} result={result_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DebugHilFailure, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(f"M8_DEBUG_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
