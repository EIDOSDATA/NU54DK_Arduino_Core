#!/usr/bin/env python3
"""! @brief 공개 AudioControl 예제의 2보드 HIL을 자동 판정합니다.

이 runner는 이미 flash된 G/controller와 F/device의 공개 UART 명령만 사용합니다.
flash와 전원 제어는 수행하지 않으며, ``--execute-reset``을 명시한 경우에만
SHA-256 probe identity를 reset helper에 전달하여 F/device를 hardware reset합니다.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Sequence


ROLES = ("controller", "device")
EXPECTED_BOARD_MAP = {
    "controller": {
        "board": "G",
        "port": "COM10",
        "probe_sha256": (
            "e44e2ba24dbcbdd3c41e05192773a058ed7dbbca2354dda703a004646ea9a334"
        ),
    },
    "device": {
        "board": "F",
        "port": "COM14",
        "probe_sha256": (
            "4574ee31f25fe05f154395ea4d8c6aa0583b04a4f7a0ea97fe3d13b05eea8ca0"
        ),
    },
}
BOARD_LABELS = {
    role: str(identity["board"])
    for role, identity in EXPECTED_BOARD_MAP.items()
}
MAX_CAMPAIGN_SECONDS = 180.0
MAX_RECOVERY_SECONDS = 30.0
MARK_QUIET_SECONDS = 0.030
MARK_MAX_SECONDS = 0.250
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
ADDRESS_PATTERN = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")
IDENTIFIER_PATTERN = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{16,}(?![0-9a-f])")
STATE_PATTERN = re.compile(
    r"^volume=(\d+) muted=([01]) offset=(-?\d+) speaker_gain=(-?\d+) "
    r"microphone_muted=([01]) microphone_gain=(-?\d+)$"
)
REPORT_PATTERN = re.compile(r"^(?P<operation>.+) result=(?P<result>\d+) native=(?P<native>-?\d+)$")

PUBLIC_EXAMPLES = {
    "controller": Path(
        "libraries/NUCODE_BLE_Audio/examples/AudioControlController/"
        "AudioControlController.ino"
    ),
    "device": Path(
        "libraries/NUCODE_BLE_Audio/examples/AudioControlDevice/AudioControlDevice.ino"
    ),
}

TOKENS = {
    "controller_found": "Audio control device found",
    "volume_discovery": "Volume discovery started",
    "microphone_discovery": "Microphone discovery started",
    "controller_disconnected": "Audio control device disconnected reason=",
    "device_ready": "Audio control device ready",
    "device_connected": "Audio controller connected",
    "device_disconnected": "Audio controller disconnected reason=",
    "advertising_restarted": "Audio control advertising restarted",
}

FATAL_TOKENS = (
    "Stack overflow",
    "FATAL ERROR",
    "***** Hardware exception",
    "Audio control device start failed",
    "Audio control controller start failed",
    "Audio control recovery limit reached",
    "Audio control disconnect recovery stopped",
    "Audio control phase timeout",
    "Audio control profile failed",
)


class HilFailure(RuntimeError):
    """! @brief HIL 계약 또는 실행 판정 실패를 나타냅니다. """


@dataclass(frozen=True)
class AudioState:
    """! @brief 두 공개 예제가 출력하는 여섯 개의 공통 상태입니다. """

    volume: int
    muted: int
    offset: int
    speaker_gain: int
    microphone_muted: int
    microphone_gain: int


@dataclass(frozen=True)
class Event:
    """! @brief 정제된 UART 한 줄과 공통 시간축 위치를 보존합니다. """

    sequence: int
    at_s: float
    role: str
    text: str


def utc_now() -> str:
    """! @brief 현재 UTC 시각을 ISO 8601 형식으로 반환합니다. """
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    """! @brief 파일 내용을 변경하지 않고 SHA-256을 계산합니다. """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sanitize_line(line: str) -> str:
    """! @brief Bluetooth 주소와 긴 원시 식별자를 transcript에서 제거합니다. """
    sanitized = ADDRESS_PATTERN.sub("<bt-address>", line)
    return IDENTIFIER_PATTERN.sub("<device-identifier>", sanitized)


def parse_state(text: str) -> AudioState | None:
    """! @brief 공개 예제의 고정 상태 한 줄을 구조화합니다. """
    match = STATE_PATTERN.fullmatch(text)
    if match is None:
        return None
    values = tuple(int(value) for value in match.groups())
    state = AudioState(*values)
    if not 0 <= state.volume <= 255:
        return None
    if not -255 <= state.offset <= 255:
        return None
    if not -100 <= state.speaker_gain <= 100:
        return None
    if not -100 <= state.microphone_gain <= 100:
        return None
    return state


def parse_report(text: str, expected_operation: str) -> tuple[int, int] | None:
    """! @brief 공개 report() 출력에서 stable Error와 native code를 읽습니다. """
    match = REPORT_PATTERN.fullmatch(text)
    if match is None or match.group("operation") != expected_operation:
        return None
    return int(match.group("result")), int(match.group("native"))


def verify_source(core_root: Path, expected_revision: str) -> dict[str, str]:
    """! @brief Core를 exact commit과 untracked 포함 clean 상태로 고정합니다. """
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
        raise HilFailure(f"Core source 확인 실패: {error}") from error
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
            raise HilFailure(f"공개 {role} 예제를 찾을 수 없습니다: {source}")
        hashes[role] = sha256_file(source)
    return hashes


def validate_board_map(
    ports: dict[str, str], probe_hashes: dict[str, str]
) -> None:
    """! @brief 고정 G/F 역할과 COM/probe hash 대응을 fail-closed 검사합니다. """
    for role in ROLES:
        expected = EXPECTED_BOARD_MAP[role]
        if ports.get(role) != expected["port"]:
            raise HilFailure(
                f"{role} port는 {expected['board']}/{expected['port']}여야 합니다."
            )
        if probe_hashes.get(role) != expected["probe_sha256"]:
            raise HilFailure(
                f"{role} probe identity가 고정 board map과 일치하지 않습니다."
            )


def validate_probe_inventory(live_hashes: Sequence[str]) -> dict[str, Any]:
    """! @brief hash만 받은 live probe 목록에 각 고정 probe가 한 개씩 있는지 검사합니다. """
    matches: dict[str, int] = {}
    for role in ROLES:
        expected_hash = str(EXPECTED_BOARD_MAP[role]["probe_sha256"])
        count = sum(value == expected_hash for value in live_hashes)
        if count != 1:
            raise HilFailure(
                f"{role} live probe hash match는 정확히 1개여야 합니다: count={count}"
            )
        matches[role] = count
    return {
        "connected_probe_count": len(live_hashes),
        "expected_hash_matches": matches,
    }


def preflight_live_probes() -> dict[str, Any]:
    """! @brief 원시 UID를 출력하지 않고 연결 probe를 SHA-256으로만 대조합니다. """
    try:
        from pyocd.core.helpers import ConnectHelper
    except ImportError as error:
        raise HilFailure("live probe preflight에는 pyOCD가 필요합니다.") from error

    try:
        hidden_stdout = io.StringIO()
        hidden_stderr = io.StringIO()
        with redirect_stdout(hidden_stdout), redirect_stderr(hidden_stderr):
            probes = ConnectHelper.get_all_connected_probes(
                blocking=False, print_wait_message=False
            )
            live_hashes = [
                hashlib.sha256(probe.unique_id.encode("utf-8")).hexdigest()
                for probe in probes
            ]
    except Exception as error:
        raise HilFailure("live probe hash preflight에 실패했습니다.") from error
    return validate_probe_inventory(live_hashes)


class Campaign:
    """! @brief 두 UART를 한 시간축에서 수집하고 bounded 판정을 제공합니다. """

    def __init__(
        self,
        serial_module: Any,
        ports: dict[str, str],
        baud: int,
        transcript_path: Path,
        total_timeout: float,
    ) -> None:
        self.serial_module = serial_module
        self.ports = ports
        self.baud = baud
        self.transcript_path = transcript_path
        self.started = time.monotonic()
        self.deadline = self.started + total_timeout
        self.streams: dict[str, Any] = {}
        self.pending = {role: bytearray() for role in ROLES}
        self.events: list[Event] = []
        self.transcript: Any = None

    def __enter__(self) -> Campaign:
        """! @brief 새 transcript를 만들고 명시된 두 COM만 엽니다. """
        self.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        self.transcript = self.transcript_path.open(
            "x", encoding="utf-8", newline="\n"
        )
        try:
            for role in ROLES:
                self.streams[role] = self.serial_module.Serial(
                    self.ports[role],
                    self.baud,
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
        """! @brief 성공과 실패 모두에서 UART와 transcript를 닫습니다. """
        self.close()

    def close(self) -> None:
        """! @brief 열린 자원을 중복 호출에 안전하게 정리합니다. """
        for stream in self.streams.values():
            try:
                stream.close()
            except Exception:
                pass
        self.streams.clear()
        if self.transcript is not None:
            self.transcript.close()
            self.transcript = None

    def remaining(self) -> float:
        """! @brief 전체 campaign에 남은 시간을 초로 반환합니다. """
        return self.deadline - time.monotonic()

    def bounded_timeout(self, requested: float, description: str) -> float:
        """! @brief 개별 대기를 전체 deadline 안으로 제한합니다. """
        remaining = self.remaining()
        if remaining <= 0.0:
            raise HilFailure(f"전체 campaign timeout: {description}")
        return min(requested, remaining)

    def mark(self, require_quiet: bool = True) -> int:
        """! @brief 이전 UART 자료를 수집하고 요청 시 실제 quiet 경계를 반환합니다. """
        if not require_quiet:
            self.pump()
            if any(self.pending.values()):
                raise HilFailure("UART action 경계에 불완전한 이전 줄이 남았습니다.")
            return len(self.events)
        timeout = self.bounded_timeout(
            MARK_MAX_SECONDS, "UART action boundary quiescence"
        )
        deadline = time.monotonic() + timeout
        quiet_since: float | None = None
        while time.monotonic() < deadline:
            captured = self.pump()
            has_buffered_bytes = any(
                stream.in_waiting > 0 for stream in self.streams.values()
            )
            has_partial_line = any(self.pending[role] for role in ROLES)
            now = time.monotonic()
            if captured or has_buffered_bytes or has_partial_line:
                quiet_since = None
            elif quiet_since is None:
                quiet_since = now
            elif now - quiet_since >= MARK_QUIET_SECONDS:
                return len(self.events)
            time.sleep(0.003)
        raise HilFailure("UART action 경계에서 bounded quiescence를 확보하지 못했습니다.")

    def record(self, role: str, text: str) -> Event:
        """! @brief 한 UART 줄을 정제한 뒤 JSON과 동일한 순서로 기록합니다. """
        event = Event(
            sequence=len(self.events),
            at_s=round(time.monotonic() - self.started, 3),
            role=role,
            text=sanitize_line(text[:800]),
        )
        self.events.append(event)
        self.transcript.write(f"{event.at_s:09.3f}|{event.role}|{event.text}\n")
        self.transcript.flush()
        if any(token in event.text for token in FATAL_TOKENS):
            raise HilFailure(f"{role} fatal UART: {event.text}")
        return event

    def pump(self) -> list[Event]:
        """! @brief 두 UART의 현재 가용 자료를 줄 단위로 수집합니다. """
        captured: list[Event] = []
        for role, stream in self.streams.items():
            data = stream.read(stream.in_waiting or 1)
            if not data:
                continue
            self.pending[role].extend(data)
            while b"\n" in self.pending[role]:
                raw, _, remainder = self.pending[role].partition(b"\n")
                self.pending[role] = bytearray(remainder)
                text = raw.rstrip(b"\r").decode(
                    "utf-8", errors="backslashreplace"
                )
                captured.append(self.record(role, text))
        return captured

    def send(self, role: str, command: str) -> None:
        """! @brief 공개 예제가 정의한 ASCII 한 글자만 전송합니다. """
        if role not in ROLES or len(command) != 1 or not command.isascii():
            raise HilFailure("UART 명령은 알려진 role의 ASCII 한 글자여야 합니다.")
        written = self.streams[role].write(command.encode("ascii"))
        self.streams[role].flush()
        if written != 1:
            raise HilFailure(f"{role} UART 명령 전송이 완전하지 않습니다.")

    def wait_event(
        self,
        predicate: Callable[[Event], bool],
        timeout: float,
        since: int,
        description: str,
    ) -> Event:
        """! @brief 조건에 맞는 event를 bounded timeout 안에서 기다립니다. """
        deadline = time.monotonic() + self.bounded_timeout(timeout, description)
        cursor = since
        while time.monotonic() < deadline:
            self.pump()
            while cursor < len(self.events):
                event = self.events[cursor]
                cursor += 1
                if predicate(event):
                    return event
            time.sleep(0.005)
        recent = " | ".join(
            f"{event.role}:{event.text}" for event in self.events[-12:]
        )
        raise HilFailure(f"timeout: {description}; recent={recent}")

    def wait_report(
        self,
        role: str,
        operation: str,
        timeout: float,
        since: int,
    ) -> tuple[Event, int, int]:
        """! @brief 지정한 공개 operation의 report 한 줄을 기다립니다. """
        event = self.wait_event(
            lambda item: item.role == role
            and parse_report(item.text, operation) is not None,
            timeout,
            since,
            f"{role} {operation} report",
        )
        parsed = parse_report(event.text, operation)
        if parsed is None:
            raise HilFailure("내부 report parser 불일치")
        return event, parsed[0], parsed[1]

    def command_report(
        self,
        role: str,
        command: str,
        operation: str,
        timeout: float,
    ) -> tuple[Event, int, int]:
        """! @brief 한 공개 명령을 보내고 해당 동기 결과를 반환합니다. """
        since = self.mark(require_quiet=False)
        self.send(role, command)
        return self.wait_report(role, operation, timeout, since)

    def wait_state(
        self,
        role: str,
        timeout: float,
        since: int,
        predicate: Callable[[AudioState], bool] | None = None,
    ) -> tuple[Event, AudioState]:
        """! @brief role의 유효 상태 줄과 구조화 상태를 기다립니다. """
        def matches(item: Event) -> bool:
            if item.role != role:
                return False
            state = parse_state(item.text)
            return state is not None and (predicate is None or predicate(state))

        event = self.wait_event(matches, timeout, since, f"{role} state")
        state = parse_state(event.text)
        if state is None:
            raise HilFailure("내부 state parser 불일치")
        return event, state

    def pair_state(
        self,
        timeout: float,
        predicate: Callable[[AudioState], bool] | None = None,
    ) -> tuple[AudioState, dict[str, int]]:
        """! @brief s 명령으로 양쪽 상태를 읽고 동일성을 검증합니다. """
        deadline = time.monotonic() + self.bounded_timeout(timeout, "상태 수렴")
        last_states: dict[str, AudioState] = {}
        last_sequences: dict[str, int] = {}
        while time.monotonic() < deadline:
            since = self.mark()
            self.send("controller", "s")
            self.send("device", "s")
            slice_deadline = min(deadline, time.monotonic() + 1.0)
            cursor = since
            while time.monotonic() < slice_deadline:
                self.pump()
                while cursor < len(self.events):
                    event = self.events[cursor]
                    cursor += 1
                    state = parse_state(event.text)
                    if event.role in ROLES and state is not None:
                        last_states[event.role] = state
                        last_sequences[event.role] = event.sequence
                if len(last_states) == 2:
                    controller = last_states["controller"]
                    device = last_states["device"]
                    if controller == device and (
                        predicate is None or predicate(controller)
                    ):
                        return controller, last_sequences
                time.sleep(0.005)
        raise HilFailure(f"두 보드 상태가 수렴하지 않았습니다: {last_states}")


def changed_state(state: AudioState, field: str, value: int) -> AudioState:
    """! @brief 한 필드만 바꾼 예상 상태를 생성합니다. """
    values = asdict(state)
    values[field] = value
    return AudioState(**values)


def run_controller_write(
    campaign: Campaign,
    command: str,
    operation: str,
    field: str,
    expected_value: int,
    timeout: float,
) -> dict[str, Any]:
    """! @brief controller write가 device와 왕복 수렴하는지 검증합니다. """
    before, _ = campaign.pair_state(timeout)
    expected = changed_state(before, field, expected_value)
    event, result, native = campaign.command_report(
        "controller", command, operation, timeout
    )
    if result != 0:
        raise HilFailure(f"{operation} 요청 거부: result={result} native={native}")
    after, sequences = campaign.pair_state(
        timeout, lambda state: state == expected
    )
    return {
        "operation": operation,
        "command": command,
        "field": field,
        "before": asdict(before),
        "after": asdict(after),
        "report_sequence": event.sequence,
        "state_sequences": sequences,
    }


def run_round_trip(campaign: Campaign, timeout: float) -> dict[str, Any]:
    """! @brief volume·mute·VOCS·VCP AICS·MICP read/write를 왕복합니다. """
    initial, _ = campaign.pair_state(timeout)
    if initial.offset > 247 or initial.speaker_gain >= 100 or initial.microphone_gain >= 100:
        raise HilFailure("증가형 공개 명령 시험에 필요한 초기 range headroom이 없습니다.")

    volume_command = "+" if initial.volume <= 250 else "-"
    volume_operation = "Volume up" if volume_command == "+" else "Volume down"
    volume_value = (
        min(255, initial.volume + 5)
        if volume_command == "+"
        else max(0, initial.volume - 5)
    )
    writes = [
        run_controller_write(
            campaign,
            volume_command,
            volume_operation,
            "volume",
            volume_value,
            timeout,
        )
    ]

    state, _ = campaign.pair_state(timeout)
    writes.append(
        run_controller_write(campaign, "m", "Volume mute", "muted", 1, timeout)
    )
    writes.append(
        run_controller_write(campaign, "u", "Volume unmute", "muted", 0, timeout)
    )
    state, _ = campaign.pair_state(timeout)
    writes.append(
        run_controller_write(
            campaign, "o", "Output offset", "offset", state.offset + 8, timeout
        )
    )
    state, _ = campaign.pair_state(timeout)
    writes.append(
        run_controller_write(
            campaign,
            "g",
            "Program input gain",
            "speaker_gain",
            state.speaker_gain + 1,
            timeout,
        )
    )
    writes.append(
        run_controller_write(
            campaign,
            "c",
            "Microphone mute",
            "microphone_muted",
            1,
            timeout,
        )
    )
    writes.append(
        run_controller_write(
            campaign,
            "v",
            "Microphone unmute",
            "microphone_muted",
            0,
            timeout,
        )
    )
    state, _ = campaign.pair_state(timeout)
    writes.append(
        run_controller_write(
            campaign,
            "h",
            "Microphone input gain",
            "microphone_gain",
            state.microphone_gain + 1,
            timeout,
        )
    )

    reads = []
    for command, operation in (
        ("r", "Read volume"),
        ("f", "Read output offset"),
        ("i", "Read program input"),
        ("k", "Read microphone"),
        ("l", "Read microphone input"),
    ):
        before, _ = campaign.pair_state(timeout)
        event, result, native = campaign.command_report(
            "controller", command, operation, timeout
        )
        if result != 0:
            raise HilFailure(f"{operation} 요청 거부: result={result} native={native}")
        completion_event, completed = campaign.wait_state(
            "controller",
            timeout,
            event.sequence + 1,
            lambda state, expected=before: state == expected,
        )
        after, sequences = campaign.pair_state(
            timeout, lambda state, expected=before: state == expected
        )
        reads.append(
            {
                "operation": operation,
                "command": command,
                "state": asdict(after),
                "report_sequence": event.sequence,
                "completion_sequence": completion_event.sequence,
                "completed_state": asdict(completed),
                "state_sequences": sequences,
            }
        )
    return {"initial": asdict(initial), "writes": writes, "reads": reads}


def run_device_notification(
    campaign: Campaign,
    command: str,
    operation: str,
    field: str,
    expected_value: int,
    timeout: float,
) -> dict[str, Any]:
    """! @brief device local 변경이 controller 구독 알림으로 도착하는지 검증합니다. """
    before, _ = campaign.pair_state(timeout)
    expected = changed_state(before, field, expected_value)
    since = campaign.mark()
    campaign.send("device", command)
    report_event, result, native = campaign.wait_report(
        "device", operation, timeout, since
    )
    if result != 0:
        raise HilFailure(f"device {operation} 거부: result={result} native={native}")
    notify_event, notified = campaign.wait_state(
        "controller",
        timeout,
        since,
        lambda state: state == expected,
    )
    after, sequences = campaign.pair_state(
        timeout, lambda state: state == expected
    )
    return {
        "operation": operation,
        "command": command,
        "field": field,
        "before": asdict(before),
        "notified": asdict(notified),
        "after": asdict(after),
        "report_sequence": report_event.sequence,
        "notification_sequence": notify_event.sequence,
        "state_sequences": sequences,
    }


def run_notifications(campaign: Campaign, timeout: float) -> list[dict[str, Any]]:
    """! @brief 다섯 상태 군의 subscription/notification을 검증합니다. """
    state, _ = campaign.pair_state(timeout)
    if state.offset > 247 or state.speaker_gain >= 100 or state.microphone_gain >= 100:
        raise HilFailure("notification 시험에 필요한 초기 range headroom이 없습니다.")
    volume_command = "+" if state.volume <= 250 else "-"
    volume_operation = "Volume up" if volume_command == "+" else "Volume down"
    volume_value = (
        min(255, state.volume + 5)
        if volume_command == "+"
        else max(0, state.volume - 5)
    )
    results = [
        run_device_notification(
            campaign,
            volume_command,
            volume_operation,
            "volume",
            volume_value,
            timeout,
        )
    ]
    state, _ = campaign.pair_state(timeout)
    results.append(
        run_device_notification(
            campaign, "o", "Output offset", "offset", state.offset + 8, timeout
        )
    )
    state, _ = campaign.pair_state(timeout)
    results.append(
        run_device_notification(
            campaign,
            "i",
            "Program input gain",
            "speaker_gain",
            state.speaker_gain + 1,
            timeout,
        )
    )
    state, _ = campaign.pair_state(timeout)
    microphone_command = "c" if state.microphone_muted == 0 else "v"
    microphone_operation = (
        "Microphone mute" if microphone_command == "c" else "Microphone unmute"
    )
    results.append(
        run_device_notification(
            campaign,
            microphone_command,
            microphone_operation,
            "microphone_muted",
            1 - state.microphone_muted,
            timeout,
        )
    )
    state, _ = campaign.pair_state(timeout)
    results.append(
        run_device_notification(
            campaign,
            "g",
            "Microphone input gain",
            "microphone_gain",
            state.microphone_gain + 1,
            timeout,
        )
    )
    return results


def drive_to_invalid(
    campaign: Campaign,
    command: str,
    operation: str,
    field: str,
    maximum: int,
    increment: int,
    maximum_attempts: int,
    timeout: float,
) -> dict[str, Any]:
    """! @brief 증가형 공개 명령으로 상한과 첫 invalid_argument를 확인합니다. """
    before, _ = campaign.pair_state(timeout)
    current = getattr(before, field)
    attempts = 0
    successful = 0
    rejection: dict[str, Any] | None = None
    while attempts < maximum_attempts:
        attempts += 1
        previous, _ = campaign.pair_state(timeout)
        if getattr(previous, field) != current:
            raise HilFailure(f"{field} range 시험 중 비결정적 상태 변경")
        event, result, native = campaign.command_report(
            "controller", command, operation, timeout
        )
        next_value = current + increment
        if next_value <= maximum:
            if result != 0:
                raise HilFailure(
                    f"{operation} 유효 범위가 거부됨: value={next_value} result={result}"
                )
            current = next_value
            expected = changed_state(previous, field, current)
            campaign.pair_state(timeout, lambda state: state == expected)
            successful += 1
            continue
        if result != 1:
            raise HilFailure(
                f"{operation} 상한 초과가 invalid_argument(1)가 아님: result={result}"
            )
        unchanged, sequences = campaign.pair_state(
            timeout, lambda state: state == previous
        )
        rejection = {
            "attempted_value": next_value,
            "result": result,
            "native": native,
            "report_sequence": event.sequence,
            "unchanged": asdict(unchanged),
            "state_sequences": sequences,
        }
        break
    if rejection is None:
        raise HilFailure(f"{operation} invalid range 거부를 관찰하지 못했습니다.")
    return {
        "operation": operation,
        "field": field,
        "minimum_observed": getattr(before, field),
        "maximum": maximum,
        "successful_increments": successful,
        "attempts": attempts,
        "rejection": rejection,
    }


def run_volume_saturation(campaign: Campaign, timeout: float) -> dict[str, Any]:
    """! @brief VCP relative volume이 uint8 상한에서 포화되는지 확인합니다. """
    initial, _ = campaign.pair_state(timeout)
    successful = 0
    while True:
        before, _ = campaign.pair_state(timeout)
        if before.volume == 255:
            break
        event, result, native = campaign.command_report(
            "controller", "+", "Volume up", timeout
        )
        if result != 0:
            raise HilFailure(f"Volume up 실패: result={result} native={native}")
        expected = changed_state(before, "volume", min(255, before.volume + 5))
        campaign.pair_state(timeout, lambda state: state == expected)
        successful += 1
        if successful > 52:
            raise HilFailure("volume 상한 도달 횟수가 bound를 초과했습니다.")
    at_max, _ = campaign.pair_state(timeout)
    event, result, native = campaign.command_report(
        "controller", "+", "Volume up", timeout
    )
    if result != 0:
        raise HilFailure(f"volume 상한 operation 실패: result={result} native={native}")
    unchanged, sequences = campaign.pair_state(
        timeout, lambda state: state == at_max
    )
    return {
        "initial_volume": initial.volume,
        "maximum_volume": unchanged.volume,
        "successful_increments": successful,
        "saturation_report_sequence": event.sequence,
        "state_sequences": sequences,
    }


def run_ranges(campaign: Campaign, timeout: float) -> dict[str, Any]:
    """! @brief 공개 예제로 도달 가능한 범위와 invalid 상태 거부를 검증합니다. """
    return {
        "volume_saturation": run_volume_saturation(campaign, timeout),
        "output_offset": drive_to_invalid(
            campaign, "o", "Output offset", "offset", 255, 8, 34, timeout
        ),
        "vcp_input_gain": drive_to_invalid(
            campaign,
            "g",
            "Program input gain",
            "speaker_gain",
            100,
            1,
            104,
            timeout,
        ),
        "micp_input_gain": drive_to_invalid(
            campaign,
            "h",
            "Microphone input gain",
            "microphone_gain",
            100,
            1,
            104,
            timeout,
        ),
    }


def run_reset_helper(
    campaign: Campaign,
    helper: Path,
    probe_hash: str,
    timeout: float,
) -> tuple[dict[str, Any], float]:
    """! @brief 원시 UID 없이 hash helper로 한 번 hardware reset합니다. """
    bounded = campaign.bounded_timeout(timeout, "device hardware reset")
    started = time.monotonic()
    try:
        result = subprocess.run(
            (sys.executable, str(helper), probe_hash),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=bounded,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise HilFailure("device reset helper timeout") from error
    if result.returncode != 0:
        raise HilFailure(f"device reset helper 실패: rc={result.returncode}")
    return {"returncode": result.returncode}, started


def wait_reconnected(
    campaign: Campaign,
    since: int,
    timeout: float,
) -> dict[str, Any]:
    """! @brief disconnect 뒤 광고·재연결·양 profile 재준비를 bounded 검증합니다. """
    deadline = time.monotonic() + campaign.bounded_timeout(
        timeout, "device reconnect/profile readiness"
    )

    def remaining(description: str) -> float:
        """! @brief 단일 recovery deadline의 남은 시간을 반환합니다. """
        available = deadline - time.monotonic()
        if available <= 0.0:
            raise HilFailure(f"recovery timeout: {description}")
        return available

    device_ready = campaign.wait_event(
        lambda event: event.role == "device"
        and event.text == TOKENS["device_ready"],
        remaining("device reboot ready"),
        since,
        "device reboot ready",
    )
    disconnected = campaign.wait_event(
        lambda event: event.role == "controller"
        and TOKENS["controller_disconnected"] in event.text,
        remaining("controller disconnect"),
        since,
        "controller disconnect",
    )
    controller_found = campaign.wait_event(
        lambda event: event.role == "controller"
        and event.text == TOKENS["controller_found"],
        remaining("controller rediscovery"),
        disconnected.sequence + 1,
        "controller rediscovery",
    )
    connected = campaign.wait_event(
        lambda event: event.role == "device"
        and event.text == TOKENS["device_connected"],
        remaining("device reconnect"),
        disconnected.sequence + 1,
        "device reconnect",
    )
    volume = campaign.wait_event(
        lambda event: event.role == "controller"
        and event.text == TOKENS["volume_discovery"],
        remaining("volume rediscovery"),
        disconnected.sequence + 1,
        "volume rediscovery",
    )
    microphone = campaign.wait_event(
        lambda event: event.role == "controller"
        and event.text == TOKENS["microphone_discovery"],
        remaining("microphone rediscovery"),
        disconnected.sequence + 1,
        "microphone rediscovery",
    )
    return {
        "device_ready_sequence": device_ready.sequence,
        "disconnect_sequence": disconnected.sequence,
        "controller_found_sequence": controller_found.sequence,
        "connect_sequence": connected.sequence,
        "volume_discovery_sequence": volume.sequence,
        "microphone_discovery_sequence": microphone.sequence,
    }


def run_recovery(
    campaign: Campaign,
    cycles: int,
    helper: Path,
    device_probe_hash: str,
    reset_timeout: float,
    recovery_timeout: float,
) -> list[dict[str, Any]]:
    """! @brief F/device reset 기반 disconnect/reconnect를 정확히 20회 수행합니다. """
    results = []
    for cycle in range(1, cycles + 1):
        since = campaign.mark(require_quiet=False)
        reset, cycle_started = run_reset_helper(
            campaign, helper, device_probe_hash, reset_timeout
        )
        elapsed = time.monotonic() - cycle_started
        remaining = recovery_timeout - elapsed
        if remaining <= 0.0:
            raise HilFailure(
                f"recovery {cycle}가 reset helper 단계에서 "
                f"{recovery_timeout:.1f}초를 초과했습니다."
            )
        recovered = wait_reconnected(campaign, since, remaining)
        elapsed = time.monotonic() - cycle_started
        if elapsed > recovery_timeout or elapsed > MAX_RECOVERY_SECONDS:
            raise HilFailure(
                f"recovery {cycle}가 30.0초 상한을 초과했습니다: {elapsed:.3f}s"
            )
        results.append(
            {
                "cycle": cycle,
                "elapsed_s": round(elapsed, 3),
                "reset": reset,
                "recovery": recovered,
            }
        )
    return results


def wait_initial_ready(campaign: Campaign, timeout: float) -> dict[str, Any]:
    """! @brief 이미 실행 중이거나 새로 연결되는 두 profile의 준비를 확인합니다. """
    since = campaign.mark()
    state, sequences = campaign.pair_state(timeout)
    microphone_sequences = [
        event.sequence
        for event in campaign.events[since:]
        if event.role == "controller"
        and event.text == TOKENS["microphone_discovery"]
    ]
    return {
        "state": asdict(state),
        "state_sequences": sequences,
        "microphone_discovery_sequence": (
            microphone_sequences[-1] if microphone_sequences else None
        ),
    }


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief self-test와 실제 HIL 실행 인자를 정의합니다. """
    parser = argparse.ArgumentParser(
        description="공개 AudioControlController/Device 2보드 HIL runner"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("self-test", help="hardware 없이 parser fixture를 시험합니다.")
    run = subparsers.add_parser("run", help="명시한 두 COM에서 HIL을 수행합니다.")
    run.add_argument(
        "--scope",
        choices=("functional", "recovery"),
        required=True,
        help="180초 계약 안에서 기능/범위 또는 20회 복구 campaign을 선택합니다.",
    )
    for role in ROLES:
        option = role.replace("_", "-")
        run.add_argument(f"--{option}-port", required=True)
        run.add_argument(f"--{option}-probe-sha256", required=True)
        run.add_argument(f"--{option}-image", type=Path, required=True)
        run.add_argument(f"--{option}-image-sha256", required=True)
    run.add_argument("--core-root", type=Path, required=True)
    run.add_argument("--core-revision", required=True)
    run.add_argument("--evidence", type=Path, required=True)
    run.add_argument("--transcript", type=Path)
    run.add_argument("--baud", type=int, default=115200)
    run.add_argument("--operation-timeout", type=float, default=12.0)
    run.add_argument(
        "--total-timeout", type=float, default=MAX_CAMPAIGN_SECONDS
    )
    run.add_argument("--cycles", type=int, default=20)
    run.add_argument("--execute-reset", action="store_true")
    run.add_argument(
        "--reset-helper",
        type=Path,
        default=Path(__file__).with_name("reset_by_probe_hash.py"),
    )
    run.add_argument("--reset-timeout", type=float, default=30.0)
    run.add_argument(
        "--recovery-timeout", type=float, default=MAX_RECOVERY_SECONDS
    )
    return parser.parse_args(arguments)


def validate_run(args: argparse.Namespace) -> tuple[dict[str, Path], Path]:
    """! @brief identity·image·경로·timeout을 UART open 전에 fail-closed 검사합니다. """
    if REVISION_PATTERN.fullmatch(args.core_revision) is None:
        raise HilFailure("core revision은 40자리 소문자 commit hex여야 합니다.")
    if args.baud != 115200:
        raise HilFailure("공개 예제 baud는 정확히 115200이어야 합니다.")
    if not 2.0 <= args.operation_timeout <= 60.0:
        raise HilFailure("operation timeout은 2..60초여야 합니다.")
    if not 120.0 <= args.total_timeout <= MAX_CAMPAIGN_SECONDS:
        raise HilFailure("total timeout은 120..180초여야 합니다.")
    if args.cycles != 20:
        raise HilFailure("M31 recovery 분모는 정확히 20회여야 합니다.")
    if not 5.0 <= args.reset_timeout <= MAX_RECOVERY_SECONDS:
        raise HilFailure("reset timeout은 5..30초여야 합니다.")
    if not 10.0 <= args.recovery_timeout <= MAX_RECOVERY_SECONDS:
        raise HilFailure("recovery timeout은 10..30초여야 합니다.")
    if args.reset_timeout > args.recovery_timeout:
        raise HilFailure("reset timeout은 전체 recovery timeout 이하여야 합니다.")

    ports = {role: getattr(args, f"{role}_port") for role in ROLES}
    if len({port.casefold() for port in ports.values()}) != 2:
        raise HilFailure("controller와 device COM은 서로 달라야 합니다.")
    probe_hashes = {
        role: getattr(args, f"{role}_probe_sha256") for role in ROLES
    }
    if any(HASH_PATTERN.fullmatch(value) is None for value in probe_hashes.values()):
        raise HilFailure("probe SHA-256은 64자리 소문자 hex여야 합니다.")
    if len(set(probe_hashes.values())) != 2:
        raise HilFailure("두 role의 probe SHA-256은 서로 달라야 합니다.")
    validate_board_map(ports, probe_hashes)

    images = {role: getattr(args, f"{role}_image").resolve() for role in ROLES}
    for role, image in images.items():
        if not image.is_file():
            raise HilFailure(f"{role} image가 없습니다: {image}")
        expected_hash = getattr(args, f"{role}_image_sha256")
        if HASH_PATTERN.fullmatch(expected_hash) is None:
            raise HilFailure(f"{role} image SHA-256 형식이 잘못되었습니다.")
        actual_hash = sha256_file(image)
        if actual_hash != expected_hash:
            raise HilFailure(
                f"{role} image hash 불일치: expected={expected_hash}, actual={actual_hash}"
            )

    evidence = args.evidence.resolve()
    transcript = (
        args.transcript.resolve()
        if args.transcript is not None
        else evidence.with_suffix(".transcript.log")
    )
    if evidence.exists():
        raise HilFailure("기존 evidence를 덮어쓰지 않습니다.")
    if transcript.exists():
        raise HilFailure("기존 transcript를 덮어쓰지 않습니다.")
    if evidence == transcript:
        raise HilFailure("evidence와 transcript 경로는 달라야 합니다.")
    if args.execute_reset and not args.reset_helper.resolve().is_file():
        raise HilFailure(f"reset helper가 없습니다: {args.reset_helper.resolve()}")
    return images, transcript


def run_fixture_tests() -> int:
    """! @brief hardware·serial import 없이 고정 transcript fixture를 시험합니다. """
    fixture_count = 0

    def require_failure(action: Callable[[], Any], description: str) -> None:
        """! @brief 지정 fixture가 HilFailure로 닫히는지 확인합니다. """
        nonlocal fixture_count
        try:
            action()
        except HilFailure:
            fixture_count += 1
            return
        raise HilFailure(f"fixture fail-closed 실패: {description}")

    state_line = (
        "volume=105 muted=0 offset=8 speaker_gain=1 "
        "microphone_muted=0 microphone_gain=1"
    )
    expected = AudioState(105, 0, 8, 1, 0, 1)
    if parse_state(state_line) != expected:
        raise HilFailure("fixture state parser 실패")
    fixture_count += 1
    if parse_state("volume=999 muted=0 offset=0 speaker_gain=0 microphone_muted=0 microphone_gain=0") is not None:
        raise HilFailure("fixture state range 거부 실패")
    fixture_count += 1
    if parse_report("Read volume result=0 native=0", "Read volume") != (0, 0):
        raise HilFailure("fixture report parser 실패")
    fixture_count += 1
    if parse_report("Output offset result=1 native=0", "Output offset") != (1, 0):
        raise HilFailure("fixture invalid_argument parser 실패")
    fixture_count += 1
    raw = "peer=AA:BB:CC:DD:EE:FF uid=0123456789abcdef0123456789abcdef"
    sanitized = sanitize_line(raw)
    if "AA:BB" in sanitized or "0123456789abcdef" in sanitized:
        raise HilFailure("fixture identifier 정제 실패")
    fixture_count += 1

    exact_ports = {
        role: str(EXPECTED_BOARD_MAP[role]["port"]) for role in ROLES
    }
    exact_hashes = {
        role: str(EXPECTED_BOARD_MAP[role]["probe_sha256"]) for role in ROLES
    }
    validate_board_map(exact_ports, exact_hashes)
    fixture_count += 1
    require_failure(
        lambda: validate_board_map(
            {"controller": "COM14", "device": "COM10"}, exact_hashes
        ),
        "swapped COM role",
    )
    inventory = validate_probe_inventory(tuple(exact_hashes.values()))
    if inventory["expected_hash_matches"] != {"controller": 1, "device": 1}:
        raise HilFailure("fixture live probe hash inventory 실패")
    fixture_count += 1
    require_failure(
        lambda: validate_probe_inventory((exact_hashes["controller"],)),
        "missing device probe hash",
    )

    parser_args = parse_arguments(
        [
            "run",
            "--scope",
            "functional",
            "--controller-port",
            exact_ports["controller"],
            "--controller-probe-sha256",
            exact_hashes["controller"],
            "--controller-image",
            "controller.bin",
            "--controller-image-sha256",
            "0" * 64,
            "--device-port",
            exact_ports["device"],
            "--device-probe-sha256",
            exact_hashes["device"],
            "--device-image",
            "device.bin",
            "--device-image-sha256",
            "1" * 64,
            "--core-root",
            ".",
            "--core-revision",
            "2" * 40,
            "--evidence",
            "evidence.json",
        ]
    )
    if (
        parser_args.total_timeout != MAX_CAMPAIGN_SECONDS
        or parser_args.recovery_timeout != MAX_RECOVERY_SECONDS
        or parser_args.reset_timeout != MAX_RECOVERY_SECONDS
    ):
        raise HilFailure("fixture hard timeout default 실패")
    fixture_count += 1
    parser_args.total_timeout = MAX_CAMPAIGN_SECONDS + 0.001
    require_failure(lambda: validate_run(parser_args), "loose campaign timeout")

    class FixtureStream:
        """! @brief mark quiescence를 검증하는 비-hardware byte stream입니다. """

        def __init__(self, payload: bytes = b"") -> None:
            self.payload = bytearray(payload)

        @property
        def in_waiting(self) -> int:
            """! @brief 읽지 않은 fixture byte 수를 반환합니다. """
            return len(self.payload)

        def read(self, size: int) -> bytes:
            """! @brief 요청 크기까지 fixture byte를 소비합니다. """
            data = bytes(self.payload[:size])
            del self.payload[:size]
            return data

    fixture_campaign = Campaign(
        None,
        exact_ports,
        115200,
        Path("unused-fixture-transcript.log"),
        2.0,
    )
    fixture_campaign.streams = {
        "controller": FixtureStream(b"Read volume result=0 native=0\n"),
        "device": FixtureStream(),
    }
    fixture_campaign.transcript = io.StringIO()
    boundary = fixture_campaign.mark()
    if boundary != 1 or len(fixture_campaign.events) != 1:
        raise HilFailure("fixture action boundary stale UART drain 실패")
    fixture_count += 1

    with tempfile.TemporaryDirectory(prefix="audio-control-hil-") as directory:
        path = Path(directory) / "evidence.json"
        with path.open("x", encoding="utf-8") as stream:
            json.dump(asdict(expected), stream)
        try:
            path.open("x", encoding="utf-8")
        except FileExistsError:
            pass
        else:
            raise HilFailure("fixture no-overwrite 실패")
    fixture_count += 1
    print(
        f"AUDIO_CONTROL_HIL_SELF_TEST=PASS;FIXTURES={fixture_count};"
        "HARDWARE=UNTOUCHED"
    )
    return 0


def run_hil(args: argparse.Namespace) -> int:
    """! @brief 실제 두 UART campaign을 수행하고 구조화 증적을 새 파일로 남깁니다. """
    images, transcript_path = validate_run(args)
    core_root = args.core_root.resolve()
    source_hashes = verify_source(core_root, args.core_revision)
    probe_preflight = preflight_live_probes()
    try:
        import serial
    except ImportError as error:
        raise HilFailure("실제 HIL 실행에는 pyserial이 필요합니다.") from error

    ports = {role: getattr(args, f"{role}_port") for role in ROLES}
    probe_hashes = {
        role: getattr(args, f"{role}_probe_sha256") for role in ROLES
    }
    image_hashes = {role: sha256_file(path) for role, path in images.items()}
    evidence_path = args.evidence.resolve()
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    status = "FAIL"
    error_text: str | None = None
    result: dict[str, Any] = {}
    campaign: Campaign | None = None
    source_clean_at_finish = False
    try:
        with Campaign(
            serial,
            ports,
            args.baud,
            transcript_path,
            args.total_timeout,
        ) as active:
            campaign = active
            result["initial_ready"] = wait_initial_ready(
                active, args.operation_timeout
            )
            if args.scope == "functional":
                result["read_write_round_trip"] = run_round_trip(
                    active, args.operation_timeout
                )
                result["notifications"] = run_notifications(
                    active, args.operation_timeout
                )
                result["range_and_invalid"] = run_ranges(
                    active, args.operation_timeout
                )
                result["reset_recovery"] = {
                    "status": "NOT_RUN_IN_FUNCTIONAL_SCOPE",
                    "cycles": [],
                }
            elif args.execute_reset:
                result["reset_recovery"] = {
                    "status": "PASS",
                    "cycles": run_recovery(
                        active,
                        args.cycles,
                        args.reset_helper.resolve(),
                        probe_hashes["device"],
                        args.reset_timeout,
                        args.recovery_timeout,
                    ),
                }
            else:
                result["reset_recovery"] = {
                    "status": "SKIP",
                    "reason": "--execute-reset was not specified",
                    "cycles": [],
                }
            final_source_hashes = verify_source(core_root, args.core_revision)
            if final_source_hashes != source_hashes:
                raise HilFailure("campaign 중 공개 예제 source hash가 변경되었습니다.")
            final_image_hashes = {
                role: sha256_file(path) for role, path in images.items()
            }
            if final_image_hashes != image_hashes:
                raise HilFailure("campaign 중 role image hash가 변경되었습니다.")
            campaign_elapsed = time.monotonic() - active.started
            if (
                campaign_elapsed > args.total_timeout
                or campaign_elapsed > MAX_CAMPAIGN_SECONDS
            ):
                raise HilFailure(
                    f"전체 campaign 180.0초 상한 초과: {campaign_elapsed:.3f}s"
                )
            result["campaign_elapsed_s"] = round(campaign_elapsed, 3)
            source_clean_at_finish = True
            status = (
                "PASS"
                if args.scope == "functional" or args.execute_reset
                else "PARTIAL"
            )
    except Exception as error:
        error_text = str(error)

    events = [] if campaign is None else [asdict(event) for event in campaign.events]
    document = {
        "schema": "nucode.m31.audio-control-hil.v1",
        "status": status,
        "scope": args.scope,
        "started_at": started_at,
        "finished_at": utc_now(),
        "core_revision": args.core_revision,
        "source_clean": source_clean_at_finish,
        "source_clean_at_start": True,
        "public_example_sha256": source_hashes,
        "probe_preflight": probe_preflight,
        "runner_behavior": {
            "flashes_devices": False,
            "power_cycles_devices": False,
            "interactive_input": False,
            "hardware_reset_enabled": args.scope == "recovery" and args.execute_reset,
            "reset_target": (
                "device" if args.scope == "recovery" and args.execute_reset else None
            ),
            "opens_only_explicit_com_ports": True,
            "raw_probe_identifiers_recorded": False,
            "existing_files_overwritten": False,
        },
        "board_map": {
            role: {
                "board": BOARD_LABELS[role],
                "port": ports[role],
                "probe_sha256": probe_hashes[role],
                "image_path": str(images[role]),
                "image_sha256": image_hashes[role],
            }
            for role in ROLES
        },
        "criteria": {
            "read_write_fields": 6,
            "read_operations": 5,
            "notification_classes": 5,
            "invalid_range_classes": 3,
            "device_reset_reconnect_cycles": 20,
        },
        "expected_tokens": TOKENS,
        "result": result,
        "events": events,
        "error": error_text,
    }
    try:
        with evidence_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except FileExistsError as error:
        raise HilFailure("종료 시 evidence 경로가 이미 존재하여 덮어쓰지 않았습니다.") from error

    print(
        f"M31_AUDIO_CONTROL_HIL={status};EVENTS={len(events)};"
        f"RESET_CYCLES={len(result.get('reset_recovery', {}).get('cycles', []))};"
        f"EVIDENCE={evidence_path}"
    )
    if status != "PASS":
        print(error_text, file=sys.stderr)
        return 1
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 선택한 action을 실행하고 process exit code를 반환합니다. """
    args = parse_arguments(arguments)
    if args.action == "self-test":
        return run_fixture_tests()
    return run_hil(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HilFailure as error:
        print(f"AUDIO_CONTROL_HIL=FAIL;ERROR={error}", file=sys.stderr)
        raise SystemExit(2) from error
