#!/usr/bin/env python3
"""! @brief M32 modern LE capability와 자원 프로필을 fail-closed 판정합니다. """

from __future__ import annotations

from dataclasses import dataclass
import re


PREFIX = "M32CAP|1|"
CAPABILITY_BITS = (
    ("sca_update", 26),
    ("power_control_request", 33),
    ("power_change_indication", 34),
    ("path_loss_monitor", 35),
    ("connection_subrating", 37),
    ("connection_subrating_host", 38),
    ("channel_classification", 39),
    ("advertising_coding_selection", 40),
    ("advertising_coding_selection_host", 41),
    ("extended_feature_set", 63),
    ("frame_space_update", 65),
    ("shorter_connection_intervals", 72),
    ("shorter_connection_intervals_host", 73),
)
PROFILE_RESOURCES = {
    "ble_baseline": {
        "connections": 2,
        "peripherals": 1,
        "adv_sets": 1,
        "identities": 1,
        "syncs": 1,
        "acl_tx": 6,
        "acl_rx": 6,
    },
    "ble_extended": {
        "connections": 2,
        "peripherals": 1,
        "adv_sets": 3,
        "identities": 3,
        "syncs": 2,
        "acl_tx": 8,
        "acl_rx": 8,
    },
}
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$", re.ASCII)
IMAGE_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


class M32CapabilityFailure(RuntimeError):
    """! @brief 기능·프로필·revision·증거 경계가 깨졌음을 나타냅니다. """


@dataclass(frozen=True)
class ExpectedIdentity:
    """! @brief target image와 비교할 4개 exact checkout revision입니다. """

    core: str
    board: str
    ncs: str
    zephyr: str


@dataclass(frozen=True)
class CapabilityResult:
    """! @brief HCI bit와 Host Kconfig·자원 값만 담습니다. """

    nonce: str
    identity: ExpectedIdentity
    profile: str
    max_page: int
    feature_bytes: bytes
    resources: dict[str, int]
    controller_bits: dict[str, bool]
    host_config: dict[str, bool]


def _record(line: str, kind: str, names: tuple[str, ...]) -> dict[str, str]:
    """! @brief 고정 순서·필드 수·중복·빈 값이 있는 record를 거부합니다. """
    parts = line.split("|")
    if parts[:3] != ["M32CAP", "1", kind] or len(parts) != 3 + len(names):
        raise M32CapabilityFailure(f"{kind} record 형식이 다릅니다")
    fields = {}
    for part, expected in zip(parts[3:], names, strict=True):
        if "=" not in part:
            raise M32CapabilityFailure(f"{kind} field가 없습니다")
        key, value = part.split("=", 1)
        if key != expected or not value or key in fields:
            raise M32CapabilityFailure(f"{kind} field 순서·값이 다릅니다")
        fields[key] = value
    return fields


def _strict_lines(transcript: bytes) -> list[str]:
    """! @brief 잡음·절단·과대·비 ASCII·raw probe UID가 섞인 출력을 거부합니다. """
    if not transcript or len(transcript) > 8192 or not transcript.endswith(b"\n"):
        raise M32CapabilityFailure("빈 출력·과대 출력·마지막 newline 누락")
    if b"\x00" in transcript:
        raise M32CapabilityFailure("NUL byte")
    try:
        decoded = transcript.decode("ascii")
    except UnicodeDecodeError as error:
        raise M32CapabilityFailure("비 ASCII transcript") from error
    lines = decoded.replace("\r\n", "\n").splitlines()
    if len(lines) != 19 or any(not line or not line.startswith(PREFIX) for line in lines):
        raise M32CapabilityFailure("protocol line 수·잡음·빈 줄")
    if any("uid=" in line.lower() or "probe_id=" in line.lower() for line in lines):
        raise M32CapabilityFailure("raw probe UID는 저장하지 않습니다")
    return lines


def _integer(value: str, field: str, minimum: int = 0, maximum: int = 255) -> int:
    """! @brief 10진 정수를 엄격히 읽고 허용 범위를 확인합니다. """
    if not value.isascii() or not value.isdecimal() or (
        len(value) > 1 and value.startswith("0")
    ):
        raise M32CapabilityFailure(f"{field} 정수 형식 오류")
    parsed = int(value)
    if parsed < minimum or parsed > maximum:
        raise M32CapabilityFailure(f"{field} 범위 오류")
    return parsed


