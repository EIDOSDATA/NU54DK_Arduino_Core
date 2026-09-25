"""! @brief M31 기능·역할·검증 분모의 미실행 계약을 생성합니다. """

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


CORE = Path(__file__).resolve().parents[2]
LOCK = json.loads((CORE / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
PARITY = json.loads((CORE / "variants/nu54dk/ncs-v3.4.0-bluetooth-sample-parity.json").read_text(
    encoding="utf-8"
))
PARITY_ROWS = sum(PARITY["counts"].values())
WORK = (
    "capability_inventory_contract", "raw_iso", "full_le_audio",
    "direction_finding", "channel_sounding", "integration_regression",
    "three_board_hil_examples", "closure_handoff",
)
AUDIO_GROUPS = (
    ("W03-01", "LC3 합성 PCM encode/decode", ("codec",), 1),
    ("W03-02", "BAP unicast PACS/ASCS", ("client", "server"), 2),
    ("W03-03", "BAP broadcast", ("source", "sink"), 2),
    ("W03-04", "BASS", ("source", "scan_delegator", "assistant"), 3),
    ("W03-05", "CAP", ("initiator", "acceptor", "commander"), 3),
    ("W03-06", "CSIP", ("coordinator", "member_a", "member_b"), 3),
    ("W03-07", "PBP public broadcast", ("source", "sink"), 2),
    ("W03-08", "VCP/VOCS/AICS/MICP", ("controller", "renderer", "microphone"), 2),
    ("W03-09", "MCP/MCS/CCP/TBS", ("controller", "server"), 2),
    ("W03-10", "TMAP/GMAP 역할", ("central", "peripheral", "broadcast"), 3),
    ("W03-11", "HAP/HAS", ("hearing_client", "hearing_server"), 2),
)
EXAMPLE_ROLES = (
    "raw_iso_central", "raw_iso_peripheral", "raw_iso_broadcaster",
    "raw_iso_receiver", "iso_combined_source", "iso_combined_peer",
    "iso_combined_receiver",
    "iso_time_sync_sender", "iso_time_sync_receiver",
    *(f"{identifier}:{role}" for identifier, _title, roles, _boards in AUDIO_GROUPS
      for role in roles),
    "cte_beacon", "cte_peripheral", "raw_iq_receiver_candidate",
    "external_angle_control", "cs_initiator", "cs_reflector",
    "cs_result", "cs_multipeer",
)


def case(identifier: str, owner: str, roles: tuple[str, ...], boards: int,
         timeout: int, iterations: int, denominator: int, metric: str,
         acceptance: dict, negative: tuple[str, ...] = ()) -> dict:
    """! @brief case별 수치·정책·실행 증거 상태를 독립적으로 고정합니다. """
    return {
        "id": identifier,
        "owner_work_id": owner,
        "roles": list(roles),
        "minimum_boards": boards,
        "timeout_seconds": timeout,
        "iterations": iterations,
        "denominator": denominator,
        "metric": metric,
        "acceptance": acceptance,
        "negative_classes": list(negative),
        "recovery_timeout_seconds": 30,
        "maximum_diagnostic_retests": 1,
        "verification_owner": "developer",
        "verification_stage": "development",
        "development_blocker": True,
        "release_blocker": True,
        "status": "NOT_RUN",
        "source_revision": None,
        "evidence": None,
    }


def contract() -> dict:
    """! @brief 8개 작업과 10개 family·전체 역할 case를 만든 뒤 검증합니다. """
    families = [
        {"id": "M31-CAP-01", "cases": [
            case("M31-CAP-01:controller", "M31-W01", ("capability_probe",), 1,
                 60, 1, 7, "feature_role_count", {"matched": 7, "revision_mismatch": 0,
                                                   "unsupported_false_positive": 0})]},
        {"id": "M31-PARITY-01", "cases": [
            case("M31-PARITY-01:all_upstream", "M31-W01", ("inventory",), 0,
                 60, 1, PARITY_ROWS, "all_inventory_rows", {"mapped": PARITY_ROWS,
                                                              "duplicate": 0, "invalid_pass": 0})]},
        {"id": "M31-ISO-01", "cases": [
            case("M31-ISO-01:cis", "M31-W02", ("central", "peripheral"), 2,
                 180, 20, 100, "received_sdu", {"minimum_received": 99,
                                                   "duplicate": 0, "out_of_order": 0, "corrupt": 0},
                 ("disconnect_pending_tx", "invalid_qos")),
            case("M31-ISO-01:bis", "M31-W02", ("broadcaster", "receiver"), 2,
                 180, 20, 100, "received_sdu", {"minimum_received": 99,
                                                   "duplicate": 0, "out_of_order": 0, "corrupt": 0},
                 ("wrong_broadcast_code", "sync_loss")),
            case("M31-ISO-01:bis_cis_combined", "M31-W02", ("broadcaster", "central", "peer"), 3,
                 180, 20, 100, "received_sdu_per_stream", {"minimum_received_per_stream": 99,
                                                              "cross_stream": 0, "corrupt": 0}),
            case("M31-ISO-01:time_sync", "M31-W02", ("sender", "receiver"), 2,
                 180, 20, 100, "timestamp_relation", {"valid_monotonic": 100,
                                                        "stale_callback": 0}),
        ]},
        {"id": "M31-AUDIO-01", "cases": [
            case(f"M31-AUDIO-01:{identifier}", "M31-W03", roles, boards,
                 180, 20 if identifier in {"W03-01", "W03-02", "W03-03", "W03-04", "W03-05", "W03-07", "W03-10"} else 100,
                 100, "control_operations_or_frames", {"valid": 100,
                                                       "state_mismatch": 0, "invalid_accept": 0},
                 ("invalid_argument", "peer_loss"))
            for identifier, _title, roles, boards in AUDIO_GROUPS
        ]},
        {"id": "M31-DF-01", "cases": [
            case("M31-DF-01:connectionless_cte_tx", "M31-W04", ("cte_advertiser",), 1,
                 180, 20, 20, "start_stop_count", {"completed": 20, "invalid_cte_accept": 0}),
            case("M31-DF-01:connected_cte_response_tx", "M31-W04", ("peripheral", "requester"), 2,
                 180, 20, 20, "response_count", {"completed": 20, "invalid_cte_accept": 0}),
            case("M31-DF-01:raw_iq_rx_candidate", "M31-W04", ("cte_advertiser", "iq_receiver"), 2,
                 180, 20, 20, "iq_report_count", {"minimum_reports": 20,
                                                  "invalid_sample_format": 0}),
            case("M31-DF-01:sdc_aod_unsupported", "M31-W04", ("capability_probe",), 1,
                 60, 20, 20, "unsupported_rejections", {"rejected": 20, "false_support": 0}),
        ]},
        {"id": "M31-CS-01", "cases": [
            case("M31-CS-01:secure_ras", "M31-W05", ("initiator", "reflector"), 2,
                 600, 100, 100, "procedure_result_count", {"valid_results": 100,
                                                              "invalid_or_nan": 0,
                                                              "insecure_accept": 0},
                 ("insecure_acl", "wrong_peer", "peer_loss")),
            case("M31-CS-01:restart", "M31-W05", ("initiator", "reflector"), 2,
                 600, 20, 20, "stop_restart_count", {"completed": 20,
                                                      "stale_result": 0}),
        ]},
        {"id": "M31-NEG-01", "cases": [
            case("M31-NEG-01:host_parser", "M31-W01", ("host",), 0,
                 60, 20, 20, "rejected_bad_inputs", {"rejected": 20, "unexpected_success": 0},
                 ("malformed", "stale", "wrong_role", "unsupported", "wrong_key", "resource_exhaustion")),
            case("M31-NEG-01:target_recovery", "M31-W06", ("sender", "receiver"), 2,
                 180, 20, 20, "recovered_failures", {"completed": 20, "resource_leaks": 0},
                 ("peer_loss", "wrong_key", "resource_exhaustion")),
        ]},
        {"id": "M31-REG-01", "cases": [
            case("M31-REG-01:m19_m30", "M31-W06", ("regression",), 3,
                 180, 1, 12, "baseline_family_count", {"families": 12,
                                                      "cross_link": 0, "resource_leaks": 0})]},
        {"id": "M31-EXAMPLE-01", "cases": [
            case("M31-EXAMPLE-01:board_roles", "M31-W07", ("all_applicable_roles",), 3,
                 600, 1, len(EXAMPLE_ROLES), "planned_role_example_count", {"built_percent": 100,
                                                                             "runtime_oracle_mismatch": 0})]},
        {"id": "M31-CLOSE-01", "cases": [
            case("M31-CLOSE-01:ledger_docs", "M31-W08", ("host",), 0,
                 60, 1, 8, "work_package_count", {"completed": 8,
                                                  "unowned_followup": 0,
                                                  "drift": 0})]},
    ]
    capabilities = [
        ("cis_central_peripheral", "M31-W02", "default_sdc"),
        ("bis_source_receiver", "M31-W02", "default_sdc"),
        ("bis_cis_combined", "M31-W02", "default_sdc"),
        ("iso_time_sync", "M31-W02", "default_sdc"),
        *[(identifier, "M31-W03", "audio_opt_in") for identifier, *_rest in AUDIO_GROUPS],
        ("connectionless_cte_tx", "M31-W04", "default_sdc"),
        ("connected_cte_response_tx", "M31-W04", "zephyr_ll_candidate"),
        ("raw_iq_rx", "M31-W04", "zephyr_ll_candidate"),
        ("aod", "M31-W04", "default_sdc"),
        ("connected_channel_sounding", "M31-W05", "default_sdc"),
    ]
    doc = {
        "schema_version": 1,
        "milestone": "M31",
        "phase": "implementation_in_progress",
        "milestone_status": "not_completed",
        "baseline": {
            "supported_release": "v0.4.1", "source_version": "0.4.1-dev",
            "ncs_revision": LOCK["ncs"]["revision"],
            "zephyr_revision": LOCK["zephyr"]["revision"],
            "board_revision": LOCK["board"]["revision"],
            "toolchain_bundle": LOCK["windows_toolchain"]["bundle_id"],
        },
        "work_packages": [
            {"id": f"M31-W{index:02}", "title": title, "status": "not_started",
             "exact_evidence": None}
            for index, title in enumerate(WORK, 1)
        ],
        "capabilities": [
            {"id": identifier, "owner_work_id": owner, "controller_variant": controller,
             "source_status": "source_candidate", "target_applicability": "unresolved",
             "native_build": "NOT_RUN", "nu54dk_build": "NOT_RUN",
             "arduino_build": "NOT_RUN",
             "runtime_query": "NOT_RUN", "functional_hil": "NOT_RUN",
             "source_revision": None, "stage_evidence": {
                 "native_build": None, "nu54dk_build": None,
                 "arduino_build": None, "runtime_query": None,
                 "functional_hil": None,
             }, "evidence": None}
            for identifier, owner, controller in capabilities
        ],
        "audio_groups": [
            {"id": identifier, "title": title, "roles": list(roles),
             "minimum_boards": boards, "status": "NOT_RUN"}
            for identifier, title, roles, boards in AUDIO_GROUPS
        ],
        "example_roles": [
            {"id": identifier, "planned_sketch": None, "actual_sketch": None,
             "source_revision": None, "build_status": "NOT_RUN",
             "runtime_status": "NOT_RUN", "evidence": None}
            for identifier in EXAMPLE_ROLES
        ],
        "test_families": families,
        "follow_up_cases": [
            {"id": "external_audio_io_physical", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "external_antenna_angle_physical", "verification_owner": "user",
             "verification_stage": "user_follow_up", "development_blocker": False,
             "release_blocker": False, "status": "NOT_RUN", "evidence": None},
            {"id": "ubuntu_host_physical", "verification_owner": "user",
             "verification_stage": "final_release", "development_blocker": False,
             "release_blocker": True, "status": "NOT_RUN", "evidence": None},
            {"id": "macos_host_physical", "verification_owner": "user",
             "verification_stage": "final_release", "development_blocker": False,
             "release_blocker": True, "status": "NOT_RUN", "evidence": None},
        ],
        "counts": {
            "work_total": 8, "work_completed": 0, "test_family_total": 10,
            "test_family_passed": 0,
            "audio_group_total": len(AUDIO_GROUPS),
            "example_role_total": len(EXAMPLE_ROLES),
            "parity_rows": PARITY_ROWS,
            "test_subcases": sum(len(family["cases"]) for family in families),
        },
    }
    validate(doc)
    return doc


def validate(doc: dict) -> None:
    """! @brief 분모·범위·PASS 증거의 부당 승격을 거부합니다. """
    counts = doc["counts"]
    if counts["work_total"] != len(doc["work_packages"]) or counts["work_completed"] != sum(
        package["status"] == "completed" for package in doc["work_packages"]
    ):
        raise ValueError("work denominator mismatch")
    for package in doc["work_packages"]:
        if package["status"] not in {"not_started", "in_progress", "completed"}:
            raise ValueError("work package status unknown")
        if package["status"] == "completed":
            if (package["id"] == "M31-W02" and
                    package.get("public_example_status") != "PASS"):
                raise ValueError("W02 public ISO example flow incomplete")
            proof = package.get("exact_evidence")
            if not proof or not (CORE / proof).is_file():
                raise ValueError("completed work without exact evidence")
            audit = json.loads((CORE / proof).read_text(encoding="utf-8"))
            if audit.get("status") != "PASS" or audit.get("source_clean") is not True or (
                audit.get("work_id") != package["id"]
            ):
                raise ValueError("completed work evidence scope mismatch")
    if counts["test_family_total"] != len(doc["test_families"]) or counts["test_subcases"] != sum(
        len(family["cases"]) for family in doc["test_families"]
    ):
        raise ValueError("test denominator mismatch")
    if counts["test_family_passed"] != sum(
        all(entry["status"] == "PASS" for entry in family["cases"])
        for family in doc["test_families"]
    ):
        raise ValueError("test family PASS denominator drift")
    if counts["audio_group_total"] != len(doc["audio_groups"]):
        raise ValueError("audio group denominator mismatch")
    if counts["example_role_total"] != len(doc["example_roles"]):
        raise ValueError("example role denominator mismatch")
    role_ids = [role["id"] for role in doc["example_roles"]]
    if len(role_ids) != len(set(role_ids)) or set(role_ids) != set(EXAMPLE_ROLES):
        raise ValueError("example role identity mismatch")
    for role in doc["example_roles"]:
        related = role.get("related_sketches", [])
        if (not isinstance(related, list) or
                any(not isinstance(sketch, str) for sketch in related) or
                len(related) != len(set(related))):
            raise ValueError("related Arduino sketch list invalid")
        sketches = ([role["actual_sketch"]] if role["actual_sketch"] else []) + related
        for sketch in sketches:
            if (not isinstance(sketch, str) or not sketch.startswith("libraries/") or
                    not sketch.endswith(".ino") or
                    not (CORE / sketch).resolve().is_relative_to((CORE / "libraries").resolve()) or
                    not (CORE / sketch).is_file()):
                raise ValueError("related Arduino sketch path invalid")
        if role["runtime_status"] == "PASS" and (
            role["build_status"] != "PASS" or not sketches or not role["evidence"] or
            not (CORE / role["evidence"]).is_file() or
            not role["source_revision"] or
            re.fullmatch(r"[0-9a-f]{40}", role["source_revision"]) is None
        ):
            raise ValueError("example runtime PASS without source, build or evidence")
    if counts["parity_rows"] != PARITY_ROWS:
        raise ValueError("parity discovered denominator mismatch")
    for group in doc["audio_groups"]:
        if group["status"] == "PASS" and not any(
            entry["id"] == f"M31-AUDIO-01:{group['id']}" and entry["status"] == "PASS"
            for entry in doc["test_families"][3]["cases"]
        ):
            raise ValueError("audio group PASS without functional case")
    for capability in doc["capabilities"]:
        stages = ("native_build", "nu54dk_build", "arduino_build", "runtime_query", "functional_hil")
        if set(capability.get("stage_evidence", {})) != set(stages):
            raise ValueError("capability stage schema missing")
        for stage in stages:
            status = capability.get(stage)
            if status not in {"NOT_RUN", "PASS", "FAIL", "HOLD", "UNSUPPORTED"}:
                raise ValueError("capability stage status unknown")
            evidence = capability["stage_evidence"][stage]
            if status == "PASS" and (not evidence or not capability.get("source_revision")):
                raise ValueError("capability PASS without exact stage evidence")
            if status == "NOT_RUN" and evidence is not None:
                raise ValueError("NOT_RUN capability has success evidence")
            if status == "PASS" and (
                re.fullmatch(r"[0-9a-f]{40}", capability["source_revision"]) is None or
                not (CORE / evidence).is_file()
            ):
                raise ValueError("capability PASS source/evidence path invalid")
        if capability["functional_hil"] == "PASS" and (
            capability["nu54dk_build"] != "PASS" or capability["runtime_query"] != "PASS"
        ):
            raise ValueError("functional HIL promoted before build/query")
    completed_work = {
        package["id"] for package in doc["work_packages"] if package["status"] == "completed"
    }
    if "M31-W04" in completed_work:
        capability_by_id = {entry["id"]: entry for entry in doc["capabilities"]}
        required_capabilities = {
            "connectionless_cte_tx", "connected_cte_response_tx", "raw_iq_rx", "aod",
        }
        if not required_capabilities.issubset(capability_by_id):
            raise ValueError("W04 capability boundary missing")
        connectionless = capability_by_id["connectionless_cte_tx"]
        connected = capability_by_id["connected_cte_response_tx"]
        if (connectionless["controller_variant"] != "default_sdc" or
                connectionless["target_applicability"] != "product_sdc_connectionless_aoa_tx" or
                any(connectionless[stage] != "PASS" for stage in (
                    "nu54dk_build", "arduino_build", "runtime_query", "functional_hil"
                ))):
            raise ValueError("W04 product SDC CTE TX boundary mismatch")
        if (connected["controller_variant"] != "zephyr_ll_candidate" or
                connected["target_applicability"] != "zephyr_ll_opt_in_aoa_response" or
                any(connected[stage] != "PASS" for stage in (
                    "nu54dk_build", "arduino_build", "runtime_query", "functional_hil"
                ))):
            raise ValueError("W04 opt-in connected response boundary mismatch")
        for identifier in ("raw_iq_rx", "aod"):
            unsupported = capability_by_id[identifier]
            if (unsupported["controller_variant"] != "default_sdc" or
                    unsupported["target_applicability"] !=
                    "unsupported_nrf54l15_product_sdc_ncs_3_4_0" or
                    any(unsupported[stage] != "UNSUPPORTED" for stage in (
                        "native_build", "nu54dk_build", "arduino_build", "runtime_query",
                        "functional_hil"
                    ))):
                raise ValueError("W04 product SDC unsupported boundary mismatch")
        example_by_id = {entry["id"]: entry for entry in doc["example_roles"]}
        for identifier in ("cte_beacon", "cte_peripheral"):
            if (identifier not in example_by_id or
                    example_by_id[identifier]["build_status"] != "PASS" or
                    example_by_id[identifier]["runtime_status"] != "PASS"):
                raise ValueError("W04 public TX example incomplete")
        receiver = example_by_id.get("raw_iq_receiver_candidate")
        if (receiver is None or receiver["build_status"] != "UNSUPPORTED" or
                receiver["runtime_status"] != "UNSUPPORTED"):
            raise ValueError("W04 product SDC RX example boundary mismatch")
        df_family = next((family for family in doc["test_families"]
                          if family["id"] == "M31-DF-01"), None)
        if df_family is None:
            raise ValueError("W04 DF test family missing")
        expected_case_status = {
            "M31-DF-01:connectionless_cte_tx": "PASS",
            "M31-DF-01:connected_cte_response_tx": "PASS",
            "M31-DF-01:raw_iq_rx_candidate": "UNSUPPORTED",
            "M31-DF-01:sdc_aod_unsupported": "UNSUPPORTED",
        }
        actual_case_status = {entry["id"]: entry["status"] for entry in df_family["cases"]}
        if any(actual_case_status.get(identifier) != status
               for identifier, status in expected_case_status.items()):
            raise ValueError("W04 DF case boundary mismatch")
    if "M31-W05" in completed_work:
        capability_by_id = {entry["id"]: entry for entry in doc["capabilities"]}
        channel_sounding = capability_by_id.get("connected_channel_sounding")
        if (channel_sounding is None or
                channel_sounding["controller_variant"] != "default_sdc" or
                channel_sounding["target_applicability"] !=
                "arduino_ras_supported_path_and_security_negative_complete" or
                any(channel_sounding[stage] != "PASS" for stage in (
                    "native_build", "nu54dk_build", "arduino_build", "runtime_query",
                    "functional_hil"
                ))):
            raise ValueError("W05 product SDC CS boundary mismatch")
        package = next(item for item in doc["work_packages"]
                       if item["id"] == "M31-W05")
        audit = json.loads((CORE / package["exact_evidence"]).read_text(encoding="utf-8"))
        supported = audit.get("supported_path", {})
        negative = audit.get("negative", {})
        stale = negative.get("one_sided_stale_key", {})
        flash_after = audit.get("flash_after", {})
        if (supported.get("status") != "PASS" or
                supported.get("raw_ras_results") != 100 or
                supported.get("stop_restart") != "20/20" or
                supported.get("disconnect_reconnect") != "20/20"):
            raise ValueError("W05 supported RAS evidence incomplete")
        if (negative.get("insecure_same_acl", {}).get("status") != "PASS" or
                negative.get("wrong_peer_and_missing_service", {}).get("status") != "PASS" or
                stale.get("status") != "PASS" or
                stale.get("authenticated_ras_accepts") != 0 or
                stale.get("automatic_repair_pairings") != 0 or
                stale.get("negative_raw_reports") != 0 or
                stale.get("stop_confirmed") is not True):
            raise ValueError("W05 security negative evidence incomplete")
        if (flash_after.get("status") != "PASS" or
                flash_after.get("independent_passes", 0) < 2 or
                flash_after.get("root_cause_claim") != "NOT_CLAIMED"):
            raise ValueError("W05 flash-after evidence incomplete")
        example_by_id = {entry["id"]: entry for entry in doc["example_roles"]}
        for identifier in ("cs_initiator", "cs_reflector"):
            example = example_by_id.get(identifier)
            if (example is None or example["build_status"] != "PASS" or
                    example["runtime_status"] != "PASS"):
                raise ValueError("W05 public RAS example incomplete")
    for family in doc["test_families"]:
        for entry in family["cases"]:
            if entry["status"] == "PASS" and (not entry["source_revision"] or not entry["evidence"]):
                raise ValueError("PASS without exact evidence")
            if entry["status"] == "PASS" and (
                re.fullmatch(r"[0-9a-f]{40}", entry["source_revision"]) is None or
                not (CORE / entry["evidence"]).is_file()
            ):
                raise ValueError("PASS case source/evidence path invalid")
            if entry["verification_owner"] != "developer" or entry["verification_stage"] != "development":
                raise ValueError("required implementation hidden as follow-up")
    for entry in doc["follow_up_cases"]:
        if entry["status"] == "PASS" and not entry["evidence"]:
            raise ValueError("follow-up PASS without physical evidence")
        if entry["verification_owner"] != "user" or entry["development_blocker"]:
            raise ValueError("follow-up owner/blocker corruption")
        if entry["verification_stage"] == "user_follow_up" and entry["release_blocker"]:
            raise ValueError("user follow-up release blocker corruption")
        if entry["verification_stage"] == "final_release" and not entry["release_blocker"]:
            raise ValueError("final Host physical gate removed")


def main() -> int:
    """! @brief 초기 계약 생성과 기계 원장의 검증을 분리합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = CORE / "variants/nu54dk/m31-ble-readiness.json"
    if args.check:
        validate(json.loads(target.read_text(encoding="utf-8")))
    else:
        target.write_text(json.dumps(contract(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("M31_CONTRACT_OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print(f"M31_CONTRACT_FAIL: {error}", file=sys.stderr)
        sys.exit(1)
