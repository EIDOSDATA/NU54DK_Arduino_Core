#!/usr/bin/env python3
"""! @brief M29 Windows GATT 관측 parser의 fail-closed 경계를 검증합니다. """

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from m29_ble_windows_gatt_protocol import (  # noqa: E402
    CHARACTERISTIC_UUID,
    PEER_NAME,
    SERVICE_UUID,
    WindowsGattObservation,
    WindowsGattProtocolFailure,
    validate_windows_gatt_observation,
)


NONCE = "00112233445566778899aabbccddeeff"


def valid_observation() -> WindowsGattObservation:
    """! @brief 모든 고정값이 맞는 Windows 관측값을 반환합니다. """

    return WindowsGattObservation(
        backend="WinRT",
        platform="Windows",
        peer_name=PEER_NAME,
        peer_address="AA:BB:CC:DD:EE:FF",
        advertised_service_uuids=(SERVICE_UUID,),
        discovered_service_uuid=SERVICE_UUID,
        characteristic_uuid=CHARACTERISTIC_UUID,
        characteristic_properties=(
            "read",
            "write",
            "write-without-response",
            "notify",
            "indicate",
        ),
        read_value=bytes.fromhex(NONCE),
        write_response_value=b"WR",
        write_command_value=b"WC",
        notification_values=(b"NTF1", b"NTF2"),
        indication_values=(b"IND1",),
        connection_rounds=2,
        disconnect_rounds=2,
    )


class M29BleWindowsGattProtocolTests(unittest.TestCase):
    """! @brief 정상 결과와 peer·GATT·payload·round 위반 거부를 검사합니다. """

    def assert_rejected(self, **changes: object) -> None:
        """! @brief 일부 field를 바꾼 관측값이 거부되는지 검사합니다. """

        with self.assertRaises(WindowsGattProtocolFailure):
            validate_windows_gatt_observation(
                replace(valid_observation(), **changes), NONCE
            )

    def test_accepts_exact_windows_gatt_result(self) -> None:
        validate_windows_gatt_observation(valid_observation(), NONCE)

    def test_rejects_non_windows_backend(self) -> None:
        self.assert_rejected(backend="BlueZ")

    def test_rejects_wrong_peer_name(self) -> None:
        self.assert_rejected(peer_name="NU54-OTHER")

    def test_rejects_missing_advertised_service(self) -> None:
        self.assert_rejected(advertised_service_uuids=())

    def test_rejects_wrong_characteristic(self) -> None:
        self.assert_rejected(characteristic_uuid=SERVICE_UUID)

    def test_rejects_missing_indicate_property(self) -> None:
        self.assert_rejected(
            characteristic_properties=(
                "read",
                "write",
                "write-without-response",
                "notify",
            )
        )

    def test_rejects_stale_nonce_read(self) -> None:
        self.assert_rejected(read_value=b"\xff" * 16)

    def test_rejects_wrong_write_payload(self) -> None:
        self.assert_rejected(write_command_value=b"WR")

    def test_rejects_reordered_notifications(self) -> None:
        self.assert_rejected(notification_values=(b"NTF2", b"NTF1"))

    def test_rejects_missing_indication(self) -> None:
        self.assert_rejected(indication_values=())

    def test_rejects_short_reconnect_count(self) -> None:
        self.assert_rejected(connection_rounds=1, disconnect_rounds=1)

    def test_rejects_bad_nonce_format(self) -> None:
        with self.assertRaises(WindowsGattProtocolFailure):
            validate_windows_gatt_observation(valid_observation(), "A" * 32)


if __name__ == "__main__":
    unittest.main()
