"""! @brief 원형 Host 분모와 별도로 실제 endpoint 형태와 legacy raw 재검증을 검사합니다. """
from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/bluetooth'))
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
import m33_regression as contract
import m33_regression_run as runner

TRANSPORT = {'kind': 'jlink-swd', 'fixture_sha256': 'a' * 64,
             'dll_sha256': 'b' * 64, 'board': 'nrf54l15dk'}
REVISION = 'a' * 40
ROLES = ('peripheral', 'mixed', 'central')


def endpoints(jlink=True):
    """! @brief 원시 UID 없는 세 역할의 서로 다른 endpoint를 만듭니다. """
    return {role: {
        'probe_sha256': hashlib.sha256(role.encode()).hexdigest(),
        'msd_root': None if jlink else f'D:/{role}', 'uart_port': f'COM{index + 1}',
        **({'transport': dict(TRANSPORT)} if jlink else {}),
    } for index, role in enumerate(ROLES)}


def multi_fixture(folder, campaign):
    """! @brief 두 multi protocol의 실제 20 nonce 원문을 byte 파일로 생성합니다. """
    protocol = importlib.import_module(campaign.replace('_multi', '_ble_multi_protocol'))
    expected = {'id': campaign, **contract.CAMPAIGNS[campaign]}
    nonces = tuple(f'{index:032x}' for index in range(protocol.CYCLE_COUNT))
    transcripts, parsed = {}, {}
    for role in ROLES:
        raw = ('\n'.join(protocol.expected_campaign_lines(role, nonces, REVISION)) + '\n').encode('ascii')
        path = folder / f'{role}.transcript.log'
        path.write_bytes(raw)
        transcripts[role] = {'name': path.name, 'size': len(raw), 'sha256': contract.digest(path)}
        parsed[role] = protocol.parse_role_campaign(raw, role, nonces, REVISION)
    cycles = []
    for index, nonce in enumerate(nonces):
        results, cleanup = {}, {}
        for role in ROLES:
            value = runner.asdict(parsed[role][index])
            cleanup[role] = {
                'active_links': value.pop('cleanup_active_links'),
                'pending_operations': value.pop('cleanup_pending_operations'),
                'buffers': value.pop('cleanup_buffers'), 'status': value.pop('cleanup_status'),
            }
            results[role] = value
        cycles.append({'cycle': index + 1, 'nonce': nonce, 'results': results, 'cleanup': cleanup})
    native = {
        'schema_version': 2, 'status': 'passed', 'core_revision': REVISION,
        'boards': endpoints(), 'images': {
            role: {'flash_sequence': 'pyocd-sector-no-reset', 'flash_bytes': '64',
                   'build_record': {'record_sha256': 'a' * 64}} for role in ROLES
        }, 'transcripts': transcripts, 'cycles': cycles,
        'termination': {'serial_closed': {role: True for role in ROLES}, 'all_serial_closed': True},
        'coverage': {'independent_sessions': 20},
    }
    path = folder / 'native.json'
    path.write_text(json.dumps(native), encoding='utf-8')
    return native, path, expected


