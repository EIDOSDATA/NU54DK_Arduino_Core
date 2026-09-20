#!/usr/bin/env python3
"""! @brief SHA-256 probe identity로 한 image를 flash하고 receipt를 남깁니다. """

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Sequence

from pyocd.core.helpers import ConnectHelper


PY_OCD = Path(
    r"C:\Users\eidos\AppData\Local\Python\pythoncore-3.14-64\Scripts\pyocd.exe"
)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
PROGRAMMED_PATTERN = re.compile(r"programmed\s+(\d+)\s+bytes", re.IGNORECASE)
DIAGNOSTIC_PATTERN = re.compile(
    r"(?i)(?:\btraceback\b|\berror\b|\bfail(?:ed|ure)?\b|\bfault\b|"
    r"\btimeout\b|communication failure|no ack|unexpected ack)"
)
LOAD_TIMEOUT_SECONDS = 120.0
RESET_TIMEOUT_SECONDS = 20.0


class FlashFailure(RuntimeError):
    """! @brief 안전한 flash 판정 실패를 나타냅니다. """


def utc_now() -> str:
    """! @brief 현재 UTC 시각을 ISO 8601로 반환합니다. """
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    """! @brief 파일 SHA-256을 계산합니다. """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def has_diagnostic_failure(output: str) -> bool:
    """! @brief 전체 pyOCD 출력의 오류 진단을 fail-closed 검사합니다. """
    return DIAGNOSTIC_PATTERN.search(output) is not None


def build_common_arguments(selected_uid: str) -> tuple[str, ...]:
    """! @brief load와 reset이 공유하는 fail-closed pyOCD 인자를 구성합니다. """
    return (
        "--uid",
        selected_uid,
        "--target",
        "nrf54l",
        "--frequency",
        "500000",
        "--connect",
        "under-reset",
        "-O",
        "cmsis_dap.limit_packets=true",
        "-O",
        "cmsis_dap.prefer_v1=false",
        "-O",
        "auto_unlock=false",
        "-O",
        "resume_on_disconnect=false",
    )


def write_receipt(path: Path, document: dict[str, Any]) -> None:
    """! @brief JSON receipt를 x-mode로 한 번만 기록합니다. """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except FileExistsError as error:
        raise FlashFailure("receipt 경로가 이미 존재합니다.") from error


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact image/probe/core/receipt 인자를 정의합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("probe_sha256")
    parser.add_argument("image", type=Path)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--role", choices=("source", "sink"), required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--leave-halted", action="store_true")
    return parser.parse_args(arguments)


