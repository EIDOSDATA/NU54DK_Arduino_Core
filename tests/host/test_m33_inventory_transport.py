"""! @brief 장치 없이 DK inventory의 실제형 USB 결합과 matrix 무 MSD 준비를 검증합니다. """
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / 'tools/ci', ROOT / 'tools/bluetooth', ROOT / 'tests/hil/nu54dk'):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
import m33_w06_artifacts as artifacts
import m33_regression_run as runner
import m33_probe_transport as transport


REVISION = '1' * 40
JLINK = {'kind': 'jlink-swd', 'fixture_sha256': 'a' * 64,
         'dll_sha256': 'b' * 64, 'board': 'nrf54l15dk'}


class InventoryTransportTests(unittest.TestCase):
    """! @brief 원형 CMSIS 조건과 명시 DK의 strict schema를 별도로 검증합니다. """

    def setUp(self):
        self.ports = []
        self.pnp = []
        self.fixture = {'boards': []}
        self.rows = []
        for index in range(3):
            serial = str(1001 + index)
            raw = serial.zfill(12)
            app, aux = 'COM' + str(20 + index * 2), 'COM' + str(21 + index * 2)
            digest = hashlib.sha256(serial.encode()).hexdigest()
            self.fixture['boards'].append({'serial': serial, 'usb_serial': raw,
                'probe_sha256': digest, 'port': app})
            self.rows.append({'probe_sha256': digest, 'port': app, 'app': app,
                'aux': aux, 'volume': None, 'transport': dict(JLINK)})
            for port, interface in ((app, '02'), (aux, '00')):
                self.ports.append(SimpleNamespace(device=port, serial_number=raw,
                    vid=0x1366, pid=0x1069, hwid='USB VID:PID=1366:1069'))
                self.pnp.append({'DeviceID': port, 'Status': 'OK',
                    'PNPDeviceID': 'USB\\VID_1366&PID_1069&MI_' + interface + '\\synthetic'})
        self.plan = {'source': {
            'source_revision': REVISION, 'source_clean': True,
            'board_revision': '2' * 40, 'board_clean': True,
            'ncs_version': '3.4.0', 'ncs_revision': '3' * 40, 'ncs_clean': True,
            'zephyr_revision': '4' * 40, 'zephyr_clean': True, 'zephyr_patches': [],
            'toolchain_bundle_id': 'dcbdc366a1',
            'sdk_root': 'D:/w06/fake-sdk',
            'toolchain_root': 'D:/w06/fake-toolchain/dcbdc366a1/opt/zephyr-sdk',
            'lock_sha256': '5' * 64,
        }, 'campaigns': [{'id': 'm30_multi', 'roles': ['peripheral', 'mixed', 'central']}]}

    def inventory(self, rows=None):
        return artifacts.current_board_inventory(self.plan, lambda: self.rows if rows is None else rows)

    def test_live_exact_APP_AUX_without_pyserial_MI(self):
        value = artifacts.jlink_board_uart_channels(self.fixture['boards'][0], self.ports, self.pnp)
        self.assertEqual(value, {'port': 'COM20', 'app': 'COM20', 'aux': 'COM21'})

    def test_live_wrong_UID_VID_PID_port_and_count_rejected(self):
        for field, value in (('serial_number', '000000009999'), ('vid', 0x0D28),
                             ('pid', 0x0204), ('device', 'not-COM')):
            ports = copy.deepcopy(self.ports)
            setattr(ports[1], field, value)
            with self.subTest(field=field), self.assertRaises(artifacts.ArtifactFailure):
                artifacts.jlink_board_uart_channels(self.fixture['boards'][0], ports, self.pnp)
        for ports in (self.ports[1:], self.ports + [self.ports[0]]):
            with self.assertRaises(artifacts.ArtifactFailure):
                artifacts.jlink_board_uart_channels(self.fixture['boards'][0], ports, self.pnp)

    def test_live_wrong_or_ambiguous_CIM_interface_rejected(self):
        for field, value in (('Status', 'Error'), ('DeviceID', 'COM99'),
                            ('PNPDeviceID', 'USB\\VID_1366&PID_1069&MI_02\\synthetic'),
                            ('PNPDeviceID', 'USB\\VID_1366&PID_1069&MI_04\\synthetic')):
            pnp = copy.deepcopy(self.pnp)
            pnp[1][field] = value
            with self.subTest(value=value), self.assertRaises(artifacts.ArtifactFailure):
                artifacts.jlink_board_uart_channels(self.fixture['boards'][0], self.ports, pnp)
        with self.assertRaises(artifacts.ArtifactFailure):
            artifacts.jlink_board_uart_channels(self.fixture['boards'][0], self.ports,
                                                self.pnp + [self.pnp[0]])

    def test_live_fixed_APP_port_cannot_be_replaced_by_AUX(self):
        row = dict(self.fixture['boards'][0], port='COM21')
        with self.assertRaises(artifacts.ArtifactFailure):
            artifacts.jlink_board_uart_channels(row, self.ports, self.pnp)

    def test_explicit_discovery_has_no_MSD_fallback_or_probe_call(self):
        ports = SimpleNamespace(comports=lambda: self.ports)
        with mock.patch.object(transport, 'load_fixture', return_value=self.fixture), \
                mock.patch.object(transport, 'descriptor', return_value=JLINK), \
                mock.patch.object(transport, 'serial_pnp_snapshot', return_value=self.pnp), \
                mock.patch.object(artifacts.runpy, 'run_path', return_value={
                    'import_pyserial': lambda: (None, ports)}):
            rows = artifacts.discover_current_boards()
        self.assertEqual(rows, self.rows)
        encoded = json.dumps(rows)
        for row in self.fixture['boards']:
            self.assertNotIn(row['usb_serial'], encoded)

    def test_offline_typed_inventory_preserves_descriptor_and_three_roles(self):
        inventory = self.inventory()
        self.assertEqual(len(inventory['physical_slots']), 3)
        self.assertTrue(all(row['volume'] is None and row['transport'] == JLINK
                            for row in inventory['physical_slots']))
        boards = runner._board_inventory(inventory, REVISION, self.plan)['m30_multi']
        self.assertEqual(set(boards), {'peripheral', 'mixed', 'central'})
        self.assertTrue(all(row['transport'] == JLINK for row in boards.values()))

    def test_offline_mixed_descriptor_fake_MSD_and_incomplete_rows_rejected(self):
        for mutation in ('mixed', 'fixture', 'dll', 'volume', 'missing', 'extra', 'bad_COM'):
            rows = copy.deepcopy(self.rows)
            if mutation == 'mixed':
                rows[0].pop('transport')
                rows[0]['volume'] = 'Z:/'
            elif mutation in ('fixture', 'dll'):
                rows[0]['transport'][mutation + '_sha256'] = 'c' * 64
            elif mutation == 'volume':
                rows[0]['volume'] = 'Z:/'
            elif mutation == 'missing':
                rows[0].pop('aux')
            elif mutation == 'extra':
                rows[0]['raw_uid'] = 'forbidden'
            else:
                rows[0]['aux'] = 'com21'
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, artifacts.ArtifactFailure)):
                self.inventory(rows)

    def test_offline_consumer_rejects_missing_descriptor_and_shared_COM(self):
        for mutation in ('missing_descriptor', 'same_aux', 'wrong_fixture', 'two_boards'):
            inventory = self.inventory()
            slots = inventory['physical_slots']
            if mutation == 'missing_descriptor':
                slots[0].pop('transport')
            elif mutation == 'same_aux':
                slots[1]['aux'] = slots[0]['aux']
            elif mutation == 'wrong_fixture':
                slots[1]['transport']['fixture_sha256'] = 'c' * 64
            else:
                slots.pop()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                runner._board_inventory(inventory, REVISION, self.plan)

    def test_offline_consumer_rejects_same_board_for_two_roles(self):
        inventory = self.inventory()
        roles = inventory['campaign_bindings'][0]['roles']
        roles[1]['slot'] = roles[0]['slot']
        with self.assertRaisesRegex(ValueError, 'distinct physical'):
            runner._board_inventory(inventory, REVISION, self.plan)

    def test_CMSIS_inventory_keeps_original_shape_and_MSD(self):
        rows = copy.deepcopy(self.rows)
        for index, row in enumerate(rows):
            row.pop('transport')
            row['volume'] = chr(70 + index) + ':/'
        inventory = self.inventory(rows)
        self.assertTrue(all('transport' not in row and row['volume']
                            for row in inventory['physical_slots']))
        rows[0]['volume'] = None
        with self.assertRaises(artifacts.ArtifactFailure):
            self.inventory(rows)

    def arguments(self, boards):
        definition = runner.CAMPAIGNS['m30_multi']
        expected = {'id': 'm30_multi', 'roles': definition['roles'],
                    'minimum_cycles': 20, 'runner': {'path': definition['runner']}}
        with mock.patch.object(runner, '_artifact_path', side_effect=lambda root, campaign, name,
                               directory=False: root / campaign / name):
            return runner._prepared_arguments(expected, boards, Path('D:/w06/fake-artifacts'),
                Path('D:/w06/fake-output'), Path('D:/w06/fake-sdk'),
                Path('D:/w06/fake-toolchain'), REVISION)[1]

    def test_matrix_JLink_omits_only_volume_and_preserves_probe_port_flash(self):
        boards = runner._board_inventory(self.inventory(), REVISION, self.plan)['m30_multi']
        values = runner._argument_values(self.arguments(boards))
        self.assertFalse(any(option.endswith('-volume') for option in values))
        self.assertEqual(values['--flash-backend'], [['pyocd-sector']])
        for role, board in boards.items():
            self.assertEqual(values['--' + role + '-port'], [[board['port']]])
            self.assertEqual(values['--probe-' + role + '-sha256'], [[board['probe_sha256']]])

    def test_matrix_CMSIS_still_requires_volume(self):
        boards = runner._board_inventory(self.inventory(), REVISION, self.plan)['m30_multi']
        for index, row in enumerate(boards.values()):
            row.pop('transport')
            row['volume'] = chr(70 + index) + ':/'
        values = runner._argument_values(self.arguments(boards))
        self.assertTrue(all('--' + role + '-volume' in values for role in boards))
        boards['central']['volume'] = None
        with self.assertRaisesRegex(ValueError, 'lacks central.volume'):
            self.arguments(boards)

    def test_matrix_rejects_mixed_transport_and_fake_MSD(self):
        for mutation in ('mixed', 'volume'):
            boards = runner._board_inventory(self.inventory(), REVISION, self.plan)['m30_multi']
            boards['central']['volume'] = 'Z:/'
            if mutation == 'mixed':
                boards['central'].pop('transport')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.arguments(boards)


if __name__ == '__main__':
    unittest.main()
