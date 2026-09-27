#!/usr/bin/env python3
"""! @brief 공개 PBP 예제의 2보드 closure HIL을 자동 판정합니다.

검토된 SHA-256 전용 sibling helper로 G/source와 F/sink를 flash한 뒤 공개
UART 명령만 사용합니다. sync-loss의 source reset도 hash 전용 helper로 수행합니다.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass
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
import time
from typing import Any, Callable, Sequence


ROLES = ("source", "sink")
EXPECTED_BOARD_MAP = {
    "source": {
        "board": "G",
        "port": "COM10",
        "probe_sha256": (
            "e44e2ba24dbcbdd3c41e05192773a058"
            "ed7dbbca2354dda703a004646ea9a334"
        ),
    },
    "sink": {
        "board": "F",
        "port": "COM14",
        "probe_sha256": (
            "4574ee31f25fe05f154395ea4d8c6aa0"
            "583b04a4f7a0ea97fe3d13b05eea8ca0"
        ),
    },
}
PUBLIC_EXAMPLES = {
    "source": Path(
        "libraries/NUCODE_BLE_Audio/examples/PublicAudioBroadcastSource/"
        "PublicAudioBroadcastSource.ino"
    ),
    "sink": Path(
        "libraries/NUCODE_BLE_Audio/examples/PublicAudioBroadcastSink/"
        "PublicAudioBroadcastSink.ino"
    ),
}
EXPECTED_DEBUG_HELPER_SHA256 = (
    "a2d9c1a83198a3e28c6d2562320697edbbc3adba03ce10c8e6295ffde310a7a2"
)
EXPECTED_FLASH_HELPER_SHA256 = (
    "3cdbd5d87aa8a39240bf06124ee0f5bfeafbfdf9c9c96c2705ab07d066497d16"
)
EXPECTED_USB_PORT_MAP = {
    "source": {
        "target_port": "COM10",
        "aux_port": "COM11",
        "serial_sha256": (
            "f419aa19cc41d8d2c8c85339a81b8f2c0e1ada5bf91f0ff04200513fc6aba69f"
        ),
    },
    "sink": {
        "target_port": "COM14",
        "aux_port": "COM15",
        "serial_sha256": (
            "a68185c274fd83f93c9520f99fb418184395f9548a52e306449733c3c9f39b46"
        ),
    },
}
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
ADDRESS_PATTERN = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")
IDENTIFIER_PATTERN = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{16,}(?![0-9a-f])")
RECEIVED_PATTERN = re.compile(
    r"^public audio received=(\d+) energy=(\d+) dropped=(\d+)$"
)
SYNC_FAILURE_PATTERN = re.compile(
    r"^public audio sync failed: (-?\d+) step=(\d+)$"
)
QUALITY_PATTERN = re.compile(r"^high quality rejected: (\d+)$")
RESET_NOISE_ESCAPE_PATTERN = re.compile(r"\\x[89a-fA-F][0-9a-fA-F]")
RESET_NOISE_MAXIMUM_UNITS = 16
DEBUG_FAILURE_PATTERN = re.compile(
    r"(?i)(?:\btraceback\b|\berror\b|\bfail(?:ed|ure)?\b|\bfault\b|"
    r"\btimeout\b|communication failure|no ack|unexpected ack)"
)
DEBUG_SUCCESS_PATTERN = re.compile(r"(?m)^COMMANDER_RC=0$")
PUBLIC_ERROR_PATTERN = re.compile(r"(?i)\b(?:error|failed|failure|rejected)\b")
FATAL_TOKENS = (
    "Stack overflow",
    "FATAL ERROR",
    "***** Hardware exception",
    "Bluetooth start failed",
    "LC3 codec start failed",
    "LC3 encode failed",
    "LC3 decode failed",
    "public audio source start failed:",
    "public audio source stop failed:",
    "public audio source failed:",
    "public audio send failed:",
    "public audio sink start failed:",
    "public audio sink stop failed:",
)
ALLOWED_COMMANDS = {
    "source": frozenset("rsh"),
    "sink": frozenset("rswh"),
}
POSITIVE_STREAM_SECONDS = 180.0
MAX_CAMPAIGN_SECONDS = 180.0
MAX_RECOVERY_SECONDS = 30.0
MARK_QUIET_SECONDS = 0.120
MARK_MAXIMUM_SECONDS = 0.750
DEBUG_EVIDENCE_LIMIT = 800
UNSUPPORTED_ERROR_CODE = 10
EXPECTED_FAILURE_STEP = 11
FLASH_HELPER_LOAD_TIMEOUT = 120.0
FLASH_HELPER_RESET_TIMEOUT = 20.0
FLASH_HELPER_OUTER_TIMEOUT = 165.0
DEBUG_HELPER_INTERNAL_TIMEOUT = 20.0


class HilFailure(RuntimeError):
    """! @brief HIL 계약 또는 실행 판정 실패를 나타냅니다. """


@dataclass(frozen=True)
class Event:
    """! @brief 정제된 UART/runner 한 줄과 공통 시간축 위치입니다. """

    sequence: int
    at_s: float
    role: str
    text: str


@dataclass(frozen=True)
class ReceivedSample:
    """! @brief 공개 sink가 출력한 LC3 누적 수신 상태입니다. """

    frames: int
    energy: int
    dropped: int


@dataclass(frozen=True)
class ErrorAllowance:
    """! @brief 명시적으로 열린 action window의 허용 오류 집합입니다. """

    sync_failures: frozenset[tuple[str, int, int]]
    quality_rejections: frozenset[tuple[str, int]]


def utc_now() -> str:
    """! @brief 현재 UTC 시각을 ISO 8601 문자열로 반환합니다. """
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    """! @brief 파일을 변경하지 않고 SHA-256을 계산합니다. """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sanitize_line(line: str) -> str:
    """! @brief 주소와 긴 원시 식별자를 외부 증적에서 제거합니다. """
    sanitized = ADDRESS_PATTERN.sub("<bt-address>", line)
    return IDENTIFIER_PATTERN.sub("<device-identifier>", sanitized)


def bounded_sanitized_text(text: str, limit: int = DEBUG_EVIDENCE_LIMIT) -> str:
    """! @brief 전체 digest를 보존하고 줄바꿈을 escape한 정제 문자열을 제한합니다. """
    stripped = text.strip()
    sanitized = sanitize_line(stripped).replace("\r", "\\r").replace("\n", "\\n")
    if len(sanitized) <= limit:
        return sanitized
    digest = hashlib.sha256(stripped.encode("utf-8")).hexdigest()
    marker = f"...<truncated sha256={digest}>..."
    side = max(0, (limit - len(marker)) // 2)
    return (sanitized[:side] + marker + sanitized[-side:])[:limit]


def inspect_debug_output(raw_output: str) -> tuple[str, bool]:
    """! @brief 전체 debug 출력을 검사한 뒤 bounded 증적을 생성합니다. """
    failed = DEBUG_FAILURE_PATTERN.search(raw_output) is not None
    complete = DEBUG_SUCCESS_PATTERN.search(raw_output) is not None
    return bounded_sanitized_text(raw_output), failed or not complete


def parse_received(text: str) -> ReceivedSample | None:
    """! @brief 공개 수신 상태 한 줄을 구조화합니다. """
    match = RECEIVED_PATTERN.fullmatch(text)
    if match is None:
        return None
    return ReceivedSample(*(int(value) for value in match.groups()))


def parse_sync_failure(text: str) -> tuple[int, int] | None:
    """! @brief 공개 sync failure의 native reason과 step을 반환합니다. """
    match = SYNC_FAILURE_PATTERN.fullmatch(text)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def parse_quality_result(text: str) -> int | None:
    """! @brief 공개 quality 거부의 stable Error 값을 반환합니다. """
    match = QUALITY_PATTERN.fullmatch(text)
    return None if match is None else int(match.group(1))


def matches_token_after_reset_noise(text: str, token: str) -> bool:
    """! @brief reset 경계의 invalid UART byte 뒤 exact token만 허용합니다. """
    if text == token:
        return True
    if not text.endswith(token):
        return False
    prefix = text[: -len(token)]
    units = 0
    has_reset_marker = False
    cursor = 0
    while cursor < len(prefix):
        escaped = RESET_NOISE_ESCAPE_PATTERN.match(prefix, cursor)
        if escaped is not None:
            has_reset_marker = True
            units += 1
            cursor = escaped.end()
            continue
        value = prefix[cursor]
        if value == "\\":
            return False
        if ord(value) < 0x20 or ord(value) == 0x7F:
            has_reset_marker = True
        units += 1
        cursor += 1
    if units == 0 or units > RESET_NOISE_MAXIMUM_UNITS:
        return False
    return has_reset_marker or units <= 4


def verify_announcement(text: str) -> None:
    """! @brief 공개 이름·program·암호화 선택을 exact 검사합니다. """
    required = (
        "selected public audio name=NUCODE-PUBLIC-AUDIO",
        "program=Synthetic 16 kHz audio",
        "encrypted=yes",
    )
    if not all(token in text for token in required):
        raise HilFailure(f"공개 announcement 불일치: {bounded_sanitized_text(text)}")


def verify_source(core_root: Path, expected_revision: str) -> dict[str, str]:
    """! @brief exact commit·clean checkout·공개 sketch hash를 확인합니다. """
    try:
        head = subprocess.check_output(
            ("git", "rev-parse", "HEAD"), cwd=core_root, text=True
        ).strip()
        dirty = subprocess.check_output(
            ("git", "status", "--porcelain=v1", "--untracked-files=all"),
            cwd=core_root,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise HilFailure("Core source 확인 실패") from error
    if head != expected_revision:
        raise HilFailure(
            f"Core revision 불일치: expected={expected_revision}, actual={head}"
        )
    if dirty:
        raise HilFailure("Core source가 untracked 파일을 포함해 clean 상태가 아닙니다.")
    hashes: dict[str, str] = {}
    for role, relative_path in PUBLIC_EXAMPLES.items():
        source = core_root / relative_path
        if not source.is_file():
            raise HilFailure(f"공개 {role} sketch가 없습니다: {source}")
        hashes[role] = sha256_file(source)
    return hashes


def validate_probe_inventory(live_hashes: Sequence[str]) -> dict[str, Any]:
    """! @brief G/F expected probe가 live 목록에 정확히 한 번씩 있는지 확인합니다. """
    matches: dict[str, int] = {}
    for role in ROLES:
        expected = str(EXPECTED_BOARD_MAP[role]["probe_sha256"])
        count = sum(value == expected for value in live_hashes)
        if count != 1:
            raise HilFailure(f"{role} live probe hash match count={count}")
        matches[role] = count
    return {
        "connected_probe_count": len(live_hashes),
        "expected_hash_matches": matches,
    }


def preflight_live_probes() -> dict[str, Any]:
    """! @brief 원시 UID 출력 없이 live probe hash inventory를 검사합니다. """
    try:
        from pyocd.core.helpers import ConnectHelper
    except ImportError as error:
        raise HilFailure("live probe preflight에는 pyOCD가 필요합니다.") from error
    try:
        logging.disable(logging.CRITICAL)
        hidden_stdout = io.StringIO()
        hidden_stderr = io.StringIO()
        with redirect_stdout(hidden_stdout), redirect_stderr(hidden_stderr):
            probes = ConnectHelper.get_all_connected_probes(
                blocking=False, print_wait_message=False
            )
            hashes = [
                hashlib.sha256(probe.unique_id.encode("utf-8")).hexdigest()
                for probe in probes
            ]
    except Exception as error:
        raise HilFailure("live probe hash preflight에 실패했습니다.") from error
    return validate_probe_inventory(hashes)


def validate_usb_port_hashes(
    entries: Sequence[tuple[str, str]],
) -> dict[str, Any]:
    """! @brief target+aux COM과 USB serial hash mapping을 exact 검사합니다. """
    normalized = [(port.casefold(), digest) for port, digest in entries]
    result: dict[str, Any] = {}
    for role in ROLES:
        expected = EXPECTED_USB_PORT_MAP[role]
        role_ports: dict[str, str] = {}
        for kind in ("target", "aux"):
            port = str(expected[f"{kind}_port"])
            matches = [
                digest for device, digest in normalized if device == port.casefold()
            ]
            if len(matches) != 1:
                raise HilFailure(f"{role} {kind} COM enumeration count={len(matches)}")
            if matches[0] != expected["serial_sha256"]:
                raise HilFailure(f"{role} {kind} USB serial SHA-256 mapping 불일치")
            role_ports[f"{kind}_port"] = port
        role_ports["serial_sha256"] = str(expected["serial_sha256"])
        result[role] = role_ports
    return {
        "required_port_count": 4,
        "roles": result,
        "raw_usb_serials_recorded": False,
    }


def preflight_usb_ports(list_ports_module: Any) -> dict[str, Any]:
    """! @brief 원시 USB serial을 기록하지 않고 exact 4개 COM mapping을 확인합니다. """
    required_ports = {
        str(value[f"{kind}_port"]).casefold()
        for value in EXPECTED_USB_PORT_MAP.values()
        for kind in ("target", "aux")
    }
    entries: list[tuple[str, str]] = []
    try:
        for port in list_ports_module.comports():
            device = str(port.device)
            if device.casefold() not in required_ports:
                continue
            serial_number = port.serial_number
            if not isinstance(serial_number, str) or not serial_number:
                raise HilFailure(f"{device} USB serial이 없습니다.")
            digest = hashlib.sha256(serial_number.encode("utf-8")).hexdigest()
            entries.append((device, digest))
    except HilFailure:
        raise
    except Exception as error:
        raise HilFailure("USB COM inventory 확인 실패") from error
    return validate_usb_port_hashes(entries)


def verify_flash_receipt(
    path: Path,
    role: str,
    probe_hash: str,
    image: Path,
    image_hash: str,
    core_revision: str,
    helper: Path,
    helper_hash: str,
) -> dict[str, Any]:
    """! @brief flash helper receipt의 exact provenance와 PASS 결과를 확인합니다. """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HilFailure(f"{role} flash receipt 읽기 실패") from error
    required = {
        "schema": "nucode.probe-flash-receipt.v1",
        "status": "PASS",
        "result": "image_programmed_and_hardware_reset",
        "role": role,
        "probe_sha256": probe_hash,
        "image_path": str(image),
        "image_sha256": image_hash,
        "core_revision": core_revision,
        "helper_path": str(helper),
        "helper_sha256": helper_hash,
        "raw_probe_identifiers_recorded": False,
        "existing_files_overwritten": False,
    }
    if not isinstance(document, dict) or any(
        document.get(field) != expected for field, expected in required.items()
    ):
        raise HilFailure(f"{role} flash receipt exact field 불일치")
    receipt_times: dict[str, datetime] = {}
    for field in ("started_at", "finished_at"):
        value = document.get(field)
        if not isinstance(value, str):
            raise HilFailure(f"{role} flash receipt {field} UTC 시각이 없습니다.")
        try:
            parsed_time = datetime.fromisoformat(value)
        except ValueError as error:
            raise HilFailure(f"{role} flash receipt {field} 형식이 잘못되었습니다.") from error
        if parsed_time.tzinfo is None or parsed_time.utcoffset() != timezone.utc.utcoffset(None):
            raise HilFailure(f"{role} flash receipt {field}가 UTC가 아닙니다.")
        receipt_times[field] = parsed_time
    if receipt_times["finished_at"] < receipt_times["started_at"]:
        raise HilFailure(f"{role} flash receipt UTC 순서가 잘못되었습니다.")
    programmed = document.get("programmed_bytes")
    load = document.get("load")
    reset = document.get("reset")
    if not isinstance(programmed, int) or programmed <= 0:
        raise HilFailure(f"{role} flash programmed byte 근거가 없습니다.")
    if (
        not isinstance(load, dict)
        or load.get("returncode") != 0
        or load.get("timeout_seconds") != FLASH_HELPER_LOAD_TIMEOUT
        or load.get("diagnostic_failure") is not False
    ):
        raise HilFailure(f"{role} flash load receipt가 PASS가 아닙니다.")
    if (
        not isinstance(reset, dict)
        or reset.get("returncode") != 0
        or reset.get("timeout_seconds") != FLASH_HELPER_RESET_TIMEOUT
        or reset.get("diagnostic_failure") is not False
        or reset.get("method") != "hardware"
    ):
        raise HilFailure(f"{role} flash reset receipt가 PASS가 아닙니다.")
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "programmed_bytes": programmed,
        "status": "PASS",
    }


def invoke_flash_helper(
    helper: Path,
    helper_hash: str,
    role: str,
    probe_hash: str,
    image: Path,
    image_hash: str,
    core_revision: str,
    receipt: Path,
) -> dict[str, Any]:
    """! @brief reviewed helper로 exact role image를 flash하고 receipt를 검증합니다. """
    invocation = (
        sys.executable,
        str(helper),
        probe_hash,
        str(image),
        "--image-sha256",
        image_hash,
        "--core-revision",
        core_revision,
        "--role",
        role,
        "--receipt",
        str(receipt),
    )
    try:
        completed = subprocess.run(
            invocation,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            timeout=FLASH_HELPER_OUTER_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise HilFailure(f"{role} flash helper emergency outer timeout") from error
    except OSError as error:
        raise HilFailure(f"{role} flash helper 실행 실패") from error
    raw_output = completed.stdout + completed.stderr
    diagnostic_failed = DEBUG_FAILURE_PATTERN.search(raw_output) is not None
    if (
        completed.returncode != 0
        or diagnostic_failed
        or re.search(r"(?m)^FLASH=PASS\b", raw_output) is None
    ):
        safe_output = bounded_sanitized_text(raw_output)
        raise HilFailure(
            f"{role} flash helper 실패 rc={completed.returncode} output={safe_output}"
        )
    return verify_flash_receipt(
        receipt,
        role,
        probe_hash,
        image,
        image_hash,
        core_revision,
        helper,
        helper_hash,
    )


def validate_contract_values(
    mode: str,
    cycles: int,
    duration: float,
    total_timeout: float,
    recovery_timeout: float,
    reset_timeout: float,
) -> None:
    """! @brief 고정 분모와 readiness 시간 계약을 검사합니다. """
    if cycles != 20:
        raise HilFailure("PBP 반복 분모는 정확히 20회여야 합니다.")
    if duration != POSITIVE_STREAM_SECONDS:
        raise HilFailure("positive stream duration은 정확히 180초여야 합니다.")
    if not 1.0 <= total_timeout <= MAX_CAMPAIGN_SECONDS:
        raise HilFailure("non-positive campaign timeout은 최대 180초여야 합니다.")
    if not 1.0 <= recovery_timeout <= MAX_RECOVERY_SECONDS:
        raise HilFailure("recovery timeout은 최대 30초여야 합니다.")
    if not DEBUG_HELPER_INTERNAL_TIMEOUT < reset_timeout <= recovery_timeout:
        raise HilFailure("reset outer timeout은 helper 20초보다 크고 recovery 이하여야 합니다.")
    if mode not in {"positive", "stop-restart", "wrong-code", "quality", "sync-loss"}:
        raise HilFailure(f"알 수 없는 mode: {mode}")


def validate_output_paths(transcript: Path, summary: Path) -> None:
    """! @brief transcript와 JSON 경로를 no-overwrite로 검사합니다. """
    if transcript == summary:
        raise HilFailure("transcript와 summary 경로는 달라야 합니다.")
    if transcript.exists():
        raise HilFailure("기존 transcript를 덮어쓰지 않습니다.")
    if summary.exists():
        raise HilFailure("기존 summary를 덮어쓰지 않습니다.")


class Campaign:
    """! @brief 두 UART와 bounded action을 단일 시간축에서 조정합니다. """

    def __init__(
        self,
        mode: str,
        serial_module: Any,
        ports: dict[str, str],
        probe_hashes: dict[str, str],
        transcript_path: Path,
        reset_helper: Path,
        reset_timeout: float,
        total_timeout: float | None,
        mark_quiet: float = MARK_QUIET_SECONDS,
        mark_maximum: float = MARK_MAXIMUM_SECONDS,
    ) -> None:
        self.mode = mode
        self.serial_module = serial_module
        self.ports = ports
        self.probe_hashes = probe_hashes
        self.transcript_path = transcript_path
        self.reset_helper = reset_helper
        self.reset_timeout = reset_timeout
        self.started = time.monotonic()
        self.deadline = None if total_timeout is None else self.started + total_timeout
        self.mark_quiet = mark_quiet
        self.mark_maximum = mark_maximum
        self.streams: dict[str, Any] = {}
        self.pending = {role: bytearray() for role in ROLES}
        self.events: list[Event] = []
        self.error_windows: dict[str, ErrorAllowance] = {}
        self.transcript: Any = None
        self.last_pump_had_bytes = False

    def __enter__(self) -> Campaign:
        """! @brief 새 transcript를 만들고 exact 두 COM만 엽니다. """
        self.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        self.transcript = self.transcript_path.open("x", encoding="utf-8", newline="\n")
        try:
            for role in ROLES:
                self.streams[role] = self.serial_module.Serial(
                    self.ports[role],
                    115200,
                    timeout=0.02,
                    write_timeout=2.0,
                    rtscts=False,
                    dsrdtr=False,
                )
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
        """! @brief 성공·실패 모두에서 열린 자원을 닫습니다. """
        self.close()

    def close(self) -> None:
        """! @brief UART와 transcript를 중복 호출에 안전하게 닫습니다. """
        for stream in self.streams.values():
            try:
                stream.close()
            except Exception:
                pass
        self.streams.clear()
        if self.transcript is not None:
            self.transcript.close()
            self.transcript = None

    def remaining_global(self, description: str) -> float:
        """! @brief non-positive 전체 campaign의 남은 시간을 반환합니다. """
        if self.deadline is None:
            return float("inf")
        remaining = self.deadline - time.monotonic()
        if remaining <= 0.0:
            raise HilFailure(f"전체 180초 timeout: {description}")
        return remaining

    def ensure_time(self, description: str, local_deadline: float | None = None) -> None:
        """! @brief global/local deadline을 모두 넘지 않았는지 확인합니다. """
        self.remaining_global(description)
        if local_deadline is not None and time.monotonic() >= local_deadline:
            raise HilFailure(f"30초 recovery timeout: {description}")

    def bounded_timeout(
        self,
        requested: float,
        description: str,
        local_deadline: float | None = None,
    ) -> float:
        """! @brief 요청 timeout을 global/local deadline 안으로 제한합니다. """
        bounds = [requested, self.remaining_global(description)]
        if local_deadline is not None:
            bounds.append(local_deadline - time.monotonic())
        bounded = min(bounds)
        if bounded <= 0.0:
            self.ensure_time(description, local_deadline)
        return bounded

    def record(self, role: str, raw_text: str) -> Event:
        """! @brief 원문을 검사하고 정제된 한 줄만 JSON/transcript에 기록합니다. """
        sanitized = sanitize_line(raw_text[:800])
        event = Event(
            sequence=len(self.events),
            at_s=round(time.monotonic() - self.started, 3),
            role=role,
            text=sanitized,
        )
        self.events.append(event)
        if self.transcript is not None:
            self.transcript.write(f"{event.at_s:09.3f}|{event.role}|{event.text}\n")
            self.transcript.flush()
        if role in ROLES:
            sync_failure = parse_sync_failure(raw_text)
            expected_sync_failure = (
                sync_failure is not None
                and any(
                    (role, sync_failure[0], sync_failure[1])
                    in allowance.sync_failures
                    for allowance in self.error_windows.values()
                )
            )
            quality_result = parse_quality_result(raw_text)
            expected_quality_rejection = (
                quality_result is not None
                and any(
                    (role, quality_result) in allowance.quality_rejections
                    for allowance in self.error_windows.values()
                )
            )
            unexpected_public_error = (
                PUBLIC_ERROR_PATTERN.search(raw_text) is not None
                and not expected_sync_failure
                and not expected_quality_rejection
            )
            if any(token in raw_text for token in FATAL_TOKENS) or unexpected_public_error:
                raise HilFailure(f"{role} fatal UART: {sanitized}")
        return event

    def arm_error_window(
        self,
        name: str,
        *,
        sync_failures: Sequence[tuple[str, int, int]] = (),
        quality_rejections: Sequence[tuple[str, int]] = (),
    ) -> None:
        """! @brief 다음 action에 필요한 exact 오류만 임시 허용합니다. """
        if name in self.error_windows:
            raise HilFailure(f"오류 window가 이미 열려 있습니다: {name}")
        allowance = ErrorAllowance(
            frozenset(sync_failures), frozenset(quality_rejections)
        )
        if not allowance.sync_failures and not allowance.quality_rejections:
            raise HilFailure(f"빈 오류 window는 열 수 없습니다: {name}")
        self.error_windows[name] = allowance
        self.record("runner", f"error-window name={name} state=armed")

    def disarm_error_window(self, name: str) -> None:
        """! @brief 명시된 오류 허용 window를 즉시 닫습니다. """
        if name not in self.error_windows:
            raise HilFailure(f"열리지 않은 오류 window입니다: {name}")
        del self.error_windows[name]
        self.record("runner", f"error-window name={name} state=disarmed")

    def assert_error_windows_closed(self) -> None:
        """! @brief campaign 종료 시 허용 오류 window가 남지 않았는지 검사합니다. """
        if self.error_windows:
            names = ",".join(sorted(self.error_windows))
            raise HilFailure(f"닫히지 않은 오류 window: {names}")

    def pump(self) -> list[Event]:
        """! @brief 두 UART에서 현재 사용 가능한 byte를 줄 단위로 수집합니다. """
        captured: list[Event] = []
        self.last_pump_had_bytes = False
        for role, stream in self.streams.items():
            count = int(stream.in_waiting)
            if count <= 0:
                continue
            data = stream.read(count)
            if not data:
                continue
            self.last_pump_had_bytes = True
            self.pending[role].extend(data)
            while b"\n" in self.pending[role]:
                raw, _, remainder = self.pending[role].partition(b"\n")
                self.pending[role] = bytearray(remainder)
                text = raw.rstrip(b"\r").decode("utf-8", errors="backslashreplace")
                captured.append(self.record(role, text))
        return captured

    def mark(self, local_deadline: float | None = None) -> int:
        """! @brief byte-quiet와 완전한 줄을 확보한 action 경계를 반환합니다. """
        started = time.monotonic()
        quiet_since: float | None = None
        while True:
            self.ensure_time("UART action 경계", local_deadline)
            self.pump()
            buffered = any(int(stream.in_waiting) > 0 for stream in self.streams.values())
            partial = any(self.pending.values())
            now = time.monotonic()
            if self.last_pump_had_bytes or buffered or partial:
                quiet_since = None
            elif quiet_since is None:
                quiet_since = now
            elif (now - quiet_since) >= self.mark_quiet:
                return len(self.events)
            if (now - started) >= self.mark_maximum:
                raise HilFailure("UART 경계에서 bounded byte quiet를 확보하지 못했습니다.")
            time.sleep(0.003)

    def send(self, role: str, command: str) -> None:
        """! @brief role별 공개 ASCII 한 글자를 완전 기록하고 flush합니다. """
        if role not in ROLES or len(command) != 1 or command not in ALLOWED_COMMANDS[role]:
            raise HilFailure(f"허용되지 않은 공개 명령: {role}:{command!r}")
        self.record(
            "runner",
            f"command board={EXPECTED_BOARD_MAP[role]['board']} value={command}",
        )
        written = self.streams[role].write(command.encode("ascii"))
        self.streams[role].flush()
        if written != 1:
            raise HilFailure(f"{role} UART 명령이 일부만 기록됐습니다.")

    def action(self, role: str, command: str, local_deadline: float | None = None) -> int:
        """! @brief quiet 경계 뒤 공개 명령을 전송하고 경계를 반환합니다. """
        since = self.mark(local_deadline)
        self.send(role, command)
        return since

    def wait_event(
        self,
        predicate: Callable[[Event], bool],
        timeout: float,
        since: int,
        description: str,
        local_deadline: float | None = None,
    ) -> Event:
        """! @brief since 이후 exact event를 bounded timeout 안에서 기다립니다. """
        deadline = time.monotonic() + self.bounded_timeout(
            timeout, description, local_deadline
        )
        cursor = since
        while time.monotonic() < deadline:
            self.ensure_time(description, local_deadline)
            self.pump()
            while cursor < len(self.events):
                event = self.events[cursor]
                cursor += 1
                if predicate(event):
                    return event
            time.sleep(0.004)
        recent = " | ".join(f"{event.role}:{event.text}" for event in self.events[-12:])
        raise HilFailure(f"timeout: {description}; recent={recent}")

    def wait_token(
        self,
        role: str,
        token: str,
        timeout: float,
        since: int,
        local_deadline: float | None = None,
        *,
        allow_reset_noise: bool = False,
    ) -> Event:
        """! @brief role의 exact 공개 token을 기다립니다. """
        return self.wait_event(
            lambda event: event.role == role
            and (
                event.text == token
                or (
                    allow_reset_noise
                    and matches_token_after_reset_noise(event.text, token)
                )
            ),
            timeout,
            since,
            f"{role}:{token}",
            local_deadline,
        )

    def wait_announcement(
        self,
        timeout: float,
        since: int,
        local_deadline: float | None = None,
    ) -> Event:
        """! @brief exact 공개 broadcast announcement를 기다립니다. """
        event = self.wait_event(
            lambda item: item.role == "sink"
            and item.text.startswith("selected public audio name="),
            timeout,
            since,
            "sink public announcement",
            local_deadline,
        )
        verify_announcement(event.text)
        return event

    def wait_received(
        self,
        expected_frames: int,
        timeout: float,
        since: int,
        local_deadline: float | None = None,
    ) -> tuple[Event, ReceivedSample]:
        """! @brief exact frame count의 양수 energy·drop 0 상태를 기다립니다. """
        event = self.wait_event(
            lambda item: item.role == "sink"
            and (sample := parse_received(item.text)) is not None
            and sample.frames == expected_frames,
            timeout,
            since,
            f"sink received={expected_frames}",
            local_deadline,
        )
        sample = parse_received(event.text)
        if sample is None:
            raise HilFailure("내부 received parser 불일치")
        if sample.energy <= 0 or sample.dropped != 0:
            raise HilFailure(f"유효하지 않은 LC3 수신 상태: {event.text}")
        return event, sample

    def reset_source(self, local_deadline: float) -> dict[str, Any]:
        """! @brief 검토된 hash-only helper로 G/source를 reset하고 실행합니다. """
        invocation = (
            sys.executable,
            str(self.reset_helper),
            self.probe_hashes["source"],
            "reset",
            "go",
            "--connect",
            "halt",
        )
        outer_timeout = self.bounded_timeout(
            self.reset_timeout, "source hardware reset", local_deadline
        )
        if outer_timeout <= DEBUG_HELPER_INTERNAL_TIMEOUT:
            raise HilFailure("source reset helper 실행에 20초 초과 예산이 없습니다.")
        try:
            completed = subprocess.run(
                invocation,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="backslashreplace",
                timeout=outer_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise HilFailure("source hash-only reset helper timeout") from error
        except OSError as error:
            raise HilFailure("source hash-only reset helper 실행 실패") from error
        output, diagnostic_failed = inspect_debug_output(
            completed.stdout + completed.stderr
        )
        self.record(
            "runner",
            f"debug board=G action=reset-and-go rc={completed.returncode} output={output}",
        )
        if completed.returncode != 0 or diagnostic_failed:
            raise HilFailure(
                f"source reset helper 실패: rc={completed.returncode} output={output}"
            )
        return {
            "board": "G",
            "action": "reset-and-go",
            "returncode": completed.returncode,
            "sanitized_output": output,
        }


def start_pair(campaign: Campaign, local_deadline: float | None = None) -> dict[str, Any]:
    """! @brief 공개 source/sink를 재시작해 방송과 첫 100 frame을 확인합니다. """
    source_since = campaign.action("source", "r", local_deadline)
    preparing = campaign.wait_token(
        "source", "public audio source preparing", 6.0, source_since, local_deadline
    )
    source_streaming = campaign.wait_token(
        "source", "public audio source streaming", 8.0, source_since, local_deadline
    )
    sink_since = campaign.action("sink", "r", local_deadline)
    scanning = campaign.wait_token(
        "sink", "public audio sink scanning", 6.0, sink_since, local_deadline
    )
    selected = campaign.wait_announcement(10.0, scanning.sequence + 1, local_deadline)
    sink_streaming = campaign.wait_token(
        "sink",
        "public audio sink streaming",
        10.0,
        selected.sequence + 1,
        local_deadline,
    )
    sample_event, sample = campaign.wait_received(
        100, 6.0, sink_streaming.sequence + 1, local_deadline
    )
    return {
        "source_preparing_sequence": preparing.sequence,
        "source_streaming_sequence": source_streaming.sequence,
        "sink_scanning_sequence": scanning.sequence,
        "announcement_sequence": selected.sequence,
        "sink_streaming_sequence": sink_streaming.sequence,
        "baseline_sample_sequence": sample_event.sequence,
        "baseline": asdict(sample),
    }


def run_positive(campaign: Campaign, duration: float) -> dict[str, Any]:
    """! @brief setup 뒤 정확히 180초 동안 LC3 증가·energy·drop을 검증합니다. """
    setup = start_pair(campaign)
    baseline = int(setup["baseline"]["frames"])
    stream_started = time.monotonic()
    stream_deadline = stream_started + duration
    cursor = int(setup["baseline_sample_sequence"]) + 1
    maximum = baseline
    samples = 0
    last_sample_at = stream_started
    while time.monotonic() < stream_deadline:
        campaign.pump()
        while cursor < len(campaign.events):
            event = campaign.events[cursor]
            cursor += 1
            if event.role != "sink":
                continue
            sample = parse_received(event.text)
            if sample is None:
                continue
            if sample.energy <= 0 or sample.dropped != 0:
                raise HilFailure(f"유효하지 않은 LC3 sample: {event.text}")
            if sample.frames <= maximum:
                raise HilFailure(f"LC3 frame counter가 단조 증가하지 않습니다: {event.text}")
            maximum = sample.frames
            samples += 1
            last_sample_at = time.monotonic()
        if (time.monotonic() - last_sample_at) > 3.0:
            raise HilFailure("positive stream 수신 상태가 3초 넘게 정지했습니다.")
        time.sleep(0.004)
    campaign.pump()
    elapsed = time.monotonic() - stream_started
    received_delta = maximum - baseline
    if elapsed < duration:
        raise HilFailure("positive stream duration이 180초보다 짧습니다.")
    if received_delta < int(duration * 80.0):
        raise HilFailure(
            f"LC3 frame 증가 부족: delta={received_delta}, duration={duration}"
        )
    campaign.record(
        "runner",
        f"positive stream_seconds={elapsed:.3f} received_delta={received_delta} dropped=0",
    )
    return {
        "setup": setup,
        "required_stream_duration_seconds": duration,
        "observed_stream_duration_seconds": round(elapsed, 3),
        "baseline_received": baseline,
        "final_received": maximum,
        "received_delta": received_delta,
        "valid_samples_after_baseline": samples,
        "dropped": 0,
    }


def finish_cycle(
    campaign: Campaign, cycle: int, started: float, recovery_timeout: float, mode: str
) -> float:
    """! @brief recovery cycle의 실제 경과가 30초 이하인지 확인합니다. """
    elapsed = time.monotonic() - started
    if elapsed > recovery_timeout or elapsed > MAX_RECOVERY_SECONDS:
        raise HilFailure(f"{mode} cycle {cycle} recovery bound 초과: {elapsed:.3f}s")
    campaign.record(
        "runner", f"{mode} cycle={cycle}/20 elapsed={elapsed:.3f}s pass"
    )
    return round(elapsed, 3)


def run_stop_restart(
    campaign: Campaign, cycles: int, recovery_timeout: float
) -> dict[str, Any]:
    """! @brief 두 역할 stop/restart와 100-frame 복구를 20회 검증합니다. """
    initial = start_pair(campaign)
    elapsed: list[float] = []
    for cycle in range(1, cycles + 1):
        started = time.monotonic()
        deadline = started + recovery_timeout
        since = campaign.action("sink", "s", deadline)
        campaign.wait_token("sink", "public audio sink stopped", 6.0, since, deadline)
        since = campaign.action("source", "s", deadline)
        campaign.wait_token("source", "public audio source stopped", 6.0, since, deadline)
        since = campaign.action("source", "r", deadline)
        campaign.wait_token(
            "source", "public audio source preparing", 6.0, since, deadline
        )
        campaign.wait_token(
            "source", "public audio source streaming", 8.0, since, deadline
        )
        since = campaign.action("sink", "r", deadline)
        scanning = campaign.wait_token(
            "sink", "public audio sink scanning", 6.0, since, deadline
        )
        selected = campaign.wait_announcement(8.0, scanning.sequence + 1, deadline)
        streaming = campaign.wait_token(
            "sink", "public audio sink streaming", 10.0, selected.sequence + 1, deadline
        )
        campaign.wait_received(100, 6.0, streaming.sequence + 1, deadline)
        elapsed.append(
            finish_cycle(campaign, cycle, started, recovery_timeout, "stop-restart")
        )
    return {
        "initial": initial,
        "cycles": cycles,
        "passed": cycles,
        "recovery_seconds": elapsed,
    }


def run_wrong_code(
    campaign: Campaign, cycles: int, recovery_timeout: float
) -> dict[str, Any]:
    """! @brief wrong code -61 거부와 recovery 전 received report 0을 검증합니다. """
    initial = start_pair(campaign)
    results: list[dict[str, Any]] = []
    for cycle in range(1, cycles + 1):
        started = time.monotonic()
        deadline = started + recovery_timeout
        since = campaign.mark(deadline)
        window = f"wrong-code-{cycle}"
        campaign.arm_error_window(
            window,
            sync_failures=(("sink", -61, EXPECTED_FAILURE_STEP),),
        )
        try:
            campaign.send("sink", "w")
            wrong_scan = campaign.wait_token(
                "sink", "public audio sink scanning", 6.0, since, deadline
            )
            failure = campaign.wait_event(
                lambda event: event.role == "sink"
                and parse_sync_failure(event.text) is not None,
                12.0,
                wrong_scan.sequence + 1,
                "wrong-code sync failure",
                deadline,
            )
            parsed = parse_sync_failure(failure.text)
            if parsed != (-61, EXPECTED_FAILURE_STEP):
                raise HilFailure(f"wrong-code reason 불일치: {failure.text}")
        finally:
            campaign.disarm_error_window(window)
        recovery_scan = campaign.wait_token(
            "sink",
            "public audio sink scanning",
            8.0,
            failure.sequence + 1,
            deadline,
        )
        report_lines = [
            event.sequence
            for event in campaign.events[since : recovery_scan.sequence + 1]
            if event.role == "sink" and parse_received(event.text) is not None
        ]
        if report_lines:
            raise HilFailure(f"wrong-code 중 received report 관측: {report_lines}")
        selected = campaign.wait_announcement(8.0, recovery_scan.sequence + 1, deadline)
        streaming = campaign.wait_token(
            "sink", "public audio sink streaming", 10.0, selected.sequence + 1, deadline
        )
        campaign.wait_received(100, 6.0, streaming.sequence + 1, deadline)
        elapsed = finish_cycle(campaign, cycle, started, recovery_timeout, "wrong-code")
        results.append(
            {
                "cycle": cycle,
                "native_reason": parsed[0],
                "failure_step": parsed[1],
                "reported_received_lines_before_recovery": 0,
                "elapsed_seconds": elapsed,
            }
        )
    return {
        "initial": initial,
        "cycles": cycles,
        "rejected": cycles,
        "recovered": cycles,
        "report_level_invalid_frame_lines": 0,
        "individual_unreported_frames": "not_observable_by_public_sketch",
        "cycle_results": results,
    }


def wait_quality_rejection(
    campaign: Campaign, role: str, since: int, deadline: float
) -> Event:
    """! @brief exact stable Error::unsupported(10) 결과만 허용합니다. """
    event = campaign.wait_event(
        lambda item: item.role == role and parse_quality_result(item.text) is not None,
        6.0,
        since,
        f"{role} high quality rejection",
        deadline,
    )
    if parse_quality_result(event.text) != UNSUPPORTED_ERROR_CODE:
        raise HilFailure(f"{role} high quality stable Error 불일치: {event.text}")
    return event


def run_quality(
    campaign: Campaign, cycles: int, recovery_timeout: float
) -> dict[str, Any]:
    """! @brief source/sink high quality exact 거부와 복구를 20회 확인합니다. """
    initial = start_pair(campaign)
    elapsed: list[float] = []
    for cycle in range(1, cycles + 1):
        started = time.monotonic()
        deadline = started + recovery_timeout
        since = campaign.mark(deadline)
        transition_window = f"quality-source-transition-{cycle}"
        source_window = f"quality-source-h-{cycle}"
        campaign.arm_error_window(
            transition_window,
            sync_failures=(("sink", -19, EXPECTED_FAILURE_STEP),),
        )
        try:
            campaign.arm_error_window(
                source_window,
                quality_rejections=(("source", UNSUPPORTED_ERROR_CODE),),
            )
            try:
                campaign.send("source", "h")
                rejected = wait_quality_rejection(
                    campaign, "source", since, deadline
                )
            finally:
                campaign.disarm_error_window(source_window)
            campaign.wait_token(
                "source",
                "public audio source preparing",
                6.0,
                rejected.sequence + 1,
                deadline,
            )
            campaign.wait_token(
                "source",
                "public audio source streaming",
                8.0,
                rejected.sequence + 1,
                deadline,
            )
            since = campaign.mark(deadline)
            campaign.disarm_error_window(transition_window)
            sink_window = f"quality-sink-h-{cycle}"
            campaign.arm_error_window(
                sink_window,
                quality_rejections=(("sink", UNSUPPORTED_ERROR_CODE),),
            )
            try:
                campaign.send("sink", "h")
                rejected = wait_quality_rejection(
                    campaign, "sink", since, deadline
                )
            finally:
                campaign.disarm_error_window(sink_window)
            scanning = campaign.wait_token(
                "sink",
                "public audio sink scanning",
                6.0,
                rejected.sequence + 1,
                deadline,
            )
            selected = campaign.wait_announcement(
                8.0, scanning.sequence + 1, deadline
            )
            streaming = campaign.wait_token(
                "sink",
                "public audio sink streaming",
                10.0,
                selected.sequence + 1,
                deadline,
            )
            campaign.wait_received(100, 6.0, streaming.sequence + 1, deadline)
        finally:
            if transition_window in campaign.error_windows:
                campaign.disarm_error_window(transition_window)
        elapsed.append(finish_cycle(campaign, cycle, started, recovery_timeout, "quality"))
    return {
        "initial": initial,
        "cycles": cycles,
        "source_unsupported_code": UNSUPPORTED_ERROR_CODE,
        "sink_unsupported_code": UNSUPPORTED_ERROR_CODE,
        "source_rejected": cycles,
        "sink_rejected": cycles,
        "recovered": cycles,
        "recovery_seconds": elapsed,
    }


def run_sync_loss(
    campaign: Campaign, cycles: int, recovery_timeout: float
) -> dict[str, Any]:
    """! @brief G reset sync loss와 새 session 100-frame 복구를 20회 확인합니다. """
    initial = start_pair(campaign)
    results: list[dict[str, Any]] = []
    for cycle in range(1, cycles + 1):
        started = time.monotonic()
        deadline = started + recovery_timeout
        since = campaign.mark(deadline)
        window = f"sync-loss-{cycle}"
        campaign.arm_error_window(
            window,
            sync_failures=(
                ("sink", -8, EXPECTED_FAILURE_STEP),
                ("sink", -104, EXPECTED_FAILURE_STEP),
            ),
        )
        try:
            reset = campaign.reset_source(deadline)
            failure = campaign.wait_event(
                lambda event: event.role == "sink"
                and parse_sync_failure(event.text) is not None,
                12.0,
                since,
                "source reset sync failure",
                deadline,
            )
            parsed = parse_sync_failure(failure.text)
            if (
                parsed is None
                or parsed[0] not in {-8, -104}
                or parsed[1] != EXPECTED_FAILURE_STEP
            ):
                raise HilFailure(f"sync-loss reason 불일치: {failure.text}")
        finally:
            campaign.disarm_error_window(window)
        campaign.wait_token(
            "source",
            "public audio source preparing",
            8.0,
            since,
            deadline,
            allow_reset_noise=True,
        )
        campaign.wait_token(
            "source", "public audio source streaming", 8.0, since, deadline
        )
        scanning = campaign.wait_token(
            "sink",
            "public audio sink scanning",
            8.0,
            failure.sequence + 1,
            deadline,
        )
        selected = campaign.wait_announcement(8.0, scanning.sequence + 1, deadline)
        streaming = campaign.wait_token(
            "sink", "public audio sink streaming", 10.0, selected.sequence + 1, deadline
        )
        campaign.wait_received(100, 6.0, streaming.sequence + 1, deadline)
        elapsed = finish_cycle(campaign, cycle, started, recovery_timeout, "sync-loss")
        results.append(
            {
                "cycle": cycle,
                "native_reason": parsed[0],
                "failure_step": parsed[1],
                "elapsed_seconds": elapsed,
                "reset": reset,
            }
        )
    return {
        "initial": initial,
        "cycles": cycles,
        "detected": cycles,
        "recovered": cycles,
        "cycle_results": results,
    }


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief closure HIL의 exact provenance와 시간 인자를 정의합니다. """
    parser = argparse.ArgumentParser(description="공개 PBP 2보드 closure HIL")
    parser.add_argument(
        "mode", choices=("positive", "stop-restart", "wrong-code", "quality", "sync-loss")
    )
    for role in ROLES:
        parser.add_argument(f"--{role}-port", required=True)
        parser.add_argument(f"--{role}-probe-sha256", required=True)
        parser.add_argument(f"--{role}-image", type=Path, required=True)
        parser.add_argument(f"--{role}-image-sha256", required=True)
        parser.add_argument(f"--{role}-example-sha256", required=True)
        parser.add_argument(f"--{role}-flash-receipt", type=Path, required=True)
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--duration", type=float, default=POSITIVE_STREAM_SECONDS)
    parser.add_argument("--total-timeout", type=float, default=MAX_CAMPAIGN_SECONDS)
    parser.add_argument("--recovery-timeout", type=float, default=MAX_RECOVERY_SECONDS)
    parser.add_argument("--reset-timeout", type=float, default=MAX_RECOVERY_SECONDS)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument(
        "--reset-helper",
        type=Path,
        default=Path(__file__).with_name("pyocd_commands_by_hash.py"),
    )
    parser.add_argument(
        "--flash-helper",
        type=Path,
        default=Path(__file__).with_name("flash_by_probe_hash.py"),
    )
    return parser.parse_args(arguments)


