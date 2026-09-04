"""Compile the production timer math and firmware framing on the Host."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/hil/nu54dk"))
import v04_protocol


class V04MathTests(unittest.TestCase):
    def test_production_clock_math_and_cross_language_protocol(self):
        compiler = shutil.which("g++")
        self.assertIsNotNone(compiler, "Host C++ compiler required")
        with tempfile.TemporaryDirectory(prefix="nu54-v04-math-") as directory:
            binary = Path(directory) / "math.exe"
            result = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "cores/arduino"), "-I", str(ROOT / "tests/zephyr/v04_pair_hil/src"),
                str(ROOT / "tests/host/v04_math_main.cpp"), "-o", str(binary)], capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            valid = v04_protocol.encode(bytes(range(16)), 71, 1, 2, [20, 100, 400000])
            result = subprocess.run([str(binary)], input=valid, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(int(result.stdout), v04_protocol.checksum(valid[:-4]))
            for broken in (valid[:-1], valid[:-4] + bytes(4), v04_protocol.encode(bytes(range(16)), 71, 2, 2)):
                result = subprocess.run([str(binary)], input=broken, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)

    def test_target_clock_uses_actual_instance_and_internal_adc_is_soc_specific(self):
        event = (ROOT / "cores/arduino/EventFabric.cpp").read_text(encoding="utf-8")
        self.assertIn("timerPrescalerFor(NRF_TIMER_BASE_FREQUENCY_GET(context->reg)", event)
        analog = (ROOT / "cores/arduino/AnalogFabric.cpp").read_text(encoding="utf-8")
        supported = analog.split("bool supportedInput(", 1)[1].split("[[nodiscard]]", 1)[0]
        self.assertNotIn("case SaadcInput::vss", supported)
        self.assertIn("case SaadcInput::avdd", supported)
        self.assertIn("channels[index].channel_config.gain =", analog)
        api = (ROOT / "cores/arduino/nucode/AnalogFabric.h").read_text(encoding="utf-8")
        self.assertIn("SaadcGain gain{SaadcGain::one}", api)
        self.assertIn("SaadcGain::one_quarter", (ROOT / "tests/zephyr/v04_pair_hil/src/main.cpp").read_text(encoding="utf-8"))


if __name__ == "__main__": unittest.main()
