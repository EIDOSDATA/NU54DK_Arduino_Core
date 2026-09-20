#!/usr/bin/env python3
"""! @brief SHA-256 probe identity로 제한된 pyOCD commander 명령을 실행합니다. """

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import logging
import re
import subprocess
import sys
from typing import Sequence

from pyocd.core.helpers import ConnectHelper


PY_OCD = (
    r"C:\Users\eidos\AppData\Local\Python\pythoncore-3.14-64"
    r"\Scripts\pyocd.exe"
)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
ADDRESS_PATTERN = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")
IDENTIFIER_PATTERN = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{16,}(?![0-9a-f])")
DIAGNOSTIC_PATTERN = re.compile(
    r"(?i)(?:\btraceback\b|\berror\b|\bfail(?:ed|ure)?\b|\bfault\b|"
    r"\btimeout\b|communication failure|no ack|unexpected ack)"
)
ALLOWED_COMMANDS = frozenset(("reset", "go", "halt"))
INTERNAL_TIMEOUT_SECONDS = 20.0
OUTPUT_LIMIT = 800


def sanitize_output(output: str, selected_uid: str) -> str:
    """! @brief 원시 UID·주소·긴 식별자를 제거하고 줄바꿈을 escape합니다. """
    sanitized = re.sub(
        re.escape(selected_uid),
        "<probe-sha256-selected>",
        output,
        flags=re.IGNORECASE,
    )
    sanitized = ADDRESS_PATTERN.sub("<bt-address>", sanitized)
    sanitized = IDENTIFIER_PATTERN.sub("<device-identifier>", sanitized)
    sanitized = sanitized.strip().replace("\r", "\\r").replace("\n", "\\n")
    if len(sanitized) <= OUTPUT_LIMIT:
        return sanitized
    digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
    marker = f"...<truncated sha256={digest}>..."
    side = max(0, (OUTPUT_LIMIT - len(marker)) // 2)
    return (sanitized[:side] + marker + sanitized[-side:])[:OUTPUT_LIMIT]


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief hash와 제한된 commander 명령을 정의합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("probe_sha256")
    parser.add_argument("commands", nargs="+")
    parser.add_argument("--connect", choices=("halt", "under-reset"), default="halt")
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief exact 한 probe에서 bounded commander를 실행합니다. """
    args = parse_arguments(arguments)
    if HASH_PATTERN.fullmatch(args.probe_sha256) is None:
        print("COMMANDER=FAIL reason=invalid-probe-hash", file=sys.stderr)
        return 2
    if any(command not in ALLOWED_COMMANDS for command in args.commands):
        print("COMMANDER=FAIL reason=unsupported-command", file=sys.stderr)
        return 2
    try:
        logging.disable(logging.CRITICAL)
        hidden_stdout = io.StringIO()
        hidden_stderr = io.StringIO()
        with redirect_stdout(hidden_stdout), redirect_stderr(hidden_stderr):
            matching_uids = [
                probe.unique_id
                for probe in ConnectHelper.get_all_connected_probes(
                    blocking=False, print_wait_message=False
                )
                if hashlib.sha256(probe.unique_id.encode("utf-8")).hexdigest()
                == args.probe_sha256
            ]
    except Exception:
        print("COMMANDER=FAIL reason=probe-inventory", file=sys.stderr)
        return 2
    if len(matching_uids) != 1:
        print(
            f"COMMANDER=FAIL reason=probe-match count={len(matching_uids)} "
            f"sha256={args.probe_sha256}",
            file=sys.stderr,
        )
        return 2
    selected_uid = matching_uids[0]
    command = [
        PY_OCD,
        "commander",
        "-q",
        "--uid",
        selected_uid,
        "--target",
        "nrf54l",
        "--frequency",
        "500000",
        "--connect",
        args.connect,
        "-O",
        "cmsis_dap.limit_packets=true",
        "-O",
        "cmsis_dap.prefer_v1=false",
        "-O",
        "auto_unlock=false",
        "-O",
        "resume_on_disconnect=false",
    ]
    for item in args.commands:
        command.extend(("-c", item))
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            timeout=INTERNAL_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print("COMMANDER=FAIL reason=timeout", file=sys.stderr)
        return 3
    except OSError:
        print("COMMANDER=FAIL reason=launch", file=sys.stderr)
        return 3
    raw_output = completed.stdout + completed.stderr
    diagnostic_failed = DIAGNOSTIC_PATTERN.search(raw_output) is not None
    safe_output = sanitize_output(raw_output, selected_uid)
    if safe_output:
        print(safe_output)
    print(f"COMMANDER_RC={completed.returncode}")
    if completed.returncode != 0 or diagnostic_failed:
        print(
            f"COMMANDER=FAIL diagnostic={str(diagnostic_failed).lower()}",
            file=sys.stderr,
        )
        return completed.returncode if completed.returncode != 0 else 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
