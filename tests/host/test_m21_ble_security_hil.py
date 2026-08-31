#!/usr/bin/env python3
"""! @brief M21 BLE security 두 보드 HIL parser와 증적을 회귀 검증합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


MODULE_PATH = Path(__file__).parents[1] / "hil" / "nu54dk" / "m21_ble_security.py"
SPEC = importlib.util.spec_from_file_location("m21_ble_security", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"M21 HIL module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

NONCE = "0123456789abcdef0123456789abcdef"
STALE = "fedcba9876543210fedcba9876543210"


## @brief central의 네 phase와 표준 profile exact token을 만듭니다.
def central_transcript(nonce: str = NONCE) -> bytes:
    suffix = f":nonce={nonce}"
    lines = [
        "NUCODE_M21_READY:role=central:bond_count=0",
        f"NUCODE_M21_CENTRAL:CLEAR:REQUESTED{suffix}",
        f"NUCODE_M21_REBOOTING:role=central{suffix}",
        "NUCODE_M21_READY:role=central:bond_count=0",
        "NUCODE_M21_CENTRAL:SCAN:PASS:phase=first:"
        f"rf_nonce_binding_bits=128{suffix}",
        f"NUCODE_M21_EVENT:CONNECTED:role=central:phase=first{suffix}",
        f"NUCODE_M21_CENTRAL:SECURE_GATT:DENIED{suffix}",
        f"NUCODE_M21_CENTRAL:BAS:READ:PASS:value=73{suffix}",
        f"NUCODE_M21_CENTRAL:BAS:NOTIFY:PASS:value=72{suffix}",
        "NUCODE_M21_CENTRAL:DIS:PASS:manufacturer=NUCODE:"
        f"model=NU54DK-M21:serial=M21-HIL{suffix}",
        "NUCODE_M21_CENTRAL:HID:REPORT:PASS:bytes=8:"
        f"down=04:release=00{suffix}",
        "NUCODE_M21_CENTRAL:PHASE:PASS:phase=first:"
        f"pairing_events=1:bond_count=1:bond_state=persistence_pending{suffix}",
        f"NUCODE_M21_REBOOTING:role=central{suffix}",
        "NUCODE_M21_READY:role=central:bond_count=1",
        "NUCODE_M21_CENTRAL:SCAN:PASS:phase=restore:"
        f"rf_nonce_binding_bits=128{suffix}",
        f"NUCODE_M21_EVENT:CONNECTED:role=central:phase=restore{suffix}",
        "NUCODE_M21_CENTRAL:PHASE:PASS:phase=restore:"
        f"pairing_events=0:bond_count=1:bond_state=verified{suffix}",
        f"NUCODE_M21_CENTRAL:ERASE:REQUESTED{suffix}",
        f"NUCODE_M21_REBOOTING:role=central{suffix}",
        "NUCODE_M21_READY:role=central:bond_count=0",
        "NUCODE_M21_CENTRAL:SCAN:PASS:phase=erased_probe:"
        f"rf_nonce_binding_bits=128{suffix}",
        f"NUCODE_M21_EVENT:CONNECTED:role=central:phase=erased_probe{suffix}",
        "NUCODE_M21_CENTRAL:OLD_KEY:RECONNECT:REJECTED:bond_count=0:"
        f"pairing_requested=1:security_failed=1{suffix}",
        "NUCODE_M21_CENTRAL:SCAN:PASS:phase=repair:"
        f"rf_nonce_binding_bits=128{suffix}",
        f"NUCODE_M21_EVENT:CONNECTED:role=central:phase=repair{suffix}",
        "NUCODE_M21_CENTRAL:PHASE:PASS:phase=repair:"
        f"pairing_events=1:bond_count=1:bond_state=persistence_pending{suffix}",
        "NUCODE_M21_CENTRAL:FINAL:PASS:pairing=PASS:bond_restore=PASS:"
        "erase_reboot=PASS:old_key_reconnect=REJECTED:repair=PASS:"
        "bas=PASS:dis=PASS:hid_protocol=PASS"
        f"{suffix}",
    ]
    return ("Zephyr boot\r\n" + "\r\n".join(lines) + "\r\n").encode("ascii")


## @brief peripheral의 네 phase와 profile 전송 exact token을 만듭니다.
def peripheral_transcript(nonce: str = NONCE) -> bytes:
    suffix = f":nonce={nonce}"
    lines = [
        "NUCODE_M21_READY:role=peripheral:bond_count=0",
        f"NUCODE_M21_PERIPHERAL:CLEAR:REQUESTED{suffix}",
        f"NUCODE_M21_REBOOTING:role=peripheral{suffix}",
        "NUCODE_M21_READY:role=peripheral:bond_count=0",
        "NUCODE_M21_PERIPHERAL:ADVERTISE:PASS:phase=first:"
        f"rf_nonce_binding_bits=128{suffix}",
        f"NUCODE_M21_EVENT:CONNECTED:role=peripheral:phase=first{suffix}",
        f"NUCODE_M21_PERIPHERAL:PROFILE:PASS:bas_notify=72:hid_bytes=8{suffix}",
        "NUCODE_M21_PERIPHERAL:PHASE:PASS:phase=first:"
        f"pairing_events=1:bond_count=1:bond_state=persistence_pending{suffix}",
        f"NUCODE_M21_REBOOTING:role=peripheral{suffix}",
        "NUCODE_M21_READY:role=peripheral:bond_count=1",
        "NUCODE_M21_PERIPHERAL:ADVERTISE:PASS:phase=restore:"
        f"rf_nonce_binding_bits=128{suffix}",
        f"NUCODE_M21_EVENT:CONNECTED:role=peripheral:phase=restore{suffix}",
        "NUCODE_M21_PERIPHERAL:PHASE:PASS:phase=restore:"
        f"pairing_events=0:bond_count=1:bond_state=verified{suffix}",
        f"NUCODE_M21_PERIPHERAL:ERASE:REQUESTED{suffix}",
        f"NUCODE_M21_REBOOTING:role=peripheral{suffix}",
        "NUCODE_M21_READY:role=peripheral:bond_count=0",
        "NUCODE_M21_PERIPHERAL:ADVERTISE:PASS:phase=erased_probe:"
        f"rf_nonce_binding_bits=128{suffix}",
        f"NUCODE_M21_EVENT:CONNECTED:role=peripheral:phase=erased_probe{suffix}",
        "NUCODE_M21_PERIPHERAL:OLD_KEY:RECONNECT:REJECTED:bond_count=0:"
        f"pairing_requested=1:security_failed=1{suffix}",
        "NUCODE_M21_PERIPHERAL:ADVERTISE:PASS:phase=repair:"
        f"rf_nonce_binding_bits=128{suffix}",
        f"NUCODE_M21_EVENT:CONNECTED:role=peripheral:phase=repair{suffix}",
        "NUCODE_M21_PERIPHERAL:PHASE:PASS:phase=repair:"
        f"pairing_events=1:bond_count=1:bond_state=persistence_pending{suffix}",
        "NUCODE_M21_PERIPHERAL:FINAL:PASS:pairing=PASS:bond_restore=PASS:"
        "erase_reboot=PASS:old_key_reconnect=REJECTED:repair=PASS:"
        "bas=PASS:dis=PASS:hid_protocol=PASS"
        f"{suffix}",
    ]
    return ("Zephyr boot\n" + "\n".join(lines) + "\n").encode("ascii")


## @brief 테스트용 물리 endpoint 표현을 만듭니다.
def endpoint(board_id: str, drive: str, port: str) -> object:
    volume = MODULE.DaplinkVolume(Path(drive), f"Unique ID: {board_id}\n")
    return MODULE.RoleEndpoint(board_id, volume, port)


class M21BleSecurityHilTests(unittest.TestCase):
    """! @brief nonce, 네 phase, 표준 profile와 manual 경계를 검증합니다. """

    def test_accepts_pair_restore_erase_repair_and_profiles(self) -> None:
        """! @brief exact 중앙·주변장치 transcript를 승인합니다. """

        central = MODULE.parse_role_transcript(central_transcript(), "central", NONCE)
        peripheral = MODULE.parse_role_transcript(
            peripheral_transcript(), "peripheral", NONCE
        )
        self.assertEqual(central.phases, ("first", "restore", "erased_probe", "repair"))
        self.assertEqual(central.pairing_events, (1, 0, 1))
        self.assertEqual(peripheral.bond_counts, (1, 1, 0, 1))
        self.assertEqual(
            central.bond_states,
            ("persistence_pending", "verified", "none", "persistence_pending"),
        )
        self.assertEqual(central.rf_nonce_binding_bits, 128)
        self.assertTrue(central.erase_reboot_verified)
        self.assertTrue(central.old_key_reconnect_rejected)

    def test_rejects_missing_encrypted_gatt_negative_or_hid(self) -> None:
        """! @brief 암호화 전 거부나 8-byte HID 검증 누락을 거부합니다. """

        missing_denial = central_transcript().replace(
            f"NUCODE_M21_CENTRAL:SECURE_GATT:DENIED:nonce={NONCE}\r\n".encode(),
            b"",
        )
        with self.assertRaisesRegex(MODULE.M21HilFailure, "누락"):
            MODULE.parse_role_transcript(missing_denial, "central", NONCE)

        missing_hid = central_transcript().replace(b"down=04:release=00", b"down=05:release=00")
        with self.assertRaisesRegex(MODULE.M21HilFailure, "누락"):
            MODULE.parse_role_transcript(missing_hid, "central", NONCE)

        missing_old_key = central_transcript().replace(
            (
                "NUCODE_M21_CENTRAL:OLD_KEY:RECONNECT:REJECTED:bond_count=0:"
                f"pairing_requested=1:security_failed=1:nonce={NONCE}\r\n"
            ).encode(),
            b"",
        )
        with self.assertRaisesRegex(MODULE.M21HilFailure, "old-key"):
            MODULE.parse_role_transcript(missing_old_key, "central", NONCE)

    def test_rejects_stale_nonce_target_fail_and_wrong_pairing_count(self) -> None:
        """! @brief stale 실행, target FAIL과 restore 재페어를 모두 거부합니다. """

        stale = central_transcript().replace(NONCE.encode(), STALE.encode(), 1)
        with self.assertRaisesRegex(MODULE.M21HilFailure, "stale"):
            MODULE.parse_role_transcript(stale, "central", NONCE)

        failed = peripheral_transcript() + b"NUCODE_M21_FAIL:role=peripheral:reason=x\n"
        with self.assertRaisesRegex(MODULE.M21HilFailure, "실패"):
            MODULE.parse_role_transcript(failed, "peripheral", NONCE)

        repaired_restore = central_transcript().replace(
            b"phase=restore:pairing_events=0", b"phase=restore:pairing_events=1"
        )
        with self.assertRaisesRegex(MODULE.M21HilFailure, "누락"):
            MODULE.parse_role_transcript(repaired_restore, "central", NONCE)

    def test_boot_ready_ignores_preflash_protocol_but_runtime_rejects_it(self) -> None:
        """! @brief flash 중 남은 이전 firmware token은 READY 전만 무시합니다. """

        class FakeSerial:
            """! @brief wait_token에 고정 UART byte열을 제공하는 최소 대역입니다. """

            def __init__(self, payload: bytes) -> None:
                self.payload = bytearray(payload)

            @property
            def in_waiting(self) -> int:
                return len(self.payload)

            def read(self, length: int) -> bytes:
                chunk = bytes(self.payload[:length])
                del self.payload[:length]
                return chunk

        stale = (
            f"NUCODE_M21_EVENT:DISCONNECTED:role=central:nonce={STALE}\r\n"
            "NUCODE_M21_FAIL:role=central:reason=old-image\r\n"
            "NUCODE_M21_READY:role=central:bond_count=0\r\n"
        ).encode("ascii")
        ready = MODULE.wait_token(
            FakeSerial(stale),
            "central",
            NONCE,
            bytearray(),
            bytearray(),
            MODULE.time.monotonic() + 1.0,
            lambda line: line == b"NUCODE_M21_READY:role=central:bond_count=0",
            enforce_protocol=False,
        )
        self.assertEqual(ready, b"NUCODE_M21_READY:role=central:bond_count=0")

        with self.assertRaisesRegex(MODULE.M21HilFailure, "stale"):
            MODULE.wait_token(
                FakeSerial(stale),
                "central",
                NONCE,
                bytearray(),
                bytearray(),
                MODULE.time.monotonic() + 1.0,
                lambda line: False,
            )

    def test_rejects_missing_or_short_rf_nonce_binding(self) -> None:
        """! @brief 128-bit RF peer binding 누락·축소를 모두 거부합니다. """

        missing = central_transcript().replace(
            (
                "NUCODE_M21_CENTRAL:SCAN:PASS:phase=restore:"
                f"rf_nonce_binding_bits=128:nonce={NONCE}\r\n"
            ).encode(),
            b"",
        )
        with self.assertRaisesRegex(MODULE.M21HilFailure, "누락"):
            MODULE.parse_role_transcript(missing, "central", NONCE)

        short = peripheral_transcript().replace(
            b"rf_nonce_binding_bits=128", b"rf_nonce_binding_bits=48", 1
        )
        with self.assertRaisesRegex(MODULE.M21HilFailure, "누락"):
            MODULE.parse_role_transcript(short, "peripheral", NONCE)

    def test_rejects_erase_without_post_reboot_zero_bond(self) -> None:
        """! @brief 제거 요청 직후 값을 영속 삭제 완료로 오판하지 않습니다. """

        transcript = central_transcript()
        erase = f"NUCODE_M21_CENTRAL:ERASE:REQUESTED:nonce={NONCE}\r\n".encode()
        tail = transcript.index(erase) + len(erase)
        ready = b"NUCODE_M21_READY:role=central:bond_count=0\r\n"
        position = transcript.index(ready, tail)
        without_reboot_proof = transcript[:position] + transcript[position + len(ready) :]
        with self.assertRaisesRegex(MODULE.M21HilFailure, "누락"):
            MODULE.parse_role_transcript(without_reboot_proof, "central", NONCE)

    def test_requires_distinct_boards_and_exact_nonce(self) -> None:
        """! @brief 같은 UID·MSD·UART와 잘못된 nonce를 차단합니다. """

        peripheral = endpoint("a" * 32, "P:/", "COM10")
        central = endpoint("b" * 32, "Q:/", "COM11")
        MODULE.validate_pair_identity(peripheral, central)
        with self.assertRaisesRegex(MODULE.M21HilFailure, "UID"):
            MODULE.validate_pair_identity(peripheral, endpoint("a" * 32, "Q:/", "COM11"))
        with self.assertRaisesRegex(MODULE.M21HilFailure, "UART"):
            MODULE.validate_pair_identity(peripheral, endpoint("b" * 32, "Q:/", "com10"))
        self.assertEqual(MODULE.build_nonce(NONCE), NONCE)
        for invalid in ("A" * 32, "a" * 31, "g" * 32):
            with self.assertRaisesRegex(MODULE.M21HilFailure, "nonce"):
                MODULE.build_nonce(invalid)

    def test_evidence_marks_only_protocol_hid_as_automatic(self) -> None:
        """! @brief OS 입력 확인은 자동 PASS와 분리해 pending으로 남깁니다. """

        peripheral_raw = peripheral_transcript()
        central_raw = central_transcript()
        execution = MODULE.PairExecution(
            MODULE.RoleExecution("1", "100", peripheral_raw),
            MODULE.RoleExecution("2", "200", central_raw),
        )
        with tempfile.TemporaryDirectory(prefix="nu54-m21-") as temporary:
            root = Path(temporary)
            peripheral_image = root / "peripheral.hex"
            central_image = root / "central.hex"
            peripheral_image.write_bytes(b":0100000001FE\n")
            central_image.write_bytes(b":0100000002FD\n")
            evidence = MODULE.build_evidence(
                core_revision="c" * 40,
                board_revision="d" * 40,
                nonce=NONCE,
                peripheral_endpoint=endpoint("a" * 32, "P:/", "COM10"),
                central_endpoint=endpoint("b" * 32, "Q:/", "COM11"),
                peripheral_image=peripheral_image,
                central_image=central_image,
                execution=execution,
                peripheral_result=MODULE.parse_role_transcript(
                    peripheral_raw, "peripheral", NONCE
                ),
                central_result=MODULE.parse_role_transcript(central_raw, "central", NONCE),
            )
        self.assertTrue(evidence["coverage"]["hid_report_protocol"])
        self.assertTrue(evidence["coverage"]["bond_delete_warm_reboot_zero"])
        self.assertTrue(evidence["coverage"]["old_key_reconnect_rejected"])
        self.assertEqual(evidence["rf_nonce_binding_bits"], 128)
        self.assertFalse(evidence["coverage"]["windows_or_smartphone_hid_input"])
        self.assertTrue(evidence["coverage"]["manual_os_hid_confirmation_pending"])


if __name__ == "__main__":
    unittest.main()
