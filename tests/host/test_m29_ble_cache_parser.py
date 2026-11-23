#!/usr/bin/env python3
"""! @brief M29-W05 robust GATT cache HIL parser의 fail-closed 경계를 검증합니다. """

from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import BlePairHilFailure  # noqa: E402
import m29_ble_cache as runner  # noqa: E402
from m29_ble_cache import parse_role_transcript  # noqa: E402


NONCE = "00112233445566778899aabbccddeeff"
REVISION = "1" * 40
SUFFIX = f"|nonce={NONCE}|core={REVISION}"


def lines(role: str) -> list[str]:
    """! @brief role별 정상 W05 고정 record를 만듭니다. """

    records = [
        f"M29W05|1|READY|role={role}|stage=1|core={REVISION}",
        f"M29W05|1|BEGIN|role={role}{SUFFIX}",
    ]
    if role == "peripheral":
        records.extend(
            (
                f"M29W05|1|ADVERTISE|role=peripheral|stage=1{SUFFIX}",
                f"M29W05|1|SERVICE_CHANGED|role=peripheral|status=requested{SUFFIX}",
                f"M29W05|1|MIGRATE_REBOOT|role=peripheral|stage=2{SUFFIX}",
                f"M29W05|1|RESUME_READY|role=peripheral{SUFFIX}",
                f"M29W05|1|REBOOT|role=peripheral|stage=2{SUFFIX}",
                f"M29W05|1|ADVERTISE|role=peripheral|stage=2{SUFFIX}",
                "M29W05|1|RESULT|role=peripheral|stage=2"
                "|service_changed_requests=1|migration_requests=1"
                f"|callback_context=pass{SUFFIX}",
            )
        )
    else:
        records.extend(
            (
                f"M29W05|1|SCAN|role=central|stage=1{SUFFIX}",
                f"M29W05|1|PRIME|role=central|cache_saved=1|handle=31{SUFFIX}",
                "M29W05|1|SERVICE_CHANGED|role=central|events=1"
                f"|invalidated=1{SUFFIX}",
                "M29W05|1|RESTORES|role=central|count=20"
                f"|cache_restored=20|stale=0{SUFFIX}",
                "M29W05|1|MIGRATION|role=central|old_handle=31"
                f"|new_handle=35|invalidated=2{SUFFIX}",
                f"M29W05|1|CORRUPT_REBOOT|role=central|status=requested{SUFFIX}",
                f"M29W05|1|RESUME_READY|role=central{SUFFIX}",
                f"M29W05|1|REBOOT|role=central|phase=corrupt{SUFFIX}",
                f"M29W05|1|SCAN|role=central|stage=2{SUFFIX}",
                f"M29W05|1|CORRUPT|role=central|rejected=1|restored=0{SUFFIX}",
                "M29W05|1|RESULT|role=central|bonded=1|reconnects=20"
                "|hash_reads=24|cache_saved=4|cache_restored=20|invalidated=2"
                "|service_changed=1|corrupt_rejected=1|stale=0"
                f"|callback_context=pass{SUFFIX}",
            )
        )
    records.append(f"M29W05|1|END|role={role}|status=pass{SUFFIX}")
    return records


def transcript(role: str) -> bytes:
    """! @brief 정상 record를 CRLF transcript로 직렬화합니다. """

    return ("\r\n".join(lines(role)) + "\r\n").encode("ascii")


