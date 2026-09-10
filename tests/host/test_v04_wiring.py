"""! @brief 결선 누락·교차·시간 만료·외부 승인 누락으로 생기는 거짓 PASS를 거부합니다. """
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
import v04_fixture as fixture
import v04_wiring as wiring
import v04_wiring_run as runner
from v04_protocol import ProtocolError


class WiringTests(unittest.TestCase):
    def test_catalog_matches_connectors_and_only_two_crossovers(self):
        """! @brief 핀 개수만 보지 않고 connector 전사 및 제외 핀을 대조합니다. """
        catalog, selected = fixture.fixture_contract(501, catalog_path=wiring.CATALOG)
        pinmap = json.loads((ROOT / 'tests/hil/nu54dk/nu54dk_connector_pinmap.json').read_text())['connectors']
        expected = {'P0.' + str(i) for i in range(4)} | {'P1.' + str(i) for i in (4, 5, 6, 7, 10, 14)} | {'P2.' + str(i) for i in range(7)} | {'GND'}
        self.assertEqual(len(selected['links']), 18)
        for role in ('dut', 'peer'):
            self.assertEqual({row[role][2] for row in selected['links']}, expected)
            for connector, pin, net in (row[role] for row in selected['links']):
                actual = pinmap[connector][str(pin)]
                if actual.startswith('P') and '.' in actual:
                    port, number = actual.split('.')
                    actual = port + '.' + str(int(number))
                self.assertEqual(actual, net)
        self.assertEqual([(row['dut'][2], row['peer'][2]) for row in selected['links'] if row['dut'][2] != row['peer'][2]], [('P1.6', 'P1.7'), ('P1.7', 'P1.6')])
        with self.assertRaises(ProtocolError):
            fixture.fixture_contract(501)

    def test_every_open_short_wrong_cross_and_stale_state_is_rejected(self):
        """! @brief 모든 net의 단선과 다른 모든 net의 동반 LOW를 독립 주입합니다. """
        for net in range(17):
            good = [0x1FFFF ^ (1 << net), 0, 0x1FFFF, 0x1FFFF, 0xFFFFFFFF, 0, 0, 1]
            wiring.observed(good, low=net)
            for other in range(17):
                bad = good.copy()
                bad[0] ^= 1 << other
                with self.assertRaises(ProtocolError):
                    wiring.observed(bad, low=net)
            for field in range(1, 8):
                bad = good.copy()
                bad[field] ^= 1
                with self.assertRaises(ProtocolError):
                    wiring.observed(bad, low=net)
        with self.assertRaises(ProtocolError):
            wiring.observed([True] * 8)

    def test_current_catalog_confirmation_cannot_use_old_fixture(self):
        """! @brief 동일 image여도 다른 결선표의 승인과 만료 확인서는 거부합니다. """
        catalog, _ = fixture.fixture_contract(501, catalog_path=wiring.CATALOG)
        images = [{'role': role, 'core_revision': 'c' * 40, 'board_revision': catalog['board_revision'], 'sha256': str(role) * 64} for role in (1, 2)]
        uids = ['a' * 32, 'b' * 32]
        confirmation = fixture.confirmation_template(images, uids, 501, catalog_path=wiring.CATALOG)
        for key, value in confirmation.items():
            if type(value) is bool:
                confirmation[key] = True
        confirmation.update(confirmed_at_unix=1000, confirmed_by='Host mock only')
        fixture.validate_confirmation(confirmation, images, uids, 501, 1001, catalog_path=wiring.CATALOG)
        for key, value in (('catalog_sha256', hashlib.sha256(fixture.CATALOG.read_bytes()).hexdigest()),
                           ('fixture_id', 408), ('confirmed_at_unix', -1000), ('links_match_catalog', False)):
            bad = copy.deepcopy(confirmation)
            bad[key] = value
            with self.assertRaises(ProtocolError):
                fixture.validate_confirmation(bad, images, uids, 501, 1001, catalog_path=wiring.CATALOG)

    def test_failed_raw_is_saved_and_both_boards_stopped(self):
        """! @brief 첫 관측 실패에도 raw와 양쪽 cleanup을 남기며 다음 LOW를 시작하지 않습니다. """
        class Device:
            def __init__(self, role):
                self.image = {'role': role}
                self.calls = []
            def command(self, opcode, values=(), **kwargs):
                self.calls.append(opcode)
                if opcode == 48:
                    return [501, 10000, 17]
                if opcode == 49:
                    return [0, 0, 0, 0, 0xFFFFFFFF, 0, 0, 0]
                return [0, 0, 0x1FFFF, 0x1FFFF, 0xFFFFFFFF, 0, 0, 1]
        devices = [Device(1), Device(2)]
        rows = []
        with patch.object(fixture, 'validate_confirmation'), self.assertRaises(ProtocolError):
            wiring.run_confirmed(devices, [], [], {}, lambda key, row: rows.append(row), sleep=lambda _: None)
        self.assertEqual([row['status'] for row in rows], ['observation', 'observation', 'cleanup'])
        self.assertTrue(all(device.calls == [48, 51, 49] for device in devices))

    def test_selected_net_set_is_validated_before_device_access(self):
        """! @brief UARTE00 부분 결선 검사가 중복·범위 밖·부족한 net을 거부합니다. """
        for nets in ((10,), (10, 10), (10, 17), (10, True)):
            with self.subTest(nets=nets), self.assertRaises(ProtocolError):
                wiring.run_checks([], lambda *_: None, lambda: None, nets=nets,
                                  sleep=lambda _: None)
        self.assertEqual(wiring.UART00_NETS, (10, 12, 14, 15))

    def test_cli_requires_explicit_execution_and_ten_mhz(self):
        """! @brief 기본 실행은 무장치 preflight이며 확인서 없는 flash를 거부합니다. """
        args = ['--dut', 'a', '--peer', 'b', '--build-root', '.', '--pyocd', 'fake']
        self.assertFalse(runner.arguments(args).execute_fixture)
        for extra in (['--execute-fixture'], ['--swd-frequency-hz', '1000000']):
            with self.assertRaises(ProtocolError):
                runner.arguments(args + extra)

    def test_actual_cpp_pin_and_timeout_boundaries(self):
        """! @brief 펌웨어의 실제 순수 계약을 독립 static_assert로 컴파일합니다. """
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(compiler_command() + ['-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-I', str(ROOT / 'tests/zephyr/v04_pair_hil/src'), '-c',
                str(ROOT / 'tests/host/v04_common_wiring_main.cpp'), '-o', str(Path(folder) / 'wiring.o')],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
