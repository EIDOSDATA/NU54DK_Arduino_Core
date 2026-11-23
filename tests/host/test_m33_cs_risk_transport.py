"""! @brief CS 위험 회귀의 명시적 DK 신원·초기화 경계를 장치 없이 검증합니다. """
from __future__ import annotations

from contextlib import contextmanager, nullcontext
import copy
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
sys.path.insert(0, str(ROOT / 'tools/bluetooth'))
import m33_cs_acl_radio_risk_run as subject
import m33_diagnostics as diagnostics
import m33_probe_transport as transport
from v04_protocol import ProbeLocks

DESCRIPTOR = {'kind': 'jlink-swd', 'fixture_sha256': 'a' * 64,
              'dll_sha256': 'b' * 64, 'board': 'nrf54l15dk'}
UID = '1057707567'
USB_SERIAL = '001057707567'
PROBE = hashlib.sha256(UID.encode()).hexdigest()


class CommonLockExpansionTests(unittest.TestCase):
    """! @brief 공통 세 잠금 확장이 parent·child의 기존 namespace를 덮어쓰지 않습니다. """
    def test_one_or_two_roles_expand_to_three_with_explicit_directory(self):
        values = ['1057707567', '1057715090', '1057783094']
        with tempfile.TemporaryDirectory(prefix='m33-lock-parent-') as temporary:
            for requested in (values[:1], values[:2]):
                with self.subTest(requested=requested):
                    directory = Path(temporary) / ('child-' + str(len(requested)))
                    with (patch.dict(os.environ, {'NU54_HIL_JLINK_FIXTURE': 'explicit-fixture'}),
                          patch.object(transport, 'lock_identities', return_value=values) as expand):
                        with ProbeLocks(requested, directory) as locks:
                            self.assertEqual(len(locks.streams), 3)
                            self.assertEqual(locks.directory, directory)
                        self.assertEqual(locks.streams, [])
                    expand.assert_called_once_with(requested)

    def test_child_temp_namespace_is_preserved(self):
        values = ['1057707567', '1057715090', '1057783094']
        with (patch.dict(os.environ, {'NU54_HIL_JLINK_FIXTURE_SHA256': 'f' * 64}),
              patch.object(transport, 'lock_identities', return_value=values),
              patch('v04_protocol.tempfile.gettempdir', return_value='D:/w06/child-owned-tmp')):
            locks = ProbeLocks(values[:1])
        self.assertEqual(locks.directory, Path('D:/w06/child-owned-tmp/nu54dk-hil-locks'))

    def test_default_cmsis_uses_requested_lock_set(self):
        environment = {key: value for key, value in os.environ.items()
                       if key not in ('NU54_HIL_JLINK_FIXTURE', 'NU54_HIL_JLINK_FIXTURE_SHA256')}
        with (patch.dict(os.environ, environment, clear=True),
              patch.object(transport, 'lock_identities') as expand):
            locks = ProbeLocks(['OLD1', 'old2'])
        self.assertEqual(locks.uids, ['old1', 'old2'])
        expand.assert_not_called()


