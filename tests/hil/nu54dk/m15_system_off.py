#!/usr/bin/env python3
"""! @brief M15 timed GRTC와 SW0 System OFF wake를 한 수동 세션에서 검증합니다. """

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
from typing import Any, Callable, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY = HIL_DIRECTORY.parents[2]
BOARD_ROOT = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m15_wake"
MAX_TRANSCRIPT_BYTES = 131072
MINIMUM_TIMED_WAKE_MS = 1500
MAXIMUM_TIMED_WAKE_MS = 10000
MINIMUM_BUTTON_PROMPT_MS = 2000
DEFAULT_RESULT_TIMEOUT_SECONDS = 240.0
RESET_LOW_POWER_WAKE = 1 << 7
RESET_DEBUG = 1 << 5
RESET_CLOCK = 1 << 11
NONCE_PATTERN = rb"([0-9a-f]{32})"

if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from m6_serial_echo import (  # noqa: E402
    DEFAULT_BAUD_RATE,
    DaplinkVolume,
    detail_value,
    find_daplink_volume,
    find_serial_port,
    import_pyserial,
    normalize_board_id,
    validate_hex_image,
    wait_for_flash_result,
)
from m14_pin_hil import (  # noqa: E402
    CORE_SOURCE_SCOPES,
    build_record_value,
    file_sha256,
    git_committed_files_digest,
    git_revision,
    validate_board_revision,
)


PROTOCOL_PREFIX = b"NUCODE_M15_SYSTEM_OFF_"
FINAL_FAIL_TOKEN = b"NUCODE_M15_SYSTEM_OFF_FAIL:"
TIMED_READY_TOKEN = (
    b"NUCODE_M15_SYSTEM_OFF_READY:schema=2:phase=TIMED:"
    b"command=ARM_TIMED:duration_us=2000000"
)
TIMED_REQUEST_PATTERN = re.compile(
    rb"NUCODE_M15_SYSTEM_OFF_REQUEST:schema=2:phase=TIMED:nonce="
    + NONCE_PATTERN
    + rb":duration_us=2000000"
)
TIMED_ENTERING_PATTERN = re.compile(
    rb"NUCODE_M15_SYSTEM_OFF_ENTERING:schema=2:phase=TIMED:nonce="
    + NONCE_PATTERN
    + rb":mode=GRTC_WAKE"
)
TIMED_BOOT_PATTERN = re.compile(
    rb"NUCODE_M15_SYSTEM_OFF_BOOT:schema=2:phase=TIMED_WAKE:nonce="
    + NONCE_PATTERN
    + rb":cause=([0-9]+):supported=([0-9]+)"
)
TIMED_WAKE_PATTERN = re.compile(
    rb"NUCODE_M15_SYSTEM_OFF_WAKE:PASS:phase=TIMED:nonce="
    + NONCE_PATTERN
    + rb":source=GRTC:cause=2048"
)
BUTTON_READY_PATTERN = re.compile(
    rb"NUCODE_M15_SYSTEM_OFF_READY:schema=2:phase=BUTTON:"
    rb"command=ARM_BUTTON:nonce="
    + NONCE_PATTERN
    + rb":wake=SW0:gpio=P1\.13:active=LOW"
)
BUTTON_REQUEST_PATTERN = re.compile(
    rb"NUCODE_M15_SYSTEM_OFF_REQUEST:schema=2:phase=BUTTON:nonce="
    + NONCE_PATTERN
    + rb":wake=SW0:gpio=P1\.13:active=LOW"
)
BUTTON_ACTION_PATTERN = re.compile(
    rb"NUCODE_M15_SYSTEM_OFF_ACTION:schema=2:phase=BUTTON:nonce="
    + NONCE_PATTERN
    + rb":expected=PRESS_LOW:host_wait_ms=2000"
)
BUTTON_ENTERING_PATTERN = re.compile(
    rb"NUCODE_M15_SYSTEM_OFF_ENTERING:schema=2:phase=BUTTON:nonce="
    + NONCE_PATTERN
    + rb":mode=GPIO_WAKE"
)
BUTTON_BOOT_PATTERN = re.compile(
    rb"NUCODE_M15_SYSTEM_OFF_BOOT:schema=2:phase=BUTTON_WAKE:nonce="
    + NONCE_PATTERN
    + rb":cause=([0-9]+):supported=([0-9]+)"
)
BUTTON_WAKE_PATTERN = re.compile(
    rb"NUCODE_M15_SYSTEM_OFF_WAKE:PASS:phase=BUTTON:nonce="
    + NONCE_PATTERN
    + rb":source=SW0:gpio=P1\.13:active=LOW:cause=128"
)
FINAL_PASS_PATTERN = re.compile(
    rb"NUCODE_M15_SYSTEM_OFF_PASS:schema=2:nonce="
    + NONCE_PATTERN
    + rb":timed=PASS:button=PASS"
)