def validate_arguments(args: argparse.Namespace) -> dict[str, Any]:
    """! @brief 실행 전 exact map·hash·경로·시간 계약을 검사합니다. """
    validate_contract_values(
        args.mode,
        args.cycles,
        args.duration,
        args.total_timeout,
        args.recovery_timeout,
        args.reset_timeout,
    )
    if args.baud != 115200:
        raise HilFailure("공개 예제 baud는 정확히 115200이어야 합니다.")
    if REVISION_PATTERN.fullmatch(args.core_revision) is None:
        raise HilFailure("core revision은 40자리 소문자 commit hex여야 합니다.")
    core_root = args.core_root.resolve()
    if not core_root.is_dir():
        raise HilFailure(f"Core root가 없습니다: {core_root}")

    ports: dict[str, str] = {}
    probe_hashes: dict[str, str] = {}
    images: dict[str, Path] = {}
    image_hashes: dict[str, str] = {}
    expected_source_hashes: dict[str, str] = {}
    for role in ROLES:
        port = getattr(args, f"{role}_port")
        probe_hash = getattr(args, f"{role}_probe_sha256")
        image = getattr(args, f"{role}_image").resolve()
        expected_image_hash = getattr(args, f"{role}_image_sha256")
        expected_source_hash = getattr(args, f"{role}_example_sha256")
        expected = EXPECTED_BOARD_MAP[role]
        if port.casefold() != str(expected["port"]).casefold():
            raise HilFailure(f"{role} COM은 {expected['port']}여야 합니다.")
        if HASH_PATTERN.fullmatch(probe_hash) is None or probe_hash != expected["probe_sha256"]:
            raise HilFailure(f"{role} probe SHA-256 mapping이 다릅니다.")
        if not image.is_file():
            raise HilFailure(f"{role} image가 없습니다: {image}")
        if HASH_PATTERN.fullmatch(expected_image_hash) is None:
            raise HilFailure(f"{role} image SHA-256 형식이 잘못되었습니다.")
        actual_image_hash = sha256_file(image)
        if actual_image_hash != expected_image_hash:
            raise HilFailure(
                f"{role} image hash 불일치: expected={expected_image_hash}, "
                f"actual={actual_image_hash}"
            )
        if HASH_PATTERN.fullmatch(expected_source_hash) is None:
            raise HilFailure(f"{role} example SHA-256 형식이 잘못되었습니다.")
        ports[role] = port
        probe_hashes[role] = probe_hash
        images[role] = image
        image_hashes[role] = actual_image_hash
        expected_source_hashes[role] = expected_source_hash
    if len(set(ports.values())) != len(ROLES) or len(set(probe_hashes.values())) != len(ROLES):
        raise HilFailure("source/sink COM과 probe hash는 서로 달라야 합니다.")

    helper = args.reset_helper.resolve()
    reviewed_helper = Path(__file__).with_name("pyocd_commands_by_hash.py").resolve()
    if helper != reviewed_helper or not helper.is_file():
        raise HilFailure("reviewed sibling SHA-256 helper만 허용합니다.")
    helper_hash = sha256_file(helper)
    if helper_hash != EXPECTED_DEBUG_HELPER_SHA256:
        raise HilFailure("reviewed sibling helper hash가 변경되었습니다.")

    flash_helper = args.flash_helper.resolve()
    reviewed_flash_helper = Path(__file__).with_name("flash_by_probe_hash.py").resolve()
    if flash_helper != reviewed_flash_helper or not flash_helper.is_file():
        raise HilFailure("reviewed sibling flash helper만 허용합니다.")
    flash_helper_hash = sha256_file(flash_helper)
    if flash_helper_hash != EXPECTED_FLASH_HELPER_SHA256:
        raise HilFailure("reviewed sibling flash helper hash가 변경되었습니다.")

    transcript = args.transcript.resolve()
    summary = args.summary.resolve()
    validate_output_paths(transcript, summary)
    flash_receipts = {
        role: getattr(args, f"{role}_flash_receipt").resolve() for role in ROLES
    }
    all_outputs = [transcript, summary, *flash_receipts.values()]
    if len(set(all_outputs)) != len(all_outputs):
        raise HilFailure("transcript·summary·flash receipt 경로는 모두 달라야 합니다.")
    for role, receipt in flash_receipts.items():
        if receipt.exists():
            raise HilFailure(f"기존 {role} flash receipt를 덮어쓰지 않습니다.")
    return {
        "core_root": core_root,
        "ports": ports,
        "probe_hashes": probe_hashes,
        "images": images,
        "image_hashes": image_hashes,
        "expected_source_hashes": expected_source_hashes,
        "helper": helper,
        "helper_hash": helper_hash,
        "flash_helper": flash_helper,
        "flash_helper_hash": flash_helper_hash,
        "flash_receipts": flash_receipts,
        "transcript": transcript,
        "summary": summary,
    }