def _bit(features: bytes, position: int) -> bool:
    """! @brief LE feature bit 위치를 raw byte에서 독립 재계산합니다. """
    if position // 8 >= len(features):
        return False
    return (features[position // 8] & (1 << (position % 8))) != 0


def parse_transcript(transcript: bytes, expected_nonce: str,
                     expected_identity: ExpectedIdentity,
                     expected_profile: str) -> CapabilityResult:
    """! @brief exact identity·nonce·13개 bit·자원 프로필을 교차 검사합니다. """
    if NONCE_PATTERN.fullmatch(expected_nonce) is None:
        raise M32CapabilityFailure("expected nonce 형식 오류")
    if any(REVISION_PATTERN.fullmatch(value) is None for value in vars(expected_identity).values()):
        raise M32CapabilityFailure("expected revision 형식 오류")
    if expected_profile not in PROFILE_RESOURCES:
        raise M32CapabilityFailure("unknown resource profile")

    lines = _strict_lines(transcript)
    if lines[0] != "M32CAP|1|READY":
        raise M32CapabilityFailure("READY 불일치")
    begin = _record(lines[1], "BEGIN", ("nonce", "controller", "profile"))
    identity_fields = _record(
        lines[2], "IDENTITY",
        ("nonce", "core", "board", "ncs", "zephyr", "controller", "profile"),
    )
    feature_fields = _record(
        lines[3], "LE_FEATURES", ("nonce", "max_page", "octets", "features")
    )
    resource_names = (
        "connections", "peripherals", "adv_sets", "identities", "syncs", "acl_tx", "acl_rx"
    )
    resource_fields = _record(lines[4], "RESOURCES", ("nonce",) + resource_names)
    end = _record(lines[-1], "END", ("records", "capabilities", "nonce"))
    if end["records"] != "17" or end["capabilities"] != "13":
        raise M32CapabilityFailure("record/capability 분모 불일치")
    for fields in (begin, identity_fields, feature_fields, resource_fields, end):
        if fields["nonce"] != expected_nonce:
            raise M32CapabilityFailure("stale/wrong nonce")
    if begin["controller"] != "product_sdc" or identity_fields["controller"] != "product_sdc":
        raise M32CapabilityFailure("wrong controller")
    if begin["profile"] != expected_profile or identity_fields["profile"] != expected_profile:
        raise M32CapabilityFailure("wrong resource profile")

    actual_identity = ExpectedIdentity(
        *(identity_fields[key] for key in ("core", "board", "ncs", "zephyr"))
    )
    if actual_identity != expected_identity:
        raise M32CapabilityFailure("revision mismatch")

    max_page = _integer(feature_fields["max_page"], "max_page")
    octets = _integer(feature_fields["octets"], "octets", 1, 248)
    expected_octets = 16 if expected_profile == "ble_extended" else 8
    if octets != expected_octets or len(feature_fields["features"]) != octets * 2 or (
        re.fullmatch(r"[0-9a-f]+", feature_fields["features"], re.ASCII) is None
    ):
        raise M32CapabilityFailure("LE feature 길이·형식 오류")
    features = bytes.fromhex(feature_fields["features"])
    if expected_profile == "ble_baseline" and max_page != 0:
        raise M32CapabilityFailure("baseline feature page 경계 불일치")
    if expected_profile == "ble_extended" and (
        max_page < 1 or not _bit(features, 63)
    ):
        raise M32CapabilityFailure("extended feature page 경계 불일치")

    resources = {
        name: _integer(resource_fields[name], name, 0, 1024) for name in resource_names
    }
    if resources != PROFILE_RESOURCES[expected_profile]:
        raise M32CapabilityFailure("compile-time 자원 프로필 불일치")

    controller_bits = {}
    host_config = {}
    for offset, (identifier, position) in enumerate(CAPABILITY_BITS, 5):
        fields = _record(lines[offset], "CAP", ("nonce", "id", "controller_bit", "host_config"))
        if fields["nonce"] != expected_nonce or fields["id"] != identifier:
            raise M32CapabilityFailure("capability 순서·role·nonce 불일치")
        if fields["controller_bit"] not in {"0", "1"} or fields["host_config"] not in {"0", "1"}:
            raise M32CapabilityFailure("알 수 없는 controller/Host 상태")
        bit = fields["controller_bit"] == "1"
        if bit != _bit(features, position):
            raise M32CapabilityFailure("CAP bit와 raw HCI byte 불일치")
        controller_bits[identifier] = bit
        host_config[identifier] = fields["host_config"] == "1"

    expected_host_config = {
        identifier: expected_profile == "ble_extended" or identifier == "channel_classification"
        for identifier, _position in CAPABILITY_BITS
    }
    if host_config != expected_host_config:
        raise M32CapabilityFailure("Host Kconfig 프로필 불일치")
    return CapabilityResult(expected_nonce, actual_identity, expected_profile, max_page,
                            features, resources, controller_bits, host_config)


def validate_evidence_envelope(envelope: dict, expected_hex_sha256: str,
                               expected_identity: ExpectedIdentity,
                               expected_profile: str) -> CapabilityResult:
    """! @brief image hash·role·revision·프로필과 transcript를 하나의 attempt로 묶습니다. """
    if IMAGE_PATTERN.fullmatch(expected_hex_sha256) is None:
        raise M32CapabilityFailure("expected image SHA-256 형식 오류")
    if envelope.get("hex_sha256") != expected_hex_sha256:
        raise M32CapabilityFailure("image hash mismatch")
    if envelope.get("role") != "capability_probe":
        raise M32CapabilityFailure("wrong board role")
    transcript = envelope.get("transcript")
    nonce = envelope.get("nonce")
    if not isinstance(transcript, bytes) or not isinstance(nonce, str):
        raise M32CapabilityFailure("missing transcript/nonce")
    return parse_transcript(transcript, nonce, expected_identity, expected_profile)
