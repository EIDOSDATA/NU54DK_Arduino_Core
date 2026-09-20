#!/usr/bin/env python3
"""! @brief MCP/MCS와 CCP/TBS 2-board UART 증거를 엄격히 판정합니다. """

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import re

from m31_ble_capability import ExpectedIdentity


SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
REVISION = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
RAW_IDENTITY = re.compile(r"(?i)\b[0-9a-f]{16,64}\b", re.ASCII)
NORMAL_PATTERN = re.compile(
    r"client: ((?:MEDIA|CALL)_[A-Z_]+) complete=1 normal_ops=(\d+)\Z"
)
SUBMITTED_PATTERN = re.compile(r"client: ((?:MEDIA|CALL)_[A-Z_]+) submitted=1\Z")
MEDIA_NEGATIVE_PATTERN = re.compile(
    r"client: MEDIA_NEG_(OPCODE|STALE_OBJECT) rejected=1 result=(\d+) native=(-?\d+)\Z"
)
CALL_NEGATIVE_PATTERN = re.compile(
    r"client: CALL_NEG_(STALE_INDEX|INVALID_TRANSITION) rejected=1 result=(\d+) native=(-?\d+)\Z"
)
NOTIFICATION_PATTERN = re.compile(r"client: .* notifications=(\d+)\Z")
RECONNECT_PATTERN = re.compile(r"host: HIL\|1\|RECONNECT_OK\|attempt=(\d+)\Z")
CALL_INCOMING_PATTERN = re.compile(r"host: HIL\|1\|CALL_INCOMING\|counted=([01])\Z")
CALL_INCOMING_RESULT = "server: CALL_INCOMING result=0 native=0"
MEDIA_NORMAL = {
    "MEDIA_PLAY", "MEDIA_PAUSE", "MEDIA_SEEK", "MEDIA_NEXT", "MEDIA_PREVIOUS",
    "MEDIA_SELECT", "MEDIA_REFRESH",
}
CALL_NORMAL_COUNTS = {
    "CALL_INCOMING": 12,
    "CALL_ORIGINATE": 10,
    "CALL_ACCEPT": 12,
    "CALL_HOLD": 22,
    "CALL_RETRIEVE": 22,
    "CALL_TERMINATE": 22,
}
REGISTER_NAMES = {
    "dp_idcode", "dp_targetid_observed", "ahb_ap_idr", "ahb_ap_csw", "ctrl_ap_idr",
    "approtect_status",
}


class MediaCallFailure(RuntimeError):
    """! @brief profile 기능·수명·identity 증거가 닫히지 않은 상태입니다. """


@dataclass(frozen=True)
class MediaCallResult:
    """! @brief 검증된 normal·negative·reconnect·notification 분모입니다. """

    profile: str
    normal_operations: int
    normal_by_operation: dict[str, int]
    negative_by_case: dict[str, int]
    recoveries: int
    reconnects: int
    state_notifications: int
    soak_seconds: float


def _lines(transcript: bytes) -> list[str]:
    """! @brief bounded ASCII transcript와 raw probe identity 부재를 확인합니다. """
    if not isinstance(transcript, bytes) or not transcript.endswith(b"\n") or (
        len(transcript) > 500_000 or b"\x00" in transcript
    ):
        raise MediaCallFailure("절단·과대·NUL transcript")
    try:
        lines = transcript.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise MediaCallFailure("비 ASCII transcript") from error
    if not lines or any(
        "uid=" in line.lower() or "probe_id=" in line.lower() or "unique id" in line.lower() or
        RAW_IDENTITY.search(line) is not None for line in lines
    ):
        raise MediaCallFailure("빈 transcript 또는 raw probe UID")
    if any(len(line) > 600 for line in lines):
        raise MediaCallFailure("UART line 길이 한도")
    return lines


