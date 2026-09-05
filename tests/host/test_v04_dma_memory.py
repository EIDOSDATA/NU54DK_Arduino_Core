"""EasyDMA RAM 범위 검사와 production 적용 지점을 검증합니다."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DmaMemoryTests(unittest.TestCase):
    def test_native_full_range_and_alignment_boundaries(self):
        compiler = shutil.which("g++")
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-v04-dma-") as folder:
            binary = Path(folder) / "dma-memory.exe"
            result = subprocess.run(
                [compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                 "-I", str(ROOT / "cores/arduino"),
                 str(ROOT / "tests/host/v04_dma_memory_main.cpp"), "-o", str(binary)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_all_candidate_dma_fabrics_use_full_range_validation(self):
        sources = {
            "serial": ROOT / "variants/nu54dk/serial_fabric_routes.cpp",
            "saadc": ROOT / "cores/arduino/internal/analog/SaadcFabric.cpp",
            "pwm": ROOT / "cores/arduino/internal/analog/PwmSequenceFabric.cpp",
            "pdm": ROOT / "cores/arduino/internal/stream/PdmFabric.cpp",
            "i2s": ROOT / "cores/arduino/internal/stream/I2sFabric.cpp",
            "stream_dma": ROOT / "cores/arduino/internal/stream/StreamFabricInternal.h",
        }
        for name, path in sources.items():
            with self.subTest(name=name):
                self.assertIn("dmaMemoryRangeValid", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
