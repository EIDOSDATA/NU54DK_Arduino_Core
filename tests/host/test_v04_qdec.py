"""Host-only QDEC expected signal and sampling contract tests."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/hil/nu54dk"))
import v04_qdec as qdec
from v04_protocol import ProtocolError

from host_compiler import compiler_command


class QdecTests(unittest.TestCase):
    def test_native_pwm_levels_match_independent_ab_decoder(self):
        """! @brief 실제 C++ 파형의 극성·A/B 배치·idle 복귀를 독립 전이 표로 검사합니다. """
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        source = r'''
#include "qdec_waveform.h"
#include <cstdio>
int main()
{
    for (unsigned reverse = 0; reverse < 2; ++reverse)
    {
        for (unsigned top : {2000U, 10000U})
        {
            for (unsigned step = 0; step < 4; ++step)
            {
                for (unsigned channel = 0; channel < 4; ++channel)
                {
                    std::printf("%u ", v04::qdecPwmValue(step, channel, reverse != 0, top));
                }
            }
            std::puts("");
        }
    }
}
'''
        source = '#include <initializer_list>\n' + source
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'qdec-wave.exe'
            result = subprocess.run([*compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                     '-I', str(ROOT / 'tests/zephyr/v04_pair_hil/src'),
                                     '-x', 'c++', '-', '-o', str(output)], input=source,
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = subprocess.check_output([str(output)], text=True, timeout=10).splitlines()
        self.assertEqual(len(lines), 4)
        for index, line in enumerate(lines):
            values = list(map(int, line.split()))
            top = (2000, 10000)[index % 2]
            self.assertEqual(len(values), 16)
            states = [0]
            for offset in range(0, 16, 4):
                levels = []
                for value in values[offset:offset + 4]:
                    compare = value & 0x7FFF
                    self.assertIn(compare, (0, top))
                    levels.append(int(compare == top) if value & 0x8000 else int(compare == 0))
                self.assertEqual(levels[2:], [0, 0])
                states.append(levels[0] * 2 + levels[1])
            self.assertEqual(states[-1], 0)
            for cycles in (1, 100):
                self.assertEqual(qdec.decode_samples([0] + states[1:] * cycles + [0]),
                                 ((-1 if index >= 2 else 1) * cycles * 4, 0))

    def test_forward_reverse_cycles_and_cancellation(self):
        for cycles in (1, 100, 1000):
            positive = qdec.states(cycles)
            negative = qdec.states(cycles, reverse=True)
            self.assertEqual(qdec.decode_samples(positive), (cycles * 4, 0))
            self.assertEqual(qdec.decode_samples(negative), (-cycles * 4, 0))
            self.assertEqual(qdec.decode_samples(positive + negative), (0, 0))

    def test_double_transition_does_not_count_as_motion(self):
        self.assertEqual(qdec.decode_samples([0, 0, 3, 3, 0, 1]), (1, 2))
        with self.assertRaises(ProtocolError):
            qdec.decode_samples([0, 4])

    def test_sampling_cannot_use_slow_nrfx_default(self):
        for interval in (2000, 10000):
            qdec.verify_timing(interval, 256, debounce=True)
            with self.assertRaises(ProtocolError):
                qdec.verify_timing(interval, 16384)

    def test_production_uses_validated_period_and_explicit_report_policy(self):
        source = (ROOT / "cores/arduino/internal/stream/QdecFabric.cpp").read_text(encoding="utf-8")
        self.assertIn("internal::qdecSamplingValid(configuration.sample_period_us, configuration.led_pre_us)", source)
        self.assertIn("internal::qdecSamplePeriodCode(context->configuration.sample_period_us)", source)
        self.assertIn("driver_configuration.reportper_inten = context->configuration.report_events", source)
        api = (ROOT / "cores/arduino/nucode/StreamFabric.h").read_text(encoding="utf-8")
        self.assertIn("sample_period_us{16384U}", api)
        self.assertIn("report_events{true}", api)

    def test_stream_dap_borrowing_is_explicit_and_does_not_change_public_gpio(self):
        source = "\n".join((ROOT / "cores/arduino/internal/stream" / name).read_text(encoding="utf-8")
                           for name in ("StreamFabricInternal.h", "PdmFabric.cpp",
                                        "I2sFabric.cpp", "QdecFabric.cpp"))
        policy = source.split("streamPin(pin_size_t", 1)[1].split("bool duplicatePins", 1)[0]
        self.assertIn("profile == StreamElectricalProfile::dap_uart_disabled", policy)
        self.assertIn("IS_ENABLED(CONFIG_SERIAL)", policy)
        self.assertIn("DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(uart20))", policy)
        self.assertIn("physical < NRF_GPIO_PIN_MAP(1, 4)", policy)
        self.assertIn("physical > NRF_GPIO_PIN_MAP(1, 7)", policy)
        calls = re.findall(r"streamPin\(configuration\.[^)]*\)", source)
        self.assertEqual(len(calls), 10)
        self.assertTrue(all("configuration.electrical_profile" in call for call in calls))
        dts = (ROOT / "dts/nucode/nu54dk-arduino-pins.dtsi").read_text(encoding="utf-8")
        for pin in range(4, 8):
            node = dts.split(f"arduino_p1_0{pin}:", 1)[1].split("};", 1)[0]
            self.assertIn("NUCODE_PIN_POLICY_SYSTEM_RESERVED", node)
            self.assertIn("<NUCODE_PIN_CAP_ANALOG>", node)

    def test_native_period_and_led_boundaries(self):
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "qdec.exe"
            source = r'''
#include "internal/qdec_sampling.h"
using namespace nucode::arduino::internal;
static_assert(qdecSamplePeriodCode(128) == 0);
static_assert(qdecSamplePeriodCode(256) == 1);
static_assert(qdecSamplePeriodCode(16384) == 7);
static_assert(qdecSamplePeriodCode(131072) == 10);
static_assert(qdecSamplePeriodCode(127) == -1);
static_assert(qdecSamplePeriodCode(0) == -1);
static_assert(qdecSamplePeriodCode(129) == -1);
static_assert(qdecSamplePeriodCode(262144) == -1);
static_assert(qdecSamplingValid(16384, 500));
static_assert(qdecSamplingValid(256, 50));
static_assert(!qdecSamplingValid(128, 128));
static_assert(!qdecSamplingValid(131072, 512));
int main()
{
    return 0;
}
'''
            result = subprocess.run([*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                     "-I", str(ROOT / "cores/arduino"), "-x", "c++", "-", "-o", str(output)],
                                    input=source, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(subprocess.run([str(output)], timeout=10).returncode, 0)


if __name__ == "__main__":
    unittest.main()