def parse_transcript(profile: str, transcript: bytes, soak_seconds: float) -> MediaCallResult:
    """! @brief 실제 공개 Serial 완료·거부·복구·재연결 결과를 분모대로 검사합니다. """
    if profile not in {"media", "call"}:
        raise MediaCallFailure("알 수 없는 profile")
    if soak_seconds < 180.0:
        raise MediaCallFailure("state notification soak가 180초 미만")
    lines = _lines(transcript)
    fatal = ("Stack overflow", "*****", "FATAL", "HardFault", "BusFault")
    if any(any(marker in line for marker in fatal) for line in lines):
        raise MediaCallFailure("target fatal UART marker")

    normal = Counter()
    normal_sequence = []
    submitted = Counter(
        matched.group(1)
        for line in lines
        if (matched := SUBMITTED_PATTERN.fullmatch(line)) is not None
    )
    for line in lines:
        matched = NORMAL_PATTERN.fullmatch(line)
        if matched is None:
            continue
        label, sequence = matched.groups()
        if label.startswith("MEDIA_") != (profile == "media"):
            raise MediaCallFailure("다른 profile normal marker 혼입")
        normal[label] += 1
        normal_sequence.append(int(sequence))
    if normal_sequence != list(range(1, len(normal_sequence) + 1)):
        raise MediaCallFailure("client normal_ops 누락·중복·역행")

    if profile == "media":
        if set(normal) - MEDIA_NORMAL or len(normal_sequence) != 100 or any(
            normal[label] == 0 for label in MEDIA_NORMAL
        ):
            raise MediaCallFailure("media normal 100 ops 또는 역할별 coverage 불일치")
        negative = Counter(
            matched.group(1)
            for line in lines
            if (matched := MEDIA_NEGATIVE_PATTERN.fullmatch(line)) is not None
        )
        if submitted != normal + Counter({
            "MEDIA_NEG_OPCODE": 20,
        }):
            raise MediaCallFailure("media remote 제출·완료 분모 불일치")
        recovery_marker = "client: MEDIA_RECOVERY result=0 native=0"
        normal_total = len(normal_sequence)
    else:
        incoming_flags = []
        incoming_results = 0
        for line in lines:
            matched = CALL_INCOMING_PATTERN.fullmatch(line)
            if matched is not None:
                incoming_flags.append(int(matched.group(1)))
            elif line == CALL_INCOMING_RESULT:
                incoming_results += 1
        if incoming_results != len(incoming_flags) or incoming_flags.count(1) != 12 or (
            incoming_flags.count(0) != 20
        ):
            raise MediaCallFailure("incoming normal/negative setup result 불일치")
        normal["CALL_INCOMING"] = incoming_flags.count(1)
        if dict(normal) != CALL_NORMAL_COUNTS:
            raise MediaCallFailure("call normal 100 ops 또는 opcode별 분모 불일치")
        negative = Counter(
            matched.group(1)
            for line in lines
            if (matched := CALL_NEGATIVE_PATTERN.fullmatch(line)) is not None
        )
        client_normal = Counter(normal)
        del client_normal["CALL_INCOMING"]
        if submitted != client_normal + Counter({
            "CALL_NEG_STALE_INDEX": 20,
            "CALL_NEG_INVALID_TRANSITION": 20,
        }):
            raise MediaCallFailure("call remote 제출·완료 분모 불일치")
        recovery_marker = "client: CALL_RECOVERY result=0 native=0"
        normal_total = sum(normal.values())

    expected_negative = {"OPCODE": 20, "STALE_OBJECT": 20} if profile == "media" else {
        "STALE_INDEX": 20, "INVALID_TRANSITION": 20,
    }
    if dict(negative) != expected_negative:
        raise MediaCallFailure("negative reject 분모 불일치")
    for line in lines:
        matched = (MEDIA_NEGATIVE_PATTERN if profile == "media" else CALL_NEGATIVE_PATTERN).fullmatch(
            line
        )
        if matched is not None and int(matched.group(2)) == 0 and int(matched.group(3)) == 0:
            raise MediaCallFailure("negative가 성공 결과로 기록됨")
    recoveries = lines.count(recovery_marker)
    if recoveries != 40:
        raise MediaCallFailure("negative 후 refresh recovery 분모 불일치")
    reconnect_values = [
        int(matched.group(1)) for line in lines
        if (matched := RECONNECT_PATTERN.fullmatch(line)) is not None
    ]
    if reconnect_values != list(range(1, 21)):
        raise MediaCallFailure("disconnect/reconnect 20/20 분모 불일치")
    notifications = [
        int(matched.group(1)) for line in lines
        if (matched := NOTIFICATION_PATTERN.fullmatch(line)) is not None
    ]
    if not notifications or max(notifications) < 20:
        raise MediaCallFailure("실제 state notification 관찰량 부족")
    if normal_total != 100:
        raise MediaCallFailure("normal operation 총 분모 불일치")
    return MediaCallResult(
        profile=profile,
        normal_operations=normal_total,
        normal_by_operation=dict(normal),
        negative_by_case=dict(negative),
        recoveries=recoveries,
        reconnects=20,
        state_notifications=max(notifications),
        soak_seconds=soak_seconds,
    )


def validate_evidence_envelope(evidence: dict, expected_images: dict[str, str],
                               identity: ExpectedIdentity) -> MediaCallResult:
    """! @brief clean source·full revision·image/config·DP/AP와 UART 측정을 결합합니다. """
    boards = evidence.get("boards")
    if not isinstance(boards, dict) or set(boards) != set(expected_images) or any(
        not isinstance(board, dict) for board in boards.values()
    ):
        raise MediaCallFailure("board role 집합 불일치")
    forbidden_keys = {"uid", "raw_uid", "probe_id", "unique_id"}
    if any(str(key).lower() in forbidden_keys for board in boards.values()
           if isinstance(board, dict) for key in board):
        raise MediaCallFailure("raw probe identity field가 evidence에 포함됨")
    if evidence.get("status") != "PASS" or evidence.get("source_clean") is not True or (
        evidence.get("identity") != vars(identity)
    ):
        raise MediaCallFailure("clean source/full revision identity 불일치")
    if any(REVISION.fullmatch(value) is None for value in vars(identity).values()):
        raise MediaCallFailure("source revision은 full 40-hex여야 함")
    for role, expected_image in expected_images.items():
        board = boards.get(role, {})
        if board.get("image_sha256") != expected_image or SHA256.fullmatch(expected_image) is None:
            raise MediaCallFailure(f"{role} image SHA-256 불일치")
        if SHA256.fullmatch(board.get("config_sha256", "")) is None or (
            SHA256.fullmatch(board.get("probe_sha256", "")) is None
        ):
            raise MediaCallFailure(f"{role} config/probe SHA-256 형식 불일치")
        registers = board.get("probe_registers")
        if not isinstance(registers, dict) or set(registers) != REGISTER_NAMES or any(
            re.fullmatch(r"0x[0-9a-f]{8}", value) is None for value in registers.values()
        ):
            raise MediaCallFailure(f"{role} DP/AP register evidence 불일치")
    transcript = evidence.get("transcript")
    if not isinstance(transcript, bytes) or evidence.get("transcript_sha256") != hashlib.sha256(
        transcript
    ).hexdigest():
        raise MediaCallFailure("transcript hash 불일치")
    return parse_transcript(evidence.get("profile", ""), transcript,
                            float(evidence.get("soak_seconds", 0.0)))
