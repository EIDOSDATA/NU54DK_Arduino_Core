#!/usr/bin/env python3
"""! @brief M33 flat/build evidence의 raw 재생과 artifact 변조 거부를 검사합니다. """

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
sys.path.insert(0, str(HIL))


def load(name: str, path: Path):
    """! @brief 경로가 고정된 script를 독립 module로 읽습니다. """

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BAP = load("m33_flat_bap", HIL / "m31_audio_bap_duplex_cycle_run.py")
CS = load("m33_flat_cs", HIL / "m31_cs_ras_pair_run.py")
TEMPLATE = load(
    "m33_template_build_evidence",
    ROOT / "libraries/NUCODE_BLE_Companion/tools/m33_template_build.py",
)
DIAGNOSTICS = load(
    "m33_diagnostics_build_evidence",
    ROOT / "tools/bluetooth/m33_diagnostics.py",
)


class FlatEvidenceTests(unittest.TestCase):
    """! @brief BAP/CS typed record가 raw transcript와 정확히 결합되는지 검사합니다. """

    def bap_record(self) -> dict:
        """! @brief server 누적 counter를 포함한 20회 BAP evidence를 만듭니다. """

        record = {"client_lines": [], "server_lines": [], "cycle_records": []}
        for cycle in range(1, 21):
            client_start = len(record["client_lines"])
            server_start = len(record["server_lines"])
            record["client_lines"].extend([
                "LE Audio duplex sent frames=100",
                "LE Audio duplex received=100 energy=5 dropped=0",
                "LE Audio duplex client streaming",
                "LE Audio stream stopped",
                "LE Audio peer disconnected",
            ])
            record["server_lines"].extend([
                f"LE Audio duplex sent={cycle * 100}",
                f"LE Audio duplex received={cycle * 100} energy=7 dropped=0",
                "LE Audio duplex peer disconnected",
            ])
            record["cycle_records"].append({
                "cycle": cycle,
                "status": "PASS",
                "duration_seconds": 1.0,
                "client": {
                    "sent_frames": 100,
                    "received_frames": 100,
                    "energy": 5,
                    "dropped_frames": 0,
                },
                "server": {
                    "sent_frames": 100,
                    "received_frames": 100,
                    "energy": 7,
                    "dropped_frames": 0,
                },
                "events": {
                    "client": ["streaming", "stopped", "disconnected"],
                    "server": ["disconnected"],
                },
                "cleanup": "PASS",
                "client_range": [client_start, len(record["client_lines"])],
                "server_range": [server_start, len(record["server_lines"])],
            })
        return record

    def test_bap_raw_ranges_counters_and_cumulative_baseline(self):
        """! @brief 20회 raw range와 누적 server counter 조작을 fail-closed 처리합니다. """

        record = self.bap_record()
        BAP.validate_cycle_records(record, 20)
        changed = copy.deepcopy(record)
        changed["server_lines"][3] = "LE Audio duplex sent=250"
        with self.assertRaisesRegex(ValueError, "typed cycle"):
            BAP.validate_cycle_records(changed, 20)
        changed = copy.deepcopy(record)
        changed["cycle_records"][1]["client_range"][0] -= 1
        with self.assertRaisesRegex(ValueError, "range"):
            BAP.validate_cycle_records(changed, 20)

    def cs_record(self) -> dict:
        """! @brief 100 procedure·20 restart·20 reconnect·quiesce evidence를 만듭니다. """

        record = {
            "initiator_lines": [],
            "reflector_lines": [],
            "procedure_records": [],
            "stop_restart_records": [],
            "disconnect_reconnect_records": [],
            "cleanup_record": None,
            "cleanup": {
                "quiesce": "PASS",
                "initiator_acl": "PASS",
                "reflector_acl": "PASS",
                "zero_link": "PASS",
                "stability_window": "PASS",
                "initiator_serial_close": "PASS",
                "reflector_serial_close": "PASS",
            },
        }
        for procedure in range(1, 101):
            line = (f"CS_RAW counter={procedure} local=4 peer=4 rtt=3 tone=1 "
                    "valid_rtt=2 distance_m=1.250")
            line_index = len(record["initiator_lines"])
            record["initiator_lines"].append(line)
            record["procedure_records"].append({
                "procedure": procedure,
                "counter": procedure,
                "local_steps": 4,
                "peer_steps": 4,
                "rtt_steps": 3,
                "tone_steps": 1,
                "valid_rtt_samples": 2,
                "distance_m": 1.25,
                "initiator_line": line_index,
                "status": "PASS",
            })
        for cycle in range(1, 21):
            initiator_start = len(record["initiator_lines"])
            reflector_start = len(record["reflector_lines"])
            record["initiator_lines"].extend([
                "CS procedures stop requested",
                "CS procedures restart requested",
                "CS_RAW counter=1000 local=4 peer=4 rtt=3 tone=1 "
                "valid_rtt=2 distance_m=1.250",
            ])
            record["reflector_lines"].extend([
                "CS procedures disabled",
                "CS procedures enabled",
            ])
            record["stop_restart_records"].append(CS._transition_record(
                record, cycle, "stop_restart", initiator_start, reflector_start
            ))
        for cycle in range(1, 21):
            initiator_start = len(record["initiator_lines"])
            reflector_start = len(record["reflector_lines"])
            record["initiator_lines"].extend([
                "CS disconnect requested",
                "CS initiator disconnected",
                "CS initiator connected; securing",
                "CS_RAW counter=2000 local=4 peer=4 rtt=3 tone=1 "
                "valid_rtt=2 distance_m=1.250",
            ])
            record["reflector_lines"].extend([
                "CS reflector disconnected",
                "CS reflector connected",
            ])
            record["disconnect_reconnect_records"].append(CS._transition_record(
                record, cycle, "disconnect_reconnect",
                initiator_start, reflector_start,
            ))
        initiator_start = len(record["initiator_lines"])
        reflector_start = len(record["reflector_lines"])
        record["initiator_lines"].extend([
            "CS quiesce requested role=initiator",
            "CS initiator disconnected",
            "CS_QUIESCED role=initiator active_acl=0 pending=0 scan=0 cs=0",
        ])
        record["reflector_lines"].extend([
            "CS quiesce requested role=reflector",
            "CS reflector disconnected",
            "CS_QUIESCED role=reflector active_acl=0 pending=0 advertising=0 cs=0",
        ])
        record["cleanup_record"] = CS._transition_record(
            record, 0, "cleanup", initiator_start, reflector_start
        )
        return record

    def test_cs_raw_procedure_transitions_and_quiesce(self):
        """! @brief raw 100회와 stable zero-link quiesce를 재생하고 조작을 거부합니다. """

        record = self.cs_record()
        CS.validate_raw_evidence(record, 100, 20)
        changed = copy.deepcopy(record)
        changed["initiator_lines"][0] = changed["initiator_lines"][0].replace(
            "distance_m=1.250", "distance_m=9.250"
        )
        with self.assertRaisesRegex(ValueError, "typed/raw"):
            CS.validate_raw_evidence(changed, 100, 20)
        changed = copy.deepcopy(record)
        changed["cleanup"]["stability_window"] = "NOT_RUN"
        with self.assertRaisesRegex(ValueError, "cleanup"):
            CS.validate_raw_evidence(changed, 100, 20)

    def test_cs_sources_expose_finite_zero_link_quiesce(self):
        """! @brief P2와 공개 pair 모두 재연결 차단·zero-link ACK를 구현해야 합니다. """

        sources = (
            ROOT / "tests/arduino-cli/p2_cs_initiator/p2_cs_initiator.ino",
            ROOT / "tests/arduino-cli/p2_cs_reflector/p2_cs_reflector.ino",
            ROOT / "libraries/NUCODE_BLE_ChannelSounding/examples/"
                   "RasInitiator/RasInitiator.ino",
            ROOT / "libraries/NUCODE_BLE_ChannelSounding/examples/"
                   "RasReflector/RasReflector.ino",
        )
        for path in sources:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertIn("requestQuiesce()", text)
                self.assertIn("pollQuiesce()", text)
                self.assertIn("active_acl=0 pending=0", text)
                self.assertIn("command == 'q'", text)

    def test_partial_serial_cleanup_records_real_commands_and_close(self):
        """! @brief 두 번째 port open 전 실패해도 첫 port STOP/quiesce와 close를 남깁니다. """

        class Port:
            """! @brief cleanup command와 close 호출을 기록하는 최소 serial입니다. """

            def __init__(self):
                self.writes = []
                self.closed = False

            def write(self, value):
                self.writes.append(value)

            def flush(self):
                return None

            def close(self):
                self.closed = True

        bap_port = Port()
        bap_record = {"cleanup": {
            "client": {"stop": "NOT_RUN", "acl": "NOT_RUN",
                       "serial_close": "NOT_RUN"},
        }}
        BAP._emergency_client_stop(bap_port, bap_record)
        BAP._close_serial(bap_port, bap_record, "client")
        self.assertEqual(bap_port.writes, [b"s"])
        self.assertTrue(bap_port.closed)
        self.assertEqual(
            bap_record["cleanup"]["client"]["serial_close"], "PASS"
        )

        cs_port = Port()
        cs_record = {"cleanup": {
            "quiesce": "NOT_RUN",
            "initiator_serial_close": "NOT_RUN",
        }}
        CS.emergency_quiesce(cs_port, cs_record)
        CS.close_serial(cs_port, cs_record, "initiator")
        self.assertEqual(cs_port.writes, [b"q"])
        self.assertTrue(cs_port.closed)
        self.assertEqual(
            cs_record["cleanup"]["initiator_serial_close"], "PASS"
        )


