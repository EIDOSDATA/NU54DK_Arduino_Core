#!/usr/bin/env python3
"""! @brief M22 RC2에서 허용한 고정 검증 명령만 실행합니다. """

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


REPOSITORY = Path(__file__).resolve().parents[2]
VERSION = "0.3.0-rc.2"
FQBN = "nucode:zephyr:nu54dk"
ARDUINO_CLI_SHA256 = "65daefba1423010575d0874275734cb4a917faf5293609f01e9db6ed1c1c7e79"
MAX_LOG_BYTES = 32 * 1024 * 1024
GATE_IDS = ("host", "package-examples", "rc-upload")


class M22GateFailure(RuntimeError):
    """! @brief 고정 gate 계약을 안전하게 계속할 수 없는 오류입니다. """


## @brief 파일의 SHA-256을 bounded streaming 방식으로 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


## @brief probe UID와 Windows 사용자 경로를 공개 로그에서 제거합니다.
def redact_text(text: str, secrets: Sequence[str] = ()) -> str:
    result = text
    for secret in sorted({value for value in secrets if value}, key=len, reverse=True):
        result = result.replace(secret, "<redacted-probe-id>")
    result = re.sub(
        r"(?i)(?:[A-Z]:[\\/])Users[\\/][^\\/\s\"']+",
        r"C:\\Users\\<redacted-user>",
        result,
    )
    return result


## @brief JSON evidence를 결정적 UTF-8 형식으로 원자 기록합니다.
def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


## @brief 선택한 gate의 정확한 shell-free 명령 allowlist를 만듭니다.
def fixed_command(args: argparse.Namespace) -> list[str]:
    python = str(Path(sys.executable).resolve())
    if args.gate == "host":
        return [
            python,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(REPOSITORY / "tests" / "host"),
            "-p",
            "test_*.py",
        ]
    if args.gate == "package-examples":
        required = (
            "arduino_cli",
            "config",
            "platform_root",
            "build_root",
            "ncs_root",
            "toolchain_root",
            "cache_root",
            "detail_evidence",
        )
        if any(getattr(args, name, None) is None for name in required):
            raise M22GateFailure("package-examples gate 필수 경로가 빠졌습니다.")
        command = [
            python,
            str(REPOSITORY / "tools" / "release" / "run_m22_package_examples.py"),
            "--arduino-cli",
            str(args.arduino_cli),
            "--config",
            str(args.config),
            "--platform-root",
            str(args.platform_root),
            "--build-root",
            str(args.build_root),
            "--ncs-root",
            str(args.ncs_root),
            "--toolchain-root",
            str(args.toolchain_root),
            "--cache-root",
            str(args.cache_root),
            "--evidence",
            str(args.detail_evidence),
        ]
        for root in args.forbid_root:
            command.extend(("--forbid-root", str(root)))
        return command
    if args.gate == "rc-upload":
        required = (
            "arduino_cli",
            "workspace",
            "platform_root",
            "core_revision",
            "runtime_payload_sha256",
            "probe_id",
        )
        if any(not getattr(args, name, None) for name in required):
            raise M22GateFailure("rc-upload gate exact identity 또는 probe UID가 빠졌습니다.")
        return [
            python,
            str(REPOSITORY / "tests" / "hil" / "nu54dk" / "m8_upload.py"),
            "--cli",
            str(args.arduino_cli),
            "--repository",
            str(REPOSITORY),
            "--workspace",
            str(args.workspace),
            "--runner",
            "pyocd",
            "--repetitions",
            "1",
            "--probe-id",
            str(args.probe_id),
            "--serial-port",
            str(args.serial_port),
            "--rc-platform-root",
            str(args.platform_root),
            "--expected-version",
            VERSION,
            "--expected-core-revision",
            str(args.core_revision),
            "--expected-runtime-payload-sha256",
            str(args.runtime_payload_sha256),
        ]
    raise M22GateFailure(f"허용하지 않은 M22 gate입니다: {args.gate}")


