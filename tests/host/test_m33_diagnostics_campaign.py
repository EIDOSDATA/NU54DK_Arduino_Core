"""! @brief DTM dual-transport aggregate의 24-case와 phase provenance를 검사합니다. """
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/bluetooth"))
import m33_diagnostics_campaign as CAMPAIGN
from m33_regression import intel_hex_ranges


REVISION = "a" * 40


def digest(path: Path) -> str:
    """! @brief fixture byte hash를 반환합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hex_record(address: int, kind: int, data: bytes = b"") -> str:
    """! @brief 검사 fixture용 Intel HEX record를 만듭니다. """
    body = bytes([len(data)]) + address.to_bytes(2, "big") + bytes([kind]) + data
    checksum = (-sum(body)) & 0xFF
    return ":" + (body + bytes([checksum])).hex().upper()


class DiagnosticsCampaignTests(unittest.TestCase):
    def validate(self, path: Path, fixtures: dict[str, dict]) -> dict:
        """! @brief synthetic exact HEX와 prepared fixture로 aggregate를 검증합니다. """

        def load_fixture(child, _preflight, h4):
            transport = "h4" if h4 else "twowire"
            self.assertEqual(transport, Path(child).stem.split(".")[0])
            return fixtures[transport]

        def inspect_hex(child, expected_hash, identity):
            image = Path(child)
            self.assertEqual(expected_hash, hashlib.sha256(
                image.read_bytes()).hexdigest())
            self.assertEqual(REVISION + "c" * 64, identity)
            ranges = intel_hex_ranges(image)
            return {"sha256": expected_hash,
                    "raw": b"".join(data for _, data in ranges),
                    "ranges": ranges}

        with mock.patch.object(CAMPAIGN, "load_phase_fixture",
                               side_effect=load_fixture), \
                mock.patch.object(CAMPAIGN.diagnostics, "inspect_hex",
                                  side_effect=inspect_hex):
            return CAMPAIGN.validate_campaign(path, REVISION)

    @staticmethod
    def transcripts(transport: str, identity: str,
                    cases: list[dict]) -> list[list[dict]]:
        """! @brief production DtmPort로 재생 가능한 raw byte transcript를 만듭니다. """

        class Responder:
            def __init__(self, h4: bool, counts: list[int]):
                self.h4 = h4
                self.counts = list(counts)
                self.pending = bytearray()
                self.active = False

            def write(self, data: bytes) -> int:
                if self.h4:
                    opcode = int.from_bytes(data[1:3], "little")
                    parameters = data[4:]
                    if opcode == 0xFC80:
                        returned = b"\x00" + identity.encode("ascii")
                    elif opcode == 0x201F:
                        returned = b"\x00" + self.counts.pop(0).to_bytes(2, "little")
                        self.active = False
                    elif opcode == 0x201D and parameters == b"\x28":
                        returned = b"\x12"
                    elif opcode == 0x201E:
                        returned = b"\x12"
                    elif opcode == 0xFFFF:
                        returned = b"\x01"
                    elif opcode == 0x201D and parameters == b"\x13":
                        returned = b"\x0c"
                    else:
                        returned = b"\x00"
                        if opcode in (0x2033, 0x2034):
                            self.active = True
                    payload = b"\x01" + opcode.to_bytes(2, "little") + returned
                    self.pending.extend(b"\x04\x0e" + bytes([len(payload)]) + payload)
                else:
                    command = int.from_bytes(data, "big")
                    if 0x3F00 <= command < 0x3F00 + 104:
                        response = (ord(identity[command - 0x3F00]) << 1).to_bytes(2, "big")
                    elif command == 0xC000:
                        response = (0x8000 | self.counts.pop(0)).to_bytes(2, "big")
                        self.active = False
                    elif command in (0x6800, 0xA800, 0x06FF):
                        response = b"\x00\x01"
                    elif command & 0xC000 in (0x4000, 0x8000):
                        response = b"\x00\x01" if self.active else b"\x00\x00"
                        self.active = True
                    else:
                        response = b"\x00\x00"
                    self.pending.extend(response)
                return len(data)

            def read(self, size: int) -> bytes:
                if not self.pending:
                    self.active = False
                    if self.h4:
                        self.pending.extend(bytes.fromhex("040e06011f20000000"))
                    else:
                        self.pending.extend(b"\x80\x00")
                result = bytes(self.pending[:size])
                del self.pending[:size]
                return result

        h4 = transport == "h4"
        ports = []
        for role in (0, 1):
            counts = [0, 0, 0]
            counts.extend(0 if row["tx_role"] == role else row["received"]
                          for row in cases)
            counts.append(0)
            ports.append(CAMPAIGN.diagnostics.DtmPort(Responder(h4, counts), h4))
        for port in ports:
            if port.identity() != identity:
                raise AssertionError("DTM fixture identity response mismatch")
            port.stop()
        for port in ports:
            port.negative()
            port.start(False, 19, 1)
            port.automatic_stop()
            port.stop()
        for row in cases:
            tx = row["tx_role"]
            rx = row["rx_role"]
            ports[rx].start(False, row["channel"], row["phy"])
            ports[tx].start(True, row["channel"], row["phy"])
            ports[tx].stop()
            if ports[rx].stop() != row["received"]:
                raise AssertionError("DTM fixture packet count mismatch")
        for port in ports:
            port.stop()
        return [port.transcript for port in ports]

    def campaign(self, root: Path) -> tuple[Path, dict]:
        """! @brief two-wire/H4 각각 exact 12-case fixture를 만듭니다. """
        transports = []
        all_cases = []
        fixtures = {}
        final_hardware = None
        identity = REVISION + "c" * 64
        config_text = "CONFIG_WATCHDOG=y\nCONFIG_BT_LL_SOFTDEVICE=y\n"
        resources = {}
        for marker, transport in enumerate(("twowire", "h4"), 1):
            image = root / f"{transport}.route.hex"
            payload = ((0x20000100).to_bytes(4, "little") +
                       (0x00000009).to_bytes(4, "little") +
                       bytes([marker]))
            image.write_text(
                hex_record(0, 0, payload) + "\n" + hex_record(0, 1) + "\n",
                encoding="ascii",
            )
            config = root / f"{transport}.config"
            config.write_text(config_text, encoding="utf-8")
            resources[transport] = {"image": image, "config": config}
        manifest_path = root / "dtm.build-manifest.json"
        manifest_path.write_text(json.dumps({
            "source_revision": REVISION,
            "dtm_identity": identity,
            "board_revision": CAMPAIGN.diagnostics.LOCK["board"]["revision"],
            "ncs_revision": CAMPAIGN.diagnostics.LOCK["ncs"]["revision"],
            "zephyr_revision": CAMPAIGN.diagnostics.LOCK["zephyr"]["revision"],
            "results": [
                {
                    "route": "dtm_hci" if transport == "h4" else "dtm_twowire",
                    "status": "PASS", "runtime": "NOT_RUN",
                    "image_sha256": digest(resources[transport]["image"]),
                    "config_sha256": digest(resources[transport]["config"]),
                }
                for transport in ("twowire", "h4")
            ],
        }), encoding="utf-8")
        third_path = root / "third-idle-fixture.json"
        third_path.write_text('{"status":"PASS"}', encoding="utf-8")
        third_reference = {"path": third_path.name, "sha256": digest(third_path)}
        for transport in ("twowire", "h4"):
            fixture_path = root / f"{transport}.fixture.json"
            preflight_path = root / f"{transport}.preflight.json"
            result_path = root / f"{transport}.result.json"
            fixture_path.write_text(json.dumps({"transport": transport}), encoding="utf-8")
            preflight_path.write_text(json.dumps({"status": "PREPARED"}), encoding="utf-8")
            baseline = {"status": "PASS", "reset_observed": False}
            parsed_ranges = intel_hex_ranges(resources[transport]["image"])
            self.assertEqual(1, len(parsed_ranges))
            range_start, range_data = parsed_ranges[0]
            range_hash = hashlib.sha256(range_data).hexdigest()
            ranges = [{"start": range_start, "length": len(range_data),
                       "expected_sha256": range_hash}]
            readback_rows = [{**ranges[0], "observed_sha256": range_hash,
                              "status": "PASS"}]
            boards = [
                {"role": role, "probe_sha256": str(index) * 64,
                 "image_sha256": digest(resources[transport]["image"]),
                 "ranges": ranges, "readback": readback_rows}
                for index, role in enumerate(("tx", "rx"), 1)
            ]
            boards.append({"role": "third", "probe_sha256": "3" * 64})
            fixtures[transport] = {
                "third_guard_baseline": baseline,
                "firmware_identity": identity,
                "boards": boards,
                "third_idle": third_reference,
            }
            preflight_path.write_text(json.dumps({
                "status": "PREPARED",
                "program_receipt": {
                    "schema_version": 1,
                    "kind": "m33_dtm_same_process_program_readback",
                    "source_revision": REVISION,
                    "transport": transport,
                    "backend": "pyocd-sector-no-reset",
                    "roles": [
                        {
                            "role": board["role"],
                            "probe_sha256": board["probe_sha256"],
                            "image_sha256": board["image_sha256"],
                            "ranges": board["ranges"],
                            "readback": board["readback"],
                        }
                        for board in boards[:2]
                    ],
                },
            }), encoding="utf-8")
            cases = [{"tx_role": tx, "rx_role": 1 - tx, "phy": phy,
                      "channel": channel, "payload": "PRBS9-37",
                      "duration_ms": 500, "received": 100,
                      "observed_tx_ms": 500, "status": "PASS"}
                     for tx in (0, 1) for phy in (1, 2) for channel in (0, 19, 39)]
            result = {"test_id": "M33-DIAG-01", "status": "PASS",
                      "fixture_sha256": digest(fixture_path), "cases": cases,
                      "negative": [
                          {"role": 0, "range_length_busy": "PASS", "firmware_lease": "PASS"},
                          {"role": 1, "range_length_busy": "PASS", "firmware_lease": "PASS"}],
                      "cleanup": [{"role": 0, "stop": "PASS"},
                                  {"role": 1, "stop": "PASS"}],
                      "third_final": baseline, "third_audit_checks": 12,
                      "transcripts": self.transcripts(transport, identity, cases)}
            result_path.write_text(json.dumps(result), encoding="utf-8")
            hardware = []
            for index, role in enumerate(("tx", "rx"), 1):
                image = root / f"{transport}.{role}.image.hex"
                image.write_bytes(resources[transport]["image"].read_bytes())
                readback = root / f"{transport}.{role}.readback.json"
                readback.write_text(json.dumps({
                    "schema_version": 1,
                    "kind": "m33_exact_program_readback",
                    "status": "PASS",
                    "role": role,
                    "probe_sha256": str(index) * 64,
                    "image_sha256": digest(image),
                    "backend": "pyocd-live-target",
                    "halted": True,
                    "resumed": False,
                    "pre_state": "HALTED",
                    "post_state": "HALTED",
                    "restored": True,
                    "ranges": readback_rows,
                }), encoding="utf-8")
                build = root / f"{transport}.{role}.build-record.json"
                build.write_text(json.dumps({
                    "schema_version": 1,
                    "kind": "m33_dtm_phase_build_record",
                    "source_revision": REVISION,
                    "source_clean": True,
                    "board_revision": CAMPAIGN.diagnostics.LOCK["board"]["revision"],
                    "ncs_revision": CAMPAIGN.diagnostics.LOCK["ncs"]["revision"],
                    "zephyr_revision": CAMPAIGN.diagnostics.LOCK["zephyr"]["revision"],
                    "transport": transport,
                    "role": role,
                    "manifest": {"path": manifest_path.name,
                                 "sha256": digest(manifest_path)},
                    "config": {"path": resources[transport]["config"].name,
                               "sha256": digest(resources[transport]["config"])},
                    "fixture": {"path": fixture_path.name,
                                "sha256": digest(fixture_path)},
                    "preflight": {"path": preflight_path.name,
                                  "sha256": digest(preflight_path)},
                    "result": {"path": result_path.name,
                               "sha256": digest(result_path)},
                    "image_sha256": digest(image),
                }), encoding="utf-8")
                hardware.append({"role": role, "probe_sha256": str(index) * 64,
                                 "image": {"path": image.name, "sha256": digest(image)},
                                 "build_record": {"path": build.name,
                                                  "sha256": digest(build)},
                                 "readback": {"path": readback.name,
                                              "sha256": digest(readback)},
                                 "flash": {"mode": "pyocd-sector-no-reset",
                                           "programmed_bytes": len(range_data),
                                           "erase": "sector",
                                           "auto_unlock": False, "mass_erase": False,
                                           "automatic_recover": False}})
            typed = [{"transport": transport, **row} for row in cases]
            all_cases.extend(typed)
            transports.append({
                "transport": transport,
                "fixture": {"path": fixture_path.name, "sha256": digest(fixture_path)},
                "preflight": {"path": preflight_path.name, "sha256": digest(preflight_path)},
                "result": {"path": result_path.name, "sha256": digest(result_path)},
                "third_idle": third_reference,
                "hardware": hardware,
            })
            final_hardware = hardware
        statuses = {token: "PASS" for token in CAMPAIGN.SEMANTICS}
        value = {
            "schema": CAMPAIGN.SCHEMA, "status": "PASS",
            "source_revision": REVISION, "source_clean": True, "cycles": 24,
            "transports": transports, "cases": all_cases,
            "rf_boundary": CAMPAIGN.RF_BOUNDARY,
            "phase_hardware": [
                {"transport": row["transport"], "hardware": row["hardware"]}
                for row in transports
            ],
            "m33_dispatch_attestation": {
                "schema_version": 1, "kind": "m33_native_campaign_attestation",
                "campaign_id": "m33_diagnostics_dtm", "source_revision": REVISION,
                "source_clean": True, "semantic_status": statuses,
                "cycle_records": [{"cycle": cycle, "status": "PASS",
                                   "semantics": dict(statuses)} for cycle in range(1, 25)],
                "hardware": final_hardware,
            },
        }
        path = root / "campaign.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path, fixtures

    def test_dual_transport_twenty_four_case_denominator(self):
        """! @brief 2 transport×12 unique case와 양쪽 STOP을 승인합니다. """
        with tempfile.TemporaryDirectory(prefix="nu54-dtm-campaign-") as folder:
            path, fixtures = self.campaign(Path(folder))

            self.assertEqual(24, self.validate(path, fixtures)["cycles"])
            with mock.patch.object(CAMPAIGN, "load_phase_fixture",
                                   side_effect=lambda child, preflight, h4: fixtures[
                                       "h4" if h4 else "twowire"
                                   ]), \
                    mock.patch.object(CAMPAIGN.diagnostics, "inspect_hex",
                                      side_effect=lambda child, expected_hash,
                                      identity: {
                                          "sha256": expected_hash,
                                          "raw": b"".join(
                                              data for _, data in
                                              intel_hex_ranges(Path(child))
                                          ),
                                          "ranges": intel_hex_ranges(Path(child)),
                                      }):
                original = path.read_bytes()
                value = json.loads(original)
                result_path = Path(folder) / value["transports"][0]["result"]["path"]
                result = json.loads(result_path.read_text(encoding="utf-8"))
                result["transcripts"][0][0]["rx"] = "0000"
                result_path.write_text(json.dumps(result), encoding="utf-8")
                value["transports"][0]["result"]["sha256"] = digest(result_path)
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "transcript"):
                    CAMPAIGN.validate_campaign(path, REVISION)
                path.write_bytes(original)
                path_value = json.loads(original)
                result_path.write_text(json.dumps({**result,
                    "transcripts": self.transcripts(
                        "twowire", fixtures["twowire"]["firmware_identity"],
                        result["cases"]
                    )}), encoding="utf-8")
                path_value["transports"][0]["result"]["sha256"] = digest(result_path)
                path.write_text(json.dumps(path_value), encoding="utf-8")
                value = json.loads(path.read_text(encoding="utf-8"))
                value["cases"].pop()
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "24 typed case"):
                    CAMPAIGN.validate_campaign(path, REVISION)

    def test_provenance_receipt_and_boundary_tampering_is_rejected(self):
        """! @brief 외부 hash를 다시 계산해도 phase·lock·RF 경계 조작을 거부합니다. """

        def mutate_build(root: Path, value: dict, field: str, replacement) -> None:
            row = value["transports"][0]
            for index, hardware in enumerate(row["hardware"]):
                build_path = root / hardware["build_record"]["path"]
                build = json.loads(build_path.read_text(encoding="utf-8"))
                build[field] = replacement
                build_path.write_text(json.dumps(build), encoding="utf-8")
                reference = {"path": build_path.name, "sha256": digest(build_path)}
                hardware["build_record"] = reference
                value["phase_hardware"][0]["hardware"][index][
                    "build_record"
                ] = reference

        mutations = (
            ("RF", lambda root, value: value.__setitem__(
                "rf_boundary", {**CAMPAIGN.RF_BOUNDARY, "rf_metrology": "PASS"}
            )),
            ("hardware receipt", lambda root, value: value[
                "phase_hardware"
            ].pop()),
            ("build record", lambda root, value: mutate_build(
                root, value, "board_revision", "f" * 40
            )),
            ("third watcher", lambda root, value: value["transports"][1].__setitem__(
                "third_idle", value["transports"][1]["fixture"]
            )),
        )
        for expected, mutation in mutations:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory(
                    prefix="nu54-dtm-tamper-") as folder:
                root = Path(folder)
                path, fixtures = self.campaign(root)
                value = json.loads(path.read_text(encoding="utf-8"))
                mutation(root, value)
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, expected):
                    self.validate(path, fixtures)

        with tempfile.TemporaryDirectory(prefix="nu54-dtm-receipt-") as folder:
            root = Path(folder)
            path, fixtures = self.campaign(root)
            value = json.loads(path.read_text(encoding="utf-8"))
            row = value["transports"][0]
            preflight_path = root / row["preflight"]["path"]
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
            preflight.pop("program_receipt")
            preflight_path.write_text(json.dumps(preflight), encoding="utf-8")
            reference = {"path": preflight_path.name,
                         "sha256": digest(preflight_path)}
            row["preflight"] = reference
            for index, hardware in enumerate(row["hardware"]):
                build_path = root / hardware["build_record"]["path"]
                build = json.loads(build_path.read_text(encoding="utf-8"))
                build["preflight"] = reference
                build_path.write_text(json.dumps(build), encoding="utf-8")
                build_reference = {"path": build_path.name,
                                   "sha256": digest(build_path)}
                hardware["build_record"] = build_reference
                value["phase_hardware"][0]["hardware"][index][
                    "build_record"
                ] = build_reference
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "same-process program receipt"):
                self.validate(path, fixtures)

    def test_execution_rejects_reduced_or_unapproved_run(self):
        """! @brief 12회 단일 route나 승인 없는 실행을 aggregate PASS로 만들지 않습니다. """
        for cycles, execute in ((12, True), (24, False)):
            with self.subTest(cycles=cycles, execute=execute), self.assertRaisesRegex(
                    ValueError, "24-case"):
                CAMPAIGN.execute(argparse.Namespace(cycles=cycles, execute=execute))


if __name__ == "__main__":
    unittest.main(verbosity=2)