def require_failure(action: Callable[[], Any], description: str) -> None:
    """! @brief self-test action이 HilFailure로 닫히는지 확인합니다. """
    try:
        action()
    except HilFailure:
        return
    raise HilFailure(f"fixture fail-closed 실패: {description}")


def run_fixture_tests() -> int:
    """! @brief hardware 없이 parser·경계·오류·no-overwrite fixture를 실행합니다. """
    fixture_count = 0
    validate_contract_values("positive", 20, 180.0, 180.0, 30.0, 30.0)
    fixture_count += 1
    require_failure(
        lambda: validate_contract_values("positive", 19, 180.0, 180.0, 30.0, 30.0),
        "cycles denominator",
    )
    fixture_count += 1
    require_failure(
        lambda: validate_contract_values("positive", 20, 179.0, 180.0, 30.0, 30.0),
        "positive duration",
    )
    fixture_count += 1
    require_failure(
        lambda: validate_contract_values("sync-loss", 20, 180.0, 181.0, 30.0, 30.0),
        "global timeout",
    )
    fixture_count += 1
    require_failure(
        lambda: validate_contract_values("sync-loss", 20, 180.0, 180.0, 31.0, 30.0),
        "recovery timeout",
    )
    fixture_count += 1
    require_failure(
        lambda: validate_contract_values("sync-loss", 20, 180.0, 180.0, 30.0, 20.0),
        "debug helper outer timeout",
    )
    fixture_count += 1

    late_output = ("clean output\n" * 100) + "Error probing AP#4: No ACK\nCOMMANDER_RC=0"
    evidence, failed = inspect_debug_output(late_output)
    if not failed or len(evidence) > DEBUG_EVIDENCE_LIMIT or "\n" in evidence:
        raise HilFailure("fixture late debug error 검사 실패")
    fixture_count += 1
    good_output, failed = inspect_debug_output("reset ok\nCOMMANDER_RC=0")
    if failed or "COMMANDER_RC=0" not in good_output:
        raise HilFailure("fixture debug success 검사 실패")
    fixture_count += 1

    raw = "peer=AA:BB:CC:DD:EE:FF uid=0123456789abcdef0123456789abcdef"
    sanitized = sanitize_line(raw)
    if "AA:BB" in sanitized or "0123456789abcdef" in sanitized:
        raise HilFailure("fixture identifier 정제 실패")
    fixture_count += 1
    sample = parse_received("public audio received=100 energy=42 dropped=0")
    if sample != ReceivedSample(100, 42, 0):
        raise HilFailure("fixture received parser 실패")
    fixture_count += 1
    sync_failure = parse_sync_failure("public audio sync failed: -61 step=11")
    if sync_failure != (-61, EXPECTED_FAILURE_STEP):
        raise HilFailure("fixture sync failure step 검사 실패")
    fixture_count += 1
    token = "public audio source preparing"
    if not matches_token_after_reset_noise(r"\xff\xbc" + token, token):
        raise HilFailure("fixture reset UART noise token 검사 실패")
    if not matches_token_after_reset_noise(r"&\xfe" + token, token):
        raise HilFailure("fixture mixed reset UART noise token 검사 실패")
    if not matches_token_after_reset_noise(r"\xFE" + token, token):
        raise HilFailure("fixture uppercase reset UART noise token 검사 실패")
    if not matches_token_after_reset_noise("?6" + token, token):
        raise HilFailure("fixture printable reset UART noise token 검사 실패")
    if not matches_token_after_reset_noise("\0" + r"\xff" + token, token):
        raise HilFailure("fixture NUL reset UART noise token 검사 실패")
    if not matches_token_after_reset_noise(r"\xfe\xfc\xdf" + token, token):
        raise HilFailure("fixture 3-byte reset UART noise token 검사 실패")
    if not matches_token_after_reset_noise(
        r"\xe4\xf0\xfe\xff\xff\xfc" + token, token
    ):
        raise HilFailure("fixture 6-byte reset UART noise token 검사 실패")
    if not matches_token_after_reset_noise(
        r"\xfc" + "\x7f" + r"\xfe\xff\xff\xfc\xff" + token, token
    ):
        raise HilFailure("fixture mixed control reset UART noise token 검사 실패")
    if not matches_token_after_reset_noise(
        "0" + r"\x9c\xfe\xff\xfe" + token, token
    ):
        raise HilFailure("fixture printable mixed reset UART noise token 검사 실패")
    if matches_token_after_reset_noise(
        (r"\xff" * 17) + token, token
    ):
        raise HilFailure("fixture 17-byte reset UART noise token 거부 실패")
    if not matches_token_after_reset_noise("?" + r"\xfe\xfc\xdf" + token, token):
        raise HilFailure("fixture 4-byte reset UART noise token 검사 실패")
    if matches_token_after_reset_noise(r"\x41" + token, token):
        raise HilFailure("fixture escaped ASCII token prefix 거부 실패")
    if matches_token_after_reset_noise(r"\xg1" + token, token):
        raise HilFailure("fixture invalid escape token 거부 실패")
    if matches_token_after_reset_noise("ABCDE" + token, token):
        raise HilFailure("fixture overlong reset prefix 거부 실패")
    fixture_count += 1
    if FLASH_HELPER_OUTER_TIMEOUT <= (
        FLASH_HELPER_LOAD_TIMEOUT + FLASH_HELPER_RESET_TIMEOUT
    ):
        raise HilFailure("fixture flash outer/internal timeout ordering 실패")
    fixture_count += 1

    class FixtureStream:
        """! @brief UART action boundary용 메모리 byte stream입니다. """

        def __init__(self, payload: bytes = b"", continuous: bool = False) -> None:
            self.payload = bytearray(payload)
            self.continuous = continuous

        @property
        def in_waiting(self) -> int:
            """! @brief 즉시 읽을 fixture byte 수를 반환합니다. """
            return len(self.payload) or (1 if self.continuous else 0)

        def read(self, size: int) -> bytes:
            """! @brief 저장 byte 또는 continuous fixture byte를 소비합니다. """
            if self.payload:
                count = min(size, len(self.payload))
                data = bytes(self.payload[:count])
                del self.payload[:count]
                return data
            return b"x" if self.continuous else b""

    def fixture_campaign(
        payload: bytes, continuous: bool = False, mode: str = "positive"
    ) -> Campaign:
        campaign = Campaign(
            mode,
            None,
            {"source": "COM10", "sink": "COM14"},
            {role: str(EXPECTED_BOARD_MAP[role]["probe_sha256"]) for role in ROLES},
            Path("unused.log"),
            Path("helper.py"),
            1.0,
            2.0,
            mark_quiet=0.005,
            mark_maximum=0.040,
        )
        campaign.streams = {
            "source": FixtureStream(payload, continuous),
            "sink": FixtureStream(),
        }
        campaign.transcript = io.StringIO()
        return campaign

    noisy_payload = b"\xffpublic audio source preparing\n"
    require_failure(
        lambda: fixture_campaign(noisy_payload).wait_token(
            "source", token, 0.020, 0
        ),
        "non-reset token noise",
    )
    noisy_campaign = fixture_campaign(noisy_payload)
    noisy_event = noisy_campaign.wait_token(
        "source", token, 0.020, 0, allow_reset_noise=True
    )
    if noisy_event.text != r"\xff" + token:
        raise HilFailure("fixture reset opt-in event 불일치")
    fixture_count += 1

    stale_campaign = fixture_campaign(b"public audio sink streaming\n")
    boundary = stale_campaign.mark()
    if boundary != 1:
        raise HilFailure("fixture stale drain boundary 실패")
    require_failure(
        lambda: stale_campaign.wait_token(
            "source", "public audio sink streaming", 0.020, boundary
        ),
        "stale event reuse",
    )
    fixture_count += 1
    require_failure(lambda: fixture_campaign(b"partial").mark(), "partial line")
    fixture_count += 1
    require_failure(
        lambda: fixture_campaign(b"", continuous=True).mark(), "continuous input"
    )
    fixture_count += 1
    fatal_campaign = fixture_campaign(b"")
    require_failure(
        lambda: fatal_campaign.record("source", "public audio send failed: -5"),
        "send failure fatal",
    )
    fixture_count += 1
    require_failure(
        lambda: fatal_campaign.record("sink", "public audio error: unexpected"),
        "generic public error fatal",
    )
    fixture_count += 1
    wrong_campaign = fixture_campaign(b"", mode="wrong-code")
    require_failure(
        lambda: wrong_campaign.record("sink", "public audio sync failed: -61 step=11"),
        "wrong-code unarmed",
    )
    fixture_count += 1
    wrong_campaign.arm_error_window(
        "fixture-wrong",
        sync_failures=(("sink", -61, EXPECTED_FAILURE_STEP),),
    )
    wrong_campaign.record("sink", "public audio sync failed: -61 step=11")
    require_failure(
        lambda: wrong_campaign.record("sink", "public audio sync failed: -61 step=10"),
        "wrong-code failure step",
    )
    wrong_campaign.disarm_error_window("fixture-wrong")
    require_failure(
        lambda: wrong_campaign.record("sink", "public audio sync failed: -61 step=11"),
        "wrong-code disarmed",
    )
    wrong_campaign.assert_error_windows_closed()
    fixture_count += 1

    quality_campaign = fixture_campaign(b"", mode="quality")
    require_failure(
        lambda: quality_campaign.record("source", "high quality rejected: 10"),
        "quality unarmed",
    )
    quality_campaign.arm_error_window(
        "fixture-source-h",
        quality_rejections=(("source", UNSUPPORTED_ERROR_CODE),),
    )
    quality_campaign.record("source", "high quality rejected: 10")
    require_failure(
        lambda: quality_campaign.record("source", "high quality rejected: 9"),
        "quality stable error",
    )
    require_failure(
        lambda: quality_campaign.record("sink", "high quality rejected: 10"),
        "quality wrong role",
    )
    quality_campaign.disarm_error_window("fixture-source-h")
    quality_campaign.arm_error_window(
        "fixture-source-transition",
        sync_failures=(("sink", -19, EXPECTED_FAILURE_STEP),),
    )
    quality_campaign.record("sink", "public audio sync failed: -19 step=11")
    require_failure(
        lambda: quality_campaign.record(
            "source", "public audio sync failed: -19 step=11"
        ),
        "quality transition wrong role",
    )
    require_failure(
        lambda: quality_campaign.record(
            "sink", "public audio sync failed: -8 step=11"
        ),
        "quality transition wrong reason",
    )
    quality_campaign.disarm_error_window("fixture-source-transition")
    quality_campaign.arm_error_window(
        "fixture-sink-h",
        quality_rejections=(("sink", UNSUPPORTED_ERROR_CODE),),
    )
    require_failure(
        lambda: quality_campaign.record(
            "sink", "public audio sync failed: -19 step=11"
        ),
        "sink-h recovery cannot reuse source transition allowance",
    )
    quality_campaign.record("sink", "high quality rejected: 10")
    quality_campaign.disarm_error_window("fixture-sink-h")
    quality_campaign.assert_error_windows_closed()
    fixture_count += 1

    sync_campaign = fixture_campaign(b"", mode="sync-loss")
    sync_campaign.arm_error_window(
        "fixture-sync-loss",
        sync_failures=(
            ("sink", -8, EXPECTED_FAILURE_STEP),
            ("sink", -104, EXPECTED_FAILURE_STEP),
        ),
    )
    sync_campaign.record("sink", "public audio sync failed: -104 step=11")
    sync_campaign.disarm_error_window("fixture-sync-loss")
    require_failure(
        lambda: sync_campaign.record(
            "sink", "public audio sync failed: -104 step=11"
        ),
        "sync-loss disarmed",
    )
    sync_campaign.assert_error_windows_closed()
    fixture_count += 1

    exact_hashes = tuple(str(EXPECTED_BOARD_MAP[role]["probe_sha256"]) for role in ROLES)
    inventory = validate_probe_inventory(exact_hashes)
    if inventory["expected_hash_matches"] != {"source": 1, "sink": 1}:
        raise HilFailure("fixture probe inventory 실패")
    fixture_count += 1
    require_failure(
        lambda: validate_probe_inventory((exact_hashes[0],)), "missing sink probe"
    )
    fixture_count += 1

    usb_entries = tuple(
        (
            str(EXPECTED_USB_PORT_MAP[role][f"{kind}_port"]),
            str(EXPECTED_USB_PORT_MAP[role]["serial_sha256"]),
        )
        for role in ROLES
        for kind in ("target", "aux")
    )
    usb_inventory = validate_usb_port_hashes(usb_entries)
    if usb_inventory["required_port_count"] != 4:
        raise HilFailure("fixture USB COM inventory 실패")
    fixture_count += 1
    require_failure(
        lambda: validate_usb_port_hashes(usb_entries[:-1]), "missing aux COM"
    )
    fixture_count += 1

    with tempfile.TemporaryDirectory(prefix="pbp-hil-") as directory:
        root = Path(directory)
        transcript = root / "transcript.log"
        summary = root / "summary.json"
        transcript.open("x", encoding="utf-8").close()
        require_failure(
            lambda: validate_output_paths(transcript, summary), "transcript overwrite"
        )
        summary.open("x", encoding="utf-8").close()
        require_failure(
            lambda: validate_output_paths(root / "new.log", summary), "summary overwrite"
        )
        image = (root / "image.hex").resolve()
        image.write_bytes(b"fixture-image")
        image_hash = sha256_file(image)
        flash_receipt = (root / "flash.json").resolve()
        flash_document = {
            "schema": "nucode.probe-flash-receipt.v1",
            "status": "PASS",
            "result": "image_programmed_and_hardware_reset",
            "role": "source",
            "probe_sha256": exact_hashes[0],
            "image_path": str(image),
            "image_sha256": image_hash,
            "core_revision": "a" * 40,
            "helper_path": str(
                Path(__file__).with_name("flash_by_probe_hash.py").resolve()
            ),
            "helper_sha256": EXPECTED_FLASH_HELPER_SHA256,
            "started_at": "2026-09-20T00:00:00+00:00",
            "finished_at": "2026-09-20T00:00:01+00:00",
            "programmed_bytes": 123,
            "load": {
                "returncode": 0,
                "timeout_seconds": FLASH_HELPER_LOAD_TIMEOUT,
                "diagnostic_failure": False,
            },
            "reset": {
                "returncode": 0,
                "timeout_seconds": FLASH_HELPER_RESET_TIMEOUT,
                "diagnostic_failure": False,
                "method": "hardware",
            },
            "raw_probe_identifiers_recorded": False,
            "existing_files_overwritten": False,
        }
        flash_receipt.write_text(
            json.dumps(flash_document), encoding="utf-8"
        )
        verified_receipt = verify_flash_receipt(
            flash_receipt,
            "source",
            exact_hashes[0],
            image,
            image_hash,
            "a" * 40,
            Path(__file__).with_name("flash_by_probe_hash.py").resolve(),
            EXPECTED_FLASH_HELPER_SHA256,
        )
        if verified_receipt["programmed_bytes"] != 123:
            raise HilFailure("fixture flash receipt 검증 실패")
    fixture_count += 1

    helper = Path(__file__).with_name("pyocd_commands_by_hash.py").resolve()
    if sha256_file(helper) != EXPECTED_DEBUG_HELPER_SHA256:
        raise HilFailure("fixture reviewed helper hash 실패")
    fixture_count += 1
    flash_helper = Path(__file__).with_name("flash_by_probe_hash.py").resolve()
    if sha256_file(flash_helper) != EXPECTED_FLASH_HELPER_SHA256:
        raise HilFailure("fixture reviewed flash helper hash 실패")
    fixture_count += 1
    print(f"M31_PBP_HIL_SELF_TEST=PASS;FIXTURES={fixture_count};HARDWARE=UNTOUCHED")
    return 0