## @brief 고정 명령을 실행하고 식별정보가 제거된 evidence만 보존합니다.
def run_gate(args: argparse.Namespace) -> dict[str, Any]:
    if (
        not isinstance(args.release_plan_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", args.release_plan_sha256)
        or not isinstance(args.release_core_revision, str)
        or not re.fullmatch(r"[0-9a-f]{40}", args.release_core_revision)
    ):
        raise M22GateFailure("fixed gate release plan/core binding이 없습니다.")
    if args.gate == "rc-upload" and args.core_revision != args.release_core_revision:
        raise M22GateFailure("RC upload core revision이 release plan과 다릅니다.")
    cli_identity: dict[str, Any] | None = None
    if args.gate in {"package-examples", "rc-upload"}:
        cli = args.arduino_cli.resolve() if args.arduino_cli else Path()
        if (
            not cli.is_file()
            or cli.is_symlink()
            or file_sha256(cli) != ARDUINO_CLI_SHA256
        ):
            raise M22GateFailure("Arduino CLI executable이 M22 exact hash와 다릅니다.")
        cli_identity = {"sha256": ARDUINO_CLI_SHA256}
    command = fixed_command(args)
    started = dt.datetime.now(dt.timezone.utc)
    try:
        result = subprocess.run(
            command,
            cwd=REPOSITORY,
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=args.timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise M22GateFailure(f"M22 {args.gate} gate 실행이 완료되지 않았습니다.") from error
    output = result.stdout[-MAX_LOG_BYTES:].decode("utf-8", errors="replace")
    redacted = redact_text(output, (str(args.probe_id or ""),))
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text(redacted, encoding="utf-8", newline="\n")
    record = {
        "schema_version": 1,
        "milestone": "M22",
        "evidence_type": "fixed-gate",
        "gate_id": args.gate,
        "status": "passed" if result.returncode == 0 else "failed",
        "release_version": VERSION,
        "release_binding": {
            "plan_sha256": args.release_plan_sha256,
            "core_revision": args.release_core_revision,
        },
        "arduino_cli": cli_identity,
        "runner": {
            "repository_relative_path": "tools/release/run_m22_fixed_gate.py",
            "sha256": file_sha256(Path(__file__).resolve()),
        },
        "command_contract": {
            "shell": False,
            "allowlisted": True,
            "probe_id_recorded": False,
        },
        "return_code": result.returncode,
        "log": {
            "file_name": args.log.name,
            "sha256": file_sha256(args.log),
            "size": args.log.stat().st_size,
            "redacted": True,
        },
        "started_at_utc": started.isoformat(),
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_json(args.evidence, record)
    if result.returncode != 0:
        raise M22GateFailure(f"M22 {args.gate} gate가 실패했습니다. log={args.log}")
    return record


## @brief 임의 child argv를 노출하지 않는 고정 parser를 구성합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="M22 RC2 고정 검증 gate")
    parser.add_argument("gate", choices=GATE_IDS)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=21600)
    parser.add_argument("--release-plan-sha256")
    parser.add_argument("--release-core-revision")
    parser.add_argument("--arduino-cli", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--platform-root", type=Path)
    parser.add_argument("--build-root", type=Path)
    parser.add_argument("--ncs-root", type=Path)
    parser.add_argument("--toolchain-root", type=Path)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--detail-evidence", type=Path)
    parser.add_argument("--forbid-root", type=Path, action="append", default=[])
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--core-revision")
    parser.add_argument("--runtime-payload-sha256")
    parser.add_argument("--probe-id")
    parser.add_argument("--serial-port", default="auto")
    return parser


## @brief M22 fixed gate 진입점입니다.
def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if not 1 <= args.timeout <= 86400:
            raise M22GateFailure("gate timeout 범위가 잘못되었습니다.")
        run_gate(args)
        return 0
    except M22GateFailure as error:
        print(f"M22_FIXED_GATE_FAIL: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
