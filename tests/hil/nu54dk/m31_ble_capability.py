#!/usr/bin/env python3
"""! @brief M31 기본 SDC와 별도 Zephyr LL capability를 fail-closed 판정합니다. """

from __future__ import annotations

from dataclasses import dataclass
import re


PREFIX = "M31CAP|1|"
CAPABILITY_BITS = (
    ("cis_central", 28),
    ("cis_peripheral", 29),
    ("bis_broadcaster", 30),
    ("bis_receiver", 31),
    ("cte_tx", 19),
    ("raw_iq_rx", 20),
    ("channel_sounding", 46),
)
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$", re.ASCII)
FEATURE_PATTERN = re.compile(r"^[0-9a-f]{16}$", re.ASCII)
IMAGE_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
CONTROLLER_VARIANTS = ("default_sdc", "zephyr_ll_candidate")


class M31CapabilityFailure(RuntimeError):
    """! @brief 기능·role·revision·증거 경계가 깨졌음을 나타냅니다. """


@dataclass(frozen=True)
class ExpectedIdentity:
    """! @brief target image와 비교할 4개 exact checkout revision입니다. """

    core: str
    board: str
    ncs: str
    zephyr: str


@dataclass(frozen=True)
class CapabilityResult:
    """! @brief HCI bit와 Host Kconfig만 담고 기능 HIL PASS는 포함하지 않습니다. """

    nonce: str
    identity: ExpectedIdentity
    feature_bytes: bytes
    controller_bits: dict[str, bool]
    host_config: dict[str, bool]
    controller_variant: str


def _record(line: str, kind: str, names: tuple[str, ...]) -> dict[str, str]:
    """! @brief 고정 순서·필드 수·중복·빈 값이 있는 record를 거부합니다. """
    parts = line.split("|")
    if parts[:3] != ["M31CAP", "1", kind] or len(parts) != 3 + len(names):
        raise M31CapabilityFailure(f"{kind} record 형식이 다릅니다")
    fields = {}
    for part, expected in zip(parts[3:], names, strict=True):
        if "=" not in part:
            raise M31CapabilityFailure(f"{kind} field가 없습니다")
        key, value = part.split("=", 1)
        if key != expected or not value or key in fields:
            raise M31CapabilityFailure(f"{kind} field 순서·값이 다릅니다")
        fields[key] = value
    return fields


def _strict_lines(transcript: bytes) -> list[str]:
    """! @brief 잡음·절단·과대·비 ASCII·raw probe UID가 섞인 출력을 거부합니다. """
    if not transcript or len(transcript) > 8192 or not transcript.endswith(b"\n"):
        raise M31CapabilityFailure("빈 출력·과대 출력·마지막 newline 누락")
    if b"\x00" in transcript:
        raise M31CapabilityFailure("NUL byte")
    try:
        decoded = transcript.decode("ascii")
    except UnicodeDecodeError as error:
        raise M31CapabilityFailure("비 ASCII transcript") from error
    lines = decoded.replace("\r\n", "\n").splitlines()
    if len(lines) != 12 or any(not line or not line.startswith(PREFIX) for line in lines):
        raise M31CapabilityFailure("protocol line 수·잡음·빈 줄")
    if any("uid=" in line.lower() or "probe_id=" in line.lower() for line in lines):
        raise M31CapabilityFailure("raw probe UID는 저장하지 않습니다")
    return lines


