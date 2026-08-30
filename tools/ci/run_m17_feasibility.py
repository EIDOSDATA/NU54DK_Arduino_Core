#!/usr/bin/env python3
"""! @brief NCS v3.4.0 무선 sample의 NU54DK build 적용 가능성을 기록합니다. """

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
LOCK_PATH = Path(__file__).with_name("ncs-3.4.0.lock.json")
LOCK_MODULE_PATH = Path(__file__).with_name("verify_ci_lock.py")
SPEC = importlib.util.spec_from_file_location("nu54_m17_lock", LOCK_MODULE_PATH)
assert SPEC and SPEC.loader
LOCK_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCK_MODULE)

OFFICIAL_BOARD = "nrf54l15dk/nrf54l15/cpuapp"
NU54DK_BOARD = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
NETWORK_POLICY = {
    "support_declaration": "deferred",
    "validation_scope": "build-feasibility-only",
    "hil": "not-run",
}
CRYPTO_POLICY = {
    "support_declaration": "build-only",
    "validation_scope": "build-only",
    "hil": "not-run",
}
SAMPLES = (
    ("crypto_rng", "samples/crypto/rng", CRYPTO_POLICY),
    ("802154_phy_test", "samples/peripheral/802154_phy_test", NETWORK_POLICY),
    ("openthread_cli", "samples/openthread/cli", NETWORK_POLICY),
    ("matter_template", "samples/matter/template", NETWORK_POLICY),
)


class FeasibilityFailure(RuntimeError):
    """! @brief M17 feasibility 계약 실패를 나타냅니다. """


