"""! @brief DLL 없이 명시 fixture·프로세스 선택·실제형 USB mapping 경계를 시험합니다. """

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools/bluetooth/m33_probe_transport.py"


class ProbeTransportTests(unittest.TestCase):
    """! @brief 모든 OS 목록은 가짜 값이며 생성 파일은 D의 시험 폴더에만 둡니다. """

    def setUp(self):
        """! @brief 실제 프로세스의 transport 선택과 독립된 모듈을 생성합니다. """
        spec = importlib.util.spec_from_file_location("probe_transport_under_test", MODULE)
        self.transport = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.transport)
        self.environment = mock.patch.dict(os.environ, {}, clear=False)
        self.environment.start()
        for key in (self.transport.FIXTURE_ENV, self.transport.HASH_ENV, self.transport.AUDIT_ENV):
            os.environ.pop(key, None)
        self.temporary = tempfile.TemporaryDirectory(prefix="m33-transport-pure-", dir="D:/w06/tmp")
        self.folder = Path(self.temporary.name).resolve()
        self.assertTrue(self.folder.is_relative_to(Path("D:/w06").resolve()))
        self.path = self.folder / "fixture.json"
        self.dll = self.folder / "synthetic.dll"
        self.dll.write_bytes(b"synthetic DLL, never loaded")
        boards = []
        for index, serial in enumerate(("1057707567", "1057715090", "1057783094")):
            boards.append({"serial": serial, "usb_serial": serial.zfill(12),
                           "probe_sha256": hashlib.sha256(serial.encode("ascii")).hexdigest(),
                           "target_uid_sha256": str(index + 1) * 64,
                           "port": "COM" + str(20 + index), "vid": 0x1366,
                           "pid": 0x1069, "interface": "MI_02"})
        self.fixture = {"kind": "nu54-hil-jlink-fixture", "version": 1,
                        "board": "nrf54l15dk", "boards": boards,
                        "dll": {"path": str(self.dll),
                                "sha256": hashlib.sha256(self.dll.read_bytes()).hexdigest()}}
        self.port = SimpleNamespace(device="COM20", vid=0x1366, pid=0x1069,
                                    serial_number=boards[0]["usb_serial"], hwid="USB VID:PID=1366:1069")
        self.ports = SimpleNamespace(comports=mock.Mock(return_value=[self.port]))
        self.pnp = [{"DeviceID": "COM20", "Status": "OK",
                     "PNPDeviceID": "USB\\VID_1366&PID_1069&MI_02\\synthetic-child"}]

    def tearDown(self):
        """! @brief 검증한 D 시험 폴더만 정리하고 실제 환경 변수를 복원합니다. """
        self.environment.stop()
        self.temporary.cleanup()

    def select(self, fixture=None, path=None):
        """! @brief 합성 manifest의 실제 byte SHA를 환경 선택에 결합합니다. """
        path = path or self.path
        path.write_text(json.dumps(fixture or self.fixture), encoding="utf-8")
        os.environ[self.transport.FIXTURE_ENV] = str(path)
        os.environ[self.transport.HASH_ENV] = hashlib.sha256(path.read_bytes()).hexdigest()

    def resolve(self, digest=None, volume=None, port="auto"):
        """! @brief 실제 CIM 호출을 대체한 목록으로 중앙 resolver를 실행합니다. """
        with mock.patch.object(self.transport, "serial_pnp_snapshot", return_value=self.pnp):
            return self.transport.resolve_endpoint(
                digest or self.fixture["boards"][0]["probe_sha256"], volume, port, self.ports)

    def test_default_CMSIS_performs_no_endpoint_scan(self):
        self.assertEqual(self.transport.descriptor(), {"kind": "cmsis-dap-v2"})
        self.assertIsNone(self.resolve())
        self.ports.comports.assert_not_called()

    def test_partial_DK_role_set_uses_same_three_locks(self):
        """! @brief 한·두 역할 요청도 세 물리 보드의 공통 lock identity로 확장합니다. """
        self.select()
        for key, hashed in (("serial", False), ("probe_sha256", True)):
            expected = [row[key] for row in self.fixture["boards"]]
            for requested in (expected[:1], expected[:2], expected):
                self.assertEqual(self.transport.lock_identities(requested, hashed=hashed), expected)
            for requested in ([], ["unmapped"], expected + ["unmapped"]):
                with self.assertRaises(ValueError):
                    self.transport.lock_identities(requested, hashed=hashed)

    def test_default_lock_namespace_identity_is_unchanged(self):
        """! @brief 기본 CMSIS의 기존 lock 대상과 호출자 순서를 바꾸지 않습니다. """
        self.assertEqual(self.transport.lock_identities(["legacy-b", "legacy-a"]),
                         ["legacy-b", "legacy-a"])

    def test_default_selection_cannot_switch_to_JLink(self):
        self.assertIsNone(self.transport.load_fixture())
        self.select()
        with self.assertRaises(ValueError):
            self.transport.load_fixture()

    def test_selected_fixture_cannot_change_or_disappear(self):
        self.select()
        self.transport.load_fixture()
        first_path = os.environ[self.transport.FIXTURE_ENV]
        first_hash = os.environ[self.transport.HASH_ENV]
        self.select(path=self.folder / "other-fixture.json")
        with self.assertRaises(ValueError):
            self.transport.load_fixture()
        os.environ[self.transport.FIXTURE_ENV] = first_path
        os.environ[self.transport.HASH_ENV] = first_hash
        os.environ.pop(self.transport.FIXTURE_ENV)
        os.environ.pop(self.transport.HASH_ENV)
        with self.assertRaises(ValueError):
            self.transport.load_fixture()

    def test_environment_pair_and_byte_pin_required(self):
        for key, value in [(self.transport.FIXTURE_ENV, str(self.path)),
                           (self.transport.HASH_ENV, "a" * 64)]:
            with self.subTest(key=key):
                os.environ[key] = value
                with self.assertRaises(ValueError):
                    self.transport.load_fixture()
                os.environ.pop(key)
        self.select()
        self.path.write_bytes(self.path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            self.transport.load_fixture()

    def test_exact_three_and_unique_identity_required(self):
        invalid = []
        two = copy.deepcopy(self.fixture)
        two["boards"].pop()
        invalid.append(two)
        for key in ["serial", "usb_serial", "probe_sha256", "target_uid_sha256", "port"]:
            repeated = copy.deepcopy(self.fixture)
            repeated["boards"][1][key] = repeated["boards"][0][key]
            invalid.append(repeated)
        for fixture in invalid:
            with self.subTest(fixture=fixture):
                self.select(fixture)
                with self.assertRaises(ValueError):
                    self.transport.load_fixture()

    def test_fixture_schema_USB_and_hash_validation(self):
        for key, value in [("serial", "001057707567"), ("usb_serial", "１２３"),
                           ("probe_sha256", "0" * 64), ("target_uid_sha256", "invalid"),
                           ("vid", 0x0D28), ("pid", 0x0204), ("interface", "MI_00"),
                           ("port", "com20")]:
            fixture = copy.deepcopy(self.fixture)
            fixture["boards"][0][key] = value
            with self.subTest(key=key):
                self.select(fixture)
                with self.assertRaises(ValueError):
                    self.transport.load_fixture()

    def test_exact_mapping_accepts_pyserial_without_MI(self):
        self.select()
        value = self.resolve()
        self.assertEqual(value["board_id"], "1057707567")
        self.assertEqual(value["port_name"], "COM20")
        self.assertIsNone(value["volume"])
        self.assertEqual(value["transport"]["kind"], "jlink-swd")
        self.assertEqual(self.transport.reset_mode(), "pyocd-jlink-sw-reset")

    def test_wrong_live_USB_serial_interface_and_COM_rejected(self):
        self.select()
        for name, value in [("vid", 0x0D28), ("pid", 0x0204),
                            ("serial_number", "001057715090"), ("device", "COM99")]:
            original = getattr(self.port, name)
            with self.subTest(name=name):
                setattr(self.port, name, value)
                with self.assertRaises(ValueError):
                    self.resolve()
                setattr(self.port, name, original)
        for key, value in [("PNPDeviceID", "USB\\VID_1366&PID_1069&MI_00\\synthetic"),
                           ("Status", "Error"), ("DeviceID", "COM99")]:
            original = self.pnp[0][key]
            with self.subTest(key=key):
                self.pnp[0][key] = value
                with self.assertRaises(ValueError):
                    self.resolve()
                self.pnp[0][key] = original

    def test_unknown_probe_duplicate_port_and_MSD_rejected(self):
        self.select()
        for kwargs in [{"digest": "f" * 64}, {"volume": "D:/"}, {"port": "COM99"}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.resolve(**kwargs)
        self.ports.comports.return_value = [self.port, self.port]
        with self.assertRaises(ValueError):
            self.resolve()

    def test_canonical_serial_and_descriptor_are_strict(self):
        self.assertEqual(self.transport.canonical_serial("001057707567"), "1057707567")
        for raw in ["", "0", " 1", "1x", "１２３", "4294967296", "0" * 13]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.transport.canonical_serial(raw)
        for value in [{"kind": "jlink-swd"}, {"kind": "cmsis-dap-v2", "fake": True}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.transport.validate_descriptor(value)


if __name__ == "__main__":
    unittest.main()
