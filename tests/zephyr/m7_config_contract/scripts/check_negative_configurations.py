#!/usr/bin/env python3
"""! @brief M7 Devicetree 구성 오류가 의도한 진단으로 실패하는지 검증합니다. """

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence


BOARD = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
CASE_NAMES = (
    "missing-wire-chosen",
    "non-spi00-chosen",
    "spi00-uart00-conflict",
)


@dataclass(frozen=True)
class NegativeCase:
    """! @brief expected-fail build 한 건의 입력과 진단 계약입니다. """

    name: str
    sample: Path
    overlay: Path
    expected_diagnostics: tuple[str, ...]


## @brief 재현 환경별 경로 인자를 해석합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    script = Path(__file__).resolve()
    default_core_root = script.parents[4]
    default_zephyr_base = Path(os.environ.get("ZEPHYR_BASE", "C:/ncs/v3.4.0/zephyr"))

    parser = argparse.ArgumentParser()
    parser.add_argument("--core-root", type=Path, default=default_core_root)
    parser.add_argument("--zephyr-base", type=Path, default=default_zephyr_base)
    parser.add_argument("--board-root", type=Path)
    parser.add_argument("--build-root", type=Path)
    parser.add_argument("--cases", nargs="+", choices=CASE_NAMES, default=CASE_NAMES)
    return parser.parse_args(arguments)


## @brief PATH의 west launcher를 찾습니다.
def west_command() -> list[str]:
    west = shutil.which("west")
    if west is not None:
        return [west]
    if importlib.util.find_spec("west") is not None:
        return [sys.executable, "-m", "west"]
    raise RuntimeError("PATH와 현재 Python에서 west를 찾을 수 없습니다.")


## @brief 하나의 expected-fail build를 실행하고 진단 marker를 확인합니다.
def run_case(
    case: NegativeCase,
    *,
    west: Sequence[str],
    core_root: Path,
    zephyr_base: Path,
    board_root: Path,
    build_root: Path,
) -> None:
    build_directory = build_root / case.name
    command = [
        *west,
        "-z",
        zephyr_base.as_posix(),
        "build",
        "--pristine",
        "always",
        "--no-sysbuild",
        "-b",
        BOARD,
        "-s",
        case.sample.as_posix(),
        "-d",
        build_directory.as_posix(),
        "--",
        f"-DBOARD_ROOT={board_root.as_posix()}",
        f"-DEXTRA_ZEPHYR_MODULES={core_root.as_posix()}",
        f"-DEXTRA_DTC_OVERLAY_FILE={case.overlay.as_posix()}",
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
        raise RuntimeError(f"{case.name} build가 예상과 달리 성공했습니다.")

    normalized_output = " ".join(result.stdout.split())
    if not any(marker in normalized_output for marker in case.expected_diagnostics):
        expected = " / ".join(case.expected_diagnostics)
        raise RuntimeError(f"{case.name} build에 예상 진단이 없습니다: {expected}")
    print(f"EXPECTED FAILURE PASS: {case.name}")


## @brief M7 negative Devicetree 구성을 독립 build로 모두 검증합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parsed = parse_arguments(arguments)
    core_root = parsed.core_root.resolve()
    zephyr_base = parsed.zephyr_base.resolve()
    board_root = (
        parsed.board_root.resolve()
        if parsed.board_root
        else core_root / "board_package" / "NU54DK_Zephyr_DTS"
    )
    build_root = (
        parsed.build_root.resolve()
        if parsed.build_root
        else core_root / "build" / "m7-negative-config-auto"
    )
    negative_root = core_root / "tests" / "zephyr" / "m7_config_contract" / "negative"
    cases = (
        NegativeCase(
            name="missing-wire-chosen",
            sample=core_root / "samples" / "zephyr" / "wire_pmic_id",
            overlay=negative_root / "missing_wire_chosen.overlay",
            expected_diagnostics=(
                "NUCODE_M7_WIRE_CHOSEN_REQUIRED",
            ),
        ),
        NegativeCase(
            name="non-spi00-chosen",
            sample=core_root / "samples" / "zephyr" / "spi_transaction",
            overlay=negative_root / "non_spi00_chosen.overlay",
            expected_diagnostics=(
                "NUCODE_M7_SPI_CHOSEN_MUST_BE_SPI00",
            ),
        ),
        NegativeCase(
            name="spi00-uart00-conflict",
            sample=core_root / "samples" / "zephyr" / "spi_transaction",
            overlay=negative_root / "spi00_uart00_conflict.overlay",
            expected_diagnostics=(
                "NUCODE_M7_SPI_UART00_CONFLICT",
                "Only one of the following peripherals can be enabled:",
            ),
        ),
    )

    for path in (core_root, zephyr_base, board_root):
        if not path.exists():
            raise RuntimeError(f"필수 경로가 없습니다: {path}")
    selected_cases = tuple(case for case in cases if case.name in parsed.cases)
    for case in selected_cases:
        if not case.sample.is_dir() or not case.overlay.is_file():
            raise RuntimeError(f"negative fixture가 없습니다: {case.name}")

    west = west_command()
    for case in selected_cases:
        run_case(
            case,
            west=west,
            core_root=core_root,
            zephyr_base=zephyr_base,
            board_root=board_root,
            build_root=build_root,
        )
    print(
        "PASS: M7 negative configuration "
        f"{len(selected_cases)}/{len(selected_cases)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"EXPECTED FAILURE ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
