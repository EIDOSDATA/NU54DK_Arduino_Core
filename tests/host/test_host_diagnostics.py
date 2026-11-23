"""! @brief Host 장치 진단의 개인정보 경계와 실제 경로 결합을 검사합니다. """
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('host_doctor_test_builder', ROOT / 'tools/nu54-builder/src/nu54_builder.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
D = importlib.import_module(builder.implementation.__name__ + '.host_diagnostics')


class HostDiagnosticTests(unittest.TestCase):
    """! @brief 포트 열기나 보드 조작 없이 비식별 출력 계약을 검증합니다. """

    def test_windows_linux_and_macos_paths_are_not_raw_output(self):
        """! @brief 각 OS의 port 이름과 raw serial은 JSON에 남기지 않습니다. """
        for system, path, expected in (
            ('windows', 'COM12', 'windows_vcom'), ('linux', '/dev/ttyACM3', 'linux_acm'),
            ('linux', '/dev/ttyUSB2', 'linux_usb'), ('macos', '/dev/cu.usbmodem-secret', 'macos_serial'),
        ):
            with self.subTest(system=system, path=path):
                port = SimpleNamespace(device=path, serial_number='private-board-uid', vid=6421, pid=1)
                rows = D.serial_inventory([port], system)
                self.assertEqual(rows[0]['kind'], expected)
                self.assertEqual(len(rows[0]['serial_sha256']), 64)
                self.assertFalse(rows[0]['device_open_attempted'])
                text = json.dumps(rows)
                self.assertNotIn(path, text)
                self.assertNotIn('private-board-uid', text)

    def test_missing_serial_does_not_invent_stable_board_identity(self):
        """! @brief serial 없는 장치는 경로를 보드 고유 identity로 대신하지 않습니다. """
        rows = D.serial_inventory([SimpleNamespace(device='COM7')], 'windows')
        self.assertIsNone(rows[0]['serial_sha256'])
        self.assertEqual(rows[0]['permission_status'], 'NOT_VERIFIED_NO_DEVICE_OPEN')

    def test_linux_by_id_alias_joins_actual_target_when_symlink_available(self):
        """! @brief 실제 symlink target과 열거 장치의 관계를 raw 이름 없이 남깁니다. """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            device = root / 'ttyACM0'
            device.write_bytes(b'')
            by_id = root / 'by-id'
            by_id.mkdir()
            alias = by_id / 'usb-private-board-uid'
            try:
                alias.symlink_to(device)
            except OSError:
                self.skipTest('현재 Host에서 비관리자 symlink 생성이 허용되지 않습니다.')
            rows = D.serial_inventory([SimpleNamespace(device=str(device))], 'linux', by_id)
            self.assertEqual(rows[0]['by_id_path_sha256'], [D.identity_hash(str(alias))])
            self.assertNotIn('usb-private-board-uid', json.dumps(rows))


if __name__ == '__main__':
    unittest.main()
