"""합성 신호 runner의 vector, oracle, 실행 안전 gate를 검사합니다."""
from pathlib import Path
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

from host_compiler import compiler_command


class SignalTests(unittest.TestCase):
    def test_pdm_stereo_rejects_shared_channels_swaps_wrong_edges_and_short_dma(self):
        """! @brief 좌우 구별·에지 반전·source 반전과 손상된 수신 길이를 독립 검사합니다. """
        for density in (25, 50, 75):
            for edge in (0, 1):
                vector = (20, 256, density, 1, edge, 1)
                positive = (not edge) != (density == 75)
                pair = [2000, -3000] if positive else [-3000, 2000]
                valid = pair * 128
                self.assertEqual(signal.pdm_received(valid, vector)["channel_means"], pair)
                for invalid in ([2000] * 256, [-3000] * 256, [2000, 3000] * 128,
                                pair[::-1] * 128, valid[:-1], []):
                    with self.assertRaises(ProtocolError):
                        signal.pdm_received(invalid, vector)

    def test_i2s_full_payload_preserves_packed_samples_after_bounded_startup(self):
        """! @brief 시작 frame 뒤 전체 payload와 packed 상위 sample 손상·누락을 검사합니다. """
        for width in (8, 16, 24, 32):
            for channels in (0, 1, 2):
                with self.subTest(width=width, channels=channels):
                    words, seed = 32, 0x13579BDF
                    shifts = list(range(0, 32, width)) if width <= 16 else [0]
                    mask = (1 << width) - 1
                    expected, _ = signal.i2s_expected(seed, words, width, channels)
                    samples = [(word >> shift) & mask for word in expected for shift in shifts]
                    padding = 3 * (2 if channels == 0 else 1)
                    def capture(prefix, body):
                        values = [0] * prefix + body
                        values += [0] * ((words + 16) * len(shifts) - len(values))
                        return [sum(values[index + offset] << shift
                                    for offset, shift in enumerate(shifts))
                                for index in range(0, len(values), len(shifts))]
                    raw = capture(padding, samples)
                    result = signal.i2s_received(raw, seed, words, width, channels)
                    self.assertEqual(result["payload_samples"], len(samples))
                    self.assertEqual(result["startup_zero_samples"], padding)
                    damaged = list(samples)
                    damaged[3] ^= 1
                    for invalid in (capture(padding, damaged), capture(padding, samples[:-1]),
                                    capture(padding, samples[:5] + samples[6:]),
                                    capture(9 * (2 if channels == 0 else 1), samples), raw[:-1]):
                        with self.assertRaises(ProtocolError):
                            signal.i2s_received(invalid, seed, words, width, channels)

    def test_i2s_finite_transfer_waits_for_payload_release_and_uses_separate_tail(self):
        """! @brief 실제 HIL 순서 helper에서 단일/이중 반환·중복·미제출 slot을 검사합니다. """
        source = r'''
#include "i2s_finite_transfer.h"
#include <cassert>
int main()
{
    v04::I2sFiniteTransfer plan;
    plan.reset(1);
    assert(!plan.complete() && plan.nextSlot() == 2);
    assert(!plan.released(1) && !plan.released(2));
    plan.queued();
    assert(plan.nextSlot() == 3 && !plan.complete());
    assert(plan.released(0) && plan.complete());
    assert(!plan.released(0));
    plan.reset(2);
    assert(plan.nextSlot() == 1 && !plan.released(1));
    plan.queued();
    assert(plan.released(0) && !plan.complete() && plan.nextSlot() == 2);
    assert(!plan.released(0) && !plan.released(2));
    plan.queued();
    assert(plan.released(1) && plan.complete() && plan.nextSlot() == 3);
    assert(!plan.released(1) && !plan.released(2));
}
'''
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "finite.cpp"
            executable = Path(folder) / "finite.exe"
            path.write_text(source, encoding="utf-8")
            result = subprocess.run(compiler_command() + ["-std=c++17", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "tests/zephyr/v04_pair_hil/src"), str(path), "-o", str(executable)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_shared_fixtures_run_all_phases_and_release_even_on_failure(self):
        """! @brief Host 실행 순서와 실패 뒤 양쪽 cleanup을 모의 mailbox로 검증합니다. """
        import struct
        events = []
        class Device:
            def __init__(self, role, fixture_id, fail=False):
                self.image = {"role": role}
                self.fixture_id = fixture_id
                self.active = False
                self.args = None
                self.fail = fail
            def command(self, opcode, args=()):
                events.append((self.image["role"], opcode))
                if opcode == 32:
                    return [self.fixture_id, 10000]
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
                        if self.fixture_id in (406, 407):
                            level = int(self.args[2] == 1)
                            return [1, self.args[2], 46, 0, level, 0, 1, 0, 0xC if level else 0x4]
                        return [1, self.args[2], 46, 1, 1, 1, int(self.args[2] == 1), 0, 0x80D]
                    return [0, 0xFFFFFFFF, 46, 0, 0, 0, 1, 0, 0]
                raise AssertionError(opcode)
        records = []
        with patch.object(signal.time, "sleep") as sleep:
            for fixture_id in (405, 406, 407):
                selected = {"id": fixture_id, "family": "analog"}
                for vector in signal.vectors("analog", fixture_id):
                    events.clear()
                    signal.run_case([Device(1, fixture_id), Device(2, fixture_id)], selected, 2, vector,
                                    lambda case, result: records.append((case, result)))
                    self.assertEqual(events[-3:], [(2, 33), (2, 38), (1, 33)])
                    sleep.assert_called_with(.025 if fixture_id in (406, 407) else .010)
                with self.assertRaisesRegex(ProtocolError, "injected receiver start failure"):
                    signal.run_case([Device(1, fixture_id, True), Device(2, fixture_id)], selected, 2,
                                    (0, 32, 0, 0, 0, 1), lambda *args: None)
                self.assertEqual(events[-3:], [(2, 33), (2, 38), (1, 33)])
        self.assertEqual(len(records), 72)
        self.assertEqual(sum(len(result.get("samples", [])) for _, result in records), 7776)

    def test_406_requires_input_bias_and_fully_settled_low_high_samples(self):
        """! @brief VBAT 공유 입력의 출력 활성화·미정착·경계 위반을 거부합니다. """
        status = [1, 1, 1, 1, 0, 32, 32, 0]
        for phase in (0, 1, 2):
            level = int(phase == 1)
            vector = (0, 32, phase, 0, 0, 1)
            source = [1, phase, 46, 0, level, 0, 1, 0, 0xC if level else 0x4]
            samples = [1025 if level else 512] * 32
            result = signal.shared_analog_result(vector, status, samples, source, 406)
            self.assertEqual(result['scope'], 'input-bias-shared-ain5-manual-saadc')
            for wrong in ([-257] * 32, [4096] * 32,
                          samples[:-1] + [1024 if level else 513], samples[:-1]):
                with self.assertRaises(ProtocolError):
                    signal.shared_analog_result(vector, status, wrong, source, 406)
            for index, bad in ((3, 1), (4, 1 - level), (8, source[8] | 1), (8, 0x80D)):
                wrong = source.copy()
                wrong[index] = bad
                with self.assertRaises(ProtocolError):
                    signal.shared_analog_result(vector, status, samples, wrong, 406)
        self.assertEqual(list(signal.vectors("analog", 406)), list(signal.vectors("analog", 405)))
        with self.assertRaises(ProtocolError):
            signal.shared_source_readback(source, 2, 408)

    def test_407_button_shared_input_rejects_stuck_low_and_any_output_driver(self):
        """! @brief 버튼 공유 입력의 세 단계·DMA 경계와 눌림 LOW·출력 구성을 거부합니다. """
        vectors = list(signal.vectors("analog", 407))
        self.assertEqual(len(vectors), 12)
        self.assertEqual(len(set(vectors)), 12)
        self.assertEqual(sum(v[1] * v[5] for v in vectors), 2592)
        for vector in vectors:
            phase = vector[2]
            count = vector[1] * vector[5]
            high = phase == 1
            source = [1, phase, 46, 0, int(high), 0, 1, 0, 0xC if high else 0x4]
            status = [1, 1, 1, 1, 0, count, vector[1], 0]
            samples = [1025 if high else 512] * count
            result = signal.shared_analog_result(vector, status, samples, source, 407)
            self.assertEqual(result["scope"], "input-bias-shared-ain6-manual-saadc")
            self.assertEqual(result["phase"], ("pulldown-before", "pullup", "pulldown-after")[phase])
            for wrong in ([0 if high else 1200] * count, samples[:-1], [-32768] * count,
                          samples[:-1] + [1024 if high else 513], [4096] * count):
                with self.assertRaises(ProtocolError):
                    signal.shared_analog_result(vector, status, wrong, source, 407)
            for index, value in ((3, 1), (4, int(not high)), (8, source[8] | 1), (8, 0x80D)):
                wrong = source.copy()
                wrong[index] = value
                with self.assertRaises(ProtocolError):
                    signal.shared_analog_result(vector, status, samples, wrong, 407)

    def test_shared_source_never_drives_high_and_releases_on_abort(self):
        """! @brief 실제 firmware helper를 컴파일하여 잘못된 인자·중복 시작·해제를 검사합니다. """
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "shared.exe"
            result = subprocess.run([*compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
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
        self.assertEqual(left16, 0xFFFFFFFF)
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
