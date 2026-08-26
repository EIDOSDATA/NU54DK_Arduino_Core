#!/usr/bin/env python3
"""! @brief UART callback 중복 사용이 configure 단계에서 거부되는지 검증합니다. """

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


EXPECTED_DIAGNOSTIC = (
    "Arduino Serial RX cannot share the chosen UART callback with CONFIG_CONSOLE_HANDLER"
)
BOARD = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"


## @brief 재현 환경별 경로 인자를 해석합니다.
def parse_arguments() -> argparse.Namespace:
    script = Path(__file__).resolve()
    default_core_root = script.parents[4]
    default_zephyr_base = Path(os.environ.get("ZEPHYR_BASE", "C:/ncs/v3.4.0/zephyr"))

    parser = argparse.ArgumentParser()
    parser.add_argument("--core-root", type=Path, default=default_core_root)
    parser.add_argument("--zephyr-base", type=Path, default=default_zephyr_base)
    parser.add_argument("--board-root", type=Path)
    parser.add_argument("--build-dir", type=Path)
    return parser.parse_args()


## @brief expected-fail build를 실행하고 Serial 충돌 진단까지 확인합니다.
def main() -> int:
    arguments = parse_arguments()
    core_root = arguments.core_root.resolve()
    zephyr_base = arguments.zephyr_base.resolve()
    board_root = (
        arguments.board_root.resolve()
        if arguments.board_root
        else core_root / "board_package" / "NU54DK_Zephyr_DTS"
    )
    build_directory = (
        arguments.build_dir.resolve()
        if arguments.build_dir
        else core_root / "build" / "m6-negative-serial-conflict-auto"
    )
    conflict_config = (
        core_root
        / "tests"
        / "zephyr"
        / "m6_config_contract"
        / "negative"
        / "serial_callback_conflict.conf"
    )
    sample = core_root / "samples" / "zephyr" / "serial_echo"
    west = shutil.which("west")
    if west is None:
        raise RuntimeError("PATH에서 west를 찾을 수 없습니다.")

    command = [
        west,
        "-z",
        zephyr_base.as_posix(),
        "build",
        "--pristine",
        "always",
        "--no-sysbuild",
        "-b",
        BOARD,
        "-s",
        sample.as_posix(),
        "-d",
        build_directory.as_posix(),
        "--",
        f"-DBOARD_ROOT={board_root.as_posix()}",
        f"-DEXTRA_ZEPHYR_MODULES={core_root.as_posix()}",
        f"-DEXTRA_CONF_FILE={conflict_config.as_posix()}",
    ]

    result = subprocess.run(
        command,
        cwd=zephyr_base.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    print(result.stdout)

    if result.returncode == 0:
        raise RuntimeError("UART callback 충돌 build가 예상과 달리 성공했습니다.")
    normalized_output = " ".join(result.stdout.split())
    if EXPECTED_DIAGNOSTIC not in normalized_output:
        raise RuntimeError("UART callback 충돌 build가 예상 진단 문구 없이 실패했습니다.")

    print("EXPECTED FAILURE PASS: Arduino Serial이 UART callback 중복 사용을 거부했습니다.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"EXPECTED FAILURE ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
