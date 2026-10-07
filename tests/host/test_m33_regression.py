#!/usr/bin/env python3
"""! @brief 회귀 증거 oracle·자원·interop·3보드 soak의 허위 승격을 거부합니다. """
from __future__ import annotations

import copy
from contextlib import nullcontext
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("m33_regression", ROOT / "tools/bluetooth/m33_regression.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "tests/hil/nu54dk"))
import m33_regression_run as RUNNER
from m33_regression_run import validate_soak
from m32_regression_soak_run import _checkout_dirty

REVISION = "a" * 40
BINDING = MODULE.Binding(0, 1, "a" * 64, "b" * 64)
SECOND = MODULE.Binding(1, 1, "c" * 64, "d" * 64)


class RegressionTests(unittest.TestCase):
    """! @brief Host oracle 검사는 production 구현 또는 실물 실행 PASS로 표시하지 않습니다. """
    def test_snapshot_keeps_baseline_and_current_evidence_separate(self):
        """! @brief M28~M32 과거 PASS가 현재 33 family의 PASS가 되지 않습니다. """
        value = MODULE.snapshot()
        self.assertEqual("NOT_RUN", value["status"])
        self.assertEqual(33, len(value["families"]))
        self.assertEqual(8, len(value["resource_groups"]))
        self.assertEqual(8, len(value["automatic_peer_groups"]))
        self.assertTrue(all(row["current_hil_status"] == "NOT_RUN" for row in value["families"]))
        self.assertEqual(2, value["historical_only"]["m28"]["target_max_connections"])
        self.assertEqual(4, value["historical_only"]["m29"]["l2cap_tx_buffers_total"])
        self.assertEqual(15, len(value["historical_only"]["m32_profiles"]))
        self.assertEqual("NOT_ASSESSED", value["qualification"])
        self.assertTrue(all(row["cause_status"] != "confirmed_cause" for row in value["sdk_risk_regressions"]))
        self.assertEqual(100, value["hil_contract"]["allowed_loss_packets"])
        self.assertEqual(0, value["hil_contract"]["required_observed_loss_packets"])
        self.assertFalse(value["hil_contract"]["stop_token"])

    def test_same_slot_stale_generation_and_cross_link_callback(self):
        """! @brief 다른 link와 이전 generation은 slot이 같아도 수락하지 않습니다. """
        oracle = MODULE.SessionOracle()
        oracle.connect(BINDING, 0)
        oracle.connect(SECOND, 0)
        oracle.request(BINDING, "read-title", 1)
        with self.assertRaises(ValueError):
            oracle.complete(SECOND, "read-title", 2)
        oracle.peer_loss(BINDING, 3)
        newer = MODULE.Binding(0, 2, BINDING.peer_sha256, BINDING.key_sha256)
        oracle.connect(newer, 4)
        for stale in (BINDING, MODULE.Binding(0, 2, SECOND.peer_sha256, BINDING.key_sha256),
                      MODULE.Binding(0, 2, BINDING.peer_sha256, SECOND.key_sha256)):
            with self.subTest(stale=stale), self.assertRaises(ValueError):
                oracle.request(stale, "new-request", 5)
        oracle.request(newer, "new-request", 5)
        oracle.complete(newer, "new-request", 6)

    def test_cancel_and_peer_loss_retire_operation(self):
        """! @brief 취소·peer loss 뒤의 late callback과 token 재사용을 거부합니다. """
        oracle = MODULE.SessionOracle()
        oracle.connect(BINDING, 0)
        oracle.request(BINDING, "operation", 10)
        oracle.cancel(BINDING)
        with self.assertRaises(ValueError):
            oracle.complete(BINDING, "operation", 11)
        with self.assertRaises(ValueError):
            oracle.request(BINDING, "operation", 12)
        oracle.request(BINDING, "next-operation", 12)
        oracle.peer_loss(BINDING, 13)
        with self.assertRaises(ValueError):
            oracle.complete(BINDING, "next-operation", 14)
        oracle.cleanup(13, 14, 0)

    def test_wrong_key_identity_and_bounded_reconnect(self):
        """! @brief RPA/slot만으로 key를 재귀속하지 않고 3회·30초를 강제합니다. """
        oracle = MODULE.SessionOracle()
        oracle.connect(BINDING, 0)
        oracle.peer_loss(BINDING, 100)
        with self.assertRaises(ValueError):
            oracle.connect(MODULE.Binding(0, 2, SECOND.peer_sha256, BINDING.key_sha256), 101)
        with self.assertRaises(ValueError):
            oracle.connect(MODULE.Binding(0, 2, BINDING.peer_sha256, SECOND.key_sha256), 101)
        for attempt in range(3):
            oracle.reconnect_attempt(0, 101 + attempt)
        with self.assertRaises(ValueError):
            oracle.reconnect_attempt(0, 104)
        with self.assertRaises(ValueError):
            oracle.connect(MODULE.Binding(0, 2, BINDING.peer_sha256, BINDING.key_sha256), 30101)

    def test_busy_operation_timeout_and_cleanup_leak(self):
        """! @brief link당 operation 하나·5초 요청·30초 정리·buffer 회수를 강제합니다. """
        oracle = MODULE.SessionOracle()
        oracle.connect(BINDING, 0)
        oracle.request(BINDING, "read", 0)
        with self.assertRaises(ValueError):
            oracle.request(BINDING, "write", 1)
        with self.assertRaises(ValueError):
            oracle.complete(BINDING, "read", 5001)
        with self.assertRaises(ValueError):
            oracle.cleanup(0, 1, 0)
        oracle.peer_loss(BINDING, 5002)
        with self.assertRaises(ValueError):
            oracle.cleanup(5002, 5003, 1)
        with self.assertRaises(ValueError):
            oracle.cleanup(5002, 35003, 0)
        oracle.cleanup(5002, 5003, 0)

    @staticmethod
    def resource_measurement():
        """! @brief 역할별 자원 parser fixture의 고정 수치를 반환합니다. """
        return {"ram_bytes": 100000, "rram_bytes": 200000,
                "minimum_stack_margin_bytes": 264, "allocation_failures": 0,
                "resource_leaks": 0, "pending_links": 0, "outstanding_buffers": 0,
                "sdc_pool_alignment_bytes": 8}

    @staticmethod
    def write_resource_elf(path, measured, image_data, addresses):
        """! @brief PT_LOAD·alloc section·symbol table을 갖춘 ELF64 fixture를 기록합니다. """
        strings = b"\0" + b"\0".join(
            MODULE.RESOURCE_MEASUREMENT_SYMBOLS[field].encode("ascii")
            for field in measured
        ) + b"\0"
        load_offset = 64 + 56
        string_offset = load_offset + len(image_data)
        symbol_offset = (string_offset + len(strings) + 7) & ~7
        symbol_count = len(measured) + 1
        section_offset = symbol_offset + symbol_count * 24
        data = bytearray(section_offset + 5 * 64)
        data[:16] = b"\x7fELF\x02\x01\x01" + b"\0" * 9
        struct.pack_into("<Q", data, 32, 64)
        struct.pack_into("<Q", data, 40, section_offset)
        struct.pack_into("<HHH", data, 52, 64, 56, 1)
        struct.pack_into("<HHH", data, 58, 64, 5, 0)
        struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, load_offset, 0, 0,
                         len(image_data), len(image_data), 4)
        data[load_offset:load_offset + len(image_data)] = image_data
        data[string_offset:string_offset + len(strings)] = strings
        for index, (address, size) in enumerate(
                ((0, measured["rram_bytes"]), (0x20000000, measured["ram_bytes"])), 1):
            offset = section_offset + index * 64
            struct.pack_into("<I", data, offset + 4, 8)
            struct.pack_into("<Q", data, offset + 8, 2)
            struct.pack_into("<Q", data, offset + 16, address)
            struct.pack_into("<Q", data, offset + 32, size)
        string_section = section_offset + 3 * 64
        struct.pack_into("<I", data, string_section + 4, 3)
        struct.pack_into("<QQ", data, string_section + 24, string_offset, len(strings))
        symbol_section = section_offset + 4 * 64
        struct.pack_into("<I", data, symbol_section + 4, 2)
        struct.pack_into("<QQ", data, symbol_section + 24, symbol_offset,
                         symbol_count * 24)
        struct.pack_into("<I", data, symbol_section + 40, 3)
        struct.pack_into("<Q", data, symbol_section + 56, 24)
        name_offset = 1
        for index, field in enumerate(measured, 1):
            symbol = MODULE.RESOURCE_MEASUREMENT_SYMBOLS[field]
            offset = symbol_offset + index * 24
            struct.pack_into("<I", data, offset, name_offset)
            struct.pack_into("<BBHQQ", data, offset + 4, 0x11, 0, 2,
                             addresses[field], 4)
            name_offset += len(symbol) + 1
        path.write_bytes(data)

    def resource(self, folder, group="gap_gatt", revision=REVISION,
                 boards=None, images=None, role_measurements=None):
        """! @brief .config·ELF/map·debugger의 parser 전용 fixture를 만듭니다. """
        path = folder / "test.config"
        path.write_text("CONFIG_BT=y\nCONFIG_BT_LL_SOFTDEVICE=y\nCONFIG_BT_MAX_CONN=2\nCONFIG_BT_EXT_ADV_MAX_ADV_SET=3\n"
                        "CONFIG_BT_PER_ADV_SYNC_MAX=2\nCONFIG_NUCODE_BLE_L2CAP=y\n"
                        "CONFIG_MAIN_STACK_SIZE=8192\nCONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=4096\n"
                        "CONFIG_BT_RX_STACK_SIZE=3200\n", encoding="utf-8")
        roles = MODULE.RAW_PRODUCER_CONTRACTS["resources"]["roles"]
        role_measurements = role_measurements or {
            role: self.resource_measurement() for role in roles
        }
        boards = boards or {
            role: {"probe_sha256": hashlib.sha256(role.encode("ascii")).hexdigest()}
            for role in roles
        }
        if images is None:
            images = {}
            for role in roles:
                marker = (sum(role.encode("ascii")) & 0xff).to_bytes(1, "little")
                vector = (0x20000100).to_bytes(4, "little") + (9).to_bytes(4, "little") + marker
                image_path = folder / f"resource-{role}.hex"
                image_path.write_text(
                    self.hex_record(0, 0, vector) + "\n" + self.hex_record(0, 1) + "\n",
                    encoding="ascii",
                )
                images[role] = {"file": {"path": image_path.name,
                                          "sha256": MODULE.digest(image_path)}}
        measured = {"ram_bytes": max(value["ram_bytes"] for value in role_measurements.values()),
                    "rram_bytes": max(value["rram_bytes"] for value in role_measurements.values()),
                    "minimum_stack_margin_bytes": min(value["minimum_stack_margin_bytes"]
                                                      for value in role_measurements.values()),
                    "allocation_failures": 0, "resource_leaks": 0, "pending_links": 0,
                    "outstanding_buffers": 0, "sdc_pool_alignment_bytes": 8}
        artifacts = {}
        for role in roles:
            role_config = folder / f"{role}.config"
            elf = folder / f"{role}.elf"
            linker_map = folder / f"{role}.map"
            debugger = folder / f"{role}.debugger.json"
            addresses = {key: 0x20000000 + index * 4
                         for index, key in enumerate(role_measurements[role])}
            role_config.write_text(
                path.read_text(encoding="utf-8") +
                f"{MODULE.RESOURCE_ROLE_CONFIG_SYMBOLS[role]}=y\n",
                encoding="utf-8",
            )
            image_path = folder / images[role]["file"]["path"]
            image_data = b"".join(data for _, data in MODULE.intel_hex_ranges(image_path))
            self.write_resource_elf(elf, role_measurements[role], image_data, addresses)
            linker_map.write_text(
                "Memory Configuration\nFLASH 0x00000000 0x000a0000 xr\n"
                f"RAM 0x20000000 0x00039800 xrw\n# role={role}\n",
                encoding="utf-8",
            )
            debugger.write_text(json.dumps({
                "schema_version": 1, "kind": "pyocd-read-only-resource-snapshot",
                "role": role, "source_revision": revision, "source_clean": True,
                "probe_sha256": boards[role]["probe_sha256"],
                "image_sha256": images[role]["file"]["sha256"],
                "backend": "pyocd-live-target", "halted": True, "resumed": True,
                "addresses": addresses,
                "measured": role_measurements[role],
            }), encoding="utf-8")
            artifacts[role] = {
                "measured": role_measurements[role],
                "config": {"path": role_config.name,
                           "sha256": MODULE.digest(role_config)},
                "elf": {"path": elf.name, "sha256": MODULE.digest(elf)},
                "map": {"path": linker_map.name, "sha256": MODULE.digest(linker_map)},
                "debugger": {"path": debugger.name, "sha256": MODULE.digest(debugger)},
            }
        proof = folder / "measurement.json"
        proof.write_text(json.dumps({"schema_version": 2, "kind": "resource_measurement_sources",
                                     "group": group, "source_revision": revision,
                                     "source_clean": True, "config_sha256": MODULE.digest(path),
                                     "roles": artifacts}), encoding="utf-8")
        return {"group": group, "config": {"path": path.name, "sha256": MODULE.digest(path)},
                "measurement_evidence": {"path": proof.name, "sha256": MODULE.digest(proof)},
                "radio_owners": ["ble"], "requested": {key: 0 for key in MODULE.COUNT_SYMBOLS},
                "role_measurements": role_measurements,
                "measurement_addresses": {
                    role: {key: 0x20000000 + index * 4
                           for index, key in enumerate(role_measurements[role])}
                    for role in roles
                },
                "measured": measured}

    @staticmethod
    def rebind_resource_config(record, base):
        """! @brief fixture config 변경 뒤 source reference만 새 byte에 다시 결합합니다. """
        proof_path = base / record["measurement_evidence"]["path"]
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        proof["config_sha256"] = record["config"]["sha256"]
        config_text = (base / record["config"]["path"]).read_text(encoding="utf-8")
        for role, entry in proof["roles"].items():
            role_config = base / entry["config"]["path"]
            role_config.write_text(
                config_text + f"{MODULE.RESOURCE_ROLE_CONFIG_SYMBOLS[role]}=y\n",
                encoding="utf-8",
            )
            entry["config"]["sha256"] = MODULE.digest(role_config)
        proof_path.write_text(json.dumps(proof), encoding="utf-8")
        record["measurement_evidence"]["sha256"] = MODULE.digest(proof_path)

    def test_resource_config_missing_overflow_unknown_and_measurement(self):
        """! @brief null/0 가짜 실측·구성 초과·없는 기능·heap fallback을 허용하지 않습니다. """
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            record = self.resource(base)
            record["requested"].update(connections=2, advertising_sets=3, periodic_syncs=2, coc_channels=2)
            MODULE.validate_resource(record, base)
            for key, value in (("connections", 3), ("advertising_sets", 4), ("periodic_syncs", 3),
                               ("coc_channels", 3), ("cs_connections", 1), ("iso_channels", 1)):
                changed = copy.deepcopy(record)
                changed["requested"][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    MODULE.validate_resource(changed, base)
            for key, value in (("ram_bytes", None), ("ram_bytes", 235521), ("rram_bytes", 655361),
                               ("resource_leaks", 1), ("pending_links", 1), ("minimum_stack_margin_bytes", 0),
                               ("sdc_pool_alignment_bytes", 4)):
                changed = copy.deepcopy(record)
                changed["measured"][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    MODULE.validate_resource(changed, base)
            changed = copy.deepcopy(record)
            changed["config"]["sha256"] = "f" * 64
            with self.assertRaises(ValueError):
                MODULE.validate_resource(changed, base)

    def test_resource_rejects_self_copied_artifact_and_uart_measurements(self):
        """! @brief ELF/map/debugger/UART 중 하나라도 독립 원본과 다르면 거부합니다. """
        for mutation in ("config", "elf", "map", "debugger", "uart"):
            with tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                if mutation == "uart":
                    path, raw = self.raw_fixture(base, "resources", "gap_gatt")
                    reference = raw["transcripts"]["resource_a"]
                    transcript = base / reference["path"]
                    transcript.write_text(
                        transcript.read_text(encoding="ascii").replace(
                            "ram_bytes=100000", "ram_bytes=99999"
                        ),
                        encoding="ascii",
                    )
                    reference["sha256"] = MODULE.digest(transcript)
                    lock = MODULE.read_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
                    with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                        MODULE.validate_raw_evidence(
                            raw, path, "resources", "gap_gatt", REVISION, lock,
                            allow_fixture=True,
                        )
                    continue
                record = self.resource(base)
                proof_path = base / record["measurement_evidence"]["path"]
                proof = json.loads(proof_path.read_text(encoding="utf-8"))
                reference = proof["roles"]["resource_a"][mutation]
                artifact = base / reference["path"]
                if mutation == "config":
                    artifact.write_text("CONFIG_BT=n\n", encoding="utf-8")
                elif mutation == "elf":
                    data = bytearray(artifact.read_bytes())
                    struct.pack_into("<Q", data, 64 + 64 + 32, 199999)
                    artifact.write_bytes(data)
                elif mutation == "map":
                    artifact.write_text(
                        "Memory Configuration\nFLASH 0x00000000 0x00000100 xr\n"
                        "RAM 0x20000000 0x00039800 xrw\n",
                        encoding="utf-8",
                    )
                else:
                    debugger = json.loads(artifact.read_text(encoding="utf-8"))
                    debugger["measured"]["minimum_stack_margin_bytes"] = 999
                    artifact.write_text(json.dumps(debugger), encoding="utf-8")
                reference["sha256"] = MODULE.digest(artifact)
                proof_path.write_text(json.dumps(proof), encoding="utf-8")
                record["measurement_evidence"]["sha256"] = MODULE.digest(proof_path)
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    MODULE.validate_resource(record, base, REVISION)

    def test_resource_rejects_role_artifact_reuse_and_symbol_address_drift(self):
        """! @brief B/C가 A의 config/ELF/map을 재사용하거나 symbol 주소를 위조하면 거부합니다. """
        for mutation in ("reuse", "address"):
            with tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                record = self.resource(base)
                proof_path = base / record["measurement_evidence"]["path"]
                proof = json.loads(proof_path.read_text(encoding="utf-8"))
                if mutation == "reuse":
                    for kind in ("config", "elf", "map"):
                        proof["roles"]["resource_b"][kind] = copy.deepcopy(
                            proof["roles"]["resource_a"][kind]
                        )
                else:
                    record["measurement_addresses"]["resource_b"]["resource_leaks"] += 4
                proof_path.write_text(json.dumps(proof), encoding="utf-8")
                record["measurement_evidence"]["sha256"] = MODULE.digest(proof_path)
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    MODULE.validate_resource(record, base, REVISION)

    def test_radio_ownership_dedicated_combinations_only(self):
        """! @brief DTM/raw HCI와 정상 BLE, DF/CS 최대치, 두 standalone radio를 차단합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            record = self.resource(base)
            for owners in (["ble", "dtm"], ["ieee802154", "esb"], ["df", "cs"], ["ble", "mesh"]):
                changed = copy.deepcopy(record)
                changed["radio_owners"] = owners
                changed["group"] = "radio_coexistence"
                with self.subTest(owners=owners), self.assertRaises(ValueError):
                    MODULE.validate_resource(changed, base)
            record = self.resource(base, "radio_coexistence")
            record.update(radio_owners=["ble", "mesh"], dedicated_coexistence="coexistence_ble_mesh")
            with self.assertRaisesRegex(ValueError, "owner absent"):
                MODULE.validate_resource(record, base)
            config = base / record["config"]["path"]
            config.write_text(config.read_text(encoding="utf-8") + "CONFIG_BT_MESH=y\n", encoding="utf-8")
            record["config"]["sha256"] = MODULE.digest(config)
            self.rebind_resource_config(record, base)
            MODULE.validate_resource(record, base)
            record["dedicated_coexistence"] = "coexistence_ble_esb"
            with self.assertRaises(ValueError):
                MODULE.validate_resource(record, base)

    def test_peer_matrix_followup_and_os_gate_are_independent(self):
        """! @brief 외부 실물 미실행은 비차단이고 OS 지원 실기는 final-release gate입니다. """
        rows = MODULE.peer_matrix()
        self.assertEqual(43, len(rows))
        for row in rows:
            MODULE.validate_peer(row)
        external, operating_system = copy.deepcopy(rows[0]), copy.deepcopy(rows[-1])
        external["release_blocker"] = True
        operating_system["release_blocker"] = False
        for row in (external, operating_system):
            with self.assertRaises(ValueError):
                MODULE.validate_peer(row)
        unsupported_without_evidence = copy.deepcopy(rows[0])
        unsupported_without_evidence["peer_support"] = "unsupported"
        with self.assertRaises(ValueError):
            MODULE.validate_peer(unsupported_without_evidence)

    def test_fixed_sdk_dtm_controller_is_not_normal_ble_host(self):
        """! @brief NCS 3.4.0 DTM의 BT=y/raw controller 경로를 normal Host와 구분합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            record = self.resource(base, "diagnostics")
            record.update(radio_owners=["dtm"])
            config = base / record["config"]["path"]
            contents = config.read_text(encoding="utf-8") + "CONFIG_BT_HCI_RAW=y\nCONFIG_BT_CTLR_DTM_HCI=y\n"
            config.write_text(contents, encoding="utf-8")
            record["config"]["sha256"] = MODULE.digest(config)
            self.rebind_resource_config(record, base)
            MODULE.validate_resource(record, base)
            config.write_text(contents + "CONFIG_BT_HCI_HOST=y\n", encoding="utf-8")
            record["config"]["sha256"] = MODULE.digest(config)
            self.rebind_resource_config(record, base)
            with self.assertRaisesRegex(ValueError, "normal BLE Host"):
                MODULE.validate_resource(record, base)

    def test_peer_unsupported_is_not_core_unsupported_or_qualified(self):
        """! @brief Windows GATT·합성 peer PASS를 전체 OS·Apple·제품 자격에 복사하지 않습니다. """
        row = MODULE.peer_matrix()[0]
        row.update(status="PEER_UNSUPPORTED", peer_support="unsupported", reason="actual service discovery absent",
                   reason_code="peer_service_absent", support_discovery="physical_discovery",
                   evidence={"path": "peer.json", "sha256": "a" * 64})
        MODULE.validate_peer(row)
        row["evidence"] = None
        with self.assertRaises(ValueError):
            MODULE.validate_peer(row)
        row["evidence"] = {"path": "peer.json", "sha256": "a" * 64}
        row["status"] = "CORE_UNSUPPORTED"
        with self.assertRaises(ValueError):
            MODULE.validate_peer(row)
        row.update(status="PASS", core_support="supported", peer_support="supported", basis="scripted_peer",
                   evidence={"path": "test", "sha256": "a" * 64}, reason_code="observed_pass",
                   support_discovery="physical_discovery")
        row["peer"].update(vendor="Test vendor", model="Test model", os_version="test")
        with self.assertRaises(ValueError):
            MODULE.validate_peer(row)
        row["basis"] = "physical_peer"
        MODULE.validate_peer(row)
        row["qualification_status"] = "QUALIFIED"
        with self.assertRaises(ValueError):
            MODULE.validate_peer(row)

    def test_peer_reason_and_support_discovery_are_bound_to_evidence(self):
        """! @brief unsupported/failure reason은 실제 구조화 discovery byte와 같아야 합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            row = copy.deepcopy(MODULE.peer_matrix()[0])
            row.update(status="PEER_UNSUPPORTED", peer_support="unsupported",
                       reason="actual service discovery absent", reason_code="peer_service_absent",
                       support_discovery="physical_discovery")
            evidence = {"schema_version": 1, "kind": "peer_support_discovery",
                        "feature": row["feature"], "peer": row["peer"], "status": row["status"],
                        "reason": row["reason"], "reason_code": row["reason_code"],
                        "support_discovery": row["support_discovery"],
                        "source_revision": REVISION, "source_clean": True}
            path = base / "peer.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            row["evidence"] = {"path": path.name, "sha256": MODULE.digest(path)}
            MODULE.validate_peer(row)
            MODULE.validate_peer_evidence(row, base, REVISION)
            row["reason"] = "unrelated free-form claim"
            with self.assertRaises(ValueError):
                MODULE.validate_peer_evidence(row, base, REVISION)

    def test_qualification_components_do_not_certify_product(self):
        """! @brief component 근거와 제품별 추가 절차를 별도 필드로 남깁니다. """
        for component in ("host", "controller", "mesh"):
            row = {"component": component, "applicability": "unresolved", "component_status": "NOT_ASSESSED",
                   "product_status": "NOT_ASSESSED", "example_status_implied": False}
            MODULE.validate_qualification(row)
            row["component_status"] = "EVIDENCE_RECORDED"
            with self.assertRaises(ValueError):
                MODULE.validate_qualification(row)
            row.update(applicability="applicable", component_version="NCS 3.4.0 LTS",
                       design_identifier=("NOT_LISTED_NO_DN" if component == "mesh"
                                          else "PLANNED_NO_DN"),
                       official_reference="https://example.invalid/test",
                       remaining_product_procedure="owner must verify and complete product qualification")
            MODULE.validate_qualification(row)
            row["design_identifier"] = "QUALIFIED"
            with self.assertRaises(ValueError):
                MODULE.validate_qualification(row)
            row["design_identifier"] = ("NOT_LISTED_NO_DN" if component == "mesh"
                                        else "PLANNED_NO_DN")
            row["product_status"] = "QUALIFIED"
            with self.assertRaises(ValueError):
                MODULE.validate_qualification(row)

    def test_qualification_producer_records_fixed_ncs_without_product_pass(self):
        """! @brief producer는 NCS 3.4.0 조사 근거만 기록하고 제품 자격을 승격하지 않습니다. """

        current = {
            "source_revision": REVISION,
            "source_clean": True,
            "prerequisite_blockers": [],
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "qualification.json"
            with mock.patch.object(MODULE, "snapshot", return_value=current):
                document = MODULE.produce_qualification(output, ROOT)
            self.assertEqual(document, MODULE.read_json(output))
            self.assertEqual(
                {"host": "PLANNED_NO_DN", "controller": "PLANNED_NO_DN",
                 "mesh": "NOT_LISTED_NO_DN"},
                {row["component"]: row["design_identifier"]
                 for row in document["qualification"]},
            )
            self.assertTrue(all(
                row["component_status"] == "EVIDENCE_RECORDED" and
                row["product_status"] == "NOT_ASSESSED" and
                row["example_status_implied"] is False
                for row in document["qualification"]
            ))
            with mock.patch.object(MODULE, "snapshot", return_value=current), \
                    self.assertRaisesRegex(ValueError, "new qualification"):
                MODULE.produce_qualification(output, ROOT)
    @staticmethod
    def hex_record(address, kind, data=b""):
        """! @brief checksum이 맞는 작은 Intel HEX record를 만듭니다. """
        body = bytes([len(data)]) + address.to_bytes(2, "big") + bytes([kind]) + data
        return ":" + (body + bytes([(-sum(body)) & 0xff])).hex().upper()

    def image_fixture(self, base, role, revision):
        """! @brief parser 단위 시험용 실제 HEX·readback·flash 결합 fixture를 만듭니다. """
        lock = MODULE.read_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
        marker = (sum(role.encode("ascii")) & 0xff).to_bytes(1, "little")
        vector = (0x20000100).to_bytes(4, "little") + (9).to_bytes(4, "little") + marker
        image_path = base / f"{role}.hex"
        image_path.write_text(self.hex_record(0, 0, vector) + "\n" + self.hex_record(0, 1) + "\n",
                              encoding="ascii")
        manifest = self.source_manifest(revision)
        record_path = base / f"{role}.build-record.txt"
        build = {"core_revision": revision, "board_revision": lock["board"]["revision"],
                 "ncs_revision": lock["ncs"]["revision"], "zephyr_revision": lock["zephyr"]["revision"],
                 "core_source_sha256": "1" * 64, "application_source_sha256": "2" * 64,
                 "board_source_sha256": "3" * 64,
                 "firmware_source_sha256": manifest["firmware_source_sha256"],
                 "application_cmake_sha256": manifest["application_cmake_sha256"],
                 "application_config_sha256": manifest["application_config_sha256"],
                 "source_manifest_sha256": manifest["sha256"]}
        record_path.write_text(json.dumps(build, sort_keys=True) + "\n", encoding="utf-8")
        build["record_sha256"] = MODULE.digest(record_path)
        ranges = [{"start": start, "length": len(data),
                   "expected_sha256": hashlib.sha256(data).hexdigest(),
                   "observed_sha256": hashlib.sha256(data).hexdigest(), "status": "PASS"}
                  for start, data in MODULE.intel_hex_ranges(image_path)]
        load_ranges = [{"start": start, "length": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()}
                       for start, data in MODULE.intel_hex_ranges(image_path)]
        probe_sha256 = hashlib.sha256(role.encode()).hexdigest()
        readback_path = base / f"{role}.readback.json"
        readback_path.write_text(json.dumps({"schema_version": 2, "status": "PASS", "role": role,
                                             "source_revision": revision,
                                             "source_manifest_sha256": manifest["sha256"],
                                             "probe_sha256": probe_sha256,
                                             "backend": "pyocd-live-target", "halted": True,
                                             "resumed": True,
                                             "image_sha256": MODULE.digest(image_path), "ranges": ranges}),
                                 encoding="utf-8")
        flash_path = base / f"{role}.flash.json"
        flash_path.write_text(json.dumps({"schema_version": 2, "status": "PASS", "role": role,
                                          "source_revision": revision, "probe_sha256": probe_sha256,
                                          "cmsis_dap": "v2-only", "mode": "pyocd-sector-sw-reset",
                                          "erase": "sector", "auto_unlock": False,
                                          "automatic_recover": False, "mass_erase": False,
                                          "source_manifest_sha256": manifest["sha256"],
                                          "image_sha256": MODULE.digest(image_path),
                                          "programmed_bytes": len(vector),
                                          "readback_sha256": MODULE.digest(readback_path)}), encoding="utf-8")
        return {"role": role, "file": {"path": image_path.name, "sha256": MODULE.digest(image_path)},
                "build_record": {"path": record_path.name, "sha256": MODULE.digest(record_path)},
                "readback": {"path": readback_path.name, "sha256": MODULE.digest(readback_path)},
                "flash_record": {"path": flash_path.name, "sha256": MODULE.digest(flash_path)},
                "build": build, "source_manifest": manifest, "load_ranges": load_ranges}

    def source_manifest(self, revision):
        """! @brief parser fixture의 full revision source manifest를 계산합니다. """
        lock = MODULE.read_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
        values = {
            "core_revision": revision,
            "board_revision": lock["board"]["revision"],
            "ncs_revision": lock["ncs"]["revision"],
            "zephyr_revision": lock["zephyr"]["revision"],
            "core_source_sha256": "1" * 64,
            "application_source_sha256": "2" * 64,
            "board_source_sha256": "3" * 64,
            "firmware_source_sha256": MODULE.digest(
                ROOT / "tests/zephyr/m28_ble_3board_hil/src/main.cpp"
            ),
            "application_cmake_sha256": MODULE.digest(
                ROOT / "tests/zephyr/m32_regression_soak_hil/CMakeLists.txt"
            ),
            "application_config_sha256": MODULE.digest(
                ROOT / "tests/zephyr/m32_regression_soak_hil/prj.conf"
            ),
        }
        encoded = "\n".join(f"{key}={values[key]}" for key in MODULE.SOURCE_MANIFEST_FIELDS)
        values["sha256"] = hashlib.sha256(encoded.encode("ascii")).hexdigest()
        return values

    def raw_fixture(self, base, field="families", identifier="gap_links", revision=REVISION):
        """! @brief 전체 closure가 아닌 scope parser 한 개의 성공 fixture를 만듭니다. """
        base.mkdir(parents=True, exist_ok=True)
        scope = MODULE.RAW_SCOPES[field]
        if field == "families" and identifier == "ecosystem_templates":
            scope = "current_template_automatic_checks"
        denominator = MODULE.RAW_DENOMINATORS[field][identifier]
        contract = MODULE.RAW_PRODUCER_CONTRACTS[field]
        producer_route = ROOT / contract["route"]
        raw = {"schema_version": 2, "evidence_kind": MODULE.RAW_EVIDENCE_KINDS[field],
               "producer": {"schema_version": 1, "kind": "schema_fixture",
                            "name": contract["name"], "route": contract["route"],
                            "route_sha256": MODULE.digest(producer_route),
                            "test_route": MODULE.RAW_TEST_ROUTES[field][identifier],
                            "protocol": contract["protocol"]},
               "id": identifier, "status": "PASS", "source_revision": revision, "source_clean": True,
               "denominator": denominator, "completed": denominator, "failures": 0, "scope": scope,
               "boards": [], "images": [], "target_manifests": {},
               "transcripts": {}, "results": {},
               "execution_receipt": None}
        role_measurements = None
        if field == "resources":
            role_measurements = {
                role: self.resource_measurement() for role in contract["roles"]
            }
            raw["role_measurements"] = role_measurements
            raw["measurement_addresses"] = {
                role: {key: 0x20000000 + index * 4
                       for index, key in enumerate(role_measurements[role])}
                for role in contract["roles"]
            }
        nonce = hashlib.sha256(f"{field}:{identifier}".encode()).hexdigest()[:32]
        for role in contract["roles"]:
            image = self.image_fixture(base, role, revision)
            probe_sha256 = hashlib.sha256(role.encode()).hexdigest()
            raw["boards"].append({"role": role, "probe_sha256": probe_sha256,
                                  "registers": {"dp_idcode": "0x6ba02477"},
                                  "image_sha256": image["file"]["sha256"]})
            raw["images"].append(image)
            target_manifest = {
                "schema_version": 1, "scope": scope, "id": identifier,
                "test_route": MODULE.RAW_TEST_ROUTES[field][identifier],
                "protocol": contract["protocol"], "role": role,
                "source_revision": revision,
                "source_manifest_sha256": image["source_manifest"]["sha256"],
            }
            if field == "resources":
                target_manifest["measurement_addresses_sha256"] = hashlib.sha256(
                    json.dumps(raw["measurement_addresses"][role], sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
                ).hexdigest()
            encoded = json.dumps(target_manifest, sort_keys=True,
                                 separators=(",", ":")).encode("utf-8")
            target_manifest["sha256"] = hashlib.sha256(encoded).hexdigest()
            raw["target_manifests"][role] = target_manifest
            lines = [
                f"{contract['protocol']}:READY:id={identifier}:role={role}:revision={revision}:"
                f"source_manifest_sha256={image['source_manifest']['sha256']}:"
                f"target_manifest_sha256={target_manifest['sha256']}"
            ]
            lines.extend(
                f"{contract['protocol']}:ITERATION:PASS:id={identifier}:role={role}:"
                f"iteration={index}:completed={index}:failures=0:nonce={nonce}"
                for index in range(1, denominator + 1)
            )
            if role_measurements is not None:
                measured = role_measurements[role]
                lines.append(
                    f"{contract['protocol']}:MEASUREMENT:PASS:id={identifier}:role={role}:"
                    f"ram_bytes={measured['ram_bytes']}:rram_bytes={measured['rram_bytes']}:"
                    f"minimum_stack_margin_bytes={measured['minimum_stack_margin_bytes']}:"
                    f"allocation_failures=0:resource_leaks=0:pending_links=0:"
                    f"outstanding_buffers=0:sdc_pool_alignment_bytes=8:nonce={nonce}"
                )
            lines.extend([
                f"{contract['protocol']}:CLEANUP:PASS:id={identifier}:role={role}:"
                f"elapsed_ms=10:active_links=0:pending_links=0:outstanding_buffers=0:"
                f"initialized=0:nonce={nonce}",
                f"{contract['protocol']}:FINAL:PASS:id={identifier}:role={role}:"
                f"completed={denominator}:failures=0:"
                f"target_manifest_sha256={target_manifest['sha256']}:nonce={nonce}",
            ])
            transcript_path = base / f"{role}.uart.log"
            transcript_path.write_text("\n".join(lines) + "\n", encoding="ascii")
            raw["transcripts"][role] = {"path": transcript_path.name,
                                         "sha256": MODULE.digest(transcript_path)}
            raw["results"][role] = {"role": role, "completed": denominator,
                                     "failures": 0, "cleanup_ms": 10,
                                     "cleanup": "pass"}
            if role_measurements is not None:
                raw["results"][role]["measured"] = role_measurements[role]
        if identifier == "ecosystem_templates":
            raw["external_interoperability"] = "NOT_RUN"
        if field == "resources":
            raw.update(self.resource(
                base, identifier, revision,
                {board["role"]: board for board in raw["boards"]},
                {image["role"]: image for image in raw["images"]},
                role_measurements,
            ))
        if field == "automatic_peers":
            peer = {"feature": identifier, "kind": "automatic", "status": "PASS",
                    "peer_support": "supported", "core_support": "supported",
                    "peer": {"vendor": "Fixture", "model": "Scripted peer", "os": "fixture",
                             "os_version": "1", "adapter": None, "app": "unit parser"},
                    "verification_owner": "developer", "verification_stage": "development",
                    "development_blocker": True, "release_blocker": True,
                    "basis": "scripted_peer", "reason_code": "observed_pass",
                    "support_discovery": "scripted_discovery", "evidence": None,
                    "qualification_status": "NOT_ASSESSED"}
            peer_evidence = {"schema_version": 1, "kind": "peer_support_discovery",
                             "feature": peer["feature"], "peer": peer["peer"],
                             "status": peer["status"], "reason": None,
                             "reason_code": peer["reason_code"],
                             "support_discovery": peer["support_discovery"],
                             "source_revision": revision, "source_clean": True}
            peer_path = base / "peer.json"
            peer_path.write_text(json.dumps(peer_evidence), encoding="utf-8")
            peer["evidence"] = {"path": peer_path.name, "sha256": MODULE.digest(peer_path)}
            raw["peer_result"] = peer
        raw_path = base / "raw.json"
        raw_path.write_text(json.dumps(raw), encoding="utf-8")
        return raw_path, raw


    def campaign_fixture(self, base, field="families", identifier="gap_links",
                         revision=REVISION):
        """! @brief 실제 campaign validator용 정규화 receipt fixture를 만듭니다. """
        base.mkdir(parents=True, exist_ok=True)
        plan = MODULE.campaign_plan(field, identifier)
        results = []
        for campaign in plan["campaigns"]:
            child = base / f"{campaign['id']}.child.json"
            child.write_text(json.dumps({
                "schema_version": 1,
                "status": "PASS",
                "source_revision": revision,
                "campaign_id": campaign["id"],
            }), encoding="utf-8")
            hardware = []
            for role in campaign["roles"]:
                hardware.append({
                    "role": role,
                    "probe_sha256": hashlib.sha256(
                        f"probe:{campaign['id']}:{role}".encode("utf-8")
                    ).hexdigest(),
                    "image_sha256": hashlib.sha256(
                        f"image:{campaign['id']}:{role}".encode("utf-8")
                    ).hexdigest(),
                    "build_record_sha256": hashlib.sha256(
                        f"build:{campaign['id']}:{role}".encode("utf-8")
                    ).hexdigest(),
                    "readback_sha256": hashlib.sha256(
                        f"readback:{campaign['id']}:{role}".encode("utf-8")
                    ).hexdigest(),
                    "program_mode": "pyocd-sector-sw-reset",
                    "programmed_bytes": 1,
                    "erase": "sector",
                    "auto_unlock": False,
                    "mass_erase": False,
                    "automatic_recover": False,
                })
            receipt = {
                "schema_version": 1,
                "kind": "schema_fixture",
                "campaign_id": campaign["id"],
                "verification": campaign["verification"],
                "status": "PASS",
                "source_revision": revision,
                "source_clean": True,
                "runner_sha256": campaign["runner"]["sha256"],
                "application_sha256": {
                    row["path"]: row["sha256"] for row in campaign["applications"]
                },
                "roles": campaign["roles"],
                "cycles": campaign["minimum_cycles"],
                "semantics": campaign["semantics"],
                "semantic_status": {
                    token: "PASS" for token in campaign["semantics"]
                },
                "child_evidence": {"path": child.name, "sha256": MODULE.digest(child)},
                "exit_code": 0,
                "pid": 100,
                "started_ns": 10,
                "finished_ns": 20,
                "command_sha256": "c" * 64,
                "hardware": hardware,
            }
            encoded = json.dumps(receipt, sort_keys=True,
                                 separators=(",", ":")).encode("utf-8")
            receipt["sha256"] = hashlib.sha256(encoded).hexdigest()
            receipt_path = base / f"{campaign['id']}.receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            results.append({
                "id": campaign["id"],
                "status": "PASS",
                "verification": campaign["verification"],
                "runner": campaign["runner"],
                "applications": campaign["applications"],
                "roles": campaign["roles"],
                "cycles": campaign["minimum_cycles"],
                "semantics": campaign["semantics"],
                "semantic_status": {
                    token: "PASS" for token in campaign["semantics"]
                },
                "evidence": {"path": receipt_path.name,
                             "sha256": MODULE.digest(receipt_path)},
            })
        document = {
            "schema_version": 1,
            "evidence_kind": "m33_actual_campaign_result",
            "field": field,
            "id": identifier,
            "status": "PASS",
            "source_revision": revision,
            "source_clean": True,
            "campaign_plan": plan,
            "campaign_results": results,
            "failures": 0,
        }
        if field == "families" and identifier == "ecosystem_templates":
            document["external_interoperability"] = "NOT_RUN"
        if field == "automatic_peers":
            document["external_interoperability"] = "NOT_RUN"
            peer = {
                "feature": identifier,
                "kind": "automatic",
                "status": "PASS",
                "peer_support": "supported",
                "core_support": "supported",
                "peer": {"vendor": "NUCODE", "model": "NU54DK scripted peer",
                         "os": "Zephyr", "os_version": "3.7", "adapter": None,
                         "app": identifier},
                "verification_owner": "developer",
                "verification_stage": "development",
                "development_blocker": True,
                "release_blocker": True,
                "basis": "scripted_peer",
                "reason_code": "observed_pass",
                "support_discovery": "scripted_discovery",
                "evidence": None,
                "qualification_status": "NOT_ASSESSED",
            }
            peer_evidence = {
                "schema_version": 1,
                "kind": "peer_support_discovery",
                "feature": identifier,
                "peer": peer["peer"],
                "status": "PASS",
                "reason": None,
                "reason_code": "observed_pass",
                "support_discovery": "scripted_discovery",
                "source_revision": revision,
                "source_clean": True,
            }
            peer_path = base / "peer.json"
            peer_path.write_text(json.dumps(peer_evidence), encoding="utf-8")
            peer["evidence"] = {"path": peer_path.name,
                                "sha256": MODULE.digest(peer_path)}
            document["peer_result"] = peer
        path = base / "campaign.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path, document

    def execution_spec_fixture(self, base, revision=REVISION):
        """! @brief dispatcher preflight와 subprocess adapter용 실행 spec을 만듭니다. """
        base.mkdir(parents=True, exist_ok=True)
        plan = MODULE.campaign_plan("families", "gap_links")
        campaign = plan["campaigns"][0]
        native = base / "m28-link-native.json"
        child = base / "m28-link-child.json"
        hardware = [
            {
                "role": role,
                "probe_sha256": hashlib.sha256(
                    f"dispatcher-probe:{role}".encode("utf-8")
                ).hexdigest(),
                "image_sha256": hashlib.sha256(
                    f"dispatcher-image:{role}".encode("utf-8")
                ).hexdigest(),
                "build_record_sha256": hashlib.sha256(
                    f"dispatcher-build:{role}".encode("utf-8")
                ).hexdigest(),
                "readback_sha256": hashlib.sha256(
                    f"dispatcher-readback:{role}".encode("utf-8")
                ).hexdigest(),
                "program_mode": "pyocd-sector-sw-reset",
                "programmed_bytes": 1,
                "erase": "sector",
                "auto_unlock": False,
                "mass_erase": False,
                "automatic_recover": False,
            }
            for role in campaign["roles"]
        ]
        native_hardware = []
        for index, row in enumerate(hardware, 1):
            image = base / f"{row['role']}-adapter-image.hex"
            build_record = base / f"{row['role']}-adapter-build-record.bin"
            readback = base / f"{row['role']}-adapter-readback.json"
            vector = ((0x20000100 + index * 4).to_bytes(4, "little") +
                      (9 + index * 2).to_bytes(4, "little") +
                      bytes([index]))
            image.write_text(
                self.hex_record(0, 0, vector) + "\n" +
                self.hex_record(0, 1) + "\n", encoding="ascii"
            )
            build_record.write_bytes(("build:" + row["role"]).encode("ascii"))
            ranges = [{
                "start": start,
                "length": len(data),
                "expected_sha256": hashlib.sha256(data).hexdigest(),
                "observed_sha256": hashlib.sha256(data).hexdigest(),
                "status": "PASS",
            } for start, data in MODULE.intel_hex_ranges(image)]
            readback.write_text(json.dumps({
                "schema_version": 1,
                "kind": "m33_exact_program_readback",
                "status": "PASS",
                "role": row["role"],
                "probe_sha256": row["probe_sha256"],
                "image_sha256": MODULE.digest(image),
                "backend": "pyocd-live-target",
                "halted": True,
                "resumed": True,
                "pre_state": "RUNNING",
                "post_state": "RUNNING",
                "restored": True,
                "ranges": ranges,
            }), encoding="utf-8")
            row["image_sha256"] = MODULE.digest(image)
            row["build_record_sha256"] = MODULE.digest(build_record)
            row["readback_sha256"] = MODULE.digest(readback)
            row["programmed_bytes"] = len(vector)
            native_hardware.append({
                "role": row["role"],
                "probe_sha256": row["probe_sha256"],
                "image": {"path": image.name, "sha256": MODULE.digest(image)},
                "build_record": {"path": build_record.name,
                                 "sha256": MODULE.digest(build_record)},
                "flash": {"mode": "pyocd-sector-sw-reset",
                          "programmed_bytes": len(vector), "erase": "sector",
                          "auto_unlock": False, "mass_erase": False,
                          "automatic_recover": False},
                "readback": {"path": readback.name,
                             "sha256": MODULE.digest(readback)},
            })
        spec = {
            "schema_version": 1,
            "kind": "m33_campaign_execution_spec",
            "field": "families",
            "id": "gap_links",
            "source_revision": revision,
            "source_clean": True,
            "campaign_plan": plan,
            "campaigns": [{
                "id": campaign["id"],
                "verification": campaign["verification"],
                "runner": campaign["runner"],
                "applications": campaign["applications"],
                "roles": campaign["roles"],
                "cycles": campaign["minimum_cycles"],
                "semantics": campaign["semantics"],
                "subcommand": None,
                "boards": [
                    {"role": row["role"],
                     "probe_sha256": row["probe_sha256"]}
                    for row in hardware
                ],
                "arguments": [{
                    "option": "--evidence",
                    "values": [str(native)],
                }],
                "timeout_seconds": 60,
                "native_evidence": native.name,
                "child_evidence": child.name,
                "reuse_receipt": None,
            }],
        }
        adapter = {
            "schema_version": 1, "status": "passed",
            "core_revision": revision, "boards": {}, "results": {},
            "m33_dispatch_attestation": {
                "schema_version": 1,
                "kind": RUNNER.NATIVE_ATTESTATION_KIND,
                "campaign_id": campaign["id"],
                "source_revision": revision,
                "source_clean": True,
                "semantic_status": {
                    token: "PASS" for token in campaign["semantics"]
                },
                "cycle_records": [
                    {"cycle": cycle, "status": "PASS",
                     "semantics": {token: "PASS" for token in campaign["semantics"]}}
                    for cycle in range(1, campaign["minimum_cycles"] + 1)
                ],
                "hardware": native_hardware,
            },
        }
        spec_path = base / "execution-spec.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        return spec_path, spec, native, child, adapter

    def soak_fixture(self, base):
        """! @brief fresh schema의 image/readback와 autonomous cleanup source를 결합합니다. """
        base.mkdir(parents=True, exist_ok=True)
        lock = MODULE.read_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
        revision = "e" * 40
        nonce = "17737ec4e77fde834ebcb1b7b5a0df5f"
        producer_route = ROOT / "tests/hil/nu54dk/m32_regression_soak_run.py"
        manifest = self.source_manifest(revision)
        document = {"schema_version": 3, "evidence_kind": "m33_fresh_soak",
                    "producer": {"schema_version": 1, "kind": "schema_fixture",
                                 "route": "tests/hil/nu54dk/m32_regression_soak_run.py",
                                 "route_sha256": MODULE.digest(producer_route),
                                 "protocol": "NUCODE_M28B3_SOAK_V3"},
                    "test_ids": ["M32-SOAK-01:primary", "M33-REG-01:representative_soak"],
                    "status": "PASS", "scope": "three_board_bounded_gatt_soak", "source_clean": True,
                    "identity": {"core": revision, "board": lock["board"]["revision"],
                                  "ncs": lock["ncs"]["revision"], "zephyr": lock["zephyr"]["revision"]},
                    "source_manifest": manifest,
                    "boards": {}, "images": {}, "transcripts": {}, "results": {},
                    "duration_seconds": 1800, "packet_denominator_per_link": 10000,
                    "allowed_loss_packets": 100, "observed_loss_packets": 0, "latency_limit_ms": 500,
                    "recovery_timeout_s": 30,
                    "host_monotonic_scope": "central_start_to_all_final",
                    "host_monotonic_elapsed_ms": 1800000,
                    "safety": {"cmsis_dap": "v2-only", "auto_unlock": False, "erase": "sector",
                               "reset": "software", "automatic_recover": False, "mass_erase": False,
                               "termination": "autonomous_finite_cleanup_final", "stop_token": False}}
        firmware = ROOT / "tests/zephyr/m28_ble_3board_hil/src/main.cpp"
        document["firmware_cleanup_contract"] = {
            "path": firmware.relative_to(ROOT).as_posix(), "sha256": MODULE.digest(firmware),
            "source_manifest_sha256": manifest["sha256"],
            "mode": "autonomous_finite_cleanup_final", "stop_token": False}
        identity_suffix = "".join(
            f":{key}={manifest[key]}" for key in MODULE.SOURCE_MANIFEST_FIELDS
        ) + f":source_manifest_sha256={manifest['sha256']}"
        for index, role in enumerate(("peripheral", "mixed", "central")):
            document["boards"][role] = {"probe_sha256": hashlib.sha256(role.encode()).hexdigest(),
                                         "vcom": f"COM{index + 1}", "registers": {"dp_idcode": "0x6ba02477"}}
            document["images"][role] = self.image_fixture(base, role, revision)
            tx = 10000 if role in ("mixed", "central") else 0
            rx = 10000 if role in ("peripheral", "mixed") else 0
            links = 2 if role == "mixed" else 1
            sequence = "sequence_per_link" if role == "mixed" else "sequence"
            lines = [f"NUCODE_M28B3_READY:role={role}:test=SOAK{identity_suffix}"]
            if role in ("peripheral", "mixed"):
                lines.append(f"NUCODE_M28B3_{role}:ADVERTISE:PASS:test=SOAK:nonce={nonce}")
            lines.extend([f"NUCODE_M28B3_{role}:TRACE:PASS:test=SOAK:source=rf-gatt:tx={tx}:rx={rx}:nonce={nonce}",
                          f"NUCODE_M28B3_{role}:SOAK:PASS:duration_s=1800:links={links}:{sequence}=10000"
                          f":loss=0:corrupt=0:duplicate=0:unexpected_disconnect=0:recovery_failures=0:drops=0"
                          f":max_gap_ms={200 if rx else 0}:cleanup_ms=1:cleanup=pass:nonce={nonce}",
                          f"NUCODE_M28B3_{role}:FINAL:PASS:test=SOAK{identity_suffix}:nonce={nonce}"])
            raw = ("\n".join(lines) + "\n").encode("ascii")
            transcript_path = base / f"{role}.transcript.log"
            transcript_path.write_bytes(raw)
            document["transcripts"][role] = {"name": transcript_path.name, "size": len(raw),
                                               "sha256": MODULE.digest(transcript_path)}
            document["results"][role] = {"role": role, "transmitted": tx, "received": rx, "loss": 0,
                                           "corrupt": 0, "duplicate": 0, "maximum_gap_ms": 200 if rx else 0,
                                           "cleanup_ms": 1, "cleanup": "pass"}
        receipt = {
            "schema_version": 1,
            "kind": "pyocd-sector-uart-live-session-v1",
            "producer_sha256": document["producer"]["route_sha256"],
            "nonce_sha256": hashlib.sha256(nonce.encode("ascii")).hexdigest(),
            "source_manifest_sha256": manifest["sha256"],
            "active_started_ns": 1000000000,
            "active_finished_ns": 1801000000000,
            "roles": {
                role: {
                    "probe_sha256": document["boards"][role]["probe_sha256"],
                    "image_sha256": document["images"][role]["file"]["sha256"],
                    "readback_sha256": document["images"][role]["readback"]["sha256"],
                    "flash_record_sha256":
                    document["images"][role]["flash_record"]["sha256"],
                    "transcript_sha256": document["transcripts"][role]["sha256"],
                }
                for role in ("peripheral", "mixed", "central")
            },
        }
        encoded = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
        receipt["sha256"] = hashlib.sha256(encoded).hexdigest()
        document["execution_receipt"] = receipt
        path = base / "soak.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path, document

    def test_soak_historical_checkout_bytes_are_not_reconstructed(self):
        """! @brief M32 checkout의 LF byte mismatch를 CRLF로 재합성해 PASS시키지 않습니다. """
        original = ROOT / "00_Docs/04_검증 기록/evidence/m32-w11-exact-94f02544/soak.json"
        document = MODULE.read_json(original)
        self.assertTrue(all(MODULE.digest(original.parent / record["name"]) != record["sha256"]
                            for record in document["transcripts"].values()))
        with self.assertRaisesRegex(ValueError, "fresh W06"):
            validate_soak(original, document["identity"]["core"])

    def test_soak_fresh_autonomous_cleanup_and_bound_images_pass(self):
        """! @brief fixture parser는 통과하지만 final physical closure에는 사용할 수 없습니다. """
        with tempfile.TemporaryDirectory() as temporary:
            path, document = self.soak_fixture(Path(temporary))
            self.assertFalse(any(b"STOP" in (path.parent / record["name"]).read_bytes()
                                 for record in document["transcripts"].values()))
            self.assertEqual(
                "SCHEMA_VALID",
                validate_soak(
                    path, document["identity"]["core"], allow_fixture=True
                )["status"],
            )
            with self.assertRaisesRegex(ValueError, "fixture"):
                validate_soak(path, document["identity"]["core"])
            document["producer"]["kind"] = "physical_hil"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "audit-only"):
                validate_soak(path, document["identity"]["core"])
            with self.assertRaises(ValueError):
                validate_soak(path, document["identity"]["core"],
                              allow_physical_audit=True)

    def test_soak_rejects_role_nonce_safety_time_revision_and_readback_drift(self):
        """! @brief fresh soak의 역할·원본·안전·monotonic·full revision을 fail-closed로 거부합니다. """
        for mutation in ("role", "nonce", "raw", "safety", "denominator", "allowed_loss",
                         "candidate", "host_time", "build_revision", "readback",
                         "probe_binding", "source_binding", "build_source_binding",
                         "receipt", "short_build_revision"):
            with tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                path, document = self.soak_fixture(base)
                revision = document["identity"]["core"]
                changed = copy.deepcopy(document)
                if mutation == "role":
                    del changed["boards"]["central"]
                elif mutation == "nonce":
                    raw = (base / changed["transcripts"]["central"]["name"]).read_bytes()
                    altered = base / "different-nonce.log"
                    altered.write_bytes(raw.replace(b"17737ec4e77fde834ebcb1b7b5a0df5f",
                                                    b"0123456789abcdef0123456789abcdef"))
                    changed["transcripts"]["central"] = {"name": altered.name,
                                                          "size": altered.stat().st_size,
                                                          "sha256": MODULE.digest(altered)}
                elif mutation == "raw":
                    changed["transcripts"]["mixed"]["sha256"] = "f" * 64
                elif mutation == "safety":
                    changed["safety"]["auto_unlock"] = True
                elif mutation == "denominator":
                    changed["packet_denominator_per_link"] = 9999
                elif mutation == "allowed_loss":
                    changed["allowed_loss_packets"] = 999
                elif mutation == "candidate":
                    changed.update(status="PASS_CANDIDATE", source_clean=False)
                elif mutation == "host_time":
                    changed["host_monotonic_elapsed_ms"] = 1
                elif mutation == "build_revision":
                    changed["images"]["central"]["build"]["core_revision"] = "b" * 40
                elif mutation == "short_build_revision":
                    changed["images"]["central"]["build"]["core_revision"] = revision[:12]
                elif mutation == "readback":
                    changed["images"]["mixed"]["readback"]["sha256"] = "f" * 64
                elif mutation == "probe_binding":
                    reference = changed["images"]["central"]["flash_record"]
                    flash_path = base / reference["path"]
                    flash = MODULE.read_json(flash_path)
                    flash["probe_sha256"] = changed["boards"]["mixed"]["probe_sha256"]
                    flash_path.write_text(json.dumps(flash), encoding="utf-8")
                    reference["sha256"] = MODULE.digest(flash_path)
                elif mutation == "source_binding":
                    changed["firmware_cleanup_contract"]["sha256"] = "f" * 64
                elif mutation == "build_source_binding":
                    image = changed["images"]["central"]
                    record_path = base / image["build_record"]["path"]
                    record_path.write_text(
                        record_path.read_text(encoding="utf-8").replace("1" * 64, "f" * 64),
                        encoding="utf-8",
                    )
                    image["build"]["core_source_sha256"] = "f" * 64
                    image["build"]["record_sha256"] = MODULE.digest(record_path)
                    image["build_record"]["sha256"] = MODULE.digest(record_path)
                else:
                    receipt = changed["execution_receipt"]
                    receipt["roles"]["central"]["transcript_sha256"] = "f" * 64
                    unsigned = {key: value for key, value in receipt.items() if key != "sha256"}
                    encoded = json.dumps(unsigned, sort_keys=True,
                                         separators=(",", ":")).encode("utf-8")
                    receipt["sha256"] = hashlib.sha256(encoded).hexdigest()
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.subTest(mutation=mutation), self.assertRaises((ValueError, RuntimeError)):
                    validate_soak(path, revision, allow_fixture=True)

    def test_closure_rejects_unfinished_catalog_before_any_pass_claim(self):
        """! @brief W02/W05 미완료·dirty·누락 catalog는 입력된 PASS보다 우선합니다. """
        current = {"source_revision": REVISION, "source_clean": True, "prerequisite_blockers": ["M33-W02", "M33-W05"], "inputs": {}}
        document = {"schema_version": 1, "source_revision": REVISION, "source_clean": True, "inputs": {}, "status": "PASS"}
        with self.assertRaisesRegex(ValueError, "prerequisite"):
            MODULE.validate_closure(document, ROOT, current)
        current["prerequisite_blockers"] = []
        current["source_clean"] = False
        with self.assertRaisesRegex(ValueError, "clean"):
            MODULE.validate_closure(document, ROOT, current)
        current["source_clean"] = True
        document["inputs"] = {"made_up": "PASS"}
        with self.assertRaisesRegex(ValueError, "drift"):
            MODULE.validate_closure(document, ROOT, current)

    def test_raw_scope_parser_accepts_bound_unit_fixture(self):
        """! @brief scope별 parser 구조 성공은 물리 closure PASS로 확대하지 않습니다. """
        with tempfile.TemporaryDirectory() as temporary:
            lock = MODULE.read_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
            for field, identifier in (("families", "gap_links"), ("resources", "gap_gatt"),
                                      ("automatic_peers", "gatt")):
                path, raw = self.raw_fixture(Path(temporary) / field, field, identifier)
                with self.subTest(field=field):
                    MODULE.validate_raw_evidence(
                        raw, path, field, identifier, REVISION, lock, allow_fixture=True
                    )

    def test_raw_scope_rejects_arbitrary_denominator_log_image_and_cleanup(self):
        """! @brief 999/999·임의 log·문자열 image·dirty/revision/cleanup 위조를 거부합니다. """
        lock = MODULE.read_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
        for mutation in ("denominator", "log", "image", "dirty", "revision", "cleanup"):
            with tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary) / mutation
                path, raw = self.raw_fixture(base)
                changed = copy.deepcopy(raw)
                if mutation == "denominator":
                    changed.update(denominator=999, completed=999)
                elif mutation == "log":
                    fake = base / "fake.log"
                    fake.write_text("synthetic schema fixture, not hardware evidence", encoding="utf-8")
                    changed["transcripts"]["peripheral"] = {
                        "path": fake.name, "sha256": MODULE.digest(fake)
                    }
                elif mutation == "image":
                    changed["images"] = ["b" * 64]
                elif mutation == "dirty":
                    changed["source_clean"] = False
                elif mutation == "revision":
                    changed["source_revision"] = "b" * 40
                else:
                    reference = changed["transcripts"]["peripheral"]
                    transcript_path = base / reference["path"]
                    transcript = transcript_path.read_text(encoding="ascii")
                    transcript_path.write_text(
                        transcript.replace("active_links=0", "active_links=1"),
                        encoding="ascii",
                    )
                    reference["sha256"] = MODULE.digest(transcript_path)
                with self.subTest(mutation=mutation), self.assertRaises((ValueError, TypeError)):
                    MODULE.validate_raw_evidence(
                        changed, path, "families", "gap_links", REVISION, lock,
                        allow_fixture=True,
                    )

    def test_raw_physical_denominators_and_fixture_boundary(self):
        """! @brief generic raw parser fixture를 보존하되 physical PASS 승격은 항상 거부합니다. """
        lock = MODULE.read_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            path, raw = self.raw_fixture(base, "automatic_peers", "gatt")
            self.assertEqual(20, raw["denominator"])
            self.assertEqual(2, len(raw["boards"]))
            with self.assertRaisesRegex(ValueError, "fixture"):
                MODULE.validate_raw_evidence(
                    raw, path, "automatic_peers", "gatt", REVISION, lock
                )
            forged_physical = copy.deepcopy(raw)
            forged_physical["producer"]["kind"] = "physical_hil"
            with self.assertRaisesRegex(ValueError, "retired"):
                MODULE.validate_raw_evidence(
                    forged_physical, path, "automatic_peers", "gatt", REVISION, lock
                )
            MODULE.validate_raw_evidence(
                raw, path, "automatic_peers", "gatt", REVISION, lock,
                allow_fixture=True,
            )
            for mutation in ("board", "probe", "image"):
                changed = copy.deepcopy(raw)
                if mutation == "board":
                    changed["boards"].pop()
                elif mutation == "probe":
                    changed["boards"][1]["probe_sha256"] = changed["boards"][0]["probe_sha256"]
                else:
                    changed["images"][1] = copy.deepcopy(changed["images"][0])
                    changed["images"][1]["role"] = "scripted_peer"
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    MODULE.validate_raw_evidence(
                        changed, path, "automatic_peers", "gatt", REVISION, lock,
                        allow_fixture=True,
                    )

    def test_raw_physical_gate_precedes_synthetic_image_and_transcript_validation(self):
        """! @brief 합성 image/UART보다 먼저 폐기된 generic physical 경로를 차단합니다. """
        runner = (ROOT / "tests/hil/nu54dk/m33_regression_run.py").read_text(encoding="utf-8")
        for token in ("validate-campaign", "execute-campaign", "campaign_plan(",
                      "shell=False"):
            self.assertIn(token, runner)
        self.assertNotIn('"execute-raw"', runner)
        self.assertNotIn("def execute_raw", runner)
        self.assertNotIn("class RawProductionHardware", runner)
        self.assertNotIn("issue_live_execution_session", runner)
        self.assertFalse(hasattr(MODULE, "issue_live_execution_session"))
        self.assertFalse(hasattr(MODULE, "LiveExecutionSession"))
        lock = MODULE.read_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
        with tempfile.TemporaryDirectory() as temporary:
            path, raw = self.raw_fixture(Path(temporary))
            raw["producer"]["kind"] = "physical_hil"
            with mock.patch.object(
                    MODULE, "validate_image_evidence",
                    side_effect=AssertionError("synthetic validator path reached")) as validator:
                with self.assertRaisesRegex(ValueError, "retired"):
                    MODULE.validate_raw_evidence(
                        raw, path, "families", "gap_links", REVISION, lock
                    )
                validator.assert_not_called()
            with self.assertRaises((ValueError, AssertionError)):
                MODULE.validate_raw_evidence(
                    raw, path, "families", "gap_links", REVISION, lock,
                    allow_physical_audit=True,
                )

    def test_host_verbose_contract_rejects_fabricated_single_test_ok(self):
        """! @brief `Ran 1 ... OK`와 한 개의 가짜 verbose ID를 고정 목록으로 거부합니다. """
        raw = (
            b"test_fake (fake.FakeTests.test_fake) ... ok\n\n"
            b"----------------------------------------------------------------------\n"
            b"Ran 1 test in 0.001s\n\nOK\n"
        )
        parsed = MODULE.parse_unittest_log(raw)
        self.assertEqual(0, parsed["exit_code"])
        self.assertFalse(MODULE.host_log_matches_contract("test_m33_regression.py", parsed))

    def test_host_import_cannot_forge_same_process_receipt(self):
        """! @brief exact ID/log 정보를 복제해도 subprocess runtime receipt는 위조하지 못합니다. """
        raw_sha256 = hashlib.sha256(b"synthetic exact-id log").hexdigest()
        record = {"test": "test_m33_regression.py", "pid": 100,
                  "started_ns": 10, "finished_ns": 20, "exit_code": 0,
                  "raw_sha256": raw_sha256}
        forged = MODULE._HostProcessRuntime(
            object(), record["test"], record["pid"], record["started_ns"],
            record["finished_ns"], record["exit_code"], raw_sha256,
        )
        with self.assertRaisesRegex(ValueError, "same-process"):
            MODULE._validate_host_runtime([record], [forged])
        source = (ROOT / "tools/bluetooth/m33_regression.py").read_text(encoding="utf-8")
        self.assertIn("subprocess.Popen(", source)
        self.assertIn('"status": "AUDIT_ONLY"', source)

    def test_raw_build_producer_is_real_catalog_and_two_pass_target(self):
        """! @brief generic raw build는 폐기되고 실제 runner registry만 production 계획에 남습니다. """
        application = ROOT / "tests/zephyr/m32_regression_soak_hil"
        self.assertFalse((application / "prepare_m33_raw_build.py").exists())
        raw_application = application / "m33_raw_hil"
        self.assertFalse(raw_application.exists() and any(
            path.is_file() for path in raw_application.rglob("*")
        ))
        self.assertEqual(set(MODULE.FAMILY_IDS), set(MODULE.FAMILY_CAMPAIGNS))
        self.assertEqual(set(MODULE.RESOURCE_GROUPS), set(MODULE.RESOURCE_CAMPAIGNS))
        self.assertEqual(set(MODULE.PEER_GROUPS), set(MODULE.AUTOMATIC_PEER_CAMPAIGNS))
        for definition in MODULE.CAMPAIGNS.values():
            self.assertNotIn(MODULE.FORBIDDEN_GENERIC_APPLICATION,
                             definition["applications"])
            runner_path = ROOT / definition["runner"]
            self.assertTrue(runner_path.is_file())
            options, _ = RUNNER._runner_interface(runner_path)
            self.assertTrue(options)
            self.assertTrue(set(RUNNER.OUTPUT_ARGUMENT_MODES) & options)
            for source in definition["applications"]:
                self.assertTrue((ROOT / source).exists())

    def test_actual_campaign_fixture_covers_family_resource_and_peer(self):
        """! @brief 세 scope가 실제 runner plan과 정규화 receipt 없이는 통과하지 않습니다. """
        with tempfile.TemporaryDirectory() as temporary:
            for field, identifier in (("families", "gap_links"),
                                      ("resources", "iso_audio"),
                                      ("automatic_peers", "ancs")):
                base = Path(temporary) / field
                path, document = self.campaign_fixture(base, field, identifier)
                with self.subTest(field=field, identifier=identifier):
                    result = MODULE.validate_campaign_evidence(
                        document, path, field, identifier, REVISION,
                        allow_fixture=True
                    )
                    self.assertEqual("SCHEMA_VALID", result["status"])

    def test_actual_campaign_rejects_generic_plan_cycle_and_semantic_claims(self):
        """! @brief generic application·분모 축소·의미 token 위조를 registry drift로 거부합니다. """
        for mutation in ("generic", "cycles", "semantics"):
            with tempfile.TemporaryDirectory() as temporary:
                path, document = self.campaign_fixture(Path(temporary))
                changed = copy.deepcopy(document)
                if mutation == "generic":
                    changed["campaign_plan"]["campaigns"][0]["applications"] = [{
                        "path": MODULE.FORBIDDEN_GENERIC_APPLICATION,
                        "sha256": "f" * 64,
                    }]
                elif mutation == "cycles":
                    changed["campaign_results"][0]["cycles"] = 1
                else:
                    changed["campaign_results"][0]["semantics"] = ["advertising_only"]
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    MODULE.validate_campaign_evidence(
                        changed, path, "families", "gap_links", REVISION,
                        allow_fixture=True
                    )

    def test_actual_campaign_rejects_duplicate_probe_and_self_receipt(self):
        """! @brief 실제 role 수만 맞춘 probe 재사용과 self-referential evidence를 거부합니다. """
        for mutation in ("probe", "self"):
            with tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                path, document = self.campaign_fixture(base)
                reference = document["campaign_results"][0]["evidence"]
                receipt_path = base / reference["path"]
                receipt = MODULE.read_json(receipt_path)
                if mutation == "probe":
                    receipt["hardware"][1]["probe_sha256"] = \
                        receipt["hardware"][0]["probe_sha256"]
                else:
                    receipt["child_evidence"] = {
                        "path": receipt_path.name,
                        "sha256": reference["sha256"],
                    }
                unsigned = {key: value for key, value in receipt.items() if key != "sha256"}
                receipt["sha256"] = hashlib.sha256(json.dumps(
                    unsigned, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")).hexdigest()
                receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
                reference["sha256"] = MODULE.digest(receipt_path)
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    MODULE.validate_campaign_evidence(
                        document, path, "families", "gap_links", REVISION,
                        allow_fixture=True
                    )

    def test_physical_receipt_revalidates_native_and_all_readback_bytes(self):
        """! @brief receipt부터 sidecar까지 다시 hash해도 image와 다른 readback을 거부합니다. """

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            expected = MODULE.campaign_plan(
                "families", "gap_links"
            )["campaigns"][0]
            statuses = {token: "PASS" for token in expected["semantics"]}
            native_hardware = []
            for index, role in enumerate(expected["roles"], 1):
                image = base / f"native.{role}.image.hex"
                vector = ((0x20000100 + index * 4).to_bytes(4, "little") +
                          (9 + index * 2).to_bytes(4, "little") +
                          bytes([index]))
                image.write_text(
                    self.hex_record(0, 0, vector) + "\n" +
                    self.hex_record(0, 1) + "\n", encoding="ascii"
                )
                build = base / f"native.{role}.build-record"
                build.write_text(f"core_revision: {REVISION}\n", encoding="utf-8")
                probe = hashlib.sha256(role.encode("ascii")).hexdigest()
                ranges = [{
                    "start": start,
                    "length": len(data),
                    "expected_sha256": hashlib.sha256(data).hexdigest(),
                    "observed_sha256": hashlib.sha256(data).hexdigest(),
                    "status": "PASS",
                } for start, data in MODULE.intel_hex_ranges(image)]
                readback = base / f"native.{role}.readback.json"
                readback.write_text(json.dumps({
                    "schema_version": 1,
                    "kind": "m33_exact_program_readback",
                    "status": "PASS",
                    "role": role,
                    "probe_sha256": probe,
                    "image_sha256": MODULE.digest(image),
                    "backend": "pyocd-live-target",
                    "halted": True,
                    "resumed": True,
                    "pre_state": "RUNNING",
                    "post_state": "RUNNING",
                    "restored": True,
                    "ranges": ranges,
                }), encoding="utf-8")
                native_hardware.append({
                    "role": role,
                    "probe_sha256": probe,
                    "image": {"path": image.name,
                              "sha256": MODULE.digest(image)},
                    "build_record": {"path": build.name,
                                     "sha256": MODULE.digest(build)},
                    "flash": {"mode": "pyocd-sector-sw-reset",
                              "programmed_bytes": len(vector),
                              "erase": "sector", "auto_unlock": False,
                              "mass_erase": False,
                              "automatic_recover": False},
                    "readback": {"path": readback.name,
                                 "sha256": MODULE.digest(readback)},
                })
            native = {
                "schema_version": 1,
                "status": "passed",
                "core_revision": REVISION,
                "boards": {},
                "results": {},
                "m33_dispatch_attestation": {
                    "schema_version": 1,
                    "kind": RUNNER.NATIVE_ATTESTATION_KIND,
                    "campaign_id": expected["id"],
                    "source_revision": REVISION,
                    "source_clean": True,
                    "semantic_status": statuses,
                    "cycle_records": [{
                        "cycle": cycle, "status": "PASS",
                        "semantics": dict(statuses),
                    } for cycle in range(1, expected["minimum_cycles"] + 1)],
                    "hardware": native_hardware,
                },
            }
            native_path = base / "native.json"
            native_path.write_text(json.dumps(native), encoding="utf-8")
            with mock.patch.object(RUNNER, "_validate_campaign_native_raw") as raw:
                hardware = RUNNER._validate_native_attestation(
                    native, native_path, expected, REVISION,
                    expected["minimum_cycles"]
                )
                child = {
                    "schema_version": 1,
                    "kind": "m33_campaign_child_result",
                    "campaign_id": expected["id"],
                    "status": "PASS",
                    "source_revision": REVISION,
                    "source_clean": True,
                    "cycles": expected["minimum_cycles"],
                    "semantics": expected["semantics"],
                    "semantic_status": statuses,
                    "hardware": hardware,
                    "native_evidence": {
                        "path": native_path.name,
                        "sha256": MODULE.digest(native_path),
                    },
                }
                child_path = base / "child.json"
                child_path.write_text(json.dumps(child), encoding="utf-8")
                receipt = {
                    "schema_version": 1,
                    "kind": "actual_runner_receipt",
                    "campaign_id": expected["id"],
                    "verification": expected["verification"],
                    "status": "PASS", "source_revision": REVISION,
                    "source_clean": True,
                    "runner_sha256": expected["runner"]["sha256"],
                    "application_sha256": {
                        row["path"]: row["sha256"]
                        for row in expected["applications"]
                    },
                    "roles": expected["roles"],
                    "cycles": expected["minimum_cycles"],
                    "semantics": expected["semantics"],
                    "semantic_status": statuses,
                    "child_evidence": {"path": child_path.name,
                                       "sha256": MODULE.digest(child_path)},
                    "exit_code": 0, "pid": 1,
                    "started_ns": 1, "finished_ns": 2,
                    "command_sha256": "c" * 64,
                    "hardware": hardware,
                }

                def write_receipt() -> tuple[Path, dict]:
                    unsigned = dict(receipt)
                    receipt["sha256"] = hashlib.sha256(json.dumps(
                        unsigned, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")).hexdigest()
                    path = base / "receipt.json"
                    path.write_text(json.dumps(receipt), encoding="utf-8")
                    return path, {"path": path.name,
                                  "sha256": MODULE.digest(path)}

                receipt_path, reference = write_receipt()
                self.assertTrue(MODULE._validate_campaign_receipt(
                    reference, base, expected, REVISION, False, True
                ))
                self.assertGreaterEqual(raw.call_count, 1)

                tampered_path = base / native_hardware[0]["readback"]["path"]
                tampered = MODULE.read_json(tampered_path)
                tampered["ranges"][0]["expected_sha256"] = "f" * 64
                tampered["ranges"][0]["observed_sha256"] = "f" * 64
                tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
                tampered_sha = MODULE.digest(tampered_path)
                native_hardware[0]["readback"]["sha256"] = tampered_sha
                native_path.write_text(json.dumps(native), encoding="utf-8")
                child["native_evidence"]["sha256"] = MODULE.digest(native_path)
                child["hardware"][0]["readback_sha256"] = tampered_sha
                child_path.write_text(json.dumps(child), encoding="utf-8")
                receipt["child_evidence"]["sha256"] = MODULE.digest(child_path)
                receipt["hardware"][0]["readback_sha256"] = tampered_sha
                receipt.pop("sha256")
                receipt_path, reference = write_receipt()
                with self.assertRaisesRegex(ValueError, "all-range readback"):
                    MODULE._validate_campaign_receipt(
                        reference, base, expected, REVISION, False, True
                    )

    def test_dispatcher_rejects_command_injection_and_unknown_option(self):
        """! @brief shell meta 문자와 등록 runner에 없는 option은 실행 전에 거부합니다. """
        for mutation in ("injection", "unknown"):
            with tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                _, spec, _, _, _ = self.execution_spec_fixture(base)
                if mutation == "injection":
                    spec["campaigns"][0]["arguments"][0]["values"][0] += ";whoami"
                else:
                    spec["campaigns"][0]["arguments"][0]["option"] = "--arbitrary-runner"
                with mock.patch.object(
                        RUNNER, "_git_identity", return_value=(REVISION, True)):
                    with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                        RUNNER._validate_execution_spec(
                            spec, base / "result.json", ROOT
                        )

    def test_dispatcher_rejects_other_runner_reduced_cycle_and_board_reuse(self):
        """! @brief 다른 runner·최소 cycle 축소·probe 재사용을 실행 전에 거부합니다. """
        for mutation in ("runner", "cycles", "boards"):
            with tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                _, spec, _, _, _ = self.execution_spec_fixture(base)
                if mutation == "runner":
                    other = MODULE.campaign_plan(
                        "families", "privacy"
                    )["campaigns"][0]["runner"]
                    spec["campaigns"][0]["runner"] = other
                else:
                    if mutation == "cycles":
                        spec["campaigns"][0]["cycles"] -= 1
                    else:
                        spec["campaigns"][0]["boards"][1]["probe_sha256"] = \
                            spec["campaigns"][0]["boards"][0]["probe_sha256"]
                with mock.patch.object(
                        RUNNER, "_git_identity", return_value=(REVISION, True)):
                    with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                        RUNNER._validate_execution_spec(
                            spec, base / "result.json", ROOT
                        )

    def test_dispatcher_rejects_historical_or_preexisting_evidence(self):
        """! @brief 과거 revision spec과 실행 전에 존재한 child evidence를 새 결과로 받지 않습니다. """
        for mutation in ("revision", "existing"):
            with tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                _, spec, native, child, adapter = self.execution_spec_fixture(base)
                if mutation == "revision":
                    spec["source_revision"] = "b" * 40
                else:
                    native.write_text(json.dumps(adapter), encoding="utf-8")
                with mock.patch.object(
                        RUNNER, "_git_identity", return_value=(REVISION, True)):
                    with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                        RUNNER._validate_execution_spec(
                            spec, base / "result.json", ROOT
                        )

    def test_dispatcher_rejects_raw_probe_identity_before_log_persistence(self):
        """! @brief spec·argv·stdout의 raw UID가 증거 파일로 남기 전에 거부됩니다. """
        raw_uid = b"00112233445566778899aabbccddeeff"
        probe_sha256 = hashlib.sha256(raw_uid).hexdigest()
        marker = raw_uid + b"\n"
        with self.assertRaisesRegex(ValueError, "raw probe identity"):
            RUNNER._reject_raw_probe_identity_bytes(
                marker, "unit log", {probe_sha256}
            )
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            spec_path, spec, native, _, adapter = self.execution_spec_fixture(base)
            spec["campaigns"][0]["boards"][0]["probe_sha256"] = probe_sha256
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            encoded = json.dumps(spec, sort_keys=True)
            self.assertNotIn("daplink_uid", encoded)
            self.assertNotIn("board-id", encoded)

            class LeakingProcess:
                """! @brief raw UID를 출력하는 실패 전 unit runner입니다. """

                def __init__(self, command, **_kwargs):
                    self.pid = 77
                    self.returncode = 0

                def communicate(self, timeout=None):
                    native.write_text(json.dumps(adapter), encoding="utf-8")
                    return marker, None

                def kill(self):
                    raise AssertionError("unit runner must not time out")

            output = base / "result.json"
            with mock.patch.object(
                    RUNNER, "_git_identity", return_value=(REVISION, True)), \
                    mock.patch.object(
                        RUNNER, "campaign_dispatch_matrix",
                        return_value={"campaigns": [{
                            "id": "m28_link", "status": "DISPATCH_READY",
                            "central_direct_readback": True,
                        }]}
                    ), \
                    mock.patch.object(RUNNER.subprocess, "Popen", LeakingProcess):
                with self.assertRaisesRegex(ValueError, "raw probe identity"):
                    RUNNER.execute_campaign_spec(spec_path, output, ROOT)
            self.assertFalse((base / "campaign.m28_link.log").exists())

    def test_dispatcher_runs_registered_runner_without_shell_and_normalizes(self):
        """! @brief unit fake process로 shell 없는 실행과 fresh adapter receipt 결합을 확인합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            spec_path, _, native, child, adapter = self.execution_spec_fixture(base)
            output = base / "result.json"
            observed = {}
            execution_order = []
            hardware = adapter["m33_dispatch_attestation"]["hardware"]

            class FakeProcess:
                """! @brief 보드에 접근하지 않고 child adapter만 생성하는 unit process입니다. """
                def __init__(self, command, **kwargs):
                    execution_order.append("runner")
                    observed["command"] = command
                    observed["kwargs"] = kwargs
                    self.pid = 321
                    self.returncode = 0

                def communicate(self, timeout=None):
                    observed["timeout"] = timeout
                    native.write_text(json.dumps(adapter), encoding="utf-8")
                    return b"unit runner pass\n", None

                def kill(self):
                    raise AssertionError("unit runner must not time out")

            with mock.patch.object(
                    RUNNER, "_git_identity", return_value=(REVISION, True)), \
                    mock.patch.object(
                        RUNNER, "campaign_dispatch_matrix",
                        return_value={"campaigns": [{"id": "m28_link",
                                                     "status": "DISPATCH_READY",
                                                     "central_direct_readback": True}]}), \
                    mock.patch.object(
                        RUNNER, "_central_program_hardware",
                        return_value=adapter["m33_dispatch_attestation"]["hardware"]
                    ) as central_readback, \
                    mock.patch.object(
                        RUNNER, "_restore_campaign_state",
                        side_effect=lambda *_args, **_kwargs:
                        execution_order.append("restore")
                    ) as state_restore, \
                    mock.patch.object(
                        RUNNER, "revalidate_stored_campaign_bundle",
                        side_effect=lambda path, expected, revision, cycles:
                        MODULE.read_json(path)["hardware"]
                    ), \
                    mock.patch.object(RUNNER, "_validate_legacy_native_raw"), \
                    mock.patch.object(RUNNER.subprocess, "Popen", FakeProcess):
                result = RUNNER.execute_campaign_spec(spec_path, output, ROOT)
            self.assertEqual("PASS", result["status"])
            state_restore.assert_called_once()
            self.assertEqual(["restore", "runner"], execution_order)
            central_readback.assert_called_once()
            self.assertTrue(output.is_file())
            self.assertIs(observed["kwargs"]["shell"], False)
            self.assertEqual(sys.executable, observed["command"][0])
            self.assertEqual("--evidence", observed["command"][-2])
            self.assertEqual(str(native), observed["command"][-1])
            self.assertEqual(60, observed["timeout"])
            receipt = base / "campaign.m28_link.receipt.json"
            reused_spec = json.loads(spec_path.read_text(encoding="utf-8"))
            reused_spec["campaigns"][0]["arguments"] = []
            reused_spec["campaigns"][0]["reuse_receipt"] = {
                "path": receipt.name,
                "sha256": MODULE.digest(receipt),
            }
            reused_path = base / "reuse-spec.json"
            reused_path.write_text(json.dumps(reused_spec), encoding="utf-8")
            with mock.patch.object(
                    RUNNER, "_git_identity", return_value=(REVISION, True)), \
                    mock.patch.object(
                        RUNNER, "revalidate_stored_campaign_bundle",
                        side_effect=lambda path, expected, revision, cycles:
                        MODULE.read_json(path)["hardware"]
                    ), \
                    mock.patch.object(
                        RUNNER.subprocess, "Popen",
                        side_effect=AssertionError("reuse must not rerun native runner")):
                reused = RUNNER.execute_campaign_spec(
                    reused_path, base / "reuse-result.json", ROOT
                )
            self.assertEqual("PASS", reused["status"])
            self.assertEqual(
                result["campaign_results"][0]["evidence"],
                reused["campaign_results"][0]["evidence"],
            )

    def test_pre_run_restore_contract_targets_only_stateful_runtime_groups(self):
        """! @brief 20/31/33 group만 실행 직전 exact 상태 복원을 요구합니다. """

        self.assertEqual({
            "m31_bap_duplex": "direct",
            "m33_ecosystem": "ecosystem_isolated",
            "m33_diagnostics_dtm": "third_idle",
        }, RUNNER.PRE_RUN_STATE_RESTORE)
        source = inspect.getsource(RUNNER._restore_campaign_state)
        self.assertIn("defer_reset=True", source)
        self.assertIn("reset_target_pyocd_sha256", source)
        self.assertIn("readback_programmed_images_by_hash", source)
        self.assertIn("validate_programming_receipt", source)
        self.assertIn('"automatic_recover": False', source)
        self.assertIn('"mass_erase": False', source)
        self.assertNotIn("chip_erase", source)

    def test_pre_run_restore_fixture_programs_resets_reads_back_and_audits(self):
        """! @brief 보드 없는 fixture로 direct/third 복원 순서와 receipt를 검증합니다. """

        import m33_diagnostics
        import m33_w06_runtime_fixture

        def fake_readback(probes, images, sidecars):
            records = {}
            for role, image in images.items():
                ranges = [
                    {
                        "start": start,
                        "length": len(raw),
                        "expected_sha256": hashlib.sha256(raw).hexdigest(),
                        "observed_sha256": hashlib.sha256(raw).hexdigest(),
                        "status": "PASS",
                    }
                    for start, raw in RUNNER.intel_hex_ranges(image)
                ]
                record = {
                    "schema_version": 1,
                    "kind": "m33_exact_program_readback",
                    "status": "PASS",
                    "role": role,
                    "probe_sha256": probes[role],
                    "image_sha256": MODULE.digest(image),
                    "backend": "pyocd-live-target",
                    "halted": True,
                    "resumed": True,
                    "pre_state": "RUNNING",
                    "post_state": "RUNNING",
                    "restored": True,
                    "ranges": ranges,
                }
                sidecars[role]["readback"].write_text(
                    json.dumps(record), encoding="utf-8"
                )
                records[role] = record
            return records, object()

        for mode, campaign_id, roles in (
                ("direct", "m31_bap_duplex", ("client", "server")),
                ("third_idle", "m33_diagnostics_dtm", ("third",))):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                images = {}
                records = {}
                probes = {}
                for index, role in enumerate(roles, 1):
                    image = base / f"{role}.hex"
                    image.write_text(
                        ":080000000102030405060708D4\n:00000001FF\n",
                        encoding="ascii"
                    )
                    record = base / f"{role}.record"
                    record.write_text(f"record:{role}\n", encoding="ascii")
                    images[role] = image
                    records[role] = record
                    probes[role] = hashlib.sha256(role.encode("ascii")).hexdigest()
                contract_input = base / "contract.json"
                contract_input.write_text("{}\n", encoding="utf-8")
                plan = {
                    "mode": mode,
                    "campaign_id": campaign_id,
                    "revision": REVISION,
                    "roles": roles,
                    "images": images,
                    "records": records,
                    "probes": probes,
                    "all_probes": dict(probes),
                    "contract_inputs": {"fixture": contract_input},
                }
                if mode == "third_idle":
                    tx = hashlib.sha256(b"tx").hexdigest()
                    rx = hashlib.sha256(b"rx").hexdigest()
                    plan.update({
                        "all_probes": {"tx": tx, "rx": rx,
                                       "third": probes["third"]},
                        "ports": {"tx": "COM1", "rx": "COM2"},
                        "fixture": contract_input,
                        "watcher": {"data": {"nonce": "1" * 32,
                                              "port": "COM3"}},
                    })
                plan = RUNNER._seal_restore_plan(plan)
                expected = {"id": campaign_id}
                native = base / "native" / "result.json"
                hardware_order = []

                def flash(role, *_args, **_kwargs):
                    hardware_order.append(f"flash:{role}")
                    self.assertEqual(
                        plan["input_sha256"]["images"][role],
                        _kwargs.get("expected_sha256"),
                    )
                    return "pyocd-sector-no-reset", "8"

                def reset(role, *_args):
                    hardware_order.append(f"reset:{role}")
                    return "pyocd-v2-sw-reset"

                def stop_watcher(_plan, transcript_path):
                    hardware_order.append("stop:third")
                    nonce = "1" * 32
                    transcript_path.write_text(
                        "\n".join((
                            f"M33PROFILE|1|READY|role=watcher|core={REVISION}|nonce=",
                            f"M33PROFILE|1|SERVER_STATS|role=watcher|core={REVISION}|nonce={nonce}",
                            f"M33PROFILE|1|STOPPED|role=watcher|core={REVISION}|nonce={nonce}|native_links=0|links=0|pending=0|scan=0|advertising=0|watchdog=0",
                        )) + "\n",
                        encoding="ascii",
                    )
                    return {
                        "port_binding": "probe_sha256_verified",
                        "ready": "PASS",
                        "server_stats": "PASS",
                        "stopped": "PASS",
                        "serial_close": "PASS",
                        "transcript": {
                            "path": transcript_path.name,
                            "sha256": MODULE.digest(transcript_path),
                        },
                    }

                with mock.patch.object(
                        RUNNER, "_state_restore_plan", return_value=plan), \
                        mock.patch.object(
                            RUNNER, "_git_identity",
                            return_value=(REVISION, True)), \
                        mock.patch.object(
                            RUNNER, "readback_programmed_images_by_hash",
                            side_effect=lambda *args: (
                                hardware_order.append("readback"),
                                fake_readback(*args),
                            )[1]), \
                        mock.patch.object(
                            RUNNER, "validate_programming_receipt"), \
                        mock.patch.object(
                            RUNNER, "_stop_restored_watcher",
                            side_effect=stop_watcher), \
                        mock.patch.object(
                            m33_diagnostics, "HashedProbeLocks",
                            side_effect=lambda _hashes: nullcontext()), \
                        mock.patch(
                            "ble_pair_hil_common.flash_image_pyocd_sha256",
                            side_effect=flash), \
                        mock.patch(
                            "ble_pair_hil_common.reset_target_pyocd_sha256",
                            side_effect=reset), \
                        mock.patch.object(
                            m33_w06_runtime_fixture, "audit_third_board",
                            side_effect=lambda *_args: (
                                hardware_order.append("audit:third"),
                                {
                                    "probe_sha256": probes[roles[0]],
                                    "state": "halted_verified",
                                },
                            )[1]), \
                        mock.patch.object(
                            m33_w06_runtime_fixture,
                            "validate_third_board_audit",
                            return_value={}):
                    with RUNNER._campaign_probe_authority(
                            plan, native) as (_environment, authority):
                        receipt_path = RUNNER._restore_campaign_state(
                            expected, {}, native, REVISION, ROOT,
                            plan=plan, authority=authority
                        )
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                self.assertEqual("m33_campaign_pre_run_state_restore",
                                 receipt["kind"])
                self.assertEqual(mode, receipt["mode"])
                self.assertEqual(list(roles),
                                 [row["role"] for row in receipt["hardware"]])
                expected_order = [
                    *(f"flash:{role}" for role in roles),
                    *(f"reset:{role}" for role in roles),
                    "readback",
                ]
                if mode == "third_idle":
                    expected_order.extend(("stop:third", "audit:third"))
                self.assertEqual(expected_order, hardware_order)
                self.assertTrue(all(
                    row["flash"]["erase"] == "sector" and
                    row["flash"]["auto_unlock"] is False and
                    row["flash"]["mass_erase"] is False and
                    row["flash"]["automatic_recover"] is False
                    for row in receipt["hardware"]
                ))
                if mode == "third_idle":
                    self.assertEqual("PASS", receipt["state"]["stopped"])
                    self.assertEqual("halted_verified",
                                     receipt["state"]["idle_audit"]["state"])
                    transcript = (receipt_path.parent /
                                  receipt["state"]["transcript"]["path"])
                    lines = transcript.read_text(encoding="ascii").splitlines()
                    transcript.write_text(
                        "\n".join(reversed(lines)) + "\n", encoding="ascii"
                    )
                    receipt["state"]["transcript"]["sha256"] = \
                        MODULE.digest(transcript)
                    unsigned = {key: value for key, value in receipt.items()
                                if key != "sha256"}
                    receipt["sha256"] = hashlib.sha256(json.dumps(
                        unsigned, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")).hexdigest()
                    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
                    with mock.patch.object(
                            RUNNER, "_state_restore_plan", return_value=plan), \
                            mock.patch.object(
                                m33_w06_runtime_fixture,
                                "validate_third_board_audit",
                                return_value={}):
                        with self.assertRaisesRegex(ValueError, "lifecycle"):
                            RUNNER._validate_state_restore_receipt(
                                receipt_path, expected, {}, REVISION, ROOT
                            )
                else:
                    role = roles[0]
                    original_receipt = copy.deepcopy(receipt)
                    for field, changed in (
                            ("mode", "pyocd-sector-sw-reset"),
                            ("programmed_bytes", 1)):
                        receipt = copy.deepcopy(original_receipt)
                        receipt["hardware"][0]["flash"][field] = changed
                        unsigned = {
                            key: value for key, value in receipt.items()
                            if key != "sha256"
                        }
                        receipt["sha256"] = hashlib.sha256(json.dumps(
                            unsigned, sort_keys=True, separators=(",", ":")
                        ).encode("utf-8")).hexdigest()
                        receipt_path.write_text(
                            json.dumps(receipt), encoding="utf-8"
                        )
                        with mock.patch.object(
                                RUNNER, "_state_restore_plan",
                                return_value=plan):
                            with self.assertRaisesRegex(
                                    ValueError, "exact no-reset"):
                                RUNNER._validate_state_restore_receipt(
                                    receipt_path, expected, {}, REVISION, ROOT
                                )
                    receipt = original_receipt
                    receipt_path.write_text(
                        json.dumps(receipt), encoding="utf-8"
                    )
                    reference = receipt["hardware"][0]["readback"]
                    readback = base / "native" / reference["path"]
                    value = json.loads(readback.read_text(encoding="utf-8"))
                    value.update({
                        "pre_state": "HALTED",
                        "post_state": "HALTED",
                        "resumed": False,
                    })
                    readback.write_text(json.dumps(value), encoding="utf-8")
                    reference["sha256"] = MODULE.digest(readback)
                    receipt["post_reset"][role] = {
                        "pre_state": "HALTED",
                        "post_state": "HALTED",
                        "resumed": False,
                        "restored": True,
                    }
                    unsigned = {key: value for key, value in receipt.items()
                                if key != "sha256"}
                    receipt["sha256"] = hashlib.sha256(json.dumps(
                        unsigned, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")).hexdigest()
                    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
                    with mock.patch.object(
                            RUNNER, "_state_restore_plan", return_value=plan):
                        with self.assertRaisesRegex(ValueError, "RUNNING"):
                            RUNNER._validate_state_restore_receipt(
                                receipt_path, expected, {}, REVISION, ROOT
                            )

    def test_restore_authority_is_continuous_and_child_lock_is_private(self):
        """! @brief restore부터 child 증거 확정까지 parent lock gap을 허용하지 않습니다. """

        import m33_diagnostics

        events = []

        class Lock:
            """! @brief unit event로 parent lock lifetime을 기록합니다. """

            def __init__(self, hashes):
                self.hashes = hashes

            def __enter__(self):
                events.append("lock-enter")
                return self

            def __exit__(self, *_args):
                events.append("lock-exit")

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            native = base / "native" / "result.json"
            plan = {"all_probes": {"a": "a" * 64, "b": "b" * 64}}
            with mock.patch.object(m33_diagnostics, "HashedProbeLocks", Lock):
                with RUNNER._campaign_probe_authority(
                        plan, native) as (environment, authority):
                    child_lock_root = Path(environment["TEMP"])
                    self.assertTrue(authority.active)
                    self.assertTrue(child_lock_root.is_dir())
                    self.assertEqual(environment["TEMP"], environment["TMP"])
                    events.extend(("restore", "child", "evidence"))
            self.assertFalse(authority.active)
            self.assertFalse(child_lock_root.exists())
        self.assertEqual(
            ["lock-enter", "restore", "child", "evidence", "lock-exit"],
            events,
        )
        source = inspect.getsource(RUNNER._run_pending_campaign)
        self.assertLess(source.index("_campaign_probe_authority"),
                        source.index("_restore_campaign_state"))
        self.assertLess(source.index("_restore_campaign_state"),
                        source.index("subprocess.Popen"))
        self.assertLess(source.index("subprocess.Popen"),
                        source.index("_write_new_json"))
        with self.assertRaisesRegex(ValueError, "active parent probe-lock"):
            RUNNER._restore_campaign_state(
                {"id": "fixture"}, {}, Path("unused.json"), REVISION,
                plan=plan
            )

    def test_restore_copy_rejects_symlink_raw_uid_and_partial_reuse(self):
        """! @brief contract copy의 symlink/raw UID/부분 root 재사용을 fail-stop합니다. """

        import m33_sdk_risk_common as risk_common
        import m33_diagnostics

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            raw_uid = "00112233445566778899aabbccddeeff"
            probe = hashlib.sha256(raw_uid.encode("ascii")).hexdigest()
            exposed = base / "exposed.txt"
            exposed.write_text(f"probe_uid={raw_uid}\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "raw probe identity"):
                RUNNER._copy_new_regular(
                    exposed, base / "copy.txt", "contract", {probe}
                )
            source = base / "source.txt"
            source.write_text("safe\n", encoding="ascii")
            snapshot = MODULE.digest(source)
            source.write_text("replaced\n", encoding="ascii")
            plan = {
                "images": {"role": source},
                "records": {"role": source},
                "contract_inputs": {"config": source},
                "validated_sha256": {
                    "images": {"role": snapshot},
                    "records": {"role": snapshot},
                    "contract": {"config": snapshot},
                },
            }
            with self.assertRaisesRegex(ValueError, "provenance validation"):
                RUNNER._seal_restore_plan(plan)
            with self.assertRaisesRegex(ValueError, "after plan validation"):
                RUNNER._copy_new_regular(
                    source, base / "changed-copy.txt", "contract", {probe},
                    snapshot
                )
            source.write_text("safe\n", encoding="ascii")
            replacement = base / "replacement.txt"
            replacement.write_text("swap\n", encoding="ascii")
            real_open = RUNNER.os.open
            swapped = False

            def swap_before_open(path, flags, *args):
                nonlocal swapped
                if Path(path) == source and not swapped:
                    swapped = True
                    replacement.replace(source)
                return real_open(path, flags, *args)

            with mock.patch.object(
                    RUNNER.os, "open", side_effect=swap_before_open):
                with self.assertRaisesRegex(ValueError, "changed while reading"):
                    RUNNER._read_regular_bytes(source, "contract source")
            source.write_text("safe\n", encoding="ascii")
            target = base / "target.txt"
            RUNNER._copy_new_regular(source, target, "contract", {probe})
            with self.assertRaises(FileExistsError):
                RUNNER._copy_new_regular(source, target, "contract", {probe})
            readback = base / "readback.json"
            risk_common._write_new_regular_json(readback, {"status": "PASS"})
            with self.assertRaises(FileExistsError):
                risk_common._write_new_regular_json(
                    readback, {"status": "FORGED"}
                )
            dangling = base / "dangling-readback.json"
            try:
                dangling.symlink_to(base / "missing.json")
            except OSError:
                dangling = None
            if dangling is not None:
                with self.assertRaises(FileExistsError):
                    risk_common._write_new_regular_json(
                        dangling, {"status": "FORGED"}
                    )
            link = base / "source-link.txt"
            try:
                link.symlink_to(source)
            except OSError:
                link = None
            if link is not None:
                with self.assertRaisesRegex(ValueError, "non-symlink"):
                    RUNNER._copy_new_regular(
                        link, base / "link-copy.txt", "contract", {probe}
                    )
            descriptor_files = {}
            for label in m33_diagnostics.THIRD_IDLE_FILES:
                described = base / f"{label}.bin"
                described.write_bytes(label.encode("ascii"))
                descriptor_files[label] = {
                    "path": described.name,
                    "sha256": MODULE.digest(described),
                }
            fixture = base / "third-idle-fixture.json"
            descriptor = {"files": descriptor_files}
            missing = copy.deepcopy(descriptor)
            missing["files"].pop("elf")
            fixture.write_text(json.dumps(missing), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "denominator"):
                RUNNER._watcher_fixture_bundle(
                    fixture, MODULE.digest(fixture), probe, REVISION
                )
            escaped = copy.deepcopy(descriptor)
            escaped["files"]["elf"]["path"] = "../elf.bin"
            fixture.write_text(json.dumps(escaped), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "descriptor"):
                RUNNER._watcher_fixture_bundle(
                    fixture, MODULE.digest(fixture), probe, REVISION
                )

    def test_third_idle_audit_validator_replays_all_stored_fields(self):
        """! @brief producer validator가 radio/readback/lifecycle 위조를 재검증합니다. """

        import m33_diagnostics
        import m33_w06_runtime_fixture as runtime_fixture

        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "fixture.json"
            fixture.write_text("{}\n", encoding="utf-8")
            probes = {
                role: hashlib.sha256(role.encode("ascii")).hexdigest()
                for role in ("client", "peer", "third")
            }
            ports = {"client": "COM1", "peer": "COM2"}
            image_raw = b"12345678"
            nonce = "1" * 32
            nonce_raw = nonce.encode("ascii") + b"\0"
            watcher = {
                "data": {
                    "nonce": nonce,
                    "files": {"elf": {"sha256": "e" * 64}},
                    "revisions": {"core": REVISION},
                },
                "image": {
                    "ranges": [(0, image_raw)],
                    "sha256": "i" * 64,
                },
                "symbols": {
                    "nonce": {
                        "symbol": "fixture_nonce",
                        "address": 0x20000000,
                        "size": 33,
                    },
                },
            }
            route_addresses = [
                m33_diagnostics.RADIO_BASE + offset
                for offset in (
                    *m33_diagnostics.RADIO_SUBSCRIBE,
                    *m33_diagnostics.RADIO_PUBLISH,
                )
            ]
            route_addresses.extend(
                base + offset
                for base in m33_diagnostics.WDT_BASES
                for offset in m33_diagnostics.WDT_ROUTES
            )
            registers = {"dhcsr_halt": m33_diagnostics.DHCSR_HALTED}
            registers.update({f"0x{address:08x}": 0
                              for address in route_addresses})
            registers[f"0x{m33_diagnostics.RADIO_BASE + 0x400:08x}"] = 0
            registers[f"0x{m33_diagnostics.RADIO_STATE:08x}"] = 0
            for base in m33_diagnostics.WDT_BASES:
                registers.update({
                    f"0x{base + 0x100:08x}": 0,
                    f"0x{base + 0x400:08x}": 0,
                    f"0x{base + 0x50C:08x}": 0,
                })
            audit = {
                "probe_sha256": probes["third"],
                "state": "halted_verified",
                "radio": {
                    "cpu": "HALTED",
                    "radio_state_address": m33_diagnostics.RADIO_STATE,
                    "radio_state": m33_diagnostics.RADIO_DISABLED,
                    "registers": registers,
                    "reset_observed": False,
                    "read_only": True,
                },
                "readback": [{
                    "start": 0,
                    "length": len(image_raw),
                    "expected_sha256": hashlib.sha256(image_raw).hexdigest(),
                    "observed_sha256": hashlib.sha256(image_raw).hexdigest(),
                    "status": "PASS",
                }],
                "lifecycle_ram": [{
                    **watcher["symbols"]["nonce"],
                    "name": "nonce",
                    "read_sha256": hashlib.sha256(nonce_raw).hexdigest(),
                    "read_value": nonce,
                    "expected_sha256": hashlib.sha256(nonce_raw).hexdigest(),
                    "status": "PASS",
                    "elf_sha256": "e" * 64,
                    "image_sha256": "i" * 64,
                    "source_revision": REVISION,
                }],
                "fixture_sha256": runtime_fixture.digest(fixture),
            }
            with mock.patch.object(
                    m33_diagnostics, "load_watcher_fixture",
                    return_value=watcher):
                runtime_fixture.validate_third_board_audit(
                    audit, probes, ports, fixture
                )
                changed = copy.deepcopy(audit)
                changed["lifecycle_ram"][0]["status"] = "FAIL"
                with self.assertRaisesRegex(
                        runtime_fixture.RuntimeFixtureFailure,
                        "lifecycle RAM"):
                    runtime_fixture.validate_third_board_audit(
                        changed, probes, ports, fixture
                    )

    def test_modern_direct_adapter_rebuilds_raw_cycle_denominator(self):
        """! @brief modern attestation 숫자 대신 runner 고유 측정 원시값을 재검증합니다. """

        expected = next(
            row for row in MODULE.campaign_plan("families", "iso")["campaigns"]
            if row["id"] == "m31_iso_cis"
        )
        nonces = [f"nonce-{index}" for index in range(20)]
        measurement = {
            "cycles": 20,
            "total_sent": 2000,
            "total_received": 1980,
            "minimum_received": 99,
            "invalid_or_lost": 20,
        }
        statuses = {token: "PASS" for token in expected["semantics"]}
        records = [
            {"cycle": cycle, "status": "PASS", "semantics": dict(statuses)}
            for cycle in range(1, 21)
        ]
        native = {
            "nonces": nonces,
            "measurement": measurement,
            "cleanup": {
                role: {"stop": "PASS", "serial_close": "PASS"}
                for role in expected["roles"]
            },
            "dispatch_cycle_records": records,
            "m33_dispatch_attestation": {"cycle_records": records},
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "native.json"
            transcript = path.with_suffix(".transcript.log")
            transcript.write_bytes(b"strict parser transcript\n")
            native["transcript_sha256"] = MODULE.digest(transcript)
            RUNNER._validate_modern_direct_native_raw(native, path, expected)
            changed = copy.deepcopy(native)
            changed["measurement"]["total_received"] = 1979
            with self.assertRaises(Exception):
                RUNNER._validate_modern_direct_native_raw(changed, path, expected)
            changed = copy.deepcopy(native)
            changed["cleanup"][expected["roles"][0]]["stop"] = "NOT_CONFIRMED"
            with self.assertRaisesRegex(ValueError, "cleanup"):
                RUNNER._validate_modern_direct_native_raw(changed, path, expected)

    def test_legacy_multi_adapter_requires_twenty_hash_only_sessions(self):
        """! @brief multi runner의 20개 nonce·cleanup·hash-only 장치 증거를 재생합니다. """
        import m29_ble_multi_protocol as protocol

        expected = {"id": "m29_multi", **MODULE.CAMPAIGNS["m29_multi"]}
        roles = tuple(expected["roles"])
        nonces = tuple(f"{index:032x}" for index in range(protocol.CYCLE_COUNT))
        parsed = {}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            transcripts = {}
            for role in roles:
                raw = (
                    "\n".join(protocol.expected_campaign_lines(
                        role, nonces, REVISION
                    )) + "\n"
                ).encode("ascii")
                path = root / f"{role}.transcript.log"
                path.write_bytes(raw)
                transcripts[role] = {
                    "name": path.name,
                    "size": len(raw),
                    "sha256": MODULE.digest(path),
                }
                parsed[role] = protocol.parse_role_campaign(
                    raw, role, nonces, REVISION
                )
            cycles = []
            for index, nonce in enumerate(nonces):
                results = {}
                cleanup = {}
                for role in roles:
                    value = RUNNER.asdict(parsed[role][index])
                    cleanup[role] = {
                        "active_links": value.pop("cleanup_active_links"),
                        "pending_operations": value.pop(
                            "cleanup_pending_operations"
                        ),
                        "buffers": value.pop("cleanup_buffers"),
                        "status": value.pop("cleanup_status"),
                    }
                    results[role] = value
                cycles.append({"cycle": index + 1, "nonce": nonce,
                               "results": results, "cleanup": cleanup})
            native = {
                "schema_version": 2,
                "status": "passed",
                "core_revision": REVISION,
                "boards": {
                    role: {
                        "probe_sha256": hashlib.sha256(
                            role.encode("ascii")
                        ).hexdigest(),
                        "msd_root": f"D:/{role}",
                        "uart_port": f"COM{index + 1}",
                    }
                    for index, role in enumerate(roles)
                },
                "images": {
                    role: {
                        "flash_sequence": "pyocd-sector-no-reset",
                        "flash_bytes": "64",
                        "build_record": {"record_sha256": "a" * 64},
                    }
                    for role in roles
                },
                "transcripts": transcripts,
                "cycles": cycles,
                "termination": {
                    "serial_closed": {role: True for role in roles},
                    "all_serial_closed": True,
                },
                "coverage": {"independent_sessions": 20},
            }
            path = root / "native.json"
            path.write_text(json.dumps(native), encoding="utf-8")
            RUNNER._validate_legacy_native_raw(
                native, path, expected, REVISION
            )
            changed = copy.deepcopy(native)
            changed["cycles"][1]["nonce"] = changed["cycles"][0]["nonce"]
            with self.assertRaisesRegex(ValueError, "nonce"):
                RUNNER._validate_legacy_native_raw(
                    changed, path, expected, REVISION
                )
            changed = copy.deepcopy(native)
            changed["boards"][roles[0]]["daplink_uid"] = "raw-secret"
            with self.assertRaisesRegex(ValueError, "hash-only"):
                RUNNER._validate_legacy_native_raw(
                    changed, path, expected, REVISION
                )

    def test_native_attestation_cannot_skip_derived_raw_validators(self):
        """! @brief attestation이 있어도 legacy·flat·build raw parser를 항상 호출합니다. """
        expected_by_id = {}
        for field, registry in MODULE.CAMPAIGN_REGISTRIES.items():
            for identifier in registry:
                for campaign in MODULE.campaign_plan(field, identifier)["campaigns"]:
                    expected_by_id.setdefault(campaign["id"], campaign)
        cases = (
            ("m28_link", "_validate_legacy_native_raw"),
            ("m30_dfu", "_validate_m30_native_raw"),
            ("m31_bap_duplex", "_validate_flat_native_raw"),
            ("m33_diagnostics_build", "_validate_diagnostic_build_raw"),
        )
        for campaign_id, validator_name in cases:
            with self.subTest(campaign_id=campaign_id), mock.patch.object(
                    RUNNER, validator_name) as validator:
                native = {"m33_dispatch_attestation": {"cycle_records": []}}
                RUNNER._validate_campaign_native_raw(
                    native, Path("native.json"), expected_by_id[campaign_id], REVISION
                )
                validator.assert_called_once()

    def test_native_adapter_registry_and_schema_families_are_fail_closed(self):
        """! @brief 48개 campaign adapter와 7개 native schema의 원시 분모·byte 경계를 검증합니다. """
        self.assertEqual(set(MODULE.CAMPAIGNS), set(RUNNER.NATIVE_ADAPTER_REGISTRY))
        self.assertEqual(48, len(RUNNER.NATIVE_ADAPTER_REGISTRY))
        references = [campaign_id
                      for registry in MODULE.CAMPAIGN_REGISTRIES.values()
                      for campaign_ids in registry.values()
                      for campaign_id in campaign_ids]
        self.assertEqual(82, len(references))
        self.assertEqual(set(MODULE.CAMPAIGNS), set(references))
        representatives = {
            "legacy_hil": "m28_link",
            "modern_hil": "m33_cis_acl_risk",
            "flat_hil": "m31_bap_duplex",
            "profile_hil": "m33_profiles_native",
            "ecosystem_hil": "m33_ecosystem",
            "build_semantic": "m33_diagnostics_build",
            "diagnostic_hil": "m33_diagnostics_dtm",
        }
        raw_validator_by_family = {
            "legacy_hil": "_validate_legacy_native_raw",
            "flat_hil": "_validate_flat_native_raw",
            "ecosystem_hil": "_validate_ecosystem_native_raw",
            "build_semantic": "_validate_diagnostic_build_raw",
            "diagnostic_hil": "_validate_diagnostics_campaign_native_raw",
        }

        def raw_context(family):
            """! @brief schema-family fixture에서는 별도 raw parser 단위검사를 중복하지 않습니다. """
            name = raw_validator_by_family.get(family)
            return mock.patch.object(RUNNER, name) if name else nullcontext()

        expected_by_id = {}
        for field, registry in MODULE.CAMPAIGN_REGISTRIES.items():
            for identifier in registry:
                for campaign in MODULE.campaign_plan(field, identifier)["campaigns"]:
                    expected_by_id.setdefault(campaign["id"], campaign)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for family, campaign_id in representatives.items():
                expected = expected_by_id[campaign_id]
                base = root / family
                base.mkdir()
                hardware = []
                for index, role in enumerate(expected["roles"], 1):
                    image = base / f"{role}.image.hex"
                    build_record = base / f"{role}.build-record.bin"
                    readback = base / f"{role}.readback.json"
                    vector = ((0x20000100 + index * 4).to_bytes(4, "little") +
                              (9 + index * 2).to_bytes(4, "little") +
                              bytes([index]))
                    image.write_text(
                        self.hex_record(0, 0, vector) + "\n" +
                        self.hex_record(0, 1) + "\n", encoding="ascii"
                    )
                    build_record.write_bytes(
                        f"{campaign_id}:{role}:build".encode("ascii")
                    )
                    probe = hashlib.sha256(
                        f"{campaign_id}:{role}:probe".encode("ascii")
                    ).hexdigest()
                    ranges = [{
                        "start": start,
                        "length": len(data),
                        "expected_sha256": hashlib.sha256(data).hexdigest(),
                        "observed_sha256": hashlib.sha256(data).hexdigest(),
                        "status": "PASS",
                    } for start, data in MODULE.intel_hex_ranges(image)]
                    readback.write_text(json.dumps({
                        "schema_version": 1,
                        "kind": "m33_exact_program_readback",
                        "status": "PASS",
                        "role": role,
                        "probe_sha256": probe,
                        "image_sha256": MODULE.digest(image),
                        "backend": "pyocd-live-target",
                        "halted": True,
                        "resumed": True,
                        "pre_state": "RUNNING",
                        "post_state": "RUNNING",
                        "restored": True,
                        "ranges": ranges,
                    }), encoding="utf-8")
                    hardware.append({
                        "role": role,
                        "probe_sha256": probe,
                        "image": {"path": image.name, "sha256": MODULE.digest(image)},
                        "build_record": {"path": build_record.name,
                                         "sha256": MODULE.digest(build_record)},
                        "flash": {"mode": "pyocd-sector-sw-reset",
                                  "programmed_bytes": len(vector), "erase": "sector",
                                  "auto_unlock": False, "mass_erase": False,
                                  "automatic_recover": False},
                        "readback": {"path": readback.name,
                                     "sha256": MODULE.digest(readback)},
                    })
                cycles = expected["minimum_cycles"]
                attestation = {
                    "schema_version": 1,
                    "kind": RUNNER.NATIVE_ATTESTATION_KIND,
                    "campaign_id": campaign_id,
                    "source_revision": REVISION,
                    "source_clean": True,
                    "semantic_status": {
                        token: "PASS" for token in expected["semantics"]
                    },
                    "cycle_records": [
                        {"cycle": cycle, "status": "PASS",
                         "semantics": {token: "PASS"
                                       for token in expected["semantics"]}}
                        for cycle in range(1, cycles + 1)
                    ],
                    "hardware": hardware,
                }
                if family == "legacy_hil":
                    native = {"status": "passed", "core_revision": REVISION,
                              "boards": {}, "results": {}}
                elif family == "modern_hil":
                    native = {"status": "PASS", "source_clean": True,
                              "identity": {"core": REVISION}, "boards": {},
                              "results": {}}
                elif family == "flat_hil":
                    native = {"status": "ARDUINO_BAP_DUPLEX_STOP_RELEASE_PASS",
                              "source_clean": True, "core_revision": REVISION}
                elif family == "profile_hil":
                    from test_m33_profile_campaign import ProfileCampaignTests
                    native_path = ProfileCampaignTests().campaign(base, REVISION)
                    native = json.loads(native_path.read_text(encoding="utf-8"))
                    hardware = native["m33_dispatch_attestation"]["hardware"]
                elif family == "ecosystem_hil":
                    import m33_ecosystem_hil as ecosystem

                    identity = REVISION + "a" * 64
                    cases = []
                    transcript_lines = []
                    schedule = [(0, "access_denied", "denied")]
                    schedule.extend(ecosystem.regression_schedule())
                    security = {
                        "denied": (0, 0, 0, 0, 1, 0),
                        "fresh": (1, 1, 1, 0, 0, 1),
                        "reconnect": (1, 0, 1, 1, 0, 1),
                    }
                    for index, (cycle, case, mode) in enumerate(schedule, 1):
                        nonce = f"{index:032x}"
                        role_results = {}
                        for role in expected["roles"]:
                            packets, attributes, writes, negative = \
                                ecosystem.COUNTERS[(case, role)]
                            secured, pairings, bonded, reconnects, rejected, owned = \
                                security[mode]
                            if mode == "denied" and role == "client":
                                rejected = 0
                            line = (
                                f"M33ECO|2|PASS|role={role}|nonce={nonce}|case={case}"
                                f"|revision={REVISION}|identity={identity}|packets={packets}"
                                f"|attributes={attributes}|writes={writes}|negative={negative}"
                                f"|links={0 if mode == 'denied' else 1}|security={secured}"
                                f"|pairings={pairings}|bonded={bonded}|reconnects={reconnects}"
                                f"|security_rejects={rejected}|test_bond={owned}"
                            )
                            role_results[role] = ecosystem.parse(
                                line, role, identity
                            )
                            transcript_lines.append(f"{role}< {line}")
                        cases.append({
                            "cycle": cycle,
                            "case": case,
                            "nonce": nonce,
                            "status": "PASS",
                            "roles": role_results,
                            "cleanup": "PASS",
                        })
                    transcript = base / "transcript.log"
                    transcript.write_text(
                        "\n".join(transcript_lines) + "\n", encoding="ascii"
                    )
                    preflight = base / "preflight.json"
                    preflight.write_text('{"status":"PASS"}\n', encoding="utf-8")
                    fixture = base / "fixture.json"
                    fixture.write_text(json.dumps({
                        "schema_version": 1,
                        "identity": identity,
                        "other_radios": "isolated_verified",
                        "test_owned_bond_cleanup": True,
                        "preflight_sha256": MODULE.digest(preflight),
                        "boards": [{
                            "role": row["role"],
                            "probe_sha256": row["probe_sha256"],
                            "readback": "verified",
                            "image_sha256": row["image"]["sha256"],
                            "build_record_sha256": row["build_record"]["sha256"],
                        } for row in hardware],
                    }), encoding="utf-8")
                    native = {
                        "schema_version": 2,
                        "status": "PASS",
                        "identity": identity,
                        "cases": cases,
                        "negative": [{"wrong_peer_nonce": "PASS",
                                      "malformed_commands": "PASS"}],
                        "cleanup": [],
                        "bond_cleanup": [{
                            "role": role,
                            "status": "PASS",
                            "exact_deleted": 1,
                            "existing_unchanged": True,
                        } for role in expected["roles"]],
                        "case_denominators": ecosystem.validate_case_denominators(cases),
                        "fixture_sha256": MODULE.digest(fixture),
                        "fixture": {"path": fixture.name,
                                    "sha256": MODULE.digest(fixture)},
                        "preflight": {"path": preflight.name,
                                      "sha256": MODULE.digest(preflight)},
                        "transcript_sha256": MODULE.digest(transcript),
                        "apple_interoperability": "NOT_RUN",
                        "google_interoperability": "NOT_RUN",
                    }
                elif family == "build_semantic":
                    native = {"source_revision": REVISION,
                              "results": [{"status": "PASS", "exit_code": 0,
                                           "runtime": "NOT_RUN"}]}
                else:
                    from test_m33_diagnostics_campaign import DiagnosticsCampaignTests
                    native_path, _fixtures = DiagnosticsCampaignTests().campaign(base)
                    native = json.loads(native_path.read_text(encoding="utf-8"))
                    hardware = native["m33_dispatch_attestation"]["hardware"]
                if family not in {"profile_hil", "diagnostic_hil"}:
                    native["m33_dispatch_attestation"] = attestation
                native_path = base / "native.json"
                child_path = base / "child.json"
                native_path.write_text(json.dumps(native), encoding="utf-8")
                with self.subTest(family=family):
                    with raw_context(family):
                        rows = RUNNER._adapt_native_evidence(
                            native_path, child_path, expected, REVISION, cycles
                        )
                    self.assertEqual(set(expected["roles"]),
                                     {row["role"] for row in rows})
                    child_path.unlink()
                    shortened = copy.deepcopy(native)
                    shortened["m33_dispatch_attestation"]["cycle_records"].pop()
                    native_path.write_text(json.dumps(shortened), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "cycle denominator"), \
                            raw_context(family):
                        RUNNER._adapt_native_evidence(
                            native_path, child_path, expected, REVISION, cycles
                        )
                    native_path.write_text(json.dumps(native), encoding="utf-8")
                    if family == "build_semantic":
                        false_pass = copy.deepcopy(native)
                        false_pass["results"][0]["status"] = "FAIL"
                        native_path.write_text(json.dumps(false_pass), encoding="utf-8")
                        with self.assertRaisesRegex(
                                ValueError, "build-semantic native result"), \
                                raw_context(family):
                            RUNNER._adapt_native_evidence(
                                native_path, child_path, expected, REVISION, cycles
                            )
                        native_path.write_text(json.dumps(native), encoding="utf-8")
                    if hardware:
                        Path(base / hardware[0]["readback"]["path"]).write_bytes(b"tampered")
                        with self.assertRaisesRegex(ValueError, "readback byte"), \
                                raw_context(family):
                            RUNNER._adapt_native_evidence(
                                native_path, child_path, expected, REVISION, cycles
                            )
            self.assertEqual(set(MODULE.CAMPAIGNS),
                             set(RUNNER.CAMPAIGN_PREPARATION_MODE))
            with mock.patch.dict(os.environ, {"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"}):
                matrix = RUNNER.campaign_dispatch_matrix(ROOT)
            self.assertEqual(48, matrix["unique_campaigns"])
            self.assertEqual(45, matrix["unique_runners"])
            self.assertEqual(46, matrix["physical_campaigns"])
            self.assertEqual(2, matrix["build_semantic_campaigns"])
            self.assertEqual("READY", matrix["status"])
            ready = {row["id"] for row in matrix["campaigns"]
                     if row["status"] == "DISPATCH_READY"}
            self.assertTrue(
                {"m32_timing", "m33_cis_acl_risk",
                 "m33_cs_acl_radio_risk"}.issubset(ready)
            )
            self.assertEqual(len(ready), matrix["dispatch_ready"])
            self.assertEqual(48, len(ready))
            artifact_root = root / "artifacts"
            campaign_artifacts = artifact_root / "m28_link"
            campaign_artifacts.mkdir(parents=True)
            for role in ("peripheral", "mixed", "central"):
                (campaign_artifacts / f"{role}-hex.hex").write_text(
                    ":00000001FF\n", encoding="ascii"
                )
            output_root = root / "prepared-output"
            output_root.mkdir()
            inventory = {
                "schema_version": 1, "kind": "m33_board_inventory",
                "source_revision": REVISION, "source_clean": True,
                "boards": [
                    {"role": role, "probe_sha256": hashlib.sha256(
                        f"id-{index}".encode("ascii")
                    ).hexdigest(), "port": f"COM{index}",
                     "volume": f"VOL{index}"}
                    for index, role in enumerate(
                        ("peripheral", "mixed", "central"), 1
                    )
                ],
            }
            with mock.patch.object(
                    RUNNER, "_git_identity", return_value=(REVISION, True)):
                spec = RUNNER.prepare_execution_spec(
                    "families", "gap_links", inventory, artifact_root,
                    output_root, root / "sdk", root / "toolchain", ROOT
                )
                plan, prepared = RUNNER._validate_execution_spec(
                    spec, output_root / "wrapper.json", ROOT
                )
            self.assertEqual("m28_link", plan["campaigns"][0]["id"])
            self.assertEqual(1, len(prepared))
            self.assertIsNone(spec["campaigns"][0]["reuse_receipt"])
            all_artifacts = root / "all-artifacts"
            all_output = root / "all-output"
            all_output.mkdir()
            role_names = sorted({role for value in MODULE.CAMPAIGNS.values()
                                 for role in value["roles"]})
            role_names.append("third")
            all_boards = {
                role: {"role": role, "probe_sha256": hashlib.sha256(
                    f"all-prepared:{role}".encode("ascii")
                ).hexdigest(), "port": f"COM{index + 10}",
                       "volume": f"VOL{index}",
                       "app": f"COM{index + 40}", "aux": f"COM{index + 70}"}
                for index, role in enumerate(role_names, 1)
            }
            path_tokens = ("hex-", "build-", "build-outdir", "signing-key",
                           "imgtool", "config", "flash-record", "fixture",
                           "prior-evidence", "fresh", "restored", "second-peer")
            for campaign_id, definition in MODULE.CAMPAIGNS.items():
                expected = expected_by_id[campaign_id]
                base = all_artifacts / campaign_id
                base.mkdir(parents=True)
                options, _ = RUNNER._runner_interface(ROOT / definition["runner"])
                artifact_names = set()
                for role in definition["roles"]:
                    cli_role = role.replace("_", "-")
                    artifact_names.update(option[2:] for option in (
                        f"--hex-{cli_role}", f"--{cli_role}-hex",
                        f"--{cli_role}-image", f"--{cli_role}-config",
                        f"--{cli_role}-flash-record") if option in options)
                if "--hex" in options:
                    artifact_names.add("hex")
                for option in options - RUNNER.FORBIDDEN_EXECUTION_OPTIONS:
                    name = option[2:]
                    if any(token in name for token in path_tokens):
                        if campaign_id in {"m33_profiles_standard",
                                           "m33_profiles_native"} and option in {
                            "--build-record", "--second-peer-role",
                            "--second-peer-build-record"}:
                            continue
                        if campaign_id == "m33_diagnostics_dtm" and option in {
                            "--build-manifest", "--twowire-hex", "--h4-hex",
                            "--third-idle-fixture"}:
                            continue
                        artifact_names.add(name)
                if campaign_id in {"m33_profiles_standard", "m33_profiles_native"}:
                    for role in ("server", "client", "watcher"):
                        cli_role = role.replace("_", "-")
                        if campaign_id == "m33_profiles_native" and role == "watcher":
                            artifact_names.update(("hex-watcher-idle",
                                                   "build-record-watcher-idle"))
                        else:
                            artifact_names.update((f"hex-{cli_role}",
                                                   f"build-record-{cli_role}"))
                    if campaign_id == "m33_profiles_native":
                        artifact_names.update(("hex-second-peer",
                                               "build-record-second-peer"))
                if campaign_id == "m33_diagnostics_dtm":
                    artifact_names.update(("build-manifest", "twowire-hex",
                                           "h4-hex", "third-idle-fixture"))
                for name in artifact_names:
                    target = base / name
                    if name != "build-manifest" and "build" in name and \
                            "record" not in name and "info" not in name:
                        target.mkdir()
                    else:
                        target.write_bytes(f"{campaign_id}:{name}".encode("ascii"))
                if campaign_id == "m33_ecosystem":
                    fixture_boards = []
                    for role in expected["roles"]:
                        image = base / f"fixture-{role}.hex"
                        image.write_bytes(b":00000001FF\n")
                        fixture_boards.append({
                            "role": role,
                            "probe_sha256": all_boards[role]["probe_sha256"],
                            "image": str(image),
                        })
                    (base / "fixture").write_text(json.dumps({
                        "boards": fixture_boards,
                        "isolated_probe_sha256": [all_boards["third"]["probe_sha256"]],
                    }), encoding="utf-8")
                with self.subTest(preparation=campaign_id):
                    subcommand, arguments, native_name = RUNNER._prepared_arguments(
                        expected, all_boards, all_artifacts, all_output,
                        root / "sdk", root / "toolchain", REVISION
                    )
                    allowed, commands = RUNNER._runner_interface(
                        ROOT / definition["runner"], subcommand
                    )
                    RUNNER._arguments_to_argv(arguments, allowed)
                    board_plan = {role: all_boards[role]["probe_sha256"]
                                  for role in RUNNER._preparation_roles(expected)}
                    RUNNER._validate_argument_board_binding(expected, arguments, board_plan)
                    occurrences = RUNNER._argument_values(arguments)
                    self.assertTrue(all(len(values) == 1 or option in {
                        "--role", "--build-record",
                    } for option, values in occurrences.items()), campaign_id)
                    for option in occurrences:
                        if option.startswith("--probe-") and option.endswith("-sha256"):
                            duplicate = copy.deepcopy(arguments)
                            duplicate.append(next(row for row in duplicate
                                                  if row["option"] == option))
                            with self.assertRaisesRegex(ValueError, "differs from board plan"):
                                RUNNER._validate_argument_board_binding(expected, duplicate, board_plan)
                    if campaign_id in {"m33_profiles_standard", "m33_profiles_native"}:
                        for defect in ("missing", "duplicate", "wrong_probe", "second_peer"):
                            changed = copy.deepcopy(arguments)
                            role_row = next(row for row in changed
                                            if row["option"] == "--role"
                                            and row["values"][0] == "watcher")
                            if defect == "missing":
                                changed.remove(role_row)
                            elif defect == "duplicate":
                                changed.append(copy.deepcopy(role_row))
                            elif defect == "wrong_probe":
                                role_row["values"][1] = "f" * 64
                            elif campaign_id == "m33_profiles_native":
                                next(row for row in changed if row["option"] ==
                                     "--second-peer-role")["values"][0] = "f" * 64
                            else:
                                changed.append({"option": "--second-peer-role",
                                                "values": ["f" * 64, "fixture.hex"]})
                            with self.subTest(profile=campaign_id, defect=defect), \
                                    self.assertRaises(ValueError):
                                RUNNER._validate_argument_board_binding(expected, changed, board_plan)
                    self.assertTrue(native_name.endswith(".json"))
                    self.assertEqual(RUNNER.CAMPAIGN_SUBCOMMAND.get(campaign_id),
                                     subcommand)
                    self.assertTrue(subcommand is None or subcommand in commands)
                    generated = {row["option"] for row in arguments}
                    if campaign_id == "m33_ecosystem":
                        self.assertIn("--fixture", generated)
                        self.assertNotIn("--toolchain", generated)
                    if campaign_id == "m33_diagnostics_dtm":
                        self.assertIn("--execute", generated)
                        self.assertIn("--third-probe-sha256", generated)
                        self.assertNotIn("--routes", generated)
                    if campaign_id == "m33_diagnostics_build":
                        self.assertNotIn("--fixture", generated)
                        self.assertNotIn("--authorize-start-tx-rx", generated)
                    if campaign_id in RUNNER.CAMPAIGN_FIXED_ARGUMENTS:
                        self.assertTrue(all(
                            option in generated for option, _value in
                            RUNNER.CAMPAIGN_FIXED_ARGUMENTS[campaign_id]
                        ))
            all_inventory = {
                "schema_version": 1, "kind": "m33_board_inventory",
                "source_revision": REVISION, "source_clean": True,
                "boards": list(all_boards.values()),
            }
            groups = []
            with mock.patch.object(RUNNER, "_git_identity", return_value=(REVISION, True)):
                for field, registry in MODULE.CAMPAIGN_REGISTRIES.items():
                    for identifier in registry:
                        with self.subTest(prepared_group=f"{field}:{identifier}"):
                            group_output = all_output / f"{field}.{identifier}"
                            group_output.mkdir()
                            spec = RUNNER.prepare_execution_spec(
                                field, identifier, all_inventory, all_artifacts,
                                group_output, root / "sdk", root / "toolchain", ROOT,
                            )
                            _plan, prepared = RUNNER._validate_execution_spec(
                                spec, group_output / "result.json", ROOT,
                            )
                            self.assertEqual(len(spec["campaigns"]), len(prepared))
                            for row, expected in zip(spec["campaigns"], _plan["campaigns"]):
                                phases = {"m33_profiles_standard": 2,
                                          "m33_profiles_native": 3}.get(row["id"])
                                limit = (20 * phases * 1800 if phases else 14400)
                                self.assertEqual(limit, row["timeout_seconds"])
                                invalid = copy.deepcopy(spec)
                                next(item for item in invalid["campaigns"]
                                     if item["id"] == row["id"])["timeout_seconds"] = limit + 1
                                with self.assertRaisesRegex(ValueError, "execution row drift"):
                                    RUNNER._validate_execution_spec(
                                        invalid, group_output / "result.json", ROOT,
                                    )
                            groups.append((field, identifier))
            self.assertEqual(49, len(groups))

    def test_prepare_spec_reuses_three_hashed_slots_by_campaign(self):
        """! @brief 순차 campaign은 3개 물리 slot을 재사용하고 회차 내 중복은 거부합니다. """

        hashes = [
            hashlib.sha256(f"physical-slot-{index}".encode("ascii")).hexdigest()
            for index in range(1, 4)
        ]

        def inventory_for(plan):
            return {
                "schema_version": 2,
                "kind": "m33_board_inventory",
                "source_revision": REVISION,
                "source_clean": True,
                "physical_slots": [
                    {
                        "slot": f"board_{index}",
                        "probe_sha256": hashes[index - 1],
                        "port": f"COM{index}",
                        "volume": f"NU54DK{index}",
                        "app": f"COM{index + 10}",
                        "aux": f"COM{index + 20}",
                    }
                    for index in range(1, 4)
                ],
                "campaign_bindings": [
                    {
                        "campaign_id": expected["id"],
                        "roles": [
                            {"role": role, "slot": f"board_{index + 1}"}
                            for index, role in enumerate(
                                RUNNER._preparation_roles(expected)
                            )
                        ],
                    }
                    for expected in plan["campaigns"]
                    if RUNNER._preparation_roles(expected)
                ],
            }

        for field, identifier in (
                ("families", "iso"),
                ("families", "channel_sounding"),
                ("families", "mesh"),
                ("resources", "diagnostics")):
            plan = MODULE.campaign_plan(field, identifier)
            inventory = inventory_for(plan)
            mapped = RUNNER._board_inventory(inventory, REVISION, plan)
            logical_roles = {
                role for expected in plan["campaigns"]
                for role in RUNNER._preparation_roles(expected)
            }
            if identifier != "diagnostics":
                self.assertGreater(len(logical_roles), 3)
            used_hashes = {
                row["probe_sha256"] for boards in mapped.values()
                for row in boards.values()
            }
            self.assertLessEqual(len(used_hashes), 3)
            for expected in plan["campaigns"]:
                boards = mapped[expected["id"]]
                self.assertEqual(
                    len(boards),
                    len({row["probe_sha256"] for row in boards.values()}),
                )

        canonical_plan = {
            "campaigns": [
                {
                    "id": campaign_id,
                    "roles": list(definition["roles"]),
                }
                for campaign_id, definition in RUNNER.CAMPAIGNS.items()
            ],
        }
        canonical_inventory = inventory_for(canonical_plan)
        group_plan = MODULE.campaign_plan("families", "iso")
        canonical_mapped = RUNNER._board_inventory(
            canonical_inventory, REVISION, group_plan
        )
        self.assertEqual(
            [campaign["id"] for campaign in group_plan["campaigns"]],
            list(canonical_mapped),
        )
        missing_canonical = copy.deepcopy(canonical_inventory)
        missing_canonical["campaign_bindings"].pop()
        with self.assertRaisesRegex(ValueError, "denominator/order"):
            RUNNER._board_inventory(
                missing_canonical, REVISION, group_plan
            )

        plan = MODULE.campaign_plan("families", "iso")
        inventory = inventory_for(plan)
        duplicate = copy.deepcopy(inventory)
        duplicate["campaign_bindings"][0]["roles"][1]["slot"] = "board_1"
        with self.assertRaisesRegex(ValueError, "same campaign"):
            RUNNER._board_inventory(duplicate, REVISION, plan)
        raw_identity = copy.deepcopy(inventory)
        raw_identity["physical_slots"][0]["probe_uid"] = \
            "00112233445566778899aabbccddeeff"
        with self.assertRaisesRegex(ValueError, "slot identity"):
            RUNNER._board_inventory(raw_identity, REVISION, plan)
        bare_uid = "00112233445566778899aabbccddeeff"
        bare_identity = copy.deepcopy(inventory)
        bare_identity["physical_slots"][0]["probe_sha256"] = hashlib.sha256(
            bare_uid.encode("ascii")
        ).hexdigest()
        bare_identity["physical_slots"][0]["port"] = bare_uid
        with self.assertRaisesRegex(ValueError, "raw probe identity"):
            RUNNER._board_inventory(bare_identity, REVISION, plan)
        too_many = copy.deepcopy(inventory)
        too_many["physical_slots"].append({
            "slot": "board_4",
            "probe_sha256": hashlib.sha256(b"physical-slot-4").hexdigest(),
        })
        with self.assertRaisesRegex(ValueError, "one to three"):
            RUNNER._board_inventory(too_many, REVISION, plan)

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            output = base / "output"
            output.mkdir()
            with mock.patch.object(
                    RUNNER, "_git_identity", return_value=(REVISION, True)), \
                    mock.patch.object(
                        RUNNER, "_prepared_arguments",
                        side_effect=lambda expected, *_args: (
                            None, [], f"native/{expected['id']}.json"
                        )):
                spec = RUNNER.prepare_execution_spec(
                    "families", "iso", inventory,
                    base / "artifacts", output, base / "sdk",
                    base / "toolchain", ROOT
                )
            self.assertEqual(3, len({
                board["probe_sha256"]
                for row in spec["campaigns"] for board in row["boards"]
            }))
            self.assertNotIn("probe_uid", json.dumps(spec))
            self.assertNotIn("board_id", json.dumps(spec))

    def test_m30_probe_identity_is_hash_only_in_every_process_argv(self):
        """! @brief M30 runner와 pyOCD backend 어느 argv에도 raw UID를 넣지 않습니다. """

        import ble_pair_hil_common as common

        for campaign_id in (
                "m30_pair", "m30_oob", "m30_bond", "m30_profiles",
                "m30_dfu", "m30_multi"):
            expected = MODULE.CAMPAIGNS[campaign_id]
            options, _subcommands = RUNNER._runner_interface(
                ROOT / expected["runner"]
            )
            self.assertFalse(any(
                option == "--board-id" or option.endswith("-board-id")
                for option in options
            ), campaign_id)
            for role in expected["roles"]:
                self.assertIn(
                    f"--probe-{role.replace('_', '-')}-sha256", options,
                    campaign_id,
                )
        for helper in (
                common.flash_image_pyocd_sha256,
                common.clear_nrf54l_rram_pyocd_sha256,
                common.erase_nrf54l_rram_pyocd_sha256):
            source = inspect.getsource(helper)
            self.assertNotIn("subprocess", source)
            self.assertNotIn('"--uid"', source)
        for invalid in (float("nan"), float("inf")):
            calls = (
                lambda: common.flash_image_pyocd_sha256(
                    "role", "a" * 64, Path("missing.hex"), invalid
                ),
                lambda: common.flash_binary_pyocd_sha256(
                    "role", "a" * 64, Path("missing.bin"), 0, invalid
                ),
                lambda: common.reset_target_pyocd_sha256(
                    "role", "a" * 64, invalid
                ),
                lambda: common.erase_nrf54l_rram_pyocd_sha256(
                    "role", "a" * 64, 0, 0x100, invalid
                ),
                lambda: common.clear_nrf54l_rram_pyocd_sha256(
                    "role", "a" * 64, 0, 0x100, invalid
                ),
            )
            for call in calls:
                with self.assertRaises(common.BlePairHilFailure):
                    call()
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "snapshot.hex"
            image.write_text(
                self.hex_record(0, 0, b"12345678") + "\n" +
                self.hex_record(0, 1) + "\n",
                encoding="ascii",
            )
            with self.assertRaisesRegex(
                    common.BlePairHilFailure, "exact HEX snapshot"):
                common.flash_image_pyocd_sha256(
                    "role", "a" * 64, image, 1.0,
                    expected_sha256="f" * 64,
                )
        expected = MODULE.campaign_plan(
            "families", "pairing_security"
        )["campaigns"][0]
        probes = {
            role: hashlib.sha256(f"uid-{role}".encode("ascii")).hexdigest()
            for role in expected["roles"]
        }
        rows = [{"option": "--peripheral-board-id",
                 "values": ["00112233445566778899aabbccddeeff"]}]
        with self.assertRaisesRegex(ValueError, "cannot store"):
            RUNNER._validate_argument_board_binding(expected, rows, probes)

    def test_flash_init_timeout_retries_once_with_a_new_session(self):
        """! @brief flash init timeout만 새 session으로 한 번 재시도하고 다른 오류는 전파합니다. """

        import ble_pair_hil_common as common

        class FlashFailure(RuntimeError):
            """! @brief pyOCD FlashFailure 이름을 재현하는 Host fixture입니다. """

        class Backend:
            """! @brief 실제 probe 없이 session 경계를 기록합니다. """

            def session(self, _probe):
                """! @brief 각 시도마다 독립된 context를 반환합니다. """

                return nullcontext(object())

        attempts = []

        def load_backend(_digest):
            attempts.append(len(attempts) + 1)
            return Backend(), object(), nullcontext

        def transient(_backend, _session):
            if len(attempts) == 1:
                raise FlashFailure("flash init timed out")

        with mock.patch.object(
                common, "_load_private_pyocd_backend", side_effect=load_backend):
            common._run_flash_session_with_retry(
                "a" * 64, float("inf"), transient
            )
        self.assertEqual([1, 2], attempts)

        attempts.clear()
        with mock.patch.object(
                common, "_load_private_pyocd_backend", side_effect=load_backend), \
                self.assertRaisesRegex(RuntimeError, "different failure"):
            common._run_flash_session_with_retry(
                "a" * 64,
                float("inf"),
                lambda _backend, _session: (_ for _ in ()).throw(
                    RuntimeError("different failure")
                ),
            )
        self.assertEqual([1], attempts)
        self.assertIn(
            "_run_flash_session_with_retry",
            inspect.getsource(common.erase_nrf54l_rram_pyocd_sha256),
        )
        self.assertNotIn(
            "_run_flash_session_with_retry",
            inspect.getsource(common.clear_nrf54l_rram_pyocd_sha256),
        )

    def test_automatic_peer_is_generated_from_same_campaign_flow(self):
        """! @brief scripted peer는 선행 파일 없이 실제 campaign PASS 뒤에만 생성합니다. """

        plan = MODULE.campaign_plan("automatic_peers", "gatt")
        expected = plan["campaigns"][0]
        probe_hashes = [
            hashlib.sha256(f"auto-slot-{index}".encode("ascii")).hexdigest()
            for index in range(1, 4)
        ]
        inventory = {
            "schema_version": 2,
            "kind": "m33_board_inventory",
            "source_revision": REVISION,
            "source_clean": True,
            "physical_slots": [
                {"slot": f"board_{index}", "probe_sha256": probe_hashes[index - 1],
                 "port": f"COM{index}"}
                for index in range(1, 4)
            ],
            "campaign_bindings": [{
                "campaign_id": expected["id"],
                "roles": [
                    {"role": role, "slot": f"board_{index + 1}"}
                    for index, role in enumerate(
                        RUNNER._preparation_roles(expected)
                    )
                ],
            }],
        }
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            prepared_output = base / "prepared"
            prepared_output.mkdir()
            with mock.patch.object(
                    RUNNER, "_git_identity", return_value=(REVISION, True)), \
                    mock.patch.object(
                        RUNNER, "_prepared_arguments",
                        return_value=(None, [], "native/m29_multi.json")):
                spec = RUNNER.prepare_execution_spec(
                    "automatic_peers", "gatt", inventory,
                    base / "artifacts", prepared_output, base / "sdk",
                    base / "toolchain", ROOT
                )
            self.assertNotIn("peer_result", spec)
            self.assertEqual("NOT_RUN", spec["external_interoperability"])
            campaign_results = [{
                "id": expected["id"],
                "status": "PASS",
                "verification": "physical_hil",
                "cycles": 20,
            }]
            output = base / "automatic-result.json"
            peer = RUNNER._automatic_peer_result(
                "gatt", output, REVISION, plan, campaign_results
            )
            MODULE.validate_peer(peer)
            MODULE.validate_peer_evidence(peer, base, REVISION)
            self.assertEqual("scripted_peer", peer["basis"])
            self.assertNotIn("external", json.dumps(peer).lower())
            failed = copy.deepcopy(campaign_results)
            failed[0]["cycles"] = 19
            with self.assertRaisesRegex(ValueError, "complete scripted"):
                RUNNER._automatic_peer_result(
                    "gatt", base / "other.json", REVISION, plan, failed
                )

    def test_diagnostics_aggregate_prepare_spec_has_no_stale_subcommand(self):
        """! @brief DTM aggregate wrapper를 run-pair 없이 exact 24-case spec으로 준비합니다. """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifacts = root / "artifacts"
            output = root / "output"
            dtm = artifacts / "m33_diagnostics_dtm"
            dtm.mkdir(parents=True)
            output.mkdir()
            for name in ("build-manifest", "twowire-hex", "h4-hex",
                         "third-idle-fixture"):
                (dtm / name).write_bytes(name.encode("ascii"))
            probes = {
                role: hashlib.sha256(role.encode("ascii")).hexdigest()
                for role in ("tx", "rx", "third")
            }
            inventory = {
                "schema_version": 1,
                "kind": "m33_board_inventory",
                "source_revision": REVISION,
                "source_clean": True,
                "boards": [
                    {
                        "role": role,
                        "probe_sha256": probes[role],
                        "port": f"COM{index}",
                    }
                    for index, role in enumerate(("tx", "rx", "third"), 1)
                ],
            }
            with mock.patch.object(
                    RUNNER, "_git_identity", return_value=(REVISION, True)):
                spec = RUNNER.prepare_execution_spec(
                    "resources", "diagnostics", inventory, artifacts, output,
                    root / "sdk", root / "toolchain", ROOT
                )
                plan, prepared = RUNNER._validate_execution_spec(
                    spec, output / "wrapper.json", ROOT
                )
            rows = {row["id"]: row for row in spec["campaigns"]}
            dtm_row = rows["m33_diagnostics_dtm"]
            self.assertIsNone(dtm_row["subcommand"])
            self.assertEqual("m33_diagnostics_dtm", plan["campaigns"][0]["id"])
            self.assertEqual(2, len(prepared))
            options = {row["option"]: row["values"]
                       for row in dtm_row["arguments"]}
            self.assertEqual(
                {"--build-manifest", "--twowire-hex", "--h4-hex",
                 "--third-idle-fixture", "--third-probe-sha256", "--execute"},
                set(options) & {
                    "--build-manifest", "--twowire-hex", "--h4-hex",
                    "--third-idle-fixture", "--third-probe-sha256", "--execute",
                },
            )
            self.assertEqual([probes["third"]], options["--third-probe-sha256"])
            self.assertEqual(
                ["tx", "rx", "third"],
                [board["role"] for board in dtm_row["boards"]],
            )
            changed = copy.deepcopy(dtm_row["arguments"])
            next(row for row in changed
                 if row["option"] == "--third-probe-sha256")["values"] = [
                     "f" * 64
                 ]
            expected = next(
                row for row in plan["campaigns"]
                if row["id"] == "m33_diagnostics_dtm"
            )
            board_plan = {
                board["role"]: board["probe_sha256"]
                for board in dtm_row["boards"]
            }
            with self.assertRaisesRegex(ValueError, "differs from board plan"):
                RUNNER._validate_argument_board_binding(
                    expected, changed, board_plan
                )

    def test_ecosystem_isolated_third_is_bound_to_spec(self):
        """! @brief ecosystem fixture의 isolated third를 inventory/spec과 동일하게 고정합니다. """

        expected = MODULE.campaign_plan(
            "families", "apple_companion"
        )["campaigns"][0]
        probes = {
            role: hashlib.sha256(role.encode("ascii")).hexdigest()
            for role in ("client", "peer", "third")
        }
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            fixture = base / "fixture.json"
            value = {
                "boards": [
                    {"role": role, "probe_sha256": probes[role]}
                    for role in ("client", "peer")
                ],
                "isolated_probe_sha256": [probes["third"]],
            }
            fixture.write_text(json.dumps(value), encoding="utf-8")
            rows = [{"option": "--fixture", "values": [str(fixture)]}]
            RUNNER._validate_argument_board_binding(expected, rows, probes)
            value["isolated_probe_sha256"] = ["f" * 64]
            fixture.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs from board plan"):
                RUNNER._validate_argument_board_binding(expected, rows, probes)

    def test_legacy_adapter_reparses_transcript_bytes_and_typed_result(self):
        """! @brief legacy child는 저장 result를 믿지 않고 기존 strict UART parser로 재구성합니다. """

        native_path = ROOT / (
            "00_Docs/04_검증 기록/evidence/"
            "m29-w02-dacf6341-long-read/m29-w02-long-read-evidence.json"
        )
        native = MODULE.read_json(native_path)
        native["boards"] = {
            role: {
                "probe_sha256": hashlib.sha256(
                    board["daplink_uid"].strip().lower().encode("ascii")
                ).hexdigest(),
                "msd_root": f"historical-fixture-{role}",
                "uart_port": f"fixture-{role}",
            }
            for role, board in native["boards"].items()
        }
        for reference in native["transcripts"].values():
            transcript = native_path.parent / reference["name"]
            reference["size"] = transcript.stat().st_size
            reference["sha256"] = MODULE.digest(transcript)
        expected = MODULE.campaign_plan(
            "families", "long_read"
        )["campaigns"][0]
        self.assertEqual("m29_long_read", expected["id"])
        RUNNER._validate_legacy_native_raw(
            native, native_path, expected, native["core_revision"]
        )
        changed = copy.deepcopy(native)
        changed["results"]["central"]["reads"] -= 1
        with self.assertRaisesRegex(ValueError, "typed result"):
            RUNNER._validate_legacy_native_raw(
                changed, native_path, expected, native["core_revision"]
            )

    def test_campaign_registry_requires_profile_and_sdk_risk_semantics(self):
        """! @brief W06의 BMS·두 번째 peer와 기록된 SDK 위험 의미가 plan에서 빠지지 않습니다. """
        required = {
            "m33_profiles_standard": "bms_reboot_restore",
            "m33_profiles_native": "native_second_peer",
            "m32_timing": "subrating_ack_boundary",
            "m33_cis_acl_risk": "acl_first_teardown",
            "m31_iso_bis": "bounded_packet_loss",
            "m33_cs_acl_radio_risk": "radio_schedule",
            "m32_mesh": "lpn_friend_clear",
            "m32_mesh_dfu": "active_watchdog_condition",
            "m33_diagnostics_dtm": "packet_count",
        }
        for campaign, semantic in required.items():
            with self.subTest(campaign=campaign):
                self.assertIn(semantic, MODULE.CAMPAIGNS[campaign]["semantics"])
        self.assertEqual(24, MODULE.CAMPAIGNS["m33_diagnostics_dtm"]["minimum_cycles"])

    def test_sdk_risks_are_split_and_condition_not_met_is_not_pass(self):
        """! @brief 결합 위험 행과 관측하지 않은 조건의 PASS 승격을 거부합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source_path = base / "campaign-source.json"
            source_path.write_text("{}\n", encoding="utf-8")
            source_reference = {
                "path": source_path.name,
                "sha256": MODULE.digest(source_path),
            }
            rows = []
            completed = set()
            for identifier, plan in MODULE.SDK_RISK_CAMPAIGNS.items():
                completed.update(plan["campaigns"])
                condition_not_met = identifier in {
                    "DRGN-29228", "DRGN-29320", "MCUBOOT_ACTIVE_WATCHDOG"
                }
                status = "CONDITION_NOT_MET" if condition_not_met else "PASS"
                row = {
                    "id": identifier,
                    "status": status,
                    "condition": plan["condition"],
                    "condition_observed": not condition_not_met,
                    "cause_status": "not_reproduced_not_assumed",
                    "campaigns": list(plan["campaigns"]),
                    "evidence": None,
                }
                evidence = {
                    "schema_version": 2,
                    "kind": "m33_sdk_risk_result",
                    "id": identifier,
                    "status": status,
                    "condition": plan["condition"],
                    "condition_observed": not condition_not_met,
                    "cause_status": "not_reproduced_not_assumed",
                    "campaigns": list(plan["campaigns"]),
                    "campaign_evidence": [{
                        "campaign_id": campaign_id,
                        "semantic_status": {"fixture": "PASS"},
                        "group": {
                            "field": field,
                            "id": group_id,
                            "evidence": source_reference,
                        },
                        "receipt": source_reference,
                        "child_evidence": source_reference,
                        "native_evidence": source_reference,
                    } for campaign_id in plan["campaigns"]
                      for _, field, group_id in MODULE.campaign_observation_keys(campaign_id)],
                    "source_revision": REVISION,
                    "source_clean": True,
                }
                path = base / f"{identifier}.json"
                path.write_text(json.dumps(evidence), encoding="utf-8")
                row["evidence"] = {"path": path.name, "sha256": MODULE.digest(path)}
                rows.append(row)
            MODULE.validate_sdk_risks(rows, base, REVISION, completed)
            changed = copy.deepcopy(rows)
            watchdog = next(row for row in changed
                            if row["id"] == "MCUBOOT_ACTIVE_WATCHDOG")
            watchdog["status"] = "PASS"
            with self.assertRaises(ValueError):
                MODULE.validate_sdk_risks(changed, base, REVISION, completed)
            self.assertNotIn("DRGN-29446_DRGN-29320", MODULE.SDK_RISK_CAMPAIGNS)

    def test_sdk_risk_derivation_keeps_unobserved_conditions_out_of_pass(self):
        """! @brief noisy RF·watchdog 미관측과 fixed 위험의 semantic 누락을 PASS로 만들지 않습니다. """

        dtm = {
            "semantic_status": {
                "dtm_tx_rx_role_swap": "PASS", "packet_count": "PASS",
                "negative": "PASS", "cleanup": "PASS",
            },
            "native": {
                "rf_boundary": {
                    "controlled_noisy_rf": "NOT_RUN",
                    "sdk_risk": {
                        "id": "DRGN-29228",
                        "status": "CONDITION_NOT_MET",
                    },
                },
            },
        }
        self.assertFalse(MODULE._risk_condition_observed("DRGN-29228", dtm))
        watchdog = {
            "semantic_status": {"active_watchdog_condition": "NOT_APPLICABLE"},
            "native": {
                "sdk_risk_regression": {
                    "mcuboot_active_watchdog": {
                        "status": "NOT_APPLICABLE",
                        "not_run_is_pass": False,
                    },
                },
            },
        }
        self.assertFalse(MODULE._risk_condition_observed(
            "MCUBOOT_ACTIVE_WATCHDOG", watchdog
        ))
        observations = {
            campaign_id: [{
                "campaign_id": campaign_id,
                "semantic_status": {},
                "group": {"field": field, "id": group_id},
                "receipt": {},
                "child_evidence": {},
                "native_evidence": {},
            } for _, field, group_id in MODULE.campaign_observation_keys(campaign_id)]
            for plan in MODULE.SDK_RISK_CAMPAIGNS.values()
            for campaign_id in plan["campaigns"]
        }
        with mock.patch.object(
                MODULE, "_risk_condition_observed", return_value=False), \
                self.assertRaisesRegex(ValueError, "fixed PASS"):
            MODULE.derive_sdk_risk_documents(observations, REVISION)

    def test_nested_campaign_observations_preserve_independent_executions_and_risk_paths(self):
        """! @brief 실제 byte 참조로 nested matrix→반복 실행→risk 연결을 보드 없이 검증합니다. """

        campaign = "m32_timing"
        registries = {"families": {"one": (campaign,)},
                      "resources": {"two": (campaign,)}, "automatic_peers": {}}
        risks = {"DRGN-29270": MODULE.SDK_RISK_CAMPAIGNS["DRGN-29270"]}
        for nested in (False, True):
            with self.subTest(nested=nested), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                paths = {}
                for ordinal, (field, identifier) in enumerate(
                        (("families", "one"), ("resources", "two")), start=1):
                    folder = base / ".campaign-attempts" / identifier if nested else base
                    folder.mkdir(parents=True, exist_ok=True)

                    def save(name, document):
                        path = folder / f"{identifier}.{name}.json"
                        path.write_text(json.dumps(document), encoding="utf-8")
                        return {"path": path.name, "sha256": MODULE.digest(path)}

                    native = save("native", {"sdk_risk_regression": {"DRGN-29270": {
                        "issue": "DRGN-29270", "acknowledged_transitions": ordinal,
                        "increased_latency_timeout_acknowledgements": ordinal,
                        "boundary_payloads": ordinal,
                    }}})
                    child = save("child", {"native_evidence": native})
                    receipt = save("receipt", {"child_evidence": child})
                    group = save("group", {"campaign_results": [{
                        "id": campaign, "evidence": receipt,
                        "semantic_status": {"subrating_ack_boundary": "PASS",
                                            "latency_timeout": "PASS"},
                    }]})
                    paths[(field, identifier)] = folder / group["path"]
                with mock.patch.object(MODULE, "CAMPAIGN_REGISTRIES", registries), \
                        mock.patch.object(MODULE, "CAMPAIGNS", {campaign: {}}), \
                        mock.patch.object(MODULE, "SDK_RISK_CAMPAIGNS", risks), \
                        mock.patch.object(MODULE, "validate_campaign_evidence") as validate, \
                        mock.patch.object(MODULE, "snapshot", return_value={
                            "source_revision": REVISION, "source_clean": True,
                            "prerequisite_blockers": [],
                        }), \
                        mock.patch.object(MODULE, "campaign_matrix_paths", return_value=paths):
                    observations = MODULE.collect_campaign_observations(paths, REVISION, base)
                    self.assertEqual(2, len(observations[campaign]))
                    self.assertNotEqual(observations[campaign][0]["receipt"],
                                        observations[campaign][1]["receipt"])
                    report = MODULE.produce_sdk_risks(base / "matrix.json", base)
                    self.assertEqual("EVIDENCE_RECORDED", report["status"])
                    self.assertEqual(4, validate.call_count)
                    document = MODULE.read_json(base / "risk.DRGN-29270.json")
                    self.assertEqual(2, document["schema_version"])
                    self.assertEqual(2, len(document["campaign_evidence"]))
                    for source in document["campaign_evidence"]:
                        for reference in (source["group"]["evidence"], source["receipt"],
                                          source["child_evidence"], source["native_evidence"]):
                            MODULE.bundle_evidence_file(reference, base)
                            self.assertEqual(nested,
                                             reference["path"].startswith(".campaign-attempts/"))

    def test_sdk_risk_rejects_missing_duplicate_and_reordered_executions(self):
        """! @brief 독립 group 실행을 하나로 축약하거나 순서를 바꾸어 위험을 숨기지 않습니다. """

        campaign = "m32_timing"
        registries = {"families": {"one": (campaign,)},
                      "resources": {"two": (campaign,)}, "automatic_peers": {}}
        observations = [{"campaign_id": campaign, "group": {"field": field, "id": identifier}}
                        for field, identifier in (("families", "one"), ("resources", "two"))]
        with mock.patch.object(MODULE, "CAMPAIGN_REGISTRIES", registries), \
                mock.patch.object(MODULE, "SDK_RISK_CAMPAIGNS", {
                    "DRGN-29270": MODULE.SDK_RISK_CAMPAIGNS["DRGN-29270"]}), \
                mock.patch.object(MODULE, "_risk_condition_observed") as condition:
            for altered in ([], observations[:1], observations[::-1],
                            [observations[0], observations[0]], observations + [None],
                            [{"campaign_id": campaign, "group": None}]):
                with self.subTest(altered=altered), self.assertRaisesRegex(ValueError, "denominator"):
                    MODULE.derive_sdk_risk_documents({campaign: altered}, REVISION)
            condition.assert_not_called()

    def test_sdk_risk_checks_later_malformed_raw_after_unobserved_condition(self):
        """! @brief 첫 실행의 NOT_RUN이 후속 실행의 잘못된 raw 검사를 단락시키지 않습니다. """

        campaign = "m33_diagnostics_dtm"
        observations = [{
            "campaign_id": campaign, "group": {"field": field, "id": identifier},
            "semantic_status": {}, "native": {"rf_boundary": {
                "controlled_noisy_rf": "NOT_RUN", "sdk_risk": {
                    "id": "DRGN-29228", "status": "CONDITION_NOT_MET"}}},
        } for field, identifier in (("families", "one"), ("resources", "two"))]
        observations[1]["native"] = {}
        registries = {"families": {"one": (campaign,)},
                      "resources": {"two": (campaign,)}, "automatic_peers": {}}
        with mock.patch.object(MODULE, "CAMPAIGN_REGISTRIES", registries), \
                mock.patch.object(MODULE, "SDK_RISK_CAMPAIGNS", {
                    "DRGN-29228": MODULE.SDK_RISK_CAMPAIGNS["DRGN-29228"]}), \
                self.assertRaisesRegex(ValueError, "raw RF boundary"):
            MODULE.derive_sdk_risk_documents({campaign: observations}, REVISION)

    def test_bundle_references_reject_escape_alias_link_and_hash_drift(self):
        """! @brief nested 참조 허용이 경로 탈출·link·byte 변경 허용으로 넓어지지 않습니다. """

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            folder = base / "nested"
            folder.mkdir()
            path = folder / "result.json"
            path.write_text("{}\n", encoding="utf-8")
            reference = MODULE._content_reference(path, base)
            self.assertEqual(path, MODULE.bundle_evidence_file(reference, base))
            for alias in ("../result.json", "nested/../nested/result.json",
                          "./nested/result.json", "nested\\result.json", str(path)):
                with self.subTest(alias=alias), self.assertRaisesRegex(ValueError, "inside the bundle"):
                    MODULE.bundle_evidence_file({**reference, "path": alias}, base)
            with self.assertRaisesRegex(ValueError, "inside the bundle"):
                MODULE._content_reference(base.parent / "external.json", base)
            with mock.patch.object(Path, "is_symlink", return_value=True), \
                    self.assertRaisesRegex(ValueError, "must not be a link"):
                MODULE.bundle_evidence_file(reference, base)
            with mock.patch.object(Path, "is_symlink", return_value=True), \
                    self.assertRaisesRegex(ValueError, "must not be a link"):
                MODULE.adjacent_evidence_file({**reference, "path": path.name}, folder)
            path.write_text('{"changed":true}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                MODULE.bundle_evidence_file(reference, base)

    def test_host_appends_to_bundle_and_preflights_all_planned_outputs(self):
        """! @brief campaign/soak 파일은 보존하고 예정 Host 파일 충돌은 실행 전에 거부합니다. """

        class Process:
            """! @brief 단일 Host 단위 시험 subprocess fixture입니다. """

            pid = 17
            returncode = 0

            @staticmethod
            def communicate(timeout: int) -> tuple[bytes, bytes]:
                del timeout
                return b"fixture", b""

        parsed = {
            "exit_code": 0,
            "tests_run": 1,
            "skipped": 0,
            "test_ids": ["fixture"],
            "test_ids_sha256": hashlib.sha256(b"fixture").hexdigest(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            retained = output / "campaign-group.01.json"
            retained.write_text("retained\n", encoding="utf-8")
            conflict = output / "test_m33_regression.py.log"
            conflict.write_text("existing\n", encoding="utf-8")
            with mock.patch.object(MODULE, "HOST_TESTS", ["test_m33_regression.py"]), \
                    mock.patch.object(MODULE.subprocess, "Popen") as popen, \
                    self.assertRaisesRegex(ValueError, "overwrite refused"):
                MODULE.run_host(output, ROOT)
            popen.assert_not_called()
            self.assertEqual("existing\n", conflict.read_text(encoding="utf-8"))
            conflict.unlink()
            check_output = [REVISION + "\n", "", REVISION + "\n", ""]
            with mock.patch.object(MODULE, "HOST_TESTS", ["test_m33_regression.py"]), \
                    mock.patch.object(MODULE.subprocess, "check_output",
                                      side_effect=check_output), \
                    mock.patch.object(MODULE.subprocess, "Popen",
                                      return_value=Process()), \
                    mock.patch.object(MODULE, "parse_unittest_log",
                                      return_value=parsed), \
                    mock.patch.object(MODULE, "host_log_matches_contract",
                                      return_value=True):
                result = MODULE.run_host(output, ROOT)
            self.assertEqual("PASS", result["status"])
            self.assertEqual("retained\n", retained.read_text(encoding="utf-8"))
            self.assertTrue((output / "result.json").is_file())

    def test_matrix_orchestrator_orders_groups_resumes_and_rejects_partial(self):
        """! @brief matrix는 완료 group을 resume하고 부분 attempt 다음 번호에서 재개합니다. """

        registries = {
            "families": {"one": ("a",), "two": ("b",)},
            "resources": {"three": ("c",)},
            "automatic_peers": {},
        }
        prepared = []
        executed = []

        def prepare(field, identifier, *_args):
            prepared.append((field, identifier))
            return {
                "field": field,
                "id": identifier,
                "source_revision": REVISION,
            }

        def execute(spec_path, output, _root):
            executed.append((spec_path.name, output.name))
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            output.write_text(json.dumps({
                "field": spec["field"],
                "id": spec["id"],
                "source_revision": REVISION,
            }) + "\n", encoding="utf-8")
            return {}

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            inventory = base / "inventory.json"
            inventory.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(RUNNER, "CAMPAIGN_REGISTRIES", registries), \
                    mock.patch.object(MODULE, "CAMPAIGN_REGISTRIES", registries), \
                    mock.patch.object(RUNNER, "_git_identity",
                                      return_value=(REVISION, True)), \
                    mock.patch.object(RUNNER, "prepare_execution_spec",
                                      side_effect=prepare), \
                    mock.patch.object(RUNNER, "execute_campaign_spec",
                                      side_effect=execute), \
                    mock.patch.object(RUNNER, "_validate_completed_matrix_group",
                                      return_value={}):
                result = RUNNER.execute_campaign_matrix(
                    inventory, base, base, base, base, ROOT
                )
                resumed = RUNNER.execute_campaign_matrix(
                    inventory, base, base, base, base, ROOT
                )
            self.assertEqual(
                [("families", "one"), ("families", "two"),
                 ("resources", "three")], prepared
            )
            self.assertEqual(3, len(executed))
            self.assertEqual(result, resumed)
            self.assertEqual(
                ".campaign-attempts/campaign-group.01.families.one."
                "attempt-1/spec.json",
                result["groups"][0]["spec"]["path"],
            )
            self.assertEqual(1, result["groups"][0]["attempt"])
            self.assertEqual(["PASS"], [
                row["status"] for row in result["groups"][0]["attempts"]
            ])
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            inventory = base / "inventory.json"
            inventory.write_text("{}\n", encoding="utf-8")
            partial, _partial_result = RUNNER._matrix_group_paths(
                base, 1, "families", "one", 1
            )
            partial.parent.mkdir(parents=True)
            partial.write_text("partial-attempt\n", encoding="utf-8")
            prepared.clear()
            executed.clear()
            with mock.patch.object(RUNNER, "CAMPAIGN_REGISTRIES", registries), \
                    mock.patch.object(MODULE, "CAMPAIGN_REGISTRIES", registries), \
                    mock.patch.object(RUNNER, "_git_identity",
                                      return_value=(REVISION, True)), \
                    mock.patch.object(RUNNER, "prepare_execution_spec",
                                      side_effect=prepare), \
                    mock.patch.object(RUNNER, "execute_campaign_spec",
                                      side_effect=execute), \
                    mock.patch.object(RUNNER, "_validate_completed_matrix_group",
                                      return_value={}):
                retried = RUNNER.execute_campaign_matrix(
                    inventory, base, base, base, base, ROOT
                )
            self.assertEqual("partial-attempt\n",
                             partial.read_text(encoding="utf-8"))
            self.assertEqual(2, retried["groups"][0]["attempt"])
            self.assertEqual(["INCOMPLETE", "PASS"], [
                row["status"] for row in retried["groups"][0]["attempts"]
            ])
            self.assertEqual(
                ".campaign-attempts/campaign-group.01.families.one."
                "attempt-2/spec.json",
                retried["groups"][0]["spec"]["path"],
            )
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            inventory = base / "inventory.json"
            inventory.write_text("{}\n", encoding="utf-8")
            failed_spec, failed_result = RUNNER._matrix_group_paths(
                base, 1, "families", "one", 1
            )
            failed_spec.parent.mkdir(parents=True)
            failed_spec.write_text("failed-spec\n", encoding="utf-8")
            failed_result.write_text("failed-result\n", encoding="utf-8")

            def validate(spec_path, *_args):
                if spec_path == failed_spec:
                    raise ValueError("stored failed attempt")
                return {}

            prepared.clear()
            executed.clear()
            with mock.patch.object(RUNNER, "CAMPAIGN_REGISTRIES", registries), \
                    mock.patch.object(MODULE, "CAMPAIGN_REGISTRIES", registries), \
                    mock.patch.object(RUNNER, "_git_identity",
                                      return_value=(REVISION, True)), \
                    mock.patch.object(RUNNER, "prepare_execution_spec",
                                      side_effect=prepare), \
                    mock.patch.object(RUNNER, "execute_campaign_spec",
                                      side_effect=execute), \
                    mock.patch.object(RUNNER,
                                      "_validate_completed_matrix_group",
                                      side_effect=validate):
                with self.assertRaisesRegex(ValueError, "stored failed attempt"):
                    RUNNER.execute_campaign_matrix(
                        inventory, base, base, base, base, ROOT
                    )
            self.assertEqual("failed-spec\n",
                             failed_spec.read_text(encoding="utf-8"))
            self.assertEqual("failed-result\n",
                             failed_result.read_text(encoding="utf-8"))
            self.assertEqual([], executed)
            self.assertEqual([], prepared)

    def test_matrix_failure_receipt_preserves_log_and_resumes_next_attempt(self):
        """! @brief 실패 byte를 봉인하고 손상·안전 실패는 다음 group 실행 전에 차단합니다. """

        registries = {"families": {"one": ("a",)}, "resources": {}, "automatic_peers": {}}
        for mode in ("resume", "tamper", "SAFETY"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                inventory = base / "inventory.json"
                inventory.write_text("{}\n", encoding="utf-8")
                spec = {"field": "families", "id": "one", "source_revision": REVISION}

                def fail(_spec, output, _root):
                    (output.parent / "raw.log").write_bytes(b"original failure")
                    raise RUNNER.execution.ExecutionFailure(
                        "SAFETY" if mode == "SAFETY" else "TRANSPORT", "failure"
                    )

                def complete(_spec, output, _root):
                    output.write_text(json.dumps(spec), encoding="utf-8")

                with mock.patch.object(RUNNER, "CAMPAIGN_REGISTRIES", registries), \
                        mock.patch.object(MODULE, "CAMPAIGN_REGISTRIES", registries), \
                        mock.patch.object(RUNNER, "_git_identity", return_value=(REVISION, True)), \
                        mock.patch.object(RUNNER, "prepare_execution_spec", return_value=spec), \
                        mock.patch.object(RUNNER, "_validate_completed_matrix_group", return_value={}):
                    with mock.patch.object(RUNNER, "execute_campaign_spec", side_effect=fail), \
                            self.assertRaises(RUNNER.execution.ExecutionFailure):
                        RUNNER.execute_campaign_matrix(inventory, base, base, base, base, ROOT)
                    first, _ = RUNNER._matrix_group_paths(base, 1, "families", "one", 1)
                    failure_path = first.parent / "failure.json"
                    original = failure_path.read_bytes()
                    if mode == "tamper":
                        (first.parent / "raw.log").write_bytes(b"tampered")
                    with mock.patch.object(RUNNER, "execute_campaign_spec", side_effect=complete) as run:
                        if mode == "resume":
                            value = RUNNER.execute_campaign_matrix(inventory, base, base, base, base, ROOT)
                            self.assertEqual(2, value["groups"][0]["attempt"])
                            self.assertIn("failure", value["groups"][0]["attempts"][0])
                            run.assert_called_once()
                        else:
                            with self.assertRaises(ValueError):
                                RUNNER.execute_campaign_matrix(inventory, base, base, base, base, ROOT)
                            run.assert_not_called()
                    self.assertEqual(original, failure_path.read_bytes())

    def test_campaign_timeout_keeps_partial_output(self):
        """! @brief child timeout의 원본 출력이 안전 실패보다 먼저 저장됩니다. """

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            item = {"row": {"timeout_seconds": 1}, "expected": {"id": "test"},
                    "command": ["test-runner"], "native": base / "native.json", "board_plan": {}}
            process = mock.Mock()
            process.communicate.side_effect = [subprocess.TimeoutExpired("test", 1), (b"partial output", None)]
            with mock.patch.object(RUNNER, "_state_restore_plan", return_value={}), \
                    mock.patch.object(RUNNER, "_campaign_probe_authority", return_value=nullcontext(({}, None))), \
                    mock.patch.object(RUNNER, "_restore_campaign_state"), \
                    mock.patch.object(RUNNER.subprocess, "Popen", return_value=process), \
                    self.assertRaises(RUNNER.execution.ExecutionFailure) as caught:
                RUNNER._run_pending_campaign(item, base / "result.json", {},
                                             {"source_revision": REVISION}, {}, ROOT)
            self.assertEqual("SAFETY", caught.exception.category)
            self.assertEqual(b"partial output", (base / "campaign.test.log").read_bytes())
            process.kill.assert_called_once()

    def test_template_campaign_never_claims_external_or_physical_pass(self):
        """! @brief Fast Pair 등 template build는 제품 peer·실물 HIL PASS로 승격하지 않습니다. """
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            path, document = self.campaign_fixture(
                base, "families", "ecosystem_templates"
            )
            result = MODULE.validate_campaign_evidence(
                document, path, "families", "ecosystem_templates", REVISION,
                allow_fixture=True
            )
            self.assertEqual("SCHEMA_VALID", result["status"])
            row = document["campaign_results"][0]
            self.assertEqual("build_semantic", row["verification"])
            receipt = MODULE.read_json(Path(temporary) / row["evidence"]["path"])
            self.assertEqual([], receipt["hardware"])
            expected = MODULE.campaign_plan(
                "families", "ecosystem_templates"
            )["campaigns"][0]
            self.assertEqual({}, RUNNER._validate_board_plan([], expected))
            with self.assertRaises(ValueError):
                RUNNER._validate_board_plan([{
                    "role": "fake",
                    "probe_sha256": "a" * 64,
                }], expected)
            document["external_interoperability"] = "PASS"
            with self.assertRaises(ValueError):
                MODULE.validate_campaign_evidence(
                    document, path, "families", "ecosystem_templates", REVISION,
                    allow_fixture=True
                )

            definition = MODULE.CAMPAIGNS["m33_ecosystem_templates"]
            self.assertEqual(
                "libraries/NUCODE_BLE_Companion/tools/m33_template_build.py",
                definition["runner"],
            )
            negative_ids = [
                "test_credentials_reject_missing_unknown_and_invalid_fast_pair_values",
                "test_credentials_reject_production_debug_and_low_entropy_values",
                "test_mds_credentials_reject_invalid_and_placeholder_values",
                "test_prepare_rejects_missing_internal_or_drifted_inputs",
            ]
            negative_log = base / "credential-negative.log"
            negative_log.write_text(
                "\n".join(negative_ids) + "\nRan 4 tests\n\nOK\n",
                encoding="utf-8",
            )
            lock = MODULE.read_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
            source_paths = {
                "fast_pair_input": "nrf/samples/bluetooth/fast_pair/input_device",
                "fast_pair_locator": "nrf/samples/bluetooth/fast_pair/locator_tag",
                "enocean": "nrf/samples/bluetooth/enocean",
                "mds": "nrf/samples/bluetooth/peripheral_mds",
            }
            typed_results = []
            for kind, source_path in source_paths.items():
                artifact_names = [
                    "build/source/zephyr/zephyr.elf",
                    "build/source/zephyr/zephyr.hex",
                    "build/source/zephyr/.config",
                ]
                if kind.startswith("fast_pair_"):
                    artifact_names.append(
                        "build/modules/nrf/subsys/bluetooth/fast_pair/"
                        "fp_provisioning_data.hex"
                    )
                artifacts = {}
                artifact_files = {}
                for index, relative in enumerate(artifact_names, 1):
                    artifact_path = base / f"{kind}.artifact.{index}.bin"
                    artifact_path.write_bytes(
                        f"{kind}:{relative}:actual".encode("ascii")
                    )
                    artifacts[relative] = MODULE.digest(artifact_path)
                    artifact_files[relative] = {
                        "path": artifact_path.name,
                        "sha256": MODULE.digest(artifact_path),
                        "size": artifact_path.stat().st_size,
                        "confidentiality": (
                            "external-build-evidence" if kind == "enocean" else
                            "external-test-credential-evidence"
                        ),
                    }
                command = ["python", "-m", "west", "build", kind]
                upstream_files = {f"{source_path}/CMakeLists.txt": "a" * 64}
                generated_sources = {"source/CMakeLists.txt": "b" * 64}
                manifest = {
                    "schema_version": 1,
                    "kind": kind,
                    "source_path": source_path,
                    "ncs_revision": lock["ncs"]["revision"],
                    "zephyr_revision": lock["zephyr"]["revision"],
                    "board_revision": lock["board"]["revision"],
                    "automatic_flash": False,
                    "external_interoperability": "NOT_RUN",
                    "build_exit_code": 0,
                    "command": command,
                    "upstream_files": upstream_files,
                    "generated_source_sha256": generated_sources,
                    "artifacts": dict(artifacts),
                }
                manifest_path = base / f"{kind}.manifest.json"
                log_path = base / f"{kind}.build.log"
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                log_path.write_text("redacted exact build", encoding="utf-8")
                typed_results.append({
                    "kind": kind,
                    "status": "PASS",
                    "exit_code": 0,
                    "runtime": "NOT_RUN",
                    "source_path": source_path,
                    "credential_mode": "none" if kind == "enocean" else "test",
                    "manifest": {"path": manifest_path.name,
                                 "sha256": MODULE.digest(manifest_path)},
                    "build_log": {"path": log_path.name,
                                  "sha256": MODULE.digest(log_path)},
                    "command": command,
                    "command_sha256": hashlib.sha256(json.dumps(
                        command, separators=(",", ":")
                    ).encode("utf-8")).hexdigest(),
                    "upstream_files": upstream_files,
                    "generated_source_sha256": generated_sources,
                    "artifacts": artifacts,
                    "artifact_files": artifact_files,
                    "automatic_flash": False,
                    "external_interoperability": "NOT_RUN",
                })
            native = {
                "schema_version": 1,
                "kind": "m33_ecosystem_template_builds",
                "status": "PASS",
                "source_revision": REVISION,
                "source_clean": True,
                "ncs_revision": lock["ncs"]["revision"],
                "zephyr_revision": lock["zephyr"]["revision"],
                "board_revision": lock["board"]["revision"],
                "credential_negative": {
                    "path": negative_log.name,
                    "sha256": MODULE.digest(negative_log),
                    "test_ids": negative_ids,
                    "exit_code": 0,
                },
                "results": typed_results,
                "external_interoperability": "NOT_RUN",
            }
            native_path = base / "companion-build-results.json"
            native_path.write_text(json.dumps(native), encoding="utf-8")
            RUNNER._validate_template_native_raw(native, native_path, REVISION)
            changed = copy.deepcopy(native)
            changed["results"][1]["kind"] = "fast_pair_input"
            with self.assertRaisesRegex(ValueError, "denominator"):
                RUNNER._validate_template_native_raw(
                    changed, native_path, REVISION
                )
            changed = copy.deepcopy(native)
            changed["results"][0]["artifacts"]["private-secret.hex"] = "d" * 64
            with self.assertRaisesRegex(ValueError, "typed result"):
                RUNNER._validate_template_native_raw(
                    changed, native_path, REVISION
                )
            template_source = (
                ROOT / definition["runner"]
            ).read_text(encoding="utf-8")
            self.assertIn("public template evidence contains credential bytes",
                          template_source)
            self.assertIn("set(artifacts) == _expected_artifacts(kind)",
                          template_source)

    def test_closure_assembler_binds_existing_actual_evidence_without_new_pass(self):
        """! @brief 기존 actual 파일만 참조하고 33+8+8·7·3 분모를 재검증합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            output = base / "closure.json"
            current = {
                "source_revision": REVISION,
                "source_clean": True,
                "prerequisite_blockers": [],
                "inputs": {"M33": {"path": "readiness.json", "sha256": "a" * 64}},
                "lock_sha256": "b" * 64,
            }
            host = base / "host.json"
            soak = base / "soak.json"
            host.write_text('{"existing":"host"}\n', encoding="utf-8")
            soak.write_text('{"existing":"soak"}\n', encoding="utf-8")
            campaigns = {}
            for field, registry in MODULE.CAMPAIGN_REGISTRIES.items():
                for identifier in registry:
                    folder = base / ".campaign-attempts" / f"{field}.{identifier}.attempt-1"
                    folder.mkdir(parents=True)
                    path = folder / "result.json"
                    path.write_text(json.dumps({
                        "status": "PASS",
                        "source_revision": REVISION,
                        "source_clean": True,
                    }), encoding="utf-8")
                    campaigns[(field, identifier)] = path
            risks = {}
            for risk_id, plan in MODULE.SDK_RISK_CAMPAIGNS.items():
                condition_observed = plan["allowed_status"] == ("PASS",)
                status = "PASS" if condition_observed else "CONDITION_NOT_MET"
                path = base / f"risk.{risk_id}.json"
                path.write_text(json.dumps({
                    "schema_version": 2,
                    "kind": "m33_sdk_risk_result",
                    "id": risk_id,
                    "status": status,
                    "condition": plan["condition"],
                    "condition_observed": condition_observed,
                    "cause_status": (
                        "conditional_regression" if condition_observed else
                        "not_reproduced_not_assumed"
                    ),
                    "campaigns": list(plan["campaigns"]),
                    "campaign_evidence": [],
                    "source_revision": REVISION,
                    "source_clean": True,
                }), encoding="utf-8")
                risks[risk_id] = path
            qualification = base / "qualification.json"
            qualification.write_text(json.dumps({
                "schema_version": 1,
                "kind": "m33_qualification_results",
                "source_revision": REVISION,
                "source_clean": True,
                "qualification": [{
                    "component": component,
                    "applicability": "applicable",
                    "component_status": "EVIDENCE_RECORDED",
                    "product_status": "NOT_ASSESSED",
                    "example_status_implied": False,
                    "component_version": "NCS 3.4.0 LTS",
                    "design_identifier": (
                        "NOT_LISTED_NO_DN" if component == "mesh" else
                        "PLANNED_NO_DN"
                    ),
                    "official_reference": "https://example.invalid/qualification",
                    "remaining_product_procedure": "별도 제품 자격 절차 필요",
                } for component in ("host", "controller", "mesh")],
            }), encoding="utf-8")

            def validate(document, bundle, observed):
                self.assertFalse(output.exists())
                self.assertEqual(base, bundle)
                self.assertEqual(current, observed)
                return {
                    "status": "AUDIT_ONLY",
                    "actual_run": "NOT_VERIFIED",
                    "scope": "stored-evidence-integrity-only",
                    "source_revision": REVISION,
                    "families": 33,
                    "resource_groups": 8,
                    "automatic_peer_groups": 8,
                    "product_qualification": "NOT_ASSESSED",
                }

            with mock.patch.object(MODULE, "snapshot", return_value=current), \
                    mock.patch.object(MODULE, "validate_campaign_evidence") as campaign_validator, \
                    mock.patch.object(MODULE, "validate_closure", side_effect=validate) as closure_validator:
                document = MODULE.assemble_closure(
                    output, host, soak, campaigns, risks, qualification, ROOT
                )
            self.assertEqual(49, campaign_validator.call_count)
            closure_validator.assert_called_once()
            self.assertEqual((33, 8, 8), (
                len(document["families"]), len(document["resources"]),
                len(document["automatic_peers"]),
            ))
            self.assertEqual(7, len(document["sdk_risk_results"]))
            self.assertEqual(3, len(document["qualification"]))
            for field, registry in MODULE.CAMPAIGN_REGISTRIES.items():
                for row in document[field]:
                    self.assertEqual(campaigns[(field, row["id"])],
                                     MODULE.bundle_evidence_file(row["evidence"], base))
            self.assertEqual(
                {"path": qualification.name,
                 "sha256": MODULE.digest(qualification)},
                document["qualification_evidence"],
            )
            self.assertTrue(all(
                row["product_status"] == "NOT_ASSESSED"
                for row in document["qualification"]
            ))
            self.assertTrue(all(
                row["status"] == "NOT_RUN" and row["evidence"] is None
                for row in document["external_peers"]
            ))
            self.assertEqual(document, json.loads(output.read_text(encoding="utf-8")))

    def test_closure_assembler_rejects_missing_nonadjacent_and_overwrite_inputs(self):
        """! @brief 누락·bundle 외부 참조·기존 출력은 파일 생성 전에 거부합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            output = base / "closure.json"
            current = {
                "source_revision": REVISION,
                "source_clean": True,
                "prerequisite_blockers": [],
            }
            with mock.patch.object(MODULE, "snapshot", return_value=current), \
                    self.assertRaisesRegex(ValueError, "denominator"):
                MODULE.assemble_closure(
                    output, base / "host.json", base / "soak.json", {}, {},
                    base / "qualification.json", ROOT
                )
            self.assertFalse(output.exists())
            external = base.parent / f"{base.name}.external.json"
            external.write_text("{}\n", encoding="utf-8")
            try:
                with self.assertRaisesRegex(ValueError, "adjacent"):
                    MODULE._closure_reference(external, output, "external")
            finally:
                external.unlink()
            output.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "new closure"):
                MODULE.assemble_closure(
                    output, base / "host.json", base / "soak.json", {}, {},
                    base / "qualification.json", ROOT
                )

    def test_closure_cli_named_paths_rejects_duplicates(self):
        """! @brief CLI named evidence 중복과 malformed key를 fail-closed로 거부합니다. """
        self.assertEqual(
            {("families", "gap_links"): Path("actual.json")},
            MODULE._named_paths(["families:gap_links=actual.json"], True),
        )
        self.assertEqual(
            {"DRGN-29270": Path("risk.json")},
            MODULE._named_paths(["DRGN-29270=risk.json"], False),
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            MODULE._named_paths([
                "families:gap_links=one.json",
                "families:gap_links=two.json",
            ], True)
        with self.assertRaisesRegex(ValueError, "field:id"):
            MODULE._named_paths(["gap_links=actual.json"], True)
        with mock.patch.object(
                MODULE, "assemble_closure", return_value={"schema_version": 1}), \
                mock.patch.object(sys, "argv", [
                    "m33_regression.py", "assemble",
                    "--output", "closure.json",
                    "--host-regression", "host.json",
                    "--soak", "soak.json",
                    "--qualification-evidence", "qualification.json",
                ]), mock.patch("builtins.print"):
            self.assertEqual(0, MODULE.main())

    def test_closure_rejects_fake_raw_evidence_instead_of_synthetic_pass(self):
        """! @brief fresh soak 뒤에도 임의 log와 hash 문자열로 전체 closure를 만들 수 없습니다. """
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            soak_path, soak = self.soak_fixture(base / "soak")
            revision = soak["identity"]["core"]
            lock_path = ROOT / "tools/ci/ncs-3.4.0.lock.json"
            current = {"source_revision": revision, "source_clean": True, "prerequisite_blockers": [],
                       "inputs": {"test-only": True}, "lock_sha256": MODULE.digest(lock_path)}
            host = {"source_revision": revision, "source_clean": True, "status": "PASS",
                    "scope": "Host-regression-only", "records": []}
            for test in MODULE.HOST_TESTS:
                log = base / (test + ".log")
                log.write_text("Ran 1 test in 0.001s\nOK\n", encoding="utf-8")
                host["records"].append({"test": test, "exit_code": 0, "tests_run": 1, "skipped": 0,
                                        "test_sha256": MODULE.digest(ROOT / "tests/host" / test),
                                        "command": MODULE.host_command(test),
                                        "log_sha256": MODULE.digest(log)})
            host_path = base / "host.json"
            host_path.write_text(json.dumps(host), encoding="utf-8")
            fake_log = base / "fake.log"
            fake_log.write_text("synthetic schema fixture, not hardware evidence", encoding="utf-8")
            first = next(iter(MODULE.FAMILIES))
            fake_raw = {"schema_version": 1, "evidence_kind": "m33_family_hil_result",
                        "id": first, "status": "PASS", "source_revision": revision, "source_clean": True,
                        "denominator": 1, "completed": 1, "failures": 0,
                        "scope": "current_functional_hil", "images": ["b" * 64],
                        "transcript": {"path": fake_log.name, "sha256": MODULE.digest(fake_log)}}
            fake_path = base / "fake-raw.json"
            fake_path.write_text(json.dumps(fake_raw), encoding="utf-8")
            fake_reference = {"path": str(fake_path), "sha256": MODULE.digest(fake_path)}
            document = {"schema_version": 1, **current, "negative_classes": sorted(MODULE.NEGATIVES),
                        "host_regression": {"path": str(host_path), "sha256": MODULE.digest(host_path)},
                        "soak": {"path": str(soak_path), "sha256": MODULE.digest(soak_path)},
                        "families": [{"id": identifier, "status": "PASS", "source_revision": revision,
                                      "evidence": fake_reference} for identifier in MODULE.FAMILIES],
                        "resources": [], "automatic_peers": [], "external_peers": MODULE.peer_matrix(),
                        "qualification": []}
            with self.assertRaises((ValueError, TypeError)):
                MODULE.validate_closure(document, base, current)

    def test_run_host_dirty_source_fails_and_main_returns_nonzero(self):
        """! @brief Host test가 성공해도 시작 checkout이 dirty이면 PASS와 exit 0을 만들지 않습니다. """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test_dir = root / "tests" / "host"
            test_dir.mkdir(parents=True)
            test_path = test_dir / "test_dummy.py"
            test_path.write_text("import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n",
                                 encoding="utf-8")
            marker = root / "tracked.txt"
            marker.write_text("clean\n", encoding="utf-8")
            for command in (("git", "init", "-q"),
                            ("git", "config", "user.email", "test@example.invalid"),
                            ("git", "config", "user.name", "M33 test"),
                            ("git", "add", "."), ("git", "commit", "-qm", "fixture")):
                subprocess.run(command, cwd=root, check=True, capture_output=True)
            marker.write_text("dirty\n", encoding="utf-8")
            expected_ids = ["T.test_ok"]
            expected_ids_sha256 = hashlib.sha256("\n".join(expected_ids).encode("utf-8")).hexdigest()
            with mock.patch.object(MODULE, "HOST_TESTS", [test_path.name]), \
                    mock.patch.object(MODULE, "HOST_TEST_EXPECTATIONS",
                                      {test_path.name: (1, expected_ids_sha256)}):
                result = MODULE.run_host(root / "host-evidence", root)
            self.assertEqual("FAIL", result["status"])
            self.assertFalse(result["source_clean"])
            record = result["records"][0]
            self.assertEqual(MODULE.digest(test_path), record["test_sha256"])
            self.assertEqual(MODULE.host_command(test_path.name), record["command"])
            log = (root / "host-evidence" / (test_path.name + ".log")).read_bytes()
            parsed = MODULE.parse_unittest_log(log)
            self.assertEqual((0, 1, 0),
                             (parsed["exit_code"], parsed["tests_run"], parsed["skipped"]))
            self.assertEqual(expected_ids, parsed["test_ids"])
            self.assertEqual(1, MODULE.parse_unittest_log(
                b"Ran 99 tests in 0.001s\nFAILED\n")["exit_code"])
            self.assertEqual(
                1,
                MODULE.parse_unittest_log(
                    b"----------------------------------------------------------------------\n"
                    b"Ran 1 test in 0.001s\n\nFAILED\nOK\n"
                )["exit_code"],
            )
        with mock.patch.object(MODULE, "run_host",
                               return_value={"status": "FAIL", "scope": "Host-regression-only"}), \
                mock.patch.object(sys, "argv", ["m33_regression.py", "host", "--output", "unused"]), \
                mock.patch("builtins.print"):
            self.assertEqual(1, MODULE.main())

    def test_soak_clean_recheck_ignores_only_its_output_files(self):
        """! @brief fresh runner 출력은 제외하되 실행 중 source 변경은 dirty로 판정합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracked = root / "tracked.txt"
            tracked.write_text("clean\n", encoding="utf-8")
            for command in (("git", "init", "-q"),
                            ("git", "config", "user.email", "test@example.invalid"),
                            ("git", "config", "user.name", "M33 test"),
                            ("git", "add", "."), ("git", "commit", "-qm", "fixture")):
                subprocess.run(command, cwd=root, check=True, capture_output=True)
            output = root / "fresh-evidence.json"
            output.write_text("{}\n", encoding="utf-8")
            self.assertFalse(_checkout_dirty(root, (output,)))
            self.assertTrue(_checkout_dirty(root))
            tracked.write_text("changed\n", encoding="utf-8")
            self.assertTrue(_checkout_dirty(root, (output,)))

    def _external_closure_fixture(self, root):
        """! @brief hash 경계 시험용 byte를 만들며 물리 oracle만 명시적으로 격리합니다. """

        bundle = root / "private"
        bundle.mkdir()
        raw = bundle / "nested" / "firmware.artifact.hex"
        raw.parent.mkdir()
        raw.write_bytes(b"private-test-only-payload\x00")
        manifest = bundle / "closure.json"
        manifest.write_text(json.dumps({"schema_version": 1,
                            "source_revision": REVISION, "source_clean": True}),
                            encoding="utf-8")
        audit = {"status": "AUDIT_ONLY", "actual_run": "NOT_VERIFIED",
                 "source_revision": REVISION}
        with mock.patch.object(MODULE, "snapshot", return_value={
                "source_revision": REVISION, "source_clean": True}), \
                mock.patch.object(MODULE, "validate_closure", return_value=audit) as validate:
            exported = MODULE.export_closure(manifest, root / "public")
        validate.assert_called_once()
        return bundle, root / "public" / "closure-reference.json", raw, exported

    def test_external_closure_exports_only_hashes_and_requires_actual_raw(self):
        """! @brief 공개 index에는 raw를 복사하지 않고 재배치된 원본 byte를 요구합니다. """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, reference, raw, exported = self._external_closure_fixture(root)
            self.assertEqual("EVIDENCE_REFERENCED", exported["status"])
            self.assertEqual({".gitattributes", "bundle-files.json", "closure-reference.json"},
                             {path.name for path in reference.parent.iterdir()})
            for path in reference.parent.iterdir():
                self.assertNotIn(raw.read_bytes(), path.read_bytes())
                self.assertNotIn(str(bundle).encode(), path.read_bytes())
            moved = root / "relocated"
            bundle.rename(moved)
            closure, base = MODULE.resolve_external_closure(reference, moved)
            self.assertEqual(moved, base)
            self.assertEqual(REVISION, closure["source_revision"])
            with mock.patch.dict(MODULE.os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, "raw bundle is required"):
                    MODULE.resolve_external_closure(reference)

    def test_external_closure_rejects_mutated_missing_extra_or_linked_raw(self):
        """! @brief 누락·추가·변조·link를 전체 byte 집합 검사에서 거부합니다. """

        for mutation in ("changed", "missing", "extra", "link"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                bundle, reference, raw, _ = self._external_closure_fixture(root)
                if mutation == "changed":
                    raw.write_bytes(b"changed")
                elif mutation == "missing":
                    raw.unlink()
                elif mutation == "extra":
                    (bundle / "extra.log").write_bytes(b"extra")
                else:
                    target = root / "outside"
                    target.mkdir()
                    (bundle / "linked").symlink_to(target, target_is_directory=True)
                with self.assertRaises((ValueError, OSError)):
                    MODULE.resolve_external_closure(reference, bundle)

    def test_external_closure_rejects_index_and_reference_tampering(self):
        """! @brief index hash·source·경로 우회는 원본 존재 여부와 무관하게 거부합니다. """

        for mutation in ("index", "source", "escape", "unknown", "duplicate"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                bundle, reference, _, value = self._external_closure_fixture(root)
                if mutation == "index":
                    (reference.parent / "bundle-files.json").write_text("{}", encoding="utf-8")
                elif mutation == "duplicate":
                    reference.write_text('{"kind":"first","kind":"second"}', encoding="utf-8")
                else:
                    if mutation == "source":
                        value["source_revision"] = "b" * 40
                    elif mutation == "escape":
                        value["bundle_manifest"]["path"] = "../bundle-files.json"
                    else:
                        value["unexpected"] = True
                    reference.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ValueError):
                    MODULE.resolve_external_closure(reference, bundle)

    def test_external_closure_export_rejects_overlap_and_overwrite(self):
        """! @brief 저장소·원본 내부 공개 출력과 기존 index 덮어쓰기를 거부합니다. """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, reference, _, _ = self._external_closure_fixture(root)
            for output in (reference.parent, bundle / "public", ROOT / "forbidden-export"):
                with self.subTest(output=output), self.assertRaisesRegex(ValueError, "new directory"):
                    MODULE.export_closure(bundle / "closure.json", output)
            with self.assertRaisesRegex(ValueError, "outside repository"):
                MODULE.resolve_external_closure(reference, bundle, root)

    def test_external_closure_cannot_export_a_metadata_only_physical_pass(self):
        """! @brief hash 시험 fixture를 실제 strict validator에 넣으면 공개 전에 실패합니다. """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle, _, _, _ = self._external_closure_fixture(root)
            current = MODULE.snapshot()
            current.update(source_revision=REVISION, source_clean=True)
            with mock.patch.object(MODULE, "snapshot", return_value=current):
                with self.assertRaises((ValueError, KeyError)):
                    MODULE.export_closure(bundle / "closure.json", root / "not-created")
            self.assertFalse((root / "not-created").exists())

    def test_duplicate_json_keys_and_missing_file_are_rejected(self):
        """! @brief 덮어쓴 status key와 실제 파일이 없는 성공 문자열을 거부합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "duplicate.json"
            path.write_text('{"status":"FAIL","status":"PASS"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                MODULE.read_json(path)
            with self.assertRaises(ValueError):
                MODULE.evidence_file({"path": str(path) + ".missing", "sha256": "a" * 64}, path.parent)


if __name__ == "__main__":
    unittest.main(verbosity=2)
