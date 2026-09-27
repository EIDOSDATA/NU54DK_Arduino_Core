"""! @brief CSIP Member backend의 thread interleaving을 실제 C++로 실행합니다. """

from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable


ROOT = Path(__file__).resolve().parents[2]


class CsipMemberLifecycleTests(unittest.TestCase):
    """! @brief unregister와 public native 호출의 수명 경계를 고정합니다. """

    def test_member_lifecycle_interleaving(self) -> None:
        """! @brief in-flight drain, quarantine, rank-only 거부와 세대 승인을 검증합니다. """

        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-csip-member-") as folder:
            binary = Path(folder) / "csip-member.exe"
            command = [
                *compiler,
                "-std=c++17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wno-missing-field-initializers",
                "-pthread",
                "-DCONFIG_BT_CSIP_SET_MEMBER=1",
                "-DCONFIG_BT_CSIP_SET_COORDINATOR=1",
            ]
            for path in (
                "tests/host/ble_stubs",
                "tests/host/arduino_stubs",
                "cores/arduino",
                "third_party/ArduinoCore-API",
                "libraries/NUCODE_BLE/src",
                "libraries/NUCODE_BLE_Audio/src",
            ):
                command += ["-I", str(ROOT / path)]
            command += [
                str(ROOT / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_Csip.cpp"),
                str(ROOT / "tests/host/m31_csip_member_lifecycle_main.cpp"),
                "-o",
                str(binary),
            ]
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(
                result.returncode, 0, result.stderr.decode(errors="replace")
            )
            result = run_executable([str(binary)], capture_output=True, timeout=10)
            self.assertEqual(
                result.returncode, 0, result.stderr.decode(errors="replace")
            )
            result = run_executable(
                [str(binary), "--non-lockable"], capture_output=True, timeout=10
            )
            self.assertEqual(
                result.returncode, 0, result.stderr.decode(errors="replace")
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
