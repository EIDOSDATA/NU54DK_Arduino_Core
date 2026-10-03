#!/usr/bin/env python3
"""! @brief M33-W02 Beacon 코덱의 byte 계약과 음성 경계를 Host에서 검증합니다. """

from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable


REPOSITORY = Path(__file__).resolve().parents[2]


class M33BeaconCodecTests(unittest.TestCase):
    """! @brief iBeacon, Eddystone UID, BTHome v2 코덱을 실행 검증합니다. """

    def test_known_bytes_round_trip_and_negative_boundaries(self) -> None:
        """! @brief production 코덱을 링크해 알려진 byte와 잘못된 입력을 검사합니다. """

        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-m33-w02-") as folder:
            binary = Path(folder) / "m33-w02-beacon.exe"
            command = [
                *compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(REPOSITORY / "libraries" / "NUCODE_BLE" / "src"),
                str(
                    REPOSITORY
                    / "libraries"
                    / "NUCODE_BLE"
                    / "src"
                    / "NUCODE_BLE_Beacon.cpp"
                ),
                str(REPOSITORY / "tests" / "host" / "m33_beacon_codec_main.cpp"),
                "-o",
                str(binary),
            ]
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(
                result.returncode, 0, result.stderr.decode(errors="replace")
            )
            for scenario in ("ibeacon", "eddystone", "bthome", "malformed"):
                with self.subTest(scenario=scenario):
                    result = run_executable(
                        [str(binary), scenario], capture_output=True, timeout=10
                    )
                    self.assertEqual(
                        result.returncode,
                        0,
                        f"{scenario}: return={result.returncode}; "
                        f"stderr={result.stderr.decode(errors='replace')}",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
