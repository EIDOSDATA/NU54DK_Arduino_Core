"""! @brief M29-W02 fixed UART protocol parser의 fail-closed 동작을 검증합니다. """

from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import BlePairHilFailure, RoleEndpoint  # noqa: E402
from m29_ble_long import execute_long_pair, parse_role_transcript  # noqa: E402


NONCE = "00112233445566778899aabbccddeeff"
REVISION = "0123456789abcdef0123456789abcdef01234567"
SUFFIX = f"|nonce={NONCE}|core={REVISION}"


def transcript(role: str) -> bytes:
    """! @brief role별 정상 protocol transcript를 구성합니다. """

    common = [
        f"M29W02|1|READY|role={role}|core={REVISION}",
        f"M29W02|1|BEGIN|role={role}{SUFFIX}",
    ]
    if role == "peripheral":
        common += [
            f"M29W02|1|ADVERTISE|role=peripheral|status=pass{SUFFIX}",
            f"M29W02|1|LINK|role=peripheral|mtu=247{SUFFIX}",
            f"M29W02|1|RESULT|role=peripheral|peer_disconnect=pass"
            f"|callback_context=pass{SUFFIX}",
            f"M29W02|1|END|role=peripheral|status=pass{SUFFIX}",
        ]
    else:
        common += [
            f"M29W02|1|SCAN|role=central|status=pass{SUFFIX}",
            f"M29W02|1|LINK|role=central|mtu=247{SUFFIX}",
            f"M29W02|1|RESULT|role=central|reads=100|bytes=512|corrupt=0"
            f"|stale=0|callback_context=pass{SUFFIX}",
            f"M29W02|1|END|role=central|status=pass{SUFFIX}",
        ]
    return ("\r\n".join(common) + "\r\n").encode("ascii")


