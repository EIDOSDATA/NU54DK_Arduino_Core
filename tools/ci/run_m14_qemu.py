#!/usr/bin/env python3
"""! @brief 고정 NCS 환경에서 M14 C++ 정책을 QEMU로 실제 실행합니다. """

from __future__ import annotations

import argparse
import hashlib
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
SPEC = importlib.util.spec_from_file_location("nu54_m14_qemu_lock", LOCK_MODULE_PATH)
assert SPEC and SPEC.loader
LOCK_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCK_MODULE)

PLATFORM_REQUEST = "qemu_cortex_m3"
PLATFORM_REPORT = "qemu_cortex_m3/ti_lm3s6965"
SCENARIO = "nucode.m14.cpp_policy"
TEST_ROOT = REPOSITORY / "tests" / "zephyr" / "m14_cpp_policy"
EXPECTED_TESTCASES = (
    "nucode.m14.cpp_policy.m14_cpp_policy.throw_catch_and_stack_unwind",
    "nucode.m14.cpp_policy.m14_cpp_policy.dynamic_cast_and_typeid",
    "nucode.m14.cpp_policy.m14_cpp_policy.random_and_diagnostics_on_zephyr",
)


class RuntimeFailure(RuntimeError):
    """! @brief M14 QEMU 실제 실행 계약 실패를 나타냅니다. """


## @brief QEMU ARM 실행기의 실제 경로와 버전 첫 줄을 반환합니다.
def qemu_identity() -> tuple[str, str]:
    executable = shutil.which("qemu-system-arm")
    if executable is None:
        raise RuntimeFailure("qemu-system-arm을 PATH에서 찾지 못했습니다.")
    result = subprocess.run(
        (executable, "--version"),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    version = result.stdout.splitlines()[0].strip() if result.stdout else ""
    if result.returncode != 0 or not version:
        raise RuntimeFailure("qemu-system-arm 버전을 확인하지 못했습니다.")
    return executable, version


## @brief 정확히 한 scenario와 세 testcase가 QEMU에서 PASS했는지 검사합니다.
def validate_report(report_path: Path) -> None:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeFailure(f"Twister 결과를 읽지 못했습니다: {error}") from error
    if not isinstance(report, dict):
        raise RuntimeFailure("Twister 결과 최상위 값이 object가 아닙니다.")
    suites = report.get("testsuites")
    if not isinstance(suites, list) or len(suites) != 1:
        raise RuntimeFailure("Twister 결과는 정확히 한 testsuite여야 합니다.")
    suite = suites[0]
    if not isinstance(suite, dict):
        raise RuntimeFailure("Twister testsuite record가 object가 아닙니다.")
    if suite.get("name") != SCENARIO:
        raise RuntimeFailure(f"예상하지 않은 scenario입니다: {suite.get('name')!r}")
    if suite.get("platform") != PLATFORM_REPORT:
        raise RuntimeFailure(f"예상하지 않은 QEMU platform입니다: {suite.get('platform')!r}")
    if suite.get("runnable") is not True or suite.get("status") != "passed":
        raise RuntimeFailure("M14 QEMU testsuite가 실제 실행 PASS 상태가 아닙니다.")

    testcases = suite.get("testcases")
    if not isinstance(testcases, list):
        raise RuntimeFailure("Twister testcase 목록이 배열이 아닙니다.")
    actual: set[str] = set()
    for testcase in testcases:
        if not isinstance(testcase, dict):
            raise RuntimeFailure("Twister testcase record가 object가 아닙니다.")
        identifier = testcase.get("identifier")
        if not isinstance(identifier, str) or identifier in actual:
            raise RuntimeFailure("Twister testcase 식별자가 없거나 중복됩니다.")
        actual.add(identifier)
        if testcase.get("status") != "passed":
            raise RuntimeFailure(f"M14 QEMU testcase가 PASS가 아닙니다: {identifier}")
    expected = set(EXPECTED_TESTCASES)
    if actual != expected:
        raise RuntimeFailure(
            "M14 QEMU testcase 집합이 다릅니다: "
            f"actual={sorted(actual)}, expected={sorted(expected)}"
        )


## @brief build-only 옵션 없이 고정 M14 Twister 실제 실행 명령을 만듭니다.
def twister_command(workspace: Path, outdir: Path) -> list[str]:
    return [
        sys.executable,
        str(workspace / "zephyr" / "scripts" / "twister"),
        "--testsuite-root",
        str(TEST_ROOT),
        "--platform",
        PLATFORM_REQUEST,
        "--scenario",
        SCENARIO,
        "--ninja",
        "--detailed-test-id",
        "--inline-logs",
        "--jobs",
        "2",
        "--outdir",
        str(outdir),
        "--extra-args",
        "USE_CCACHE=0",
    ]


## @brief exact NCS workspace에서 M14 C++ 정책을 QEMU로 실제 실행합니다.
def run_runtime(workspace: Path, outdir: Path, lock: dict[str, Any]) -> tuple[str, str]:
    LOCK_MODULE.validate_workspace(workspace, lock)
    if outdir.exists():
        raise RuntimeFailure(f"Twister outdir는 실행 전에 없어야 합니다: {outdir}")
    qemu_path, qemu_version = qemu_identity()
    command = twister_command(workspace, outdir)
    if "--build-only" in command:
        raise RuntimeFailure("M14 QEMU gate에는 build-only를 사용할 수 없습니다.")
    environment = dict(os.environ)
    environment["ZEPHYR_BASE"] = str(workspace / "zephyr")
    print(f"[M14-QEMU] exec: {subprocess.list2cmdline(command)}", flush=True)
    result = subprocess.run(command, cwd=workspace, env=environment, check=False)
    if result.returncode != 0:
        raise RuntimeFailure(f"Twister가 종료 코드 {result.returncode}로 실패했습니다.")
    validate_report(outdir / "twister.json")
    return qemu_path, qemu_version


## @brief M14 QEMU gate를 실행하고 exact identity가 포함된 JSON 증적을 기록합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=SCRIPT_ROOT / "ncs-3.4.0.lock.json")
    args = parser.parse_args(arguments)

    lock_path = args.lock.resolve()
    lock = LOCK_MODULE.strict_json_object(lock_path)
    LOCK_MODULE.validate_lock(lock)
    workspace = args.workspace.resolve()
    outdir = args.outdir.resolve()
    outdir.parent.mkdir(parents=True, exist_ok=True)
    qemu_path, qemu_version = run_runtime(workspace, outdir, lock)

    evidence = {
        "schema_version": 1,
        "gate": "m14-qemu-runtime",
        "status": "passed",
        "execution": "runtime",
        "scenario": SCENARIO,
        "platform_request": PLATFORM_REQUEST,
        "platform_report": PLATFORM_REPORT,
        "testcases": list(EXPECTED_TESTCASES),
        "qemu_path": qemu_path,
        "qemu_version": qemu_version,
        "lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "ncs_revision": lock["ncs"]["revision"],
        "zephyr_revision": lock["zephyr"]["revision"],
        "container_digest": lock["linux_toolchain_container"]["digest"],
    }
    (outdir / "m14-qemu-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"M14_QEMU_RUNTIME_PASS={len(EXPECTED_TESTCASES)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeFailure, LOCK_MODULE.LockFailure) as error:
        print(f"M14_QEMU_RUNTIME_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
