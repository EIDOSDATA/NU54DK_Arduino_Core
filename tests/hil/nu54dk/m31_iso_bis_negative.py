#!/usr/bin/env python3
"""! @file m31_iso_bis_negative.py
@brief BIS 인증 거부·동기 손실과 즉시 복구의 두 세션 raw 원본을 판정합니다.
"""

from __future__ import annotations

from dataclasses import dataclass

from m31_ble_capability import ExpectedIdentity
from m31_iso_bis import M31BisFailure, NONCE, REVISION, ROLES, SHA256, number, record


NEGATIVE_EVENTS = {
    "wrong_broadcast_code": {
        "source": ("BEGIN", "IDENTITY", "BIG_SYNCED", "SEND_ARMED", "TX_END",
                   "BIG_DISCONNECTED", "STOPPED"),
        "receiver": ("BEGIN", "IDENTITY", "PA_SYNCED", "BIG_SYNCED",
                     "BAD_CODE_DISCONNECTED", "BIG_DISCONNECTED",
                     "BAD_CODE_REJECTED", "STOPPED"),
    },
    "sync_loss": {
        "source": ("BEGIN", "IDENTITY", "BIG_SYNCED", "BIG_DISCONNECTED", "STOPPED"),
        "receiver": ("BEGIN", "IDENTITY", "PA_SYNCED", "BIG_SYNCED", "LOSS_ARMED",
                     "BIG_DISCONNECTED", "SYNC_LOST", "STOPPED"),
    },
}
RECOVERY_EVENTS = {
    "source": ("BEGIN", "IDENTITY", "BIG_SYNCED", "SEND_ARMED", "TX_END",
               "BIG_DISCONNECTED", "STOPPED"),
    "receiver": ("BEGIN", "IDENTITY", "PA_SYNCED", "BIG_SYNCED", "RX_END",
                 "BIG_DISCONNECTED", "STOPPED"),
}


@dataclass(frozen=True)
class NegativeBisResult:
    """! @brief 거부 원인과 새 BIG의 payload 수신을 따로 보존합니다. """

    negative_class: str
    cycles: int
    rejected_payloads: int
    recovery_sent: int
    recovery_received: int
    recovery_empty_slots: int


