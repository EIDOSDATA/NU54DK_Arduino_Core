"""NU54DK led0 alias 누락이 명시적인 compile 오류로 거부되는지 검증합니다."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


EXPECTED_DIAGNOSTIC = "NU54DK Arduino Variant에는 활성화된 led0 alias가 필요합니다."
BOARD = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"


def parse_arguments() -> argparse.Namespace:
    """재현 환경별 경로 인자를 해석합니다."""

    script = Path(__file__).resolve()
    default_core_root = script.parents[4]
    default_zephyr_base = Path(os.environ.get("ZEPHYR_BASE", "C:/ncs/v3.4.0/zephyr"))

    parser = argparse.ArgumentParser()
    parser.add_argument("--core-root", type=Path, default=default_core_root)
    parser.add_argument("--zephyr-base", type=Path, default=default_zephyr_base)
    parser.add_argument("--board-root", type=Path)
    parser.add_argument("--build-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    """expected-fail build를 실행하고 진단 문구까지 일치하는지 판정합니다."""

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
        else core_root / "build" / "m3-negative-missing-led0-auto"
    )
    overlay = core_root / "tests" / "zephyr" / "m3_runtime" / "negative" / "missing_led0.overlay"
    sample = core_root / "samples" / "zephyr" / "blink"
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
        f"-DDTC_OVERLAY_FILE={overlay.as_posix()}",
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
        raise RuntimeError("led0 누락 build가 예상과 달리 성공했습니다.")
    if EXPECTED_DIAGNOSTIC not in result.stdout:
        raise RuntimeError("led0 누락 build가 예상 진단 문구 없이 실패했습니다.")

    print("EXPECTED FAILURE PASS: led0 alias 누락을 Variant compile 계약이 거부했습니다.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"EXPECTED FAILURE ERROR: {error}", file=sys.stderr)
        sys.exit(1)
