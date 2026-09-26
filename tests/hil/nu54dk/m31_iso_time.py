#!/usr/bin/env python3
"""! @brief BIS 기반 ISO timestamp 관계와 20회 재시작 원본을 판정합니다. """

from __future__ import annotations

from dataclasses import dataclass

from m31_ble_capability import ExpectedIdentity
from m31_iso_bis import M31BisFailure, parse_bis_transcript, validate_bis_envelope


class M31TimeFailure(RuntimeError):
    """! @brief 실제 SDU timestamp 또는 source 경계가 맞지 않는 오류입니다. """


@dataclass(frozen=True)
class IsoTimeResult:
    """! @brief 두 controller의 독립 시계에서 관찰한 interval 관계를 보존합니다. """

    cycles: int
    total_sent: int
    total_received: int
    valid_monotonic: int
    stale_callback: int
    timestamped_sent: int


def _time_record(line: str, role: str, event: str, nonce: str,
                 fields: set[str]) -> dict[str, str]:
    """! @brief 한 역할·nonce의 bounded timestamp record만 수락합니다. """
    prefix = f"{role}: M31BIS|1|{event}|nonce={nonce}|"
    if len(line) > 512 or not line.startswith(prefix):
        raise M31TimeFailure("time event role/nonce 오류")
    values = {}
    for part in line[len(prefix):].split("|"):
        if part.count("=") != 1:
            raise M31TimeFailure("time field 형식 오류")
        key, value = part.split("=", 1)
        if not key or not value or key in values:
            raise M31TimeFailure("time field 누락·중복")
        values[key] = value
    if set(values) != fields:
        raise M31TimeFailure("time field 집합 오류")
    return values


def _number(values: dict[str, str], name: str, maximum: int) -> int:
    """! @brief 시간·카운터의 정수·범위를 고정합니다. """
    value = values[name]
    if not value.isdecimal():
        raise M31TimeFailure(f"{name} numeric 오류")
    result = int(value)
    if result > maximum:
        raise M31TimeFailure(f"{name} range 오류")
    return result


def _common(transcript: bytes, nonces: list[str], identity: ExpectedIdentity) -> tuple[bytes, object]:
    """! @brief TIME line을 제거한 뒤 기존 BIS SDU·BIG 계약을 그대로 검사합니다. """
    if not isinstance(transcript, bytes) or not transcript.endswith(b"\n"):
        raise M31TimeFailure("절단 time transcript")
    try:
        lines = transcript.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise M31TimeFailure("비 ASCII time transcript") from error
    ordinary = [line for line in lines if "|TIME_TX_END|" not in line and "|TIME_END|" not in line]
    raw = ("\n".join(ordinary) + "\n").encode("ascii")
    try:
        result = parse_bis_transcript(raw, nonces, identity)
    except M31BisFailure as error:
        raise M31TimeFailure(str(error)) from error
    return raw, result


def parse_time_transcript(transcript: bytes, nonces: list[str],
                          identity: ExpectedIdentity) -> IsoTimeResult:
    """! @brief 첫 HCI 기준시각 이후 99개 send_ts와 100개 RX 시각을 검사합니다. """
    _ordinary, bis = _common(transcript, nonces, identity)
    lines = transcript.decode("ascii").splitlines()
    time_lines = [line for line in lines if "|TIME_TX_END|" in line or "|TIME_END|" in line]
    if len(time_lines) != 40:
        raise M31TimeFailure("20-cycle time event 분모 오류")
    total_valid = 0
    total_timestamped = 0
    for nonce in nonces:
        source_lines = [line for line in lines if line.startswith(
            f"source: M31BIS|1|TIME_TX_END|nonce={nonce}|")]
        receiver_lines = [line for line in lines if line.startswith(
            f"receiver: M31BIS|1|TIME_END|nonce={nonce}|")]
        if len(source_lines) != 1 or len(receiver_lines) != 1:
            raise M31TimeFailure("cycle time event 누락·중복")
        tx = _time_record(source_lines[0], "source", "TIME_TX_END", nonce,
                          {"timestamped", "first_ts", "last_ts"})
        rx = _time_record(receiver_lines[0], "receiver", "TIME_END", nonce,
                          {"valid", "stale", "first_ts", "last_ts"})
        if lines.index(source_lines[0]) >= lines.index(
            f"source: M31BIS|1|TX_END|nonce={nonce}|sent=100") or (
            lines.index(receiver_lines[0]) >= next(
                index for index, line in enumerate(lines)
                if line.startswith(f"receiver: M31BIS|1|RX_END|nonce={nonce}|")
            )
        ):
            raise M31TimeFailure("TIME_END가 SDU 완료보다 늦습니다")
        timestamped = _number(tx, "timestamped", 100)
        valid = _number(rx, "valid", 100)
        stale = _number(rx, "stale", 100)
        if timestamped != 99 or valid != 100 or stale != 0:
            raise M31TimeFailure("time SDU 분모 또는 stale callback 오류")
        for record in (tx, rx):
            first = _number(record, "first_ts", 0xffffffff)
            last = _number(record, "last_ts", 0xffffffff)
            if abs(((last - first) & 0xffffffff) - 990000) > 1000:
                raise M31TimeFailure("10ms × 99 timestamp 관계 오류")
        total_timestamped += timestamped
        total_valid += valid
    if bis.total_received != total_valid or bis.total_sent != 2000:
        raise M31TimeFailure("timestamp와 BIS payload 분모 불일치")
    return IsoTimeResult(20, bis.total_sent, bis.total_received, total_valid, 0,
                         total_timestamped)


def validate_time_envelope(envelope: dict, expected_images: dict[str, str],
                           identity: ExpectedIdentity) -> IsoTimeResult:
    """! @brief clean exact 두 probe/image와 time-aware transcript를 교차 확인합니다. """
    if envelope.get("source_clean") is not True or envelope.get("test_id") != "M31-ISO-01:time_sync":
        raise M31TimeFailure("미커밋 time 후보를 exact PASS로 승격")
    ordinary, _bis = _common(envelope.get("transcript"), envelope.get("nonces"), identity)
    try:
        validate_bis_envelope({
            "source_clean": True, "test_id": "M31-ISO-01:bis", "transcript": ordinary,
            "nonces": envelope.get("nonces"), "boards": envelope.get("boards"),
        }, expected_images, identity)
    except M31BisFailure as error:
        raise M31TimeFailure(str(error)) from error
    return parse_time_transcript(envelope["transcript"], envelope["nonces"], identity)