class SystemOffHilFailure(RuntimeError):
    """! @brief M15 System OFF HIL 계약 위반을 나타냅니다. """


class TranscriptFailure(SystemOffHilFailure):
    """! @brief 실패 원인과 수집된 UART byte를 함께 보존합니다. """

    def __init__(self, message: str, transcript: bytes) -> None:
        """! @brief 오류 설명과 현재까지의 transcript를 저장합니다. """

        super().__init__(message)
        self.transcript = transcript


@dataclass(frozen=True)
class SystemOffResult:
    """! @brief 두 System OFF wake의 nonce와 reset 원인입니다. """

    nonce: str
    timed_reset_cause: int
    timed_supported: int
    button_reset_cause: int
    button_supported: int
    wake_source: str = "SW0"
    gpio: str = "P1.13"
    active_level: str = "LOW"


@dataclass(frozen=True)
class CaptureResult:
    """! @brief UART 원문, host 시간과 수동 확인 시각입니다. """

    transcript: bytes
    nonce: str
    timed_entering_to_wake_ms: int
    button_entering_to_wake_ms: int
    isolation_confirmed_at_utc: str
    button_confirmed_at_utc: str


## @brief 실행 인자를 생성하고 두 수동 fixture 승인을 명시적으로 요구합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "M15 image를 한 번 기록한 뒤 DAP SWD를 격리하고 timed GRTC와 "
            "SW0(P1.13) System OFF wake를 검증합니다."
        )
    )
    parser.add_argument("--hex", dest="hex_path")
    parser.add_argument(
        "--board-id",
        required=True,
        help="다중 보드 오선택을 막기 위한 온보드 CMSIS-DAP UID",
    )
    parser.add_argument("--volume")
    parser.add_argument("--port", default="auto")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=45.0)
    parser.add_argument(
        "--result-timeout", type=float, default=DEFAULT_RESULT_TIMEOUT_SECONDS
    )
    parser.add_argument(
        "--evidence", help="PASS JSON evidence 경로(--discover-only가 아니면 필수)"
    )
    parser.add_argument(
        "--expected-core-revision", help="시험할 checkout의 기대 40자리 Core commit"
    )
    parser.add_argument(
        "--acknowledge-interface-switch",
        action="store_true",
        help=(
            "DAP 연결 제어용 2연 SW1에서 DISABLE_SWD만 차단하고 "
            "DISABLE_UART는 연결 상태로 둘 준비가 되었음을 명시"
        ),
    )
    parser.add_argument(
        "--acknowledge-button-wake",
        action="store_true",
        help="host 안내 뒤 사용자 SW0(P1.13)을 한 번 누를 준비가 되었음을 명시",
    )
    parser.add_argument(
        "--overwrite-evidence",
        action="store_true",
        help="새 PASS가 완료된 뒤 기존 evidence를 원자적으로 교체",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="MSD와 UART만 탐색하고 flash·System OFF 시험 없이 종료",
    )
    return parser.parse_args(arguments)


## @brief 공식 clean Ubuntu CI와 같은 commit blob 기준의 digest를 계산합니다.
def current_source_digests() -> dict[str, str]:
    board_scope = BOARD_ROOT / "boards" / "nucode" / "nu54dk"
    return {
        "core_source_sha256": git_committed_files_digest(
            REPOSITORY, REPOSITORY, CORE_SOURCE_SCOPES
        ),
        "application_source_sha256": git_committed_files_digest(
            REPOSITORY, APPLICATION_SOURCE_ROOT, (APPLICATION_SOURCE_ROOT,)
        ),
        "board_source_sha256": git_committed_files_digest(
            BOARD_ROOT, BOARD_ROOT, (board_scope,)
        ),
    }


