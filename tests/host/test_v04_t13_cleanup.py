"""! @brief 한쪽 PREPARE 실패 시 미준비 상대의 STOP 세션 보존을 검사합니다. """
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
from v04_protocol import ProtocolError
import v04_t13_cases as cases
import v04_t13_fault as serial_fault
import v04_t13_stream_fault as stream_fault


class PartialPreparationCleanupTests(unittest.TestCase):
    """! @brief target의 미준비 접근 거부가 두 보드 STOP을 막는 회귀를 재현합니다. """

    def test_unprepared_peer_keeps_stop_after_serial_or_stream_prepare_failure(self):
        for module, case_id in ((serial_fault, 2), (stream_fault, 30)):
            with self.subTest(module=module.__name__):
                test = next(row for row in cases.cases() if row['id'] == case_id)
                devices = []
                for role in (1, 2):
                    device = mock.Mock()
                    device.image = {'role': role}
                    state = {'selected': False, 'poisoned': False}

                    def command(opcode, args=(), timeout=2, *, state=state):
                        if state['poisoned']:
                            raise ProtocolError('session faulted after command rejection')
                        if opcode == 97:
                            state['selected'] = True
                            return [0]
                        if opcode == 99:
                            return [case_id if state['selected'] else 0] + [0] * 15
                        if opcode in (100, 104) and not state['selected']:
                            state['poisoned'] = True
                            raise ProtocolError('firmware rejected unprepared snapshot: 403')
                        if opcode in (100, 104, 110, 115):
                            return [0] * 20
                        if opcode == 102:
                            return [1, 1]
                        if opcode == 107:
                            return [1, 0, 0, 0, 0, 0, 0, 0]
                        if opcode == 51:
                            return [0, 0, 0, 0, 0xFFFFFFFF, 0, 0, 0]
                        return [1]

                    device.command.side_effect = command
                    devices.append(device)
                rows = []
                with self.assertRaisesRegex(ProtocolError, 'preparation failed'):
                    module.execute(devices, test, 1, 1, mock.Mock(),
                        lambda identifier, row: rows.append({'id': identifier, **row}), preflight=True)
                cleanup = next(row for row in rows if row['status'] == 'cleanup')
                self.assertEqual([row['stopped'] for row in cleanup['outcomes']], [True, True])
                self.assertFalse(any(call.args[0] in (100, 104) for call in devices[0].command.call_args_list))
                self.assertTrue(all(any(call.args[0] == 102 for call in device.command.call_args_list)
                    for device in devices))
                self.assertFalse(any(row['status'] == 'passed' for row in rows))


if __name__ == '__main__':
    unittest.main()
