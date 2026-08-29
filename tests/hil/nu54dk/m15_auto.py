#!/usr/bin/env python3
"""! @brief 공식 clean Ubuntu CI M15 artifact의 비버튼 기능을 자동 HIL로 검증합니다. """

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
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
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY = HIL_DIRECTORY.parents[2]
BOARD_ROOT = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m15_hil"
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
    git_committed_files_digest,
    git_revision,
    validate_board_revision,
)


PREFIX = b"NUCODE_M15_AUTO_"
FAIL_PREFIX = b"NUCODE_M15_AUTO_FAIL:"
FINAL_PREFIX = b"NUCODE_M15_AUTO_FINAL:PASS:nonce="
START_COMMAND = b"NUCODE_M15_AUTO_COMMAND:START:"
CONTINUE_COMMAND = b"NUCODE_M15_AUTO_COMMAND:CONTINUE:"
CLEAR_COMMAND = b"NUCODE_M15_AUTO_COMMAND:CLEAR\r\n"
RESET_SOFTWARE = 1 << 1
RESET_WATCHDOG = 1 << 4
RESET_CLOCK = 1 << 11
MAX_TRANSCRIPT_BYTES = 262144
DEFAULT_RESULT_TIMEOUT_SECONDS = 90.0

BOOT_PATTERN = re.compile(
    rb"^NUCODE_M15_AUTO_BOOT:schema=1:stage=([a-z_]+):cause=([0-9]+):"
    rb"supported=([0-9]+):uptime_ms=([0-9]+)$"
)
STATE_PATTERN = re.compile(
    rb"^NUCODE_M15_AUTO_STATE:schema=1:stage=([a-z_]+):nonce=([0-9a-f]{32}|none)$"
)
IDENTITY_PATTERN = re.compile(
    rb"^NUCODE_M15_AUTO_IDENTITY:PASS:model=([^\r\n:]+):target=([^\r\n:]+):"
    rb"soc=([^\r\n:]+):device_id=([0-9a-f]{16}|[0-9a-f]{32})$"
)
RESET_PATTERN = re.compile(
    rb"^NUCODE_M15_AUTO_RESET:PASS:phase=([a-z_]+):cause=([0-9]+):supported=([0-9]+)$"
)
UPTIME_PATTERN = re.compile(
    rb"^NUCODE_M15_AUTO_UPTIME:PASS:before=([0-9]+):after=([0-9]+)$"
)
GRTC_PATTERN = re.compile(
    rb"^NUCODE_M15_AUTO_GRTC:PASS:frequency=([0-9]+):before=([0-9]+):"
    rb"scheduled=([0-9]+):after=([0-9]+):callbacks=1$"
)


class AutoHilFailure(RuntimeError):
    """! @brief M15 자동 HIL의 장치·protocol·evidence 실패를 나타냅니다. """


class ProtocolExecutionFailure(AutoHilFailure):
    """! @brief 실행 실패와 그 시점까지의 raw UART byte를 함께 보존합니다. """

    def __init__(self, message: str, transcript: bytes) -> None:
        """! @brief 실패 설명과 부분 transcript를 변경 불가능한 byte로 저장합니다. """

        super().__init__(message)
        self.transcript = transcript


@dataclass(frozen=True)
class AutoHilResult:
    """! @brief 검증된 M15 자동 HIL의 핵심 결과입니다. """

    nonce: str
    board_model: str
    board_target: str
    soc: str
    device_id: str
    initial_reset_cause: int
    software_reset_cause: int
    watchdog_reset_cause: int
    timed_wake_reset_cause: int
    uptime_before_ms: int
    uptime_after_ms: int
    grtc_frequency_hz: int
    grtc_before_ticks: int
    grtc_scheduled_ticks: int
    grtc_after_ticks: int
    watchdog_interval_seconds: float
    system_off_interval_seconds: float


@dataclass(frozen=True)
class ExecutionResult:
    """! @brief 실제 UART 상태 머신 실행 결과와 원문 transcript입니다. """

    flash_sequence: str
    flash_bytes: str
    transcript: bytes
    scenario_transcript: bytes
    watchdog_interval_seconds: float
    system_off_interval_seconds: float


