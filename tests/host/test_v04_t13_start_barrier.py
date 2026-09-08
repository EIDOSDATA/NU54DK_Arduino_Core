"""! @brief Host 시작 명령 간격과 무관하게 양쪽 RX 준비 후 송신하는 순서를 검증합니다. """
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_run as runner
from v04_protocol import ProtocolError


class StartBarrierTests(unittest.TestCase):
    def devices(self, fail_role=None, fail_opcode=None):
        self.calls = []
        self.clock = 0.0
        devices = []
        for role in (1, 2):
            device = mock.Mock(image={'role': role})
            def command(opcode, values=(), timeout=2, role=role):
                self.calls.append((role, opcode, values))
                self.clock += .250
                return [0] if (role, opcode) == (fail_role, fail_opcode) else [1]
            device.command.side_effect = command
            devices.append(device)
        return devices

    def test_slow_host_arms_both_receivers_before_any_transmit_release(self):
        """! @brief 기존100ms보다 긴250ms 간격에서도 두 RX 응답이 송신 허가보다 먼저입니다. """
        devices = self.devices()
        rows = []
        test = {'id': 2, 'harness': 'S', 'serial_links': []}
        with mock.patch.object(runner.time, 'monotonic', side_effect=lambda: self.clock):
            runner.start_devices(devices, test, lambda name, row: rows.append(row), 'test',
                                 serial_start_barrier=True)
        self.assertEqual(self.calls, [(2, 98, (1,)), (1, 98, (1,)), (2, 184, ()), (1, 184, ())])
        self.assertEqual([row['host_elapsed_seconds'] for row in rows[1:]], [.25, .5, .75, 1.0])
        self.assertTrue(all(row['both_receivers_prepared'] for row in rows[3:]))

    def test_failed_receiver_preparation_never_releases_transmission(self):
        devices = self.devices(fail_role=1, fail_opcode=98)
        with self.assertRaises(ProtocolError):
            runner.start_devices(devices, {'id': 2, 'harness': 'S', 'serial_links': []},
                                 lambda *args: None, 'test', serial_start_barrier=True)
        self.assertEqual(self.calls, [(2, 98, (1,)), (1, 98, (1,))])

    def test_original_start_has_no_release_and_other_topologies_are_rejected(self):
        devices = self.devices()
        test = {'id': 2, 'harness': 'S', 'serial_links': []}
        runner.start_devices(devices, test, lambda *args: None, 'test')
        self.assertEqual(self.calls, [(2, 98, ()), (1, 98, ())])
        for changed in ({**test, 'harness': 'U'}, {**test, 'id': 6}):
            with self.assertRaises(ProtocolError):
                runner.start_devices(devices, changed, lambda *args: None, 'test', serial_start_barrier=True)


if __name__ == '__main__':
    unittest.main()