## @brief Git 명령의 표준 출력을 반환하고 실패를 M17 계약 오류로 바꿉니다.
def git_output(path: Path, arguments: Sequence[str], context: str) -> str:
    try:
        result = subprocess.run(
            ("git", "-C", str(path), *arguments),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    except OSError as error:
        raise FeasibilityFailure(f"{context} Git 검사를 실행하지 못했습니다: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or "Git이 세부 오류를 반환하지 않았습니다."
        raise FeasibilityFailure(f"{context} Git 검사에 실패했습니다: {detail}")
    return result.stdout


## @brief build 전에 NCS·Zephyr와 실제 board checkout의 exact 상태를 검증합니다.
def validate_execution_inputs(workspace: Path, lock: dict[str, Any]) -> dict[str, str]:
    LOCK_MODULE.validate_workspace(workspace, lock)
    for source_root, label in (
        (workspace / "nrf", "NCS workspace"),
        (workspace / "zephyr", "Zephyr workspace"),
    ):
        source_status = git_output(
            source_root,
            ("status", "--porcelain", "--untracked-files=all"),
            label,
        )
        if source_status.strip():
            raise FeasibilityFailure(f"{label}에 미커밋 변경이 있습니다.")
    board_root = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
    board_revision = LOCK_MODULE.git_revision(board_root)
    expected_board_revision = str(lock["board"]["revision"])
    if board_revision != expected_board_revision:
        raise FeasibilityFailure(
            "board checkout revision이 lock과 다릅니다: "
            f"expected={expected_board_revision}, actual={board_revision}"
        )
    board_status = git_output(
        board_root,
        ("status", "--porcelain", "--untracked-files=all"),
        "board checkout",
    )
    if board_status.strip():
        raise FeasibilityFailure("board checkout에 미커밋 변경이 있습니다.")
    gitlink_output = git_output(
        REPOSITORY,
        ("ls-tree", "HEAD", "--", "board_package/NU54DK_Zephyr_DTS"),
        "부모 저장소 board gitlink",
    )
    match = re.fullmatch(
        r"160000 commit ([0-9a-f]{40})\tboard_package/NU54DK_Zephyr_DTS\r?\n?",
        gitlink_output,
    )
    if match is None or match.group(1) != expected_board_revision:
        actual = match.group(1) if match else "invalid-or-missing"
        raise FeasibilityFailure(
            "부모 저장소 board gitlink가 lock과 다릅니다: "
            f"expected={expected_board_revision}, actual={actual}"
        )
    return {
        "ncs_revision": str(lock["ncs"]["revision"]),
        "zephyr_revision": str(lock["zephyr"]["revision"]),
        "board_revision": board_revision,
    }


## @brief 파일의 SHA-256을 계산합니다.
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


## @brief official control 또는 NU54DK applicability build 명령을 만듭니다.
def build_command(
    west: str, source: Path, build_dir: Path, board: str
) -> list[str]:
    return [
        west,
        "build",
        "-b",
        board,
        "-s",
        str(source),
        "-d",
        str(build_dir),
        "-p",
        "always",
        "--sysbuild",
        "--",
        f"-DBOARD_ROOT={REPOSITORY / 'board_package' / 'NU54DK_Zephyr_DTS'}",
    ]


## @brief NCS west workspace에서 한 build를 실행하고 정규화한 log와 결과 metadata를 반환합니다.
def run_build(command: Sequence[str], log_path: Path, workspace: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            tuple(command),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=workspace,
        )
        output = result.stdout
        return_code = result.returncode
    except OSError as error:
        output = f"실행하지 못했습니다: {error}\n"
        return_code = 127
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    return {
        "command": list(command),
        "return_code": return_code,
        "result": "pass" if return_code == 0 else "fail",
        "log": str(log_path),
        "log_sha256": sha256_file(log_path),
    }


## @brief sample별 지원 경계가 승인한 정책과 정확히 같은지 검사합니다.
def validate_sample_policy(sample_name: str, policy: dict[str, str]) -> None:
    expected = CRYPTO_POLICY if sample_name == "crypto_rng" else NETWORK_POLICY
    if policy != expected:
        raise FeasibilityFailure(f"승인하지 않은 sample 정책입니다: {sample_name}: {policy}")


## @brief 세 sample의 control과 NU54DK applicability build를 실행합니다.
def execute(workspace: Path, outdir: Path, west: str) -> tuple[dict[str, Any], bool]:
    lock = LOCK_MODULE.strict_json_object(LOCK_PATH)
    LOCK_MODULE.validate_lock(lock)
    input_identity = validate_execution_inputs(workspace, lock)

    records: list[dict[str, Any]] = []
    gate_passed = True
    for sample_name, relative_source, policy in SAMPLES:
        validate_sample_policy(sample_name, policy)
        source = workspace / "nrf" / relative_source
        if not source.is_dir():
            raise FeasibilityFailure(f"공식 NCS sample이 없습니다: {source}")
        builds: dict[str, Any] = {}
        for role, board in (("official_control", OFFICIAL_BOARD), ("nu54dk_applicability", NU54DK_BOARD)):
            build_dir = outdir / "build" / sample_name / role
            log_path = outdir / "logs" / f"{sample_name}-{role}.log"
            builds[role] = run_build(
                build_command(west, source, build_dir, board), log_path, workspace
            )
        gate_passed &= builds["official_control"]["return_code"] == 0
        if sample_name == "crypto_rng":
            gate_passed &= builds["nu54dk_applicability"]["return_code"] == 0
        records.append(
            {
                "sample": sample_name,
                "official_source": f"nrf/{relative_source}",
                "policy": dict(policy),
                "builds": builds,
            }
        )

    if validate_execution_inputs(workspace, lock) != input_identity:
        raise FeasibilityFailure("build 도중 exact 입력 revision이 변경됐습니다.")

    evidence = {
        "schema_version": 1,
        "milestone": "M17",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ncs": {"tag": lock["ncs"]["tag"], "revision": lock["ncs"]["revision"]},
        "zephyr": {"revision": lock["zephyr"]["revision"]},
        "board_package": {"revision": lock["board"]["revision"]},
        "official_board": OFFICIAL_BOARD,
        "applicability_board": NU54DK_BOARD,
        "gate_contract": {
            "crypto_rng": ["official_control", "nu54dk_applicability"],
            "networking": ["official_control"],
        },
        "control_gate": "pass" if gate_passed else "fail",
        "samples": records,
    }
    return evidence, gate_passed


## @brief CLI 인자를 구성합니다.
def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--west", default="west")
    return parser.parse_args(argv)


## @brief feasibility evidence를 쓰고 official control gate 결과를 반환합니다.
def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    outdir = args.outdir.resolve()
    try:
        evidence, controls_passed = execute(
            args.workspace.resolve(), outdir, args.west
        )
        outdir.mkdir(parents=True, exist_ok=True)
        evidence_path = outdir / "m17-feasibility.json"
        evidence_path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"M17_FEASIBILITY_EVIDENCE={evidence_path}")
        return 0 if controls_passed else 1
    except (FeasibilityFailure, LOCK_MODULE.LockFailure) as error:
        print(f"M17_FEASIBILITY_FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