def run_flash(args: argparse.Namespace) -> int:
    """! @brief image를 load/reset하고 hash-bound receipt를 기록합니다. """
    started_at = utc_now()
    helper_path = Path(__file__).resolve()
    helper_hash = sha256_file(helper_path)
    probe_hash = args.probe_sha256.lower()
    image = args.image.resolve()
    receipt = args.receipt.resolve()
    if HASH_PATTERN.fullmatch(probe_hash) is None:
        raise FlashFailure("probe SHA-256 형식이 잘못되었습니다.")
    if HASH_PATTERN.fullmatch(args.image_sha256) is None:
        raise FlashFailure("image SHA-256 형식이 잘못되었습니다.")
    if REVISION_PATTERN.fullmatch(args.core_revision) is None:
        raise FlashFailure("core revision 형식이 잘못되었습니다.")
    if not image.is_file():
        raise FlashFailure("image 파일이 없습니다.")
    if receipt.exists():
        raise FlashFailure("기존 receipt를 덮어쓰지 않습니다.")
    actual_image_hash = sha256_file(image)
    if actual_image_hash != args.image_sha256:
        raise FlashFailure("image SHA-256이 일치하지 않습니다.")
    if not PY_OCD.is_file():
        raise FlashFailure("exact pyOCD 실행 파일이 없습니다.")

    try:
        logging.disable(logging.CRITICAL)
        hidden_stdout = io.StringIO()
        hidden_stderr = io.StringIO()
        with redirect_stdout(hidden_stdout), redirect_stderr(hidden_stderr):
            probes = ConnectHelper.get_all_connected_probes(
                blocking=False, print_wait_message=False
            )
            matching_uids = [
                probe.unique_id
                for probe in probes
                if hashlib.sha256(probe.unique_id.encode("utf-8")).hexdigest()
                == probe_hash
            ]
    except Exception as error:
        raise FlashFailure("probe hash inventory 확인 실패") from error
    if len(matching_uids) != 1:
        raise FlashFailure(f"probe hash match count={len(matching_uids)}")
    selected_uid = matching_uids[0]
    common = build_common_arguments(selected_uid)
    try:
        load = subprocess.run(
            (
                str(PY_OCD),
                "load",
                *common,
                "-O",
                "smart_flash=false",
                "--erase",
                "sector",
                "--format",
                "hex",
                "--no-reset",
                str(image),
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            timeout=LOAD_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise FlashFailure("pyOCD load timeout") from error
    except OSError as error:
        raise FlashFailure("pyOCD load 실행 실패") from error
    load_output = load.stdout + load.stderr
    load_diagnostic_failed = has_diagnostic_failure(load_output)
    byte_match = PROGRAMMED_PATTERN.search(load_output)
    programmed_bytes = int(byte_match.group(1)) if byte_match is not None else 0
    if load.returncode != 0 or load_diagnostic_failed or programmed_bytes <= 0:
        raise FlashFailure(
            f"pyOCD load 실패 rc={load.returncode} "
            f"diagnostic={load_diagnostic_failed} programmed={programmed_bytes}"
        )

    reset_returncode: int | None = None
    reset_diagnostic_failed = False
    if not args.leave_halted:
        try:
            reset = subprocess.run(
                (str(PY_OCD), "reset", *common, "--method", "hw"),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="backslashreplace",
                timeout=RESET_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise FlashFailure("pyOCD reset timeout") from error
        except OSError as error:
            raise FlashFailure("pyOCD reset 실행 실패") from error
        reset_output = reset.stdout + reset.stderr
        reset_diagnostic_failed = has_diagnostic_failure(reset_output)
        reset_returncode = reset.returncode
        if reset.returncode != 0 or reset_diagnostic_failed:
            raise FlashFailure(
                f"pyOCD reset 실패 rc={reset.returncode} "
                f"diagnostic={reset_diagnostic_failed}"
            )
    if sha256_file(image) != actual_image_hash or sha256_file(helper_path) != helper_hash:
        raise FlashFailure("flash 중 image 또는 helper가 변경되었습니다.")

    document = {
        "schema": "nucode.probe-flash-receipt.v1",
        "status": "PASS",
        "result": (
            "image_programmed_and_left_halted"
            if args.leave_halted
            else "image_programmed_and_hardware_reset"
        ),
        "role": args.role,
        "probe_sha256": probe_hash,
        "image_path": str(image),
        "image_sha256": actual_image_hash,
        "core_revision": args.core_revision,
        "helper_path": str(helper_path),
        "helper_sha256": helper_hash,
        "started_at": started_at,
        "finished_at": utc_now(),
        "programmed_bytes": programmed_bytes,
        "load": {
            "returncode": load.returncode,
            "timeout_seconds": LOAD_TIMEOUT_SECONDS,
            "diagnostic_failure": load_diagnostic_failed,
        },
        "reset": {
            "performed": not args.leave_halted,
            "returncode": reset_returncode,
            "timeout_seconds": RESET_TIMEOUT_SECONDS,
            "diagnostic_failure": reset_diagnostic_failed,
            "method": "none" if args.leave_halted else "hardware",
        },
        "raw_probe_identifiers_recorded": False,
        "existing_files_overwritten": False,
    }
    write_receipt(receipt, document)
    print(
        f"FLASH=PASS role={args.role} probe_sha256={probe_hash} "
        f"image_sha256={actual_image_hash} programmed_bytes={programmed_bytes} "
        f"receipt={receipt}"
    )
    return 0


def run_self_test() -> int:
    """! @brief hardware 없이 parser·diagnostic·x-mode receipt를 시험합니다. """
    if has_diagnostic_failure(("clean\n" * 200) + "Error: No ACK") is not True:
        raise FlashFailure("late diagnostic fixture 실패")
    if has_diagnostic_failure("programmed 123 bytes"):
        raise FlashFailure("clean diagnostic fixture 실패")
    common = build_common_arguments("fixture-uid")
    if "resume_on_disconnect=false" not in common:
        raise FlashFailure("leave-halted disconnect fixture 실패")
    parsed = parse_arguments(
        [
            "0" * 64,
            "fixture.hex",
            "--image-sha256",
            "1" * 64,
            "--core-revision",
            "2" * 40,
            "--role",
            "source",
            "--receipt",
            "fixture.json",
            "--leave-halted",
        ]
    )
    if not parsed.leave_halted:
        raise FlashFailure("leave-halted parser fixture 실패")
    with tempfile.TemporaryDirectory(prefix="flash-helper-") as directory:
        receipt = Path(directory) / "receipt.json"
        write_receipt(receipt, {"status": "fixture"})
        try:
            write_receipt(receipt, {"status": "overwrite"})
        except FlashFailure:
            pass
        else:
            raise FlashFailure("receipt no-overwrite fixture 실패")
    print("FLASH_HELPER_SELF_TEST=PASS;HARDWARE=UNTOUCHED")
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief self-test 또는 실제 flash를 실행합니다. """
    selected = list(sys.argv[1:] if arguments is None else arguments)
    if selected == ["self-test"]:
        return run_self_test()
    return run_flash(parse_arguments(arguments))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FlashFailure as error:
        print(f"FLASH=FAIL reason={type(error).__name__} detail={error}", file=sys.stderr)
        raise SystemExit(2) from error