class M29BleCacheParserTests(unittest.TestCase):
    """! @brief 정상 수락과 identity/order/정량 위반 거부를 검사합니다. """

    def assert_rejected(self, raw: bytes, role: str = "central") -> None:
        """! @brief 지정 transcript가 예외로 거부되는지 검사합니다. """

        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(raw, NONCE, REVISION, role)

    def test_accepts_exact_roles(self) -> None:
        central = parse_role_transcript(transcript("central"), NONCE, REVISION, "central")
        peripheral = parse_role_transcript(
            transcript("peripheral"), NONCE, REVISION, "peripheral"
        )
        self.assertEqual(
            (
                central.reconnects,
                central.hash_reads,
                central.cache_restored,
                central.corrupt_rejected,
            ),
            (20, 24, 20, 1),
        )
        self.assertEqual((peripheral.stage, peripheral.service_changed), (2, 1))

    def test_rejects_missing_record(self) -> None:
        records = lines("central")
        self.assert_rejected(("\n".join(records[:5] + records[6:]) + "\n").encode())

    def test_rejects_duplicate_record(self) -> None:
        records = lines("central")
        self.assert_rejected(("\n".join(records[:5] + records[4:]) + "\n").encode())

    def test_rejects_reordered_record(self) -> None:
        records = lines("central")
        records[4], records[5] = records[5], records[4]
        self.assert_rejected(("\n".join(records) + "\n").encode())

    def test_rejects_stale_nonce(self) -> None:
        self.assert_rejected(transcript("central").replace(NONCE.encode(), b"f" * 32))

    def test_rejects_wrong_revision(self) -> None:
        self.assert_rejected(transcript("central").replace(REVISION.encode(), b"2" * 40))

    def test_rejects_ascii_noise(self) -> None:
        self.assert_rejected(b"boot noise\n" + transcript("central"))

    def test_rejects_non_ascii_noise(self) -> None:
        self.assert_rejected(b"\xff\n" + transcript("central"))

    def test_rejects_target_failure(self) -> None:
        self.assert_rejected(
            transcript("central").replace(
                b"M29W05|1|RESULT|role=central",
                b"M29W05|1|FAIL|role=central|stage=restore",
            )
        )

    def test_rejects_wrong_quantitative_value(self) -> None:
        self.assert_rejected(
            transcript("central").replace(b"cache_restored=20", b"cache_restored=19")
        )

    def test_rejects_unchanged_migration_handle(self) -> None:
        self.assert_rejected(
            transcript("central").replace(b"new_handle=35", b"new_handle=31")
        )

    def test_rejects_prime_migration_handle_mismatch(self) -> None:
        self.assert_rejected(
            transcript("central").replace(b"old_handle=31", b"old_handle=30")
        )

    def test_rejects_wrong_role(self) -> None:
        self.assert_rejected(transcript("central"), "peripheral")

    def test_rejects_invalid_revision_argument(self) -> None:
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript("central"), NONCE, "bad", "central")

    def test_reboot_framing_is_bounded_and_only_inside_handshake(self) -> None:
        """! @brief 두 role reset 경계만 허용하고 다른 위치·내용·한도는 거부합니다. """

        for role in ("central", "peripheral"):
            ready = runner._resume_ready(role, NONCE, REVISION)
            clean = transcript(role)
            for noise in (b"\xff\r\n", b"\x00\xff" * 16 + b"\r\n"):
                raw = clean.replace(ready, noise + ready)
                parse_role_transcript(raw, NONCE, REVISION, role)
                self.assertIn(noise, raw)
                self.assert_rejected(noise + clean, role)
            for noise in (b"\xff" * 33 + b"\n", b"boot error\n", b"\x80\n", b"\xff"):
                self.assert_rejected(clean.replace(ready, noise + ready), role)
            self.assert_rejected(clean.replace(ready, ready.replace(NONCE.encode(), b"f" * 32)), role)
            self.assert_rejected(clean.replace(ready + b"\r\n", b""), role)
            self.assert_rejected(clean.replace(ready, ready + b"\r\n" + ready), role)
            reboot = f"M29W05|1|REBOOT|role={role}".encode()
            self.assert_rejected(clean.replace(reboot, b"\xff\n" + reboot), role)

    def test_live_collector_preserves_framing_and_requests_exact_resume(self) -> None:
        """! @brief 실제 collector가 raw를 바꾸지 않고 양 role에 exact 재개를 보냅니다. """

        self.enterContext(patch("builtins.print"))

        class Port:
            def __init__(self, raw: bytes) -> None:
                self.raw = raw
                self.writes = []

            @property
            def in_waiting(self) -> int:
                return len(self.raw)

            def read(self, count: int) -> bytes:
                value, self.raw = self.raw[:count], self.raw[count:]
                return value

            def write(self, data: bytes) -> int:
                self.writes.append(data)
                return len(data)

            def flush(self) -> None:
                pass

        for role in ("central", "peripheral"):
            ready = runner._resume_ready(role, NONCE, REVISION)
            raw = transcript(role).replace(ready, b"\xff\x00\r\n" + ready)
            port, capture = Port(raw), bytearray()
            stop = threading.Event()
            with patch.object(stop, "wait", return_value=False):
                runner._collect_end(port, role, NONCE, REVISION, bytearray(), capture,
                                    time.monotonic() + 5, stop)
            self.assertEqual(bytes(capture), raw)
            self.assertEqual(port.writes, [b"M29W05|1|RESUME?\r\n",
                                          f"M29W05|1|RESUME{SUFFIX}\r\n".encode()])
            parse_role_transcript(bytes(capture), NONCE, REVISION, role)
            for broken in (raw.replace(ready, b"bad"), raw.replace(b"\xff\x00", b"\xff" * 33),
                           raw.replace(ready, ready.replace(NONCE.encode(), b"f" * 32))):
                bad_port, failed_capture = Port(broken), bytearray()
                failed_stop = threading.Event()
                with patch.object(failed_stop, "wait", return_value=False):
                    with self.assertRaises(BlePairHilFailure):
                        runner._collect_end(bad_port, role, NONCE, REVISION, bytearray(),
                                            failed_capture, time.monotonic() + 5, failed_stop)
                self.assertEqual(bytes(failed_capture), broken)
                self.assertEqual(len(bad_port.writes), 1)
                self.assertTrue(failed_stop.is_set())
            timeout_port = Port(runner._reboot_marker(role, NONCE, REVISION) + b"\n")
            timeout_capture = bytearray()
            timeout_stop = threading.Event()
            with patch.object(timeout_stop, "wait", return_value=False):
                with self.assertRaises(TimeoutError):
                    runner._collect_end(timeout_port, role, NONCE, REVISION, bytearray(),
                                        timeout_capture, time.monotonic() + 0.02, timeout_stop)
            self.assertTrue(timeout_stop.is_set())
            self.assertEqual(len(timeout_port.writes), 1)


if __name__ == "__main__":
    unittest.main()