class M29BleLongParserTests(unittest.TestCase):
    """! @brief strict identity·순서·정량 parser의 양성·음성 case입니다. """

    def assert_rejected(self, raw: bytes, role: str = "central") -> None:
        """! @brief 변형 transcript가 반드시 거부되는지 확인합니다. """

        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(raw, NONCE, REVISION, role)

    def test_accepts_exact_two_role_protocol(self):
        central = parse_role_transcript(transcript("central"), NONCE, REVISION, "central")
        peripheral = parse_role_transcript(
            transcript("peripheral"), NONCE, REVISION, "peripheral"
        )
        self.assertEqual((central.mtu, central.reads, central.payload_bytes), (247, 100, 512))
        self.assertEqual(peripheral.role, "peripheral")

    def test_rejects_noise(self):
        self.assert_rejected(b"noise\r\n" + transcript("central"))

    def test_rejects_non_ascii_noise(self):
        self.assert_rejected(b"\xff\r\n" + transcript("central"))

    def test_rejects_missing_record(self):
        lines = transcript("central").splitlines()
        self.assert_rejected(b"\n".join(lines[:3] + lines[4:]) + b"\n")

    def test_rejects_duplicate_record(self):
        lines = transcript("central").splitlines()
        self.assert_rejected(b"\n".join(lines[:2] + [lines[1]] + lines[2:]) + b"\n")

    def test_rejects_reordered_record(self):
        lines = transcript("central").splitlines()
        lines[2], lines[3] = lines[3], lines[2]
        self.assert_rejected(b"\n".join(lines) + b"\n")

    def test_rejects_stale_nonce(self):
        self.assert_rejected(transcript("central").replace(NONCE.encode(), b"f" * 32))

    def test_rejects_wrong_revision(self):
        self.assert_rejected(transcript("central").replace(REVISION.encode(), b"f" * 40))

    def test_rejects_wrong_quantitative_result(self):
        self.assert_rejected(transcript("central").replace(b"reads=100", b"reads=99"))

    def test_rejects_target_fail(self):
        raw = transcript("central").replace(
            b"M29W02|1|RESULT|role=central",
            b"M29W02|1|FAIL|role=central|stage=read",
        )
        self.assert_rejected(raw)

    def test_rejects_wrong_role_and_invalid_revision_argument(self):
        self.assert_rejected(transcript("peripheral"), "central")
        with self.assertRaises(BlePairHilFailure):
            parse_role_transcript(transcript("central"), NONCE, "bad", "central")

    def test_pyocd_programs_both_roles_before_clean_software_reset(self):
        """! @brief program 중 UART noise를 버리고 두 role을 제어된 순서로 시작합니다. """

        operations = []
        ports = {}

        class FakePort:
            """! @brief reset 경계와 protocol 응답을 재현하는 직렬 포트입니다. """

            def __init__(self, role: str) -> None:
                self.role = role
                self.buffer = bytearray()

            def __enter__(self):
                return self

            def __exit__(self, _type, _value, _traceback) -> None:
                return None

            @property
            def in_waiting(self) -> int:
                return len(self.buffer)

            def reset_input_buffer(self) -> None:
                self.buffer.clear()

            def read(self, size: int) -> bytes:
                data = bytes(self.buffer[:size])
                del self.buffer[:size]
                return data

            def write(self, data: bytes) -> int:
                suffix = f"|nonce={NONCE}|core={REVISION}\r\n".encode("ascii")
                if self.role == "peripheral":
                    records = (
                        b"M29W02|1|BEGIN|role=peripheral" + suffix,
                        b"M29W02|1|ADVERTISE|role=peripheral|status=pass" + suffix,
                        b"M29W02|1|LINK|role=peripheral|mtu=247" + suffix,
                        b"M29W02|1|RESULT|role=peripheral|peer_disconnect=pass"
                        b"|callback_context=pass" + suffix,
                        b"M29W02|1|END|role=peripheral|status=pass" + suffix,
                    )
                else:
                    records = (
                        b"M29W02|1|BEGIN|role=central" + suffix,
                        b"M29W02|1|SCAN|role=central|status=pass" + suffix,
                        b"M29W02|1|LINK|role=central|mtu=247" + suffix,
                        b"M29W02|1|RESULT|role=central|reads=100|bytes=512"
                        b"|corrupt=0|stale=0|callback_context=pass" + suffix,
                        b"M29W02|1|END|role=central|status=pass" + suffix,
                    )
                self.buffer.extend(b"".join(records))
                return len(data)

            def flush(self) -> None:
                return None

        class FakeSerialModule:
            """! @brief 역할별 FakePort를 pyserial과 같은 형식으로 제공합니다. """

            EIGHTBITS = 8
            PARITY_NONE = "N"
            STOPBITS_ONE = 1

            @staticmethod
            def Serial(*, port, **_kwargs):
                role = "peripheral" if port == "COM1" else "central"
                ports[role] = FakePort(role)
                return ports[role]

        def program(role, _digest, _image, _timeout, *, defer_reset=False):
            self.assertTrue(defer_reset)
            operations.append(f"program:{role}")
            ports[role].buffer.extend(b"***** HARD FAULT *****\r\n")
            return "pyocd-sector-no-reset", "4096"

        def reset(role, _digest, _timeout):
            operations.append(f"reset:{role}")
            ports[role].buffer.extend(
                f"M29W02|1|READY|role={role}|core={REVISION}\r\n".encode("ascii")
            )
            return "pyocd-v2-sw-reset"

        with mock.patch("m29_ble_long.flash_image_pyocd_sha256", side_effect=program), \
                mock.patch("m29_ble_long.reset_target_pyocd_sha256", side_effect=reset):
            result = execute_long_pair(
                serial_module=FakeSerialModule,
                peripheral_endpoint=RoleEndpoint("peripheral", mock.Mock(), "COM1"),
                central_endpoint=RoleEndpoint("central", mock.Mock(), "COM2"),
                peripheral_image=Path("peripheral.hex"),
                central_image=Path("central.hex"),
                nonce=NONCE,
                core_revision=REVISION,
                baud_rate=115200,
                flash_timeout=120.0,
                result_timeout=30.0,
                flash_backend="pyocd-sector",
            )

        self.assertEqual(
            operations,
            [
                "program:peripheral",
                "program:central",
                "reset:peripheral",
                "reset:central",
            ],
        )
        self.assertEqual(result.peripheral.flash_sequence, "pyocd-sector-sw-reset")
        self.assertEqual(result.central.flash_sequence, "pyocd-sector-sw-reset")
        self.assertNotIn(b"HARD FAULT", result.peripheral.transcript)
        self.assertNotIn(b"HARD FAULT", result.central.transcript)


if __name__ == "__main__":
    unittest.main(verbosity=2)