class CsTransportTests(unittest.TestCase):
    """! @brief 기본 DAP와 명시 DK mapping·reset 동작이 섞이지 않도록 확인합니다. """
    def test_probe_resolution_uses_selected_backend_without_connect_helper(self):
        probes = [SimpleNamespace(unique_id=value) for value in (UID, '1057715090', '1057783094')]
        hashes = [hashlib.sha256(row.unique_id.encode()).hexdigest() for row in probes]
        selected = SimpleNamespace(ensure_pyocd_available=Mock())
        backend = SimpleNamespace(discover=Mock(return_value=(probes, [])))
        with (patch.object(subject, 'probe_transport', return_value=selected),
              patch.object(diagnostics, 'create_preparation_backend', return_value=backend),
              patch.object(diagnostics, 'private_debug_output', return_value=nullcontext())):
            self.assertEqual(subject.resolve_probes(dict(zip(subject.ROLES, hashes[:2]))),
                             dict(zip(subject.ROLES, [row.unique_id for row in probes[:2]])))
        selected.ensure_pyocd_available.assert_called_once_with()
        backend.discover.assert_called_once_with()

    def test_duplicate_probe_enumeration_is_rejected(self):
        probes = [SimpleNamespace(unique_id=UID), SimpleNamespace(unique_id=UID)]
        with (patch.object(subject, 'probe_transport', return_value=SimpleNamespace(
                ensure_pyocd_available=Mock())),
              patch.object(diagnostics, 'create_preparation_backend', return_value=SimpleNamespace(
                  discover=lambda: (probes, []))),
              patch.object(diagnostics, 'private_debug_output', return_value=nullcontext())):
            with self.assertRaisesRegex(subject.CsAclRadioRiskFailure, 'duplicate'):
                subject.resolve_probes(dict(zip(subject.ROLES, [PROBE, 'f' * 64])))

    def mapping(self):
        board = {'serial': UID, 'usb_serial': USB_SERIAL, 'probe_sha256': PROBE,
                 'vid': 0x1366, 'pid': 0x1069}
        port = SimpleNamespace(device='COM23', serial_number=USB_SERIAL, vid=0x1366, pid=0x1069)
        pnp = {'DeviceID': 'COM23', 'Status': 'OK',
               'PNPDeviceID': 'USB\\VID_1366&PID_1069&MI_00\\private-instance'}
        selector = SimpleNamespace(descriptor=lambda: DESCRIPTOR,
                                   load_fixture=lambda: {'boards': [board]},
                                   resolve_endpoint=Mock(), serial_pnp_snapshot=lambda: [pnp])
        return selector, port, pnp

    def test_dual_uart_uses_raw_serial_and_distinct_mi00_aux(self):
        selector, port, _pnp = self.mapping()
        ports = SimpleNamespace(comports=lambda: [port])
        with (patch.object(subject, 'probe_transport', return_value=selector),
              patch.object(subject, 'import_pyserial', return_value=(object(), ports))):
            subject.require_role_ports({'app': 'COM24', 'aux': 'COM23'}, UID)
        selector.resolve_endpoint.assert_called_once_with(PROBE, None, 'COM24', ports)

    def test_wrong_aux_interface_or_board_is_rejected(self):
        for changed in ('interface', 'serial', 'pid'):
            with self.subTest(changed=changed):
                selector, port, pnp = self.mapping()
                if changed == 'interface':
                    pnp['PNPDeviceID'] = pnp['PNPDeviceID'].replace('MI_00', 'MI_02')
                elif changed == 'serial':
                    port.serial_number = '001057715090'
                else:
                    port.pid = 0x0204
                with (patch.object(subject, 'probe_transport', return_value=selector),
                      patch.object(subject, 'import_pyserial', return_value=(
                          object(), SimpleNamespace(comports=lambda: [port])))):
                    with self.assertRaisesRegex(subject.CsAclRadioRiskFailure, 'MI00 identity'):
                        subject.require_role_ports({'app': 'COM24', 'aux': 'COM23'}, UID)

    def test_default_mapping_and_start_keep_original_functions(self):
        selected = SimpleNamespace(descriptor=lambda: {'kind': 'cmsis-dap-v2'})
        streams = {'app': object(), 'aux': object()}
        with (patch.object(subject, 'probe_transport', return_value=selected),
              patch.object(subject, 'require_mapping') as require,
              patch.object(subject, 'reset_halted_start', return_value={'legacy': True}) as start,
              patch.object(subject, '_load_private_pyocd_backend') as backend):
            subject.require_role_ports({'app': 'COM2', 'aux': 'COM3'}, 'old-uid')
            self.assertEqual(subject.start_role(streams, 'old-uid'), {'legacy': True})
        self.assertEqual(require.call_count, 2)
        start.assert_called_once_with(streams, 'old-uid')
        backend.assert_not_called()

    def startup(self, *, close_failure=False, halted=True, post_state='RUNNING', calls=None):
        """! @brief 실제 시작 경로의 resume 전후 상태와 세션 종료를 모의합니다. """
        calls = [] if calls is None else calls
        resumed = False
        registers = {0x5010A080: 2, 0x500D8290: 2}
        def read(address):
            calls.append(('read', address))
            return 0x411FD210 if address == 0xE000ED00 else registers[address]
        def write(address, value):
            calls.append(('write', address, value))
            registers[address] = value
        def state():
            """! @brief resume 후에만 후속 상태나 읽기 오류를 반환합니다. """
            calls.append(('state',))
            if resumed:
                if isinstance(post_state, Exception):
                    raise post_state
                return SimpleNamespace(name=post_state)
            return SimpleNamespace(name='HALTED' if halted else 'RUNNING')
        def resume():
            """! @brief 추가 reset 없이 실행 상태 전이를 기록합니다. """
            nonlocal resumed
            resumed = True
            calls.append(('resume',))
        target = SimpleNamespace(
            reset_and_halt=lambda **kwargs: calls.append(('reset', kwargs)),
            get_state=state,
            read32=read, write32=write, flush=lambda: calls.append(('flush',)),
            resume=resume,
        )
        @contextmanager
        def session(probe):
            calls.append(('open', probe))
            try:
                yield SimpleNamespace(target=target)
            finally:
                calls.append(('close',))
                if close_failure:
                    raise RuntimeError('checked close failed')
        backend = SimpleNamespace(session=session,
                                  target_type=SimpleNamespace(ResetType=SimpleNamespace(SYSRESETREQ='software')))
        streams = {role: SimpleNamespace(
            reset_input_buffer=lambda name=role: calls.append(('input', name)),
            reset_output_buffer=lambda name=role: calls.append(('output', name)),
        ) for role in ('app', 'aux')}
        with (patch.object(subject, 'probe_transport', return_value=SimpleNamespace(descriptor=lambda: DESCRIPTOR)),
              patch.object(subject, '_load_private_pyocd_backend', return_value=(backend, 'probe', nullcontext)),
              patch.object(subject.time, 'sleep') as sleep):
            result = subject.start_role(streams, UID)
        sleep.assert_called_once_with(0.05)
        return result, calls

    def test_dk_software_reset_drains_only_while_halted_and_closes(self):
        result, calls = self.startup()
        self.assertIn(('reset', {'reset_type': 'software'}), calls)
        reset = calls.index(('reset', {'reset_type': 'software'}))
        resume = calls.index(('resume',))
        self.assertTrue(all(reset < index < resume for index, row in enumerate(calls)
                            if row[0] in ('input', 'output', 'write')))
        self.assertEqual(calls[-1], ('close',))
        self.assertEqual(result['frequency_hz'], 500000)
        self.assertEqual(subject.validate_start_transport(result), DESCRIPTOR)

    def test_checked_close_failure_prevents_start_receipt(self):
        with self.assertRaisesRegex(RuntimeError, 'checked close failed'):
            self.startup(close_failure=True)

    def test_failed_halt_prevents_drain_and_success(self):
        calls = []
        with self.assertRaisesRegex(subject.CsAclRadioRiskFailure, 'did not halt'):
            self.startup(halted=False, calls=calls)
        self.assertFalse(any(row[0] in ('resume', 'input', 'output') for row in calls))
        self.assertEqual(calls[-1], ('close',))

    def test_dk_confirms_running_or_sleeping_before_close(self):
        for active in ('RUNNING', 'SLEEPING'):
            with self.subTest(active=active):
                _result, calls = self.startup(post_state=active)
                self.assertEqual(calls[-3:], [('resume',), ('state',), ('close',)])
                self.assertEqual(sum(row[0] == 'reset' for row in calls), 1)
                self.assertEqual(calls.count(('resume',)), 1)

    def test_dk_still_halted_times_out_closes_without_retry(self):
        calls = []
        with (patch.object(diagnostics.time, 'monotonic', side_effect=[0.0, 1.0]),
              self.assertRaises(diagnostics.IdleAuditFailure) as raised):
            self.startup(post_state='HALTED', calls=calls)
        self.assertEqual(raised.exception.evidence['kind'], 'target_state_timeout')
        self.assertEqual(calls[-3:], [('resume',), ('state',), ('close',)])
        self.assertEqual(sum(row[0] == 'reset' for row in calls), 1)
        self.assertEqual(calls.count(('resume',)), 1)

    def test_dk_reset_or_lockup_after_resume_closes_and_rejects(self):
        for invalid in ('RESET', 'LOCKUP'):
            with self.subTest(invalid=invalid):
                calls = []
                with self.assertRaises(diagnostics.IdleAuditFailure) as raised:
                    self.startup(post_state=invalid, calls=calls)
                self.assertEqual(raised.exception.evidence['kind'], 'target_state_invalid')
                self.assertEqual(calls[-3:], [('resume',), ('state',), ('close',)])
                self.assertEqual(sum(row[0] == 'reset' for row in calls), 1)
                self.assertEqual(calls.count(('resume',)), 1)

    def test_dk_post_resume_read_error_propagates_after_close(self):
        calls = []
        failure = RuntimeError('state read failed')
        with self.assertRaises(RuntimeError) as raised:
            self.startup(post_state=failure, calls=calls)
        self.assertIs(raised.exception, failure)
        self.assertEqual(calls[-3:], [('resume',), ('state',), ('close',)])
        self.assertEqual(sum(row[0] == 'reset' for row in calls), 1)
        self.assertEqual(calls.count(('resume',)), 1)

    def test_start_receipt_rejects_wrong_reset_frequency_or_bias(self):
        original, _calls = self.startup()
        for changed in ('reset_type', 'frequency_hz', 'bias', 'missing_transport'):
            with self.subTest(changed=changed):
                record = copy.deepcopy(original)
                if changed == 'bias':
                    record['target_uart_idle_bias'][0]['after'] = '0x00000002'
                elif changed == 'missing_transport':
                    del record['transport']
                else:
                    record[changed] = 'hardware' if changed == 'reset_type' else 1000000
                with self.assertRaises(subject.CsAclRadioRiskFailure):
                    subject.validate_start_transport(record)


if __name__ == '__main__':
    unittest.main()
