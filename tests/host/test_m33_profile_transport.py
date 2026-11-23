"""! @brief DK profile 원문·세션·관측의 실패 전파를 장치 없이 검증합니다. """
from __future__ import annotations

from collections import deque
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
import m33_profile_transport as subject
from m33_profile_uart_capture import CapturePort

TRANSPORT = {'kind': 'jlink-swd', 'fixture_sha256': 'a' * 64,
             'dll_sha256': 'b' * 64, 'board': 'nrf54l15dk'}
NONCE = '1' * 32


def write_json(path, value):
    """! @brief 순수 fixture JSON을 실제 byte hash와 함께 만듭니다. """
    path.write_text(json.dumps(value), encoding='utf-8')
    return {'path': path.name, 'sha256': subject.file_digest(path)}


def idle():
    """! @brief 합격한 strict idle 관측의 공개 필드만 반환합니다. """
    return {'cpu': 'HALTED', 'radio_state': 0, 'reset_observed': False,
            'read_only': True, 'registers': {}}


def make_bundle(folder):
    """! @brief 독립 byte 파일을 가진 세 역할·11세션의 최소 계약 fixture를 만듭니다. """
    evidence = {'transport': dict(TRANSPORT), 'transport_capture_errors': [],
                'boards': {}, 'uart_capture': {}, 'cleanup': {}, 'debug_sessions': [],
                'exact_program': {}}
    transcript = []
    for index, role in enumerate(subject.ROLES):
        probe = str(index + 2) * 64
        evidence['boards'][role] = {'probe_sha256': probe, 'image_sha256': 'c' * 64}
        evidence['cleanup'][role] = {'nonce': NONCE}
        rx = f'M33PROFILE|1|STOPPED|role={role}|nonce={NONCE}\n'.encode()
        tx = f'M33PROFILE|1|STOP|nonce={NONCE}\n'.encode()
        rx_path, tx_path = folder / f'{role}.rx.bin', folder / f'{role}.tx.bin'
        rx_path.write_bytes(rx)
        tx_path.write_bytes(tx)
        transcript.append(f'{role}: {rx.decode().strip()}')
        evidence['uart_capture'][role] = {
            'role': role, 'status': 'COMPLETE',
            'boundary': 'AFTER_ORIGINAL_PREPROBE_CLEAR_THROUGH_CLOSE',
            'errors': [], 'unconsumed_bytes': 0, 'reader_joined': True,
            'closed': True, 'last_byte_newline': True, 'delivered_bytes': len(rx),
            'rx': {'path': rx_path.name, 'sha256': subject.file_digest(rx_path), 'bytes': len(rx)},
            'tx': {'path': tx_path.name, 'sha256': subject.file_digest(tx_path),
                   'bytes': len(tx), 'returned_bytes': len(tx)},
            'events': [{'kind': 'original_preprobe_clear'},
                       {'kind': 'write', 'requested': len(tx), 'returned': len(tx)}],
        }
        for initialized in ([False, True, True, True, True]
                            if role == 'watcher' else [False, True, True]):
            receipt = {'status': 'PASS', 'transport': dict(TRANSPORT),
                       'probe_sha256': probe, 'initialized': initialized,
                       'cpu_identity_verified': initialized,
                       'target_uid_sha256': str(index + 5) * 64 if initialized else None,
                       'session_close': {'status': 'PASS', 'operations': []}}
            evidence['debug_sessions'].append(write_json(
                folder / f'debug-{len(evidence["debug_sessions"])}.json', receipt
            ))
    log = folder / 'transcript.log'
    log.write_text('\n'.join(transcript) + '\n', encoding='ascii')
    evidence['transcript'] = {'path': log.name, 'sha256': subject.file_digest(log)}
    readback = {'status': 'PASS', 'role': 'watcher', 'probe_sha256': '4' * 64,
                'image_sha256': 'c' * 64, 'pre_state': 'SLEEPING', 'post_state': 'RUNNING',
                'resumed': True, 'restored': True,
                'ranges': [{'start': 0, 'length': 16, 'status': 'PASS'}]}
    evidence['exact_program']['watcher'] = {
        'readback': write_json(folder / 'original.readback.json', readback)
    }
    evidence['post_reset_watcher_readback'] = {
        'status': 'PASS', 'calls': 1, 'additional_reset_calls': 0,
        'additional_program_calls': 0, 'additional_START_calls': 0,
        'original_program_receipt_replaced': False, 'readback_binding_restored': True,
        'idle': {'status': 'PASS', 'before': idle(), 'after': idle()},
        'session': evidence['debug_sessions'][-1],
        'readback': write_json(folder / 'post.readback.json', readback),
    }
    return evidence