def parse_negative_transcript(transcript: bytes, nonces: list[str],
                              identity: ExpectedIdentity,
                              negative_class: str) -> NegativeBisResult:
    """! @brief 첫 세션의 실패 원인·자원 반환·둘째 세션의 100-SDU 복구를 확인합니다. """
    if negative_class not in NEGATIVE_EVENTS or not isinstance(transcript, bytes) or (
        not transcript.endswith(b"\n") or len(transcript) > 20000 or b"\x00" in transcript
    ):
        raise M31BisFailure("negative 종류 또는 raw 원본 오류")
    if len(nonces) != 2 or len(set(nonces)) != 2 or any(NONCE.fullmatch(value) is None for value in nonces):
        raise M31BisFailure("negative/recovery nonce 오류")
    if any(REVISION.fullmatch(value) is None for value in vars(identity).values()):
        raise M31BisFailure("expected revision 오류")
    try:
        lines = transcript.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise M31BisFailure("non-ASCII raw 원본") from error
    if any("uid=" in line.lower() or "probe_id=" in line.lower() for line in lines):
        raise M31BisFailure("raw probe UID")
    entries = [(role, fields) for role, fields in map(record, lines)]
    if len(entries) < 20 or [item for _role, item in entries[:2]] != [
        {"event": "READY", "role": "source"}, {"event": "READY", "role": "receiver"}
    ]:
        raise M31BisFailure("양 보드 READY 누락")
    start_index = 2
    if negative_class == "wrong_broadcast_code":
        if entries[2] != ("receiver", {"event": "BAD_CODE_READY"}):
            raise M31BisFailure("wrong code 선택 누락")
        start_index = 3
    if any(item["event"] in {"READY", "BAD_CODE_READY"} for _role, item in entries[start_index:]):
        raise M31BisFailure("중복 READY 또는 wrong code")

    groups = {nonce: {role: [] for role in ROLES} for nonce in nonces}
    positions: dict[tuple[str, str, str], int] = {}
    cycle = -1
    for position, (role, item) in enumerate(entries[start_index:], start_index):
        nonce = item.get("nonce")
        next_nonce = nonces[cycle + 1] if cycle < 1 else None
        if item["event"] == "BEGIN" and role == "source" and nonce == next_nonce:
            if cycle >= 0 and any(
                sum(previous["event"] == "STOPPED" for previous in groups[nonces[cycle]][prior]) != 1
                for prior in ROLES
            ):
                raise M31BisFailure("두 BIG 반환 전 복구 재시작")
            cycle += 1
        if cycle < 0 or nonce != nonces[cycle]:
            raise M31BisFailure("stale 또는 잘못된 session nonce")
        if item["event"] != "EMPTY_SLOT" and (role, nonce, item["event"]) in positions:
            raise M31BisFailure("negative event 중복")
        positions[(role, nonce, item["event"])] = position
        groups[nonce][role].append(item)
    if cycle != 1:
        raise M31BisFailure("실패·복구 두 세션 누락")

    for index, nonce in enumerate(nonces):
        expected = NEGATIVE_EVENTS[negative_class] if index == 0 else RECOVERY_EVENTS
        for role in ROLES:
            events = groups[nonce][role]
            effective = [item for item in events if item["event"] != "EMPTY_SLOT"]
            if tuple(item["event"] for item in effective) != expected[role]:
                raise M31BisFailure("negative/recovery event 누락·순서·중복")
            if any(item.get("nonce") != nonce for item in events):
                raise M31BisFailure("role nonce mismatch")
            for item in events:
                if item["event"] == "IDENTITY" and any(
                    item.get(key) != value for key, value in vars(identity).items()
                ):
                    raise M31BisFailure("firmware source revision mismatch")
                if item["event"] in {"BEGIN", "BIG_SYNCED", "STOPPED"} and item.get("role") != role:
                    raise M31BisFailure("firmware role mismatch")
                if item["event"] == "EMPTY_SLOT":
                    number(item, "seq", 65535)
                    if role != "receiver" or number(item, "flags", 255) not in {4, 12}:
                        raise M31BisFailure("controller slot 형식 오류")
            if len([item for item in events if item["event"] == "EMPTY_SLOT"]) > 4:
                raise M31BisFailure("bounded slot 출력 위반")
            if effective[-2]["event"] == "BIG_DISCONNECTED":
                number(effective[-2], "reason", 255)

    first = groups[nonces[0]]
    recovered = groups[nonces[1]]
    if negative_class == "wrong_broadcast_code":
        source_end = next(item for item in first["source"] if item["event"] == "TX_END")
        mic_failure = next(item for item in first["receiver"] if item["event"] == "BAD_CODE_DISCONNECTED")
        rejected = next(item for item in first["receiver"] if item["event"] == "BAD_CODE_REJECTED")
        receiver_disconnect = next(item for item in first["receiver"] if item["event"] == "BIG_DISCONNECTED")
        if number(source_end, "sent", 100) != 100 or number(mic_failure, "reason", 255) != 61 or (
            number(receiver_disconnect, "reason", 255) != 61 or
            number(rejected, "received", 100) != 0 or
            number(rejected, "disconnected", 1) != 1 or
            number(rejected, "empty_slots", 65535) < 1 or
            number(first["source"][-1], "tx", 100) != 100 or
            positions[("source", nonces[0], "TX_END")] >
            positions[("receiver", nonces[0], "BAD_CODE_REJECTED")]
        ):
            raise M31BisFailure("MIC 거부 또는 payload 유출")
    else:
        receiver_disconnect = next(item for item in first["receiver"] if item["event"] == "BIG_DISCONNECTED")
        if number(receiver_disconnect, "reason", 255) != 19 or (
            number(first["source"][-1], "tx", 100) != 0 or
            positions[("receiver", nonces[0], "LOSS_ARMED")] >
            positions[("source", nonces[0], "STOPPED")] or
            positions[("source", nonces[0], "STOPPED")] >
            positions[("receiver", nonces[0], "SYNC_LOST")]
        ):
            raise M31BisFailure("유도한 PA/BIG 동기 손실 미확인")
    if any(number(first[role][-1], "rx", 100) != 0 for role in ROLES) or (
        number(first["receiver"][-1], "tx", 100) != 0
    ):
        raise M31BisFailure("negative 자원 반환 카운터 오류")

    source_end = next(item for item in recovered["source"] if item["event"] == "TX_END")
    receiver_end = next(item for item in recovered["receiver"] if item["event"] == "RX_END")
    sent = number(source_end, "sent", 100)
    received = number(receiver_end, "received", 100)
    empty = number(receiver_end, "empty_slots", 65535)
    if sent != 100 or received < 99 or (
        number(receiver_end, "corrupt", 100) != 0 or
        number(receiver_end, "duplicate", 100) != 0 or
        number(receiver_end, "out_of_order", 100) != 0 or
        number(recovered["source"][-1], "tx", 100) != sent or
        number(recovered["source"][-1], "rx", 100) != 0 or
        number(recovered["receiver"][-1], "rx", 100) != received or
        number(recovered["receiver"][-1], "tx", 100) != 0
    ):
        raise M31BisFailure("새 BIG의 100 SDU 즉시 복구 실패")
    return NegativeBisResult(negative_class, 2, 0, sent, received, empty)


def validate_negative_envelope(envelope: dict, images: dict[str, str],
                               identity: ExpectedIdentity) -> NegativeBisResult:
    """! @brief clean source 및 서로 다른 probe/image의 실기 경계를 강제합니다. """
    if envelope.get("source_clean") is not True or envelope.get("test_id") != "M31-ISO-01:bis":
        raise M31BisFailure("negative 개발 후보의 완료 승격")
    boards = envelope.get("boards")
    if not isinstance(boards, dict) or set(boards) != set(ROLES) or set(images) != set(ROLES):
        raise M31BisFailure("board mapping 오류")
    probes = set()
    for role in ROLES:
        board = boards[role]
        if not isinstance(board, dict) or board.get("image_sha256") != images[role] or (
            SHA256.fullmatch(images[role]) is None or
            SHA256.fullmatch(board.get("probe_sha256", "")) is None
        ):
            raise M31BisFailure("image/probe SHA-256 mismatch")
        probes.add(board["probe_sha256"])
    if len(probes) != 2:
        raise M31BisFailure("동일 probe 역할 재사용")
    return parse_negative_transcript(envelope.get("transcript"), envelope.get("nonces"),
                                     identity, envelope.get("negative_class"))
