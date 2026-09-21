#!/usr/bin/env python3
"""! @brief M31 CIS 양 역할의 SDU·해제·재시작 transcript를 엄격히 판정합니다. """

from __future__ import annotations

from dataclasses import dataclass
import re

from m31_ble_capability import ExpectedIdentity


NONCE = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
REVISION = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
ROLES = ("central", "peripheral")
EXPECTED_EVENTS = {
    "central": ("BEGIN", "IDENTITY", "ACL_CONNECTED", "ISO_CONNECTED",
                "TX_END", "ISO_DISCONNECTED", "ACL_DISCONNECTED", "STOPPED"),
    "peripheral": ("BEGIN", "IDENTITY", "ACL_CONNECTED", "ISO_CONNECTED",
                   "RX_END", "ISO_DISCONNECTED", "ACL_DISCONNECTED", "STOPPED"),
}
EVENT_FIELDS = {
    "READY": {"role"},
    "BEGIN": {"nonce", "role"},
    "IDENTITY": {"nonce", "core", "board", "ncs", "zephyr"},
    "ACL_CONNECTED": {"nonce"},
    "ISO_CONNECTED": {"nonce"},
    "RX_INVALID": {"nonce", "seq", "flags", "len"},
    "TX_END": {"nonce", "sent"},
    "RX_END": {"nonce", "received", "corrupt", "duplicate", "invalid_or_lost"},
    "ISO_DISCONNECTED": {"nonce", "reason"},
    "ACL_DISCONNECTED": {"nonce", "reason"},
    "STOPPED": {"nonce", "role", "tx", "rx"},
}


class M31IsoFailure(RuntimeError):
    """! @brief 정확한 기능 증거를 닫을 수 없는 protocol 또는 측정 오류입니다. """


@dataclass(frozen=True)
class IsoCisResult:
    """! @brief 검증된 반복·SDU 수를 image identity와 분리해 보존합니다. """

    cycles: int
    total_sent: int
    total_received: int
    minimum_received: int
    invalid_or_lost: int


def _record(line: str) -> tuple[str, dict[str, str]]:
    """! @brief 역할 표지와 한 번씩만 나온 ASCII key/value를 읽습니다. """
    if len(line) > 512 or ": M31ISO|1|" not in line:
        raise M31IsoFailure("protocol prefix 또는 line 길이 오류")
    role, payload = line.split(": ", 1)
    if role not in ROLES or not payload.startswith("M31ISO|1|"):
        raise M31IsoFailure("알 수 없는 role/protocol")
    parts = payload.split("|")
    event = parts[2]
    if event == "FAIL" or event in {"RX_BAD_LENGTH", "RX_BAD_PAYLOAD"}:
        raise M31IsoFailure(f"target failure: {event}")
    fields = {}
    for part in parts[3:]:
        if part.count("=") != 1:
            raise M31IsoFailure("record field 형식 오류")
        key, value = part.split("=", 1)
        if not key or not value or key in fields:
            raise M31IsoFailure("record field 누락·중복")
        fields[key] = value
    if event not in EVENT_FIELDS or set(fields) != EVENT_FIELDS[event]:
        raise M31IsoFailure("알 수 없는 event/field 또는 누락된 field")
    return role, {"event": event, **fields}


def _number(fields: dict[str, str], name: str, maximum: int) -> int:
    """! @brief 음수·소수·한도 초과 카운터를 거부합니다. """
    value = fields.get(name, "")
    if not value.isdecimal():
        raise M31IsoFailure(f"{name} numeric 오류")
    number = int(value)
    if number > maximum:
        raise M31IsoFailure(f"{name} range 오류")
    return number


