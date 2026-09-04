#!/usr/bin/env python3
"""! @brief GitHub-hosted M12 software gate를 로컬과 CI에서 동일하게 실행합니다. """

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable, Sequence
from urllib.parse import unquote


REPOSITORY = Path(__file__).resolve().parents[2]
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))")


class GateFailure(RuntimeError):
    """! @brief M12 software gate 실패를 나타냅니다. """


## @brief command를 shell 없이 실행하고 실패를 gate 오류로 바꿉니다.
def run_checked(command: Sequence[str | Path]) -> None:
    normalized = [str(item) for item in command]
    print(f"[M12] exec: {subprocess.list2cmdline(normalized)}", flush=True)
    result = subprocess.run(normalized, cwd=REPOSITORY, check=False)
    if result.returncode != 0:
        raise GateFailure(
            f"명령이 종료 코드 {result.returncode}로 실패했습니다: "
            f"{subprocess.list2cmdline(normalized)}"
        )


## @brief 지정 디렉터리에서 unittest pattern 하나를 실행합니다.
def run_unittest(directory: Path, pattern: str) -> None:
    run_checked(
        (
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-v",
            "-s",
            directory,
            "-p",
            pattern,
        )
    )


## @brief package 전용 suite를 제외한 host와 AC-03 HIL runner unit suite를 실행합니다.
def run_host_gate() -> None:
    test_root = REPOSITORY / "tests" / "host"
    files = sorted(test_root.glob("test_*.py"))
    selected = [path for path in files if path.name != "test_m10_packaging.py"]
    if not selected:
        raise GateFailure("실행할 host unit test가 없습니다.")
    for path in selected:
        run_unittest(test_root, path.name)
    run_unittest(
        REPOSITORY / "tests" / "hil" / "nu54dk",
        "test_ac03_storage.py",
    )
    run_unittest(
        REPOSITORY / "tests" / "hil" / "nu54dk",
        "test_m24_uarte_onboard.py",
    )
    run_unittest(
        REPOSITORY / "tests" / "hil" / "nu54dk",
        "test_m24_twim_onboard.py",
    )
    run_unittest(
        REPOSITORY / "tests" / "hil" / "nu54dk",
        "test_m25_onboard.py",
    )


## @brief 재현 package 생성·검증 suite만 별도로 실행합니다.
def run_package_gate() -> None:
    run_unittest(REPOSITORY / "tests" / "host", "test_m10_packaging.py")


## @brief Git이 추적하거나 새로 추가할 Markdown 파일 목록을 반환합니다.
def tracked_markdown_files() -> Iterable[Path]:
    result = subprocess.run(
        (
            "git",
            "-c",
            "core.quotepath=false",
            "-C",
            str(REPOSITORY),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "*.md",
        ),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise GateFailure("Git에서 Markdown 파일 목록을 읽지 못했습니다.")
    for line in result.stdout.split("\0"):
        if line:
            yield REPOSITORY / Path(line)


## @brief Markdown UTF-8과 저장소 내부 상대 link의 존재를 검사합니다.
def run_docs_gate() -> None:
    checked = 0
    failures: list[str] = []
    repository = REPOSITORY.resolve()
    for path in tracked_markdown_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            failures.append(f"{path.relative_to(REPOSITORY)}: UTF-8 read 실패: {error}")
            continue
        checked += 1
        for match in LINK_PATTERN.finditer(text):
            raw_target = match.group(1) or match.group(2) or ""
            target = unquote(raw_target.split("#", 1)[0].split("?", 1)[0])
            if not target or re.match(r"^(?:https?|mailto):", target, re.IGNORECASE):
                continue
            if target.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", target):
                continue
            candidate = (path.parent / target).resolve()
            if not candidate.is_relative_to(repository):
                failures.append(
                    f"{path.relative_to(REPOSITORY)}: 저장소 밖 link: {raw_target}"
                )
            elif not candidate.exists():
                failures.append(
                    f"{path.relative_to(REPOSITORY)}: 없는 local link: {raw_target}"
                )
    if checked == 0:
        failures.append("검사할 Markdown 파일이 없습니다.")
    if failures:
        raise GateFailure("Markdown 검사 실패:\n" + "\n".join(failures))
    print(f"[M12] Markdown UTF-8/local-link PASS: {checked} files")


## @brief Arduino CLI가 표준 library 예제 전체를 열거하는지 검사합니다.
def run_examples_gate(cli: Path) -> None:
    run_checked(
        (
            sys.executable,
            REPOSITORY / "tests" / "arduino-cli" / "run_smoke.py",
            "--cli",
            cli.resolve(),
            "--tests",
            "examples",
        )
    )


## @brief CI lock과 workflow fail-closed 계약 test를 실행합니다.
def run_contract_gate() -> None:
    run_unittest(REPOSITORY / "tests" / "ci", "test_*.py")


## @brief M23 inventory와 M24 serial-fabric route/API 계약을 검사합니다.
def run_inventory_gate() -> None:
    run_checked(
        (
            sys.executable,
            REPOSITORY / "tools" / "peripheral" / "verify_m23_inventory.py",
        )
    )
    run_checked(
        (
            sys.executable,
            REPOSITORY / "tools" / "peripheral" / "verify_m24_serial_contract.py",
        )
    )


## @brief 선택한 software gate만 실행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "gate", choices=("contract", "inventory", "host", "docs", "package", "examples")
    )
    parser.add_argument("--arduino-cli", type=Path)
    args = parser.parse_args(arguments)
    if args.gate == "contract":
        run_contract_gate()
    elif args.gate == "inventory":
        run_inventory_gate()
    elif args.gate == "host":
        run_host_gate()
    elif args.gate == "docs":
        run_docs_gate()
    elif args.gate == "package":
        run_package_gate()
    elif args.gate == "examples":
        if args.arduino_cli is None or not args.arduino_cli.is_file():
            raise GateFailure("examples gate에는 exact Arduino CLI 경로가 필요합니다.")
        run_examples_gate(args.arduino_cli)
    else:
        raise GateFailure(f"지원하지 않는 gate입니다: {args.gate}")
    print(f"M12_GATE_PASS={args.gate}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateFailure as error:
        print(f"M12_GATE_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