class BuildEvidenceTests(unittest.TestCase):
    """! @brief 외부 retained artifact와 진단 exact manifest 변조를 검사합니다. """

    def test_template_retained_artifact_bytes_are_required(self):
        """! @brief artifact hash 문자열만 있고 실제 byte가 없거나 변조되면 거부합니다. """

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            artifact = output / "enocean.artifact.deadbeef0000.zephyr.hex"
            artifact.write_bytes(b":00000001FF\n")
            checksum = TEMPLATE.digest(artifact)
            row = {
                "artifacts": {"build/source/zephyr/zephyr.hex": checksum},
                "artifact_files": {
                    "build/source/zephyr/zephyr.hex": {
                        "path": artifact.name,
                        "sha256": checksum,
                        "size": artifact.stat().st_size,
                        "confidentiality": "external-build-evidence",
                    },
                },
            }
            TEMPLATE.validate_retained_artifacts(row, output)
            artifact.write_bytes(b"changed")
            with self.assertRaisesRegex(TEMPLATE.TemplateBuildFailure, "byte"):
                TEMPLATE.validate_retained_artifacts(row, output)

    def test_template_manifest_binds_exact_source_argv_config_and_elf(self):
        """! @brief template manifest의 SDK source·argv·config·ELF byte를 재검증합니다. """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sdk = root / "sdk"
            toolchain = root / "toolchain"
            build = root / "enocean"
            upstream = sdk / TEMPLATE.SOURCE_PATHS["enocean"]
            upstream.mkdir(parents=True)
            (upstream / "main.c").write_text("int main(void) { return 0; }\n",
                                              encoding="utf-8")
            generated = build / "source"
            generated.mkdir(parents=True)
            (generated / "main.c").write_text("int main(void) { return 0; }\n",
                                               encoding="utf-8")
            zephyr = build / "build/source/zephyr"
            zephyr.mkdir(parents=True)
            elf = zephyr / "zephyr.elf"
            image = zephyr / "zephyr.hex"
            config = zephyr / ".config"
            elf.write_bytes(b"ELF-ENOCEAN")
            image.write_text(":00000001FF\n", encoding="ascii")
            config.write_text("CONFIG_BT=y\n", encoding="utf-8")
            log = build / "build.log"
            log.write_text("build passed\n", encoding="utf-8")
            lock = json.loads(
                (ROOT / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8")
            )
            manifest = {
                "schema_version": 1,
                "kind": "enocean",
                "ncs_revision": lock["ncs"]["revision"],
                "zephyr_revision": lock["zephyr"]["revision"],
                "board_revision": lock["board"]["revision"],
                "board": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
                "source_path": TEMPLATE.SOURCE_PATHS["enocean"],
                "upstream_files": TEMPLATE.source_manifest(upstream),
                "command": TEMPLATE.expected_build_command(
                    "enocean", build, toolchain, ROOT
                ),
                "automatic_flash": False,
                "external_interoperability": "NOT_RUN",
                "credential_mode": "none",
                "generated_source_sha256": TEMPLATE.source_manifest(generated),
                "known_boundaries": [],
                "build_exit_code": 0,
                "artifacts": {
                    "build/source/zephyr/zephyr.elf": TEMPLATE.digest(elf),
                    "build/source/zephyr/zephyr.hex": TEMPLATE.digest(image),
                },
            }
            manifest_path = build / "template-manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            row = TEMPLATE._validate_result(
                "enocean", build, manifest, (), sdk, toolchain, ROOT, lock
            )
            self.assertIn("build/source/zephyr/.config", row["artifacts"])
            self.assertEqual(
                row["command_sha256"],
                hashlib.sha256(json.dumps(
                    manifest["command"], separators=(",", ":")
                ).encode("utf-8")).hexdigest(),
            )
            changed = copy.deepcopy(manifest)
            changed["command"].append("--flash")
            with self.assertRaisesRegex(TEMPLATE.TemplateBuildFailure, "command"):
                TEMPLATE._validate_result(
                    "enocean", build, changed, (), sdk, toolchain, ROOT, lock
                )

    def diagnostic_manifest(self, output: Path, sdk: Path,
                            toolchain: Path) -> dict:
        """! @brief controller/scan-request actual byte를 가진 최소 manifest를 만듭니다. """

        rows = []
        for route in ("controller", "scan_request"):
            directory = output / route / "zephyr"
            directory.mkdir(parents=True)
            image = directory / "zephyr.hex"
            image.write_text(":00000001FF\n", encoding="ascii")
            config = directory / ".config"
            required = ["CONFIG_WATCHDOG=y", "CONFIG_BT_LL_SOFTDEVICE=y"]
            if route == "controller":
                required.append("CONFIG_BT_HCI_RAW=y")
            else:
                required.extend(("CONFIG_BT_HCI_HOST=y", "CONFIG_BT_EXT_ADV=y",
                                 "CONFIG_BT_BROADCASTER=y"))
            config.write_text("\n".join(required) + "\n", encoding="utf-8")
            elf = directory / "zephyr.elf"
            elf.write_bytes(b"ELF" + route.encode("ascii"))
            log = output / f"{route}.log"
            log.write_text("build passed\n", encoding="utf-8")
            nm = output / f"{route}.nm.log"
            nm.write_text("00000000 T nucode_upstream_main\n", encoding="utf-8")
            command = ["build", route]
            rows.append({
                "route": route,
                "status": "PASS",
                "exit_code": 0,
                "dtm_identity": None,
                "log_sha256": DIAGNOSTICS.sha256(log),
                "image_sha256": DIAGNOSTICS.sha256(image),
                "config_sha256": DIAGNOSTICS.sha256(config),
                "elf_sha256": DIAGNOSTICS.sha256(elf),
                "nm": {"path": nm.name, "sha256": DIAGNOSTICS.sha256(nm),
                       "exit_code": 0},
                "command": command,
                "command_sha256": hashlib.sha256(json.dumps(
                    command, separators=(",", ":")
                ).encode("utf-8")).hexdigest(),
                "source_files": {f"source/{route}.c": route * 32},
                "build_root_mode": "fresh",
                "runtime": "NOT_RUN",
            })
        return {
            "source_revision": "a" * 40,
            "source_clean": True,
            "dtm_identity": "b" * 104,
            "board_revision": DIAGNOSTICS.LOCK["board"]["revision"],
            "ncs_revision": DIAGNOSTICS.LOCK["ncs"]["revision"],
            "zephyr_revision": DIAGNOSTICS.LOCK["zephyr"]["revision"],
            "toolchain_bundle_id": DIAGNOSTICS.LOCK["windows_toolchain"]["bundle_id"],
            "sdk_root": str(sdk.resolve()),
            "toolchain_root": str(toolchain.resolve()),
            "results": rows,
        }

    def test_diagnostics_manifest_binds_argv_sources_elf_and_nm(self):
        """! @brief exact argv/source/config/ELF/nm와 root drift를 모두 거부합니다. """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output"
            sdk = root / "sdk"
            toolchain = root / "toolchain"
            output.mkdir()
            sdk.mkdir()
            toolchain.mkdir()
            manifest = self.diagnostic_manifest(output, sdk, toolchain)

            def plan(route, _sdk, _toolchain, _output):
                return ["build", route]

            def sources(route, _sdk):
                return {f"source/{route}.c": route * 32}

            with mock.patch.object(DIAGNOSTICS, "build_plan", side_effect=plan), \
                    mock.patch.object(DIAGNOSTICS, "route_source_manifest",
                                      side_effect=sources), \
                    mock.patch.object(DIAGNOSTICS, "validate_locked_sources",
                                      return_value={
                                          "core": "a" * 40,
                                          "ncs": DIAGNOSTICS.LOCK["ncs"]["revision"],
                                          "zephyr": DIAGNOSTICS.LOCK["zephyr"]["revision"],
                                          "board": DIAGNOSTICS.LOCK["board"]["revision"],
                                      }), \
                    mock.patch.object(DIAGNOSTICS, "source_identity",
                                      return_value="b" * 104), \
                    mock.patch.object(DIAGNOSTICS, "inspect_hex"):
                DIAGNOSTICS.validate_release_build_manifest(
                    manifest, output, sdk, toolchain
                )
                changed = copy.deepcopy(manifest)
                changed["results"][0]["command"] = ["build", "wrong"]
                with self.assertRaisesRegex(ValueError, "provenance"):
                    DIAGNOSTICS.validate_release_build_manifest(
                        changed, output, sdk, toolchain
                    )
                changed = copy.deepcopy(manifest)
                changed["toolchain_root"] = str(root / "other")
                with self.assertRaisesRegex(ValueError, "identity"):
                    DIAGNOSTICS.validate_release_build_manifest(
                        changed, output, sdk, toolchain
                    )
                (output / "controller.nm.log").write_text(
                    "symbol missing\n", encoding="utf-8"
                )
                with self.assertRaisesRegex(ValueError, "nm provenance"):
                    DIAGNOSTICS.validate_release_build_manifest(
                        manifest, output, sdk, toolchain
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