class TransportEvidenceTests(unittest.TestCase):
    """! @brief 정상 파일과 하나씩 훼손한 증거를 구분합니다. """
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='m33-profile-transport-')
        self.folder = Path(self.temporary.name)
        self.evidence = make_bundle(self.folder)
        self.selection = patch.object(subject, 'transport_module', return_value=SimpleNamespace(
            validate_descriptor=lambda value: None
        ))
        self.selection.start()

    def tearDown(self):
        self.selection.stop()
        self.temporary.cleanup()

    def check(self):
        return subject.validate_evidence(self.folder / 'phase.json', self.evidence, TRANSPORT)

    def test_complete_bundle_and_unique_phase_paths(self):
        self.assertEqual(self.check(), TRANSPORT)
        first = set(subject.extra_sidecars(self.folder / 'case.cycle-01.fresh.run'))
        second = set(subject.extra_sidecars(self.folder / 'case.cycle-01.fresh.retry-02.run'))
        self.assertEqual(len(first), 18)
        self.assertFalse(first & second)

    def test_raw_file_tamper_rejected(self):
        with (self.folder / 'client.rx.bin').open('ab') as stream:
            stream.write(b'lost\n')
        with self.assertRaisesRegex(ValueError, 'byte mismatch'):
            self.check()

    def test_unconsumed_uart_rejected(self):
        self.evidence['uart_capture']['watcher']['unconsumed_bytes'] = 1
        with self.assertRaisesRegex(ValueError, 'capture incomplete'):
            self.check()

    def test_rehashed_extra_protocol_line_rejected(self):
        record = self.evidence['uart_capture']['server']
        path = self.folder / record['rx']['path']
        with path.open('ab') as stream:
            stream.write(b'M33PROFILE|1|FAIL|reason=unexpected\n')
        record['rx']['sha256'] = subject.file_digest(path)
        record['rx']['bytes'] = record['delivered_bytes'] = path.stat().st_size
        with self.assertRaisesRegex(ValueError, 'transcript mismatch'):
            self.check()

    def test_checked_close_failure_rejected_after_rehash(self):
        reference = self.evidence['debug_sessions'][2]
        path = self.folder / reference['path']
        receipt = json.loads(path.read_text())
        receipt['session_close']['status'] = 'FAIL'
        reference.update(write_json(path, receipt))
        with self.assertRaisesRegex(ValueError, 'close/identity mismatch'):
            self.check()

    def test_session_replay_rejected(self):
        self.evidence['debug_sessions'][1] = self.evidence['debug_sessions'][2]
        with self.assertRaisesRegex(ValueError, 'session replay'):
            self.check()

    def test_active_cpu_not_restored_rejected(self):
        reference = self.evidence['post_reset_watcher_readback']['readback']
        path = self.folder / reference['path']
        receipt = json.loads(path.read_text())
        receipt['post_state'] = 'HALTED'
        reference.update(write_json(path, receipt))
        with self.assertRaisesRegex(ValueError, 'watcher readback mismatch'):
            self.check()

    def test_partial_readback_ranges_rejected(self):
        reference = self.evidence['post_reset_watcher_readback']['readback']
        path = self.folder / reference['path']
        receipt = json.loads(path.read_text())
        receipt['ranges'] = []
        reference.update(write_json(path, receipt))
        with self.assertRaisesRegex(ValueError, 'full readback ranges mismatch'):
            self.check()

    def test_transport_drift_rejected(self):
        with self.assertRaisesRegex(ValueError, 'changed across phases'):
            subject.validate_evidence(self.folder / 'phase.json', self.evidence,
                                      dict(TRANSPORT, fixture_sha256='f' * 64))

    def test_default_cmsis_retains_original_shape(self):
        self.assertEqual(subject.validate_evidence(self.folder / 'legacy.json', {}),
                         {'kind': 'cmsis-dap-v2'})
        with self.assertRaisesRegex(ValueError, 'cannot carry DK'):
            subject.validate_evidence(self.folder / 'legacy.json', {'uart_capture': {}})


