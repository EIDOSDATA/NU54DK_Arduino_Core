"""! @brief native 장치 없이 명시 transport의 endpoint 경계를 검사합니다. """

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import ble_pair_hil_common as common
import m31_ble_capability_run as m31
import m32_ble_capability_run as m32


class EndpointTransportTests(unittest.TestCase):
    """! @brief 기존 CMSIS 출력과 명시 J-Link의 무 MSD 결합을 구분합니다. """

    def setUp(self):
        """! @brief 실제 fixture·USB·DLL과 무관한 작은 값만 준비합니다. """
        self.descriptor = {
            "kind": "jlink-swd", "fixture_sha256": "a" * 64,
            "dll_sha256": "b" * 64, "board": "nrf54l15dk",
        }
        self.volume = SimpleNamespace(root=Path("D:/"), details="synthetic")
        self.legacy = common.RoleEndpoint("abcd", self.volume, "COM1")
        self.jlink = common.RoleEndpoint("1057707567", None, "COM24", dict(self.descriptor))

    def test_legacy_public_shape_unchanged(self):
        self.assertEqual(common.public_endpoint(self.legacy), {
            "probe_sha256": common.probe_sha256("abcd"),
            "msd_root": str(self.volume.root), "uart_port": "COM1",
        })

    def test_jlink_public_no_fake_MSD(self):
        self.assertEqual(common.public_endpoint(self.jlink), {
            "probe_sha256": common.probe_sha256("1057707567"),
            "msd_root": None, "uart_port": "COM24", "transport": self.descriptor,
        })

    def test_mixed_transport_and_fixture_rejected(self):
        other = dict(self.descriptor, fixture_sha256="c" * 64)
        second = common.RoleEndpoint("1057715090", None, "COM19", other)
        for pair in [(self.legacy, self.jlink), (self.jlink, second)]:
            with self.subTest(pair=pair), self.assertRaises(common.BlePairHilFailure):
                common.validate_pair_identity(*pair)

    def test_unknown_descriptor_and_fake_MSD_rejected(self):
        values = [
            common.RoleEndpoint("1", self.volume, "COM2", self.descriptor),
            common.RoleEndpoint("1", None, "COM2"),
            common.RoleEndpoint("1", None, "COM2", {"kind": "jlink-swd"}),
            common.RoleEndpoint("1", None, "COM2", dict(self.descriptor, dll_sha256=1)),
        ]
        for endpoint in values:
            with self.subTest(endpoint=endpoint), self.assertRaises(common.BlePairHilFailure):
                common.public_endpoint(endpoint)

    def test_distinct_board_and_port_required_without_MSD(self):
        valid = common.RoleEndpoint("1057715090", None, "COM19", self.descriptor)
        common.validate_pair_identity(self.jlink, valid)
        for board, port in [(self.jlink.board_id, "COM19"), (valid.board_id, "com24")]:
            repeated = common.RoleEndpoint(board, None, port, self.descriptor)
            with self.subTest(board=board, port=port), self.assertRaises(common.BlePairHilFailure):
                common.validate_pair_identity(self.jlink, repeated)
        repeated_volume = common.RoleEndpoint("ef01", self.volume, "COM2")
        with self.assertRaises(common.BlePairHilFailure):
            common.validate_pair_identity(self.legacy, repeated_volume)

    def test_selected_discovery_no_DAP_fallback(self):
        selected = {"board_id": self.jlink.board_id, "volume": None,
                    "port_name": self.jlink.port_name, "transport": self.descriptor}
        selector = SimpleNamespace(resolve_endpoint=mock.Mock(return_value=selected))
        digest = common.probe_sha256(self.jlink.board_id)
        ports = object()
        with mock.patch.object(common, "probe_transport", return_value=selector), \
                mock.patch.object(common, "read_details") as details, \
                mock.patch.object(m31, "read_details") as details31, \
                mock.patch.object(m32, "read_details") as details32:
            endpoint = common.discover_endpoint_sha256(digest, None, "auto", ports)
            self.assertEqual(endpoint, self.jlink)
            self.assertEqual(m31.discover(digest, ports), (self.jlink.board_id, None, "COM24"))
            self.assertEqual(m32.discover_live(digest, ports), (self.jlink.board_id, None, "COM24"))
            details.assert_not_called()
            details31.assert_not_called()
            details32.assert_not_called()

    def test_invalid_selected_mapping_never_falls_back(self):
        selected = {"board_id": "1057715090", "volume": None,
                    "port_name": "COM24", "transport": self.descriptor}
        selector = SimpleNamespace(resolve_endpoint=mock.Mock(return_value=selected))
        with mock.patch.object(common, "probe_transport", return_value=selector), \
                mock.patch.object(common, "read_details") as details:
            with self.assertRaises(common.BlePairHilFailure):
                common.discover_endpoint_sha256(
                    common.probe_sha256(self.jlink.board_id), None, "auto", object())
            details.assert_not_called()

    def test_default_discovery_uses_original_CMSIS_path(self):
        selector = SimpleNamespace(resolve_endpoint=mock.Mock(return_value=None))
        details = "Target Detect: " + common.DAPLINK_TARGET + "\nUnique ID: abcd\n"
        with mock.patch.object(common, "probe_transport", return_value=selector), \
                mock.patch.object(common, "read_details", return_value=details), \
                mock.patch.object(common, "find_serial_port", return_value="COM1"):
            endpoint = common.discover_endpoint_sha256(
                common.probe_sha256("abcd"), "D:/", "COM1", object())
        self.assertEqual(endpoint.board_id, "abcd")
        self.assertIsNone(endpoint.transport)
        self.assertEqual(endpoint.volume.details, details)

    def test_three_board_validation_keeps_identity_guards(self):
        for name in ["m28_ble_3board", "m29_ble_multi", "m30_ble_multi"]:
            module = importlib.import_module(name)
            endpoints = {role: common.RoleEndpoint(str(100 + index), None, "COM" + str(index),
                                                  self.descriptor)
                         for index, role in enumerate(module.ROLES)}
            with self.subTest(module=name):
                module.validate_three_board_identity(endpoints)
                first, second = list(module.ROLES)[:2]
                endpoints[second] = endpoints[first]
                with self.assertRaises(common.BlePairHilFailure):
                    module.validate_three_board_identity(endpoints)

    def test_M30_serializers_preserve_legacy_and_declare_JLink(self):
        for suffix in ["pair", "oob", "bond", "profile", "dfu"]:
            module = importlib.import_module("m30_ble_" + suffix)
            with self.subTest(module=suffix):
                self.assertEqual(module.endpoint_evidence(self.legacy), {
                    "board_id_sha256": common.probe_sha256("abcd"), "volume": "D:", "port": "COM1",
                })
                self.assertEqual(module.endpoint_evidence(self.jlink), {
                    "board_id_sha256": common.probe_sha256(self.jlink.board_id),
                    "volume": None, "port": "COM24", "transport": self.descriptor,
                })


if __name__ == "__main__":
    unittest.main()
