#!/usr/bin/env python3
"""! @brief M29 Windows GATT 상호운용 관측값을 fail-closed로 검증합니다. """

from __future__ import annotations

from dataclasses import dataclass
import re


PEER_NAME = "NU54-GATT"
SERVICE_UUID = "8e7e2001-7d8c-4c1a-9d2d-8b6519f77410"
CHARACTERISTIC_UUID = "8e7e2002-7d8c-4c1a-9d2d-8b6519f77410"
REQUIRED_PROPERTIES = frozenset(
    {"read", "write", "write-without-response", "notify", "indicate"}
)
NONCE_PATTERN = re.compile(r"[0-9a-f]{32}")


class WindowsGattProtocolFailure(RuntimeError):
    """! @brief Windows peer의 identity·service·operation 결과가 다른 경우입니다. """


@dataclass(frozen=True)
class WindowsGattObservation:
    """! @brief WinRT central이 직접 관측한 GATT 상호운용 결과입니다. """

    backend: str
    platform: str
    peer_name: str
    peer_address: str
    advertised_service_uuids: tuple[str, ...]
    discovered_service_uuid: str
    characteristic_uuid: str
    characteristic_properties: tuple[str, ...]
    read_value: bytes
    write_response_value: bytes
    write_command_value: bytes
    notification_values: tuple[bytes, ...]
    indication_values: tuple[bytes, ...]
    connection_rounds: int
    disconnect_rounds: int


def validate_windows_gatt_observation(
    observation: WindowsGattObservation, nonce: str
) -> None:
    """! @brief 고정 service와 두 연결의 read/write/notify/indicate 결과를 검사합니다. """

    if NONCE_PATTERN.fullmatch(nonce) is None:
        raise WindowsGattProtocolFailure("nonce는 32자리 lowercase hex여야 합니다.")
    if observation.backend != "WinRT" or observation.platform != "Windows":
        raise WindowsGattProtocolFailure("Windows WinRT backend 결과만 허용합니다.")
    if observation.peer_name != PEER_NAME or observation.peer_address == "":
        raise WindowsGattProtocolFailure("광고 peer identity가 일치하지 않습니다.")
    advertised = {value.lower() for value in observation.advertised_service_uuids}
    if SERVICE_UUID not in advertised:
        raise WindowsGattProtocolFailure("광고 service UUID가 누락되었습니다.")
    if observation.discovered_service_uuid.lower() != SERVICE_UUID:
        raise WindowsGattProtocolFailure("발견한 service UUID가 일치하지 않습니다.")
    if observation.characteristic_uuid.lower() != CHARACTERISTIC_UUID:
        raise WindowsGattProtocolFailure("발견한 characteristic UUID가 일치하지 않습니다.")
    properties = {value.lower() for value in observation.characteristic_properties}
    if not REQUIRED_PROPERTIES.issubset(properties):
        raise WindowsGattProtocolFailure("필수 GATT property가 누락되었습니다.")
    if observation.read_value != bytes.fromhex(nonce):
        raise WindowsGattProtocolFailure("128-bit nonce read 값이 일치하지 않습니다.")
    if observation.write_response_value != b"WR":
        raise WindowsGattProtocolFailure("write with response 값이 일치하지 않습니다.")
    if observation.write_command_value != b"WC":
        raise WindowsGattProtocolFailure("write without response 값이 일치하지 않습니다.")
    if observation.notification_values != (b"NTF1", b"NTF2"):
        raise WindowsGattProtocolFailure("두 연결의 notification 순서가 일치하지 않습니다.")
    if observation.indication_values != (b"IND1",):
        raise WindowsGattProtocolFailure("첫 연결의 indication 값이 일치하지 않습니다.")
    if observation.connection_rounds != 2 or observation.disconnect_rounds != 2:
        raise WindowsGattProtocolFailure("연결·해제 round가 각각 2회가 아닙니다.")