def run_hil(args: argparse.Namespace) -> int:
    """! @brief 실제 HIL을 실행하고 구조화된 no-overwrite 증적을 남깁니다. """
    validated = validate_arguments(args)
    core_root: Path = validated["core_root"]
    runner_path = Path(__file__).resolve()
    runner_hash = sha256_file(runner_path)
    source_hashes = verify_source(core_root, args.core_revision)
    if source_hashes != validated["expected_source_hashes"]:
        raise HilFailure(
            f"공개 sketch hash 불일치: expected={validated['expected_source_hashes']}, "
            f"actual={source_hashes}"
        )
    probe_preflight = preflight_live_probes()
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as error:
        raise HilFailure("실제 HIL에는 pyserial이 필요합니다.") from error
    usb_port_preflight = preflight_usb_ports(list_ports)
    flash_receipts = {
        role: invoke_flash_helper(
            validated["flash_helper"],
            validated["flash_helper_hash"],
            role,
            validated["probe_hashes"][role],
            validated["images"][role],
            validated["image_hashes"][role],
            args.core_revision,
            validated["flash_receipts"][role],
        )
        for role in ROLES
    }
    if verify_source(core_root, args.core_revision) != source_hashes:
        raise HilFailure("flash 중 공개 source가 변경되었습니다.")
    if any(
        sha256_file(validated["images"][role]) != validated["image_hashes"][role]
        for role in ROLES
    ):
        raise HilFailure("flash 중 role image가 변경되었습니다.")
    if sha256_file(validated["helper"]) != validated["helper_hash"]:
        raise HilFailure("flash 중 reviewed debug helper가 변경되었습니다.")
    if (
        sha256_file(validated["flash_helper"])
        != validated["flash_helper_hash"]
    ):
        raise HilFailure("flash 중 reviewed flash helper가 변경되었습니다.")
    if sha256_file(runner_path) != runner_hash:
        raise HilFailure("flash 중 runner가 변경되었습니다.")

    started_at = utc_now()
    status = "FAIL"
    error_text: str | None = None
    result: dict[str, Any] = {}
    campaign = Campaign(
        args.mode,
        serial,
        validated["ports"],
        validated["probe_hashes"],
        validated["transcript"],
        validated["helper"],
        args.reset_timeout,
        None if args.mode == "positive" else args.total_timeout,
    )
    try:
        with campaign:
            if args.mode == "positive":
                result = run_positive(campaign, args.duration)
            elif args.mode == "stop-restart":
                result = run_stop_restart(campaign, args.cycles, args.recovery_timeout)
            elif args.mode == "wrong-code":
                result = run_wrong_code(campaign, args.cycles, args.recovery_timeout)
            elif args.mode == "quality":
                result = run_quality(campaign, args.cycles, args.recovery_timeout)
            else:
                result = run_sync_loss(campaign, args.cycles, args.recovery_timeout)
            campaign.assert_error_windows_closed()

            final_source_hashes = verify_source(core_root, args.core_revision)
            if final_source_hashes != source_hashes:
                raise HilFailure("campaign 중 공개 source가 변경되었습니다.")
            final_image_hashes = {
                role: sha256_file(path) for role, path in validated["images"].items()
            }
            if final_image_hashes != validated["image_hashes"]:
                raise HilFailure("campaign 중 role image가 변경되었습니다.")
            if sha256_file(validated["helper"]) != validated["helper_hash"]:
                raise HilFailure("campaign 중 reviewed helper가 변경되었습니다.")
            if (
                sha256_file(validated["flash_helper"])
                != validated["flash_helper_hash"]
            ):
                raise HilFailure("campaign 중 reviewed flash helper가 변경되었습니다.")
            for role in ROLES:
                receipt = validated["flash_receipts"][role]
                if sha256_file(receipt) != flash_receipts[role]["sha256"]:
                    raise HilFailure(f"campaign 중 {role} flash receipt가 변경되었습니다.")
            if sha256_file(runner_path) != runner_hash:
                raise HilFailure("campaign 중 runner가 변경되었습니다.")
            campaign.ensure_time("campaign 종료 검증")
            campaign_elapsed = time.monotonic() - campaign.started
            if args.mode != "positive" and campaign_elapsed > args.total_timeout:
                raise HilFailure(f"전체 campaign 180초 상한 초과: {campaign_elapsed:.3f}s")
            result["campaign_elapsed_seconds"] = round(campaign_elapsed, 3)
            status = "PASS"
    except Exception as error:
        error_text = bounded_sanitized_text(str(error))

    transcript_path: Path = validated["transcript"]
    transcript_hash = sha256_file(transcript_path) if transcript_path.is_file() else None
    final_provenance: dict[str, Any]
    try:
        rechecked_source_hashes = verify_source(core_root, args.core_revision)
        rechecked_image_hashes = {
            role: sha256_file(path) for role, path in validated["images"].items()
        }
        rechecked_debug_helper_hash = sha256_file(validated["helper"])
        rechecked_flash_helper_hash = sha256_file(validated["flash_helper"])
        rechecked_runner_hash = sha256_file(runner_path)
        rechecked_receipt_hashes = {
            role: sha256_file(validated["flash_receipts"][role]) for role in ROLES
        }
        if rechecked_source_hashes != source_hashes:
            raise HilFailure("종료 후 공개 source hash가 변경되었습니다.")
        if rechecked_image_hashes != validated["image_hashes"]:
            raise HilFailure("종료 후 role image hash가 변경되었습니다.")
        if rechecked_debug_helper_hash != validated["helper_hash"]:
            raise HilFailure("종료 후 reviewed debug helper hash가 변경되었습니다.")
        if rechecked_flash_helper_hash != validated["flash_helper_hash"]:
            raise HilFailure("종료 후 reviewed flash helper hash가 변경되었습니다.")
        if rechecked_runner_hash != runner_hash:
            raise HilFailure("종료 후 runner hash가 변경되었습니다.")
        if any(
            rechecked_receipt_hashes[role] != flash_receipts[role]["sha256"]
            for role in ROLES
        ):
            raise HilFailure("종료 후 flash receipt hash가 변경되었습니다.")
        final_provenance = {
            "verified": True,
            "core_revision": args.core_revision,
            "public_example_sha256": rechecked_source_hashes,
            "image_sha256": rechecked_image_hashes,
            "debug_helper_sha256": rechecked_debug_helper_hash,
            "flash_helper_sha256": rechecked_flash_helper_hash,
            "runner_sha256": rechecked_runner_hash,
            "flash_receipt_sha256": rechecked_receipt_hashes,
        }
    except Exception as error:
        status = "FAIL"
        provenance_error = bounded_sanitized_text(str(error))
        final_provenance = {"verified": False, "error": provenance_error}
        if error_text is None:
            error_text = provenance_error
        else:
            error_text = bounded_sanitized_text(
                f"{error_text}; final provenance recheck: {provenance_error}"
            )
    events = [asdict(event) for event in campaign.events]
    document = {
        "schema": "nucode.m31.pbp-hil.v2",
        "status": status,
        "mode": args.mode,
        "started_at": started_at,
        "finished_at": utc_now(),
        "core_revision": args.core_revision,
        "source_clean": final_provenance["verified"],
        "public_example_sha256": source_hashes,
        "runner": {"path": str(runner_path), "sha256": runner_hash},
        "debug_helper": {
            "path": str(validated["helper"]),
            "sha256": validated["helper_hash"],
            "raw_probe_identifiers_recorded": False,
        },
        "flash_helper": {
            "path": str(validated["flash_helper"]),
            "sha256": validated["flash_helper_hash"],
            "outer_timeout_seconds": FLASH_HELPER_OUTER_TIMEOUT,
        },
        "flash_receipts": flash_receipts,
        "final_provenance": final_provenance,
        "probe_preflight": probe_preflight,
        "usb_port_preflight": usb_port_preflight,
        "board_map": {
            role: {
                "board": EXPECTED_BOARD_MAP[role]["board"],
                "port": validated["ports"][role],
                "probe_sha256": validated["probe_hashes"][role],
                "image_path": str(validated["images"][role]),
                "image_sha256": validated["image_hashes"][role],
            }
            for role in ROLES
        },
        "runner_behavior": {
            "flashes_devices": True,
            "power_cycles_devices": False,
            "interactive_input": False,
            "opens_only_explicit_com_ports": True,
            "raw_probe_identifiers_recorded": False,
            "existing_files_overwritten": False,
        },
        "time_contract": {
            "positive_stream_duration_seconds": POSITIVE_STREAM_SECONDS,
            "non_positive_campaign_timeout_seconds": args.total_timeout,
            "recovery_timeout_seconds": args.recovery_timeout,
            "cycles": args.cycles,
        },
        "transcript": {
            "path": str(transcript_path),
            "sha256": transcript_hash,
            "event_count": len(events),
        },
        "result": result,
        "events": events,
        "error": error_text,
    }
    summary_path: Path = validated["summary"]
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with summary_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except FileExistsError as error:
        raise HilFailure("종료 시 summary가 생겨 덮어쓰지 않았습니다.") from error

    print(
        f"M31_PBP_{args.mode.upper().replace('-', '_')}={status};"
        f"EVENTS={len(events)};SUMMARY={summary_path}"
    )
    if status != "PASS":
        print(error_text, file=sys.stderr)
        return 1
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief self-test 또는 실제 closure HIL을 실행합니다. """
    selected = list(sys.argv[1:] if arguments is None else arguments)
    if selected == ["self-test"]:
        return run_fixture_tests()
    return run_hil(parse_arguments(arguments))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HilFailure as error:
        print(f"M31_PBP_HIL=FAIL;ERROR={bounded_sanitized_text(str(error))}", file=sys.stderr)
        raise SystemExit(2) from error