## @brief CLI 인자를 만들며 board UID를 실제 실행에서 반드시 요구합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "NU54DK M15 image를 DAPLink로 기록하고 identity, GRTC, Settings/ZMS, "
            "WDT와 timed System OFF를 자동 검증합니다."
        )
    )
    parser.add_argument("--hex", dest="hex_path")
    parser.add_argument("--board-id", required=True, help="대상 DAPLink Unique ID")
    parser.add_argument("--volume")
    parser.add_argument("--port", default="auto")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=45.0)
    parser.add_argument(
        "--result-timeout", type=float, default=DEFAULT_RESULT_TIMEOUT_SECONDS
    )
    parser.add_argument("--evidence", help="PASS JSON evidence 경로")
    parser.add_argument(
        "--expected-core-revision",
        help="시험할 checkout의 기대 40자리 Core commit",
    )
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument(
        "--recovery-mode",
        choices=("none", "reset", "reflash"),
        default="reset",
        help="실패 뒤 pyOCD로 수행할 비파괴 복구(기본: reset)",
    )
    parser.add_argument(
        "--recovery-hex",
        help="--recovery-mode reflash에서 기록할 안전 image",
    )
    return parser.parse_args(arguments)


## @brief 파일 SHA-256을 streaming 방식으로 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


