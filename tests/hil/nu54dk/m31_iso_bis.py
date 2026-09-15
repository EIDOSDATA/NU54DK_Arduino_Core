#!/usr/bin/env python3
"""! @brief M31 BIS source/receiver의 20-cycle raw transcript를 엄격히 판정합니다. """

from __future__ import annotations

from dataclasses import dataclass
import re

from m31_ble_capability import ExpectedIdentity


NONCE = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
REVISION = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
ROLES = ("source", "receiver")
EXPECTED_EVENTS = {
    "source": ("BEGIN", "IDENTITY", "BIG_SYNCED", "SEND_ARMED", "TX_END",
               "BIG_DISCONNECTED", "STOPPED"),
    "receiver": ("BEGIN", "IDENTITY", "PA_SYNCED", "BIG_SYNCED", "RX_END",
                 "BIG_DISCONNECTED", "STOPPED"),
}
EVENT_FIELDS = {
    "READY": {"role"},
    "BEGIN": {"nonce", "role"},
    "IDENTITY": {"nonce", "core", "board", "ncs", "zephyr"},
    "PA_SYNCED": {"nonce"},
    "BIG_SYNCED": {"nonce", "role"},
    "SEND_ARMED": {"nonce"},
    "EMPTY_SLOT": {"nonce", "seq", "flags"},
    "TX_END": {"nonce", "sent"},
    "RX_END": {"nonce", "received", "corrupt", "duplicate", "out_of_order", "empty_slots"},
    "BIG_DISCONNECTED": {"nonce", "reason"},
    "STOPPED": {"nonce", "role", "tx", "rx"},
    "BAD_CODE_READY": set(),
    "BAD_CODE_DISCONNECTED": {"nonce", "reason"},
    "BAD_CODE_REJECTED": {"nonce", "received", "empty_slots", "disconnected"},
    "LOSS_ARMED": {"nonce"},
    "SYNC_LOST": {"nonce"},
}


class M31BisFailure(RuntimeError):
    """! @brief 역할·source·SDU·재시작 증거를 닫을 수 없는 오류입니다. """


@dataclass(frozen=True)
class IsoBisResult:
    """! @brief 검증된 BIS 반복·payload와 controller empty slot을 분리합니다. """

    cycles: int
    total_sent: int
    total_received: int
    minimum_received: int
    empty_slots: int


def record(line: str) -> tuple[str, dict[str, str]]:
    """! @brief 한 줄의 ASCII role/event/field를 중복 없이 읽습니다. """
    if len(line) > 512 or ": M31BIS|1|" not in line:
        raise M31BisFailure("protocol prefix 또는 line 길이 오류")
    role, payload = line.split(": ", 1)
    if role not in ROLES or not payload.startswith("M31BIS|1|"):
        raise M31BisFailure("알 수 없는 role/protocol")
    parts = payload.split("|")
    event = parts[2]
    if event == "FAIL":
        raise M31BisFailure("target FAIL")
    fields = {}
    for part in parts[3:]:
        if part.count("=") != 1:
            raise M31BisFailure("record field 형식 오류")
        key, value = part.split("=", 1)
        if not key or not value or key in fields:
            raise M31BisFailure("record field 누락·중복")
        fields[key] = value
    if event not in EVENT_FIELDS or set(fields) != EVENT_FIELDS[event]:
        raise M31BisFailure("알 수 없는 event/field 또는 누락된 field")
    return role, {"event": event, **fields}


def number(fields: dict[str, str], name: str, maximum: int) -> int:
    """! @brief 음수·소수·한도 초과 숫자를 거부합니다. """
    value = fields.get(name, "")
    if not value.isdecimal():
        raise M31BisFailure(f"{name} numeric 오류")
    result = int(value)
    if result > maximum:
        raise M31BisFailure(f"{name} range 오류")
    return result