class IdleObservationTests(unittest.TestCase):
    """! @brief 추가 idle 관측은 원래 monitor·오류·binding 복구를 보존해야 합니다. """
    def test_same_monitor_and_original_return(self):
        observed = []
        monitor = object()
        target = object()
        expected = object()
        def audit(actual_target, actual_monitor, **kwargs):
            observed.append(('idle', actual_target, actual_monitor))
            return idle()
        def read(actual_target, ranges, *, monitor):
            observed.append(('read', actual_target, monitor))
            return expected
        diagnostics = SimpleNamespace(readback_ranges=read, verify_isolation=audit,
                                      RADIO_PASSIVE_SHORTS=0)
        observation = {'idle': {}}
        with subject.strict_watcher_readback(diagnostics, observation):
            self.assertIs(diagnostics.readback_ranges(target, [], monitor=monitor), expected)
        self.assertEqual([row[0] for row in observed], ['idle', 'read', 'idle'])
        self.assertTrue(all(row[1] is target and row[2] is monitor for row in observed))
        self.assertIs(diagnostics.readback_ranges, read)
        self.assertTrue(observation['readback_binding_restored'])

    def test_original_failure_propagates_and_binding_restores(self):
        def failed(*args, **kwargs):
            raise OSError('read failed')
        diagnostics = SimpleNamespace(readback_ranges=failed, verify_isolation=lambda *a, **k: idle(),
                                      RADIO_PASSIVE_SHORTS=0)
        observation = {'idle': {}}
        with self.assertRaisesRegex(OSError, 'read failed'):
            with subject.strict_watcher_readback(diagnostics, observation):
                diagnostics.readback_ranges(object(), [], monitor=object())
        self.assertIs(diagnostics.readback_ranges, failed)
        self.assertEqual(observation['idle']['status'], 'FAIL')
        self.assertTrue(observation['readback_binding_restored'])


class WatcherLifecycleTests(unittest.TestCase):
    """! @brief post-reset 관측은 별도 readback과 checked close 한 번만 인정합니다. """
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='m33-profile-watcher-')
        self.folder = Path(self.temporary.name)
        self.receipts = []
        self.calls = 0
        self.close_status = 'PASS'
        self.post_state = 'SLEEPING'
        self.audit_calls = 0
        self.audit_fail_at = None
        self.original_receipt = object()
        self.module = SimpleNamespace(descriptor=lambda: dict(TRANSPORT),
                                      session_receipts=lambda: list(self.receipts))
        self.transport_patch = patch.object(subject, 'transport_module', return_value=self.module)
        self.transport_patch.start()
        self.diagnostics = SimpleNamespace(readback_ranges=lambda *a, **k: [],
                                           verify_isolation=self.audit, RADIO_PASSIVE_SHORTS=0)
        self.module_patch = patch.dict(sys.modules, {'m33_diagnostics': self.diagnostics})
        self.module_patch.start()
        boards = {role: {'uid': str(index + 1), 'probe_sha256': str(index + 2) * 64,
                         'vcom': f'COM{index + 1}', 'image': self.folder / f'{role}.hex'}
                  for index, role in enumerate(subject.ROLES)}
        self.context = subject.ProfileTransport(SimpleNamespace(), boards, self.folder / 'phase.run')

    def tearDown(self):
        self.module_patch.stop()
        self.transport_patch.stop()
        self.temporary.cleanup()

    def audit(self, *args, **kwargs):
        self.audit_calls += 1
        if self.audit_calls == self.audit_fail_at:
            raise RuntimeError('idle failed')
        return idle()

    def readback(self, identities, hashes, images, sidecars):
        self.calls += 1
        self.diagnostics.readback_ranges(object(), [], monitor=object())
        record = {'status': 'PASS', 'pre_state': 'RUNNING', 'post_state': self.post_state,
                  'resumed': True, 'restored': self.post_state in subject.ACTIVE}
        write_json(sidecars['watcher']['readback'], record)
        self.receipts.append({'status': 'PASS', 'transport': dict(TRANSPORT),
                              'probe_sha256': '4' * 64, 'initialized': True,
                              'cpu_identity_verified': True, 'target_uid_sha256': '7' * 64,
                              'session_close': {'status': self.close_status}})
        return {'watcher': record}, self.original_receipt

    def test_success_is_one_separate_observation(self):
        self.context.observe_watcher(self.readback)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.context.observation['status'], 'PASS')
        self.assertFalse(self.context.observation['original_program_receipt_replaced'])
        self.assertEqual(self.context.session_index, 0)
        self.assertEqual(self.context.observation['additional_reset_calls'], 0)

    def test_duplicate_refused_before_any_extra_access(self):
        self.context.observe_watcher(self.readback)
        with self.assertRaisesRegex(ValueError, 'repeated or late'):
            self.context.observe_watcher(self.readback)
        self.assertEqual(self.calls, 1)

    def test_failed_close_does_not_become_pass(self):
        self.close_status = 'FAIL'
        with self.assertRaisesRegex(ValueError, 'checked close incomplete'):
            self.context.observe_watcher(self.readback)
        self.assertEqual(self.context.observation['status'], 'FAIL')

    def test_halted_cpu_does_not_become_active_restoration(self):
        self.post_state = 'HALTED'
        with self.assertRaisesRegex(ValueError, 'CPU restoration failed'):
            self.context.observe_watcher(self.readback)

    def test_pre_idle_failure_restores_binding_without_readback(self):
        self.audit_fail_at = 1
        original = self.diagnostics.readback_ranges
        with self.assertRaisesRegex(RuntimeError, 'idle failed'):
            self.context.observe_watcher(self.readback)
        self.assertIs(self.diagnostics.readback_ranges, original)
        self.assertEqual(self.audit_calls, 1)
        self.assertTrue(self.context.observation['readback_binding_restored'])

    def test_post_idle_failure_restores_binding_without_receipt(self):
        self.audit_fail_at = 2
        original = self.diagnostics.readback_ranges
        with self.assertRaisesRegex(RuntimeError, 'idle failed'):
            self.context.observe_watcher(self.readback)
        self.assertIs(self.diagnostics.readback_ranges, original)
        self.assertEqual(self.receipts, [])
        self.assertTrue(self.context.observation['readback_binding_restored'])