## @brief 자동 HIL image 입력 source와 board checkout이 clean한지 검사합니다.
def validate_source_clean() -> None:
    core_paths = (
        "cores/arduino",
        "dts",
        "libraries",
        "third_party/ArduinoCore-API",
        "third_party/ArduinoCore-API.provenance.yml",
        "variants/nu54dk",
        "zephyr",
        "tests/zephyr/m15_hil",
        "tests/hil/nu54dk/m15_auto.py",
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
        raise AutoHilFailure(
            "M15 자동 HIL source에 commit되지 않은 변경이 있습니다: "
            f"{core.stdout.strip() or core.stderr.strip()}"
        )
    if board.returncode != 0 or board.stdout.strip():
        raise AutoHilFailure(
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
            raise AutoHilFailure("NUCODE build record가 허용 크기를 초과했습니다.")
        text = record_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise AutoHilFailure(
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
            raise AutoHilFailure(
                "NUCODE build record가 exact M15 자동 HIL 계약과 다릅니다: "
                f"{key}={values[key]}, expected={expected_value}"
            )
    for key, expected_digest in current_source_digests().items():
        if re.fullmatch(r"[0-9a-f]{64}", values[key]) is None:
            raise AutoHilFailure(f"NUCODE build record digest가 잘못되었습니다: {key}")
        if values[key] != expected_digest:
            raise AutoHilFailure(
                "NUCODE build record source digest가 현재 exact source와 다릅니다: "
                f"{key}={values[key]}, expected={expected_digest}"
            )
    values["record_name"] = record_path.name
    values["record_sha256"] = file_sha256(record_path)
    return values


## @brief 실행 전 고정한 HEX byte가 시험 중 변경되지 않았는지 검사합니다.
def validate_image_unchanged(image: Path, expected_size: int, expected_sha256: str) -> None:
    if image.stat().st_size != expected_size or file_sha256(image) != expected_sha256:
        raise AutoHilFailure("자동 시험 중 HEX byte가 변경되어 PASS 증적 생성을 거부했습니다.")


## @brief 증적과 transcript 출력 경로를 안전하게 준비합니다.
def prepare_output_paths(
    evidence_argument: str | None, overwrite: bool
) -> tuple[Path, Path]:
    if not evidence_argument:
        raise AutoHilFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(evidence_argument).resolve()
    transcript = evidence.with_suffix(".transcript.log")
    existing = [path for path in (evidence, transcript) if path.exists()]
    if existing and not overwrite:
        raise AutoHilFailure(
            "기존 evidence를 자동 덮어쓰지 않습니다: "
            + ", ".join(str(path) for path in existing)
        )
    evidence.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for path in existing:
            path.unlink()
    return evidence, transcript


## @brief M15 HEX를 DAPLink MSD로 기록하고 완료 sequence를 반환합니다.
def flash_image(
    volume: DaplinkVolume, image: Path, timeout_seconds: float
) -> tuple[str, str]:
    if timeout_seconds <= 0:
        raise AutoHilFailure("--flash-timeout은 0보다 커야 합니다.")
    previous_sequence = detail_value(volume.details, "Flash Sequence")
    shutil.copyfile(image, volume.root / "NUCODE_M15_AUTO.HEX")
    details = wait_for_flash_result(volume.root, previous_sequence, timeout_seconds)
    return (
        detail_value(details, "Flash Sequence") or "unknown",
        detail_value(details, "Last Flash Bytes") or "unknown",
    )


## @brief exact UID와 attach-only 정책으로 pyOCD session을 만듭니다.
def create_probe_release_session(board_id: str, connect_helper: Any = None) -> Any:
    if connect_helper is None:
        try:
            from pyocd.core.helpers import ConnectHelper
        except ImportError as error:
            raise AutoHilFailure("M15 HIL Python 환경에 pyOCD가 없습니다.") from error
        connect_helper = ConnectHelper
    session = connect_helper.session_with_chosen_probe(
        unique_id=board_id,
        auto_open=False,
        options={
            "target_override": "nrf54l",
            "connect_mode": "attach",
            "resume_on_disconnect": True,
        },
    )
    if session is None:
        raise AutoHilFailure(f"CMSIS-DAP probe를 찾지 못했습니다: {board_id}")
    return session


## @brief SW-DP를 dormant 상태로 전환해 host 없는 동안의 debug 재접속을 막습니다.
def enter_swd_dormant(probe: Any) -> None:
    probe.swj_sequence(51, 0xFFFFFFFFFFFFFF)
    probe.swj_sequence(16, 0xE3BC)


## @brief System OFF 전에 DP power, SWD dormant와 CMSIS-DAP 해제를 검증합니다.
def release_probe_debug_power(board_id: str) -> None:
    session = create_probe_release_session(board_id)
    probe = session.probe
    if str(probe.unique_id).casefold() != board_id.casefold():
        raise AutoHilFailure(
            "선택된 CMSIS-DAP probe가 exact UID와 다릅니다: "
            f"기대={board_id}, 실제={probe.unique_id}"
        )
    release = {
        "dp_called": False,
        "dp_acknowledged": False,
        "swd_dormant_completed": False,
        "dap_called": False,
        "dap_disconnected": False,
    }
    try:
        session.open()
        debug_port = session.target.dp
        original_probe_disconnect = probe.disconnect

        def checked_disconnect() -> None:
            """! @brief debug power ACK를 내리고 SW-DP를 dormant로 전환합니다. """
            release["dp_called"] = True
            release["dp_acknowledged"] = bool(debug_port.power_down_debug())
            if release["dp_acknowledged"]:
                enter_swd_dormant(probe)
                release["swd_dormant_completed"] = True

        def checked_probe_disconnect() -> None:
            """! @brief CMSIS-DAP DAP_Disconnect가 완료됐는지 보존합니다. """
            release["dap_called"] = True
            original_probe_disconnect()
            release["dap_disconnected"] = True

        debug_port.disconnect = checked_disconnect
        probe.disconnect = checked_probe_disconnect
        session.close()
    finally:
        if probe.is_open:
            try:
                probe.disconnect()
            finally:
                probe.close()
    if not all(release.values()) or probe.is_open:
        raise AutoHilFailure(
            "CMSIS-DAP debug/system power request 해제를 검증하지 못했습니다: "
            f"{release}"
        )


## @brief DAPLink 기록 뒤 target이 명령을 기다리는 동안 probe debug power를 해제합니다.
def flash_and_release_debug_power(
    volume: DaplinkVolume,
    image: Path,
    timeout_seconds: float,
    board_id: str,
) -> tuple[str, str]:
    flash_result = flash_image(volume, image, timeout_seconds)
    release_probe_debug_power(board_id)
    return flash_result


## @brief 한 UART 명령을 CRLF로 끝내 전송합니다.
def write_command(serial_port: Any, command: bytes) -> None:
    request = command + b"\r\n"
    written = serial_port.write(request)
    serial_port.flush()
    if written != len(request):
        raise AutoHilFailure(
            f"UART 명령 일부만 전송했습니다: 기대={len(request)}, 실제={written}"
        )


## @brief 제한된 transcript buffer에서 완전한 UART line을 하나 반환합니다.
def read_line(
    serial_port: Any,
    buffer: bytearray,
    deadline: float,
    raw_capture: bytearray | None = None,
) -> tuple[bytes, bytes]:
    while time.monotonic() < deadline:
        newline = buffer.find(b"\n")
        if newline >= 0:
            raw = bytes(buffer[: newline + 1])
            del buffer[: newline + 1]
            return raw.rstrip(b"\r\n"), raw
        waiting = serial_port.in_waiting
        chunk = serial_port.read(waiting if waiting > 0 else 1)
        if chunk:
            buffer.extend(chunk)
            if raw_capture is not None:
                raw_capture.extend(chunk)
                if len(raw_capture) > MAX_TRANSCRIPT_BYTES:
                    raise AutoHilFailure("M15 UART transcript가 허용 크기를 초과했습니다.")
            if len(buffer) > MAX_TRANSCRIPT_BYTES:
                raise AutoHilFailure("UART line buffer가 허용 크기를 초과했습니다.")
    raise AutoHilFailure("M15 UART protocol이 제한 시간 안에 완료되지 않았습니다.")


## @brief 실행 실패에도 그 시점까지의 UART 원문을 보존해 상태 머신을 실행합니다.
def execute_protocol(
    serial_module: Any,
    port_name: str,
    baud_rate: int,
    result_timeout_seconds: float,
    flash_callback: Any,
) -> ExecutionResult:
    transcript = bytearray()
    try:
        return _execute_protocol(
            serial_module=serial_module,
            port_name=port_name,
            baud_rate=baud_rate,
            result_timeout_seconds=result_timeout_seconds,
            flash_callback=flash_callback,
            raw_capture=transcript,
        )
    except ProtocolExecutionFailure:
        raise
    except Exception as error:
        raise ProtocolExecutionFailure(str(error), bytes(transcript)) from error


## @brief 제공된 raw buffer에 모든 UART byte를 누적하며 상태 머신을 실행합니다.
def _execute_protocol(
    serial_module: Any,
    port_name: str,
    baud_rate: int,
    result_timeout_seconds: float,
    flash_callback: Any,
    raw_capture: bytearray,
) -> ExecutionResult:
    if baud_rate != DEFAULT_BAUD_RATE:
        raise AutoHilFailure(f"M15 HIL은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    if not 30.0 <= result_timeout_seconds <= 180.0:
        raise AutoHilFailure("--result-timeout은 30..180초 범위여야 합니다.")

    nonce = secrets.token_hex(16).encode("ascii")
    scenario_lines: list[bytes] = []
    pending = bytearray()
    started = False
    expected_states = [
        b"soft_reset",
        b"watchdog_arm",
        b"watchdog_wait",
        b"timed_wake_wait",
    ]
    state_index = 0
    last_boot: bytes | None = None
    watchdog_armed_at: float | None = None
    watchdog_boot_at: float | None = None
    system_off_entered_at: float | None = None
    system_off_boot_at: float | None = None

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
        flash_sequence, flash_bytes = flash_callback()
        deadline = time.monotonic() + result_timeout_seconds

        while time.monotonic() < deadline:
            line, raw = read_line(serial_port, pending, deadline, raw_capture)
            sys.stdout.write(raw.decode("utf-8", errors="backslashreplace"))
            sys.stdout.flush()
            stripped = line.strip()
            if not stripped.startswith(PREFIX):
                continue
            if stripped.startswith(FAIL_PREFIX):
                raise AutoHilFailure(f"target이 실패를 보고했습니다: {stripped!r}")

            boot = BOOT_PATTERN.fullmatch(stripped)
            if boot is not None:
                last_boot = stripped
                stage = boot.group(1)
                now = time.monotonic()
                if started and stage == b"watchdog_wait":
                    watchdog_boot_at = now
                if started and stage == b"timed_wake_wait":
                    system_off_boot_at = now
                if started:
                    scenario_lines.append(stripped)
                continue

            state = STATE_PATTERN.fullmatch(stripped)
            if state is not None:
                stage, observed_nonce = state.groups()
                if not started:
                    if stage != b"idle":
                        serial_port.write(CLEAR_COMMAND)
                        serial_port.flush()
                        continue
                    if last_boot is None:
                        raise AutoHilFailure("idle STATE 앞의 BOOT token이 없습니다.")
                    scenario_lines.extend((last_boot, stripped))
                    write_command(serial_port, START_COMMAND + nonce)
                    started = True
                    continue

                scenario_lines.append(stripped)
                if state_index >= len(expected_states) or stage != expected_states[state_index]:
                    raise AutoHilFailure(
                        "상태 전이 순서가 다릅니다: "
                        f"index={state_index}, stage={stage!r}"
                    )
                if observed_nonce != nonce:
                    raise AutoHilFailure("재부팅 뒤 scenario nonce가 달라졌습니다.")
                state_index += 1
                write_command(serial_port, CONTINUE_COMMAND + nonce)
                continue

            if started:
                scenario_lines.append(stripped)
            if stripped == b"NUCODE_M15_AUTO_WDT:EXPIRY_ARMED:timeout_ms=1500:feeds=1":
                watchdog_armed_at = time.monotonic()
            elif stripped == b"NUCODE_M15_AUTO_SYSTEM_OFF:ENTERING":
                system_off_entered_at = time.monotonic()
            elif stripped == FINAL_PREFIX + nonce:
                break
        else:
            raise AutoHilFailure("M15 최종 PASS token을 제한 시간 안에 찾지 못했습니다.")

    if state_index != len(expected_states):
        raise AutoHilFailure("M15 reset 경계 상태가 모두 관찰되지 않았습니다.")
    if None in (
        watchdog_armed_at,
        watchdog_boot_at,
        system_off_entered_at,
        system_off_boot_at,
    ):
        raise AutoHilFailure("watchdog 또는 System OFF 시간 경계가 누락됐습니다.")
    watchdog_interval = float(watchdog_boot_at - watchdog_armed_at)  # type: ignore[operator]
    system_off_interval = float(system_off_boot_at - system_off_entered_at)  # type: ignore[operator]
    scenario_transcript = b"\n".join(scenario_lines) + b"\n"
    return ExecutionResult(
        flash_sequence=flash_sequence,
        flash_bytes=flash_bytes,
        transcript=bytes(raw_capture),
        scenario_transcript=scenario_transcript,
        watchdog_interval_seconds=watchdog_interval,
        system_off_interval_seconds=system_off_interval,
    )


## @brief protocol line을 기대 정규식으로 하나씩 소비합니다.
def _match_line(
    lines: list[bytes], cursor: int, pattern: re.Pattern[bytes] | bytes
) -> tuple[re.Match[bytes] | None, int]:
    if cursor >= len(lines):
        raise AutoHilFailure("M15 protocol line이 중간에 누락됐습니다.")
    line = lines[cursor]
    if isinstance(pattern, bytes):
        if line != pattern:
            raise AutoHilFailure(
                f"M15 protocol 순서/값이 다릅니다: 기대={pattern!r}, 실제={line!r}"
            )
        return None, cursor + 1
    match = pattern.fullmatch(line)
    if match is None:
        raise AutoHilFailure(f"M15 protocol 형식이 다릅니다: {line!r}")
    return match, cursor + 1


## @brief reset line을 소비하고 기대 bit와 지원 mask를 독립 검증합니다.
def _consume_reset(
    lines: list[bytes], cursor: int, phase: bytes, required_mask: int
) -> tuple[int, int]:
    match, cursor = _match_line(lines, cursor, RESET_PATTERN)
    assert match is not None
    actual_phase, cause_text, supported_text = match.groups()
    cause = int(cause_text, 10)
    supported = int(supported_text, 10)
    if (
        actual_phase != phase
        or (required_mask != 0 and (cause & required_mask) == 0)
        or (cause & ~supported) != 0
    ):
        raise AutoHilFailure(
            "reset cause 계약이 다릅니다: "
            f"phase={actual_phase!r}, cause={cause}, supported={supported}"
        )
    return cause, cursor


## @brief 완전한 scenario transcript를 fail-closed로 독립 검증합니다.
def parse_transcript(
    transcript: bytes,
    watchdog_interval_seconds: float,
    system_off_interval_seconds: float,
) -> AutoHilResult:
    if FAIL_PREFIX in transcript:
        raise AutoHilFailure("transcript에 target FAIL token이 있습니다.")
    lines = [
        line.strip()
        for line in transcript.replace(b"\r", b"").split(b"\n")
        if line.strip().startswith(PREFIX)
    ]
    cursor = 0

    boot, cursor = _match_line(lines, cursor, BOOT_PATTERN)
    assert boot is not None
    if boot.group(1) != b"idle":
        raise AutoHilFailure("scenario는 clean idle boot에서 시작해야 합니다.")
    initial_cause = int(boot.group(2), 10)
    initial_supported = int(boot.group(3), 10)
    if (initial_cause & ~initial_supported) != 0:
        raise AutoHilFailure("초기 reset cause가 supported mask 밖입니다.")

    _, cursor = _match_line(
        lines, cursor, b"NUCODE_M15_AUTO_STATE:schema=1:stage=idle:nonce=none"
    )
    start_pattern = re.compile(rb"^NUCODE_M15_AUTO_START:PASS:nonce=([0-9a-f]{32})$")
    start, cursor = _match_line(lines, cursor, start_pattern)
    assert start is not None
    nonce = start.group(1)

    identity, cursor = _match_line(lines, cursor, IDENTITY_PATTERN)
    assert identity is not None
    model, target, soc, device_id = identity.groups()
    initial_reset, cursor = _consume_reset(lines, cursor, b"initial", 0)
    if initial_reset != initial_cause:
        raise AutoHilFailure("초기 BOOT와 reset report의 원인이 다릅니다.")

    uptime, cursor = _match_line(lines, cursor, UPTIME_PATTERN)
    assert uptime is not None
    uptime_before, uptime_after = (int(value, 10) for value in uptime.groups())
    if uptime_after <= uptime_before or (uptime_after - uptime_before) < 20:
        raise AutoHilFailure("64-bit uptime 진행량이 계약보다 작습니다.")

    grtc, cursor = _match_line(lines, cursor, GRTC_PATTERN)
    assert grtc is not None
    frequency, grtc_before, grtc_scheduled, grtc_after = (
        int(value, 10) for value in grtc.groups()
    )
    if frequency <= 0 or not (grtc_before < grtc_scheduled <= grtc_after):
        raise AutoHilFailure("GRTC counter/alarm tick 관계가 올바르지 않습니다.")

    _, cursor = _match_line(lines, cursor, b"NUCODE_M15_AUTO_SETTINGS:SAVED:length=8")
    _, cursor = _match_line(
        lines,
        cursor,
        b"NUCODE_M15_AUTO_TRANSITION:next=soft_reset:method=software",
    )
    boot, cursor = _match_line(lines, cursor, BOOT_PATTERN)
    assert boot is not None
    if boot.group(1) != b"soft_reset" or (int(boot.group(2), 10) & RESET_SOFTWARE) == 0:
        raise AutoHilFailure("software reset BOOT 원인이 다릅니다.")
    _, cursor = _match_line(
        lines,
        cursor,
        b"NUCODE_M15_AUTO_STATE:schema=1:stage=soft_reset:nonce=" + nonce,
    )
    _, cursor = _match_line(
        lines,
        cursor,
        b"NUCODE_M15_AUTO_CONTINUE:PASS:stage=soft_reset:nonce=" + nonce,
    )
    software_cause, cursor = _consume_reset(lines, cursor, b"software", RESET_SOFTWARE)
    _, cursor = _match_line(
        lines, cursor, b"NUCODE_M15_AUTO_SETTINGS:LOAD_DELETE:PASS:length=8"
    )
    _, cursor = _match_line(
        lines, cursor, b"NUCODE_M15_AUTO_WDT:STOP:PASS:feeds=3:survival_ms=2300"
    )
    _, cursor = _match_line(
        lines,
        cursor,
        b"NUCODE_M15_AUTO_TRANSITION:next=watchdog_arm:method=software",
    )

    boot, cursor = _match_line(lines, cursor, BOOT_PATTERN)
    assert boot is not None
    if boot.group(1) != b"watchdog_arm" or (int(boot.group(2), 10) & RESET_SOFTWARE) == 0:
        raise AutoHilFailure("watchdog arm boot 원인이 다릅니다.")
    _, cursor = _match_line(
        lines,
        cursor,
        b"NUCODE_M15_AUTO_STATE:schema=1:stage=watchdog_arm:nonce=" + nonce,
    )
    _, cursor = _match_line(
        lines,
        cursor,
        b"NUCODE_M15_AUTO_CONTINUE:PASS:stage=watchdog_arm:nonce=" + nonce,
    )
    _, cursor = _consume_reset(
        lines, cursor, b"watchdog_arm_software", RESET_SOFTWARE
    )
    _, cursor = _match_line(
        lines,
        cursor,
        b"NUCODE_M15_AUTO_WDT:EXPIRY_ARMED:timeout_ms=1500:feeds=1",
    )

    boot, cursor = _match_line(lines, cursor, BOOT_PATTERN)
    assert boot is not None
    if boot.group(1) != b"watchdog_wait" or (int(boot.group(2), 10) & RESET_WATCHDOG) == 0:
        raise AutoHilFailure("watchdog reset BOOT 원인이 다릅니다.")
    _, cursor = _match_line(
        lines,
        cursor,
        b"NUCODE_M15_AUTO_STATE:schema=1:stage=watchdog_wait:nonce=" + nonce,
    )
    _, cursor = _match_line(
        lines,
        cursor,
        b"NUCODE_M15_AUTO_CONTINUE:PASS:stage=watchdog_wait:nonce=" + nonce,
    )
    watchdog_cause, cursor = _consume_reset(lines, cursor, b"watchdog", RESET_WATCHDOG)
    _, cursor = _match_line(
        lines,
        cursor,
        b"NUCODE_M15_AUTO_SYSTEM_OFF:REQUESTED:duration_us=2000000",
    )
    _, cursor = _match_line(lines, cursor, b"NUCODE_M15_AUTO_SYSTEM_OFF:ENTERING")

    boot, cursor = _match_line(lines, cursor, BOOT_PATTERN)
    assert boot is not None
    if boot.group(1) != b"timed_wake_wait" or (int(boot.group(2), 10) & RESET_CLOCK) == 0:
        raise AutoHilFailure("timed System OFF BOOT 원인이 다릅니다.")
    _, cursor = _match_line(
        lines,
        cursor,
        b"NUCODE_M15_AUTO_STATE:schema=1:stage=timed_wake_wait:nonce=" + nonce,
    )
    _, cursor = _match_line(
        lines,
        cursor,
        b"NUCODE_M15_AUTO_CONTINUE:PASS:stage=timed_wake_wait:nonce=" + nonce,
    )
    timed_cause, cursor = _consume_reset(lines, cursor, b"timed_wake", RESET_CLOCK)
    timed_wake_pattern = re.compile(
        rb"^NUCODE_M15_AUTO_SYSTEM_OFF:WAKE:PASS:duration_us=2000000:cause=([0-9]+)$"
    )
    wake, cursor = _match_line(lines, cursor, timed_wake_pattern)
    assert wake is not None
    if int(wake.group(1), 10) != timed_cause:
        raise AutoHilFailure("timed wake token과 reset report가 다릅니다.")
    _, cursor = _match_line(lines, cursor, FINAL_PREFIX + nonce)
    if cursor != len(lines):
        raise AutoHilFailure(f"최종 PASS 뒤 예상하지 않은 protocol token이 있습니다: {lines[cursor:]!r}")

    if not 1.0 <= watchdog_interval_seconds <= 6.0:
        raise AutoHilFailure(
            f"watchdog reset 시간이 범위를 벗어났습니다: {watchdog_interval_seconds:.3f}s"
        )
    if not 1.5 <= system_off_interval_seconds <= 10.0:
        raise AutoHilFailure(
            f"timed System OFF wake 시간이 범위를 벗어났습니다: {system_off_interval_seconds:.3f}s"
        )

    return AutoHilResult(
        nonce=nonce.decode("ascii"),
        board_model=model.decode("ascii"),
        board_target=target.decode("ascii"),
        soc=soc.decode("ascii"),
        device_id=device_id.decode("ascii"),
        initial_reset_cause=initial_reset,
        software_reset_cause=software_cause,
        watchdog_reset_cause=watchdog_cause,
        timed_wake_reset_cause=timed_cause,
        uptime_before_ms=uptime_before,
        uptime_after_ms=uptime_after,
        grtc_frequency_hz=frequency,
        grtc_before_ticks=grtc_before,
        grtc_scheduled_ticks=grtc_scheduled,
        grtc_after_ticks=grtc_after,
        watchdog_interval_seconds=round(watchdog_interval_seconds, 6),
        system_off_interval_seconds=round(system_off_interval_seconds, 6),
    )


## @brief pyOCD reset 또는 명시한 안전 image reflash 명령을 구성합니다.
def recovery_command(
    mode: str, board_id: str, recovery_image: Path | None
) -> list[str]:
    base = [sys.executable, "-m", "pyocd"]
    if mode == "reset":
        return base + ["reset", "-t", "nrf54l", "-u", board_id]
    if mode == "reflash":
        if recovery_image is None:
            raise AutoHilFailure("reflash 복구에는 --recovery-hex가 필요합니다.")
        return base + [
            "load",
            "-t",
            "nrf54l",
            "-u",
            board_id,
            str(recovery_image),
        ]
    if mode != "none":
        raise AutoHilFailure(f"알 수 없는 recovery mode입니다: {mode}")
    return []


## @brief 실패 뒤 pyOCD 복구를 shell 없이 한 번만 수행합니다.
def recover_target(mode: str, board_id: str, recovery_hex: str | None) -> str:
    if mode == "none":
        return "not-requested"
    recovery_image = validate_hex_image(recovery_hex) if mode == "reflash" else None
    command = recovery_command(mode, board_id, recovery_image)
    environment = dict(os.environ)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        command,
        cwd=REPOSITORY,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60.0,
    )
    if result.returncode != 0:
        raise AutoHilFailure(
            f"pyOCD {mode} 복구 실패({result.returncode}): "
            f"{(result.stdout + result.stderr)[-1000:]}"
        )
    return "passed"


## @brief PASS evidence가 image, UART 원문과 실제 장치 identity를 결합합니다.
def build_evidence(
    *,
    core_revision: str,
    board_revision: str,
    board_id: str,
    volume: DaplinkVolume,
    port_name: str,
    image: Path,
    image_size: int,
    image_sha256: str,
    transcript_path: Path,
    execution: ExecutionResult,
    result: AutoHilResult,
    build_record: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "evidence_type": "m15-auto-board-system-hil",
        "status": "passed",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "board": {
            "daplink_uid": board_id,
            "target_detect": detail_value(volume.details, "Target Detect"),
            "uart_port": port_name,
            "device_id": result.device_id,
            "model": result.board_model,
            "target": result.board_target,
            "soc": result.soc,
        },
        "image": {
            "name": image.name,
            "size": image_size,
            "sha256": image_sha256,
            "flash_sequence": execution.flash_sequence,
            "flash_bytes": execution.flash_bytes,
        },
        "build_record": build_record,
        "transcript": {
            "name": transcript_path.name,
            "size": len(execution.transcript),
            "sha256": hashlib.sha256(execution.transcript).hexdigest(),
            "scenario_sha256": hashlib.sha256(
                execution.scenario_transcript
            ).hexdigest(),
        },
        "result": asdict(result),
        "safety": {
            "button_wake_executed": False,
            "pmic_write_executed": False,
            "mass_erase_requested": False,
            "recovery_requested": False,
            "probe_debug_power_released_and_swd_dormant_before_start": True,
        },
    }


## @brief 실패가 보존한 부분 UART 원문을 companion transcript에 기록합니다.
def save_failure_transcript(
    transcript_path: Path,
    error: Exception,
    execution: ExecutionResult | None,
) -> bool:
    if execution is not None:
        transcript = execution.transcript
    elif isinstance(error, ProtocolExecutionFailure):
        transcript = error.transcript
    else:
        return False
    transcript_path.write_bytes(transcript)
    return True


## @brief 장치 탐색 또는 전체 M15 자동 HIL을 실행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    board_id = normalize_board_id(args.board_id)
    volume = find_daplink_volume(board_id, args.volume)
    serial_module, list_ports = import_pyserial()
    port_name = find_serial_port(board_id, args.port, list_ports)
    print(
        "NU54DK M15 discovery SUCCESS: "
        f"uid={board_id}, volume={volume.root}, port={port_name}, baud={args.baud}"
    )
    if args.discover_only:
        return 0

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
    execution: ExecutionResult | None = None
    try:
        execution = execute_protocol(
            serial_module=serial_module,
            port_name=port_name,
            baud_rate=args.baud,
            result_timeout_seconds=args.result_timeout,
            flash_callback=lambda: flash_and_release_debug_power(
                volume, image, args.flash_timeout, board_id
            ),
        )
        validate_image_unchanged(image, image_size, image_sha256)
        transcript_path.write_bytes(execution.transcript)
        result = parse_transcript(
            execution.scenario_transcript,
            execution.watchdog_interval_seconds,
            execution.system_off_interval_seconds,
        )
        evidence = build_evidence(
            core_revision=core_revision,
            board_revision=board_revision,
            board_id=board_id,
            volume=volume,
            port_name=port_name,
            image=image,
            image_size=image_size,
            image_sha256=image_sha256,
            transcript_path=transcript_path,
            execution=execution,
            result=result,
            build_record=build_record,
        )
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(
            "M15 AUTO HIL PASS: "
            f"uid={board_id}, device_id={result.device_id}, "
            f"wdt={result.watchdog_interval_seconds:.3f}s, "
            f"system_off={result.system_off_interval_seconds:.3f}s, "
            f"evidence={evidence_path}"
        )
        return 0
    except Exception as error:
        save_failure_transcript(transcript_path, error, execution)
        try:
            recovery = recover_target(args.recovery_mode, board_id, args.recovery_hex)
            print(f"M15 자동 HIL 실패 복구 결과: {recovery}", file=sys.stderr)
        except Exception as recovery_error:
            print(
                f"M15 자동 HIL 실패 뒤 복구도 실패했습니다: {recovery_error}",
                file=sys.stderr,
            )
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"M15 AUTO HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
