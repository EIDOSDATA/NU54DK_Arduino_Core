#!/usr/bin/env python3
"""! @brief Arduino CLI M8 pyOCD/J-Link upload를 실제 NU54DK에서 반복 검증합니다. """

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Sequence


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


FQBN = "nucode:zephyr:nu54dk"
READY_TOKEN = b"NUCODE_M8_UPLOAD_READY"


class UploadHilFailure(RuntimeError):
    """! @brief M8 실제 upload 계약 위반을 나타냅니다. """


## @brief Arduino IDE에 포함된 CLI 기본 경로를 반환합니다.
def default_cli() -> Path:
    return Path("C:/Program Files/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe")


## @brief 명령을 실행하고 출력 및 종료 code를 보존합니다.
def run(command: Sequence[str | Path]) -> tuple[int, str, float]:
    started = time.monotonic()
    result = subprocess.run(
        [str(value) for value in command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    elapsed = time.monotonic() - started
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    return result.returncode, result.stdout, elapsed


## @brief repository를 격리된 Arduino hardware package로 복사합니다.
def stage_platform(repository: Path, user_root: Path) -> Path:
    platform = user_root / "hardware" / "nucode" / "zephyr"
    platform.mkdir(parents=True)
    for name in ("boards.txt", "platform.txt", "LICENSE"):
        shutil.copy2(repository / name, platform / name)
    for name in (
        "board_package",
        "cores",
        "dts",
        "libraries",
        "third_party",
        "tools",
        "variants",
        "zephyr",
    ):
        shutil.copytree(
            repository / name,
            platform / name,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
    return platform


## @brief 파일 SHA-256을 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


## @brief reset 후 NU54DK UART에서 고정 생존 표식을 기다립니다.
def wait_for_ready(port: str, timeout_seconds: float) -> bytes:
    try:
        import serial
    except ImportError as error:
        raise UploadHilFailure("pyserial이 없어 UART reset 표식을 확인할 수 없습니다.") from error
    deadline = time.monotonic() + timeout_seconds
    transcript = bytearray()
    with serial.Serial(port=port, baudrate=115200, timeout=0.25) as stream:
        stream.reset_input_buffer()
        while time.monotonic() < deadline:
            block = stream.read(512)
            if block:
                transcript.extend(block)
                if READY_TOKEN in transcript:
                    return bytes(transcript)
    raise UploadHilFailure(
        f"{port}에서 upload 후 reset 표식을 받지 못했습니다: {bytes(transcript)!r}"
    )


## @brief 실행 인자를 구성합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    repository = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, default=default_cli())
    parser.add_argument("--repository", type=Path, default=repository)
    parser.add_argument("--workspace", type=Path, default=repository / "build" / "m8-upload-hil")
    parser.add_argument("--runner", choices=("pyocd", "jlink"), default="pyocd")
    parser.add_argument("--probe-id")
    parser.add_argument("--serial-port", default="COM10")
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--uart-timeout", type=float, default=6.0)
    parser.add_argument("--settle-seconds", type=float, default=2.0)
    parser.add_argument("--uart-each", action="store_true")
    return parser.parse_args(arguments)


## @brief Arduino CLI build와 실제 반복 upload HIL을 수행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if args.repetitions < 1:
        raise UploadHilFailure("반복 횟수는 1 이상이어야 합니다.")
    if args.runner == "jlink" and not (args.probe_id or "").strip():
        raise UploadHilFailure("J-Link HIL에는 --probe-id serial이 필요합니다.")
    repository = args.repository.resolve()
    cli = args.cli.resolve()
    sketch = repository / "tests" / "arduino-cli" / "m8_upload"
    if not cli.is_file() or not (sketch / "m8_upload.ino").is_file():
        raise UploadHilFailure("Arduino CLI 또는 M8 upload sketch를 찾지 못했습니다.")

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_root = args.workspace.resolve() / timestamp
    user_root = run_root / "user"
    build_path = run_root / "build"
    run_root.mkdir(parents=True)
    stage_platform(repository, user_root)
    config = run_root / "arduino-cli.yaml"
    config.write_text(f"directories:\n  user: {user_root.as_posix()}\n", encoding="utf-8")

    compile_command: list[str | Path] = [
        cli,
        "compile",
        "--fqbn",
        FQBN,
        "--config-file",
        config,
        "--build-path",
        build_path,
        "--board-options",
        f"upload_probe={args.runner}",
        sketch,
    ]
    return_code, _, compile_seconds = run(compile_command)
    if return_code != 0:
        raise UploadHilFailure(f"Arduino CLI compile이 종료 코드 {return_code}로 실패했습니다.")

    manifest_path = build_path / "m8_upload.ino.nu54-build.json"
    if not manifest_path.is_file():
        raise UploadHilFailure(f"M8 build manifest가 없습니다: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hex_path = Path(manifest["artifacts"]["hex"]["path"])
    hex_sha256 = file_sha256(hex_path)
    upload_results: list[dict[str, object]] = []
    for sequence in range(1, args.repetitions + 1):
        upload_command: list[str | Path] = [
            cli,
            "upload",
            "--fqbn",
            FQBN,
            "--config-file",
            config,
            "--build-path",
            build_path,
            "--board-options",
            f"upload_probe={args.runner}",
        ]
        if args.runner == "jlink":
            upload_command.extend(("--upload-field", f"probe_id={args.probe_id}"))
        upload_command.append(sketch)
        print(f"NUCODE_M8_UPLOAD_ATTEMPT:{sequence}/{args.repetitions}")
        return_code, output, upload_seconds = run(upload_command)
        if return_code != 0 or "NU54_UPLOAD_PASS" not in output:
            raise UploadHilFailure(
                f"Arduino CLI upload {sequence}회차가 종료 코드 {return_code}로 실패했습니다."
            )
        verify_uart = args.uart_each or sequence == args.repetitions
        transcript = wait_for_ready(args.serial_port, args.uart_timeout) if verify_uart else b""
        upload_results.append(
            {
                "sequence": sequence,
                "upload_seconds": round(upload_seconds, 3),
                "uart_checked": verify_uart,
                "uart_ready": READY_TOKEN in transcript if verify_uart else None,
            }
        )
        print(f"NUCODE_M8_UPLOAD_ATTEMPT_PASS:{sequence}/{args.repetitions}")
        if sequence != args.repetitions and args.settle_seconds > 0.0:
            time.sleep(args.settle_seconds)

    summary = {
        "schema_version": 1,
        "runner": args.runner,
        "probe_id": args.probe_id if args.runner == "jlink" else "auto-single",
        "serial_port": args.serial_port,
        "repetitions": args.repetitions,
        "compile_seconds": round(compile_seconds, 3),
        "hex_path": hex_path.as_posix(),
        "hex_sha256": hex_sha256,
        "mass_erase_requested": False,
        "recover_requested": False,
        "uploads": upload_results,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    summary_path = run_root / "m8-upload-result.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"M8_UPLOAD_HIL_PASS runner={args.runner} repetitions={args.repetitions} "
        f"hex_sha256={hex_sha256} result={summary_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UploadHilFailure as error:
        print(f"M8_UPLOAD_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