def parse_cis_transcript(transcript: bytes, nonces: list[str],
                         identity: ExpectedIdentity) -> IsoCisResult:
    """! @brief 100-SDU 양 역할과 20번 동일 firmware STOP→START를 확인합니다. """
    if not isinstance(transcript, bytes) or not transcript.endswith(b"\n") or (
        len(transcript) > 100000 or b"\x00" in transcript
    ):
        raise M31IsoFailure("절단·과대·NUL transcript")
    if len(nonces) != 20 or len(set(nonces)) != 20 or any(NONCE.fullmatch(item) is None for item in nonces):
        raise M31IsoFailure("nonce 분모·중복·형식")
    if any(REVISION.fullmatch(value) is None for value in vars(identity).values()):
        raise M31IsoFailure("expected source revision 형식")
    try:
        lines = transcript.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise M31IsoFailure("비 ASCII transcript") from error
    if not lines or any("uid=" in line.lower() or "probe_id=" in line.lower() for line in lines):
        raise M31IsoFailure("빈 transcript 또는 raw probe UID")
    records = [_record(line) for line in lines]
    ready = records[:2]
    if {role for role, fields in ready if fields == {"event": "READY", "role": role}} != set(ROLES):
        raise M31IsoFailure("양 역할 READY 누락·중복")
    if any(fields["event"] == "READY" for _role, fields in records[2:]):
        raise M31IsoFailure("중복 READY")
    groups: dict[str, dict[str, list[dict[str, str]]]] = {
        nonce: {role: [] for role in ROLES} for nonce in nonces
    }
    current_index = -1
    for role, fields in records[2:]:
        event = fields["event"]
        nonce = fields.get("nonce")
        if nonce not in groups:
            raise M31IsoFailure("unknown/stale nonce")
        next_nonce = nonces[current_index + 1] if current_index + 1 < len(nonces) else None
        if event == "BEGIN" and nonce == next_nonce:
            if current_index >= 0 and any(
                sum(entry["event"] == "STOPPED" for entry in groups[nonces[current_index]][prior]) != 1
                for prior in ROLES
            ):
                raise M31IsoFailure("이전 session 반환 전 재시작")
            current_index += 1
        if current_index < 0 or nonce != nonces[current_index]:
            raise M31IsoFailure("nonce/cycle 순서 오류")
        if event not in set(EXPECTED_EVENTS[role]) | {"RX_INVALID"}:
            raise M31IsoFailure("알 수 없는 또는 역할에 맞지 않는 event")
        if event == "RX_INVALID" and role != "peripheral":
            raise M31IsoFailure("잘못된 invalid SDU 역할")
        groups[nonce][role].append(fields)
    if current_index != 19:
        raise M31IsoFailure("20-cycle 분모 누락")
    total_sent = 0
    total_received = 0
    minimum_received = 100
    invalid_or_lost = 0
    for nonce in nonces:
        for role in ROLES:
            events = groups[nonce][role]
            effective = [item for item in events if item["event"] != "RX_INVALID"]
            if tuple(item["event"] for item in effective) != EXPECTED_EVENTS[role]:
                raise M31IsoFailure(f"{role} event 누락·중복·순서")
            for item in events:
                if item["event"] == "IDENTITY":
                    if any(item.get(key) != value for key, value in vars(identity).items()):
                        raise M31IsoFailure("firmware/source revision mismatch")
                if item["event"] == "BEGIN" and item.get("role") != role:
                    raise M31IsoFailure("BEGIN role mismatch")
                if item["event"] == "STOPPED" and item.get("role") != role:
                    raise M31IsoFailure("STOP role mismatch")
                if item["event"] == "RX_INVALID":
                    if _number(item, "len", 100) != 0 or _number(item, "flags", 255) not in {4, 12}:
                        raise M31IsoFailure("invalid slot 형식 오류")
                    _number(item, "seq", 65535)
                if item["event"] in {"ISO_DISCONNECTED", "ACL_DISCONNECTED"}:
                    _number(item, "reason", 255)
            if any(item.get("nonce") != nonce for item in events):
                raise M31IsoFailure("role session nonce mismatch")
            end = next(item for item in effective if item["event"] in {"TX_END", "RX_END"})
            stopped = effective[-1]
            if role == "central":
                sent = _number(end, "sent", 100)
                if sent != 100 or _number(stopped, "tx", 100) != sent or _number(stopped, "rx", 100) != 0:
                    raise M31IsoFailure("central TX 분모/해제 불일치")
                total_sent += sent
            else:
                received = _number(end, "received", 100)
                if received < 99 or _number(end, "corrupt", 100) != 0 or (
                    _number(end, "duplicate", 100) != 0 or
                    _number(stopped, "rx", 100) != received or _number(stopped, "tx", 100) != 0
                ):
                    raise M31IsoFailure("peripheral RX 수락·무결성·해제 불일치")
                total_received += received
                minimum_received = min(minimum_received, received)
                invalid_or_lost += _number(end, "invalid_or_lost", 65535)
    return IsoCisResult(20, total_sent, total_received, minimum_received, invalid_or_lost)


def validate_cis_envelope(envelope: dict, expected_images: dict[str, str],
                          identity: ExpectedIdentity) -> IsoCisResult:
    """! @brief 두 exact image·익명 probe·실기 source 경계를 함께 검사합니다. """
    if envelope.get("source_clean") is not True or envelope.get("test_id") != "M31-ISO-01:cis":
        raise M31IsoFailure("미커밋 개발 시도를 완료 증거로 승격")
    boards = envelope.get("boards")
    if not isinstance(boards, dict) or set(boards) != set(ROLES) or set(expected_images) != set(ROLES):
        raise M31IsoFailure("board role mapping 오류")
    probes = set()
    for role in ROLES:
        board = boards[role]
        if not isinstance(board, dict) or board.get("image_sha256") != expected_images[role] or (
            SHA256.fullmatch(expected_images[role]) is None or
            SHA256.fullmatch(board.get("probe_sha256", "")) is None
        ):
            raise M31IsoFailure("image/probe identity mismatch")
        probes.add(board["probe_sha256"])
    if len(probes) != 2:
        raise M31IsoFailure("동일 probe의 양 역할 재사용")
    return parse_cis_transcript(envelope.get("transcript"), envelope.get("nonces"), identity)
