"""합성 신호 runner의 vector, oracle, 실행 안전 gate를 검사합니다."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/hil/nu54dk"))
import v04_signal as signal
import v04_signal_run as runner
from v04_protocol import ProtocolError


class SignalTests(unittest.TestCase):
    def test_405_runs_all_phases_and_proves_source_release_even_on_failure(self):
        """! @brief Host 실행 순서와 실패 뒤 양쪽 cleanup을 모의 mailbox로 검증합니다. """
        import struct
        events = []
        class Device:
            def __init__(self, role, fail=False):
                self.image = {"role": role}
                self.active = False
                self.args = None
                self.fail = fail
            def command(self, opcode, args=()):
                events.append((self.image["role"], opcode))
                if opcode == 32:
                    return [405, 10000]
                if opcode == 34:
                    self.active = True
                    self.args = args
                    return [0]
                if opcode == 33:
                    self.active = False
                    return [0]
                if opcode == 35:
                    if self.fail:
                        raise ProtocolError("injected receiver start failure")
                    return [0]
                if opcode == 36:
                    return [1, 1, 1, 1, 0, self.args[1] * self.args[5], self.args[1], 0]
                if opcode == 37:
                    sample = 1200 if self.args[2] == 1 else 0
                    return list(struct.unpack(f"<{args[1] // 2}I", struct.pack(f"<{args[1]}h", *([sample] * args[1]))))
                if opcode == 38:
                    if self.active:
                        return [1, self.args[2], 46, 1, 1, 1, int(self.args[2] == 1), 0, 0x80D]
                    return [0, 0xFFFFFFFF, 46, 0, 0, 0, 1, 0, 0]
                raise AssertionError(opcode)
        selected = {"id": 405, "family": "analog"}
        records = []
        with patch.object(signal.time, "sleep"):
            for vector in signal.vectors("analog", 405):
                events.clear()
                signal.run_case([Device(1), Device(2)], selected, 2, vector,
                                lambda case, result: records.append((case, result)))
                self.assertEqual(events[-3:], [(2, 33), (2, 38), (1, 33)])
            with self.assertRaisesRegex(ProtocolError, "injected receiver start failure"):
                signal.run_case([Device(1, True), Device(2)], selected, 2,
                                (0, 32, 0, 0, 0, 1), lambda *args: None)
            self.assertEqual(events[-3:], [(2, 33), (2, 38), (1, 33)])
        self.assertEqual(len(records), 24)
        self.assertEqual(sum(len(result.get("samples", [])) for _, result in records), 2592)

    def test_shared_source_never_drives_high_and_releases_on_abort(self):
        """! @brief 실제 firmware helper를 컴파일하여 잘못된 인자·중복 시작·해제를 검사합니다. """
        compiler = shutil.which("g++")
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "shared.exe"
            result = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT), str(ROOT / "tests/host/v04_shared_analog_main.cpp"),
                "-o", str(executable)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_405_has_low_release_low_for_every_dma_boundary(self):
        actual = list(signal.vectors("analog", 405))
        self.assertEqual(len(actual), 12)
        self.assertEqual(len(set(actual)), 12)
        self.assertEqual(sum(v[1] * v[5] for v in actual), 2592)
        for offset in range(0, 12, 3):
            self.assertEqual([v[2] for v in actual[offset:offset + 3]], [0, 1, 2])
        for fixture_id in (401, 402, 403, 404, 408):
            self.assertEqual(list(signal.vectors("analog", fixture_id)),
                             list(signal.vectors("analog")))

    def test_shared_adc_oracle_rejects_stuck_levels_short_dma_and_push_pull(self):
        for phase in (0, 1, 2):
            vector = (0, 32, phase, 0, 0, 2)
            status = [1, 1, 1, 1, 0, 64, 32, 0]
            source = [1, phase, 46, 1, 1, 1, int(phase == 1), 0, 0x80D]
            samples = [1200 if phase == 1 else 4] * 64
            result = signal.shared_analog_result(vector, status, samples, source)
            self.assertEqual(len(result["samples"]), 64)
            for position, changed in ((0, samples[:-1]), (0, [0 if phase == 1 else 1200] * 64),
                                       (0, [-257] * 64), (0, [4096] * 64),
                                       (1, [1, 1, 1, 1, 0, 63, 32, 0]),
                                       (2, [1, phase, 46, 1, 1, 0, int(phase == 1), 0, 0x80D]),
                                       (2, [1, phase, 46, 1, 1, 1, int(phase == 1), 0, 0xD])):
                arguments = [samples, status, source]
                arguments[position] = changed
                with self.assertRaises(ProtocolError):
                    signal.shared_analog_result(vector, arguments[1], arguments[0], arguments[2])
        vector = (0, 32, 1, 0, 0, 2)
        signal.shared_analog_result(vector, status, [0] * 3 + [1200] * 61,
                                    [1, 1, 46, 1, 1, 1, 1, 0, 0x80D])
        with self.assertRaises(ProtocolError):
            signal.shared_analog_result(vector, status, [0] * 4 + [1200] * 60,
                                        [1, 1, 46, 1, 1, 1, 1, 0, 0x80D])

    def test_partial_arm_failure_still_disarms_both_devices(self):
        """! @brief 두 번째 보드 arm 실패 시 첫 번째 보드의 lease를 방치하지 않습니다. """
        events = []
        class Device:
            def __init__(self, role):
                self.image = {"role": role}
            def command(self, opcode, args=()):
                events.append((self.image["role"], opcode))
                if opcode == 32:
                    if self.image["role"] == 2:
                        raise ProtocolError("injected arm failure")
                    return [401, 10000]
                return [0]
        with self.assertRaisesRegex(ProtocolError, "injected arm failure"):
            signal.run_case([Device(1), Device(2)], {"family": "analog", "id": 401},
                            2, (20, 32, 1021, 512, 0, 1), lambda *args: None)
        self.assertEqual(events[-2:], [(1, 33), (2, 33)])

    def test_vector_counts_and_boundaries(self):
        self.assertEqual(len(list(signal.vectors("analog"))), 48)
        self.assertEqual(len(list(signal.vectors("qdec"))), 48)
        self.assertEqual(len(list(signal.vectors("i2s"))), 96)
        self.assertEqual(len(list(signal.vectors("pdm"))), 96)
        self.assertIn((48000, 32, 0, 256, 2, 0x13579BDF),
                      signal.vectors("i2s"))
        self.assertIn((21, 1024, 75, 1, 1, 2), signal.vectors("pdm"))

    def test_i2s_masks_are_width_and_channel_explicit(self):
        _, stereo16 = signal.i2s_expected(1, 2, 16, 0)
        _, left16 = signal.i2s_expected(1, 2, 16, 1)
        _, stereo32 = signal.i2s_expected(1, 2, 32, 0)
        self.assertEqual(stereo16, 0xFFFFFFFF)
        self.assertEqual(left16, 0xFFFF)
        self.assertEqual(stereo32, 0xFFFFFFFF)

    def test_pdm_runner_requires_channel_and_density_discrimination(self):
        source = (ROOT / "tests/hil/nu54dk/v04_signal.py").read_text(
            encoding="utf-8")
        self.assertIn("PDM stereo channels are not independently distinguishable", source)
        self.assertIn("PDM density ordering mismatch", source)

    def test_pdm_firmware_reports_the_released_dma_length(self):
        source = (ROOT / "cores/arduino/internal/stream/PdmFabric.cpp").read_text(
            encoding="utf-8")
        self.assertIn("samples = slot.bytes / sizeof(std::int16_t)", source)
        self.assertIn("event->buffer_released, samples, 0", source)

    def test_default_cli_is_preflight_and_execution_needs_files(self):
        base = ["--dut", "a" * 32, "--peer", "b" * 32,
                "--build-root", "unused", "--pyocd", "unused",
                "--fixture", "401"]
        self.assertFalse(runner.arguments(base).execute_fixture)
        with self.assertRaises(ProtocolError):
            runner.arguments(base + ["--execute-fixture"])

    def test_signal_campaign_is_bounded(self):
        base = ["--dut", "a" * 32, "--peer", "b" * 32,
                "--build-root", "unused", "--pyocd", "unused",
                "--fixture", "401"]
        self.assertEqual(runner.arguments(base + ["--repetitions", "100"]).repetitions,
                         100)
        with self.assertRaises(ProtocolError):
            runner.arguments(base + ["--duration-seconds", "7201"])

    def test_invalid_vectors_fail_closed(self):
        with self.assertRaises(ProtocolError):
            list(signal.vectors("unknown"))
        with self.assertRaises(ProtocolError):
            signal.arguments_for("analog", tuple(range(9)))


if __name__ == "__main__":
    unittest.main()
