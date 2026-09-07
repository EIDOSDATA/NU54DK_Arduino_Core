"""! @brief 고정 세션의 만료·단절과 실제 GPIO 관측 오류가 PASS가 되지 않는지 검사합니다. """
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
import v04_common_gpio as gpio
import v04_common_session as common
import v04_common_run as runner
from v04_protocol import ProtocolError


class CommonTests(unittest.TestCase):
    def inputs(self):
        catalog = json.loads(common.CATALOG.read_text(encoding='utf-8'))
        images = [{'role': role, 'board_revision': catalog['board_revision'], 'core_revision': 'c' * 40,
                   'symbols': {'v04_identity': 0x20000000}} for role in (1, 2)]
        uids = ['a' * 32, 'b' * 32]
        grant = {'type': 'v04-fixed-common-harness-session', 'catalog_sha256': hashlib.sha256(common.CATALOG.read_bytes()).hexdigest(),
                 'board_revision': catalog['board_revision'], 'uid_sha256': [hashlib.sha256(uid.encode()).hexdigest() for uid in uids],
                 'allowed_fixture_ids': list(common.ALLOWED), 'confirmed_at_unix': 1000, 'expires_at_unix': 4000,
                 'confirmed_by': 'Host mock only', 'user_condition_reply': 'mock', 'user_maintain_reply': 'mock', 'session_id': 'mock'}
        for key in ('maintain_harness_until_end', 'notify_before_usb_wiring_switch_changes',
                    'dap_uart_disconnected_both', 'swd_connected_both', 'power_rails_not_joined',
                    'equal_io_voltage_confirmed', 'common_ground_confirmed', 'links_match_catalog',
                    'pullups_match_catalog', 'extra_outputs_disconnected'):
            grant[key] = True
        return grant, images, uids

    def test_deadline_conditions_identity_and_scope_fail_closed(self):
        grant, images, uids = self.inputs()
        common.validate(grant, images, uids, 502, now=3999)
        for key, value in (('confirmed_at_unix', 4001), ('expires_at_unix', 3999),
                           ('expires_at_unix', 1000 + common.MAX_SECONDS + 1),
                           ('expires_at_unix', float('nan')), ('links_match_catalog', 1),
                           ('maintain_harness_until_end', False), ('catalog_sha256', 'old'),
                           ('user_maintain_reply', ''), ('allowed_fixture_ids', [501, 502, 301])):
            bad = copy.deepcopy(grant)
            bad[key] = value
            with self.assertRaises(ProtocolError):
                common.validate(bad, images, uids, 502, now=3999)
        for identifier in (101, 301, 408, 420, 430, 440, 999):
            with self.assertRaises(ProtocolError):
                common.validate(grant, images, uids, identifier, now=2000)
        bad_images = copy.deepcopy(images)
        bad_images[1]['core_revision'] = 'd' * 40
        with self.assertRaises(ProtocolError):
            common.validate(grant, bad_images, uids, 502, now=2000)

    def test_disconnection_latches_even_if_probe_reappears(self):
        grant, images, uids = self.inputs()
        available = []
        with patch.object(common.time, 'time', return_value=2000):
            continuity = common.Continuity(grant, images, uids, [], lambda: set(available), lambda *_: None, monotonic=lambda: 10)
            with self.assertRaises(ProtocolError):
                continuity.check(502)
            available[:] = uids
            with self.assertRaises(ProtocolError):
                continuity.check(502)

    def test_common_links_match_original_without_reinterpreting_legacy(self):
        catalog = json.loads(common.CATALOG.read_text(encoding='utf-8'))
        original = json.loads((common.CATALOG.parent / 'v04_common_fixture.json').read_text(encoding='utf-8'))
        self.assertEqual(catalog['fixtures'][0], original['fixtures'][0])
        self.assertEqual([row['id'] for row in catalog['fixtures']], list(common.ALLOWED))
        for row in catalog['fixtures']:
            self.assertEqual(row['links'], original['fixtures'][0]['links'])

    def test_raw_wrong_level_direction_error_or_count_cannot_pass(self):
        class Device:
            image = {'role': 1}
            words = [0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 10, 0, 0, 1, 0, 1]
            def command(self, *_args, **_kwargs):
                return self.words
        device = Device()
        for field in (0, 1, 2, 3, 8, 9, 11, 15):
            device.words = Device.words.copy()
            device.words[field] ^= 1
            saved = []
            with self.assertRaises(ProtocolError):
                gpio.level(device, lambda key, row: saved.append(row), 'mock', 0, 1, True)
            self.assertEqual(saved[0]['words'], device.words)

    def test_failed_case_still_stops_both_boards(self):
        class Device:
            def __init__(self, role):
                self.image = {'role': role}
                self.calls = []
            def command(self, opcode, *_args, **_kwargs):
                self.calls.append(opcode)
                if opcode == 64:
                    return [502, 10000]
                if opcode == 65:
                    return [gpio.NONE] + [0] * 15
                return [1]
        devices = [Device(1), Device(2)]
        saved = []
        with self.assertRaises(ProtocolError):
            gpio.gpio_case(devices, 1, 0, 1, lambda _: None, lambda key, row: saved.append(row))
        self.assertEqual([device.calls[-1] for device in devices], [65, 65])
        self.assertEqual(saved[-1]['status'], 'cleanup')
        self.assertTrue(all(row['stopped'] for row in saved[-1]['outcomes']))

    def test_channel_coverage_and_explicit_execution(self):
        rows = list(gpio.channel_vectors())
        self.assertEqual([(row[0], row[1]) for row in rows], [(20, i) for i in range(8)] + [(30, i) for i in range(4)])
        args = runner.arguments(['--dut', 'a', '--peer', 'b', '--build-root', '.', '--pyocd', 'fake', '--session-grant', 'fake'])
        self.assertFalse(args.execute_fixture)


if __name__ == '__main__':
    unittest.main()
