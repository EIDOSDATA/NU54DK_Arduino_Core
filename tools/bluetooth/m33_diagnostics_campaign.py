#!/usr/bin/env python3
"""! @brief Two-wire/H4 DTM 12+12 물리 결과를 exact 24-case campaign으로 결합합니다. """
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import m33_diagnostics as diagnostics

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "nucode-m33-diagnostics-campaign-v1"
TRANSPORTS = (("twowire", False), ("h4", True))
SEMANTICS = ("dtm_tx_rx_role_swap", "packet_count", "negative", "cleanup")
RF_BOUNDARY = {
    "rf_metrology": "NOT_RUN",
    "controlled_noisy_rf": "NOT_RUN",
    "sdk_risk": {
        "id": "DRGN-29228",
        "status": "CONDITION_NOT_MET",
        "failure_cause": "NOT_ASSUMED",
    },
}


def digest(path: Path) -> str:
    """! @brief 파일 byte의 SHA-256을 반환합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_revision() -> str:
    """! @brief untracked를 포함한 clean current revision만 반환합니다. """
    revision = diagnostics.revision(ROOT)
    dirty = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain=v1",
         "--untracked-files=all"], capture_output=True, text=True, check=True
    ).stdout
    if dirty:
        raise ValueError("DTM campaign requires clean current source")
    return revision


class TranscriptReplay:
    """! @brief 저장 UART transaction을 DtmPort의 실제 parser에 순서대로 재입력합니다. """

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.index = 0
        self.pending = bytearray()

    def write(self, data: bytes) -> int:
        """! @brief 다음 raw TX와 exact command byte를 비교합니다. """
        if self.pending or self.index >= len(self.rows):
            raise ValueError("DTM transcript command ordering mismatch")
        row = self.rows[self.index]
        if (not isinstance(row, dict) or set(row) != {"tx", "rx"}
                or row.get("tx") != data.hex()):
            raise ValueError("DTM transcript command byte mismatch")
        try:
            self.pending.extend(bytes.fromhex(row["rx"]))
        except (TypeError, ValueError) as error:
            raise ValueError("DTM transcript response byte mismatch") from error
        self.index += 1
        return len(data)

    def read(self, size: int) -> bytes:
        """! @brief command response 또는 firmware lease auto-stop byte를 읽습니다. """
        if not self.pending:
            if self.index >= len(self.rows):
                return b""
            row = self.rows[self.index]
            if not isinstance(row, dict) or set(row) != {"rx_auto_stop"}:
                raise ValueError("DTM transcript unsolicited response mismatch")
            try:
                self.pending.extend(bytes.fromhex(row["rx_auto_stop"]))
            except (TypeError, ValueError) as error:
                raise ValueError("DTM transcript auto-stop byte mismatch") from error
            self.index += 1
        result = bytes(self.pending[:size])
        del self.pending[:size]
        return result

    def finish(self) -> None:
        """! @brief 소비하지 않은 raw transaction을 거부합니다. """
        if self.pending or self.index != len(self.rows):
            raise ValueError("DTM transcript denominator mismatch")


def replay_transcripts(result: dict, fixture: dict, transport: str) -> None:
    """! @brief raw UART byte로 identity·negative·12 case·STOP 분모를 재실행합니다. """
    rows = result.get("transcripts")
    if not isinstance(rows, list) or len(rows) != 2 or any(
            not isinstance(value, list) for value in rows):
        raise ValueError("DTM raw transcript role denominator mismatch")
    replays = [TranscriptReplay(value) for value in rows]
    ports = [diagnostics.DtmPort(replay, transport == "h4")
             for replay in replays]
    for port in ports:
        if port.identity() != fixture.get("firmware_identity"):
            raise ValueError("DTM transcript firmware identity mismatch")
        port.stop()
    for port in ports:
        port.negative()
        port.start(False, 19, 1)
        port.automatic_stop()
        port.stop()
    for case in result.get("cases", []):
        tx = case["tx_role"]
        rx = case["rx_role"]
        ports[rx].start(False, case["channel"], case["phy"])
        ports[tx].start(True, case["channel"], case["phy"])
        ports[tx].stop()
        if ports[rx].stop() != case["received"]:
            raise ValueError("DTM transcript packet count mismatch")
    for port in ports:
        port.stop()
    for replay in replays:
        replay.finish()


def validate_result(result: dict, fixture: dict, transport: str) -> list[dict]:
    """! @brief transport별 2×2×3 case와 negative/STOP/third guard를 검증합니다. """
    cases = result.get("cases")
    expected = {(tx, 1 - tx, phy, channel)
                for tx in (0, 1) for phy in (1, 2) for channel in (0, 19, 39)}
    observed = {(row.get("tx_role"), row.get("rx_role"), row.get("phy"),
                 row.get("channel")) for row in cases or []}
    if (result.get("test_id") != "M33-DIAG-01" or result.get("status") != "PASS"
            or result.get("fixture_sha256") is None or observed != expected
            or len(cases or []) != 12
            or any(row.get("status") != "PASS" or row.get("payload") != "PRBS9-37"
                   or not 50 <= row.get("received", -1) <= 2000 for row in cases)
            or result.get("negative") != [
                {"role": 0, "range_length_busy": "PASS", "firmware_lease": "PASS"},
                {"role": 1, "range_length_busy": "PASS", "firmware_lease": "PASS"},
            ]
            or result.get("cleanup") != [
                {"role": 0, "stop": "PASS"}, {"role": 1, "stop": "PASS"}
            ]
            or result.get("third_final") != fixture.get("third_guard_baseline")
            or not isinstance(result.get("third_audit_checks"), int)
            or result["third_audit_checks"] <= 0):
        raise ValueError(f"DTM {transport} raw denominator mismatch")
    replay_transcripts(result, fixture, transport)
    return [{"transport": transport, **row} for row in cases]


def load_phase_fixture(fixture_path: Path, preflight_path: Path,
                       h4: bool) -> dict:
    """! @brief 이름이 분리된 aggregate fixture와 preflight 실제 byte를 함께 검증합니다. """
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    diagnostics.validate_fixture(fixture)
    if (fixture.get("preparation_version") != 3
            or fixture.get("start_required") is not True
            or fixture.get("preflight_evidence_sha256") != digest(preflight_path)):
        raise ValueError("DTM aggregate fixture/preflight identity mismatch")
    report = json.loads(preflight_path.read_text(encoding="utf-8"))
    expected_safety = {
        "erase": "sector_only", "auto_unlock": False, "mass_erase": False,
        "recover": False, "resume_on_disconnect": False,
        "third_program": False, "third_reset": False, "third_resume": False,
        "radio_task_writes": False, "wdt_writes": False,
        "tx_rx_passive_shorts_mask": diagnostics.RADIO_PASSIVE_SHORTS,
        "soft_reset_is_full_chip_initialization": False,
    }
    if (report.get("status") != "PREPARED" or report.get("mode") != "execute"
            or report.get("boards") != fixture.get("boards")
            or report.get("firmware_identity") != fixture.get("firmware_identity")
            or report.get("transport") != fixture.get("transport")
            or fixture.get("transport") != ("h4" if h4 else "twowire")
            or report.get("safety") != expected_safety
            or report.get("third_final") != fixture.get("third_guard_baseline")
            or report.get("third_lifecycle", {}).get("origin") !=
            diagnostics.THIRD_IDLE_SCHEMA
            or report.get("third_lifecycle", {}).get(
                "reset_program_resume_after_stopped"
            ) is not False
            or report.get("third_idle") != fixture.get("third_idle")):
        raise ValueError("DTM aggregate prepared fixture content mismatch")
    idle = fixture["third_idle"]
    diagnostics.load_watcher_fixture(
        fixture_path.parent / idle["path"], idle["sha256"],
        fixture["boards"][2]["probe_sha256"]
    )
    return fixture


def bundle_transport(output: Path, transport: str, fixture_path: Path,
                     preflight_path: Path, result_path: Path, manifest_path: Path,
                     route_image: Path) -> tuple[dict, list[dict], list[dict]]:
    """! @brief prepare/run bytes와 phase별 image/readback/build record를 인접 sidecar로 보존합니다. """
    h4 = transport == "h4"
    fixture = load_phase_fixture(fixture_path, preflight_path, h4)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("fixture_sha256") != digest(fixture_path):
        raise ValueError("DTM result/fixture hash mismatch")
    cases = validate_result(result, fixture, transport)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    route = "dtm_hci" if h4 else "dtm_twowire"
    rows = [row for row in manifest.get("results", []) if row.get("route") == route]
    config_source = route_image.parent / ".config"
    if (manifest.get("source_revision") != diagnostics.revision(ROOT)
            or manifest.get("dtm_identity") != fixture.get("firmware_identity")
            or len(rows) != 1 or rows[0].get("status") != "PASS"
            or rows[0].get("runtime") != "NOT_RUN"
            or rows[0].get("image_sha256") != digest(route_image)
            or not config_source.is_file()
            or rows[0].get("config_sha256") != digest(config_source)):
        raise ValueError("DTM build manifest/fixture identity mismatch")
    config = output / f"{transport}.config"
    shutil.copyfile(config_source, config)
    hardware = []
    for role_index, role in enumerate(("tx", "rx")):
        board = fixture["boards"][role_index]
        image = output / f"{transport}.{role}.image.hex"
        shutil.copyfile(route_image, image)
        if digest(image) != board.get("image_sha256") or digest(image) != digest(route_image):
            raise ValueError("DTM prepared image byte mismatch")
        readback = output / f"{transport}.{role}.readback.json"
        readback.write_text(json.dumps({
            "schema_version": 1,
            "kind": "m33_exact_program_readback",
            "status": "PASS",
            "role": role,
            "probe_sha256": board["probe_sha256"],
            "image_sha256": digest(image),
            "backend": "pyocd-live-target",
            "halted": True,
            "resumed": False,
            "pre_state": "HALTED",
            "post_state": "HALTED",
            "restored": True,
            "ranges": board.get("readback"),
        }, sort_keys=True) + "\n", encoding="utf-8")
        build = output / f"{transport}.{role}.build-record.json"
        build.write_text(json.dumps({
            "schema_version": 1, "kind": "m33_dtm_phase_build_record",
            "source_revision": manifest["source_revision"], "source_clean": True,
            "board_revision": manifest["board_revision"],
            "ncs_revision": manifest["ncs_revision"],
            "zephyr_revision": manifest["zephyr_revision"],
            "transport": transport, "role": role,
            "manifest": {"path": manifest_path.name, "sha256": digest(manifest_path)},
            "config": {"path": config.name, "sha256": digest(config)},
            "fixture": {"path": fixture_path.name, "sha256": digest(fixture_path)},
            "preflight": {"path": preflight_path.name, "sha256": digest(preflight_path)},
            "result": {"path": result_path.name, "sha256": digest(result_path)},
            "image_sha256": digest(image),
        }, sort_keys=True), encoding="utf-8")
        programmed = sum(row.get("length", 0) for row in board.get("ranges", []))
        hardware.append({
            "role": role, "probe_sha256": board["probe_sha256"],
            "image": {"path": image.name, "sha256": digest(image)},
            "build_record": {"path": build.name, "sha256": digest(build)},
            "flash": {"mode": "pyocd-sector-no-reset", "programmed_bytes": programmed,
                      "erase": "sector", "auto_unlock": False, "mass_erase": False,
                      "automatic_recover": False},
            "readback": {"path": readback.name, "sha256": digest(readback)},
        })
    reference = {
        "transport": transport,
        "fixture": {"path": fixture_path.name, "sha256": digest(fixture_path)},
        "preflight": {"path": preflight_path.name, "sha256": digest(preflight_path)},
        "result": {"path": result_path.name, "sha256": digest(result_path)},
        "third_idle": fixture["third_idle"],
        "hardware": hardware,
    }
    return reference, cases, hardware


def adjacent(path: Path, reference: dict, label: str) -> Path:
    """! @brief aggregate와 인접한 content-addressed file만 반환합니다. """
    if (not isinstance(reference, dict) or set(reference) != {"path", "sha256"}
            or not isinstance(reference.get("path"), str)
            or Path(reference["path"]).name != reference["path"]):
        raise ValueError(f"DTM {label} reference mismatch")
    child = (path.parent / reference["path"]).resolve()
    if (child.parent != path.parent or not child.is_file()
            or digest(child) != reference.get("sha256")):
        raise ValueError(f"DTM {label} byte mismatch")
    return child


def validate_phase_hardware(path: Path, row: dict, fixture: dict,
                            revision: str) -> list[dict]:
    """! @brief transport phase의 image·build·program·readback을 fixture와 재결합합니다. """
    transport = row["transport"]
    declared = row.get("hardware")
    if (not isinstance(declared, list) or len(declared) != 2
            or [value.get("role") for value in declared] != ["tx", "rx"]):
        raise ValueError("DTM phase hardware denominator mismatch")
    manifest_path = None
    route_image_hash = None
    validated = []
    for index, hardware in enumerate(declared):
        board = fixture["boards"][index]
        image = adjacent(path, hardware.get("image"), "phase image")
        build_path = adjacent(path, hardware.get("build_record"),
                              "phase build record")
        readback_path = adjacent(path, hardware.get("readback"),
                                 "phase readback")
        build = json.loads(build_path.read_text(encoding="utf-8"))
        required = {
            "schema_version", "kind", "source_revision", "source_clean",
            "board_revision", "ncs_revision", "zephyr_revision", "transport",
            "role", "manifest", "config", "fixture", "preflight", "result",
            "image_sha256",
        }
        if (set(build) != required or build.get("schema_version") != 1
                or build.get("kind") != "m33_dtm_phase_build_record"
                or build.get("source_revision") != revision
                or build.get("source_clean") is not True
                or build.get("board_revision") != diagnostics.LOCK["board"]["revision"]
                or build.get("ncs_revision") != diagnostics.LOCK["ncs"]["revision"]
                or build.get("zephyr_revision") != diagnostics.LOCK["zephyr"]["revision"]
                or build.get("transport") != transport
                or build.get("role") != hardware["role"]
                or build.get("image_sha256") != digest(image)):
            raise ValueError("DTM phase build record mismatch")
        manifest = adjacent(path, build["manifest"], "build manifest")
        config = adjacent(path, build["config"], "resolved config")
        if manifest_path is None:
            manifest_path = manifest
        elif manifest_path != manifest:
            raise ValueError("DTM transport build manifest drift")
        for label in ("fixture", "preflight", "result"):
            if build[label] != row[label]:
                raise ValueError(f"DTM build/{label} binding mismatch")
        preflight_path = adjacent(path, build["preflight"], "program preflight")
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        expected_receipt = {
            "schema_version": 1,
            "kind": "m33_dtm_same_process_program_readback",
            "source_revision": revision,
            "transport": transport,
            "backend": "pyocd-sector-no-reset",
            "roles": [
                {
                    "role": fixture["boards"][role_index]["role"],
                    "probe_sha256": fixture["boards"][role_index]["probe_sha256"],
                    "image_sha256": fixture["boards"][role_index]["image_sha256"],
                    "ranges": fixture["boards"][role_index]["ranges"],
                    "readback": fixture["boards"][role_index]["readback"],
                }
                for role_index in range(2)
            ],
        }
        if preflight.get("program_receipt") != expected_receipt:
            raise ValueError("DTM same-process program receipt mismatch")
        manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
        route = "dtm_hci" if transport == "h4" else "dtm_twowire"
        route_rows = [value for value in manifest_value.get("results", [])
                      if isinstance(value, dict) and value.get("route") == route]
        config_text = config.read_text(encoding="utf-8")
        if (manifest_value.get("source_revision") != revision
                or manifest_value.get("board_revision") != diagnostics.LOCK["board"]["revision"]
                or manifest_value.get("ncs_revision") != diagnostics.LOCK["ncs"]["revision"]
                or manifest_value.get("zephyr_revision") != diagnostics.LOCK["zephyr"]["revision"]
                or manifest_value.get("dtm_identity") != fixture["firmware_identity"]
                or len(route_rows) != 1 or route_rows[0].get("status") != "PASS"
                or route_rows[0].get("runtime") != "NOT_RUN"
                or route_rows[0].get("image_sha256") != digest(image)
                or route_rows[0].get("config_sha256") != digest(config)
                or "CONFIG_WATCHDOG=y" not in config_text
                or "CONFIG_BT_LL_SOFTDEVICE=y" not in config_text
                or any(f"CONFIG_{token}=y" in config_text for token in
                       ("UART_CONSOLE", "PRINTK", "LOG", "BT_HCI_HOST"))):
            raise ValueError("DTM manifest/config route mismatch")
        inspected = diagnostics.inspect_hex(
            image, digest(image), fixture["firmware_identity"]
        )
        expected_ranges = diagnostics.image_plan(inspected)["ranges"]
        readback = json.loads(readback_path.read_text(encoding="utf-8"))
        observed_ranges = board.get("readback")
        expected_readback = [
            {**expected, "observed_sha256": expected["expected_sha256"],
             "status": "PASS"}
            for expected in expected_ranges
        ]
        flash = hardware.get("flash", {})
        if (hardware.get("probe_sha256") != board.get("probe_sha256")
                or board.get("image_sha256") != digest(image)
                or board.get("ranges") != expected_ranges
                or observed_ranges != expected_readback
                or readback != {
                    "schema_version": 1,
                    "kind": "m33_exact_program_readback",
                    "status": "PASS",
                    "role": hardware["role"],
                    "probe_sha256": hardware["probe_sha256"],
                    "image_sha256": digest(image),
                    "backend": "pyocd-live-target",
                    "halted": True,
                    "resumed": False,
                    "pre_state": "HALTED",
                    "post_state": "HALTED",
                    "restored": True,
                    "ranges": expected_readback,
                }
                or not str(flash.get("mode", "")).startswith("pyocd-sector")
                or flash.get("programmed_bytes") != sum(
                    value["length"] for value in expected_ranges
                )
                or flash.get("erase") != "sector"
                or flash.get("auto_unlock") is not False
                or flash.get("mass_erase") is not False
                or flash.get("automatic_recover") is not False):
            raise ValueError("DTM phase program/readback mismatch")
        route_image_hash = digest(image)
        validated.append(hardware)
    if route_image_hash is None:
        raise ValueError("DTM phase image missing")
    return validated


def validate_campaign(path: Path, expected_revision: str | None = None) -> dict:
    """! @brief aggregate가 참조하는 dual fixture와 24 typed case를 다시 검증합니다. """
    path = path.resolve()
    value = json.loads(path.read_text(encoding="utf-8"))
    revision = expected_revision or diagnostics.revision(ROOT)
    if (value.get("schema") != SCHEMA or value.get("status") != "PASS"
            or value.get("source_revision") != revision
            or value.get("source_clean") is not True or value.get("cycles") != 24):
        raise ValueError("DTM campaign identity mismatch")
    if value.get("rf_boundary") != RF_BOUNDARY:
        raise ValueError("DTM RF boundary mismatch")
    transports = value.get("transports")
    if not isinstance(transports, list) or [row.get("transport") for row in transports] != [
            "twowire", "h4"]:
        raise ValueError("DTM dual transport denominator mismatch")
    cases = []
    final_hardware = None
    phase_hardware = []
    probe_mapping = None
    route_images = set()
    third_identity = None
    for row, (_, h4) in zip(transports, TRANSPORTS, strict=True):
        for label in ("fixture", "preflight", "result"):
            adjacent(path, row.get(label, {}), label)
        fixture_path = path.parent / row["fixture"]["path"]
        preflight_path = path.parent / row["preflight"]["path"]
        fixture = load_phase_fixture(fixture_path, preflight_path, h4)
        result = json.loads((path.parent / row["result"]["path"]).read_text(encoding="utf-8"))
        if result.get("fixture_sha256") != digest(fixture_path):
            raise ValueError("DTM result/fixture hash mismatch")
        cases.extend(validate_result(result, fixture, row["transport"]))
        declared = validate_phase_hardware(path, row, fixture, revision)
        current_mapping = {
            value["role"]: value["probe_sha256"] for value in declared
        }
        if probe_mapping is None:
            probe_mapping = current_mapping
        elif probe_mapping != current_mapping:
            raise ValueError("DTM transport probe mapping drift")
        route_images.add(declared[0]["image"]["sha256"])
        if row.get("third_idle") != fixture.get("third_idle"):
            raise ValueError("DTM third watcher fixture mismatch")
        adjacent(path, row["third_idle"], "third watcher fixture")
        current_third = {
            "probe_sha256": fixture["boards"][2]["probe_sha256"],
            "third_idle": row.get("third_idle"),
            "baseline": fixture.get("third_guard_baseline"),
        }
        if third_identity is None:
            third_identity = current_third
        elif third_identity != current_third:
            raise ValueError("DTM third watcher transport drift")
        phase_hardware.append({"transport": row["transport"],
                               "hardware": declared})
        final_hardware = declared
    expected_keys = {(transport, tx, 1 - tx, phy, channel)
                     for transport in ("twowire", "h4") for tx in (0, 1)
                     for phy in (1, 2) for channel in (0, 19, 39)}
    if (len(cases) != 24 or
            {(row["transport"], row["tx_role"], row["rx_role"], row["phy"], row["channel"])
             for row in cases} != expected_keys or value.get("cases") != cases):
        raise ValueError("DTM 24 typed case denominator mismatch")
    if value.get("phase_hardware") != phase_hardware:
        raise ValueError("DTM dual transport hardware receipt mismatch")
    if len(route_images) != 2:
        raise ValueError("DTM transport image phases are not distinct")
    attestation = value.get("m33_dispatch_attestation", {})
    statuses = {token: "PASS" for token in SEMANTICS}
    expected_records = [{"cycle": index, "status": "PASS", "semantics": dict(statuses)}
                        for index in range(1, 25)]
    if (attestation.get("campaign_id") != "m33_diagnostics_dtm"
            or attestation.get("source_revision") != revision
            or attestation.get("source_clean") is not True
            or attestation.get("semantic_status") != statuses
            or attestation.get("cycle_records") != expected_records
            or attestation.get("hardware") != final_hardware):
        raise ValueError("DTM campaign attestation mismatch")
    return value


def execute(args: argparse.Namespace) -> dict:
    """! @brief fresh current watcher로 prepare/run을 두 transport에 순차 적용합니다. """
    if not args.execute or args.cycles != 24:
        raise ValueError("DTM campaign requires explicit 24-case execution")
    revision = clean_revision()
    output = args.output.resolve()
    if output.exists() or output.suffix.lower() != ".json":
        raise ValueError("new DTM campaign JSON output required")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.build_manifest.read_text(encoding="utf-8"))
    if manifest.get("source_revision") != revision:
        raise ValueError("DTM build manifest is not current revision")
    watcher_hash = digest(args.third_idle_fixture)
    transport_records = []
    all_cases = []
    final_hardware = None
    for transport, h4 in TRANSPORTS:
        route_image = args.h4_hex if h4 else args.twowire_hex
        prepare_dir = output.parent / f"{output.stem}.{transport}.prepare"
        run_dir = output.parent / f"{output.stem}.{transport}.run"
        diagnostics.prepare_pair(argparse.Namespace(
            sdk=args.sdk_root, output=prepare_dir,
            firmware_identity=manifest["dtm_identity"], transport=transport,
            tx_probe_sha256=args.tx_probe_sha256, tx_port=args.tx_port,
            tx_hex=route_image, tx_hex_sha256=digest(route_image),
            rx_probe_sha256=args.rx_probe_sha256, rx_port=args.rx_port,
            rx_hex=route_image, rx_hex_sha256=digest(route_image),
            third_probe_sha256=args.third_probe_sha256,
            execute=True, authorize_sector_program=True,
            authorize_tx_rx_algorithm_reset=True, authorize_third_halt_audit=True,
            third_idle_fixture=args.third_idle_fixture,
            third_idle_fixture_sha256=watcher_hash,
        ))
        diagnostics.run_pair(argparse.Namespace(
            fixture=prepare_dir / "fixture.json", output=run_dir,
            h4=h4, authorize_start_tx_rx=True,
        ))
        fixture_copy = output.parent / f"{transport}.fixture.json"
        preflight_copy = output.parent / f"{transport}.preflight.json"
        result_copy = output.parent / f"{transport}.result.json"
        manifest_copy = output.parent / f"{output.stem}.build-manifest.json"
        if not manifest_copy.exists():
            shutil.copyfile(args.build_manifest, manifest_copy)
        shutil.copyfile(prepare_dir / "fixture.json", fixture_copy)
        shutil.copyfile(prepare_dir / "preflight.json", preflight_copy)
        shutil.copyfile(run_dir / "result.json", result_copy)
        # fixture의 상대 sidecar를 aggregate 인접 경계로 복사합니다.
        fixture = json.loads(fixture_copy.read_text(encoding="utf-8"))
        third_name = fixture["third_idle"]["path"]
        third_value = json.loads((prepare_dir / third_name).read_text(encoding="utf-8"))
        third_names = [third_name]
        third_names.extend(
            descriptor["path"] for descriptor in third_value.get("files", {}).values()
        )
        for name in third_names:
            source = prepare_dir / name
            target = output.parent / name
            if not target.exists():
                shutil.copyfile(source, target)
            elif digest(target) != digest(source):
                raise ValueError("DTM watcher sidecar differs between transports")
        fixture["preflight_evidence_sha256"] = digest(preflight_copy)
        fixture_copy.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
        result = json.loads(result_copy.read_text(encoding="utf-8"))
        result["fixture_sha256"] = digest(fixture_copy)
        result_copy.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        record, cases, hardware = bundle_transport(
            output.parent, transport, fixture_copy, preflight_copy, result_copy,
            manifest_copy, route_image
        )
        transport_records.append(record)
        all_cases.extend(cases)
        final_hardware = hardware
    statuses = {token: "PASS" for token in SEMANTICS}
    result = {
        "schema": SCHEMA, "status": "PASS", "source_revision": revision,
        "source_clean": True, "cycles": 24, "transports": transport_records,
        "cases": all_cases, "rf_boundary": RF_BOUNDARY,
        "phase_hardware": [
            {"transport": row["transport"], "hardware": row["hardware"]}
            for row in transport_records
        ],
        "m33_dispatch_attestation": {
            "schema_version": 1, "kind": "m33_native_campaign_attestation",
            "campaign_id": "m33_diagnostics_dtm", "source_revision": revision,
            "source_clean": True, "semantic_status": statuses,
            "cycle_records": [{"cycle": index, "status": "PASS",
                               "semantics": dict(statuses)} for index in range(1, 25)],
            "hardware": final_hardware,
        },
    }
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if clean_revision() != revision:
        raise ValueError("DTM campaign source changed during execution")
    return validate_campaign(output, revision)


def main() -> int:
    """! @brief 자동 erase/recover 없이 명시 승인된 dual-transport campaign을 실행합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-manifest", type=Path, required=True)
    parser.add_argument("--twowire-hex", type=Path, required=True)
    parser.add_argument("--h4-hex", type=Path, required=True)
    parser.add_argument("--third-idle-fixture", type=Path, required=True)
    parser.add_argument("--tx-probe-sha256", required=True)
    parser.add_argument("--tx-port", required=True)
    parser.add_argument("--rx-probe-sha256", required=True)
    parser.add_argument("--rx-port", required=True)
    parser.add_argument("--third-probe-sha256", required=True)
    parser.add_argument("--cycles", type=int, default=24)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except (KeyError, OSError, RuntimeError, subprocess.SubprocessError,
            TypeError, ValueError) as error:
        print("M33 DTM campaign FAIL: " + str(error))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
