"""! @brief 명시적 DK profile의 전송·추가 관측·UART 원문을 원형 판정에 결합합니다. """
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from m33_profile_uart_capture import CaptureSerial

ROOT = Path(__file__).resolve().parents[3]
ROLES = ('server', 'client', 'watcher')
ACTIVE = {'RUNNING', 'SLEEPING'}
PROTOCOL = 'M33PROFILE|1|'


def transport_module():
    """! @brief 장치를 열지 않고 명시적 전송 선택 모듈만 불러옵니다. """
    directory = str(ROOT / 'tools/bluetooth')
    if directory not in sys.path:
        sys.path.insert(0, directory)
    import m33_probe_transport
    return m33_probe_transport


def descriptor():
    """! @brief 실행 시 선택한 전송을 원시 UID 없이 반환합니다. """
    return transport_module().descriptor()


def extra_sidecars(prefix: Path) -> list[Path]:
    """! @brief phase·retry prefix에 귀속한 새 원문·관측 파일을 미리 예약합니다. """
    paths = [prefix.with_suffix(f'.{role}.{direction}.bin')
             for role in ROLES for direction in ('rx', 'tx')]
    paths.append(prefix.with_suffix('.watcher-post-reset.readback.json'))
    paths.extend(prefix.with_suffix(f'.debug-{index:02d}.json')
                 for index in range(1, 12))
    return paths