def parse_bis_transcript(transcript: bytes, nonces: list[str],
                         identity: ExpectedIdentity) -> IsoBisResult:
    """! @brief 양 BIG의 완전 종료 후 100-SDU session 20개를 검사합니다. """
    if not isinstance(transcript, bytes) or not transcript.endswith(b"\n") or (
        len(transcript) > 100000 or b"\x00" in transcript
    ):
        raise M31BisFailure("절단·과대·NUL transcript")
    if len(nonces) != 20 or len(set(nonces)) != 20 or any(NONCE.fullmatch(item) is None for item in nonces):
        raise M31BisFailure("nonce 분모·중복·형식")
    if any(REVISION.fullmatch(value) is None for value in vars(identity).values()):
        raise M31BisFailure("expected source revision 형식")
    try:
        lines = transcript.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise M31BisFailure("비 ASCII transcript") from error
    if not lines or any("uid=" in line.lower() or "probe_id=" in line.lower() for line in lines):
        raise M31BisFailure("빈 transcript 또는 raw probe UID")
    records = [record(line) for line in lines]
    if len(records) < 2 or {
        role for role, fields in records[:2] if fields == {"event": "READY", "role": role}
    } != set(ROLES):
        raise M31BisFailure("양 역할 READY 누락·중복")
    if any(fields["event"] == "READY" for _role, fields in records[2:]):
        raise M31BisFailure("중복 READY")
    groups: dict[str, dict[str, list[dict[str, str]]]] = {
        nonce: {role: [] for role in ROLES} for nonce in nonces
    }
    current_index = -1
    for role, fields in records[2:]:
        event = fields["event"]
        nonce = fields.get("nonce")
        if nonce not in groups:
            raise M31BisFailure("unknown/stale nonce")
        next_nonce = nonces[current_index + 1] if current_index + 1 < len(nonces) else None
        if event == "BEGIN" and nonce == next_nonce:
            if current_index >= 0 and any(
                sum(entry["event"] == "STOPPED" for entry in groups[nonces[current_index]][prior]) != 1
                for prior in ROLES
            ):
                raise M31BisFailure("이전 BIG 반환 전 재시작")
            current_index += 1
        if current_index < 0 or nonce != nonces[current_index]:
            raise M31BisFailure("nonce/cycle 순서 오류")
        if event not in set(EXPECTED_EVENTS[role]) | {"EMPTY_SLOT"}:
            raise M31BisFailure("역할에 맞지 않는 event")
        if event == "EMPTY_SLOT" and role != "receiver":
            raise M31BisFailure("잘못된 empty slot 역할")
        groups[nonce][role].append(fields)
    if current_index != 19:
        raise M31BisFailure("20-cycle 분모 누락")
    total_sent = 0
    total_received = 0
    minimum_received = 100
    empty_slots = 0
    for nonce in nonces:
        for role in ROLES:
            events = groups[nonce][role]
            effective = [item for item in events if item["event"] != "EMPTY_SLOT"]
            if tuple(item["event"] for item in effective) != EXPECTED_EVENTS[role]:
                raise M31BisFailure(f"{role} event 누락·중복·순서")
            if any(item.get("nonce") != nonce for item in events):
                raise M31BisFailure("role session nonce mismatch")
            for item in events:
                event = item["event"]
                if event == "IDENTITY" and any(
                    item.get(key) != value for key, value in vars(identity).items()
                ):
                    raise M31BisFailure("firmware/source revision mismatch")
                if event in {"BEGIN", "BIG_SYNCED", "STOPPED"} and item.get("role") != role:
                    raise M31BisFailure("role field mismatch")
                if event == "BIG_DISCONNECTED":
                    number(item, "reason", 255)
                if event == "EMPTY_SLOT":
                    number(item, "seq", 65535)
                    if number(item, "flags", 255) not in {4, 12}:
                        raise M31BisFailure("empty slot flags")
            stopped = effective[-1]
            if role == "source":
                sent = number(effective[-3], "sent", 100)
                if sent != 100 or number(stopped, "tx", 100) != sent or number(stopped, "rx", 100) != 0:
                    raise M31BisFailure("source TX 분모/해제 불일치")
                total_sent += sent
            else:
                received = number(effective[-3], "received", 100)
                if received < 99 or number(effective[-3], "corrupt", 100) != 0 or (
                    number(effective[-3], "duplicate", 100) != 0 or
                    number(effective[-3], "out_of_order", 100) != 0 or
                    number(stopped, "rx", 100) != received or number(stopped, "tx", 100) != 0
                ):
                    raise M31BisFailure("receiver RX 수락·무결성·해제 불일치")
                slots = number(effective[-3], "empty_slots", 65535)
                printed = [item for item in events if item["event"] == "EMPTY_SLOT"]
                if len(printed) > 4 or slots < len(printed):
                    raise M31BisFailure("empty slot 출력 상한/카운터 불일치")
                if any(events.index(item) > events.index(effective[-3]) for item in printed):
                    raise M31BisFailure("RX_END 뒤 empty slot")
                total_received += received
                minimum_received = min(minimum_received, received)
                empty_slots += slots
    return IsoBisResult(20, total_sent, total_received, minimum_received, empty_slots)


def validate_bis_envelope(envelope: dict, expected_images: dict[str, str],
                          identity: ExpectedIdentity) -> IsoBisResult:
    """! @brief clean source·두 probe·두 image의 exact 실기 경계를 검사합니다. """
    if envelope.get("source_clean") is not True or envelope.get("test_id") != "M31-ISO-01:bis":
        raise M31BisFailure("미커밋 개발 시도를 완료 증거로 승격")
    boards = envelope.get("boards")
    if not isinstance(boards, dict) or set(boards) != set(ROLES) or set(expected_images) != set(ROLES):
        raise M31BisFailure("board role mapping 오류")
    probes = set()
    for role in ROLES:
        board = boards[role]
        if not isinstance(board, dict) or board.get("image_sha256") != expected_images[role] or (
            SHA256.fullmatch(expected_images[role]) is None or
            SHA256.fullmatch(board.get("probe_sha256", "")) is None
        ):
            raise M31BisFailure("image/probe identity mismatch")
        probes.add(board["probe_sha256"])
    if len(probes) != 2:
        raise M31BisFailure("동일 probe의 양 역할 재사용")
    return parse_bis_transcript(envelope.get("transcript"), envelope.get("nonces"), identity)
