"""! @brief 무점퍼 실기 계획과 nonce·DMA 시작·cleanup의 독립 판정을 검증합니다. """
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hil/nu54dk'))
from v04_nojumper import Device, ProtocolError, pwm_vectors, validate_reply

ROOT = Path(__file__).resolve().parents[2]


class NojumperTests(unittest.TestCase):
    def test_firmware_checks_the_canonical_pwm_block_key(self):
        source = (
            ROOT
            / 'tests'
            / 'zephyr'
            / 'm25_nojumper_hil'
            / 'src'
            / 'main.cpp'
        ).read_text(encoding='utf-8')
        self.assertIn(
            'peripheralIoResource(IoResourceKind::pwm_block, instance)', source
        )
        self.assertNotIn(
            'peripheralIoResource(IoResourceKind::pwm_block, instance,', source
        )

    def record(self, flags=1):
        request = [1, 919, 1, 20, flags, 2, 1000, 1]
        reply = request[:] + [0] * 24
        reply[2] = 0
        reply[11] = 1
        reply[18] = reply[24] = 2
        reply[19:22] = [1, 1, 1]
        if not flags & 1 or flags & 2:
            reply[13] = reply[15] = 1
        if flags & 32:
            reply[22] = 7
        return request, reply

    def test_plan_has_all_modes_without_duplicate_vectors(self):
        vectors = list(pwm_vectors())
        self.assertEqual(len(vectors), 960)
        self.assertEqual(len(set(vectors)), 960)
        for instance in (20, 21, 22):
            self.assertEqual(sum(v[1] == instance for v in vectors), 320)

    def test_valid_cancel_and_start_modes(self):
        for flags in (0, 1, 3, 33, 35):
            validate_reply(*self.record(flags))

    def test_cancel_rejects_any_dma_or_period_activity(self):
        for index in range(12, 17):
            request, reply = self.record()
            reply[index] = 1
            with self.assertRaises(ProtocolError):
                validate_reply(request, reply)

    def test_started_requires_dma_and_wave_counter(self):
        for index in (13, 15):
            request, reply = self.record(3)
            reply[index] = 0
            with self.assertRaises(ProtocolError):
                validate_reply(request, reply)

    def test_identity_result_and_cleanup_fail_closed(self):
        for index in (0, 1, 2, 3, 7, 8, 9, 10, 11, 17, 18, 19, 20, 21):
            request, reply = self.record()
            reply[index] ^= 1
            with self.assertRaises(ProtocolError):
                validate_reply(request, reply)

    def test_subscribed_start_must_be_rejected(self):
        request, reply = self.record(33)
        reply[22] = 0
        with self.assertRaises(ProtocolError):
            validate_reply(request, reply)

    def test_failure_is_preserved_before_poisoning_session(self):
        target = Mock()
        target.read32.return_value = 1
        target.read_memory_block32.return_value = [0] * 32
        device = Device(target, {'symbols': {'nojumper_request': 0x20000000,
                                            'nojumper_response': 0x20000100}})
        rows = []
        with self.assertRaises(ProtocolError):
            device.command((1, 20, 1, 2, 1000, 1), rows.append)
        self.assertEqual(len(rows), 1)
        self.assertTrue(device.poisoned)
        writes = target.write32.call_count
        with self.assertRaises(ProtocolError):
            device.command((1, 20, 1, 2, 1000, 1), rows.append)
        self.assertEqual(target.write32.call_count, writes)


if __name__ == '__main__':
    unittest.main()
