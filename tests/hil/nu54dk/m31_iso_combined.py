#!/usr/bin/env python3
"""! @file m31_iso_combined.py
@brief 세 보드의 CIS 수신→BIS 전달, 자원 해제, 20회 재시작 원본을 판정합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from m31_ble_capability import ExpectedIdentity
from m31_iso_cis import NONCE, REVISION, SHA256


ROLES = ("peer", "combined", "receiver")
PREFIXES = {"peer": "M31ISO|1|", "combined": "M31COMB|1|", "receiver": "M31BIS|1|"}
FIRMWARE_ROLES = {"peer": "peripheral", "combined": "combined", "receiver": "receiver"}
EVENT_FIELDS = {
    "peer": {
        "READY": {"role"}, "BEGIN": {"nonce", "role"},
        "IDENTITY": {"nonce", "core", "board", "ncs", "zephyr"},
        "ACL_CONNECTED": {"nonce"},
        "ISO_INFO": {"nonce", "can_send", "p_bn", "max_sdu"},
        "ISO_CONNECTED": {"nonce"}, "SEND_ARMED": {"nonce"},
        "TX_END": {"nonce", "sent"},
        "ISO_DISCONNECTED": {"nonce", "reason"},
        "ACL_DISCONNECTED": {"nonce", "reason"},
        "STOPPED": {"nonce", "role", "tx", "rx"},
    },
    "combined": {
        "READY": {"role"}, "BEGIN": {"nonce", "role"},
        "IDENTITY": {"nonce", "core", "board", "ncs", "zephyr"},
        "ACL_CONNECTED": {"nonce"}, "CIS_CONNECTED": {"nonce"},
        "BIG_SYNCED": {"nonce"},
        "CIS_RX_END": {"nonce", "received", "corrupt", "duplicate", "cross_stream", "empty_slots"},
        "BIS_TX_END": {"nonce", "sent", "cross_stream"},
        "CIS_DISCONNECTED": {"nonce", "reason"},
        "ACL_DISCONNECTED": {"nonce", "reason"},
        "BIG_DISCONNECTED": {"nonce", "reason"},
        "STOPPED": {"nonce", "role", "cis_rx", "bis_tx", "cross_stream"},
    },
    "receiver": {
        "READY": {"role"}, "BEGIN": {"nonce", "role"},
        "IDENTITY": {"nonce", "core", "board", "ncs", "zephyr"},
        "PA_SYNCED": {"nonce"}, "BIG_SYNCED": {"nonce", "role"},
        "EMPTY_SLOT": {"nonce", "seq", "flags"},
        "RX_END": {"nonce", "received", "corrupt", "duplicate", "out_of_order", "empty_slots"},
        "BIG_DISCONNECTED": {"nonce", "reason"},
        "STOPPED": {"nonce", "role", "tx", "rx"},
    },
}
EXPECTED_EVENTS = {
    "peer": ("BEGIN", "IDENTITY", "ACL_CONNECTED", "ISO_INFO", "ISO_CONNECTED",
             "SEND_ARMED", "TX_END", "ISO_DISCONNECTED", "ACL_DISCONNECTED", "STOPPED"),
    "receiver": ("BEGIN", "IDENTITY", "PA_SYNCED", "BIG_SYNCED", "RX_END",
                 "BIG_DISCONNECTED", "STOPPED"),
}


class M31CombinedFailure(RuntimeError):
    """! @brief 누락·변조·역할 혼동을 성공으로 승격하지 않는 판정 오류입니다. """


@dataclass(frozen=True)
class CombinedResult:
    """! @brief 세 무선 구간의 독립 분모와 최저 1회 수신치를 보존합니다. """

    cycles: int
    peer_sent: int
    cis_received: int
    bis_forwarded: int
    bis_received: int
    minimum_cis_received: int
    minimum_bis_received: int
    cis_empty_slots: int
    bis_empty_slots: int


def record(line: str) -> tuple[str, dict[str, str]]:
    """! @brief 보드 prefix와 각 event의 정확한 key 집합만 읽습니다. """
    if len(line) > 512 or ": " not in line:
        raise M31CombinedFailure("protocol line 형식·길이 오류")
    role, payload = line.split(": ", 1)
    if role not in ROLES or not payload.startswith(PREFIXES[role]):
        raise M31CombinedFailure("role 또는 protocol prefix 오류")
    parts = payload.split("|")
    event = parts[2]
    if event == "FAIL" or event not in EVENT_FIELDS[role]:
        raise M31CombinedFailure("target FAIL 또는 알 수 없는 event")
    fields = {}
    for part in parts[3:]:
        if part.count("=") != 1:
            raise M31CombinedFailure("event field 형식 오류")
        key, value = part.split("=", 1)
        if not key or not value or key in fields:
            raise M31CombinedFailure("event field 누락·중복")
        fields[key] = value
    if set(fields) != EVENT_FIELDS[role][event]:
        raise M31CombinedFailure("event field 집합 오류")
    return role, {"event": event, **fields}


def number(fields: dict[str, str], key: str, maximum: int) -> int:
    """! @brief ASCII 정수의 부호·한도·누락을 엄격히 확인합니다. """
    value = fields.get(key, "")
    if re.fullmatch(r"[0-9]+", value, re.ASCII) is None:
        raise M31CombinedFailure(f"{key} 숫자 오류")
    result = int(value)
    if result > maximum:
        raise M31CombinedFailure(f"{key} 한도 오류")
    return result


def parse_combined_transcript(transcript: bytes, nonces: list[str],
                              identities: dict[str, ExpectedIdentity],
                              expected_cycles: int = 20) -> CombinedResult:
    """! @brief 3-role 실제 raw의 무결성·전달 수·재시작 순서를 교차 확인합니다. """
    if not isinstance(transcript, bytes) or not transcript.endswith(b"\n") or (
        len(transcript) > 200000 or b"\x00" in transcript
    ):
        raise M31CombinedFailure("절단·과대·NUL transcript")
    if expected_cycles not in {1, 20} or len(nonces) != expected_cycles or (
        len(set(nonces)) != expected_cycles or
        any(NONCE.fullmatch(value) is None for value in nonces)
    ):
        raise M31CombinedFailure("cycle/nonce 분모 오류")
    if set(identities) != set(ROLES) or any(
        REVISION.fullmatch(value) is None
        for identity in identities.values() for value in vars(identity).values()
    ):
        raise M31CombinedFailure("expected firmware revision 오류")
    try:
        lines = transcript.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise M31CombinedFailure("비 ASCII transcript") from error
    if any("uid=" in line.lower() or "probe_id=" in line.lower() for line in lines):
        raise M31CombinedFailure("raw probe UID")
    entries = [record(line) for line in lines]
    if len(entries) < 30 or entries[:3] != [
        (role, {"event": "READY", "role": FIRMWARE_ROLES[role]}) for role in ROLES
    ]:
        raise M31CombinedFailure("세 보드 READY 순서·역할 오류")
    if any(item["event"] == "READY" for _role, item in entries[3:]):
        raise M31CombinedFailure("중복 READY")

    groups = {nonce: {role: [] for role in ROLES} for nonce in nonces}
    positions: dict[tuple[str, str, str], int] = {}
    cycle = -1
    for position, (role, item) in enumerate(entries[3:], 3):
        nonce = item.get("nonce")
        next_nonce = nonces[cycle + 1] if cycle + 1 < expected_cycles else None
        if role == "combined" and item["event"] == "BEGIN" and nonce == next_nonce:
            if cycle >= 0 and any(
                sum(previous["event"] == "STOPPED"
                    for previous in groups[nonces[cycle]][previous_role]) != 1
                for previous_role in ROLES
            ):
                raise M31CombinedFailure("이전 세 역할 자원 반환 전 재시작")
            cycle += 1
        if cycle < 0 or nonce != nonces[cycle]:
            raise M31CombinedFailure("stale/unknown session nonce")
        if item["event"] != "EMPTY_SLOT" and (role, nonce, item["event"]) in positions:
            raise M31CombinedFailure("중복 session event")
        positions[(role, nonce, item["event"])] = position
        groups[nonce][role].append(item)
    if cycle != expected_cycles - 1:
        raise M31CombinedFailure("cycle 분모 누락")

    peer_sent = cis_received = bis_forwarded = bis_received = 0
    minimum_cis = minimum_bis = 100
    cis_empty = bis_empty = 0
    for nonce in nonces:
        peer = groups[nonce]["peer"]
        combined = groups[nonce]["combined"]
        receiver = groups[nonce]["receiver"]
        receiver_effective = [item for item in receiver if item["event"] != "EMPTY_SLOT"]
        for role, items in (("peer", peer), ("receiver", receiver_effective)):
            if tuple(item["event"] for item in items) != EXPECTED_EVENTS[role]:
                raise M31CombinedFailure(f"{role} event 누락·순서·중복")
        combined_names = [item["event"] for item in combined]
        if len(combined_names) != 11 or combined_names[:3] != [
            "BEGIN", "IDENTITY", "ACL_CONNECTED"
        ] or set(combined_names[3:5]) != {"BIG_SYNCED", "CIS_CONNECTED"} or (
            combined_names[5:7] != ["CIS_RX_END", "BIS_TX_END"] or
            set(combined_names[7:10]) != {
                "CIS_DISCONNECTED", "ACL_DISCONNECTED", "BIG_DISCONNECTED"
            } or combined_names[-1] != "STOPPED"
        ):
            raise M31CombinedFailure("combined 연결·전달·해제 event 오류")
        for role, items in (("peer", peer), ("combined", combined),
                            ("receiver", receiver)):
            for item in items:
                if item.get("nonce") != nonce:
                    raise M31CombinedFailure("role nonce mismatch")
                if item["event"] == "IDENTITY" and any(
                    item.get(key) != value for key, value in vars(identities[role]).items()
                ):
                    raise M31CombinedFailure("firmware source revision mismatch")
                if item["event"] in {"BEGIN", "STOPPED"} and (
                    item.get("role") != FIRMWARE_ROLES[role]
                ):
                    raise M31CombinedFailure("firmware role mismatch")
                if item["event"] == "BIG_SYNCED" and role == "receiver" and (
                    item.get("role") != "receiver"
                ):
                    raise M31CombinedFailure("BIG receiver role mismatch")
                if item["event"] in {"BIG_DISCONNECTED", "ISO_DISCONNECTED",
                                     "CIS_DISCONNECTED", "ACL_DISCONNECTED"}:
                    if number(item, "reason", 255) not in {19, 22}:
                        raise M31CombinedFailure("정상 protocol 해제 reason 오류")
                if item["event"] == "EMPTY_SLOT":
                    if role != "receiver" or number(item, "flags", 255) not in {4, 12}:
                        raise M31CombinedFailure("controller empty slot 형식 오류")
                    number(item, "seq", 65535)
        if sum(item["event"] == "EMPTY_SLOT" for item in receiver) > 4:
            raise M31CombinedFailure("bounded empty slot 출력 초과")
        peer_info = peer[3]
        if (number(peer_info, "can_send", 1) != 1 or
            number(peer_info, "p_bn", 255) < 1 or
            number(peer_info, "max_sdu", 4095) != 8):
            raise M31CombinedFailure("CIS peripheral TX 경로 QoS 오류")
        peer_end = peer[6]
        cis_end = combined[5]
        bis_end = combined[6]
        receiver_end = receiver_effective[4]
        sent = number(peer_end, "sent", 100)
        cis = number(cis_end, "received", 100)
        forwarded = number(bis_end, "sent", 100)
        received = number(receiver_end, "received", 100)
        if sent != 100 or cis < 99 or forwarded != cis or received < 99 or (
            received > forwarded or
            any(number(cis_end, key, 100) != 0
                for key in ("corrupt", "duplicate", "cross_stream")) or
            number(bis_end, "cross_stream", 100) != 0 or
            any(number(receiver_end, key, 100) != 0
                for key in ("corrupt", "duplicate", "out_of_order")) or
            number(peer[-1], "tx", 100) != sent or number(peer[-1], "rx", 100) != 0 or
            number(combined[-1], "cis_rx", 100) != cis or
            number(combined[-1], "bis_tx", 100) != forwarded or
            number(combined[-1], "cross_stream", 100) != 0 or
            number(receiver_effective[-1], "tx", 100) != 0 or
            number(receiver_effective[-1], "rx", 100) != received
        ):
            raise M31CombinedFailure("CIS→BIS SDU 분모·무결성·해제 카운터 오류")
        if not (
            positions[("peer", nonce, "SEND_ARMED")] <
            positions[("combined", nonce, "CIS_RX_END")] <
            positions[("combined", nonce, "BIS_TX_END")] <
            positions[("receiver", nonce, "RX_END")]
        ):
            raise M31CombinedFailure("CIS→BIS 전달 순서 오류")
        peer_sent += sent
        cis_received += cis
        bis_forwarded += forwarded
        bis_received += received
        minimum_cis = min(minimum_cis, cis)
        minimum_bis = min(minimum_bis, received)
        cis_empty += number(cis_end, "empty_slots", 65535)
        bis_empty += number(receiver_end, "empty_slots", 65535)
    return CombinedResult(expected_cycles, peer_sent, cis_received, bis_forwarded,
                          bis_received, minimum_cis, minimum_bis, cis_empty, bis_empty)


def validate_combined_envelope(envelope: dict, images: dict[str, str],
                               identity: ExpectedIdentity) -> CombinedResult:
    """! @brief clean revision, 별도 세 probe/image, 20개 session만 PASS로 인정합니다. """
    if envelope.get("source_clean") is not True or (
        envelope.get("test_id") != "M31-ISO-01:bis_cis_combined" or
        envelope.get("cycles") != 20 or envelope.get("identity") != vars(identity)
    ):
        raise M31CombinedFailure("dirty 또는 서로 다른 source의 완료 승격")
    boards = envelope.get("boards")
    if not isinstance(boards, dict) or set(boards) != set(ROLES) or set(images) != set(ROLES):
        raise M31CombinedFailure("three-board mapping 오류")
    probes = set()
    image_hashes = set()
    for role in ROLES:
        board = boards[role]
        if not isinstance(board, dict) or board.get("image_sha256") != images[role] or (
            SHA256.fullmatch(images[role]) is None or
            SHA256.fullmatch(board.get("probe_sha256", "")) is None or
            board.get("flash_mode") != "pyocd-sector-hw-reset"
        ):
            raise M31CombinedFailure("image/probe SHA 또는 sector flash 오류")
        probes.add(board["probe_sha256"])
        image_hashes.add(images[role])
    if len(probes) != 3 or len(image_hashes) != 3:
        raise M31CombinedFailure("한 probe/image의 역할 재사용")
    return parse_combined_transcript(envelope.get("transcript"), envelope.get("nonces"),
                                     {role: identity for role in ROLES})
