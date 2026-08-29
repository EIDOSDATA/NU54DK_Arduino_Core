#!/usr/bin/env python3
"""! @brief M12의 대표 Zephyr target suite를 build-only로 실행합니다. """

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = Path(__file__).resolve().parent
LOCK_MODULE_PATH = SCRIPT_ROOT / "verify_ci_lock.py"
SPEC = importlib.util.spec_from_file_location("nu54_m12_lock", LOCK_MODULE_PATH)
assert SPEC and SPEC.loader
LOCK_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCK_MODULE)
BOARD_TARGET = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
SUITES = (
    ("m3_runtime", "nucode.m3.runtime"),
    ("m4_api_contract", "nucode.m4.api_contract"),
    ("m6_core_api", "nucode.m6.core_api"),
    ("m7_core_api", "nucode.m7.core_api"),
    ("m14_core_contract", "nucode.m14.core_contract"),
    ("m14_variant_contract", "nucode.m14.variant_contract"),
    ("m14_pin_hil", "nucode.m14.pin_hil"),
    ("m15_board", "nucode.m15.board"),
    ("m15_hil", "nucode.m15.auto_hil"),
    ("m15_wake", "nucode.m15.wake"),
)
WINDOWS_OUTDIR_MAX_LENGTH = 32


class BuildFailure(RuntimeError):
    """! @brief 대표 Zephyr build 계약 실패를 나타냅니다. """


## @brief Windows 도구의 MAX_PATH 영향을 피할 수 있는 짧은 출력 경로인지 검사합니다.
def validate_outdir_path(outdir: Path) -> None:
    if os.name == "nt" and len(str(outdir)) > WINDOWS_OUTDIR_MAX_LENGTH:
        raise BuildFailure(
            "Windows Twister outdir가 너무 깁니다. "
            f"{WINDOWS_OUTDIR_MAX_LENGTH}자 이하의 짧은 절대 경로를 사용하십시오: "
            r"예: C:\t\m12"
        )


## @brief Twister 결과가 정확한 build-only suite 집합인지 검사합니다.
def validate_report(report_path: Path) -> None:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BuildFailure(f"Twister 결과를 읽지 못했습니다: {error}") from error
    suites = report.get("testsuites")
    if not isinstance(suites, list):
        raise BuildFailure("Twister testsuites가 배열이 아닙니다.")
    expected = {scenario for _directory, scenario in SUITES}
    actual: set[str] = set()
    for suite in suites:
        if not isinstance(suite, dict):
            raise BuildFailure("Twister suite record가 object가 아닙니다.")
        name = suite.get("name")
        if not isinstance(name, str) or name in actual:
            raise BuildFailure("Twister suite 이름이 없거나 중복됩니다.")
        actual.add(name)
        if (
            suite.get("platform") != BOARD_TARGET
            or suite.get("status") != "not run"
            or any(
                not isinstance(testcase, dict)
                or testcase.get("status") != "not run"
                or testcase.get("reason") != "Test was built only"
                for testcase in suite.get("testcases", [])
            )
        ):
            raise BuildFailure(f"Twister build-only 결과가 PASS가 아닙니다: {name}")
    if actual != expected:
        raise BuildFailure(f"Twister suite 집합이 다릅니다: {sorted(actual)}")


## @brief exact NCS workspace에서 고정된 target suite만 빌드합니다.
def run_build(workspace: Path, outdir: Path, lock: dict[str, Any]) -> None:
    LOCK_MODULE.validate_workspace(workspace, lock)
    validate_outdir_path(outdir)
    if outdir.exists():
        raise BuildFailure(f"Twister outdir는 실행 전에 없어야 합니다: {outdir}")
    board_root = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
    if LOCK_MODULE.git_revision(board_root) != lock["board"]["revision"]:
        raise BuildFailure("checkout된 board submodule이 M12 lock과 다릅니다.")
    command: list[str | Path] = [sys.executable, workspace / "zephyr" / "scripts" / "twister"]
    for directory, _scenario in SUITES:
        command.extend(("--testsuite-root", REPOSITORY / "tests" / "zephyr" / directory))
    command.extend(
        (
            "--platform",
            BOARD_TARGET,
            "--board-root",
            board_root / "boards",
            "--build-only",
            "--ninja",
            "--detailed-test-id",
            "--jobs",
            "2",
            "--outdir",
            outdir,
            "--extra-args",
            f"BOARD_ROOT={board_root.as_posix()}",
            "--extra-args",
            f"EXTRA_ZEPHYR_MODULES={REPOSITORY.as_posix()}",
            "--extra-args",
            "USE_CCACHE=0",
        )
    )
    for _directory, scenario in SUITES:
        command.extend(("--scenario", scenario))
    environment = dict(os.environ)
    environment["ZEPHYR_BASE"] = str(workspace / "zephyr")
    print(f"[M12-ZEPHYR] exec: {subprocess.list2cmdline([str(item) for item in command])}")
    result = subprocess.run(command, cwd=workspace, env=environment, check=False)
    if result.returncode != 0:
        raise BuildFailure(f"Twister가 종료 코드 {result.returncode}로 실패했습니다.")
    validate_report(outdir / "twister.json")


## @brief 대표 Zephyr build를 실행하고 고정 identity evidence를 기록합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=SCRIPT_ROOT / "ncs-3.4.0.lock.json")
    args = parser.parse_args(arguments)
    lock = LOCK_MODULE.strict_json_object(args.lock.resolve())
    LOCK_MODULE.validate_lock(lock)
    workspace = args.workspace.resolve()
    outdir = args.outdir.resolve()
    outdir.parent.mkdir(parents=True, exist_ok=True)
    run_build(workspace, outdir, lock)
    evidence = {
        "schema_version": 1,
        "gate": "m12-zephyr-build-only",
        "status": "passed",
        "board": BOARD_TARGET,
        "scenarios": [scenario for _directory, scenario in SUITES],
        "ncs_revision": lock["ncs"]["revision"],
        "zephyr_revision": lock["zephyr"]["revision"],
        "container_digest": lock["linux_toolchain_container"]["digest"],
    }
    (outdir / "m12-build-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"M12_ZEPHYR_BUILD_PASS={len(SUITES)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BuildFailure, LOCK_MODULE.LockFailure) as error:
        print(f"M12_ZEPHYR_BUILD_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