class FakeSerial:
    """! @brief 실제 장치 없이 byte별 도착과 timeout을 제공하는 수신 fixture입니다. """
    def __init__(self):
        self.timeout, self.write_timeout = 0.05, 5.0
        self.is_open = True
        self.queue = deque()
        self.condition = threading.Condition()
        self.read_sizes = []

    @property
    def in_waiting(self):
        with self.condition:
            return len(self.queue)

    def read(self, size):
        self.read_sizes.append(size)
        with self.condition:
            if not self.queue:
                self.condition.wait(self.timeout)
            return bytes(self.queue.popleft() for _ in range(min(size, len(self.queue))))

    def feed(self, data):
        with self.condition:
            self.queue.extend(data)
            self.condition.notify_all()

    def reset_input_buffer(self):
        with self.condition:
            self.queue.clear()

    def write(self, payload):
        return len(payload)

    def close(self):
        self.is_open = False
        with self.condition:
            self.condition.notify_all()


class CaptureTests(unittest.TestCase):
    """! @brief 비동기 RX 손실·지연·닫기 경계를 순수 serial fixture로 확인합니다. """
    def test_delayed_fragments_are_preserved_without_256_byte_wait(self):
        with tempfile.TemporaryDirectory(prefix='m33-profile-capture-') as temporary:
            real = FakeSerial()
            capture = CapturePort(real, 'server', Path(temporary) / 'phase.run')
            capture.reset_input_buffer()
            capture.write(b'PROBE\n')
            real.feed(b'REA')
            timer = threading.Timer(0.06, lambda: real.feed(b'DY\n'))
            timer.start()
            received = bytearray()
            deadline = time.monotonic() + 1.0
            while not received.endswith(b'\n') and time.monotonic() < deadline:
                received.extend(capture.readline())
            timer.join()
            capture.close()
            self.assertEqual(bytes(received), b'READY\n')
            self.assertEqual(capture.receipt()['status'], 'COMPLETE')
            self.assertEqual(real.read_sizes[0], 1)
            self.assertEqual((Path(temporary) / 'phase.server.rx.bin').read_bytes(), b'READY\n')

    def test_undelivered_raw_bytes_remain_incomplete(self):
        with tempfile.TemporaryDirectory(prefix='m33-profile-capture-') as temporary:
            real = FakeSerial()
            capture = CapturePort(real, 'watcher', Path(temporary) / 'phase.run')
            capture.reset_input_buffer()
            real.feed(b'UNCONSUMED\n')
            deadline = time.monotonic() + 1.0
            while capture.read_bytes == 0 and time.monotonic() < deadline:
                time.sleep(0.005)
            capture.close()
            self.assertEqual(capture.receipt()['status'], 'INCOMPLETE')


if __name__ == '__main__':
    unittest.main()
