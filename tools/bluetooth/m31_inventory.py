"""! @brief 고정 NCS Bluetooth sample metadata를 M31 parity 원장으로 수집합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import yaml


TARGET = "nrf54l15dk/nrf54l15/cpuapp"
MODULES = {
    "nrf": "99553055607b2e9885fbc80ccd11fa9da81c2df0",
    "zephyr": "bf801e4e3d19e1ffa76164346480cb7734dd2800",
}
METADATA_KEYS = (
    "platform_allow", "platform_exclude", "integration_platforms", "filter",
    "depends_on", "build_only", "sysbuild", "harness", "extra_args",
    "extra_conf_files", "extra_overlay_confs", "tags",
)
RESULT_KINDS = (
    "native_build", "nu54dk_build", "arduino_build", "runtime",
    "negative", "interoperability",
)
SOURCE_ONLY_SYMBOLS = {
    "M31-W02": (
        "BT_ISO", "BT_ISO_CENTRAL", "BT_ISO_PERIPHERAL",
        "BT_ISO_BROADCASTER", "BT_ISO_SYNC_RECEIVER",
    ),
    "M31-W03": (
        "BT_BAP_UNICAST_CLIENT", "BT_BAP_UNICAST_SERVER",
        "BT_BAP_BROADCAST_SOURCE", "BT_BAP_BROADCAST_SINK",
        "BT_BAP_SCAN_DELEGATOR", "BT_BAP_BROADCAST_ASSISTANT",
        "BT_PACS", "BT_ASCS", "BT_CAP_INITIATOR", "BT_CAP_ACCEPTOR",
        "BT_CAP_COMMANDER", "BT_CSIP_SET_MEMBER", "BT_CSIP_SET_COORDINATOR",
        "BT_PBP", "BT_VCP_VOL_REND", "BT_VCP_VOL_CTLR", "BT_VOCS",
        "BT_VOCS_CLIENT", "BT_AICS", "BT_AICS_CLIENT",
        "BT_MICP_MIC_DEV", "BT_MICP_MIC_CTLR", "BT_MCS", "BT_MCC",
        "BT_TBS", "BT_TBS_CLIENT", "BT_TMAP", "BT_GMAP", "BT_HAS",
        "BT_HAS_CLIENT",
    ),
    "M31-W04": ("BT_DF", "BT_DF_CONNECTIONLESS_CTE_TX", "BT_DF_CONNECTIONLESS_CTE_RX"),
    "M31-W05": ("BT_CHANNEL_SOUNDING",),
}
M31_TEST_FAMILIES = {
    "M31-W01": "M31-PARITY-01",
    "M31-W02": "M31-ISO-01",
    "M31-W03": "M31-AUDIO-01",
    "M31-W04": "M31-DF-01",
    "M31-W05": "M31-CS-01",
}


def sha256(data: bytes) -> str:
    """! @brief 원본 byte의 SHA-256을 계산합니다. """
    return hashlib.sha256(data).hexdigest()


def source_digest(directory: Path) -> tuple[str, int, int]:
    """! @brief sample 하위의 경로와 모든 원본 byte를 결정적으로 해시합니다. """
    digest = hashlib.sha256()
    count = 0
    size = 0
    for source in sorted(path for path in directory.rglob("*") if path.is_file()):
        relative = source.relative_to(directory).as_posix().encode("utf-8")
        payload = source.read_bytes()
        digest.update(len(relative).to_bytes(4, "little"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "little"))
        digest.update(payload)
        count += 1
        size += len(payload)
    return digest.hexdigest(), count, size


def revision(path: Path) -> str:
    """! @brief source checkout revision을 고정 lock과 대조합니다. """
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def owner_for(module: str, sample_path: str) -> tuple[str, str, str | None]:
    """! @brief 전체 sample을 명시된 제품 작업 묶음에 귀속합니다. """
    name = sample_path.removeprefix("samples/bluetooth/")
    if sample_path == "applications/nrf_audio":
        return "M31-W03", "profile", None
    if sample_path == "applications/ipc_radio":
        return "M32-W01", "direct", None
    if name.startswith("classic/") or name == "nrf_dm":
        return "M33-W01", "excluded", "nrf54l15 내장 BLE 범위 밖 또는 고정 SDK target 비적용"
    if name.startswith("channel_sounding/"):
        return "M31-W05", "profile", None
    if name.startswith("direction_finding_"):
        return "M31-W04", "profile", None
    if name.startswith(("iso_", "iso/")):
        return "M31-W02", "profile", None
    if name.startswith((
        "bap_", "cap_", "pbp_", "ccp_", "tmap_", "hap_",
    )):
        return "M31-W03", "profile", None
    if name.startswith("mesh/dfu/"):
        return "M32-W08", "profile", None
    if name.startswith(("mesh/light_ctrl", "mesh/ble_peripheral_lbs_coex")):
        return "M32-W07" if "light_ctrl" in name else "M32-W10", "profile", None
    if name.startswith("mesh") or "/mesh/" in sample_path:
        return "M32-W06", "profile", None
    if name.startswith(("path_loss_monitoring", "rssi_power_control")):
        return "M32-W02", "profile", None
    if name.startswith(("shorter_conn_intervals", "subrating", "throughput")):
        return "M32-W03", "profile", None
    if name.startswith((
        "multiple_adv_sets", "scanning_while_connecting", "encrypted_advertising",
        "broadcaster_multiple", "direct_adv", "peripheral_accept_list",
        "peripheral_identity", "peripheral_with_multiple_identities",
    )):
        return "M32-W04", "profile", None
    if name.startswith(("llpm", "conn_time_sync", "event_trigger", "radio_notification_cb")):
        return "M32-W05", "profile", None
    if name.startswith("radio_coex"):
        return "M32-W10", "profile", None
    if sample_path.startswith(("samples/esb/", "samples/wifi/ble_coex")):
        return "M32-W10", "profile", None
    if name.startswith(("fast_pair", "peripheral_ancs_client", "peripheral_ams_client",
                        "enocean", "nrf_auraconfig")):
        return "M33-W03", "template", None
    if name.startswith(("hci_", "direct_test_mode", "rpc_host")):
        return "M33-W04", "template", None
    return "M33-W01", "direct", None


def feature_ids_for(module: str, sample_path: str, owner: str) -> list[str]:
    """! @brief 고정 source path를 M31 하위 기능 또는 후속 catalog key에 연결합니다. """
    name = sample_path.removeprefix("samples/bluetooth/")
    if sample_path == "applications/nrf_audio":
        return ["M31-A:W03-01", "M31-A:W03-02", "M31-A:W03-03"]
    if owner == "M31-W02":
        if "time_sync" in name:
            return ["M31-A:iso_time_sync"]
        if "combined" in name:
            return ["M31-A:bis_cis_combined"]
        if "broadcast" in name or "receive" in name:
            return ["M31-A:bis"]
        return ["M31-A:cis"]
    if owner == "M31-W03":
        audio_names = (
            ("bap_broadcast_assistant", "W03-04"),
            ("bap_broadcast", "W03-03"),
            ("bap_unicast", "W03-02"),
            ("cap_", "W03-05"),
            ("pbp_", "W03-07"),
            ("ccp_", "W03-09"),
            ("tmap_", "W03-10"),
            ("hap_", "W03-11"),
        )
        return [f"M31-A:{identifier}" for prefix, identifier in audio_names if name.startswith(prefix)]
    if owner == "M31-W04":
        return ["M31-B:raw_iq_rx" if name.endswith(("_rx", "_central")) else "M31-B:cte_tx"]
    if owner == "M31-W05":
        return ["M31-C:connected_channel_sounding"]
    return [f"catalog:{module}:{sample_path}"]


def bluetooth_dependency(metadata: dict, directory: Path) -> str | None:
    """! @brief 기본 Bluetooth root 밖의 tag·Kconfig 의존성을 찾습니다. """
    common = metadata.get("common") or {}
    tests = metadata.get("tests") or {}
    variants = [common, *tests.values()] if isinstance(tests, dict) else [common]
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        tags = variant.get("tags") or []
        if isinstance(tags, str):
            tags = tags.split()
        if "bluetooth" in tags:
            return "upstream_bluetooth_tag"
        dependency = str(variant.get("depends_on") or "")
        if "bluetooth" in dependency.lower() or "CONFIG_BT" in dependency:
            return "upstream_bluetooth_dependency"
    configuration = directory / "prj.conf"
    if configuration.exists() and re.search(r"^CONFIG_BT=y$", configuration.read_text(
        encoding="utf-8", errors="replace"
    ), re.MULTILINE):
        return "application_bluetooth_kconfig"
    return None


def target_metadata(effective: dict) -> dict:
    """! @brief 정확한 L15 qualifier만 upstream metadata 근거로 사용합니다. """
    allow = effective.get("platform_allow")
    exclude = effective.get("platform_exclude")
    integration = effective.get("integration_platforms")
    def exact(values: object) -> bool | None:
        if values is None:
            return None
        entries = values if isinstance(values, list) else [values]
        return TARGET in entries
    return {
        "platform_allow_exact": exact(allow),
        "platform_exclude_exact": exact(exclude),
        "integration_platform_exact": exact(integration),
        "filter_evaluated": False if effective.get("filter") else None,
    }


def empty_results() -> dict:
    """! @brief build와 실행의 미검증 상태를 독립적으로 보존합니다. """
    return {
        kind: {"status": "NOT_RUN", "source_revision": None, "evidence": None}
        for kind in RESULT_KINDS
    }


def planned_verification(owner: str, identifier: str) -> dict:
    """! @brief 후속 owner의 수치 미확정과 M31 고정 family를 구별합니다. """
    family = M31_TEST_FAMILIES.get(owner)
    return {
        "local_test_id": family,
        "case_id": f"{identifier}:implementation",
        "timeout_seconds": None,
        "iterations": None,
        "denominator": None,
        "metric": None,
        "unit": None,
        "acceptance": None,
        "negative_expected_errors": [],
        "recovery_timeout_seconds": None,
        "maximum_diagnostic_retests": 1,
        "numeric_source": "variants/nu54dk/m31-ble-readiness.json" if family else None,
    }


def resource_budget() -> dict:
    """! @brief 측정 전 자원값을 0이나 임의 상한으로 꾸미지 않습니다. """
    return {
        "ram_bytes": None, "rram_bytes": None, "acl_slots": None,
        "cis_slots": None, "bis_slots": None, "buffer_count": None,
        "ase_slots": None, "codec_frames": None,
    }


def source_only_features(sdk_root: Path) -> list[dict]:
    """! @brief sample이 없는 Bluetooth 기능도 정확한 Kconfig 근거로 기록합니다. """
    patterns = {
        symbol: re.compile(rf"^(?:menuconfig|config) {re.escape(symbol)}(?:\s|$)", re.MULTILINE)
        for symbols in SOURCE_ONLY_SYMBOLS.values() for symbol in symbols
    }
    references = {symbol: [] for symbol in patterns}
    for module in MODULES:
        root = sdk_root / module
        for source in sorted((root / "subsys/bluetooth").rglob("Kconfig*")):
            if not source.is_file():
                continue
            content = source.read_text(encoding="utf-8", errors="replace")
            for symbol, pattern in patterns.items():
                if pattern.search(content):
                    references[symbol].append(f"{module}:{source.relative_to(root).as_posix()}")
    features = []
    for work_id, symbols in SOURCE_ONLY_SYMBOLS.items():
        for symbol in symbols:
            features.append({
                "id": f"kconfig:{symbol}",
                "symbol": symbol,
                "owner_work_id": work_id,
                "source_references": references[symbol],
                "source_status": "source_candidate" if references[symbol] else "unresolved",
                "target_applicability": "unresolved",
                "controller_variant": None,
                "native_build": empty_results()["native_build"],
                "runtime": empty_results()["runtime"],
            })
    return features


def collect(sdk_root: Path, core_root: Path) -> dict:
    """! @brief 두 upstream root의 sample/test variant를 빠짐없이 수집합니다. """
    lock = json.loads((core_root / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
    for module, expected in MODULES.items():
        found = revision(sdk_root / module)
        if found != expected:
            raise ValueError(f"{module} revision mismatch: {found}")
    if lock["ncs"]["revision"] != MODULES["nrf"] or lock["zephyr"]["revision"] != MODULES["zephyr"]:
        raise ValueError("repository SDK lock mismatch")
    samples = []
    variants = []
    discovery_roots = {
        "nrf": ("samples/bluetooth", "samples", "applications"),
        "zephyr": ("samples/bluetooth", "samples"),
    }
    for module in MODULES:
        discovered_paths = {}
        for discovery_root in discovery_roots[module]:
            root = sdk_root / module / discovery_root
            for metadata_path in sorted(root.rglob("sample.yaml")):
                if metadata_path in discovered_paths:
                    continue
                if discovery_root != "samples/bluetooth" and "samples/bluetooth" in metadata_path.as_posix():
                    continue
                loaded = yaml.safe_load(metadata_path.read_bytes())
                if not isinstance(loaded, dict):
                    raise ValueError(f"malformed sample metadata: {metadata_path}")
                reason = "primary_bluetooth_tree" if discovery_root == "samples/bluetooth" else bluetooth_dependency(
                    loaded, metadata_path.parent
                )
                if reason:
                    discovered_paths[metadata_path] = (loaded, discovery_root, reason)
        for metadata_path, (loaded, discovery_root, discovery_reason) in sorted(discovered_paths.items()):
            raw = metadata_path.read_bytes()
            digest, source_count, source_size = source_digest(metadata_path.parent)
            path = metadata_path.parent.relative_to(sdk_root / module).as_posix()
            sample_id = f"{module}:{path}"
            owner, route, exclusion = owner_for(module, path)
            feature_ids = feature_ids_for(module, path, owner)
            related = sorted(
                entry.relative_to(sdk_root / module).as_posix()
                for entry in metadata_path.parent.iterdir()
                if entry.name.lower().startswith("readme") or entry.name.endswith(".overlay")
            )
            config_file = metadata_path.parent / "prj.conf"
            if config_file.is_file():
                related.append(config_file.relative_to(sdk_root / module).as_posix())
                related.sort()
            samples.append({
                "id": sample_id,
                "upstream_module": module,
                "upstream_path": path,
                "metadata_path": f"{path}/sample.yaml",
                "source_sha256": digest,
                "metadata_sha256": sha256(raw),
                "source_file_count": source_count,
                "source_size_bytes": source_size,
                "discovery_root": discovery_root,
                "discovery_reason": discovery_reason,
                "readme_or_overlay": related,
                "owner_work_id": owner,
                "route": route,
                "feature_ids": feature_ids,
                "exclusion_reason": exclusion,
                "sample_metadata": loaded.get("sample"),
            })
            common = loaded.get("common") or {}
            tests = loaded.get("tests") or {}
            if not isinstance(common, dict) or not isinstance(tests, dict):
                raise ValueError(f"malformed common/tests: {metadata_path}")
            for test_id, override in sorted(tests.items()):
                if not isinstance(override, dict):
                    raise ValueError(f"malformed test variant: {metadata_path}:{test_id}")
                effective = {**common, **override}
                variants.append({
                    "id": f"{sample_id}:{test_id}",
                    "parent_sample_id": sample_id,
                    "test_id": test_id,
                    "variant_id": test_id,
                    "metadata_common": common,
                    "metadata_override": override,
                    "metadata_effective": {key: effective.get(key) for key in METADATA_KEYS},
                    "target_metadata": target_metadata(effective),
                    "target_applicability": "unresolved",
                    "target_reason": "native/NU54DK build 및 controller 실행 판정 전",
                    "source_status": "source_candidate",
                    "source_references": related,
                    "controller_variant": "zephyr_ll_candidate" if owner == "M31-W04" and (
                        path.endswith("_rx") or path.endswith("_central")
                    ) else "default_sdc" if owner.startswith("M31-") else None,
                    "maturity": None,
                    "protocol_dependencies": [],
                    "minimum_boards": None,
                    "roles": None,
                    "peer_dependencies": None,
                    "external_equipment": None,
                    "external_wiring": None,
                    "resource_budget": resource_budget(),
                    "verification_contract": planned_verification(owner, f"{sample_id}:{test_id}"),
                    "arduino_provision": {
                        "primary_route": route, "secondary_routes": [],
                        "planned_sketch": None, "actual_sketch": None,
                        "profile": None, "library": None, "build_matrix_id": None,
                        "public_api_boundary": None, "direct_api_opt_in": None,
                    },
                    "evidence_identity": {
                        "firmware_sha256": None, "image_sha256": None,
                        "probe_sha256": None, "anonymous_role_mapping": None,
                        "nonce": None, "attempt_id": None, "raw_evidence_sha256": None,
                    },
                    "scope_status": "excluded" if exclusion else "planned",
                    "scope_reason": exclusion,
                    "scope_decision_date": "2026-09-16" if exclusion else None,
                    "follow_up_owner_work_id": owner if owner.startswith(("M32-", "M33-")) else None,
                    "owner_work_id": owner,
                    "route": route,
                    "exclusion_reason": exclusion,
                    "feature_ids": feature_ids,
                    "planned_sketch": None,
                    "actual_sketch": None,
                    "verification_cases": [{
                        "id": f"{sample_id}:{test_id}:implementation",
                        "verification_owner": "developer",
                        "verification_stage": "development",
                        "blocker_scope": owner,
                        "development_blocker": exclusion is None,
                        "release_blocker": exclusion is None,
                        "status": "NOT_RUN",
                        "evidence": None,
                    }],
                    "results": empty_results(),
                })
    features = source_only_features(sdk_root)
    return {
        "schema_version": 1,
        "generator_version": "m31-w01-1",
        "generated_from": {module: {"revision": rev, "roots": list(discovery_roots[module])} for module, rev in MODULES.items()},
        "board_revision": lock["board"]["revision"],
        "lock_sha256": sha256((core_root / "tools/ci/ncs-3.4.0.lock.json").read_bytes()),
        "windows_toolchain_bundle": lock["windows_toolchain"]["bundle_id"],
        "target_qualifier": TARGET,
        "samples": samples,
        "variants": variants,
        "source_only_features": features,
        "counts": {"samples": len(samples), "variants": len(variants), "source_only_features": len(features)},
    }


def validate(doc: dict) -> None:
    """! @brief identity·책임·증거 상태의 잘못된 승격을 차단합니다. """
    if doc.get("schema_version") != 1 or doc.get("target_qualifier") != TARGET:
        raise ValueError("schema/target mismatch")
    for name in ("board_revision", "lock_sha256", "generator_version", "windows_toolchain_bundle"):
        if not doc.get(name):
            raise ValueError(f"inventory document identity missing: {name}")
    if re.fullmatch(r"[0-9a-f]{40}", doc["board_revision"]) is None or (
        re.fullmatch(r"[0-9a-f]{64}", doc["lock_sha256"]) is None
    ):
        raise ValueError("board/lock identity malformed")
    generated = doc.get("generated_from")
    if not isinstance(generated, dict) or any(
        generated.get(module, {}).get("revision") != expected or
        not generated.get(module, {}).get("roots") for module, expected in MODULES.items()
    ):
        raise ValueError("upstream revision mismatch")
    parents = {item["id"] for item in doc["samples"]}
    if len(parents) != len(doc["samples"]):
        raise ValueError("duplicate sample identity")
    for sample in doc["samples"]:
        for name in ("upstream_module", "upstream_path", "metadata_path", "discovery_root",
                     "discovery_reason", "owner_work_id", "route", "feature_ids"):
            if name not in sample or sample[name] is None:
                raise ValueError(f"sample source/owner field missing: {name}")
        if sample["id"] != f"{sample['upstream_module']}:{sample['upstream_path']}" or (
            sample["upstream_module"] not in MODULES
        ):
            raise ValueError("sample source identity mismatch")
        if any(re.fullmatch(r"[0-9a-f]{64}", sample.get(name, "")) is None
               for name in ("source_sha256", "metadata_sha256")) or (
            sample.get("source_file_count", 0) < 1 or sample.get("source_size_bytes", -1) < 0
        ):
            raise ValueError("sample subtree/metadata hash missing")
    identities = set()
    for item in doc["variants"]:
        if item["id"] in identities or item["parent_sample_id"] not in parents:
            raise ValueError("duplicate/orphan variant identity")
        identities.add(item["id"])
        if item["id"] != f"{item['parent_sample_id']}:{item['test_id']}" or (
            item["variant_id"] != item["test_id"]
        ):
            raise ValueError("upstream variant ID mismatch")
        for name in ("metadata_common", "metadata_override", "metadata_effective", "target_metadata",
                     "source_status", "source_references", "controller_variant", "maturity",
                     "protocol_dependencies", "minimum_boards", "roles", "peer_dependencies",
                     "external_equipment", "external_wiring", "resource_budget",
                     "verification_contract", "arduino_provision", "evidence_identity", "scope_status"):
            if name not in item:
                raise ValueError(f"variant schema field missing: {name}")
        if not all(key in item["metadata_effective"] for key in METADATA_KEYS) or (
            item["target_metadata"] != target_metadata(item["metadata_effective"])
        ):
            raise ValueError("metadata nullable/target interpretation drift")
        if item["minimum_boards"] is not None and item["minimum_boards"] not in range(0, 4):
            raise ValueError("minimum board count invalid")
        if item["source_status"] not in {"source_candidate", "unresolved"} or (
            item["scope_status"] != ("excluded" if item["exclusion_reason"] else "planned")
        ):
            raise ValueError("source/scope status drift")
        contract = item["verification_contract"]
        if contract.get("case_id") != f"{item['id']}:implementation" or (
            contract.get("local_test_id") != M31_TEST_FAMILIES.get(item["owner_work_id"])
        ):
            raise ValueError("local test/owner mapping drift")
        owner_match = re.fullmatch(r"M(31|32|33)-W([0-9]{2})", item["owner_work_id"])
        if owner_match is None or int(owner_match.group(2)) not in range(
            1, {"31": 9, "32": 13, "33": 9}[owner_match.group(1)]
        ):
            raise ValueError("invalid owner")
        if item["route"] not in {"direct", "profile", "template", "excluded"}:
            raise ValueError("invalid route")
        if item["route"] == "excluded" and not item["exclusion_reason"]:
            raise ValueError("reasonless exclusion")
        for case in item["verification_cases"]:
            stage = case["verification_stage"]
            owner = case["verification_owner"]
            if stage == "user_follow_up":
                if owner != "user" or case["development_blocker"] or case["release_blocker"]:
                    raise ValueError("user follow-up scope corruption")
            elif stage == "final_release":
                if owner != "user" or case["development_blocker"] or not case["release_blocker"]:
                    raise ValueError("final Host gate corruption")
            elif stage == "development":
                if owner != "developer":
                    raise ValueError("implementation case hidden")
            else:
                raise ValueError("invalid verification stage")
            if case.get("status") == "PASS" and not case.get("evidence"):
                raise ValueError("verification PASS without evidence")
            if stage == "user_follow_up" and case.get("status") == "PASS":
                raise ValueError("user physical NOT_RUN cannot be promoted by inventory")
        for kind in RESULT_KINDS:
            result = item["results"][kind]
            if result["status"] not in {"NOT_RUN", "PASS", "FAIL", "HOLD", "NOT_APPLICABLE"}:
                raise ValueError("invalid result status")
            if result["status"] == "PASS" and (not result["source_revision"] or not result["evidence"]):
                raise ValueError("PASS without exact evidence")
            if kind == "runtime" and result["status"] == "PASS" and item["results"]["nu54dk_build"]["status"] != "PASS":
                raise ValueError("runtime PASS without target build")
            if kind == "runtime" and result["status"] == "PASS" and item.get("target_applicability") != "applicable":
                raise ValueError("runtime PASS with unresolved target applicability")
            if result["status"] == "PASS":
                if re.fullmatch(r"[0-9a-f]{40}", result["source_revision"]) is None:
                    raise ValueError("PASS source revision malformed")
                evidence_path = (Path(__file__).resolve().parents[2] / result["evidence"]).resolve()
                root = Path(__file__).resolve().parents[2]
                if root not in evidence_path.parents or not evidence_path.is_file():
                    raise ValueError("PASS evidence link missing or outside repository")
        if item["results"]["runtime"]["status"] == "PASS" and any(
            contract.get(key) is None for key in ("timeout_seconds", "iterations", "denominator",
                                                  "metric", "unit", "acceptance")
        ):
            raise ValueError("runtime PASS without fixed quantitative contract")
    if doc["counts"] != {
        "samples": len(doc["samples"]),
        "variants": len(doc["variants"]),
        "source_only_features": len(doc["source_only_features"]),
    }:
        raise ValueError("inventory counts drift")
    symbols = {item["id"] for item in doc["source_only_features"]}
    if len(symbols) != len(doc["source_only_features"]):
        raise ValueError("duplicate source-only feature")
    for feature in doc["source_only_features"]:
        if feature["runtime"]["status"] == "PASS":
            raise ValueError("source-only runtime cannot be promoted by inventory")


def main() -> int:
    """! @brief 생성·검증·drift 검사를 CLI에서 실행합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("variants/nu54dk/ncs-v3.4.0-bluetooth-sample-parity.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    core_root = Path(__file__).resolve().parents[2]
    generated = collect(args.sdk_root.resolve(), core_root)
    validate(generated)
    output = args.output if args.output.is_absolute() else core_root / args.output
    encoded = json.dumps(generated, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != encoded:
            raise ValueError("Bluetooth sample parity drift")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(f"M31_PARITY samples={generated['counts']['samples']} variants={generated['counts']['variants']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"M31_PARITY_FAIL: {error}", file=sys.stderr)
        sys.exit(1)