def _bit(features: bytes, position: int) -> bool:
    """! @brief LE feature bit 위치를 raw byte에서 독립 재계산합니다. """
    return (features[position // 8] & (1 << (position % 8))) != 0


def parse_transcript(transcript: bytes, expected_nonce: str,
                     expected_identity: ExpectedIdentity,
                     expected_controller_variant: str = "default_sdc") -> CapabilityResult:
    """! @brief exact identity·nonce·7개 bit·Host 상태를 교차 검사합니다. """
    if NONCE_PATTERN.fullmatch(expected_nonce) is None:
        raise M31CapabilityFailure("expected nonce 형식 오류")
    if any(REVISION_PATTERN.fullmatch(value) is None for value in vars(expected_identity).values()):
        raise M31CapabilityFailure("expected revision 형식 오류")
    if expected_controller_variant not in CONTROLLER_VARIANTS:
        raise M31CapabilityFailure("unknown controller variant")
    lines = _strict_lines(transcript)
    if lines[0] != "M31CAP|1|READY":
        raise M31CapabilityFailure("READY 불일치")
    begin = _record(lines[1], "BEGIN", ("nonce", "controller"))
    identity_fields = _record(lines[2], "IDENTITY", ("nonce", "core", "board", "ncs", "zephyr", "controller"))
    feature_fields = _record(lines[3], "LE_FEATURES", ("nonce", "features"))
    end = _record(lines[-1], "END", ("records", "capabilities", "nonce"))
    if end["records"] != "10" or end["capabilities"] != "7":
        raise M31CapabilityFailure("record/capability 분모 불일치")
    for fields in (begin, identity_fields, feature_fields, end):
        if fields["nonce"] != expected_nonce:
            raise M31CapabilityFailure("stale/wrong nonce")
    if begin["controller"] != expected_controller_variant or (
        identity_fields["controller"] != expected_controller_variant
    ):
        raise M31CapabilityFailure("wrong controller variant")
    actual_identity = ExpectedIdentity(*(identity_fields[key] for key in ("core", "board", "ncs", "zephyr")))
    if actual_identity != expected_identity:
        raise M31CapabilityFailure("revision mismatch")
    feature_hex = feature_fields["features"]
    if FEATURE_PATTERN.fullmatch(feature_hex) is None:
        raise M31CapabilityFailure("LE feature 길이·형식 오류")
    features = bytes.fromhex(feature_hex)
    if expected_controller_variant == "default_sdc" and _bit(features, 21):
        raise M31CapabilityFailure("기본 SDC AoD unsupported 계약 불일치")
    controller_bits = {}
    host_config = {}
    for offset, (identifier, position) in enumerate(CAPABILITY_BITS, 4):
        fields = _record(lines[offset], "CAP", ("nonce", "id", "controller_bit", "host_config"))
        if fields["nonce"] != expected_nonce or fields["id"] != identifier:
            raise M31CapabilityFailure("capability 순서·role·nonce 불일치")
        if fields["controller_bit"] not in {"0", "1"} or fields["host_config"] not in {"0", "1"}:
            raise M31CapabilityFailure("알 수 없는 controller/Host 상태")
        bit = fields["controller_bit"] == "1"
        if bit != _bit(features, position):
            raise M31CapabilityFailure("CAP bit와 raw HCI byte 불일치")
        controller_bits[identifier] = bit
        host_config[identifier] = fields["host_config"] == "1"
    if expected_controller_variant == "default_sdc" and controller_bits["raw_iq_rx"]:
        raise M31CapabilityFailure("기본 SDC IQ RX를 supported로 잘못 승격")
    if expected_controller_variant == "zephyr_ll_candidate" and (
        not controller_bits["raw_iq_rx"] or _bit(features, 22) or
        not host_config["raw_iq_rx"]
    ):
        raise M31CapabilityFailure("Zephyr LL 기본 안테나 IQ 후보 HCI/Host 경계 불일치")
    return CapabilityResult(expected_nonce, actual_identity, features,
                            controller_bits, host_config, expected_controller_variant)


def validate_evidence_envelope(envelope: dict, expected_hex_sha256: str,
                               expected_identity: ExpectedIdentity,
                               expected_controller_variant: str = "default_sdc") -> CapabilityResult:
    """! @brief image hash·role·revision과 transcript를 하나의 attempt로 묶습니다. """
    if IMAGE_PATTERN.fullmatch(expected_hex_sha256) is None:
        raise M31CapabilityFailure("expected image SHA-256 형식 오류")
    if envelope.get("hex_sha256") != expected_hex_sha256:
        raise M31CapabilityFailure("image hash mismatch")
    if envelope.get("role") != "capability_probe":
        raise M31CapabilityFailure("wrong board role")
    transcript = envelope.get("transcript")
    nonce = envelope.get("nonce")
    if not isinstance(transcript, bytes) or not isinstance(nonce, str):
        raise M31CapabilityFailure("missing transcript/nonce")
    return parse_transcript(transcript, nonce, expected_identity,
                            expected_controller_variant)
