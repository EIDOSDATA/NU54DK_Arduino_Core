"""! @brief 원형 Host 분모와 별도로 matrix 실행 직전 transport 결합을 검사합니다. """
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "tools/bluetooth", ROOT / "tests/hil/nu54dk"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
import m33_probe_transport as transport
import m33_regression_run as runner

REVISION = "1" * 40
JLINK = {"kind": "jlink-swd", "fixture_sha256": "a" * 64,
         "dll_sha256": "b" * 64, "board": "nrf54l15dk"}
CMSIS = {"kind": "cmsis-dap-v2"}


class ExecutionTransportTests(unittest.TestCase):
    """! @brief offline replay를 보존하면서 새 실행의 fixture 교체를 거부합니다. """

    def setUp(self):
        roles = ["peripheral", "mixed", "central"]
        self.plan = {"campaigns": [{"id": "m30_multi", "roles": roles}]}
        self.inventory = {
            "schema_version": 2, "kind": "m33_board_inventory",
            "source_revision": REVISION, "source_clean": True,
            "physical_slots": [],
            "campaign_bindings": [{"campaign_id": "m30_multi", "roles": [
                {"role": role, "slot": "slot" + str(index)}
                for index, role in enumerate(roles)
            ]}],
        }
        self.fixture = {"boards": []}
        for index, role in enumerate(roles):
            digest = hashlib.sha256(role.encode("ascii")).hexdigest()
            app, aux = "COM" + str(20 + index * 2), "COM" + str(21 + index * 2)
            self.inventory["physical_slots"].append({
                "slot": "slot" + str(index), "probe_sha256": digest,
                "port": app, "app": app, "aux": aux, "volume": None,
                "transport": dict(JLINK),
            })
            self.fixture["boards"].append({"probe_sha256": digest, "port": app})

    def legacy_inventory(self):
        """! @brief 같은 역할 표를 원형 CMSIS MSD inventory로 변환합니다. """
        value = copy.deepcopy(self.inventory)
        for index, row in enumerate(value["physical_slots"]):
            del row["transport"]
            row["volume"] = "D:/probe" + str(index)
        return value

    def test_live_matching_typed_and_legacy(self):
        with mock.patch.object(transport, "descriptor", return_value=JLINK), \
                mock.patch.object(transport, "load_fixture", return_value=self.fixture):
            runner._validate_execution_inventory_transport(
                self.inventory, REVISION, self.plan)
        with mock.patch.object(transport, "descriptor", return_value=CMSIS), \
                mock.patch.object(transport, "load_fixture", side_effect=AssertionError):
            runner._validate_execution_inventory_transport(
                self.legacy_inventory(), REVISION, self.plan)

    def test_live_mismatched_backend_fixture_and_dll(self):
        cases = [(self.inventory, CMSIS), (self.legacy_inventory(), JLINK),
                 (self.inventory, dict(JLINK, fixture_sha256="c" * 64)),
                 (self.inventory, dict(JLINK, dll_sha256="c" * 64))]
        for inventory, selected in cases:
            with self.subTest(selected=selected), \
                    mock.patch.object(transport, "descriptor", return_value=selected), \
                    mock.patch.object(transport, "load_fixture", side_effect=AssertionError), \
                    self.assertRaises(ValueError):
                runner._validate_execution_inventory_transport(
                    inventory, REVISION, self.plan)

    def test_live_probe_and_app_binding_before_programming(self):
        for mutation in ("probe", "port"):
            inventory = copy.deepcopy(self.inventory)
            row = inventory["physical_slots"][2]
            if mutation == "probe":
                row["probe_sha256"] = "d" * 64
            else:
                row["port"] = row["app"] = "COM99"
            with self.subTest(mutation=mutation), \
                    mock.patch.object(transport, "descriptor", return_value=JLINK), \
                    mock.patch.object(transport, "load_fixture", return_value=self.fixture), \
                    self.assertRaises(ValueError):
                runner._validate_execution_inventory_transport(
                    inventory, REVISION, self.plan)

    def test_offline_inventory_does_not_read_selection(self):
        with mock.patch.object(transport, "descriptor", side_effect=AssertionError), \
                mock.patch.object(transport, "load_fixture", side_effect=AssertionError):
            result = runner._board_inventory(self.inventory, REVISION, self.plan)
        self.assertEqual(set(result["m30_multi"]), {"peripheral", "mixed", "central"})

    def test_matrix_transport_failure_precedes_preparation(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with mock.patch.object(runner, "_git_identity", return_value=(REVISION, True)), \
                    mock.patch.object(runner, "read_json", return_value=self.inventory), \
                    mock.patch.object(runner, "CAMPAIGN_REGISTRIES", {"field": {"id": {}}}), \
                    mock.patch.object(runner, "_matrix_session", return_value=(output / "session.json", {})), \
                    mock.patch.object(runner, "_matrix_attempt_numbers", return_value=[]), \
                    mock.patch.object(runner, "campaign_plan", return_value=self.plan), \
                    mock.patch.object(transport, "descriptor", return_value=CMSIS), \
                    mock.patch.object(runner, "prepare_execution_spec") as prepare, \
                    mock.patch.object(runner, "execute_campaign_spec") as execute, \
                    self.assertRaises(ValueError):
                runner._execute_campaign_matrix(output / "inventory.json", output,
                                                output, output, output)
            prepare.assert_not_called()
            execute.assert_not_called()
            self.assertEqual(list(output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