def file_digest(path: Path) -> str:
    """! @brief 원문 파일의 실제 SHA-256을 계산합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def adjacent(parent: Path, reference: dict) -> Path:
    """! @brief 같은 phase 폴더의 일반 파일과 실제 byte hash만 허용합니다. """
    if (not isinstance(reference, dict)
            or not isinstance(reference.get('path'), str)
            or Path(reference['path']).name != reference['path']):
        raise ValueError('profile transport sidecar path invalid')
    path = parent / reference['path']
    if (path.is_symlink() or not path.is_file() or path.resolve().parent != parent.resolve()
            or file_digest(path) != reference.get('sha256')):
        raise ValueError('profile transport sidecar byte mismatch')
    return path


@contextmanager
def strict_watcher_readback(diagnostics, observation: dict):
    """! @brief 같은 raw reset monitor로 원형 HEX 읽기 전후 strict idle을 검사합니다. """
    original = diagnostics.readback_ranges

    def audited(target, ranges, *, monitor):
        """! @brief 원형 readback·CPU 복귀는 그대로 두고 한 번의 유휴 관측만 추가합니다. """
        if observation['idle']:
            raise ValueError('repeated post-reset watcher readback')
        row = {'status': 'FAIL'}
        observation['idle'] = row
        row['before'] = diagnostics.verify_isolation(
            target, monitor, allowed_shorts=diagnostics.RADIO_PASSIVE_SHORTS
        )
        value = original(target, ranges, monitor=monitor)
        row['after'] = diagnostics.verify_isolation(
            target, monitor, allowed_shorts=diagnostics.RADIO_PASSIVE_SHORTS
        )
        row['status'] = 'PASS'
        return value

    diagnostics.readback_ranges = audited
    try:
        yield
    finally:
        diagnostics.readback_ranges = original
        observation['readback_binding_restored'] = True


def session_pass(receipt: dict, expected_transport: dict, expected_probe: str) -> bool:
    """! @brief 실제 전송·신원·checked close를 완료한 세션만 인정합니다. """
    return (isinstance(receipt, dict) and receipt.get('status') == 'PASS'
            and receipt.get('probe_sha256') == expected_probe
            and receipt.get('transport') == expected_transport
            and receipt.get('session_close', {}).get('status') == 'PASS'
            and type(receipt.get('initialized')) is bool
            and (receipt['initialized'] is False
                 or (receipt.get('cpu_identity_verified') is True
                     and re.fullmatch(r'[0-9a-f]{64}',
                                      str(receipt.get('target_uid_sha256', ''))) is not None)))


class ProfileTransport:
    """! @brief 명시적 J-Link phase의 추가 증거를 하나의 기존 lock 구간에 결합합니다. """
    def __init__(self, serial, boards: dict, prefix: Path):
        self.transport = descriptor()
        if self.transport.get('kind') != 'jlink-swd':
            raise ValueError('profile DK transport must be explicitly selected')
        self.boards = boards
        self.prefix = prefix
        self.audit_start = len(transport_module().session_receipts())
        for path in extra_sidecars(prefix):
            if path.exists() or path.is_symlink():
                raise ValueError('existing profile transport sidecar')
        mappings = [{'role': role, 'port': boards[role]['vcom']} for role in ROLES]
        self.serial = CaptureSerial(serial, mappings, prefix)
        self.observation = {
            'status': 'NOT_RUN', 'calls': 0, 'idle': {},
            'additional_reset_calls': 0, 'additional_program_calls': 0,
            'additional_START_calls': 0, 'original_program_receipt_replaced': False,
            'readback_binding_restored': False,
        }
        self.session_index = None
        self.finished = False

    def observe_watcher(self, readback) -> None:
        """! @brief 마지막 watcher software reset 뒤 별도 full readback 한 번을 수행합니다. """
        observation = self.observation
        if observation['calls'] != 0 or self.finished:
            raise ValueError('repeated or late watcher observation')
        observation.update(calls=1, status='FAIL',
                           started_utc=datetime.now(timezone.utc).isoformat())
        module = transport_module()
        import m33_diagnostics as diagnostics
        before = len(module.session_receipts())
        board = self.boards['watcher']
        path = self.prefix.with_suffix('.watcher-post-reset.readback.json')
        try:
            with strict_watcher_readback(diagnostics, observation):
                records, _unused_original_receipt = readback(
                    {'watcher': board['uid']}, {'watcher': board['probe_sha256']},
                    {'watcher': board['image']}, {'watcher': {'readback': path}},
                )
            record = records.get('watcher', {})
            if (set(records) != {'watcher'} or record.get('status') != 'PASS'
                    or record.get('pre_state') not in ACTIVE
                    or record.get('post_state') not in ACTIVE
                    or record.get('resumed') is not True
                    or record.get('restored') is not True
                    or observation['idle'].get('status') != 'PASS'):
                raise ValueError('post-reset watcher image/idle/CPU restoration failed')
            receipts = module.session_receipts()[before:]
            if (len(receipts) != 1
                    or not session_pass(receipts[0], self.transport, board['probe_sha256'])
                    or receipts[0].get('initialized') is not True):
                raise ValueError('post-reset watcher checked close incomplete')
            self.session_index = before - self.audit_start
            observation['readback'] = {'path': path.name, 'sha256': file_digest(path)}
            observation['status'] = 'PASS'
        finally:
            observation['finished_utc'] = datetime.now(timezone.utc).isoformat()

    def finish(self) -> dict:
        """! @brief lock 해제 전에 모든 capture를 닫고 실제 세션 원문을 같은 폴더에 보존합니다. """
        if self.finished:
            raise ValueError('profile transport already finalized')
        self.finished = True
        result = {'transport': self.transport, 'uart_capture': self.serial.finish(),
                  'post_reset_watcher_readback': self.observation,
                  'debug_sessions': [], 'transport_capture_errors': []}
        receipts = transport_module().session_receipts()[self.audit_start:]
        for index, receipt in enumerate(receipts, 1):
            try:
                source = Path(receipt['path'])
                destination = self.prefix.with_suffix(f'.debug-{index:02d}.json')
                if (source.is_symlink() or not source.is_file()
                        or file_digest(source) != receipt['sha256']
                        or destination.exists() or destination.is_symlink()):
                    raise ValueError('session receipt changed or output occupied')
                with destination.open('xb') as stream:
                    stream.write(source.read_bytes())
                result['debug_sessions'].append({
                    'path': destination.name, 'sha256': file_digest(destination),
                })
            except (KeyError, OSError, TypeError, ValueError) as error:
                result['transport_capture_errors'].append(type(error).__name__)
        if self.session_index is not None:
            if self.session_index < len(result['debug_sessions']):
                self.observation['session'] = result['debug_sessions'][self.session_index]
            else:
                result['transport_capture_errors'].append('ObservationSessionMissing')
        return result


def validate_evidence(path: Path, evidence: dict,
                      expected_transport: dict | None = None) -> dict:
    """! @brief 원형 profile 판정에 더해 DK 전송·원문·관측 byte의 완전성을 검사합니다. """
    selected = evidence.get('transport', {'kind': 'cmsis-dap-v2'})
    transport_module().validate_descriptor(selected)
    if expected_transport is not None and selected != expected_transport:
        raise ValueError('profile transport changed across phases')
    extra = ('uart_capture', 'post_reset_watcher_readback', 'debug_sessions',
             'transport_capture_errors')
    if selected['kind'] == 'cmsis-dap-v2':
        if any(name in evidence for name in extra):
            raise ValueError('CMSIS profile cannot carry DK transport evidence')
        return selected
    parent = path.resolve().parent
    if evidence.get('transport_capture_errors') != []:
        raise ValueError('profile transport capture failed')
    captures = evidence.get('uart_capture')
    boards = evidence.get('boards', {})
    if not isinstance(captures, dict) or set(captures) != set(ROLES):
        raise ValueError('profile UART capture denominator')
    transcript = adjacent(parent, evidence.get('transcript')).read_bytes().decode('ascii')
    for role in ROLES:
        record = captures[role]
        if (record.get('role') != role or record.get('status') != 'COMPLETE'
                or record.get('boundary') != 'AFTER_ORIGINAL_PREPROBE_CLEAR_THROUGH_CLOSE'
                or record.get('errors') != [] or record.get('unconsumed_bytes') != 0
                or record.get('reader_joined') is not True
                or record.get('closed') is not True
                or record.get('last_byte_newline') is not True):
            raise ValueError('profile UART capture incomplete')
        rx = adjacent(parent, record.get('rx')).read_bytes()
        tx = adjacent(parent, record.get('tx')).read_bytes()
        events = record.get('events', [])
        writes = events[1:]
        if (not rx or not rx.endswith(b'\n')
                or len(rx) != record['rx'].get('bytes')
                or len(rx) != record.get('delivered_bytes')
                or len(tx) != record['tx'].get('bytes')
                or len(tx) != record['tx'].get('returned_bytes')
                or not events or events[0].get('kind') != 'original_preprobe_clear'
                or any(event.get('kind') != 'write'
                       or type(event.get('requested')) is not int
                       or event['requested'] <= 0
                       or event.get('returned') != event['requested'] for event in writes)
                or sum(event['requested'] for event in writes) != len(tx)):
            raise ValueError('profile UART raw byte denominator')
        actual = [f'{role}: {line.decode("ascii", errors="replace").strip()}'
                  for line in rx.splitlines() if line.startswith(PROTOCOL.encode())]
        expected = [line for line in transcript.splitlines()
                    if line.startswith(role + ': ')]
        if actual != expected:
            raise ValueError('profile raw UART/transcript mismatch')
        nonce = evidence.get('cleanup', {}).get(role, {}).get('nonce')
        stop = f'{PROTOCOL}STOP|nonce={nonce}\n'.encode()
        if tx.splitlines(keepends=True).count(stop) != 1:
            raise ValueError('profile UART STOP command denominator')
    sessions = evidence.get('debug_sessions')
    if not isinstance(sessions, list) or len(sessions) != 11:
        raise ValueError('profile debug session denominator')
    session_records = []
    seen = set()
    counts = {role: [0, 0] for role in ROLES}
    target_identities = {role: set() for role in ROLES}
    by_probe = {board.get('probe_sha256'): role for role, board in boards.items()}
    for reference in sessions:
        session_path = adjacent(parent, reference)
        if session_path in seen:
            raise ValueError('profile debug session replay')
        seen.add(session_path)
        receipt = json.loads(session_path.read_text(encoding='utf-8'))
        probe = receipt.get('probe_sha256')
        if probe not in by_probe or not session_pass(receipt, selected, probe):
            raise ValueError('profile debug session close/identity mismatch')
        counts[by_probe[probe]][int(receipt['initialized'])] += 1
        if receipt['initialized']:
            target_identities[by_probe[probe]].add(receipt['target_uid_sha256'])
        session_records.append(receipt)
    if counts != {'server': [1, 2], 'client': [1, 2], 'watcher': [1, 4]}:
        raise ValueError('profile debug session role denominator')
    if (any(len(values) != 1 for values in target_identities.values())
            or len(set().union(*target_identities.values())) != 3):
        raise ValueError('profile target UID changed or roles share a target')
    observation = evidence.get('post_reset_watcher_readback', {})
    if (observation.get('status') != 'PASS' or observation.get('calls') != 1
            or observation.get('additional_reset_calls') != 0
            or observation.get('additional_program_calls') != 0
            or observation.get('additional_START_calls') != 0
            or observation.get('original_program_receipt_replaced') is not False
            or observation.get('readback_binding_restored') is not True
            or observation.get('idle', {}).get('status') != 'PASS'
            or observation.get('session') not in sessions):
        raise ValueError('profile post-reset watcher observation incomplete')
    observed_session = session_records[sessions.index(observation['session'])]
    if (observed_session['probe_sha256'] != boards['watcher']['probe_sha256']
            or observed_session['initialized'] is not True):
        raise ValueError('profile watcher observation session mismatch')
    for position in ('before', 'after'):
        idle = observation['idle'].get(position, {})
        if (idle.get('cpu') != 'HALTED' or idle.get('radio_state') != 0
                or idle.get('reset_observed') is not False
                or idle.get('read_only') is not True):
            raise ValueError('profile watcher strict idle mismatch')
    readback_path = adjacent(parent, observation.get('readback'))
    readback = json.loads(readback_path.read_text(encoding='utf-8'))
    original_reference = evidence.get('exact_program', {}).get('watcher', {}).get('readback')
    if (original_reference == observation['readback']
            or readback.get('status') != 'PASS' or readback.get('role') != 'watcher'
            or readback.get('probe_sha256') != boards['watcher']['probe_sha256']
            or readback.get('image_sha256') != boards['watcher']['image_sha256']
            or readback.get('pre_state') not in ACTIVE
            or readback.get('post_state') not in ACTIVE
            or readback.get('resumed') is not True or readback.get('restored') is not True):
        raise ValueError('profile post-reset watcher readback mismatch')
    if original_reference is not None:
        original = json.loads(adjacent(parent, original_reference).read_text(encoding='utf-8'))
        if readback.get('ranges') != original.get('ranges'):
            raise ValueError('profile watcher full readback ranges mismatch')
    return selected