## @brief System OFF HIL 입력 source와 board checkout이 clean한지 검사합니다.
def validate_source_clean() -> None:
    core_paths = (
        "cores/arduino",
        "dts",
        "libraries",
        "third_party/ArduinoCore-API",
        "third_party/ArduinoCore-API.provenance.yml",
        "variants/nu54dk",
        "zephyr",
        "tests/zephyr/m15_wake",
        "tests/hil/nu54dk/m15_system_off.py",
        "tests/hil/nu54dk/m14_pin_hil.py",
        "tests/hil/nu54dk/m6_serial_echo.py",
    )
    core = subprocess.run(
        (
            "git",
            "-C",
            str(REPOSITORY),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *core_paths,
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    board = subprocess.run(
        (
            "git",
            "-C",
            str(BOARD_ROOT),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if core.returncode != 0 or core.stdout.strip():
        raise SystemOffHilFailure(
            "M15 System OFF HIL source에 commit되지 않은 변경이 있습니다: "
            f"{core.stdout.strip() or core.stderr.strip()}"
        )
    if board.returncode != 0 or board.stdout.strip():
        raise SystemOffHilFailure(
            "board_package submodule이 clean하지 않습니다: "
            f"{board.stdout.strip() or board.stderr.strip()}"
        )


## @brief HEX build record를 exact revision, target과 source byte에 결합합니다.
def validate_build_record(
    image: Path, core_revision: str, board_revision: str
) -> dict[str, str]:
    record_path = image.parent.parent / "nucode_arduino_core_build.yml"
    try:
        if record_path.stat().st_size > 16384:
            raise SystemOffHilFailure("NUCODE build record가 허용 크기를 초과했습니다.")
        text = record_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise SystemOffHilFailure(
            f"HEX의 NUCODE build record를 읽지 못했습니다: {record_path}: {error}"
        ) from error

    keys = (
        "core_revision",
        "core_source_sha256",
        "application_source_sha256",
        "board_revision",
        "board_source_sha256",
        "ncs_revision",
        "zephyr_revision",
        "board",
        "board_qualifiers",
    )
    values = {key: build_record_value(text, key) for key in keys}
    expected = {
        "core_revision": core_revision[:12],
        "board_revision": board_revision[:12],
        "ncs_revision": "99553055607b",
        "zephyr_revision": "bf801e4e3d19",
        "board": "nrf54l15dk",
        "board_qualifiers": "nrf54l15/cpuapp/nu54dk",
    }
    for key, expected_value in expected.items():
        if values[key] != expected_value:
            raise SystemOffHilFailure(
                "NUCODE build record가 exact M15 HIL 계약과 다릅니다: "
                f"{key}={values[key]}, expected={expected_value}"
            )
    for key, expected_digest in current_source_digests().items():
        if re.fullmatch(r"[0-9a-f]{64}", values[key]) is None:
            raise SystemOffHilFailure(f"NUCODE build record digest가 잘못되었습니다: {key}")
        if values[key] != expected_digest:
            raise SystemOffHilFailure(
                "NUCODE build record source digest가 현재 exact source와 다릅니다: "
                f"{key}={values[key]}, expected={expected_digest}"
            )
    values["record_name"] = record_path.name
    values["record_sha256"] = file_sha256(record_path)
    return values


## @brief M15 HEX를 DAPLink MSD로 한 번 기록하고 완료 정보를 반환합니다.
def flash_image(
    volume: DaplinkVolume, image: Path, timeout_seconds: float
) -> tuple[str, str]:
    if timeout_seconds <= 0:
        raise SystemOffHilFailure("--flash-timeout은 0보다 커야 합니다.")
    previous_sequence = detail_value(volume.details, "Flash Sequence")
    shutil.copyfile(image, volume.root / "NUCODE_M15_SYSTEM_OFF.HEX")
    details = wait_for_flash_result(volume.root, previous_sequence, timeout_seconds)
    return (
        detail_value(details, "Flash Sequence") or "unknown",
        detail_value(details, "Last Flash Bytes") or "unknown",
    )


## @brief protocol 정규식 하나를 소비하고 nonce를 누적합니다.
def _take_pattern(
    lines: list[bytes], cursor: int, pattern: re.Pattern[bytes], nonces: list[str]
) -> tuple[re.Match[bytes], int]:
    if cursor >= len(lines):
        raise SystemOffHilFailure("M15 System OFF protocol line이 중간에 누락되었습니다.")
    match = pattern.fullmatch(lines[cursor])
    if match is None:
        raise SystemOffHilFailure(
            "M15 System OFF protocol 순서/값이 다릅니다: "
            f"line={cursor}, actual={lines[cursor]!r}"
        )
    nonces.append(match.group(1).decode("ascii"))
    return match, cursor + 1


## @brief reset 원인이 기대 단일 bit이며 supported mask에 포함되는지 검사합니다.
def _validate_reset_cause(
    phase: str, cause: int, supported: int, expected: int
) -> None:
    if cause & RESET_DEBUG:
        raise SystemOffHilFailure(
            f"{phase} wake에 금지된 RESET_DEBUG가 포함되었습니다: cause={cause}"
        )
    if cause != expected:
        raise SystemOffHilFailure(
            f"{phase} reset 원인이 정확한 단일 기대값이 아닙니다: "
            f"cause={cause}, expected={expected}"
        )
    if cause & ~supported:
        raise SystemOffHilFailure(
            f"{phase} reset 원인이 supported mask 밖에 있습니다: "
            f"cause={cause}, supported={supported}"
        )


## @brief UART의 CRLF, LF와 단독 CR을 동일한 정확한 record 경계로 정규화합니다.
def _normalize_uart_line_endings(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


## @brief schema 2의 timed GRTC→SW0 전체 순서와 동일 nonce만 승인합니다.
def parse_transcript(transcript: bytes) -> SystemOffResult:
    normalized = _normalize_uart_line_endings(transcript)
    if FINAL_FAIL_TOKEN in normalized:
        raise SystemOffHilFailure("target이 M15 System OFF 실패를 보고했습니다.")
    lines = [
        line.strip()
        for line in normalized.split(b"\n")
        if line.strip().startswith(PROTOCOL_PREFIX)
    ]
    cursor = 0
    nonces: list[str] = []

    def take_exact(expected: bytes) -> None:
        nonlocal cursor
        if cursor >= len(lines) or lines[cursor] != expected:
            actual = lines[cursor] if cursor < len(lines) else b"<missing>"
            raise SystemOffHilFailure(
                "M15 System OFF protocol 순서/값이 다릅니다: "
                f"line={cursor}, expected={expected!r}, actual={actual!r}"
            )
        cursor += 1

    def take(pattern: re.Pattern[bytes]) -> re.Match[bytes]:
        nonlocal cursor
        match, cursor = _take_pattern(lines, cursor, pattern, nonces)
        return match

    take_exact(TIMED_READY_TOKEN)
    take(TIMED_REQUEST_PATTERN)
    take(TIMED_ENTERING_PATTERN)
    timed_boot = take(TIMED_BOOT_PATTERN)
    take(TIMED_WAKE_PATTERN)
    take(BUTTON_READY_PATTERN)
    take(BUTTON_REQUEST_PATTERN)
    take(BUTTON_ACTION_PATTERN)
    take(BUTTON_ENTERING_PATTERN)
    button_boot = take(BUTTON_BOOT_PATTERN)
    take(BUTTON_WAKE_PATTERN)
    take(FINAL_PASS_PATTERN)
    if cursor != len(lines):
        raise SystemOffHilFailure(
            "최종 PASS 뒤 예상하지 않은 M15 protocol line이 있습니다: "
            f"{lines[cursor:]!r}"
        )
    if not nonces or len(set(nonces)) != 1:
        raise SystemOffHilFailure(f"M15 protocol nonce가 단계마다 다릅니다: {nonces!r}")

    timed_cause = int(timed_boot.group(2), 10)
    timed_supported = int(timed_boot.group(3), 10)
    button_cause = int(button_boot.group(2), 10)
    button_supported = int(button_boot.group(3), 10)
    _validate_reset_cause("TIMED", timed_cause, timed_supported, RESET_CLOCK)
    _validate_reset_cause(
        "BUTTON", button_cause, button_supported, RESET_LOW_POWER_WAKE
    )
    return SystemOffResult(
        nonce=nonces[0],
        timed_reset_cause=timed_cause,
        timed_supported=timed_supported,
        button_reset_cause=button_cause,
        button_supported=button_supported,
    )


## @brief timed ENTERING부터 CLOCK wake까지의 host 관찰 구간을 검사합니다.
def validate_timed_interval(entering_at: float | None, wake_at: float | None) -> int:
    if entering_at is None or wake_at is None or wake_at < entering_at:
        raise SystemOffHilFailure("timed ENTERING과 wake 시각을 모두 관찰하지 못했습니다.")
    elapsed_ms = int(round((wake_at - entering_at) * 1000.0))
    if not MINIMUM_TIMED_WAKE_MS <= elapsed_ms <= MAXIMUM_TIMED_WAKE_MS:
        raise SystemOffHilFailure(
            "timed GRTC wake 구간이 허용 범위 밖입니다: "
            f"{elapsed_ms}ms, expected={MINIMUM_TIMED_WAKE_MS}..{MAXIMUM_TIMED_WAKE_MS}ms"
        )
    return elapsed_ms


## @brief BUTTON ENTERING부터 wake까지 PRESS NOW 안전 간격을 검사합니다.
def validate_button_interval(entering_at: float | None, wake_at: float | None) -> int:
    if entering_at is None or wake_at is None or wake_at < entering_at:
        raise SystemOffHilFailure("button ENTERING과 wake 시각을 모두 관찰하지 못했습니다.")
    elapsed_ms = int(round((wake_at - entering_at) * 1000.0))
    if elapsed_ms < MINIMUM_BUTTON_PROMPT_MS:
        raise SystemOffHilFailure(
            "SW0을 PRESS NOW 안내보다 먼저 눌렀거나 button wake가 너무 빠릅니다: "
            f"{elapsed_ms}ms"
        )
    return elapsed_ms


## @brief 사용자가 DAP SWD만 격리했음을 exact 문구로 확인합니다.
def _confirm_swd_isolation(confirm: Callable[[str], str]) -> None:
    prompt = (
        "DAP 연결 제어용 2연 SW1에서 실제 보드 실크를 따라 DISABLE_SWD만 "
        "차단하고 DISABLE_UART는 연결 상태로 유지하십시오. 완료 후 "
        "DISABLE_SWD_ONLY 입력: "
    )
    try:
        response = confirm(prompt)
    except (EOFError, OSError) as error:
        raise SystemOffHilFailure(
            f"DISABLE_SWD_ONLY 확인 입력을 읽지 못했습니다: {error}"
        ) from error
    if response.strip() != "DISABLE_SWD_ONLY":
        raise SystemOffHilFailure(
            "DISABLE_SWD_ONLY 확인이 없어 flash 뒤 System OFF 시험을 중단했습니다."
        )


## @brief 사용자가 wake용 SW0을 놓은 상태인지 exact 문구로 확인합니다.
def _confirm_button_released(confirm: Callable[[str], str]) -> None:
    prompt = (
        "사용자 SW0(P1.13)이 눌리지 않은 RELEASED 상태인지 확인하십시오. "
        "완료 후 SW0_RELEASED 입력: "
    )
    try:
        response = confirm(prompt)
    except (EOFError, OSError) as error:
        raise SystemOffHilFailure(
            f"SW0_RELEASED 확인 입력을 읽지 못했습니다: {error}"
        ) from error
    if response.strip() != "SW0_RELEASED":
        raise SystemOffHilFailure(
            "SW0_RELEASED 확인이 없어 button System OFF 시험을 중단했습니다."
        )


## @brief flash 뒤 동일 UART session에서 timed wake와 수동 SW0 wake를 수집합니다.
def capture_protocol(
    serial_port: Any,
    timeout_seconds: float,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    confirm: Callable[[str], str] = input,
    nonce_factory: Callable[[int], str] = secrets.token_hex,
    utc_now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> CaptureResult:
    if not 30.0 <= timeout_seconds <= 600.0:
        raise SystemOffHilFailure("--result-timeout은 30..600초 범위여야 합니다.")

    deadline = monotonic() + timeout_seconds
    observed = bytearray()
    processed_lines = 0
    nonce: str | None = None
    timed_arm_sent = False
    button_arm_sent = False
    button_prompt_emitted = False
    isolation_confirmed_at_utc: str | None = None
    button_confirmed_at_utc: str | None = None
    timed_entering_at: float | None = None
    timed_wake_at: float | None = None
    button_entering_at: float | None = None
    button_wake_at: float | None = None

    while True:
        now = monotonic()
        if (
            button_entering_at is not None
            and not button_prompt_emitted
            and ((now - button_entering_at) * 1000.0) >= MINIMUM_BUTTON_PROMPT_MS
        ):
            print("M15 PRESS NOW: 사용자 SW0(P1.13)을 한 번 누르십시오.")
            button_prompt_emitted = True
        if now >= deadline:
            break

        try:
            waiting = serial_port.in_waiting
            chunk = serial_port.read(waiting if waiting > 0 else 1)
        except (OSError, ValueError) as error:
            raise TranscriptFailure(
                f"SWD 격리 세션의 UART 수신에 실패했습니다: {error}",
                bytes(observed),
            ) from error
        if not chunk:
            continue
        observed.extend(chunk)
        sys.stdout.write(chunk.decode("utf-8", errors="replace"))
        sys.stdout.flush()
        if len(observed) > MAX_TRANSCRIPT_BYTES:
            raise TranscriptFailure(
                "M15 UART transcript가 허용 크기를 초과했습니다.", bytes(observed)
            )

        complete_lines = _normalize_uart_line_endings(bytes(observed)).split(b"\n")[:-1]
        for line in complete_lines[processed_lines:]:
            token = line.strip()
            if token.startswith(FINAL_FAIL_TOKEN):
                raise TranscriptFailure(
                    "target이 M15 System OFF 실패를 보고했습니다.", bytes(observed)
                )
            if token == TIMED_READY_TOKEN and not timed_arm_sent:
                try:
                    _confirm_swd_isolation(confirm)
                except SystemOffHilFailure as error:
                    raise TranscriptFailure(str(error), bytes(observed)) from error
                isolation_confirmed_at_utc = utc_now().isoformat()
                nonce = nonce_factory(16)
                if re.fullmatch(r"[0-9a-f]{32}", nonce) is None:
                    raise TranscriptFailure(
                        "host nonce 생성기가 소문자 32자리 16진수를 반환하지 않았습니다.",
                        bytes(observed),
                    )
                timed_command = f"ARM_TIMED:{nonce}\n".encode("ascii")
                try:
                    written = serial_port.write(timed_command)
                    if written != len(timed_command):
                        raise OSError(
                            f"UART short write: {written}/{len(timed_command)} bytes"
                        )
                    serial_port.flush()
                except (OSError, ValueError) as error:
                    raise TranscriptFailure(
                        f"SWD 격리 뒤 timed ARM 전송에 실패했습니다: {error}",
                        bytes(observed),
                    ) from error
                timed_arm_sent = True
                deadline = monotonic() + timeout_seconds
                print(
                    "M15 timed ARM을 전송했습니다. 이제 debug/flash를 실행하지 마십시오."
                )
            elif TIMED_ENTERING_PATTERN.fullmatch(token) is not None:
                if timed_entering_at is None:
                    timed_entering_at = monotonic()
            elif TIMED_BOOT_PATTERN.fullmatch(token) is not None:
                if timed_wake_at is None:
                    timed_wake_at = monotonic()
            elif BUTTON_READY_PATTERN.fullmatch(token) is not None:
                ready = BUTTON_READY_PATTERN.fullmatch(token)
                assert ready is not None
                ready_nonce = ready.group(1).decode("ascii")
                if nonce is None or ready_nonce != nonce:
                    raise TranscriptFailure(
                        "button 단계 nonce가 host nonce와 다릅니다.", bytes(observed)
                    )
                if not button_arm_sent:
                    try:
                        _confirm_button_released(confirm)
                    except SystemOffHilFailure as error:
                        raise TranscriptFailure(str(error), bytes(observed)) from error
                    button_confirmed_at_utc = utc_now().isoformat()
                    button_command = f"ARM_BUTTON:{nonce}\n".encode("ascii")
                    try:
                        written = serial_port.write(button_command)
                        if written != len(button_command):
                            raise OSError(
                                "UART short write: "
                                f"{written}/{len(button_command)} bytes"
                            )
                        serial_port.flush()
                    except (OSError, ValueError) as error:
                        raise TranscriptFailure(
                            f"SWD 격리 뒤 button ARM 전송에 실패했습니다: {error}",
                            bytes(observed),
                        ) from error
                    button_arm_sent = True
                    deadline = monotonic() + timeout_seconds
                    print("M15 button ARM을 전송했습니다. PRESS NOW를 기다리십시오.")
            elif BUTTON_ENTERING_PATTERN.fullmatch(token) is not None:
                if button_entering_at is None:
                    button_entering_at = monotonic()
            elif BUTTON_BOOT_PATTERN.fullmatch(token) is not None:
                if button_wake_at is None:
                    button_wake_at = monotonic()

            if FINAL_PASS_PATTERN.fullmatch(token) is not None:
                transcript = bytes(observed)
                try:
                    result = parse_transcript(transcript)
                    if (
                        nonce is None
                        or result.nonce != nonce
                        or not timed_arm_sent
                        or not button_arm_sent
                        or not button_prompt_emitted
                        or isolation_confirmed_at_utc is None
                        or button_confirmed_at_utc is None
                    ):
                        raise SystemOffHilFailure(
                            "수동 확인, ARM 또는 PRESS NOW 없이 최종 PASS가 나타났습니다."
                        )
                    timed_ms = validate_timed_interval(
                        timed_entering_at, timed_wake_at
                    )
                    button_ms = validate_button_interval(
                        button_entering_at, button_wake_at
                    )
                except SystemOffHilFailure as error:
                    raise TranscriptFailure(str(error), transcript) from error
                return CaptureResult(
                    transcript=transcript,
                    nonce=nonce,
                    timed_entering_to_wake_ms=timed_ms,
                    button_entering_to_wake_ms=button_ms,
                    isolation_confirmed_at_utc=isolation_confirmed_at_utc,
                    button_confirmed_at_utc=button_confirmed_at_utc,
                )
        processed_lines = len(complete_lines)

    transcript = bytes(observed)
    raise TranscriptFailure(
        "UART에서 M15 최종 PASS/FAIL token을 제한 시간 안에 찾지 못했습니다. "
        f"observed_tail={transcript[-512:]!r}",
        transcript,
    )


## @brief flash를 먼저 한 번 수행한 뒤 SWD 격리 이후에는 UART만 사용합니다.
def verify_system_off(
    serial_module: Any,
    port_name: str,
    baud_rate: int,
    flash_callback: Callable[[], tuple[str, str]],
    result_timeout: float,
    *,
    confirm: Callable[[str], str] = input,
    nonce_factory: Callable[[int], str] = secrets.token_hex,
) -> tuple[str, str, CaptureResult, SystemOffResult]:
    if baud_rate != DEFAULT_BAUD_RATE:
        raise SystemOffHilFailure(
            f"M15 기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다: 요청={baud_rate}"
        )
    with serial_module.Serial(
        port=port_name,
        baudrate=baud_rate,
        bytesize=serial_module.EIGHTBITS,
        parity=serial_module.PARITY_NONE,
        stopbits=serial_module.STOPBITS_ONE,
        timeout=0.1,
        write_timeout=2.0,
    ) as serial_port:
        serial_port.reset_input_buffer()
        sequence, byte_count = flash_callback()
        capture = capture_protocol(
            serial_port,
            result_timeout,
            confirm=confirm,
            nonce_factory=nonce_factory,
        )
    return sequence, byte_count, capture, parse_transcript(capture.transcript)


## @brief evidence와 companion transcript의 신규 생성 조건을 검사합니다.
def prepare_output_paths(
    evidence_argument: str | None, overwrite: bool
) -> tuple[Path, Path]:
    if not evidence_argument:
        raise SystemOffHilFailure("실제 시험에는 --evidence JSON 경로가 필요합니다.")
    evidence = Path(evidence_argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise SystemOffHilFailure("--evidence는 .json 확장자여야 합니다.")
    if evidence.exists() and not evidence.is_file():
        raise SystemOffHilFailure(f"증적 경로가 일반 파일이 아닙니다: {evidence}")
    if evidence.exists() and not overwrite:
        raise SystemOffHilFailure(
            f"기존 증적을 자동 덮어쓰지 않습니다: {evidence}; 새 경로 또는 "
            "--overwrite-evidence를 사용하십시오."
        )
    evidence.parent.mkdir(parents=True, exist_ok=True)

    while True:
        attempt_id = secrets.token_hex(8)
        transcript = evidence.with_name(
            f"{evidence.stem}.attempt-{attempt_id}.transcript.log"
        )
        if not transcript.exists():
            break
    return evidence, transcript


## @brief 임시 파일을 완전히 기록한 뒤 목적 경로를 원자적으로 교체합니다.
def atomic_write_bytes(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


## @brief 새 transcript를 먼저 확정하고 PASS evidence를 마지막에 원자 교체합니다.
def write_pass_outputs(
    evidence_path: Path,
    transcript_path: Path,
    transcript: bytes,
    evidence: dict[str, Any],
) -> None:
    encoded_evidence = (
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    atomic_write_bytes(transcript_path, transcript)
    atomic_write_bytes(evidence_path, encoded_evidence)


## @brief PASS를 exact source·image·nonce·수동 fixture·안전 계약과 결합합니다.
def build_evidence(
    *,
    core_revision: str,
    board_revision: str,
    board_id: str,
    image: Path,
    image_size: int,
    image_sha256: str,
    flash_sequence: str,
    flash_byte_count: str,
    port_name: str,
    transcript_path: Path,
    capture: CaptureResult,
    result: SystemOffResult,
    build_record: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "gate": "m15-nu54dk-system-off-wake-hil",
        "status": "passed",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "probe": {"type": "CMSIS-DAP-v2", "uid": board_id},
        "serial": {"port": port_name, "baud": DEFAULT_BAUD_RATE},
        "flash": {
            "transport": "DAPLink-MSD",
            "mass_erase_requested": False,
            "recover_requested": False,
            "sequence": flash_sequence,
            "byte_count": flash_byte_count,
        },
        "image": {
            "name": image.name,
            "size": image_size,
            "sha256": image_sha256,
        },
        "build_record": build_record,
        "protocol": {"schema": 2, "nonce": result.nonce},
        "manual_fixture": {
            "acknowledged": True,
            "switch_reference": "DAP interface two-pole SW1",
            "disable_swd_isolated": True,
            "disable_uart_isolated": False,
            "switch_direction_assumed": False,
            "isolation_confirmed_at_utc": capture.isolation_confirmed_at_utc,
            "button_confirmed_at_utc": capture.button_confirmed_at_utc,
            "wake_button": "SW0",
            "gpio": "P1.13",
            "active_level": "LOW",
        },
        "safety": {
            "debug_access_after_isolation": False,
            "flash_after_isolation": False,
            "mass_erase": False,
            "recovery": False,
        },
        "result": {
            "timed": {
                "wake_source": "GRTC",
                "expected_reset_cause": "RESET_CLOCK",
                "reset_cause_raw": result.timed_reset_cause,
                "supported_raw": result.timed_supported,
                "observed_entering_to_wake_ms": capture.timed_entering_to_wake_ms,
            },
            "button": {
                "wake_source": result.wake_source,
                "gpio": result.gpio,
                "active_level": result.active_level,
                "expected_reset_cause": "RESET_LOW_POWER_WAKE",
                "reset_cause_raw": result.button_reset_cause,
                "supported_raw": result.button_supported,
                "observed_entering_to_wake_ms": capture.button_entering_to_wake_ms,
            },
        },
        "transcript": {
            "name": transcript_path.name,
            "size": len(capture.transcript),
            "sha256": hashlib.sha256(capture.transcript).hexdigest(),
        },
    }


## @brief 장치 탐색 또는 한 번의 flash 뒤 전체 M15 수동 HIL을 수행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    board_id = normalize_board_id(args.board_id)
    volume = find_daplink_volume(board_id, args.volume)
    serial_module, list_ports = import_pyserial()
    port_name = find_serial_port(board_id, args.port, list_ports)
    print(
        "NU54DK discovery SUCCESS: "
        f"uid={board_id}, volume={volume.root}, port={port_name}, baud={args.baud}"
    )
    if args.discover_only:
        return 0

    if not args.acknowledge_interface_switch:
        raise SystemOffHilFailure(
            "실제 시험은 --acknowledge-interface-switch가 필요합니다. DAP 연결 "
            "제어용 2연 SW1과 사용자 버튼 SW0을 혼동하지 마십시오."
        )
    if not args.acknowledge_button_wake:
        raise SystemOffHilFailure(
            "실제 시험은 --acknowledge-button-wake가 필요합니다. PRESS NOW 뒤에만 "
            "사용자 SW0(P1.13)을 한 번 눌러야 합니다."
        )

    evidence_path, transcript_path = prepare_output_paths(
        args.evidence, args.overwrite_evidence
    )
    image = validate_hex_image(args.hex_path)
    core_revision = git_revision(REPOSITORY, args.expected_core_revision)
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    validate_source_clean()
    build_record = validate_build_record(image, core_revision, board_revision)
    image_size = image.stat().st_size
    image_sha256 = file_sha256(image)

    print(
        "M15 System OFF HIL 시작: image는 runner가 먼저 한 번만 기록합니다. "
        "TIMED READY 뒤 안내에 따라 DISABLE_SWD만 차단하며, 그 뒤에는 어떠한 "
        "debug/flash/recover도 실행하지 않습니다."
    )
    try:
        sequence, byte_count, capture, result = verify_system_off(
            serial_module=serial_module,
            port_name=port_name,
            baud_rate=args.baud,
            flash_callback=lambda: flash_image(volume, image, args.flash_timeout),
            result_timeout=args.result_timeout,
        )
    except TranscriptFailure as error:
        atomic_write_bytes(transcript_path, error.transcript)
        raise SystemOffHilFailure(
            f"{error}; 실패 transcript={transcript_path}"
        ) from error

    if image.stat().st_size != image_size or file_sha256(image) != image_sha256:
        atomic_write_bytes(transcript_path, capture.transcript)
        raise SystemOffHilFailure("수동 시험 중 HEX byte가 변경되어 PASS 증적 생성을 거부했습니다.")

    evidence = build_evidence(
        core_revision=core_revision,
        board_revision=board_revision,
        board_id=board_id,
        image=image,
        image_size=image_size,
        image_sha256=image_sha256,
        flash_sequence=sequence,
        flash_byte_count=byte_count,
        port_name=port_name,
        transcript_path=transcript_path,
        capture=capture,
        result=result,
        build_record=build_record,
    )
    write_pass_outputs(
        evidence_path,
        transcript_path,
        capture.transcript,
        evidence,
    )
    print(
        "M15 System OFF wake HIL PASS: "
        f"timed_ms={capture.timed_entering_to_wake_ms}, "
        f"button_ms={capture.button_entering_to_wake_ms}, "
        f"evidence={evidence_path}, transcript={transcript_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        EOFError,
        RuntimeError,
        OSError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        print(f"M15 System OFF HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
