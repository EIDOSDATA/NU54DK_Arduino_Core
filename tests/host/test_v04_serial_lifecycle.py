"""Run the production transaction state machine using bounded fake hardware."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SerialLifecycleTests(unittest.TestCase):
    def test_native_production_route_validator(self):
        compiler = shutil.which("g++")
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-v04-routes-") as folder:
            for console in (0, 1):
                binary = Path(folder) / f"routes-{console}.exe"
                result = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    f"-DTEST_UART_STATUS={console}", "-DCONFIG_SERIAL=1",
                    "-I", str(ROOT / "tests/host/serial_fabric_stubs"), "-I", str(ROOT / "cores/arduino"),
                    "-I", str(ROOT / "variants/nu54dk"), str(ROOT / "variants/nu54dk/serial_fabric_routes.cpp"),
                    str(ROOT / "tests/host/v04_serial_routes_main.cpp"), "-o", str(binary)], capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
                result = subprocess.run([str(binary)], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_native_production_lifecycle(self):
        compiler = shutil.which("g++")
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-v04-lifecycle-") as folder:
            binary = Path(folder) / "lifecycle.exe"
            result = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-DCONFIG_ZTEST=1",
                "-I", str(ROOT / "tests/host/serial_fabric_stubs"), "-I", str(ROOT / "cores/arduino"),
                "-I", str(ROOT / "variants/nu54dk"), str(ROOT / "cores/arduino/SerialFabric.cpp"),
                str(ROOT / "tests/host/v04_serial_lifecycle_main.cpp"), "-o", str(binary)], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            result = subprocess.run([str(binary)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


if __name__ == "__main__": unittest.main()