class EndpointTransportTests(unittest.TestCase):
    """! @brief 명시 DK와 기존 CMSIS endpoint의 형태·신원·원문 경계를 검증합니다. """
    def test_original_cmsis_exact_fields_and_nonempty_msd_are_preserved(self):
        self.assertEqual(runner._validate_native_endpoint_transport(
            endpoints(False), ROLES, strict_legacy=True), {'kind': 'cmsis-dap-v2'})
        for mutation in ('missing', 'empty', 'none', 'extra'):
            with self.subTest(mutation=mutation):
                rows = endpoints(False)
                row = rows['central']
                if mutation == 'missing':
                    del row['msd_root']
                elif mutation == 'extra':
                    row['unexpected'] = True
                else:
                    row['msd_root'] = '' if mutation == 'empty' else None
                with self.assertRaises(ValueError):
                    runner._validate_native_endpoint_transport(rows, ROLES, strict_legacy=True)

    def test_jlink_requires_typed_no_msd_and_consistent_descriptor(self):
        self.assertEqual(runner._validate_native_endpoint_transport(
            endpoints(), ROLES, strict_legacy=True), TRANSPORT)
        for mutation in ('missing', 'mixed', 'volume', 'fixture', 'dll', 'board', 'extra'):
            with self.subTest(mutation=mutation):
                rows = endpoints()
                row = rows['central']
                if mutation == 'missing':
                    del row['transport']
                elif mutation == 'mixed':
                    row['transport'] = {'kind': 'cmsis-dap-v2'}
                elif mutation == 'volume':
                    row['msd_root'] = 'Z:/'
                elif mutation in ('fixture', 'dll'):
                    row['transport'][mutation + '_sha256'] = 'e' * 64
                elif mutation == 'board':
                    row['transport']['board'] = 'unknown'
                else:
                    row['cmsis_dap'] = 'v2-only'
                with self.assertRaises(ValueError):
                    runner._validate_native_endpoint_transport(rows, ROLES, strict_legacy=True)

    def test_jlink_rejects_duplicate_probes_ports_or_invalid_port(self):
        for mutation in ('probe', 'port', 'invalid_port'):
            with self.subTest(mutation=mutation):
                rows = endpoints()
                if mutation == 'probe':
                    rows['central']['probe_sha256'] = rows['mixed']['probe_sha256']
                elif mutation == 'port':
                    rows['central']['uart_port'] = rows['mixed']['uart_port']
                else:
                    rows['central']['uart_port'] = 'auto'
                with self.assertRaises(ValueError):
                    runner._validate_native_endpoint_transport(rows, ROLES, strict_legacy=True)

    def test_m28_debug_identity_is_preserved_as_declared_extra(self):
        rows = endpoints()
        for row in rows.values():
            row['debug_identity'] = {'source': 'pyocd-direct'}
        self.assertEqual(runner._validate_native_endpoint_transport(
            rows, ROLES, extra_fields=('debug_identity',)), TRANSPORT)
        del rows['central']['debug_identity']
        with self.assertRaises(ValueError):
            runner._validate_native_endpoint_transport(rows, ROLES, extra_fields=('debug_identity',))

    def test_m30_named_endpoints_use_same_typed_rule(self):
        rows = {role: {'board_id_sha256': row['probe_sha256'], 'volume': row['msd_root'],
                       'port': row['uart_port'], 'transport': row['transport']}
                for role, row in endpoints().items() if role != 'mixed'}
        roles = ('peripheral', 'central')
        self.assertEqual(runner._validate_native_endpoint_transport(
            rows, roles, fields=('board_id_sha256', 'volume', 'port')), TRANSPORT)
        for row in rows.values():
            del row['transport']
        with self.assertRaisesRegex(ValueError, 'explicit J-Link'):
            runner._validate_native_endpoint_transport(rows, roles,
                                                       fields=('board_id_sha256', 'volume', 'port'))

    def test_both_registered_multi_raw_validators_accept_complete_jlink_evidence(self):
        for campaign in ('m29_multi', 'm30_multi'):
            with self.subTest(campaign=campaign), tempfile.TemporaryDirectory() as temporary:
                native, path, expected = multi_fixture(Path(temporary), campaign)
                runner._validate_legacy_native_raw(native, path, expected, REVISION)
                native['boards'] = endpoints(False)
                runner._validate_legacy_native_raw(native, path, expected, REVISION)

    def test_jlink_does_not_relax_multi_raw_cleanup_or_cycle_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            native, path, expected = multi_fixture(Path(temporary), 'm29_multi')
            for mutation in ('cleanup', 'cycle', 'transport'):
                with self.subTest(mutation=mutation):
                    changed = copy.deepcopy(native)
                    if mutation == 'cleanup':
                        changed['cycles'][0]['cleanup']['central']['buffers'] = 1
                    elif mutation == 'cycle':
                        changed['cycles'].pop()
                    else:
                        changed['boards']['central']['transport']['dll_sha256'] = 'f' * 64
                    with self.assertRaises(ValueError):
                        runner._validate_legacy_native_raw(changed, path, expected, REVISION)


if __name__ == '__main__':
    unittest.main()
