#!/usr/bin/env python3
"""! @brief M31 LC3 합성 PCM의 20-cycle codec transcript를 엄격히 판정합니다. """

from __future__ import annotations

from dataclasses import dataclass
import re

from m31_ble_capability import ExpectedIdentity


NONCE = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
REVISION = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
EVENT_FIELDS = {
    "READY": {"scenario", "role"},
    "NEG_END": {"nonce", "scenario", "rejected", "invalid_accept"},
    "BEGIN": {"nonce", "scenario", "role"},
    "IDENTITY": {"nonce", "core", "board", "ncs", "zephyr"},
    "END": {"nonce", "scenario", "encoded", "decoded", "frame_samples", "frame_octets",
            "checksum", "energy", "plc", "errors"},
    "STOPPED": {"nonce", "scenario"},
}


class M31AudioLc3Failure(RuntimeError):
    """! @brief codec 실행이나 exact evidence 계약 위반을 나타냅니다. """


@dataclass(frozen=True)
class AudioLc3Result:
    """! @brief 검증한 frame·negative 분모와 codec 형식을 보존합니다. """

    cycles: int
    encoded_frames: int
    decoded_frames: int
    rejected_invalid: int
    frame_samples: int
    frame_octets: int


def _record(line: str) -> dict[str, str]:
    """! @brief bounded ASCII protocol 한 행의 field 집합을 읽습니다. """
    if len(line) > 512 or not line.startswith("NUCODE_AUDIO|1|"):
        raise M31AudioLc3Failure("protocol prefix 또는 line 길이 오류")
    parts = line.split("|")
    event = parts[2]
    if event == "FAIL":
        raise M31AudioLc3Failure("target FAIL")
    fields: dict[str, str] = {}
    for part in parts[3:]:
        if part.count("=") != 1:
            raise M31AudioLc3Failure("field 형식 오류")
        key, value = part.split("=", 1)
        if not key or not value or key in fields:
            raise M31AudioLc3Failure("field 누락·중복")
        fields[key] = value
    if event not in EVENT_FIELDS or set(fields) != EVENT_FIELDS[event]:
        raise M31AudioLc3Failure("event 또는 field 집합 오류")
    return {"event": event, **fields}


def _number(record: dict[str, str], name: str, maximum: int) -> int:
    """! @brief 음수·소수·범위 초과를 거부합니다. """
    value = record.get(name, "")
    if not value.isdecimal():
        raise M31AudioLc3Failure(f"{name} numeric 오류")
    result = int(value)
    if result > maximum:
        raise M31AudioLc3Failure(f"{name} range 오류")
    return result


def parse_lc3_transcript(transcript: bytes, nonces: list[str],
                         identity: ExpectedIdentity) -> AudioLc3Result:
    """! @brief 20회 각각의 invalid 거부와 100-frame encode/decode를 확인합니다. """
    if not isinstance(transcript, bytes) or not transcript.endswith(b"\n") or (
        len(transcript) > 100000 or b"\x00" in transcript
    ):
        raise M31AudioLc3Failure("절단·과대·NUL transcript")
    if len(nonces) != 20 or len(set(nonces)) != 20 or any(
        NONCE.fullmatch(nonce) is None for nonce in nonces
    ):
        raise M31AudioLc3Failure("nonce 분모·중복·형식 오류")
    if any(REVISION.fullmatch(value) is None for value in vars(identity).values()):
        raise M31AudioLc3Failure("expected source revision 형식 오류")
    try:
        lines = transcript.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise M31AudioLc3Failure("비 ASCII transcript") from error
    if any("uid=" in line.lower() or "probe_id=" in line.lower() for line in lines):
        raise M31AudioLc3Failure("raw probe UID")
    records = [_record(line) for line in lines]
    if not records or records[0] != {
        "event": "READY", "scenario": "lc3-loopback", "role": "codec"
    }:
        raise M31AudioLc3Failure("READY 누락 또는 역할 오류")
    expected_events = ("NEG_END", "BEGIN", "IDENTITY", "END", "STOPPED")
    if len(records) != 1 + len(nonces) * len(expected_events):
        raise M31AudioLc3Failure("20-cycle event 분모 오류")

    encoded_total = 0
    decoded_total = 0
    rejected_total = 0
    for cycle, nonce in enumerate(nonces):
        start = 1 + cycle * len(expected_events)
        cycle_records = records[start:start + len(expected_events)]
        if tuple(record["event"] for record in cycle_records) != expected_events:
            raise M31AudioLc3Failure("cycle event 누락·중복·순서 오류")
        if any(record.get("nonce") != nonce for record in cycle_records):
            raise M31AudioLc3Failure("stale 또는 unknown nonce")
        negative, begin, identity_record, end, stopped = cycle_records
        if any(
            record.get("scenario") != "lc3-loopback"
            for record in (negative, begin, end, stopped)
        ):
            raise M31AudioLc3Failure("audio scenario 불일치")
        if begin.get("role") != "codec":
            raise M31AudioLc3Failure("codec role 불일치")
        if any(identity_record.get(key) != value for key, value in vars(identity).items()):
            raise M31AudioLc3Failure("firmware/source revision mismatch")
        rejected = _number(negative, "rejected", 2)
        invalid_accept = _number(negative, "invalid_accept", 2)
        encoded = _number(end, "encoded", 100)
        decoded = _number(end, "decoded", 100)
        if rejected != 2 or invalid_accept != 0 or encoded != 100 or decoded != 100:
            raise M31AudioLc3Failure("negative 또는 frame 분모 오류")
        if _number(end, "frame_samples", 1000) != 160 or (
            _number(end, "frame_octets", 400) != 40 or
            _number(end, "checksum", 0xffffffff) in {0, 2166136261} or
            _number(end, "energy", 0xffffffff) == 0 or
            _number(end, "plc", 100) != 0 or _number(end, "errors", 100) != 0
        ):
            raise M31AudioLc3Failure("LC3 frame 형식·출력·오류 계약 위반")
        rejected_total += rejected
        encoded_total += encoded
        decoded_total += decoded
    return AudioLc3Result(20, encoded_total, decoded_total, rejected_total, 160, 40)


def validate_lc3_envelope(envelope: dict, expected_image: str,
                          identity: ExpectedIdentity) -> AudioLc3Result:
    """! @brief clean source와 exact image/probe/hardware-reset evidence를 함께 검사합니다. """
    if envelope.get("source_clean") is not True or envelope.get("test_id") != "M31-AUDIO-01:W03-01":
        raise M31AudioLc3Failure("미커밋 개발 시도를 완료 증거로 승격")
    board = envelope.get("board")
    if not isinstance(board, dict) or board.get("image_sha256") != expected_image or (
        SHA256.fullmatch(expected_image) is None or
        SHA256.fullmatch(board.get("probe_sha256", "")) is None or
        board.get("flash_mode") != "pyocd-sector-hw-reset"
    ):
        raise M31AudioLc3Failure("image/probe/reset identity mismatch")
    return parse_lc3_transcript(envelope.get("transcript"), envelope.get("nonces"), identity)
