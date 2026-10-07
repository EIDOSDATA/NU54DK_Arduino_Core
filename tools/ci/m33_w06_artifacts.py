#!/usr/bin/env python3
"""! @brief M33-W06의 등록 campaign용 exact target artifact layout을 준비합니다. """

from __future__ import annotations

import argparse
import ast
from concurrent.futures import Future, ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Callable, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
LOCK_PATH = Path(__file__).with_name("ncs-3.4.0.lock.json")
REGISTRY_PATH = REPOSITORY / "tools/bluetooth/m33_regression.py"
BOARD_ROOT = REPOSITORY / "board_package/NU54DK_Zephyr_DTS"
BOARD_TARGET = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
PLATFORM_DIRECTORY = BOARD_TARGET.replace("/", "_")
TOOLCHAIN_DIRECTORY = "zephyr_gnu"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")
NATIVE_RECORD_FIELDS = (
    "core_revision",
    "core_source_sha256",
    "application_source_sha256",
    "board_revision",
    "board_source_sha256",
    "ncs_revision",
    "zephyr_revision",
    "board",
    "board_qualifiers",
    "toolchain_variant",
    "toolchain_path",
    "cxx_compiler",
)
PATH_TOKENS = (
    "hex-",
    "build-",
    "build-outdir",
    "signing-key",
    "imgtool",
    "config",
    "flash-record",
    "fixture",
    "prior-evidence",
    "fresh",
    "restored",
    "second-peer",
    "manifest",
)
RUNTIME_KINDS = {
    "file",
    "fixture",
    "flash_record",
    "runtime_evidence",
    "signing_key",
    "tool",
}
FORBIDDEN_BUILD_TOKENS = (
    "--erase",
    "--flash",
    "--mass-erase",
    "--recover",
    "--unlock",
    "nrfjprog",
    "pyocd",
)
IGNORED_OPTIONS = {
    "--development",
    "--discover-only",
    "--help",
    "--overwrite-evidence",
    "--reuse-build-root",
}
CAMPAIGN_OPTION_ALIASES = {
    "m31_cs_negative_missing_service": {"--spoof-image"},
    "m31_cs_negative_wrong_peer": {"--wrong-image"},
}
SUBCOMMANDS = {
    "m33_ecosystem": "run",
    "m33_diagnostics_build": "build",
}
M28_VARIANTS = {
    "m28_link": "link",
    "m28_periodic_past": "periodic",
    "m28_link_control": "control",
}
SCENARIO_OVERRIDES = {
    ("m28_adv_pawr_privacy", "peripheral-hex"): "nucode.m28.b2p",
    ("m28_adv_pawr_privacy", "central-hex"): "nucode.m28.b2c",
    ("m30_pair", "peripheral-image"): "nucode.m30.pair.kdf.p",
    ("m30_pair", "central-image"): "nucode.m30.pair.kdf.c",
    ("m30_oob", "peripheral-image"): "nucode.m30.oob.p",
    ("m30_oob", "central-image"): "nucode.m30.oob.c",
    ("m30_bond", "peripheral-image"): "nucode.m30.bond.p",
    ("m30_bond", "central-image"): "nucode.m30.bond.c",
    ("m30_profiles", "peripheral-image"): "nucode.m30.profile.p",
    ("m30_profiles", "central-image"): "nucode.m30.profile.c",
    ("m30_dfu", "peripheral-image"): "nucode.m30.dfu.peripheral",
    ("m30_dfu", "central-image"): "nucode.m30.dfu.central",
    ("m31_iso_bis", "hex-source"): "nucode.m31.iso_bis.source",
    ("m31_iso_bis", "hex-receiver"): "nucode.m31.iso_bis.receiver",
    ("m31_iso_combined", "hex-peer"): "nucode.m31.iso_combined.peer",
    ("m31_iso_combined", "hex-combined"): "nucode.m31.iso_combined.central",
    ("m31_iso_combined", "hex-receiver"): "nucode.m31.iso_bis.receiver",
    ("m32_standalone_radio", "hex-radio154-transmitter"): "nucode.m32.radio154_hil.transmitter",
    ("m32_standalone_radio", "hex-radio154-receiver"): "nucode.m32.radio154_hil.receiver",
    ("m32_standalone_radio", "hex-esb-ptx"): "nucode.m32.esb_hil.ptx",
    ("m32_standalone_radio", "hex-esb-prx"): "nucode.m32.esb_hil.prx",
    ("m32_coexistence", "hex-ble-154-dut"): "nucode.m32.coexistence_hil.ble_154.dut",
    ("m32_coexistence", "hex-ble-154-radio-peer"): "nucode.m32.coexistence_hil.ble_154.radio_peer",
    ("m32_coexistence", "hex-ble-154-ble-peer"): "nucode.m32.coexistence_hil.ble_154.ble_peer",
    ("m32_coexistence", "hex-ble-esb-dut"): "nucode.m32.coexistence_hil.ble_esb.dut",
    ("m32_coexistence", "hex-ble-esb-radio-peer"): "nucode.m32.coexistence_hil.ble_esb.radio_peer",
    ("m32_coexistence", "hex-ble-esb-ble-peer"): "nucode.m32.coexistence_hil.ble_esb.ble_peer",
    ("m32_coexistence", "hex-ble-mesh-dut"): "nucode.m32.coexistence_hil.ble_mesh.dut",
    ("m32_coexistence", "hex-ble-mesh-mesh-peer"): "nucode.m32.coexistence_hil.ble_mesh.mesh_peer",
    ("m32_coexistence", "hex-ble-mesh-ble-peer"): "nucode.m32.coexistence_hil.ble_mesh.ble_peer",
}
DIRECT_WEST_ARGUMENTS = {
    ("m33_beacons", "hex-advertiser"): ("tests/zephyr/m33_ble_beacon_hil", ("M33_BEACON_ROLE=advertiser",)),
    ("m33_beacons", "hex-observer"): ("tests/zephyr/m33_ble_beacon_hil", ("M33_BEACON_ROLE=observer",)),
    ("m33_profiles_standard", "hex-server"): ("tests/zephyr/m33_profile_hil", ("M33_PROFILE_ROLE=server",)),
    ("m33_profiles_standard", "hex-client"): ("tests/zephyr/m33_profile_hil", ("M33_PROFILE_ROLE=client",)),
    ("m33_profiles_standard", "hex-watcher"): ("tests/zephyr/m33_profile_hil", ("M33_PROFILE_ROLE=watcher",)),
    ("m33_profiles_native", "hex-server"): ("tests/zephyr/m33_profile_hil", ("M33_PROFILE_FAMILY=native", "M33_PROFILE_ROLE=server")),
    ("m33_profiles_native", "hex-client"): ("tests/zephyr/m33_profile_hil", ("M33_PROFILE_FAMILY=native", "M33_PROFILE_ROLE=client")),
    ("m33_profiles_native", "hex-watcher-idle"): ("tests/zephyr/m33_profile_hil", ("M33_PROFILE_ROLE=watcher",)),
    ("m33_profiles_native", "hex-second-peer"): ("tests/zephyr/m33_profile_hil", ("M33_PROFILE_FAMILY=native", "M33_PROFILE_ROLE=watcher")),
}
CS_QUIESCE_SOURCES = {
    "initiator": (
        "libraries/NUCODE_BLE_ChannelSounding/examples/RasInitiator/RasInitiator.ino",
        "tests/arduino-cli/p2_cs_initiator/p2_cs_initiator.ino",
    ),
    "reflector": (
        "libraries/NUCODE_BLE_ChannelSounding/examples/RasReflector/RasReflector.ino",
        "tests/arduino-cli/p2_cs_reflector/p2_cs_reflector.ino",
    ),
}
CS_QUIESCE_ACKS = {
    "initiator": "CS_QUIESCED role=initiator active_acl=0 pending=0 scan=0 cs=0",
    "reflector": "CS_QUIESCED role=reflector active_acl=0 pending=0 advertising=0 cs=0",
}
CS_DELTA_BUILD_SLOTS = (
    ("m31_cs_ras", "initiator-image",
     "libraries/NUCODE_BLE_ChannelSounding/examples/RasInitiator"),
    ("m31_cs_ras", "reflector-image",
     "libraries/NUCODE_BLE_ChannelSounding/examples/RasReflector"),
    ("m33_cs_acl_radio_risk", "hex-initiator",
     "tests/arduino-cli/p2_cs_initiator"),
    ("m33_cs_acl_radio_risk", "hex-reflector",
     "tests/arduino-cli/p2_cs_reflector"),
)
W06_ARDUINO_PROFILE_OVERRIDES = {
    "tests/arduino-cli/p2_cs_initiator": "adaptive",
    "tests/arduino-cli/p2_cs_reflector": "adaptive",
}
ARDUINO_REVISION_FAMILIES = {
    "NUCODE_BLE_ISO": "m31_iso_revisions",
    "NUCODE_BLE_Audio": "m31_audio_revisions",
    "NUCODE_BLE_DirectionFinding": "m31_df_revisions",
    "NUCODE_BLE_ChannelSounding": "m31_cs_revisions",
}
ARDUINO_REVISION_FEATURES = {
    "NUCODE_BLE_ISO": "nucode.ble.iso",
    "NUCODE_BLE_Audio": "nucode.ble.audio",
    "NUCODE_BLE_DirectionFinding": "nucode.ble.direction_finding",
    "NUCODE_BLE_ChannelSounding": "nucode.ble.channel_sounding",
}
SOAK_ARTIFACT_ID = "m33_regression_soak"
SOAK_APPLICATION = "tests/zephyr/m32_regression_soak_hil"
SOAK_RUNNER = "tests/hil/nu54dk/m32_regression_soak_run.py"
SOAK_ROLES = ("peripheral", "mixed", "central")
DEFAULT_BUILD_WORKERS = 2
MAX_BUILD_WORKERS = 4
MAX_BUILD_SHARDS = 16
CI_TWISTER_PARTITIONS_PER_GROUP = 4
SHORT_TWISTER_NAMES = "0123456789abcdefghijklmnopqrstuvwxyz"
ISOLATED_CACHE_ENVIRONMENTS = (
    "XDG_CACHE_HOME",
    "CCACHE_DIR",
    "PIP_CACHE_DIR",
    "PYTHONPYCACHEPREFIX",
    "TMP",
    "TEMP",
    "TMPDIR",
)


def soak_contract(repository: Path = REPOSITORY) -> dict[str, Any]:
    """! @brief 1800초 soak의 세 역할 image/config/build provenance를 비-campaign으로 고정합니다. """

    artifacts = []
    for role in SOAK_ROLES:
        scenario = f"nucode.m32.regression_soak_hil.{role}"
        recipe = {
            "builder": "run_zephyr_build.py",
            "application": SOAK_APPLICATION,
            "scenario": scenario,
            "jobs": 2,
        }
        artifacts.extend((
            {
                "name": f"hex-{role}",
                "kind": "target_image",
                "role": role,
                "binding": role,
                "required_for_dispatch": False,
                "recipe": recipe,
            },
            {
                "name": f"{role}-config",
                "kind": "configuration",
                "role": role,
                "binding": role,
                "required_for_dispatch": False,
                "recipe": None,
            },
            {
                "name": f"build-record-{role}",
                "kind": "build_record",
                "role": role,
                "binding": role,
                "required_for_dispatch": False,
                "recipe": None,
            },
        ))
    runner = repository / SOAK_RUNNER
    require(runner.is_file(), "soak runner가 없습니다")
    return {
        "id": SOAK_ARTIFACT_ID,
        "campaign": False,
        "application": SOAK_APPLICATION,
        "roles": list(SOAK_ROLES),
        "runner": {"path": SOAK_RUNNER, "sha256": file_sha256(runner)},
        "artifacts": artifacts,
    }


class ArtifactFailure(RuntimeError):
    """! @brief W06 artifact 계약 위반을 나타냅니다. """


def require(condition: bool, message: str) -> None:
    """! @brief 조건이 거짓이면 fail-closed 오류를 발생시킵니다. """

    if not condition:
        raise ArtifactFailure(message)


def file_sha256(path: Path) -> str:
    """! @brief 파일 byte의 SHA-256을 반환합니다. """

    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    """! @brief JSON 값을 고정 직렬화한 SHA-256을 반환합니다. """

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def cs_source_delta(repository: Path = REPOSITORY) -> dict[str, Any]:
    """! @brief W05 이후 CS quiesce 변경 네 source와 current-S 재빌드 분모를 고정합니다. """

    files: dict[str, str] = {}
    contracts = {}
    for role, paths in CS_QUIESCE_SOURCES.items():
        acknowledgement = CS_QUIESCE_ACKS[role]
        required = (
            "bool quiesceRequested = false;",
            "void requestQuiesce()",
            "void pollQuiesce()",
            "command == 'q'",
            acknowledgement,
            "!BLEConnection.connecting()",
        )
        for relative in paths:
            path = repository / relative
            require(path.is_file(), f"CS quiesce source가 없습니다: {relative}")
            source = path.read_text(encoding="utf-8")
            require(all(token in source for token in required),
                    f"CS quiesce mirror 계약이 동기화되지 않았습니다: {relative}")
            files[relative] = file_sha256(path)
        contract = {
            "command": "q",
            "acknowledgement": acknowledgement,
            "active_acl": 0,
            "pending": 0,
            "automatic_restart": False,
            "sources": list(paths),
        }
        contract["sha256"] = canonical_sha256(contract)
        contracts[role] = contract
    return {
        "kind": "m33_w06_current_source_delta",
        "reason": "cs_quiesce_after_w05_adb",
        "w05_adb": {
            "completed": "204/204",
            "scope": "baseline_before_cs_quiesce_delta",
            "current_source_status": "NOT_VERIFIED",
        },
        "current_source_build_required": True,
        "files": files,
        "contracts": contracts,
        "build_slots": [
            {"campaign_id": campaign_id, "name": name, "application": application}
            for campaign_id, name, application in CS_DELTA_BUILD_SLOTS
        ],
    }


def strict_json(path: Path, encoding: str = "utf-8") -> dict[str, Any]:
    """! @brief 중복 key와 비-object 최상위를 거부하며 JSON을 읽습니다. """

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in document, f"JSON key가 중복됩니다: {path}: {key}")
            document[key] = value
        return document

    try:
        result = json.loads(path.read_text(encoding=encoding), object_pairs_hook=object_pairs)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArtifactFailure(f"JSON을 읽지 못했습니다: {path}: {error}") from error
    require(isinstance(result, dict), f"JSON 최상위 값이 object가 아닙니다: {path}")
    return result


def git_output(repository: Path, *arguments: str) -> str:
    """! @brief 지정 Git checkout의 출력을 반환합니다. """

    try:
        result = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ArtifactFailure(f"Git 검사가 실패했습니다: {repository}: {error}") from error
    require(result.returncode == 0, f"Git 검사가 실패했습니다: {repository}: {result.stderr.strip()}")
    return result.stdout.strip()


def validate_source_lock(
    repository: Path,
    sdk_root: Path,
    toolchain_root: Path,
    expected_revision: str | None = None,
) -> dict[str, Any]:
    """! @brief clean Core와 NCS 3.4.0·toolchain·board lock을 함께 검증합니다. """

    repository = repository.resolve()
    sdk_root = sdk_root.resolve()
    toolchain_root = toolchain_root.resolve()
    lock = strict_json(repository / "tools/ci/ncs-3.4.0.lock.json")
    require(lock.get("schema_version") == 1, "NCS lock schema가 다릅니다")
    require(lock.get("ncs", {}).get("tag") == "v3.4.0", "NCS 3.4.0 lock이 아닙니다")
    revision = git_output(repository, "rev-parse", "HEAD").lower()
    require(REVISION.fullmatch(revision) is not None, "Core revision 형식이 잘못됐습니다")
    if expected_revision is not None:
        require(revision == expected_revision.lower(), "요청한 exact Core revision과 HEAD가 다릅니다")
    board_root = repository / "board_package/NU54DK_Zephyr_DTS"
    nrf_root = sdk_root / "nrf"
    zephyr_root = sdk_root / "zephyr"
    checkouts = {
        "Core": repository,
        "board": board_root,
        "nrf": nrf_root,
        "zephyr": zephyr_root,
    }
    for label, checkout in checkouts.items():
        dirty = git_output(
            checkout, "status", "--porcelain=v1", "--untracked-files=all"
        )
        require(not dirty, f"W06 artifact 준비에는 clean exact {label} source가 필요합니다")
    board_revision = git_output(board_root, "rev-parse", "HEAD").lower()
    ncs_revision = git_output(nrf_root, "rev-parse", "HEAD").lower()
    zephyr_revision = git_output(zephyr_root, "rev-parse", "HEAD").lower()
    require(board_revision == lock["board"]["revision"], "board submodule revision이 lock과 다릅니다")
    require(ncs_revision == lock["ncs"]["revision"], "NCS revision이 3.4.0 lock과 다릅니다")
    require(zephyr_revision == lock["zephyr"]["revision"], "Zephyr revision이 3.4.0 lock과 다릅니다")
    gitlink = git_output(repository, "ls-tree", "HEAD", "board_package/NU54DK_Zephyr_DTS")
    require(lock["board"]["revision"] in gitlink, "Core HEAD의 board gitlink가 lock과 다릅니다")
    bundle = str(lock["windows_toolchain"]["bundle_id"])
    normalized_toolchain = toolchain_root.as_posix().casefold()
    require(bundle.casefold() in normalized_toolchain, "Windows toolchain bundle path가 lock과 다릅니다")
    return {
        "source_revision": revision,
        "source_clean": True,
        "board_revision": board_revision,
        "board_clean": True,
        "ncs_version": "3.4.0",
        "ncs_revision": ncs_revision,
        "ncs_clean": True,
        "zephyr_revision": zephyr_revision,
        "zephyr_clean": True,
        "toolchain_bundle_id": bundle,
        "sdk_root": sdk_root.as_posix(),
        "toolchain_root": toolchain_root.as_posix(),
        "lock_sha256": file_sha256(repository / "tools/ci/ncs-3.4.0.lock.json"),
    }


def validate_source_binding(
    planned: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """! @brief 위치 필드만 재결합하고 exact source·SDK identity는 그대로 검증합니다. """

    location_keys = {"sdk_root", "toolchain_root"}
    require(set(planned) == set(current), "source identity 필드가 다릅니다")
    require(
        {key: value for key, value in planned.items() if key not in location_keys}
        == {key: value for key, value in current.items() if key not in location_keys},
        "재결합한 source/SDK/board/toolchain identity가 plan과 다릅니다",
    )
    binding = {
        "identity_sha256": canonical_sha256({
            key: value for key, value in planned.items()
            if key not in location_keys
        }),
        "planned": {
            "sdk_root": planned["sdk_root"],
            "toolchain_root": planned["toolchain_root"],
        },
        "current": {
            "sdk_root": current["sdk_root"],
            "toolchain_root": current["toolchain_root"],
        },
    }
    binding["binding_sha256"] = canonical_sha256(binding)
    return binding


def require_source_binding(
    document: dict[str, Any],
    planned: dict[str, Any],
    effective: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    """! @brief 문서가 검증된 effective source 위치 결합을 그대로 보존하는지 확인합니다. """

    expected = validate_source_binding(planned, effective)
    require(document.get("source_binding") == expected,
            f"{label} effective source binding이 다릅니다")
    return expected


def validate_recorded_source_binding(
    document: dict[str, Any],
    planned: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    """! @brief 이전 host가 기록한 위치 결합 자체의 exact identity와 hash를 검사합니다. """

    binding = document.get("source_binding")
    require(isinstance(binding, dict) and isinstance(binding.get("current"), dict),
            f"{label} source binding이 없습니다")
    require(set(binding["current"]) == {"sdk_root", "toolchain_root"},
            f"{label} current source 위치 필드가 잘못됐습니다")
    effective = dict(planned)
    effective.update(binding["current"])
    expected = validate_source_binding(planned, effective)
    require(binding == expected, f"{label} recorded source binding이 다릅니다")
    return expected


def parse_transfer_contract(path: Path) -> dict[str, Any]:
    """! @brief Actions artifact 전송 계약을 중복·혼합 없이 엄격하게 읽습니다. """

    path = path.resolve()
    try:
        text = path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as error:
        raise ArtifactFailure(f"transfer contract를 읽지 못했습니다: {path}") from error
    rows = {}
    for line in text.splitlines():
        require(line and "=" in line, "transfer contract line이 잘못됐습니다")
        key, value = line.split("=", 1)
        require(key and value and key not in rows,
                "transfer contract key/value가 없거나 중복됩니다")
        rows[key] = value
    required = {
        "SCHEMA", "RUN_ID", "RUN_ATTEMPT", "SHARD_COUNT",
        "AGGREGATE_ONLY_SUFFICIENT",
        "SHARD_0", "SHARD_1", "SHARD_2", "SHARD_3",
    }
    require(set(rows) == required
            and rows["SCHEMA"] == "m33-w06-transfer-v1"
            and rows["RUN_ID"].isdigit()
            and rows["RUN_ATTEMPT"].isdigit()
            and rows["SHARD_COUNT"] == "4"
            and rows["AGGREGATE_ONLY_SUFFICIENT"] == "0",
            "transfer contract schema/run/count가 잘못됐습니다")
    run_id = rows["RUN_ID"]
    run_attempt = rows["RUN_ATTEMPT"]
    artifacts = []
    for index in range(4):
        expected = (
            f"m33-w06-build-shard-{index}-{run_id}-attempt-{run_attempt}"
        )
        require(rows[f"SHARD_{index}"] == expected,
                f"transfer contract shard artifact가 다릅니다: {index}")
        artifacts.append(expected)
    return {
        "schema_version": 1,
        "kind": "m33_w06_transfer_contract",
        "run_id": run_id,
        "run_attempt": run_attempt,
        "shard_count": 4,
        "aggregate_only_sufficient": False,
        "artifacts": artifacts,
        "file_sha256": file_sha256(path),
    }


def validate_transfer_contract(document: dict[str, Any]) -> dict[str, Any]:
    """! @brief 직렬화된 transfer contract의 run·artifact 분모를 재검증합니다. """

    require(isinstance(document, dict) and set(document) == {
        "schema_version", "kind", "run_id", "shard_count",
        "run_attempt", "aggregate_only_sufficient", "artifacts", "file_sha256",
    }, "transfer contract document 형식이 잘못됐습니다")
    run_id = document.get("run_id")
    run_attempt = document.get("run_attempt")
    artifacts = document.get("artifacts")
    require(
        document.get("schema_version") == 1
        and document.get("kind") == "m33_w06_transfer_contract"
        and isinstance(run_id, str) and run_id.isdigit()
        and isinstance(run_attempt, str) and run_attempt.isdigit()
        and document.get("shard_count") == 4
        and document.get("aggregate_only_sufficient") is False
        and isinstance(artifacts, list)
        and artifacts == [
            f"m33-w06-build-shard-{index}-{run_id}-attempt-{run_attempt}"
            for index in range(4)
        ]
        and SHA256.fullmatch(str(document.get("file_sha256"))) is not None,
        "transfer contract document identity가 잘못됐습니다",
    )
    return document


def load_campaigns(repository: Path = REPOSITORY) -> dict[str, dict[str, Any]]:
    """! @brief 현재 source의 campaign registry를 읽습니다. """

    namespace = runpy.run_path(str(repository / "tools/bluetooth/m33_regression.py"))
    campaigns = namespace.get("CAMPAIGNS")
    require(isinstance(campaigns, dict) and campaigns, "M33 campaign registry가 비어 있습니다")
    return campaigns


def runner_options(path: Path, subcommand: str | None = None) -> set[str]:
    """! @brief runner source의 argparse long option을 정적으로 추출합니다. """

    require(path.is_file(), f"runner가 없습니다: {path}")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    loop_values: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.For) or not isinstance(node.target, ast.Name):
            continue
        values: Any = constants.get(node.iter.id) if isinstance(node.iter, ast.Name) else None
        if values is None:
            try:
                values = ast.literal_eval(node.iter)
            except (ValueError, TypeError):
                values = None
        if isinstance(values, (tuple, list)) and values and all(
            isinstance(value, str) for value in values
        ):
            loop_values[node.target.id] = tuple(values)
            for statement in node.body:
                if (
                    not isinstance(statement, ast.Assign)
                    or len(statement.targets) != 1
                    or not isinstance(statement.targets[0], ast.Name)
                    or not isinstance(statement.value, ast.Call)
                    or not isinstance(statement.value.func, ast.Attribute)
                    or statement.value.func.attr != "replace"
                    or not isinstance(statement.value.func.value, ast.Name)
                    or statement.value.func.value.id != node.target.id
                    or len(statement.value.args) != 2
                ):
                    continue
                try:
                    old = ast.literal_eval(statement.value.args[0])
                    new = ast.literal_eval(statement.value.args[1])
                except (ValueError, TypeError):
                    continue
                if isinstance(old, str) and isinstance(new, str):
                    loop_values[statement.targets[0].id] = tuple(
                        value.replace(old, new) for value in values
                    )
    parser_scopes: dict[str, str] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "add_parser"
            and node.value.args
            and isinstance(node.value.args[0], ast.Constant)
            and isinstance(node.value.args[0].value, str)
        ):
            parser_scopes[node.targets[0].id] = node.value.args[0].value
    scoped_options: dict[str | None, set[str]] = {None: set()}
    dynamic_scopes: set[str | None] = set()
    subcommands: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "add_argument":
            receiver = node.func.value
            scope = (
                parser_scopes.get(receiver.id)
                if isinstance(receiver, ast.Name)
                else None
            )
            discovered = scoped_options.setdefault(scope, set())
            for argument in node.args:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str) and argument.value.startswith("--"):
                    discovered.add(argument.value)
                elif isinstance(argument, ast.JoinedStr):
                    rendered = [""]
                    for part in argument.values:
                        if isinstance(part, ast.Constant) and isinstance(part.value, str):
                            rendered = [value + part.value for value in rendered]
                        elif isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name):
                            values = loop_values.get(
                                part.value.id,
                                constants.get(part.value.id.upper() + "S", ()),
                            )
                            if isinstance(values, (tuple, list)) and values and all(isinstance(value, str) for value in values):
                                rendered = [prefix + value for prefix in rendered for value in values]
                            else:
                                dynamic_scopes.add(scope)
                                rendered = []
                        else:
                            dynamic_scopes.add(scope)
                            rendered = []
                    discovered.update(value for value in rendered if value.startswith("--"))
        elif node.func.attr == "add_parser" and node.args and isinstance(node.args[0], ast.Constant):
            value = node.args[0].value
            if isinstance(value, str):
                subcommands.add(value)
    if subcommand is not None and not subcommands:
        subcommand = None
    if subcommand is not None:
        require(subcommand in subcommands, f"runner subcommand를 찾지 못했습니다: {path}: {subcommand}")
        options = set(scoped_options.get(None, set()))
        options.update(scoped_options.get(subcommand, set()))
        dynamic = None in dynamic_scopes or subcommand in dynamic_scopes
    else:
        options = set().union(*scoped_options.values())
        dynamic = bool(dynamic_scopes)
    if dynamic:
        if subcommand is not None:
            require(subcommand in subcommands, f"runner subcommand를 찾지 못했습니다: {path}: {subcommand}")
        command = [sys.executable, "-B", str(path)]
        if subcommand is not None:
            command.append(subcommand)
        command.append("--help")
        result = subprocess.run(
            command,
            cwd=str(REPOSITORY),
            capture_output=True,
            timeout=30,
            shell=False,
            check=False,
        )
        require(result.returncode == 0, f"runner help interface를 읽지 못했습니다: {path}")
        help_text = (result.stdout + result.stderr).decode("ascii", errors="ignore")
        discovered = re.findall(
            r"(?<![A-Za-z0-9_-])(--[a-z0-9][a-z0-9-]*)", help_text
        )
        options = set(discovered)
    return {option for option in options if "_" not in option}


def artifact_kind(name: str) -> str:
    """! @brief dispatcher artifact 이름을 준비 종류로 분류합니다. """

    if name == "hex" or name.startswith("hex-") or name.endswith("-hex") or name.endswith("-image"):
        return "target_image"
    if "build-record" in name:
        return "build_record"
    if "manifest" in name:
        return "build_record"
    if "build" in name and "info" not in name:
        return "build_tree"
    if "config" in name:
        return "configuration"
    if "flash-record" in name:
        return "flash_record"
    if "signing-key" in name:
        return "signing_key"
    if "imgtool" in name:
        return "tool"
    if "fixture" in name:
        return "fixture"
    if "evidence" in name or name in {"fresh", "restored", "second-peer"}:
        return "runtime_evidence"
    return "file"


def campaign_artifacts(
    campaign_id: str,
    definition: dict[str, Any],
    repository: Path = REPOSITORY,
) -> list[dict[str, Any]]:
    """! @brief dispatcher와 같은 규칙으로 campaign input artifact를 계산합니다. """

    options = runner_options(
        repository / definition["runner"],
        SUBCOMMANDS.get(campaign_id),
    )
    names: set[str] = set()
    roles = tuple(definition["roles"])
    for role in roles:
        cli_role = role.replace("_", "-")
        for option in (f"--hex-{cli_role}", f"--{cli_role}-hex", f"--{cli_role}-image"):
            if option in options:
                names.add(option[2:])
        for option in (f"--{cli_role}-config", f"--{cli_role}-flash-record"):
            if option in options:
                names.add(option[2:])
    if "--hex" in options:
        names.add("hex")
    populated = {f"--{name}" for name in names}
    ignored = IGNORED_OPTIONS | CAMPAIGN_OPTION_ALIASES.get(campaign_id, set())
    for option in sorted(options - populated - ignored):
        name = option[2:]
        if campaign_id in {"m33_profiles_standard", "m33_profiles_native"} and option in {
            "--build-record",
            "--second-peer-role",
            "--second-peer-build-record",
        }:
            continue
        if any(token in name for token in PATH_TOKENS) or name.endswith(("-hex", "-image")):
            names.add(name)
    if campaign_id in {"m33_profiles_standard", "m33_profiles_native"}:
        physical_roles = ("server", "client", "watcher")
        for role in physical_roles:
            cli_role = role.replace("_", "-")
            suffix = "-idle" if campaign_id == "m33_profiles_native" and role == "watcher" else ""
            names.add(f"hex-{cli_role}{suffix}")
            names.add(f"build-record-{cli_role}{suffix}")
        if campaign_id == "m33_profiles_native":
            names.add("hex-second-peer")
            names.add("build-record-second-peer")
    rows = []
    for name in sorted(names):
        kind = artifact_kind(name)
        exact_role = next(
            (
                role
                for role in roles
                if name in {
                    f"hex-{role.replace('_', '-')}",
                    f"{role.replace('_', '-')}-hex",
                    f"{role.replace('_', '-')}-image",
                    f"{role.replace('_', '-')}-config",
                    f"{role.replace('_', '-')}-flash-record",
                    f"build-record-{role.replace('_', '-')}",
                }
            ),
            None,
        )
        rows.append({
            "name": name,
            "kind": kind,
            "role": exact_role,
            "binding": re.sub(r"^(?:hex-|build-record-)", "", name).replace("-image", ""),
            "required_for_dispatch": True,
        })
    return rows


def testcase_scenarios(repository: Path = REPOSITORY) -> dict[str, str]:
    """! @brief 모든 testcase.yaml의 scenario와 application root를 유일하게 수집합니다. """

    scenarios: dict[str, str] = {}
    for path in sorted((repository / "tests/zephyr").glob("*/testcase.yaml")):
        for match in re.finditer(r"^  ([A-Za-z0-9_.-]+):\s*$", path.read_text(encoding="utf-8"), re.MULTILINE):
            scenario = match.group(1)
            require(scenario not in scenarios, f"test scenario가 중복됩니다: {scenario}")
            scenarios[scenario] = path.parent.relative_to(repository).as_posix()
    return scenarios


def scenario_for_artifact(
    campaign_id: str,
    artifact: dict[str, Any],
    definition: dict[str, Any],
    scenarios: dict[str, str],
) -> tuple[str, str] | None:
    """! @brief 역할·phase slot에 대응하는 exact Twister scenario를 결정합니다. """

    name = artifact["name"]
    override = SCENARIO_OVERRIDES.get((campaign_id, name))
    if override is not None:
        require(override in scenarios, f"고정 scenario가 없습니다: {campaign_id}:{name}:{override}")
        return scenarios[override], override
    if (campaign_id, name) in DIRECT_WEST_ARGUMENTS:
        return None
    applications = set(definition["applications"])
    candidates = [(scenario, application) for scenario, application in scenarios.items() if application in applications]
    if campaign_id in M28_VARIANTS:
        variant = M28_VARIANTS[campaign_id]
        role = artifact["role"]
        matches = [item for item in candidates if f".{variant}.{role}" in item[0]]
        require(len(matches) == 1, f"M28 scenario mapping이 모호합니다: {campaign_id}:{name}")
        return matches[0][1], matches[0][0]
    role = artifact["role"]
    binding = artifact["binding"].replace("-", "_")
    scored: list[tuple[int, str, str]] = []
    for scenario, application in candidates:
        normalized = scenario.replace("-", "_")
        score = 0
        if binding and binding in normalized:
            score += 100
        if role is not None and normalized.endswith("." + role):
            score += 80
        if role == "peripheral" and normalized.endswith(".p"):
            score += 70
        if role == "central" and normalized.endswith(".c"):
            score += 70
        tokens = [token for token in binding.split("_") if len(token) > 1]
        score += sum(5 for token in tokens if token in normalized)
        if score:
            scored.append((score, scenario, application))
    if not scored:
        return None
    best = max(value[0] for value in scored)
    matches = [value for value in scored if value[0] == best]
    require(len(matches) == 1, f"scenario mapping이 모호합니다: {campaign_id}:{name}")
    return matches[0][2], matches[0][1]


def arduino_application_for_artifact(
    artifact: dict[str, Any],
    applications: Sequence[str],
    repository: Path = REPOSITORY,
) -> str | None:
    """! @brief 역할 이름을 실제 Arduino sketch root에 유일하게 결합합니다. """

    sketches = [
        value
        for value in applications
        if (repository / value / (Path(value).name + ".ino")).is_file()
    ]
    if not sketches:
        return None
    if len(sketches) == 1:
        return sketches[0]
    binding = str(artifact["binding"]).replace("-", "_").casefold()
    role = str(artifact.get("role") or "").replace("-", "_").casefold()
    aliases = {
        "missing_service_peer": ("missingservice",),
        "spoof": ("missingservice",),
        "wrong_peer": ("wrongpeer",),
        "wrong": ("wrongpeer",),
    }
    tokens = {
        token.replace("_", "")
        for token in (binding, role)
        if token
    }
    for key, values in aliases.items():
        if key in {binding, role}:
            tokens.update(values)
    scored: list[tuple[int, str]] = []
    for application in sketches:
        name = Path(application).name.casefold().replace("_", "").replace("-", "")
        score = sum(100 for token in tokens if token and token in name)
        scored.append((score, application))
    best = max(score for score, _application in scored)
    matches = [application for score, application in scored if score == best and score > 0]
    if not matches:
        known_roles = {
            "client", "initiator", "missingservice", "reflector", "server",
            "wrongpeer",
        }
        incompatible = known_roles - tokens
        matches = [
            application
            for _score, application in scored
            if not any(
                token in Path(application).name.casefold().replace("_", "").replace("-", "")
                for token in incompatible
            )
        ]
    require(
        len(matches) == 1,
        f"Arduino 역할과 sketch mapping이 모호합니다: {artifact['name']}:{sketches}",
    )
    return matches[0]


def recipe_for_artifact(
    campaign_id: str,
    artifact: dict[str, Any],
    definition: dict[str, Any],
    scenarios: dict[str, str],
) -> dict[str, Any] | None:
    """! @brief 한 artifact를 만드는 실제 source/build selector를 반환합니다. """

    kind = artifact["kind"]
    name = artifact["name"]
    if campaign_id == "m33_diagnostics_dtm" and name == "build-manifest":
        return {
            "builder": "m33_diagnostics.py",
            "application": "templates/bluetooth/diagnostics/dtm",
            "routes": ["dtm_twowire", "dtm_hci"],
            "jobs": 2,
        }
    if kind == "target_image":
        if campaign_id == "m33_diagnostics_dtm" and name in {"twowire-hex", "h4-hex"}:
            return {
                "builder": "m33_diagnostics.py",
                "application": "templates/bluetooth/diagnostics/dtm",
                "transport": name.removesuffix("-hex"),
                "jobs": 2,
            }
        direct = DIRECT_WEST_ARGUMENTS.get((campaign_id, name))
        if direct is not None:
            return {
                "builder": "west_direct",
                "application": direct[0],
                "selectors": list(direct[1]),
                "jobs": 2,
            }
        mapped = scenario_for_artifact(campaign_id, artifact, definition, scenarios)
        if mapped is not None:
            return {
                "builder": "run_zephyr_build.py",
                "application": mapped[0],
                "scenario": mapped[1],
                "jobs": 2,
            }
        applications = definition["applications"]
        sketch = arduino_application_for_artifact(artifact, applications)
        if sketch is not None:
            source = (REPOSITORY / sketch / (Path(sketch).name + ".ino")).read_text(encoding="utf-8")
            match = re.search(r"feature set[^`\r\n]*`([a-z0-9_]+)`", source, re.IGNORECASE)
            return {
                "builder": "arduino-cli",
                "application": sketch,
                "profile": W06_ARDUINO_PROFILE_OVERRIDES.get(
                    sketch,
                    match.group(1) if match is not None else "ble",
                ),
                "jobs": 1,
            }
        return None
    if kind == "build_tree":
        application = definition["applications"][0] if definition["applications"] else None
        selectors: list[str] = []
        if campaign_id == "m33_diagnostics_build":
            return {
                "builder": "m33_diagnostics.py",
                "application": "templates/bluetooth/diagnostics",
                "routes": ["controller", "scan_request"],
                "jobs": 2,
            }
        if campaign_id == "m30_dfu":
            selector_by_name = {
                "peripheral-build-outdir": "nucode.m30.dfu.peripheral",
                "unconfirmed-build-outdir": "nucode.m30.power.unconfirmed",
                "central-build-outdir": "nucode.m30.dfu.central",
            }
            selectors = [selector_by_name[name]] if name in selector_by_name else []
        elif campaign_id == "m32_mesh_dfu":
            role = name.removeprefix("build-").replace("-", "_")
            selectors = [f"nucode.m32.mesh_dfu_hil.{role}"]
        else:
            selectors = [scenario for scenario, root in scenarios.items() if root == application]
        return {
            "builder": "run_zephyr_build.py",
            "application": application,
            "scenarios": sorted(selectors),
            "jobs": 2,
        }
    return None


def build_plan(identity: dict[str, Any], repository: Path = REPOSITORY) -> dict[str, Any]:
    """! @brief 현재 runner와 registry에서 artifact 계약을 생성합니다. """

    campaigns = load_campaigns(repository)
    scenarios = testcase_scenarios(repository)
    rows = []
    for campaign_id, definition in campaigns.items():
        artifacts = campaign_artifacts(campaign_id, definition, repository)
        for artifact in artifacts:
            artifact["recipe"] = recipe_for_artifact(campaign_id, artifact, definition, scenarios)
            if artifact["kind"] in {"target_image", "build_tree"}:
                require(artifact["recipe"] is not None, f"build recipe가 없습니다: {campaign_id}:{artifact['name']}")
        rows.append({
            "id": campaign_id,
            "runner": definition["runner"],
            "applications": definition["applications"],
            "roles": definition["roles"],
            "verification": definition["verification"],
            "artifacts": artifacts,
        })
    plan = {
        "schema_version": 1,
        "kind": "m33_w06_artifact_plan",
        "expected_campaign_count": len(campaigns),
        "source": identity,
        "policy": {
            "ncs_version": "3.4.0",
            "maximum_parallel_jobs": 2,
            "default_parallel_actions": DEFAULT_BUILD_WORKERS,
            "maximum_parallel_actions": MAX_BUILD_WORKERS,
            "flash": False,
            "mass_erase": False,
            "auto_unlock": False,
            "automatic_recover": False,
        },
        "source_delta": cs_source_delta(repository),
        "campaigns": rows,
        "soak": soak_contract(repository),
    }
    plan["contract_sha256"] = canonical_sha256(plan)
    validate_plan(plan, repository)
    return plan


def plan_artifacts(plan: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """! @brief plan의 artifact를 campaign/name key로 평탄화합니다. """

    result: dict[tuple[str, str], dict[str, Any]] = {}
    for campaign in plan["campaigns"]:
        for artifact in campaign["artifacts"]:
            key = (campaign["id"], artifact["name"])
            require(key not in result, f"artifact key가 중복됩니다: {key}")
            result[key] = artifact
    soak = plan.get("soak")
    if soak is not None:
        require(isinstance(soak, dict) and soak.get("id") == SOAK_ARTIFACT_ID,
                "non-campaign soak artifact contract가 잘못됐습니다")
        for artifact in soak["artifacts"]:
            key = (SOAK_ARTIFACT_ID, artifact["name"])
            require(key not in result, f"artifact key가 중복됩니다: {key}")
            result[key] = artifact
    return result


def build_artifacts(plan: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """! @brief target build가 직접 만들 수 있는 slot만 반환합니다. """

    return {
        key: artifact
        for key, artifact in plan_artifacts(plan).items()
        if artifact["kind"] not in RUNTIME_KINDS
    }


def runtime_artifacts(plan: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """! @brief 실기 실행 또는 외부 보안 입력이 필요한 slot만 반환합니다. """

    return {
        key: artifact
        for key, artifact in plan_artifacts(plan).items()
        if artifact["kind"] in RUNTIME_KINDS
    }


def recipe_key(recipe: dict[str, Any]) -> str:
    """! @brief build recipe의 고정 식별자를 반환합니다. """

    return canonical_sha256(recipe)


def suite_groups(repository: Path = REPOSITORY) -> dict[str, str]:
    """! @brief 기존 Zephyr build 도구의 scenario→group mapping을 읽습니다. """

    path = repository / "tools/ci/run_zephyr_build.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    groups: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "SUITE_GROUPS" for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        require(isinstance(value, dict), "SUITE_GROUPS 형식이 잘못됐습니다")
        for group, rows in value.items():
            for _directory, scenario in rows:
                require(scenario not in groups, f"scenario build group이 중복됩니다: {scenario}")
                groups[scenario] = group
    require(groups, "기존 Zephyr suite group을 읽지 못했습니다")
    return groups


def toolchain_python(toolchain_root: Path) -> Path:
    """! @brief 고정 toolchain bundle의 Python 실행 파일을 찾습니다. """

    toolchain_root = toolchain_bundle_root(toolchain_root)
    candidates = (
        toolchain_root / "opt/bin/python.exe",
        toolchain_root / "bin/python.exe",
        toolchain_root / "python.exe",
    )
    matches = [candidate.resolve() for candidate in candidates if candidate.is_file()]
    require(len(matches) == 1, f"toolchain Python을 유일하게 찾지 못했습니다: {toolchain_root}")
    return matches[0]


def toolchain_bundle_root(toolchain_root: Path) -> Path:
    """! @brief bundle root와 opt/zephyr-sdk 입력을 하나의 bundle root로 정규화합니다. """

    root = toolchain_root.resolve()
    if root.name.casefold() == "zephyr-sdk" and root.parent.name.casefold() == "opt":
        return root.parent.parent
    return root


def toolchain_environment(toolchain_root: Path, sdk_root: Path) -> dict[str, str]:
    """! @brief NCS toolchain bundle manifest에서 build 환경을 exact 재구성합니다. """

    root = toolchain_bundle_root(toolchain_root)
    manifest = strict_json(root / "environment.json", encoding="utf-8-sig")
    rows = manifest.get("env_vars")
    require(isinstance(rows, list), "toolchain environment env_vars가 배열이 아닙니다")
    environment: dict[str, str] = {}
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get("key"), str), "toolchain environment row가 잘못됐습니다")
        name = row["key"]
        if row.get("type") == "relative_paths":
            values = row.get("values")
            require(isinstance(values, list) and all(isinstance(value, str) for value in values), "toolchain relative path가 잘못됐습니다")
            paths = [str((root / value).resolve()) for value in values]
            if row.get("existing_value_treatment") == "prepend_to" and os.environ.get(name):
                paths.append(os.environ[name])
            environment[name] = os.pathsep.join(paths)
        elif row.get("type") == "string":
            require(isinstance(row.get("value"), str), "toolchain string 환경 값이 잘못됐습니다")
            environment[name] = row["value"]
        else:
            raise ArtifactFailure(f"지원하지 않는 toolchain environment type입니다: {row.get('type')}")
    environment.update({
        "CCACHE_DISABLE": "1",
        "CMAKE_BUILD_PARALLEL_LEVEL": "2",
        "PYTHONUTF8": "1",
        "ZEPHYR_BASE": str(sdk_root / "zephyr"),
        "ZEPHYR_SDK_INSTALL_DIR": str(root / "opt/zephyr-sdk"),
        "ZEPHYR_TOOLCHAIN_VARIANT": "zephyr",
    })
    return environment


def require_external_root(path: Path, identity: dict[str, Any], label: str) -> Path:
    """! @brief resolve된 root와 보호 tree의 동일·상위·하위 중첩을 거부합니다. """

    root = path.resolve()
    protected = (
        REPOSITORY.resolve(),
        (REPOSITORY / "board_package/NU54DK_Zephyr_DTS").resolve(),
        Path(identity["sdk_root"]).resolve(),
        toolchain_bundle_root(Path(identity["toolchain_root"])),
    )
    for source in protected:
        require(
            root != source and not root.is_relative_to(source) and
            not source.is_relative_to(root),
            f"{label} root는 source/SDK/toolchain 밖이어야 합니다: {root}",
        )
    return root


def require_external_fresh_root(path: Path, identity: dict[str, Any], label: str) -> Path:
    """! @brief 생성 root가 보호 tree 밖의 새 경로인지 검사합니다. """

    root = require_external_root(path, identity, label)
    require(not root.exists(), f"{label} root는 기존에 없어야 합니다: {root}")
    return root


def require_external_output(path: Path, identity: dict[str, Any], label: str) -> Path:
    """! @brief 새 output 파일의 resolve된 parent가 보호 tree 밖인지 검사합니다. """

    output = path.resolve()
    require_external_root(output.parent, identity, label)
    require(not output.exists(), f"{label} output은 기존에 없어야 합니다: {output}")
    return output


def checked_subprocess(
    command: Sequence[str],
    cwd: Path,
    timeout_seconds: int,
    executor: Callable[..., Any] = subprocess.run,
    environment: dict[str, str] | None = None,
) -> None:
    """! @brief 민감한 stdout/stderr를 게시하지 않고 subprocess 성공만 확인합니다. """

    process_environment = None
    if environment is not None:
        process_environment = dict(os.environ)
        process_environment.update(environment)
    try:
        result = executor(
            list(command),
            cwd=str(cwd),
            env=process_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ArtifactFailure(f"외부 준비 명령을 실행하지 못했습니다: {command[0]}") from error
    require(
        result.returncode == 0,
        f"외부 준비 명령이 실패했습니다: {command[0]}: exit={result.returncode}",
    )


def prepare_arduino_checkout(
    identity: dict[str, Any],
    output_root: Path,
    executor: Callable[..., Any] = subprocess.run,
    identity_reader: Callable[..., str] = git_output,
    planned_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """! @brief exact S와 board gitlink를 독립 Arduino hardware checkout으로 준비합니다. """

    root = require_external_fresh_root(output_root, identity, "Arduino")
    platform = root / "user/hardware/nucode/zephyr"
    platform.parent.mkdir(parents=True)
    commands = (
        (
            "git", "clone", "--no-hardlinks", "--no-checkout", "--quiet",
            str(REPOSITORY.resolve()), str(platform),
        ),
        (
            "git", "-C", str(platform), "checkout", "--detach", "--quiet",
            identity["source_revision"],
        ),
        (
            "git", "-C", str(platform), "config",
            "submodule.board_package/NU54DK_Zephyr_DTS.url", str(BOARD_ROOT.resolve()),
        ),
        (
            "git", "-c", "protocol.file.allow=always", "-C", str(platform),
            "submodule", "update", "--init", "--checkout", "--quiet",
            "board_package/NU54DK_Zephyr_DTS",
        ),
    )
    for command in commands:
        checked_subprocess(command, REPOSITORY, 300, executor)
    board = platform / "board_package/NU54DK_Zephyr_DTS"
    require(platform.is_dir() and board.is_dir(), "Arduino exact checkout 생성이 완료되지 않았습니다")
    require(not platform.is_symlink() and not board.is_symlink(), "Arduino checkout은 symlink일 수 없습니다")
    require(
        identity_reader(platform, "rev-parse", "HEAD").lower() == identity["source_revision"],
        "Arduino checkout이 exact S와 다릅니다",
    )
    require(
        identity_reader(board, "rev-parse", "HEAD").lower() == identity["board_revision"],
        "Arduino checkout의 board gitlink가 plan과 다릅니다",
    )
    require(
        not identity_reader(platform, "status", "--porcelain=v1", "--untracked-files=all")
        and not identity_reader(board, "status", "--porcelain=v1", "--untracked-files=all"),
        "Arduino exact checkout이 clean 상태가 아닙니다",
    )
    data_root = root / "data"
    downloads_root = root / "downloads"
    data_root.mkdir()
    downloads_root.mkdir()
    config = root / "arduino-cli.yaml"
    config.write_text(
        "directories:\n"
        f"  data: {data_root.as_posix()}\n"
        f"  downloads: {downloads_root.as_posix()}\n"
        f"  user: {(root / 'user').as_posix()}\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "kind": "m33_w06_arduino_checkout",
        "source_revision": identity["source_revision"],
        "source_clean": True,
        "board_revision": identity["board_revision"],
        "board_clean": True,
        "platform_is_symlink": False,
        "arduino_config_sha256": file_sha256(config),
        "source_binding": validate_source_binding(
            planned_identity or identity, identity
        ),
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    atomic_write_json(root / "m33-w06-arduino-checkout.json", manifest)
    return manifest


def board_uart_channels(raw_uid: str, ports: Sequence[Any]) -> dict[str, str]:
    """! @brief 같은 실제 DAPLink UID의 APP x.3과 AUX x.1을 중복 없이 결합합니다. """

    candidates = [port for port in ports
                  if (port.serial_number or "").casefold() == raw_uid.casefold()
                  and port.vid == 0x0D28 and port.pid == 0x0204]
    channels = {}
    for name, index in (("app", 3), ("aux", 1)):
        matches = [port for port in candidates
                   if (port.location or "").casefold().endswith(f":x.{index}")
                   or f"mi_{index:02d}" in (port.hwid or "").casefold()]
        require(len(matches) == 1 and isinstance(matches[0].device, str)
                and matches[0].device,
                f"현재 DAPLink {name} interface를 하나로 결정하지 못했습니다")
        channels[name] = matches[0].device
    require(len(candidates) == 2 and
            channels["app"].casefold() != channels["aux"].casefold(),
            "현재 DAPLink APP/AUX 연결이 중복되거나 불완전합니다")
    return channels


def discover_current_boards() -> list[dict[str, str]]:
    """! @brief Windows의 현재 DAPLink volume·VCOM을 읽고 UID는 hash로만 반환합니다. """

    module = runpy.run_path(
        str(REPOSITORY / "tests/hil/nu54dk/m31_w07_hil_campaign.py")
    )
    _serial, list_ports = module["import_pyserial"]()
    ports = list(list_ports.comports())
    boards = []
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        volume = Path(f"{letter}:/")
        details = module["read_details"](volume)
        if details is None:
            continue
        target = module["detail_value"](details, "Target Detect")
        idcode = (module["detail_value"](details, "SWD DP IDCODE") or "").casefold()
        voltage = module["detail_value"](details, "Target Voltage") or ""
        raw_uid = (module["detail_value"](details, "Unique ID") or "").casefold()
        if (
            target not in module["TARGETS"]
            or idcode != module["SWD_DP_IDCODE"]
            or "present" not in voltage
            or not raw_uid
        ):
            continue
        try:
            port = module["find_serial_port"](raw_uid, "auto", list_ports)
        except Exception as error:
            raise ArtifactFailure("현재 DAPLink VCOM 연결을 hash identity에 결합하지 못했습니다") from error
        channels = board_uart_channels(raw_uid, ports)
        require(channels["app"] == port, "현재 target UART와 APP interface가 다릅니다")
        boards.append({
            "probe_sha256": module["digest_uid"](raw_uid),
            "port": port,
            "volume": volume.as_posix(),
            **channels,
        })
    return boards


def current_board_inventory(
    plan: dict[str, Any],
    discoverer: Callable[[], list[dict[str, Any]]] = discover_current_boards,
    effective_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """! @brief 세 물리 slot과 전체 campaign 역할 재배치를 schema v2로 생성합니다. """

    identity = plan["source"]
    current = effective_source or identity
    validate_source_binding(identity, current)
    discovered = discoverer()
    require(isinstance(discovered, list) and len(discovered) == 3, "현재 연결된 NU54DK 세 대가 필요합니다")
    rows = sorted(discovered, key=lambda item: str(item.get("probe_sha256", "")))
    require(
        len({row.get("probe_sha256") for row in rows}) == 3
        and len({str(row.get("port", "")).casefold() for row in rows}) == 3,
        "현재 board probe/port 연결이 서로 달라야 합니다",
    )
    slots = []
    for index, row in enumerate(rows, 1):
        probe = row.get("probe_sha256")
        port = row.get("port")
        volume = row.get("volume")
        app = row.get("app")
        aux = row.get("aux")
        require(
            SHA256.fullmatch(str(probe)) is not None
            and isinstance(port, str) and port
            and isinstance(volume, str) and volume
            and isinstance(app, str) and app == port
            and isinstance(aux, str) and aux and aux.casefold() != app.casefold(),
            f"현재 board connection 정보가 불완전합니다: board_{index}",
        )
        slots.append({
            "slot": f"board_{index}",
            "probe_sha256": probe,
            "port": port,
            "volume": volume,
            "app": app,
            "aux": aux,
        })
    require(len({slot[key].casefold() for slot in slots for key in ("app", "aux")}) == 6,
            "현재 세 보드의 APP/AUX 포트는 모두 달라야 합니다")
    hil_directory = REPOSITORY / "tests/hil/nu54dk"
    if str(hil_directory) not in sys.path:
        sys.path.insert(0, str(hil_directory))
    regression = runpy.run_path(
        str(REPOSITORY / "tests/hil/nu54dk/m33_regression_run.py")
    )
    bindings = []
    for campaign in plan["campaigns"]:
        roles = tuple(regression["_preparation_roles"](campaign))
        require(len(roles) <= len(slots), f"campaign 동시 board 역할이 물리 slot보다 많습니다: {campaign['id']}")
        if roles:
            bindings.append({
                "campaign_id": campaign["id"],
                "roles": [
                    {"role": role, "slot": f"board_{index + 1}"}
                    for index, role in enumerate(roles)
                ],
            })
    document = {
        "schema_version": 2,
        "kind": "m33_board_inventory",
        "source_revision": identity["source_revision"],
        "source_clean": True,
        "physical_slots": slots,
        "campaign_bindings": bindings,
    }
    reject_raw_probe_identity(document, "board inventory")
    regression["_board_inventory"](
        document,
        identity["source_revision"],
        {"campaigns": plan["campaigns"]},
    )
    return document


def create_build_actions(
    plan: dict[str, Any],
    work_root: Path,
    sdk_root: Path,
    toolchain_root: Path,
    arduino_cli: Path,
    arduino_config: Path,
    fqbn_prefix: str,
    repository: Path = REPOSITORY,
    split_twister: bool = False,
) -> list[dict[str, Any]]:
    """! @brief plan recipe를 안전한 build-only subprocess action으로 변환합니다. """

    bundle_root = toolchain_bundle_root(toolchain_root)
    python = toolchain_python(bundle_root)
    zephyr_environment = toolchain_environment(bundle_root, sdk_root)
    artifacts = build_artifacts(plan)
    recipes = {
        recipe_key(artifact["recipe"]): artifact["recipe"]
        for artifact in artifacts.values()
        if artifact.get("recipe") is not None
    }
    actions: list[dict[str, Any]] = []
    groups = suite_groups(repository)
    selected: dict[str, set[str]] = {}
    for recipe in recipes.values():
        if recipe["builder"] != "run_zephyr_build.py":
            continue
        scenarios = [recipe["scenario"]] if "scenario" in recipe else recipe["scenarios"]
        for scenario in scenarios:
            require(scenario in groups, f"기존 Zephyr build group에 scenario가 없습니다: {scenario}")
            selected.setdefault(groups[scenario], set()).add(scenario)
    twister_units = []
    scenario_weights: dict[str, int] = {}
    for artifact in artifacts.values():
        recipe = artifact.get("recipe")
        if not isinstance(recipe, dict) or recipe.get("builder") != "run_zephyr_build.py":
            continue
        scenarios = [recipe["scenario"]] if "scenario" in recipe else recipe["scenarios"]
        for scenario in scenarios:
            scenario_weights[scenario] = scenario_weights.get(scenario, 0) + 1
    for group, scenarios in sorted(selected.items()):
        ordered = sorted(scenarios)
        if split_twister:
            parent = {scenario: scenario for scenario in ordered}

            def find(scenario: str) -> str:
                while parent[scenario] != scenario:
                    parent[scenario] = parent[parent[scenario]]
                    scenario = parent[scenario]
                return scenario

            for recipe in recipes.values():
                linked = recipe.get("scenarios")
                if recipe.get("builder") != "run_zephyr_build.py" or not linked:
                    continue
                linked = [scenario for scenario in linked if scenario in parent]
                for scenario in linked[1:]:
                    parent[find(scenario)] = find(linked[0])
            components: dict[str, list[str]] = {}
            for scenario in ordered:
                components.setdefault(find(scenario), []).append(scenario)
            component_rows = sorted(
                components.values(),
                key=lambda values: (
                    -sum(scenario_weights.get(value, 1) for value in values),
                    values[0],
                ),
            )
            partition_count = min(
                CI_TWISTER_PARTITIONS_PER_GROUP, len(component_rows)
            )
            partitions: list[list[str]] = [[] for _ in range(partition_count)]
            partition_loads = [0 for _ in range(partition_count)]
            for component in component_rows:
                partition = min(
                    range(partition_count),
                    key=lambda value: (partition_loads[value], value),
                )
                partitions[partition].extend(component)
                partition_loads[partition] += sum(
                    scenario_weights.get(value, 1) for value in component
                )
            units = sorted(
                (sorted(values) for values in partitions if values),
                key=lambda values: values[0],
            )
        else:
            units = [ordered]
        for scenarios_in_action in units:
            suffix = ("-" + canonical_sha256(scenarios_in_action)[:12]
                      if split_twister else "")
            twister_units.append((group, scenarios_in_action,
                                  f"twister-{group}{suffix}"))
    require(
        len(twister_units) <= len(SHORT_TWISTER_NAMES),
        "Twister short output 이름이 부족합니다",
    )
    short_root = Path(work_root).resolve().anchor
    require(short_root, "Twister short output drive를 찾지 못했습니다")
    for short_index, (group, scenarios, action_id) in enumerate(twister_units):
        output = work_root / "builds" / action_id
        scratch_output = Path(short_root) / SHORT_TWISTER_NAMES[short_index]
        command = [
            str(python), "-B",
            str(repository / "tools/ci/run_zephyr_build.py"),
            "--workspace", str(sdk_root),
            "--outdir", str(scratch_output),
            "--group", group,
            "--jobs", "2",
        ]
        for scenario in scenarios:
            command.extend(("--suite", scenario))
        actions.append({
            "id": action_id,
            "kind": "twister",
            "command": command,
            "cwd": str(repository),
            "output": str(output),
            "scratch_output": str(scratch_output),
            "precreate_output": False,
            "environment": dict(zephyr_environment),
            "group": group,
            "scenarios": scenarios,
            "jobs": 2,
        })
    for key, recipe in sorted(recipes.items()):
        builder = recipe["builder"]
        if builder == "run_zephyr_build.py":
            continue
        if builder == "west_direct":
            output = work_root / "builds" / f"west-{key[:12]}"
            profile = recipe["application"] == "tests/zephyr/m33_profile_hil"
            command = [
                str(python), "-B", "-I", "-m", "west", "build",
                "--sysbuild" if profile else "--no-sysbuild",
                "-p", "always", "-b", BOARD_TARGET,
                "-d", str(output), str(repository / recipe["application"]), "--",
                f"-DBOARD_ROOT={(repository / 'board_package/NU54DK_Zephyr_DTS').as_posix()}",
                f"-DEXTRA_ZEPHYR_MODULES={repository.as_posix()}",
                "-DUSE_CCACHE=0",
            ]
            command.extend(f"-D{selector}" for selector in recipe["selectors"])
            actions.append({
                "id": f"west-{key[:12]}",
                "kind": "west_direct",
                "command": command,
                "cwd": str(repository),
                "output": str(output),
                "precreate_output": False,
                "environment": dict(zephyr_environment),
                "recipe_key": key,
                "jobs": 2,
            })
        elif builder == "arduino-cli":
            output = work_root / "builds" / f"arduino-{key[:12]}"
            command = [
                str(arduino_cli), "compile", "--config-file", str(arduino_config),
                "--fqbn", f"{fqbn_prefix}:feature_set={recipe['profile']}",
                "--libraries", str(repository / "tests/arduino-cli"),
                "--build-path", str(output), str(repository / recipe["application"]),
            ]
            actions.append({
                "id": f"arduino-{key[:12]}",
                "kind": "arduino-cli",
                "command": command,
                "cwd": str(repository),
                "output": str(output),
                "precreate_output": True,
                "environment": {"CMAKE_BUILD_PARALLEL_LEVEL": "1"},
                "recipe_key": key,
                "jobs": 1,
            })
        elif builder == "m33_diagnostics.py":
            continue
        else:
            raise ArtifactFailure(f"지원하지 않는 build recipe입니다: {builder}")
    diagnostics = repository / "tools/bluetooth/m33_diagnostics.py"
    dtm_routes = sorted({
        "dtm_twowire" if recipe.get("transport") == "twowire" else "dtm_hci"
        for recipe in recipes.values()
        if recipe["builder"] == "m33_diagnostics.py" and "transport" in recipe
    })
    if dtm_routes:
        output = work_root / "builds/diagnostics-dtm"
        actions.append({
            "id": "diagnostics-dtm",
            "kind": "diagnostics",
            "command": [
                str(python), "-B", str(diagnostics), "build",
                "--sdk", str(sdk_root), "--toolchain", str(bundle_root),
                "--output", str(output), "--jobs", "2", "--routes", *dtm_routes,
            ],
            "cwd": str(repository),
            "output": str(output),
            "precreate_output": False,
            "environment": {},
            "routes": dtm_routes,
            "jobs": 2,
        })
    build_routes = sorted({
        route
        for recipe in recipes.values()
        if recipe["builder"] == "m33_diagnostics.py"
        and recipe.get("application") == "templates/bluetooth/diagnostics"
        and "routes" in recipe
        for route in recipe["routes"]
    })
    if build_routes:
        output = work_root / "builds/diagnostics-build"
        actions.append({
            "id": "diagnostics-build",
            "kind": "diagnostics",
            "command": [
                str(python), "-B", str(diagnostics), "build",
                "--sdk", str(sdk_root), "--toolchain", str(bundle_root),
                "--output", str(output), "--jobs", "2", "--routes", *build_routes,
            ],
            "cwd": str(repository),
            "output": str(output),
            "precreate_output": False,
            "environment": {},
            "routes": build_routes,
            "jobs": 2,
        })
    profile_records: set[tuple[str, str, str]] = set()
    for (campaign_id, _name), artifact in artifacts.items():
        if campaign_id not in {"m33_profiles_standard", "m33_profiles_native"}:
            continue
        recipe = artifact.get("recipe")
        if artifact["kind"] != "target_image" or not isinstance(recipe, dict):
            continue
        selectors = dict(selector.split("=", 1) for selector in recipe["selectors"])
        profile_records.add((
            selectors.get("M33_PROFILE_FAMILY", "standard"),
            selectors["M33_PROFILE_ROLE"],
            recipe_key(recipe),
        ))
    action_by_recipe = {
        action.get("recipe_key"): action
        for action in actions
        if action.get("recipe_key") is not None
    }
    for family, role, key in sorted(profile_records):
        require(key in action_by_recipe, f"profile west build action이 없습니다: {family}:{role}")
        output = work_root / "records" / f"profile-{family}-{role}"
        build = Path(action_by_recipe[key]["output"])
        actions.append({
            "id": f"profile-record-{family}-{role}",
            "kind": "profile_record",
            "command": [
                str(python), "-B", str(repository / "tests/hil/nu54dk/m33_profile_build_record.py"),
                "--family", family, "--role", role,
                "--build-dir", str(build), "--output-dir", str(output),
            ],
            "cwd": str(repository),
            "output": str(output),
            "precreate_output": False,
            "environment": {},
            "profile": {"family": family, "role": role, "recipe_key": key},
            "depends_on": [action_by_recipe[key]["id"]],
            "jobs": 1,
        })
    for ordinal, action in enumerate(actions, start=1):
        action["plan_ordinal"] = ordinal
        action.setdefault("depends_on", [])
        cache_root = work_root / "caches" / action["id"]
        action["cache_root"] = str(cache_root)
        cache_environment = {
            "XDG_CACHE_HOME": str(cache_root / "xdg"),
            "CCACHE_DIR": str(cache_root / "ccache"),
            "PIP_CACHE_DIR": str(cache_root / "pip"),
            "PYTHONPYCACHEPREFIX": str(cache_root / "pycache"),
            "TMP": str(cache_root / "tmp"),
            "TEMP": str(cache_root / "tmp"),
            "TMPDIR": str(cache_root / "tmp"),
        }
        action["environment"] = {
            **action.get("environment", {}),
            **cache_environment,
        }
        if action["kind"] == "arduino-cli":
            application = action["command"].pop()
            action["command"].extend((
                "--build-cache-path",
                str(cache_root / "arduino-build"),
                application,
            ))
            action["environment"]["ARDUINO_DIRECTORIES_DOWNLOADS"] = str(
                cache_root / "arduino-downloads"
            )
            action["environment"]["NUCODE_BUILD_CACHE_ROOT"] = str(
                cache_root / "builder"
            )
    require(all(1 <= int(action["jobs"]) <= 2 for action in actions), "build action jobs가 2를 넘습니다")
    require(len({action["id"] for action in actions}) == len(actions), "build action id가 중복됩니다")
    return actions


def create_shard_build_actions(*arguments: Any, **keywords: Any) -> list[dict[str, Any]]:
    """! @brief CI shard용으로 multi-scenario 의존 단위만 유지해 Twister action을 분할합니다. """

    require("split_twister" not in keywords,
            "shard action factory의 split_twister override를 허용하지 않습니다")
    return create_build_actions(*arguments, **keywords, split_twister=True)


def build_slot_action_owners(
    plan: dict[str, Any],
    actions: Sequence[dict[str, Any]],
) -> dict[tuple[str, str], str]:
    """! @brief 각 build slot을 실제 byte를 최종 생성하는 action 하나에 결합합니다. """

    artifacts = build_artifacts(plan)
    recipe_actions = {
        action.get("recipe_key"): action["id"]
        for action in actions
        if action.get("recipe_key") is not None
    }
    scenario_actions = {
        scenario: action["id"]
        for action in actions if action["kind"] == "twister"
        for scenario in action["scenarios"]
    }
    profile_actions = {
        (action["profile"]["family"], action["profile"]["role"]): action["id"]
        for action in actions if action["kind"] == "profile_record"
    }
    action_ids = {action["id"] for action in actions}
    owners: dict[tuple[str, str], str] = {}
    for key, artifact in artifacts.items():
        recipe = artifact.get("recipe")
        if not isinstance(recipe, dict):
            continue
        builder = recipe["builder"]
        if builder == "run_zephyr_build.py":
            scenarios = [recipe["scenario"]] if "scenario" in recipe else recipe["scenarios"]
            candidates = {scenario_actions.get(scenario) for scenario in scenarios}
            require(None not in candidates and len(candidates) == 1,
                    f"Twister slot action이 유일하지 않습니다: {key}")
            owner = next(iter(candidates))
        elif builder == "west_direct":
            if key[0] in {"m33_profiles_standard", "m33_profiles_native"}:
                selectors = dict(value.split("=", 1) for value in recipe["selectors"])
                profile = (
                    selectors.get("M33_PROFILE_FAMILY", "standard"),
                    selectors["M33_PROFILE_ROLE"],
                )
                owner = profile_actions.get(profile)
            else:
                owner = recipe_actions.get(recipe_key(recipe))
        elif builder == "arduino-cli":
            owner = recipe_actions.get(recipe_key(recipe))
        elif builder == "m33_diagnostics.py":
            owner = ("diagnostics-dtm"
                     if key[0] == "m33_diagnostics_dtm"
                     else "diagnostics-build")
        else:
            raise ArtifactFailure(f"build slot action builder를 지원하지 않습니다: {builder}")
        require(owner in action_ids, f"build slot action이 없습니다: {key}:{owner}")
        owners[key] = str(owner)
    for key, artifact in artifacts.items():
        if key in owners:
            continue
        campaign_id, name = key
        if artifact["kind"] == "build_record" and campaign_id == SOAK_ARTIFACT_ID:
            source_key = (campaign_id, f"hex-{name.removeprefix('build-record-')}")
        elif artifact["kind"] == "build_record" and campaign_id.startswith("m33_profiles_"):
            source_key = (campaign_id, f"hex-{name.removeprefix('build-record-')}")
        elif artifact["kind"] == "build_record" and campaign_id == "m33_diagnostics_dtm":
            owners[key] = "diagnostics-dtm"
            continue
        elif artifact["kind"] == "configuration":
            binding = name.removesuffix("-config")
            candidates = [
                image_key
                for image_key, image in artifacts.items()
                if image_key[0] == campaign_id and
                image["kind"] == "target_image" and
                image["binding"].replace("-image", "") == binding
            ]
            require(len(candidates) == 1,
                    f"configuration slot owner가 모호합니다: {key}:{candidates}")
            source_key = candidates[0]
        else:
            raise ArtifactFailure(f"build slot action owner가 없습니다: {key}")
        require(source_key in owners,
                f"derived build slot source owner가 없습니다: {key}:{source_key}")
        owners[key] = owners[source_key]
    require(set(owners) == set(artifacts), "build slot action owner가 부분 상태입니다")
    return owners


def partial_build_plan(
    plan: dict[str, Any],
    slot_keys: set[tuple[str, str]],
) -> dict[str, Any]:
    """! @brief shard가 소유한 slot만 포함하되 원본 source/plan hash를 유지합니다. """

    campaigns = []
    for campaign in plan["campaigns"]:
        artifacts = [
            artifact for artifact in campaign["artifacts"]
            if (campaign["id"], artifact["name"]) in slot_keys
        ]
        if artifacts:
            row = dict(campaign)
            row["artifacts"] = artifacts
            campaigns.append(row)
    result = {
        "source": plan["source"],
        "contract_sha256": plan["contract_sha256"],
        "campaigns": campaigns,
    }
    soak = plan.get("soak")
    if isinstance(soak, dict):
        artifacts = [
            artifact for artifact in soak["artifacts"]
            if (SOAK_ARTIFACT_ID, artifact["name"]) in slot_keys
        ]
        if artifacts:
            result["soak"] = {**soak, "artifacts": artifacts}
    require(set(build_artifacts(result)) == slot_keys,
            "partial build plan slot denominator가 다릅니다")
    return result


def create_build_shard_plan(
    plan: dict[str, Any],
    actions: Sequence[dict[str, Any]],
    shard_count: int,
) -> dict[str, Any]:
    """! @brief 의존 action을 분리하지 않는 결정적 load-balanced shard 계약을 만듭니다. """

    require(type(shard_count) is int and 1 <= shard_count <= MAX_BUILD_SHARDS,
            f"shard-count는 1~{MAX_BUILD_SHARDS}여야 합니다")
    identifiers = [action["id"] for action in actions]
    require(len(set(identifiers)) == len(identifiers), "shard action id가 중복됩니다")
    parent = {identifier: identifier for identifier in identifiers}

    def find(identifier: str) -> str:
        while parent[identifier] != identifier:
            parent[identifier] = parent[parent[identifier]]
            identifier = parent[identifier]
        return identifier

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for action in actions:
        for dependency in action["depends_on"]:
            require(dependency in parent, "shard action dependency가 없습니다")
            union(action["id"], dependency)
    components: dict[str, list[dict[str, Any]]] = {}
    for action in actions:
        components.setdefault(find(action["id"]), []).append(action)
    owners = build_slot_action_owners(plan, actions)
    owned_slot_counts = {
        identifier: sum(1 for owner in owners.values() if owner == identifier)
        for identifier in identifiers
    }

    def action_weight(action: dict[str, Any]) -> int:
        """! @brief action 내부 병렬도와 생성 slot 수를 함께 반영한 shard 추정 부하입니다. """

        return int(action["jobs"]) * max(1, owned_slot_counts[action["id"]])

    ordered_components = sorted(
        components.values(),
        key=lambda rows: (
            -sum(action_weight(row) for row in rows),
            min(int(row["plan_ordinal"]) for row in rows),
        ),
    )
    shard_loads = [0 for _ in range(shard_count)]
    shard_by_action = {}
    for rows in ordered_components:
        shard = min(range(shard_count), key=lambda value: (shard_loads[value], value))
        for action in rows:
            shard_by_action[action["id"]] = shard
        shard_loads[shard] += sum(action_weight(row) for row in rows)
    require(all(load > 0 for load in shard_loads),
            "shard-count가 dependency component 수보다 큽니다")
    artifacts = build_artifacts(plan)
    assignments = []
    for action in actions:
        slots = []
        for key in sorted(key for key, owner in owners.items()
                          if owner == action["id"]):
            artifact = artifacts[key]
            slots.append({
                "campaign_id": key[0],
                "name": key[1],
                "kind": artifact["kind"],
                "recipe_sha256": canonical_sha256(artifact.get("recipe")),
            })
        assignments.append({
            "ordinal": action["plan_ordinal"],
            "id": action["id"],
            "kind": action["kind"],
            "depends_on": action["depends_on"],
            "jobs": action["jobs"],
            "shard": shard_by_action[action["id"]],
            "slots": slots,
        })
    document = {
        "schema_version": 1,
        "kind": "m33_w06_build_shard_plan",
        "plan_sha256": plan["contract_sha256"],
        "source": plan["source"],
        "shard_count": shard_count,
        "action_count": len(actions),
        "build_slot_count": len(artifacts),
        "runtime_slot_count": len(runtime_artifacts(plan)),
        "total_slot_count": len(plan_artifacts(plan)),
        "shard_loads": shard_loads,
        "assignments": assignments,
    }
    document["contract_sha256"] = canonical_sha256(document)
    return document


def validate_build_shard_plan(
    document: dict[str, Any],
    plan: dict[str, Any],
    actions: Sequence[dict[str, Any]],
    shard_count: int,
) -> None:
    """! @brief shard plan이 current recipe/action/source에서 그대로 파생됐는지 검사합니다. """

    require(document == create_build_shard_plan(plan, actions, shard_count),
            "build shard plan이 current exact action/recipe와 다릅니다")


def validate_plan(plan: dict[str, Any], repository: Path = REPOSITORY) -> None:
    """! @brief plan이 현재 runner registry와 안전 정책을 정확히 반영하는지 검증합니다. """

    require(plan.get("schema_version") == 1 and plan.get("kind") == "m33_w06_artifact_plan", "artifact plan schema가 다릅니다")
    policy = plan.get("policy")
    require(isinstance(policy, dict), "artifact plan policy가 없습니다")
    require(
        policy == {
            "ncs_version": "3.4.0",
            "maximum_parallel_jobs": 2,
            "default_parallel_actions": DEFAULT_BUILD_WORKERS,
            "maximum_parallel_actions": MAX_BUILD_WORKERS,
            "flash": False,
            "mass_erase": False,
            "auto_unlock": False,
            "automatic_recover": False,
        },
        "artifact plan 안전 정책이 다릅니다",
    )
    require(plan.get("source_delta") == cs_source_delta(repository),
            "W06 current-S source delta/hash 계약이 다릅니다")
    campaigns = load_campaigns(repository)
    actual_rows = plan.get("campaigns")
    require(
        isinstance(actual_rows, list)
        and plan.get("expected_campaign_count") == len(campaigns)
        and len(actual_rows) == len(campaigns),
        "artifact plan campaign 수가 다릅니다",
    )
    require({row.get("id") for row in actual_rows} == set(campaigns), "artifact plan campaign 집합이 다릅니다")
    scenarios = testcase_scenarios(repository)
    expected_soak = soak_contract(repository)
    require(plan.get("soak") == expected_soak,
            "non-campaign soak artifact contract가 drift했습니다")
    require(all(
        artifact["recipe"] is None or
        artifact["recipe"].get("scenario") in scenarios
        for artifact in expected_soak["artifacts"]
    ), "soak scenario가 current testcase 원장에 없습니다")
    for row in actual_rows:
        expected = campaign_artifacts(row["id"], campaigns[row["id"]], repository)
        for artifact in expected:
            artifact["recipe"] = recipe_for_artifact(
                row["id"],
                artifact,
                campaigns[row["id"]],
                scenarios,
            )
        actual = row.get("artifacts")
        require(isinstance(actual, list), f"artifact 배열이 없습니다: {row['id']}")
        require(
            [
                (
                    item.get("name"), item.get("kind"), item.get("role"),
                    item.get("binding"), item.get("required_for_dispatch"), item.get("recipe"),
                )
                for item in actual
            ]
            == [
                (
                    item["name"], item["kind"], item["role"],
                    item["binding"], item["required_for_dispatch"], item["recipe"],
                )
                for item in expected
            ],
            f"runner artifact contract가 drift했습니다: {row['id']}",
        )
        for artifact in actual:
            recipe = artifact.get("recipe")
            if recipe is not None:
                require(isinstance(recipe.get("jobs"), int) and 1 <= recipe["jobs"] <= 2, "artifact build jobs가 2를 넘습니다")
    artifacts_by_key = plan_artifacts(plan)
    for campaign_id, name, application in CS_DELTA_BUILD_SLOTS:
        artifact = artifacts_by_key.get((campaign_id, name))
        require(
            isinstance(artifact, dict)
            and artifact.get("kind") == "target_image"
            and artifact.get("required_for_dispatch") is True
            and artifact.get("recipe", {}).get("builder") == "arduino-cli"
            and artifact.get("recipe", {}).get("application") == application,
            f"CS current-S exact build slot이 다릅니다: {campaign_id}:{name}",
        )
    expected_digest = plan.get("contract_sha256")
    clone = dict(plan)
    clone.pop("contract_sha256", None)
    require(SHA256.fullmatch(str(expected_digest)) is not None and canonical_sha256(clone) == expected_digest, "artifact plan hash가 다릅니다")


def validate_build_command(action: dict[str, Any]) -> None:
    """! @brief build action이 flash·erase·unlock·recover를 호출하지 않는지 검사합니다. """

    command = action.get("command")
    require(isinstance(command, list) and command, f"build command가 없습니다: {action.get('id')}")
    require(all(isinstance(token, str) and token for token in command), "build command token 형식이 잘못됐습니다")
    lowered = [token.casefold() for token in command]
    for forbidden in FORBIDDEN_BUILD_TOKENS:
        if forbidden.startswith("--"):
            present = any(token == forbidden or token.startswith(forbidden + "=") for token in lowered)
        else:
            present = any(Path(token).stem.casefold() == forbidden for token in lowered)
        require(
            not present,
            f"build-only action에 금지 명령이 있습니다: {action.get('id')}:{forbidden}",
        )
    require(1 <= int(action.get("jobs", 0)) <= 2, "build action jobs가 2를 넘습니다")


def validate_build_action_graph(
    actions: Sequence[dict[str, Any]],
    work_root: Path,
    max_workers: int,
) -> None:
    """! @brief 병렬 action의 output/cache 격리와 의존 DAG를 실행 전에 검사합니다. """

    require(type(max_workers) is int and
            1 <= max_workers <= MAX_BUILD_WORKERS,
            f"max-workers는 1~{MAX_BUILD_WORKERS}여야 합니다")
    require(actions, "build action이 없습니다")
    identifiers = [action.get("id") for action in actions]
    require(all(isinstance(identifier, str) and identifier
                for identifier in identifiers) and
            len(set(identifiers)) == len(identifiers),
            "build action id가 없거나 중복됩니다")
    work_root = work_root.resolve()
    cache_parent = (work_root / "caches").resolve()
    outputs: list[Path] = []
    caches: list[Path] = []
    scratch_outputs: list[Path] = []
    identifier_set = set(identifiers)
    for action in actions:
        validate_build_command(action)
        output = Path(action.get("output", "")).resolve()
        cache_root = Path(action.get("cache_root", "")).resolve()
        require(output.is_relative_to(work_root) and output != work_root,
                f"build output이 work root 밖입니다: {action['id']}")
        require(cache_root.is_relative_to(cache_parent) and
                cache_root != cache_parent,
                f"build cache가 action별 cache root 밖입니다: {action['id']}")
        scratch_value = action.get("scratch_output")
        if scratch_value is not None:
            scratch = Path(str(scratch_value)).resolve()
            command = action["command"]
            require(
                action["kind"] == "twister"
                and scratch.parent == Path(scratch.anchor)
                and scratch.drive.casefold() == work_root.drive.casefold()
                and len(str(scratch)) <= 4
                and len(scratch.name) == 1
                and scratch.name in SHORT_TWISTER_NAMES
                and "--outdir" in command
                and Path(command[command.index("--outdir") + 1]).resolve()
                == scratch,
                f"Twister short output 계약이 잘못됐습니다: {action['id']}",
            )
            scratch_outputs.append(scratch)
        dependencies = action.get("depends_on")
        require(isinstance(dependencies, list) and
                len(dependencies) == len(set(dependencies)) and
                all(isinstance(value, str) and value in identifier_set and
                    value != action["id"] for value in dependencies),
                f"build action 의존성이 잘못됐습니다: {action['id']}")
        environment = action.get("environment")
        require(isinstance(environment, dict),
                f"build action environment가 없습니다: {action['id']}")
        for key in ISOLATED_CACHE_ENVIRONMENTS:
            value = environment.get(key)
            require(isinstance(value, str) and
                    Path(value).resolve().is_relative_to(cache_root),
                    f"build cache environment가 격리되지 않았습니다: {action['id']}:{key}")
        if action["kind"] == "arduino-cli":
            command = action["command"]
            require("--build-cache-path" in command,
                    f"Arduino build cache가 없습니다: {action['id']}")
            index = command.index("--build-cache-path")
            require(index + 1 < len(command) and
                    Path(command[index + 1]).resolve().is_relative_to(cache_root) and
                    Path(environment.get("ARDUINO_DIRECTORIES_DOWNLOADS", ""))
                    .resolve().is_relative_to(cache_root) and
                    Path(environment.get("NUCODE_BUILD_CACHE_ROOT", ""))
                    .resolve().is_relative_to(cache_root),
                    f"Arduino cache가 action별로 격리되지 않았습니다: {action['id']}")
        outputs.append(output)
        caches.append(cache_root)
    for index, left in enumerate(outputs):
        for right in outputs[index + 1:]:
            require(left != right and not left.is_relative_to(right) and
                    not right.is_relative_to(left),
                    "build action output이 중복되거나 겹칩니다")
    for index, left in enumerate(caches):
        for right in caches[index + 1:]:
            require(left != right and not left.is_relative_to(right) and
                    not right.is_relative_to(left),
                    "build action cache root가 중복되거나 겹칩니다")
    for output in outputs:
        require(all(not output.is_relative_to(cache) and
                    not cache.is_relative_to(output) for cache in caches),
                "build output과 cache root가 겹칩니다")
    require(
        len(scratch_outputs) == len(set(scratch_outputs)),
        "Twister short output이 중복됩니다",
    )
    completed: set[str] = set()
    remaining = set(identifier_set)
    dependencies_by_id = {
        action["id"]: set(action["depends_on"])
        for action in actions
    }
    while remaining:
        ready = {
            identifier for identifier in remaining
            if dependencies_by_id[identifier] <= completed
        }
        require(ready, "build action 의존성에 cycle이 있습니다")
        completed.update(ready)
        remaining.difference_update(ready)


def output_bytes(value: bytes | str | None) -> bytes:
    """! @brief subprocess 출력을 손실 없는 byte evidence로 정규화합니다. """

    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8", errors="replace")


def atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    """! @brief 새 JSON 파일을 같은 directory의 임시 파일을 거쳐 원자 생성합니다. """

    path = path.resolve()
    require(not path.exists(), f"기존 파일을 덮어쓰지 않습니다: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    require(not temporary.exists(), f"temporary JSON이 이미 있습니다: {temporary}")
    try:
        encoded = (
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        require(not path.exists(), f"기존 파일을 덮어쓰지 않습니다: {path}")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def json_output_bytes(document: dict[str, Any]) -> bytes:
    """! @brief atomic JSON writer와 동일한 직렬화 byte를 반환합니다. """

    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def publish_json_set(rows: Sequence[tuple[Path, bytes]]) -> None:
    """! @brief 같은 directory의 JSON 집합을 실패 시 잔여물 없이 publish합니다. """

    require(rows and len({path for path, _encoded in rows}) == len(rows),
            "publish JSON path가 비었거나 중복됐습니다")
    temporary_rows = []
    published = []
    try:
        for path, encoded in rows:
            require(not path.exists(), f"기존 파일을 덮어쓰지 않습니다: {path}")
            temporary = path.with_name(f".{path.name}.tmp-set-{os.getpid()}")
            require(not temporary.exists(),
                    f"temporary JSON이 이미 있습니다: {temporary}")
            with temporary.open("xb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_rows.append((temporary, path))
        require(all(not path.exists() for _temporary, path in temporary_rows),
                "publish 직전에 output이 생성됐습니다")
        for temporary, path in temporary_rows:
            temporary.replace(path)
            published.append(path)
    except Exception:
        for path in published:
            if path.is_file() and not path.is_symlink():
                path.unlink()
        raise
    finally:
        for temporary, _path in temporary_rows:
            if temporary.is_file() and not temporary.is_symlink():
                temporary.unlink()


def write_failure_receipt(work_root: Path, receipts: list[dict[str, Any]], reason: str) -> None:
    """! @brief 중단된 build의 완료·실패 subprocess 기록을 보존합니다. """

    path = work_root / "m33-w06-build-failure.json"
    if path.exists():
        return
    atomic_write_json(path, {
        "schema_version": 1,
        "kind": "m33_w06_build_failure",
        "status": "FAIL",
        "reason": reason,
        "actions": receipts,
    })


def sanitize_twister_output(output: Path) -> bool:
    """! @brief Twister가 만든 direct-child link tree만 검증 후 제거합니다. """

    lexical_root = Path(os.path.abspath(output))
    root = _safe_directory_root(
        lexical_root, lexical_root.parent, "Twister output root"
    )
    links = root / "twister_links"
    try:
        links.lstat()
    except FileNotFoundError:
        _safe_directory_files(root, "Twister sanitized output")
        return False
    except OSError as error:
        raise ArtifactFailure(
            f"Twister link tree lstat에 실패했습니다: {links}"
        ) from error
    links = _safe_directory_root(links, root, "Twister generated link tree")
    children: list[tuple[Path, os.stat_result]] = []
    targets = set()
    try:
        candidates = sorted(links.iterdir(), key=lambda value: value.name)
    except OSError as error:
        raise ArtifactFailure(
            f"Twister link tree를 열지 못했습니다: {links}"
        ) from error
    for child in candidates:
        require(
            re.fullmatch(r"test_[0-9]+", child.name) is not None
            and Path(os.path.abspath(child)).parent == links,
            f"Twister link tree에 계약 밖 node가 있습니다: {child}",
        )
        try:
            status = child.lstat()
        except OSError as error:
            raise ArtifactFailure(
                f"Twister generated link lstat에 실패했습니다: {child}"
            ) from error
        require(
            stat.S_ISLNK(status.st_mode) or _node_is_reparse(child, status),
            f"Twister generated node가 link/reparse가 아닙니다: {child}",
        )
        try:
            target = child.resolve(strict=True)
        except OSError as error:
            raise ArtifactFailure(
                f"Twister generated link target을 찾지 못했습니다: {child}"
            ) from error
        require(
            target.is_relative_to(root)
            and not target.is_relative_to(links),
            f"Twister generated link가 output root를 탈출합니다: {child}",
        )
        _safe_directory_root(target, None, "Twister generated link target")
        target_key = target.as_posix().casefold()
        require(target_key not in targets,
                f"Twister generated link target이 중복됩니다: {child}")
        targets.add(target_key)
        children.append((child, status))
    _safe_directory_files(
        root, "Twister pre-sanitized output", excluded_directory=links
    )
    for child, status in children:
        try:
            if stat.S_ISLNK(status.st_mode):
                child.unlink()
            else:
                child.rmdir()
        except OSError as error:
            raise ArtifactFailure(
                f"Twister generated link 제거에 실패했습니다: {child}"
            ) from error
    try:
        links.rmdir()
    except OSError as error:
        raise ArtifactFailure(
            f"Twister generated link tree 제거에 실패했습니다: {links}"
        ) from error
    _safe_directory_files(root, "Twister sanitized output")
    return True


def execute_build_actions(
    actions: Sequence[dict[str, Any]],
    work_root: Path,
    timeout_seconds: int,
    max_workers: int = DEFAULT_BUILD_WORKERS,
    executor: Callable[..., Any] = subprocess.run,
) -> list[dict[str, Any]]:
    """! @brief 독립 action만 격리 병렬 실행하고 receipt는 plan 순서로 기록합니다. """

    require(60 <= timeout_seconds <= 14400, "build timeout은 60~14400초여야 합니다")
    validate_build_action_graph(actions, work_root, max_workers)
    for action in actions:
        output = Path(action["output"]).resolve()
        require(not output.exists(), f"fresh build output이 아닙니다: {output}")
        scratch_value = action.get("scratch_output")
        if scratch_value is not None:
            scratch = Path(str(scratch_value)).resolve()
            require(
                not scratch.exists(),
                f"fresh Twister short output이 아닙니다: {scratch}",
            )
        cache_root = Path(action["cache_root"]).resolve()
        require(not cache_root.exists(),
                f"fresh build cache가 아닙니다: {cache_root}")
    logs = work_root / "logs"
    logs.mkdir(parents=True, exist_ok=False)

    def run_action(ordinal: int, action: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        """! @brief 한 action을 자기 output/cache에서 실행하고 완전한 receipt를 반환합니다. """

        output = Path(action["output"]).resolve()
        scratch = (
            Path(str(action["scratch_output"])).resolve()
            if action.get("scratch_output") is not None
            else None
        )
        cache_root = Path(action["cache_root"]).resolve()
        stdout = b""
        stderr = b""
        timed_out = False
        exit_code: int | None = None
        launch_error: str | None = None
        postprocess_error: str | None = None
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            cache_root.mkdir(parents=True, exist_ok=False)
            for key in ISOLATED_CACHE_ENVIRONMENTS:
                Path(action["environment"][key]).mkdir(
                    parents=True, exist_ok=True
                )
            if action["kind"] == "arduino-cli":
                Path(action["environment"]["ARDUINO_DIRECTORIES_DOWNLOADS"]).mkdir(
                    parents=True, exist_ok=True
                )
                Path(action["environment"]["NUCODE_BUILD_CACHE_ROOT"]).mkdir(
                    parents=True, exist_ok=True
                )
            if action.get("precreate_output"):
                output.mkdir()
            environment = dict(os.environ)
            environment.update(action["environment"])
            completed = executor(
                action["command"],
                cwd=action["cwd"],
                env=environment,
                capture_output=True,
                timeout=timeout_seconds,
                shell=False,
                check=False,
            )
            stdout = output_bytes(completed.stdout)
            stderr = output_bytes(completed.stderr)
            exit_code = int(completed.returncode)
        except subprocess.TimeoutExpired as error:
            stdout = output_bytes(error.stdout)
            stderr = output_bytes(error.stderr)
            timed_out = True
        except OSError as error:
            stderr = str(error).encode("utf-8", errors="replace")
            launch_error = type(error).__name__
        if (
            action["kind"] == "twister"
            and scratch is not None
            and scratch.exists()
            and not timed_out
            and launch_error is None
            and exit_code is not None
        ):
            try:
                sanitize_twister_output(scratch)
            except ArtifactFailure as error:
                stderr += str(error).encode("utf-8", errors="replace")
                postprocess_error = type(error).__name__
        if (
            scratch is not None
            and scratch.exists()
            and not timed_out
            and launch_error is None
            and postprocess_error is None
            and exit_code is not None
        ):
            try:
                output.parent.mkdir(parents=True, exist_ok=True)
                scratch.replace(output)
            except OSError as error:
                stderr += str(error).encode("utf-8", errors="replace")
                launch_error = type(error).__name__
        stdout_path = logs / f"{action['id']}.stdout.bin"
        stderr_path = logs / f"{action['id']}.stderr.bin"
        with stdout_path.open("xb") as stream:
            stream.write(stdout)
        with stderr_path.open("xb") as stream:
            stream.write(stderr)
        receipt = {
            "ordinal": ordinal,
            "id": action["id"],
            "kind": action["kind"],
            "depends_on": action["depends_on"],
            "command": action["command"],
            "cwd": action["cwd"],
            "output": output.as_posix(),
            "cache_root": cache_root.as_posix(),
            "shell": False,
            "jobs": action["jobs"],
            "timeout_seconds": timeout_seconds,
            "timed_out": timed_out,
            "exit_code": exit_code,
            "launch_error": launch_error,
            "postprocess_error": postprocess_error,
            "output_exists": output.exists(),
            "stdout": {"path": stdout_path.as_posix(), "sha256": file_sha256(stdout_path)},
            "stderr": {"path": stderr_path.as_posix(), "sha256": file_sha256(stderr_path)},
        }
        if (timed_out or launch_error is not None or
                postprocess_error is not None or exit_code != 0 or
                not output.exists()):
            reason = (
                f"build action 실패: {action['id']}: timeout={timed_out}:"
                f"launch={launch_error}:postprocess={postprocess_error}:"
                f"exit={exit_code}:output={output.exists()}"
            )
            return receipt, reason
        return receipt, None

    pending = set(range(len(actions)))
    completed: set[str] = set()
    receipt_by_index: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while pending:
            ready = [
                index for index in sorted(pending)
                if set(actions[index]["depends_on"]) <= completed
            ]
            require(ready, "build action 실행 의존성이 교착됐습니다")
            batch = ready[:max_workers]
            futures: dict[Future, int] = {
                pool.submit(
                    run_action,
                    int(actions[index].get("plan_ordinal", index + 1)),
                    actions[index],
                ): index
                for index in batch
            }
            failures: dict[int, str] = {}
            for future, index in futures.items():
                receipt, reason = future.result()
                receipt_by_index[index] = receipt
                if reason is not None:
                    failures[index] = reason
            pending.difference_update(batch)
            if failures:
                receipts = [receipt_by_index[index]
                            for index in sorted(receipt_by_index)]
                first = failures[min(failures)]
                write_failure_receipt(work_root, receipts, first)
                raise ArtifactFailure(first)
            completed.update(actions[index]["id"] for index in batch)
    return [receipt_by_index[index] for index in range(len(actions))]


def unique_file(paths: Sequence[Path], label: str) -> Path:
    """! @brief 정확히 하나인 nonempty file을 반환합니다. """

    matches = sorted({path.resolve() for path in paths if path.is_file() and path.stat().st_size > 0})
    require(len(matches) == 1, f"{label} file 수가 정확히 1이 아닙니다: {matches}")
    return matches[0]


def twister_scenario_root(action: dict[str, Any], scenario: str) -> Path:
    """! @brief 한 Twister scenario의 고정 output root를 반환합니다. """

    require(scenario in action["scenarios"], f"Twister action에 scenario가 없습니다: {scenario}")
    root = Path(action["output"]) / PLATFORM_DIRECTORY / TOOLCHAIN_DIRECTORY / scenario
    require(root.is_dir(), f"Twister scenario output이 없습니다: {root}")
    return root.resolve()


def twister_image(action: dict[str, Any], scenario: str, application: str) -> Path:
    """! @brief scenario에서 application build record와 인접한 primary HEX를 찾습니다. """

    root = twister_scenario_root(action, scenario)
    application_name = Path(application).name
    candidates = []
    for image in root.rglob("zephyr.hex"):
        record = image.parent.parent / "nucode_arduino_core_build.yml"
        if record.is_file() and application_name in image.parts:
            candidates.append(image)
    return unique_file(candidates, f"{scenario} primary HEX")


def twister_soak_image(action: dict[str, Any], scenario: str) -> Path:
    """! @brief custom M33 record가 인접한 soak 역할의 primary HEX를 찾습니다. """

    root = twister_scenario_root(action, scenario)
    candidates = [
        image for image in root.rglob("zephyr.hex")
        if (image.parent.parent / "m33_w06_build_record.json").is_file()
    ]
    return unique_file(candidates, f"{scenario} soak primary HEX")


def twister_build_tree(action: dict[str, Any], scenarios: Sequence[str], name: str) -> Path:
    """! @brief aggregate 또는 exact sysbuild root를 build-tree slot에 연결합니다. """

    require(scenarios, f"build tree scenario가 없습니다: {name}")
    if name == "build-outdir":
        require(all(scenario in action["scenarios"] for scenario in scenarios), "aggregate build group이 다릅니다")
        return Path(action["output"]).resolve()
    require(len(scenarios) == 1, f"exact sysbuild slot에 scenario가 여러 개입니다: {name}")
    root = twister_scenario_root(action, scenarios[0])
    domains = sorted(root.rglob("domains.yaml"))
    require(len(domains) == 1, f"exact sysbuild root를 유일하게 찾지 못했습니다: {name}")
    return domains[0].parent.resolve()


def arduino_manifest(action: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    """! @brief Arduino action의 유일한 build manifest를 반환합니다. """

    path = unique_file(list(Path(action["output"]).glob("*.nu54-build.json")), "Arduino build manifest")
    return path, strict_json(path)


def arduino_config(
    record: dict[str, Any],
    record_path: Path | None = None,
    image: Path | None = None,
) -> Path:
    """! @brief Arduino manifest가 결합한 live native build config를 반환합니다. """

    if record_path is not None and image is not None:
        portable = validate_arduino_portable_provenance(
            image.resolve(), record_path.resolve(), record
        )
        if portable is not None:
            return portable
    value = record.get("source_inputs", {}).get("live_build_record", {}).get("path")
    require(isinstance(value, str) and value, "Arduino live build record path가 없습니다")
    live_record = Path(value).resolve()
    require(live_record.is_file(), f"Arduino live build record가 없습니다: {live_record}")
    config = live_record.parent / "zephyr/.config"
    require(config.is_file() and config.stat().st_size > 0, f"Arduino resolved config가 없습니다: {config}")
    return config.resolve()


def resolve_build_entries(
    plan: dict[str, Any],
    actions: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """! @brief 성공한 action output에서 모든 buildable slot을 유일하게 해석합니다. """

    artifacts = build_artifacts(plan)
    twister_actions = {
        scenario: action
        for action in actions
        if action["kind"] == "twister"
        for scenario in action["scenarios"]
    }
    recipe_actions = {
        action["recipe_key"]: action
        for action in actions
        if action.get("recipe_key") is not None
    }
    diagnostics_actions = {
        action["id"]: action
        for action in actions
        if action["kind"] == "diagnostics"
    }
    profile_actions = {
        (action["profile"]["family"], action["profile"]["role"]): action
        for action in actions
        if action["kind"] == "profile_record"
    }
    resolved: dict[tuple[str, str], Path] = {}
    for key, artifact in artifacts.items():
        recipe = artifact.get("recipe")
        if not isinstance(recipe, dict):
            continue
        builder = recipe["builder"]
        if builder == "run_zephyr_build.py":
            scenarios = [recipe["scenario"]] if "scenario" in recipe else recipe["scenarios"]
            require(all(scenario in twister_actions for scenario in scenarios), f"Twister action mapping이 없습니다: {key}")
            action = twister_actions[scenarios[0]]
            require(all(twister_actions[scenario] is action for scenario in scenarios), f"build tree scenario group이 나뉘었습니다: {key}")
            if artifact["kind"] == "target_image":
                if key[0] == SOAK_ARTIFACT_ID:
                    resolved[key] = twister_soak_image(action, recipe["scenario"])
                else:
                    resolved[key] = twister_image(action, recipe["scenario"], recipe["application"])
            else:
                resolved[key] = twister_build_tree(action, scenarios, artifact["name"])
        elif builder == "west_direct":
            action = recipe_actions.get(recipe_key(recipe))
            require(action is not None, f"direct west action mapping이 없습니다: {key}")
            if key[0] in {"m33_profiles_standard", "m33_profiles_native"}:
                selectors = dict(value.split("=", 1) for value in recipe["selectors"])
                profile = (selectors.get("M33_PROFILE_FAMILY", "standard"), selectors["M33_PROFILE_ROLE"])
                require(profile in profile_actions, f"profile record action mapping이 없습니다: {key}")
                resolved[key] = Path(profile_actions[profile]["output"]) / "image.hex"
            else:
                resolved[key] = Path(action["output"]) / "zephyr/zephyr.hex"
        elif builder == "arduino-cli":
            action = recipe_actions.get(recipe_key(recipe))
            require(action is not None, f"Arduino action mapping이 없습니다: {key}")
            _manifest_path, record = arduino_manifest(action)
            image = Path(str(record.get("artifacts", {}).get("hex", {}).get("path", ""))).resolve()
            require(image.is_file(), f"Arduino primary HEX가 없습니다: {key}")
            resolved[key] = image
        elif builder == "m33_diagnostics.py":
            if key[0] == "m33_diagnostics_dtm" and \
                    artifact["kind"] == "build_record":
                action = diagnostics_actions.get("diagnostics-dtm")
                require(action is not None, "DTM diagnostics action mapping이 없습니다")
                resolved[key] = Path(action["output"]) / "manifest.json"
            elif "transport" in recipe:
                action = diagnostics_actions.get("diagnostics-dtm")
                require(action is not None, "DTM diagnostics action mapping이 없습니다")
                route = "dtm_twowire" if recipe["transport"] == "twowire" else "dtm_hci"
                resolved[key] = Path(action["output"]) / route / "zephyr/zephyr.hex"
            else:
                action = diagnostics_actions.get("diagnostics-build")
                require(action is not None, "build diagnostics action mapping이 없습니다")
                resolved[key] = Path(action["output"])
    for key, artifact in artifacts.items():
        if key in resolved:
            continue
        campaign_id, name = key
        if artifact["kind"] == "build_record" and campaign_id == SOAK_ARTIFACT_ID:
            role = name.removeprefix("build-record-")
            image = resolved[(campaign_id, f"hex-{role}")]
            resolved[key] = image.parent.parent / "m33_w06_build_record.json"
        elif artifact["kind"] == "build_record" and campaign_id.startswith("m33_profiles_"):
            image_name = "hex-" + name.removeprefix("build-record-")
            image_artifact = artifacts[(campaign_id, image_name)]
            recipe = image_artifact["recipe"]
            selectors = dict(value.split("=", 1) for value in recipe["selectors"])
            profile = (selectors.get("M33_PROFILE_FAMILY", "standard"), selectors["M33_PROFILE_ROLE"])
            resolved[key] = Path(profile_actions[profile]["output"]) / "build-record.json"
        elif artifact["kind"] == "build_record" and campaign_id == "m33_diagnostics_dtm":
            resolved[key] = Path(diagnostics_actions["diagnostics-dtm"]["output"]) / "manifest.json"
        elif artifact["kind"] == "configuration":
            binding = name.removesuffix("-config")
            candidates = [
                image_key
                for image_key, image_artifact in artifacts.items()
                if image_key[0] == campaign_id
                and image_artifact["kind"] == "target_image"
                and image_artifact["binding"].replace("-image", "") == binding
            ]
            require(len(candidates) == 1, f"config role image mapping이 모호합니다: {key}:{candidates}")
            image = resolved[candidates[0]]
            if campaign_id == SOAK_ARTIFACT_ID:
                resolved[key] = image.parent / ".config"
            else:
                record = strict_json(adjacent_build_record(image))
                resolved[key] = arduino_config(record)
        else:
            raise ArtifactFailure(f"buildable slot resolver가 없습니다: {key}:{artifact['kind']}")
    require(set(resolved) == set(artifacts), "build output resolver가 부분 상태입니다")
    return [
        {"campaign_id": campaign_id, "name": name, "path": resolved[(campaign_id, name)].resolve().as_posix()}
        for campaign_id, name in sorted(resolved)
    ]


def runtime_inputs_template(
    plan: dict[str, Any],
    effective_source: dict[str, Any] | None = None,
    transfer_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """! @brief build가 만들 수 없는 실기·보안 입력의 NOT_PROVIDED manifest를 만듭니다. """

    document = {
        "schema_version": 1,
        "kind": "m33_w06_runtime_inputs",
        "plan_sha256": plan["contract_sha256"],
        "source": plan["source"],
        "source_binding": validate_source_binding(
            plan["source"], effective_source or plan["source"]
        ),
        "transfer_contract": (
            validate_transfer_contract(transfer_contract)
            if transfer_contract is not None else None
        ),
        "entries": [
            {
                "campaign_id": campaign_id,
                "name": name,
                "kind": artifact["kind"],
                "status": "NOT_PROVIDED",
                "path": None,
            }
            for (campaign_id, name), artifact in sorted(runtime_artifacts(plan).items())
        ],
    }
    document["manifest_sha256"] = canonical_sha256(document)
    return document


def bind_runtime_inputs(
    plan: dict[str, Any],
    paths: dict[tuple[str, str], Path],
    effective_source: dict[str, Any] | None = None,
    transfer_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """! @brief 후속 실기 준비기가 만든 모든 runtime file을 exact manifest에 결합합니다. """

    expected = runtime_artifacts(plan)
    require(set(paths) == set(expected), "runtime input path 집합이 부분 또는 과다 상태입니다")
    current = effective_source or plan["source"]
    document = runtime_inputs_template(plan, current, transfer_contract)
    for entry in document["entries"]:
        key = (entry["campaign_id"], entry["name"])
        source = paths[key].resolve()
        require(source.is_file() and source.stat().st_size > 0, f"runtime input file이 없습니다: {key}:{source}")
        entry["status"] = "PROVIDED"
        entry["path"] = source.as_posix()
    document.pop("manifest_sha256")
    document["manifest_sha256"] = canonical_sha256(document)
    validate_runtime_inputs(
        plan,
        document,
        require_complete=True,
        effective_source=current,
        transfer_contract=transfer_contract,
    )
    return document


def validate_runtime_inputs(
    plan: dict[str, Any],
    document: dict[str, Any],
    require_complete: bool,
    effective_source: dict[str, Any] | None = None,
    transfer_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """! @brief runtime input manifest의 key·상태·byte를 fail-closed 검증합니다. """

    require(
        document.get("schema_version") == 1
        and document.get("kind") == "m33_w06_runtime_inputs",
        "runtime input manifest schema가 다릅니다",
    )
    digest = document.get("manifest_sha256")
    clone = dict(document)
    clone.pop("manifest_sha256", None)
    require(
        SHA256.fullmatch(str(digest)) is not None and canonical_sha256(clone) == digest,
        "runtime input manifest hash가 다릅니다",
    )
    require(
        document.get("plan_sha256") == plan["contract_sha256"]
        and document.get("source") == plan["source"],
        "runtime input manifest plan/source가 다릅니다",
    )
    require_source_binding(
        document,
        plan["source"],
        effective_source or plan["source"],
        "runtime input manifest",
    )
    observed_transfer = document.get("transfer_contract")
    if observed_transfer is not None:
        validate_transfer_contract(observed_transfer)
    require(observed_transfer == transfer_contract,
            "runtime input transfer contract가 다릅니다")
    expected = runtime_artifacts(plan)
    entries = document.get("entries")
    require(isinstance(entries, list), "runtime input entries가 배열이 아닙니다")
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries:
        require(isinstance(entry, dict), "runtime input entry가 object가 아닙니다")
        key = (entry.get("campaign_id"), entry.get("name"))
        require(key in expected and key not in by_key, f"runtime input key가 잘못됐습니다: {key}")
        require(entry.get("kind") == expected[key]["kind"], f"runtime input kind가 다릅니다: {key}")
        by_key[key] = entry
    require(set(by_key) == set(expected), "runtime input manifest가 부분 상태입니다")
    validated: list[dict[str, Any]] = []
    for key, artifact in expected.items():
        entry = by_key[key]
        status = entry.get("status")
        path_value = entry.get("path")
        if status == "NOT_PROVIDED":
            require(not require_complete and path_value is None, f"runtime input이 준비되지 않았습니다: {key}")
            continue
        require(status == "PROVIDED" and isinstance(path_value, str) and path_value, f"runtime input 상태가 잘못됐습니다: {key}")
        source = Path(path_value).resolve()
        require(source.is_file() and source.stat().st_size > 0, f"runtime input file이 없습니다: {key}:{source}")
        digest_value = file_sha256(source)
        validated.append({
            "campaign_id": key[0],
            "name": key[1],
            "kind": artifact["kind"],
            "source": source.as_posix(),
            "sha256": digest_value,
        })
    for campaign_id in {key[0] for key in expected}:
        hashes = [
            row["sha256"]
            for row in validated
            if row["campaign_id"] == campaign_id and row["kind"] == "signing_key"
        ]
        require(len(hashes) == len(set(hashes)), f"서로 다른 signing key slot이 같은 byte입니다: {campaign_id}")
    if require_complete:
        require(len(validated) == len(expected), "runtime input manifest가 완성되지 않았습니다")
    return validated


def reject_raw_probe_identity(value: Any, label: str) -> None:
    """! @brief 공개 runtime JSON에서 원시 probe UID field를 재귀적으로 거부합니다. """

    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            require(
                normalized not in {"uid", "raw_uid", "daplink_uid", "probe_uid"}
                and not normalized.endswith("_raw_uid"),
                f"{label}에 원시 probe UID field가 있습니다",
            )
            reject_raw_probe_identity(child, label)
    elif isinstance(value, list):
        for child in value:
            reject_raw_probe_identity(child, label)


def build_index_paths(
    plan: dict[str, Any],
    index: dict[str, Any],
    effective_source: dict[str, Any] | None = None,
    relocation_root: Path | None = None,
) -> dict[tuple[str, str], Path]:
    """! @brief 검증된 build index entry를 key별 절대 경로로 반환합니다. """

    validated = validate_index(
        plan,
        index,
        effective_source=effective_source,
        relocation_root=relocation_root,
    )
    return {
        (entry["campaign_id"], entry["name"]): Path(entry["source"]).resolve()
        for entry in validated
    }


def signing_key_from_build_trees(
    paths: dict[tuple[str, str], Path],
    campaign_id: str,
    names: Sequence[str],
    planned_sdk_root: Path | None = None,
    current_sdk_root: Path | None = None,
) -> Path:
    """! @brief 모든 MCUboot build `.config`가 사용한 동일 signing key를 역추적합니다. """

    require(
        (planned_sdk_root is None) == (current_sdk_root is None),
        "signing key SDK 위치 재결합 인자가 불완전합니다",
    )
    if planned_sdk_root is not None and current_sdk_root is not None:
        planned_sdk_root = planned_sdk_root.resolve()
        current_sdk_root = current_sdk_root.resolve()
        require(
            planned_sdk_root.is_absolute() and current_sdk_root.is_absolute(),
            "signing key SDK root가 절대 경로가 아닙니다",
        )
    resolved: list[Path] = []
    expression = re.compile(r'^CONFIG_BOOT_SIGNATURE_KEY_FILE="([^"\r\n]+)"$', re.MULTILINE)
    for name in names:
        root = paths.get((campaign_id, name))
        require(root is not None and root.is_dir(), f"signing key build tree가 없습니다: {campaign_id}:{name}")
        values = []
        for config in config_files(root):
            match = expression.search(config.read_text(encoding="utf-8"))
            if match is not None:
                values.append(match.group(1))
        require(len(values) == 1, f"MCUboot signing key config를 유일하게 찾지 못했습니다: {campaign_id}:{name}")
        candidate = Path(values[0])
        require(candidate.is_absolute(), f"MCUboot signing key path가 절대 경로가 아닙니다: {campaign_id}:{name}")
        if planned_sdk_root is not None and current_sdk_root is not None:
            try:
                relative = candidate.relative_to(planned_sdk_root)
            except ValueError:
                pass
            else:
                candidate = (current_sdk_root / relative).resolve()
                require(
                    candidate.is_relative_to(current_sdk_root),
                    f"MCUboot signing key SDK 재결합이 root를 탈출합니다: {campaign_id}:{name}",
                )
        candidate = candidate.resolve()
        require(candidate.is_file() and candidate.stat().st_size > 0, f"MCUboot signing key가 없습니다: {campaign_id}:{name}")
        resolved.append(candidate)
    require(
        len({path.as_posix().casefold() for path in resolved}) == 1
        and len({file_sha256(path) for path in resolved}) == 1,
        f"campaign MCUboot signing key가 서로 다릅니다: {campaign_id}",
    )
    return resolved[0]


def validate_flash_record(
    path: Path,
    role: str,
    identity: dict[str, Any],
    build_paths: dict[tuple[str, str], Path],
) -> str:
    """! @brief BAP flash-only 기록을 exact S·image·config·hashed probe에 결합합니다. """

    document = strict_json(path, encoding="utf-8-sig")
    reject_raw_probe_identity(document, f"{role} flash record")
    image = build_paths[("m31_bap_duplex", f"{role}-image")]
    config = build_paths[("m31_bap_duplex", f"{role}-config")]
    flash = document.get(f"{role}_flash")
    safe_flash = (
        isinstance(flash, list)
        and len(flash) == 2
        and str(flash[0]).startswith("pyocd-sector-")
        and str(flash[1]).isdigit()
        and int(flash[1]) > 0
    )
    probe = str(document.get(f"{role}_probe_sha256", ""))
    require(
        document.get("status") == "FLASH_PREPARED"
        and document.get("source_clean") is True
        and document.get("core_revision") == identity["source_revision"]
        and safe_flash
        and SHA256.fullmatch(probe) is not None
        and document.get(f"{role}_image_sha256") == file_sha256(image)
        and document.get(f"{role}_config_sha256") == file_sha256(config),
        f"{role} flash record가 current-S build/current connection과 다릅니다",
    )
    return probe


def runtime_producer_paths(
    plan: dict[str, Any],
    producer_path: Path,
) -> dict[tuple[str, str], Path]:
    """! @brief current-S fixture producer의 두 runtime output을 검증해 반환합니다. """

    producer = strict_json(producer_path.resolve(), encoding="utf-8-sig")
    reject_raw_probe_identity(producer, "runtime producer")
    require(
        producer.get("schema_version") == 1
        and producer.get("kind") == "m33_w06_runtime_producer"
        and producer.get("status") == "PASS"
        and producer.get("source_revision") == plan["source"]["source_revision"]
        and producer.get("source_clean") is True,
        "runtime producer가 current-S PASS가 아닙니다",
    )
    expected = {
        ("m33_ecosystem", "fixture"): "fixture",
        ("m33_diagnostics_dtm", "third-idle-fixture"): "fixture",
    }
    entries = producer.get("runtime_inputs")
    require(isinstance(entries, list), "runtime producer input 배열이 없습니다")
    paths: dict[tuple[str, str], Path] = {}
    for entry in entries:
        require(isinstance(entry, dict), "runtime producer input이 object가 아닙니다")
        key = (entry.get("campaign_id"), entry.get("name"))
        require(key in expected and key not in paths, f"runtime producer key가 잘못됐습니다: {key}")
        require(entry.get("kind") == expected[key], f"runtime producer kind가 다릅니다: {key}")
        value = entry.get("path")
        require(isinstance(value, str) and Path(value).is_absolute(), f"runtime producer path가 절대 경로가 아닙니다: {key}")
        path = Path(value).resolve()
        require(
            path.is_file()
            and path.stat().st_size > 0
            and SHA256.fullmatch(str(entry.get("sha256", ""))) is not None
            and file_sha256(path) == entry["sha256"],
            f"runtime producer file/hash가 다릅니다: {key}",
        )
        paths[key] = path
    require(set(paths) == set(expected), "runtime producer output이 부분 상태입니다")

    ecosystem = runpy.run_path(str(REPOSITORY / "tools/bluetooth/m33_ecosystem_hil.py"))
    ecosystem_fixture = strict_json(paths[("m33_ecosystem", "fixture")], encoding="utf-8-sig")
    reject_raw_probe_identity(ecosystem_fixture, "ecosystem fixture")
    try:
        ecosystem["validate_fixture"](ecosystem_fixture)
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise ArtifactFailure("ecosystem fixture 검증이 실패했습니다") from error
    require(
        ecosystem_fixture.get("identity", "")[:40] == plan["source"]["source_revision"],
        "ecosystem fixture가 current-S가 아닙니다",
    )

    diagnostics_path = paths[("m33_diagnostics_dtm", "third-idle-fixture")]
    diagnostics_fixture = strict_json(diagnostics_path, encoding="utf-8-sig")
    reject_raw_probe_identity(diagnostics_fixture, "third-idle fixture")
    probe = diagnostics_fixture.get("probe_sha256")
    require(SHA256.fullmatch(str(probe)) is not None, "third-idle fixture probe hash가 없습니다")
    diagnostics = runpy.run_path(str(REPOSITORY / "tools/bluetooth/m33_diagnostics.py"))
    try:
        diagnostics["load_watcher_fixture"](
            diagnostics_path,
            file_sha256(diagnostics_path),
            probe,
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise ArtifactFailure("third-idle fixture 검증이 실패했습니다") from error
    require(
        diagnostics_fixture.get("revisions", {}).get("core") == plan["source"]["source_revision"],
        "third-idle fixture가 current-S가 아닙니다",
    )
    return paths


def bind_prepared_runtime_inputs(
    plan: dict[str, Any],
    index: dict[str, Any],
    generated_root: Path,
    client_flash_record: Path,
    server_flash_record: Path,
    runtime_producer: Path,
    executor: Callable[..., Any] = subprocess.run,
    effective_source: dict[str, Any] | None = None,
    relocation_root: Path | None = None,
) -> dict[str, Any]:
    """! @brief build-derived 도구·키와 current connection 기록을 9개 slot에 자동 결합합니다. """

    identity = effective_source or plan["source"]
    build_paths = build_index_paths(
        plan,
        index,
        effective_source=identity,
        relocation_root=relocation_root,
    )
    sdk_root = Path(identity["sdk_root"]).resolve()
    toolchain_root = Path(identity["toolchain_root"]).resolve()
    imgtool = (sdk_root / "bootloader/mcuboot/scripts/imgtool.py").resolve()
    python = toolchain_python(toolchain_root)
    require(imgtool.is_file() and imgtool.stat().st_size > 0, "고정 SDK imgtool.py가 없습니다")
    trust_key = signing_key_from_build_trees(
        build_paths,
        "m30_dfu",
        ("central-build-outdir", "peripheral-build-outdir", "unconfirmed-build-outdir"),
        Path(plan["source"]["sdk_root"]),
        sdk_root,
    )
    mesh_key = signing_key_from_build_trees(
        build_paths,
        "m32_mesh_dfu",
        ("build-candidate", "build-distributor", "build-target-a", "build-target-b"),
        Path(plan["source"]["sdk_root"]),
        sdk_root,
    )
    root = require_external_fresh_root(generated_root, identity, "runtime 생성")
    root.mkdir(parents=True)
    wrong_key = root / "m30-dfu-wrong-ecdsa-p256.pem"
    checked_subprocess(
        (str(python), str(imgtool), "keygen", "-k", str(wrong_key), "-t", "ecdsa-p256"),
        root,
        60,
        executor,
        toolchain_environment(toolchain_root, sdk_root),
    )
    require(wrong_key.is_file() and wrong_key.stat().st_size > 0, "wrong signing key가 생성되지 않았습니다")
    wrong_hash = file_sha256(wrong_key)
    require(
        wrong_hash not in {file_sha256(trust_key), file_sha256(mesh_key)},
        "wrong signing key가 build signing key와 같습니다",
    )
    client_flash_record = client_flash_record.resolve()
    server_flash_record = server_flash_record.resolve()
    client_probe = validate_flash_record(client_flash_record, "client", identity, build_paths)
    server_probe = validate_flash_record(server_flash_record, "server", identity, build_paths)
    require(client_probe != server_probe, "client/server flash record가 같은 probe를 사용합니다")
    producer = runtime_producer_paths(plan, runtime_producer)
    paths = {
        ("m30_dfu", "imgtool"): imgtool,
        ("m30_dfu", "imgtool-python"): python,
        ("m30_dfu", "trust-signing-key"): trust_key,
        ("m30_dfu", "wrong-signing-key"): wrong_key,
        ("m31_bap_duplex", "client-flash-record"): client_flash_record,
        ("m31_bap_duplex", "server-flash-record"): server_flash_record,
        ("m32_mesh_dfu", "signing-key"): mesh_key,
        **producer,
    }
    return bind_runtime_inputs(
        plan,
        paths,
        identity,
        index.get("transfer_contract"),
    )


def build_from_plan(
    plan: dict[str, Any],
    work_root: Path,
    index_output: Path,
    runtime_output: Path,
    arduino_cli: Path,
    arduino_config: Path,
    fqbn_prefix: str,
    timeout_seconds: int,
    max_workers: int = DEFAULT_BUILD_WORKERS,
    executor: Callable[..., Any] = subprocess.run,
    identity_validator: Callable[..., dict[str, Any]] = validate_source_lock,
    action_factory: Callable[..., list[dict[str, Any]]] = create_build_actions,
    entry_resolver: Callable[..., list[dict[str, Any]]] = resolve_build_entries,
    index_validator: Callable[..., list[dict[str, Any]]] | None = None,
    plan_validator: Callable[..., None] = validate_plan,
    sdk_root: Path | None = None,
    toolchain_root: Path | None = None,
) -> dict[str, Any]:
    """! @brief fresh 외부 root에서 plan 전체를 build하고 exact index를 원자 생성합니다. """

    plan_validator(plan)
    sdk_root = (sdk_root or Path(plan["source"]["sdk_root"])).resolve()
    toolchain_root = (
        toolchain_root or Path(plan["source"]["toolchain_root"])
    ).resolve()
    location = dict(plan["source"])
    location["sdk_root"] = sdk_root.as_posix()
    location["toolchain_root"] = toolchain_root.as_posix()
    validate_source_binding(plan["source"], location)
    work_root = require_external_fresh_root(work_root, location, "build")
    index_output = require_external_output(
        index_output, location, "build index"
    )
    runtime_output = require_external_output(
        runtime_output, location, "runtime input"
    )
    before = identity_validator(
        REPOSITORY,
        sdk_root,
        toolchain_root,
        plan["source"]["source_revision"],
    )
    source_binding = validate_source_binding(plan["source"], before)
    require(index_output != runtime_output,
            "build index/runtime manifest는 서로 다른 파일이어야 합니다")
    require(arduino_cli.resolve().is_file(), f"Arduino CLI가 없습니다: {arduino_cli}")
    require(arduino_config.resolve().is_file(), f"Arduino CLI config가 없습니다: {arduino_config}")
    require(sdk_root.is_dir() and toolchain_root.is_dir(), "SDK/toolchain root가 없습니다")
    work_root.mkdir(parents=True)
    try:
        actions = action_factory(
            plan,
            work_root,
            sdk_root,
            toolchain_root,
            arduino_cli.resolve(),
            arduino_config.resolve(),
            fqbn_prefix,
        )
        receipts = execute_build_actions(
            actions, work_root, timeout_seconds, max_workers, executor
        )
        entries = entry_resolver(plan, actions)
        index = {
            "schema_version": 1,
            "kind": "m33_w06_build_index",
            "plan_sha256": plan["contract_sha256"],
            "source": plan["source"],
            "source_binding": source_binding,
            "transfer_contract": None,
            "entries": entries,
            "actions": receipts,
        }
        validator = validate_index if index_validator is None else index_validator
        if index_validator is None:
            validator(plan, index, effective_source=before)
        else:
            validator(plan, index)
        runtime = runtime_inputs_template(plan, before)
        validate_runtime_inputs(
            plan, runtime, require_complete=False, effective_source=before
        )
    except Exception as error:
        after_failure = identity_validator(
            REPOSITORY,
            sdk_root,
            toolchain_root,
            plan["source"]["source_revision"],
        )
        if after_failure != before:
            raise ArtifactFailure("실패한 build 도중 source identity가 변경됐습니다") from error
        raise
    after = identity_validator(
        REPOSITORY,
        sdk_root,
        toolchain_root,
        plan["source"]["source_revision"],
    )
    require(after == before, "build 도중 source identity가 변경됐습니다")
    try:
        atomic_write_json(runtime_output, runtime)
        atomic_write_json(index_output, index)
    except Exception:
        if runtime_output.exists() and not index_output.exists():
            runtime_output.unlink()
        raise
    return index


def _portable_path(path: Path, base: Path, label: str) -> str:
    """! @brief bundle 내부 경로만 POSIX 상대 경로로 직렬화합니다. """

    resolved = path.resolve()
    try:
        relative = resolved.relative_to(base.resolve()).as_posix()
    except ValueError as error:
        raise ArtifactFailure(f"{label}가 bundle 밖입니다: {resolved}") from error
    require(relative not in ("", "."), f"{label}가 bundle root 자체입니다")
    return relative


def _node_is_reparse(path: Path, status: os.stat_result) -> bool:
    """! @brief Windows reparse point와 Python junction을 이식 가능하게 판별합니다. """

    attributes = int(getattr(status, "st_file_attributes", 0))
    is_junction = getattr(path, "is_junction", None)
    return bool(attributes & 0x400) or bool(
        callable(is_junction) and is_junction()
    )


def _safe_node(
    path: Path,
    label: str,
    expected: str | None = None,
) -> os.stat_result:
    """! @brief symlink·junction·reparse를 거부하고 node 종류를 lstat으로 검사합니다. """

    try:
        status = path.lstat()
    except OSError as error:
        raise ArtifactFailure(f"{label} lstat에 실패했습니다: {path}") from error
    require(
        not stat.S_ISLNK(status.st_mode)
        and not path.is_symlink()
        and not _node_is_reparse(path, status),
        f"{label}는 symlink/junction/reparse point일 수 없습니다: {path}",
    )
    if expected == "file":
        require(stat.S_ISREG(status.st_mode),
                f"{label}가 regular file이 아닙니다: {path}")
    elif expected == "directory":
        require(stat.S_ISDIR(status.st_mode),
                f"{label}가 directory가 아닙니다: {path}")
    return status


def _safe_directory_root(path: Path, parent: Path | None, label: str) -> Path:
    """! @brief named directory 자체가 실제 parent 바로 아래의 non-reparse node인지 검사합니다. """

    lexical = Path(os.path.abspath(path))
    _safe_node(lexical, label, "directory")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        raise ArtifactFailure(f"{label} resolve에 실패했습니다: {lexical}") from error
    require(resolved == lexical,
            f"{label}가 다른 directory로 resolve됩니다: {lexical}")
    if parent is not None:
        parent_resolved = parent.resolve(strict=True)
        require(lexical.parent.resolve(strict=True) == parent_resolved,
                f"{label} parent가 expected root와 다릅니다: {lexical}")
    return resolved


def _safe_regular_file(path: Path, parent: Path, label: str) -> Path:
    """! @brief regular file 자체와 resolved parent가 exact bundle인지 검사합니다. """

    lexical = Path(os.path.abspath(path))
    _safe_node(lexical, label, "file")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        raise ArtifactFailure(f"{label} resolve에 실패했습니다: {lexical}") from error
    expected_parent = parent.resolve(strict=True)
    require(
        resolved == lexical
        and lexical.parent.resolve(strict=True) == expected_parent,
        f"{label} parent/resolve identity가 다릅니다: {lexical}",
    )
    return resolved


def _safe_directory_files(
    path: Path,
    label: str,
    excluded_directory: Path | None = None,
) -> list[Path]:
    """! @brief tree 전체를 lstat하며 외부 링크·reparse 의존성 없이 file을 수집합니다. """

    root = _safe_directory_root(path, None, label)
    excluded = None
    if excluded_directory is not None:
        excluded = _safe_directory_root(
            excluded_directory, root, f"{label} excluded directory"
        )
        require(
            excluded.parent == root,
            f"{label} excluded directory는 root의 direct child여야 합니다: "
            f"{excluded}",
        )
    files = []

    def walk_error(error: OSError) -> None:
        """! @brief directory traversal 오류를 누락 없이 fail-closed 처리합니다. """

        raise ArtifactFailure(
            f"{label} traversal에 실패했습니다: {error.filename or root}"
        ) from error

    for current_text, directories, names in os.walk(
        root, followlinks=False, onerror=walk_error
    ):
        current = Path(current_text)
        require(current.resolve(strict=True).is_relative_to(root),
                f"{label} traversal이 root를 탈출했습니다: {current}")
        retained_directories = []
        for name in directories:
            child = current / name
            if excluded is not None and Path(os.path.abspath(child)) == excluded:
                continue
            _safe_node(child, f"{label} descendant directory", "directory")
            require(child.resolve(strict=True).is_relative_to(root),
                    f"{label} descendant directory가 root를 탈출했습니다: {child}")
            retained_directories.append(name)
        directories[:] = retained_directories
        for name in names:
            child = current / name
            _safe_node(child, f"{label} descendant file", "file")
            resolved = child.resolve(strict=True)
            require(resolved == child and resolved.is_relative_to(root),
                    f"{label} descendant file이 root를 탈출했습니다: {child}")
            files.append(resolved)
    return sorted(files, key=lambda value: value.relative_to(root).as_posix())


def _bundle_path(base: Path, relative: str, label: str) -> Path:
    """! @brief 절대·탈출 경로를 거부하고 bundle 내부 existing path만 반환합니다. """

    require(isinstance(relative, str) and relative and
            not Path(relative).is_absolute(), f"{label} 상대 경로가 필요합니다")
    relative_path = Path(relative)
    require(relative_path.as_posix() == relative.replace("\\", "/") and
            all(part not in ("", ".", "..") for part in relative_path.parts),
            f"{label} canonical 상대 경로가 필요합니다: {relative}")
    root = _safe_directory_root(base, None, f"{label} bundle root")
    path = root
    for index, part in enumerate(relative_path.parts):
        path = path / part
        status = _safe_node(path, f"{label} bundle node")
        if index < len(relative_path.parts) - 1:
            require(stat.S_ISDIR(status.st_mode),
                    f"{label} 중간 node가 directory가 아닙니다: {path}")
    resolved = path.resolve(strict=True)
    require(resolved == path and resolved.is_relative_to(root),
            f"{label} bundle 경로가 탈출했습니다: {relative}")
    return resolved


def _path_sha256(path: Path) -> str:
    """! @brief file 또는 directory 전체 byte의 결정적 SHA-256을 반환합니다. """

    if path.is_file():
        return file_sha256(path)
    require(path.is_dir(), f"hash 대상이 file/directory가 아닙니다: {path}")
    return directory_sha256(path)


def _arduino_portable_root(image: Path) -> Path:
    """! @brief Arduino image에 결합된 portable provenance directory를 반환합니다. """

    return image.parent / ".m33-w06-portable" / image.name


def freeze_arduino_provenance(entries: Sequence[dict[str, Any]]) -> None:
    """! @brief shard 밖 Builder cache의 record/config byte를 image 옆에 동결합니다. """

    frozen = set()
    for entry in entries:
        source = Path(entry["path"]).resolve()
        if source.suffix.lower() != ".hex" or not source.is_file():
            continue
        if source in frozen:
            continue
        frozen.add(source)
        record_path = source.with_suffix(".nu54-build.json")
        if not record_path.is_file():
            continue
        record = strict_json(record_path)
        live = record.get("source_inputs", {}).get("live_build_record", {})
        live_path = Path(str(live.get("path", ""))).resolve()
        require(
            live_path.is_file()
            and SHA256.fullmatch(str(live.get("sha256"))) is not None
            and file_sha256(live_path) == live["sha256"],
            f"Arduino live build record byte가 다릅니다: {record_path}",
        )
        config = live_path.parent / "zephyr/.config"
        require(config.is_file() and config.stat().st_size > 0,
                f"Arduino resolved config가 없습니다: {record_path}")
        config_artifact = (
            record.get("context", {}).get("resource_audit", {})
            .get("inputs", {}).get("config", {})
        )
        require(
            isinstance(config_artifact, dict)
            and Path(str(config_artifact.get("path", ""))).resolve()
            == config.resolve()
            and config_artifact.get("sha256") == file_sha256(config),
            f"Arduino resolved config provenance가 다릅니다: {record_path}",
        )
        portable = _arduino_portable_root(source)
        require(not portable.exists(),
                f"Arduino portable provenance가 이미 있습니다: {portable}")
        (portable / "zephyr").mkdir(parents=True)
        portable_record = portable / "nucode_arduino_core_build.yml"
        portable_config = portable / "zephyr/.config"
        shutil.copyfile(live_path, portable_record)
        shutil.copyfile(config, portable_config)
        document = {
            "schema_version": 1,
            "kind": "m33_w06_arduino_portable_provenance",
            "image": {
                "identity": source.name,
                "origin": str(record.get("artifacts", {}).get("hex", {}).get("path", "")),
                "sha256": file_sha256(source),
                "size": source.stat().st_size,
            },
            "arduino_record": {
                "identity": record_path.name,
                "sha256": file_sha256(record_path),
            },
            "live_build_record": {
                "identity": portable_record.name,
                "origin": str(live.get("path", "")),
                "sha256": file_sha256(portable_record),
            },
            "resolved_config": {
                "identity": "zephyr/.config",
                "origin": str(config_artifact["path"]),
                "sha256": file_sha256(portable_config),
            },
        }
        document["manifest_sha256"] = canonical_sha256(document)
        atomic_write_json(portable / "manifest.json", document)


def validate_arduino_portable_provenance(
    image: Path,
    record_path: Path,
    record: dict[str, Any],
    identity: dict[str, Any] | None = None,
) -> Path | None:
    """! @brief relocation된 Arduino image의 원본 record/config byte를 재검증합니다. """

    portable = _arduino_portable_root(image)
    if not portable.is_dir():
        return None
    require(
        portable.resolve().is_relative_to(image.parent.resolve()),
        f"Arduino portable provenance가 image tree를 탈출합니다: {portable}",
    )
    manifest = strict_json(portable / "manifest.json")
    checksum = manifest.get("manifest_sha256")
    clone = dict(manifest)
    clone.pop("manifest_sha256", None)
    require(
        set(manifest) == {
            "schema_version", "kind", "image", "arduino_record",
            "live_build_record", "resolved_config", "manifest_sha256",
        }
        and manifest["schema_version"] == 1
        and manifest["kind"] == "m33_w06_arduino_portable_provenance"
        and SHA256.fullmatch(str(checksum)) is not None
        and canonical_sha256(clone) == checksum,
        f"Arduino portable provenance manifest가 잘못됐습니다: {portable}",
    )
    live = record.get("source_inputs", {}).get("live_build_record", {})
    image_artifact = record.get("artifacts", {}).get("hex", {})
    config_artifact = (
        record.get("context", {}).get("resource_audit", {})
        .get("inputs", {}).get("config", {})
    )
    expected = {
        "image": {
            "identity": image.name,
            "origin": str(image_artifact.get("path", "")),
            "sha256": file_sha256(image),
            "size": image.stat().st_size,
        },
        "arduino_record": {
            "identity": record_path.name,
            "sha256": file_sha256(record_path),
        },
        "live_build_record": {
            "identity": "nucode_arduino_core_build.yml",
            "origin": str(live.get("path", "")),
            "sha256": str(live.get("sha256", "")),
        },
        "resolved_config": {
            "identity": "zephyr/.config",
            "origin": str(config_artifact.get("path", "")),
            "sha256": str(config_artifact.get("sha256", "")),
        },
    }
    for key, value in expected.items():
        require(manifest.get(key) == value,
                f"Arduino portable {key} identity가 다릅니다: {portable}")
    portable_record = portable / "nucode_arduino_core_build.yml"
    portable_config = portable / "zephyr/.config"
    require(
        portable_record.is_file()
        and portable_config.is_file()
        and portable_record.resolve().is_relative_to(portable.resolve())
        and portable_config.resolve().is_relative_to(portable.resolve())
        and file_sha256(portable_record) == manifest["live_build_record"]["sha256"]
        and file_sha256(portable_config) == manifest["resolved_config"].get("sha256")
        and manifest["resolved_config"].get("identity") == "zephyr/.config",
        f"Arduino portable record/config byte가 다릅니다: {portable}",
    )
    if identity is not None:
        validate_native_record(portable_record, identity)
    actual_files = {
        path.relative_to(portable).as_posix()
        for path in portable.rglob("*") if path.is_file()
    }
    require(
        actual_files == {
            "manifest.json", "nucode_arduino_core_build.yml", "zephyr/.config",
        },
        f"Arduino portable provenance file 집합이 다릅니다: {portable}",
    )
    return portable_config


def relocate_arduino_config_entries(
    plan: dict[str, Any],
    entries: Sequence[dict[str, Any]],
) -> None:
    """! @brief config slot을 shard 내부의 검증된 portable config로 재결합합니다. """

    by_key = {
        (entry["campaign_id"], entry["name"]): entry
        for entry in entries
    }
    artifacts = build_artifacts(plan)
    for key, entry in by_key.items():
        if artifacts[key]["kind"] != "configuration":
            continue
        binding = key[1].removesuffix("-config")
        candidates = [
            row for row_key, row in by_key.items()
            if row_key[0] == key[0]
            and artifacts[row_key]["kind"] == "target_image"
            and artifacts[row_key]["binding"].replace("-image", "") == binding
        ]
        if len(candidates) != 1:
            continue
        image = Path(candidates[0]["path"]).resolve()
        record_path = adjacent_build_record(image)
        if record_path.suffix.lower() != ".json":
            continue
        config = validate_arduino_portable_provenance(
            image, record_path, strict_json(record_path)
        )
        require(config is not None, f"Arduino portable config가 없습니다: {key}")
        entry["path"] = config.as_posix()


def build_shard_from_plan(
    plan: dict[str, Any],
    shard_plan: dict[str, Any],
    shard_index: int,
    work_root: Path,
    shard_output: Path,
    arduino_cli: Path,
    arduino_config: Path,
    fqbn_prefix: str,
    timeout_seconds: int,
    max_workers: int = DEFAULT_BUILD_WORKERS,
    executor: Callable[..., Any] = subprocess.run,
    identity_validator: Callable[..., dict[str, Any]] = validate_source_lock,
    action_factory: Callable[..., list[dict[str, Any]]] = create_shard_build_actions,
    entry_resolver: Callable[..., list[dict[str, Any]]] = resolve_build_entries,
    plan_validator: Callable[..., None] = validate_plan,
    sdk_root: Path | None = None,
    toolchain_root: Path | None = None,
    run_id: str | None = None,
    run_attempt: str | None = None,
) -> dict[str, Any]:
    """! @brief 한 shard의 action/slot만 build하고 portable immutable manifest를 생성합니다. """

    plan_validator(plan)
    shard_count = shard_plan.get("shard_count")
    require(type(shard_index) is int and type(shard_count) is int and
            0 <= shard_index < shard_count <= MAX_BUILD_SHARDS,
            "build shard index/count가 잘못됐습니다")
    sdk_root = (sdk_root or Path(plan["source"]["sdk_root"])).resolve()
    toolchain_root = (
        toolchain_root or Path(plan["source"]["toolchain_root"])
    ).resolve()
    location = dict(plan["source"])
    location["sdk_root"] = sdk_root.as_posix()
    location["toolchain_root"] = toolchain_root.as_posix()
    validate_source_binding(plan["source"], location)
    work_root = require_external_fresh_root(
        work_root, location, "shard build"
    )
    shard_output = shard_output.resolve()
    require(shard_output.parent == work_root,
            "shard output은 fresh work root 바로 아래여야 합니다")
    before = identity_validator(
        REPOSITORY, sdk_root, toolchain_root,
        plan["source"]["source_revision"],
    )
    source_binding = validate_source_binding(plan["source"], before)
    require(
        (run_id is None and run_attempt is None)
        or (isinstance(run_id, str) and run_id.isdigit()
            and isinstance(run_attempt, str) and run_attempt.isdigit()),
        "shard run ID/attempt가 잘못됐습니다",
    )
    require(arduino_cli.resolve().is_file() and arduino_config.resolve().is_file(),
            "shard Arduino CLI/config가 없습니다")
    work_root.mkdir(parents=True)
    actions = action_factory(
        plan, work_root, sdk_root, toolchain_root,
        arduino_cli.resolve(), arduino_config.resolve(), fqbn_prefix,
    )
    validate_build_shard_plan(shard_plan, plan, actions, shard_count)
    assignments = [
        row for row in shard_plan["assignments"]
        if row["shard"] == shard_index
    ]
    selected_ids = {row["id"] for row in assignments}
    selected_actions = [action for action in actions
                        if action["id"] in selected_ids]
    require([action["id"] for action in selected_actions] ==
            [row["id"] for row in assignments],
            "shard action 순서가 shard plan과 다릅니다")
    slot_keys = {
        (slot["campaign_id"], slot["name"])
        for row in assignments for slot in row["slots"]
    }
    try:
        receipts = execute_build_actions(
            selected_actions, work_root, timeout_seconds,
            max_workers, executor,
        )
        partial_plan = partial_build_plan(plan, slot_keys)
        entries = entry_resolver(partial_plan, selected_actions)
        partial_index = {
            "schema_version": 1,
            "kind": "m33_w06_build_index",
            "plan_sha256": plan["contract_sha256"],
            "source": plan["source"],
            "source_binding": source_binding,
            "transfer_contract": None,
            "entries": entries,
            "actions": receipts,
        }
        validate_index(partial_plan, partial_index, effective_source=before)
        freeze_arduino_provenance(entries)
        relocate_arduino_config_entries(partial_plan, entries)
        validated_entries = validate_index(
            partial_plan, partial_index, effective_source=before
        )
    except Exception as error:
        after_failure = identity_validator(
            REPOSITORY, sdk_root, toolchain_root,
            plan["source"]["source_revision"],
        )
        if after_failure != before:
            raise ArtifactFailure("실패한 shard build 도중 source identity가 변경됐습니다") from error
        raise
    after = identity_validator(
        REPOSITORY, sdk_root, toolchain_root,
        plan["source"]["source_revision"],
    )
    require(after == before, "shard build 도중 source identity가 변경됐습니다")
    artifact_contract = build_artifacts(plan)
    validated_by_key = {
        (row["campaign_id"], row["name"]): row
        for row in validated_entries
    }
    entry_rows = []
    for entry in entries:
        key = (entry["campaign_id"], entry["name"])
        source = Path(entry["path"]).resolve()
        artifact = artifact_contract[key]
        provenance_paths = set()
        validated = validated_by_key[key]
        if isinstance(validated.get("build_record"), dict):
            provenance_paths.add(Path(validated["build_record"]["path"]).resolve())
        for config in validated.get("configs", []):
            provenance_paths.add(Path(config["path"]).resolve())
        portable = _arduino_portable_root(source)
        if portable.is_dir():
            provenance_paths.update(
                path.resolve() for path in portable.rglob("*") if path.is_file()
            )
        provenance = [
            {
                "path": _portable_path(path, work_root,
                                       "shard provenance file"),
                "origin_path": path.as_posix(),
                "sha256": file_sha256(path),
            }
            for path in sorted(provenance_paths,
                               key=lambda value: value.as_posix().casefold())
        ]
        entry_rows.append({
            "campaign_id": key[0],
            "name": key[1],
            "kind": artifact["kind"],
            "recipe_sha256": canonical_sha256(artifact.get("recipe")),
            "path": _portable_path(source, work_root, "shard build entry"),
            "origin_path": source.as_posix(),
            "sha256": _path_sha256(source),
            "provenance": provenance,
        })
    receipt_by_id = {receipt["id"]: receipt for receipt in receipts}
    action_rows = []
    for assignment, action in zip(assignments, selected_actions, strict=True):
        receipt = receipt_by_id[action["id"]]
        stdout = Path(receipt["stdout"]["path"])
        stderr = Path(receipt["stderr"]["path"])
        output = Path(action["output"])
        action_rows.append({
            "ordinal": assignment["ordinal"],
            "id": action["id"],
            "kind": action["kind"],
            "depends_on": action["depends_on"],
            "receipt": receipt,
            "output": {
                "path": _portable_path(output, work_root, "shard action output"),
                "sha256": directory_sha256(output),
            },
            "stdout": {
                "path": _portable_path(stdout, work_root, "shard stdout"),
                "sha256": file_sha256(stdout),
            },
            "stderr": {
                "path": _portable_path(stderr, work_root, "shard stderr"),
                "sha256": file_sha256(stderr),
            },
        })
    document = {
        "schema_version": 1,
        "kind": "m33_w06_build_shard_result",
        "status": "BUILD_ONLY",
        "functional_hil": "NOT_RUN",
        "source": plan["source"],
        "source_binding": source_binding,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "origin_root": work_root.as_posix(),
        "plan_sha256": plan["contract_sha256"],
        "shard_plan_sha256": shard_plan["contract_sha256"],
        "shard_index": shard_index,
        "shard_count": shard_count,
        "action_count": len(action_rows),
        "build_slot_count": len(entry_rows),
        "actions": action_rows,
        "entries": entry_rows,
    }
    document["manifest_sha256"] = canonical_sha256(document)
    atomic_write_json(shard_output, document)
    recorded = identity_validator(
        REPOSITORY, sdk_root, toolchain_root,
        plan["source"]["source_revision"],
    )
    if recorded != before:
        shard_output.unlink()
        raise ArtifactFailure("shard manifest 기록 중 source identity가 변경됐습니다")
    return document


def validate_build_shard_manifest(
    document: dict[str, Any],
    manifest_path: Path,
    plan: dict[str, Any],
    shard_plan: dict[str, Any],
    effective_source: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """! @brief shard manifest의 schema·source·slot recipe·portable byte hash를 재검증합니다. """

    manifest_parent = _safe_directory_root(
        manifest_path.parent, None, "build shard manifest parent"
    )
    manifest_path = _safe_regular_file(
        manifest_path, manifest_parent, "build shard manifest"
    )

    required = {
        "schema_version", "kind", "status", "functional_hil", "source",
        "source_binding", "run_id", "run_attempt", "origin_root",
        "plan_sha256", "shard_plan_sha256", "shard_index", "shard_count",
        "action_count", "build_slot_count", "actions", "entries",
        "manifest_sha256",
    }
    checksum = document.get("manifest_sha256")
    clone = dict(document)
    clone.pop("manifest_sha256", None)
    require(set(document) == required and document["schema_version"] == 1 and
            document["kind"] == "m33_w06_build_shard_result" and
            document["status"] == "BUILD_ONLY" and
            document["functional_hil"] == "NOT_RUN" and
            document["source"] == plan["source"] and
            (document.get("run_id") is None or
             (isinstance(document.get("run_id"), str) and
              document["run_id"].isdigit())) and
            ((document.get("run_id") is None and
              document.get("run_attempt") is None) or
             (isinstance(document.get("run_attempt"), str) and
              document["run_attempt"].isdigit())) and
            isinstance(document["origin_root"], str) and
            Path(document["origin_root"]).is_absolute() and
            document["plan_sha256"] == plan["contract_sha256"] and
            document["shard_plan_sha256"] == shard_plan["contract_sha256"] and
            document["shard_count"] == shard_plan["shard_count"] and
            checksum == canonical_sha256(clone),
            "build shard manifest schema/source/hash가 다릅니다")
    validate_recorded_source_binding(
        document, plan["source"], "build shard manifest"
    )
    index = document["shard_index"]
    require(type(index) is int and 0 <= index < document["shard_count"],
            "build shard manifest index가 잘못됐습니다")
    expected_actions = [
        row for row in shard_plan["assignments"] if row["shard"] == index
    ]
    expected_slots = {
        (slot["campaign_id"], slot["name"]): slot
        for row in expected_actions for slot in row["slots"]
    }
    require(isinstance(document["actions"], list) and
            len(document["actions"]) == document["action_count"] ==
            len(expected_actions) and
            isinstance(document["entries"], list) and
            len(document["entries"]) == document["build_slot_count"] ==
            len(expected_slots),
            "build shard manifest action/slot denominator가 다릅니다")
    base = manifest_parent
    origin = Path(document["origin_root"])
    action_rows = []
    for observed, expected in zip(document["actions"], expected_actions, strict=True):
        require(isinstance(observed, dict) and set(observed) == {
            "ordinal", "id", "kind", "depends_on", "receipt",
            "output", "stdout", "stderr",
        } and observed["ordinal"] == expected["ordinal"] and
                observed["id"] == expected["id"] and
                observed["kind"] == expected["kind"] and
                observed["depends_on"] == expected["depends_on"],
                "build shard action identity/order가 다릅니다")
        receipt = observed["receipt"]
        require(isinstance(receipt, dict) and
                receipt.get("ordinal") == expected["ordinal"] and
                receipt.get("id") == expected["id"] and
                receipt.get("kind") == expected["kind"] and
                receipt.get("depends_on") == expected["depends_on"] and
                receipt.get("shell") is False and
                receipt.get("timed_out") is False and
                receipt.get("exit_code") == 0 and
                receipt.get("launch_error") is None and
                "postprocess_error" in receipt and
                receipt.get("postprocess_error") is None and
                receipt.get("output_exists") is True,
                "build shard action receipt가 성공을 입증하지 않습니다")
        for label in ("output", "stdout", "stderr"):
            reference = observed[label]
            require(isinstance(reference, dict) and
                    set(reference) == {"path", "sha256"} and
                    SHA256.fullmatch(str(reference["sha256"])),
                    f"build shard {label} reference가 잘못됐습니다")
            source = _bundle_path(base, reference["path"], f"shard {label}")
            require(_path_sha256(source) == reference["sha256"],
                    f"build shard {label} hash가 다릅니다")
            receipt_path = (
                receipt[label]["path"] if label in {"stdout", "stderr"}
                else receipt["output"]
            )
            require(
                Path(str(receipt_path)).resolve()
                == (origin / reference["path"]).resolve(),
                f"build shard {label} origin/relative identity가 다릅니다",
            )
        action_rows.append(receipt)
    artifact_contract = build_artifacts(plan)
    entry_rows = []
    seen = set()
    for entry in document["entries"]:
        require(isinstance(entry, dict) and set(entry) == {
            "campaign_id", "name", "kind", "recipe_sha256", "path",
            "origin_path", "sha256", "provenance",
        }, "build shard entry schema가 잘못됐습니다")
        key = (entry["campaign_id"], entry["name"])
        expected = expected_slots.get(key)
        require(expected is not None and key not in seen and
                entry["kind"] == expected["kind"] and
                entry["recipe_sha256"] == expected["recipe_sha256"] and
                expected["kind"] == artifact_contract[key]["kind"] and
                entry["recipe_sha256"] ==
                canonical_sha256(artifact_contract[key].get("recipe")),
                f"build shard entry identity/recipe가 다릅니다: {key}")
        source = _bundle_path(base, entry["path"], "shard build entry")
        require(Path(str(entry["origin_path"])).is_absolute() and
                Path(entry["origin_path"]).resolve() ==
                (origin / entry["path"]).resolve() and
                SHA256.fullmatch(str(entry["sha256"])) is not None and
                _path_sha256(source) == entry["sha256"],
                f"build shard entry origin/hash가 다릅니다: {key}")
        provenance = entry["provenance"]
        require(isinstance(provenance, list),
                f"build shard entry provenance가 배열이 아닙니다: {key}")
        seen_provenance = set()
        for reference in provenance:
            require(isinstance(reference, dict) and set(reference) == {
                "path", "origin_path", "sha256",
            }, f"build shard provenance schema가 잘못됐습니다: {key}")
            relative = reference["path"]
            provenance_path = _bundle_path(
                base, relative, "shard provenance file"
            )
            require(
                relative not in seen_provenance
                and provenance_path.is_file()
                and Path(str(reference["origin_path"])).resolve() ==
                (origin / relative).resolve()
                and SHA256.fullmatch(str(reference["sha256"])) is not None
                and file_sha256(provenance_path) == reference["sha256"],
                f"build shard provenance origin/hash가 다릅니다: {key}",
            )
            seen_provenance.add(relative)
        if entry["kind"] == "target_image":
            require(provenance,
                    f"target image provenance가 비어 있습니다: {key}")
        seen.add(key)
        entry_rows.append({
            "campaign_id": key[0],
            "name": key[1],
            "path": source.as_posix(),
            "sha256": entry["sha256"],
            "origin_path": entry["origin_path"],
            "relative_path": entry["path"],
            "shard_manifest_sha256": document["manifest_sha256"],
            "shard_index": index,
            "run_id": document["run_id"],
            "run_attempt": document["run_attempt"],
        })
    require(seen == set(expected_slots), "build shard entry가 누락됐습니다")
    return entry_rows, action_rows


def aggregate_build_shards(
    plan: dict[str, Any],
    shard_plan: dict[str, Any],
    shards_root: Path,
    output: Path,
    index_output: Path,
    runtime_output: Path,
    actions: Sequence[dict[str, Any]],
    sdk_root: Path | None = None,
    toolchain_root: Path | None = None,
    transfer_contract: dict[str, Any] | None = None,
    identity_validator: Callable[..., dict[str, Any]] = validate_source_lock,
    plan_validator: Callable[..., None] = validate_plan,
    expected_denominator: tuple[int, int, int] = (150, 141, 9),
    validate_source_digests: bool = True,
) -> dict[str, Any]:
    """! @brief 모든 immutable shard를 강검증해 141 build/9 runtime aggregate를 만듭니다. """

    plan_validator(plan)
    validate_build_shard_plan(
        shard_plan, plan, actions, shard_plan.get("shard_count")
    )
    total_count, build_count, runtime_count = expected_denominator
    require(len(plan_artifacts(plan)) == total_count and
            len(build_artifacts(plan)) == build_count and
            len(runtime_artifacts(plan)) == runtime_count,
            "W06 aggregate slot denominator가 계약과 다릅니다")
    bound_sdk = (sdk_root or Path(plan["source"]["sdk_root"])).resolve()
    bound_toolchain = (
        toolchain_root or Path(plan["source"]["toolchain_root"])
    ).resolve()
    current = identity_validator(
        REPOSITORY,
        bound_sdk,
        bound_toolchain,
        plan["source"]["source_revision"],
    )
    source_binding = validate_source_binding(plan["source"], current)
    shards_root = _safe_directory_root(
        shards_root, None, "downloaded shard root"
    )
    require_external_root(shards_root, current, "downloaded shard")
    shard_count = shard_plan["shard_count"]
    contract = (
        validate_transfer_contract(transfer_contract)
        if transfer_contract is not None else None
    )
    if contract is not None:
        require(shard_count == contract["shard_count"] == 4,
                "transfer contract와 shard plan 분모가 다릅니다")
        bundle_roots = [
            _safe_directory_root(
                shards_root / artifact,
                shards_root,
                f"shard artifact directory {artifact}",
            )
            for artifact in contract["artifacts"]
        ]
        manifests = []
        for index, root in enumerate(bundle_roots):
            expected = root / f"m33-w06-shard-{index}.json"
            manifests.append(_safe_regular_file(
                expected, root, "shard artifact manifest"
            ))
        discovered = [
            path for path in _safe_directory_files(
                shards_root, "downloaded shard root"
            )
            if re.fullmatch(r"m33-w06-shard-[0-9]+\.json", path.name)
        ]
        require(
            sorted(discovered) == sorted(manifests),
            "download root에 계약 밖 shard manifest가 있습니다",
        )
    else:
        manifests = [
            path for path in _safe_directory_files(
                shards_root, "downloaded shard root"
            )
            if re.fullmatch(r"m33-w06-shard-[0-9]+\.json", path.name)
        ]
    require(len(manifests) == shard_count,
            f"build shard manifest는 정확히 {shard_count}개여야 합니다")
    entries = []
    receipts = []
    shard_rows = []
    relocations = []
    seen_indices = set()
    for manifest_path in manifests:
        document = strict_json(manifest_path)
        index = document.get("shard_index")
        require(index not in seen_indices, "build shard index가 중복됐습니다")
        shard_entries, shard_receipts = validate_build_shard_manifest(
            document, manifest_path, plan, shard_plan, current
        )
        if contract is not None:
            require(
                document["run_id"] == contract["run_id"]
                and document["run_attempt"] == contract["run_attempt"]
                and manifest_path.parent.name == contract["artifacts"][index],
                "shard run/attempt/artifact identity가 transfer contract와 다릅니다",
            )
        else:
            require(document["run_id"] is None and
                    document["run_attempt"] is None,
                    "run ID가 있는 shard에는 transfer contract가 필요합니다")
        artifact_name = manifest_path.parent.name
        for entry in shard_entries:
            entry["artifact_name"] = artifact_name
        seen_indices.add(index)
        entries.extend(shard_entries)
        receipts.extend(shard_receipts)
        relocations.append({
            "origin_root": document["origin_root"],
            "bundle_root": manifest_path.resolve().parent.as_posix(),
            "manifest_sha256": document["manifest_sha256"],
            "manifest_path": manifest_path.resolve().as_posix(),
            "shard_index": index,
            "run_id": document["run_id"],
            "run_attempt": document["run_attempt"],
            "artifact_name": artifact_name,
        })
        shard_rows.append({
            "shard_index": index,
            "manifest": {
                "path": _portable_path(manifest_path, shards_root,
                                       "shard manifest"),
                "sha256": file_sha256(manifest_path),
            },
            "manifest_sha256": document["manifest_sha256"],
            "action_count": document["action_count"],
            "build_slot_count": document["build_slot_count"],
        })
    require(seen_indices == set(range(shard_count)),
            "build shard index denominator가 불완전합니다")
    expected_keys = set(build_artifacts(plan))
    observed_keys = [(row["campaign_id"], row["name"]) for row in entries]
    require(len(observed_keys) == len(set(observed_keys)) == build_count and
            set(observed_keys) == expected_keys,
            "aggregate build slot이 누락·중복됐습니다")
    expected_action_ids = [row["id"] for row in shard_plan["assignments"]]
    require(len(receipts) == len(expected_action_ids) and
            sorted(receipt["id"] for receipt in receipts) ==
            sorted(expected_action_ids),
            "aggregate action receipt가 누락·중복됐습니다")
    receipts.sort(key=lambda row: row["ordinal"])
    require([receipt["id"] for receipt in receipts] == expected_action_ids,
            "aggregate action receipt ordinal이 다릅니다")
    index = {
        "schema_version": 1,
        "kind": "m33_w06_build_index",
        "plan_sha256": plan["contract_sha256"],
        "source": plan["source"],
        "source_binding": source_binding,
        "transfer_contract": contract,
        "entries": sorted(entries, key=lambda row: (row["campaign_id"], row["name"])),
        "actions": receipts,
        "relocations": sorted(
            relocations, key=lambda row: row["origin_root"].casefold()
        ),
    }
    validate_index(
        plan,
        index,
        validate_source_digests=validate_source_digests,
        effective_source=current,
    )
    runtime = runtime_inputs_template(plan, current, contract)
    validate_runtime_inputs(
        plan,
        runtime,
        require_complete=False,
        effective_source=current,
        transfer_contract=contract,
    )
    output = output.resolve()
    index_output = index_output.resolve()
    runtime_output = runtime_output.resolve()
    require(output.parent == shards_root and index_output.parent == shards_root and
            runtime_output.parent == shards_root and
            len({output, index_output, runtime_output}) == 3 and
            not any(path.exists() for path in (output, index_output, runtime_output)),
            "aggregate outputs은 shard root의 서로 다른 새 파일이어야 합니다")
    portable_entries = []
    for row in index["entries"]:
        key = (row["campaign_id"], row["name"])
        source = Path(row["path"])
        artifact = build_artifacts(plan)[key]
        portable_entries.append({
            "campaign_id": key[0],
            "name": key[1],
            "kind": artifact["kind"],
            "recipe_sha256": canonical_sha256(artifact.get("recipe")),
            "path": _portable_path(source, shards_root, "aggregate build entry"),
            "sha256": _path_sha256(source),
        })
    index_bytes = json_output_bytes(index)
    runtime_bytes = json_output_bytes(runtime)
    document = {
        "schema_version": 1,
        "kind": "m33_w06_ci_build_aggregate",
        "status": "BUILD_ONLY",
        "functional_hil": "NOT_RUN",
        "physical_campaigns": "NOT_RUN",
        "soak": "NOT_RUN",
        "source": plan["source"],
        "source_binding": source_binding,
        "transfer_contract": contract,
        "plan_sha256": plan["contract_sha256"],
        "shard_plan_sha256": shard_plan["contract_sha256"],
        "total_slot_count": total_count,
        "build_slot_count": build_count,
        "runtime_slot_count": runtime_count,
        "runtime_status": "NOT_PROVIDED",
        "shards": sorted(shard_rows, key=lambda row: row["shard_index"]),
        "entries": portable_entries,
        "build_index": {
            "path": index_output.name,
            "sha256": hashlib.sha256(index_bytes).hexdigest(),
        },
        "runtime_inputs": {
            "path": runtime_output.name,
            "sha256": hashlib.sha256(runtime_bytes).hexdigest(),
        },
    }
    document["aggregate_sha256"] = canonical_sha256(document)
    output_bytes_value = json_output_bytes(document)
    prewrite = identity_validator(
        REPOSITORY,
        bound_sdk,
        bound_toolchain,
        plan["source"]["source_revision"],
    )
    require(prewrite == current, "aggregate 기록 전 source identity가 변경됐습니다")
    publish_json_set((
        (index_output, index_bytes),
        (runtime_output, runtime_bytes),
        (output, output_bytes_value),
    ))
    postwrite = identity_validator(
        REPOSITORY,
        bound_sdk,
        bound_toolchain,
        plan["source"]["source_revision"],
    )
    if postwrite != current:
        for path in (output, index_output, runtime_output):
            if path.is_file() and not path.is_symlink():
                path.unlink()
        raise ArtifactFailure("aggregate 기록 중 source identity가 변경됐습니다")
    return document


def validate_hex(path: Path) -> None:
    """! @brief Intel HEX checksum과 data record 존재를 검사합니다. """

    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ArtifactFailure(f"HEX를 읽지 못했습니다: {path}: {error}") from error
    data_records = 0
    for line in lines:
        require(line.startswith(":") and len(line) >= 11 and len(line) % 2 == 1, f"Intel HEX record 형식이 잘못됐습니다: {path}")
        try:
            record = bytes.fromhex(line[1:])
        except ValueError as error:
            raise ArtifactFailure(f"Intel HEX 문자가 잘못됐습니다: {path}") from error
        require(len(record) == record[0] + 5 and sum(record) & 0xFF == 0, f"Intel HEX checksum/길이가 잘못됐습니다: {path}")
        if record[3] == 0 and record[0] > 0:
            data_records += 1
    require(data_records > 0, f"Intel HEX data record가 없습니다: {path}")


def validate_relocations(
    index: dict[str, Any],
    relocation_root: Path | None = None,
) -> list[dict[str, Any]]:
    """! @brief shard origin을 현재 download root에 결합한 경로 표를 검사합니다. """

    rows = index.get("relocations", [])
    require(isinstance(rows, list), "build index relocations가 배열이 아닙니다")
    contract_value = index.get("transfer_contract")
    contract = (
        validate_transfer_contract(contract_value)
        if contract_value is not None else None
    )
    require(not rows or contract is not None or
            all(row.get("run_id") is None and row.get("run_attempt") is None
                for row in rows
                if isinstance(row, dict)),
            "run-bound relocation에는 transfer contract가 필요합니다")
    if contract is not None:
        require(len(rows) == contract["shard_count"] == 4,
                "transfer contract relocation 분모가 다릅니다")
    validated = []
    origins = set()
    roots = set()
    effective_parent = (
        _safe_directory_root(relocation_root, None, "relocation download root")
        if relocation_root is not None else None
    )
    for row in rows:
        require(isinstance(row, dict) and set(row) == {
            "origin_root", "bundle_root", "manifest_sha256", "manifest_path",
            "shard_index", "run_id", "run_attempt", "artifact_name",
        }, "build index relocation 형식이 잘못됐습니다")
        shard_index = row["shard_index"]
        run_id = row["run_id"]
        run_attempt = row["run_attempt"]
        artifact_name = row["artifact_name"]
        require(isinstance(artifact_name, str) and artifact_name
                and Path(artifact_name).name == artifact_name,
                "build index relocation artifact name이 잘못됐습니다")
        origin = Path(str(row["origin_root"]))
        lexical_root = (
            effective_parent / artifact_name
            if effective_parent is not None else Path(str(row["bundle_root"]))
        )
        expected_parent = (
            effective_parent
            if effective_parent is not None else Path(os.path.abspath(lexical_root)).parent
        )
        root = _safe_directory_root(
            lexical_root, expected_parent, "relocated shard artifact directory"
        )
        manifest_name = Path(str(row["manifest_path"])).name
        lexical_manifest = (
            root / manifest_name
            if effective_parent is not None else Path(str(row["manifest_path"]))
        )
        manifest_path = _safe_regular_file(
            lexical_manifest, root, "relocated shard manifest"
        )
        require(
            origin.is_absolute()
            and root.is_absolute()
            and manifest_path.parent == root
            and manifest_path.name == f"m33-w06-shard-{shard_index}.json"
            and type(shard_index) is int
            and root.name == artifact_name
            and SHA256.fullmatch(str(row["manifest_sha256"])) is not None,
            "build index relocation root/hash가 잘못됐습니다",
        )
        manifests = [
            path for path in _safe_directory_files(
                root, "relocated shard artifact directory"
            )
            if re.fullmatch(r"m33-w06-shard-[0-9]+\.json", path.name)
        ]
        require(len(manifests) == 1 and manifests[0] == manifest_path,
                "build index relocation shard manifest를 유일하게 찾지 못했습니다")
        manifest = strict_json(manifest_path)
        checksum = manifest.get("manifest_sha256")
        clone = dict(manifest)
        clone.pop("manifest_sha256", None)
        require(
            checksum == row["manifest_sha256"]
            and manifest.get("origin_root") == origin.as_posix()
            and manifest.get("shard_index") == shard_index
            and manifest.get("run_id") == run_id
            and manifest.get("run_attempt") == run_attempt
            and canonical_sha256(clone) == checksum,
            "build index relocation shard manifest identity/hash가 다릅니다",
        )
        manifest_entries = manifest.get("entries")
        require(isinstance(manifest_entries, list),
                "build index relocation shard entries가 없습니다")
        for entry in manifest_entries:
            require(isinstance(entry, dict) and isinstance(entry.get("path"), str)
                    and isinstance(entry.get("origin_path"), str)
                    and isinstance(entry.get("provenance"), list),
                    "build index relocation shard entry가 잘못됐습니다")
            entry_path = _bundle_path(root, entry["path"],
                                      "relocated shard entry")
            require(
                Path(entry["origin_path"]).resolve() ==
                (origin / entry["path"]).resolve()
                and SHA256.fullmatch(str(entry.get("sha256"))) is not None
                and _path_sha256(entry_path) == entry["sha256"],
                "build index relocation shard entry byte/hash가 다릅니다",
            )
            for reference in entry["provenance"]:
                require(isinstance(reference, dict)
                        and set(reference) == {
                            "path", "origin_path", "sha256",
                        }, "build index relocation provenance가 잘못됐습니다")
                provenance_path = _bundle_path(
                    root, reference["path"], "relocated shard provenance"
                )
                require(
                    provenance_path.is_file()
                    and Path(reference["origin_path"]).resolve() ==
                    (origin / reference["path"]).resolve()
                    and SHA256.fullmatch(str(reference["sha256"])) is not None
                    and file_sha256(provenance_path) == reference["sha256"],
                    "build index relocation provenance byte/hash가 다릅니다",
                )
        if contract is not None:
            require(
                run_id == contract["run_id"]
                and run_attempt == contract["run_attempt"]
                and 0 <= shard_index < contract["shard_count"]
                and artifact_name == contract["artifacts"][shard_index],
                "build index relocation이 transfer contract와 다릅니다",
            )
        else:
            require(run_id is None and run_attempt is None,
                    "run-bound relocation에는 transfer contract가 필요합니다")
        origin_key = origin.as_posix().casefold().rstrip("/")
        root_key = root.as_posix().casefold().rstrip("/")
        require(origin_key not in origins and root_key not in roots,
                "build index relocation root가 중복됩니다")
        origins.add(origin_key)
        roots.add(root_key)
        validated.append({
            "origin_root": origin.as_posix(),
            "bundle_root": root.as_posix(),
            "manifest_sha256": row["manifest_sha256"],
            "manifest_path": manifest_path.as_posix(),
            "shard_index": shard_index,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "artifact_name": artifact_name,
        })
    if contract is not None:
        require(
            sorted(row["shard_index"] for row in validated) == list(range(4)),
            "build index relocation shard denominator가 불완전합니다",
        )
    return validated


def resolve_relocated_path(
    value: str,
    relocations: Sequence[dict[str, str]],
    label: str,
) -> Path:
    """! @brief origin 절대 경로를 검증된 shard 상대 경로로 안전하게 재결합합니다. """

    require(isinstance(value, str) and value, f"{label} 경로가 없습니다")
    source = Path(value)
    require(source.is_absolute(), f"{label} origin 절대 경로가 아닙니다")
    if not relocations:
        require(source.exists(), f"{label} 경로가 없습니다: {source}")
        return source.resolve()
    matches = []
    for row in relocations:
        origin = Path(row["origin_root"])
        try:
            relative = source.relative_to(origin)
        except ValueError:
            continue
        target = (Path(row["bundle_root"]) / relative).resolve()
        root = Path(row["bundle_root"]).resolve()
        require(target.is_relative_to(root), f"{label} relocation이 bundle을 탈출합니다")
        if target.exists():
            matches.append(target)
    require(len(matches) == 1,
            f"{label} relocation 경로를 유일하게 찾지 못했습니다: {value}")
    return matches[0]


def discover_relocation_root(
    index_path: Path,
    index: dict[str, Any],
    requested: Path | None = None,
) -> Path | None:
    """! @brief control artifact와 sibling shard directory의 download root를 유일하게 찾습니다. """

    rows = index.get("relocations", [])
    if not rows:
        require(requested is None, "relocation이 없는 index에 shards root가 지정됐습니다")
        return None
    names = [row.get("artifact_name") for row in rows if isinstance(row, dict)]
    require(len(names) == len(rows) and all(isinstance(name, str) and name
                                            for name in names),
            "relocation artifact name이 없습니다")
    if requested is not None:
        candidates = [requested.resolve()]
    else:
        parent = index_path.resolve().parent
        candidates = [parent, parent.parent]
    matches = [
        candidate for candidate in dict.fromkeys(candidates)
        if candidate.is_dir()
        and all((candidate / str(name)).is_dir() for name in names)
    ]
    require(len(matches) == 1,
            "shard artifact download root를 유일하게 찾지 못했습니다")
    return matches[0]


def native_record_values(path: Path) -> dict[str, str]:
    """! @brief native YAML build record의 고정 scalar를 읽습니다. """

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ArtifactFailure(f"native build record를 읽지 못했습니다: {path}: {error}") from error
    values: dict[str, str] = {}
    for key in NATIVE_RECORD_FIELDS:
        match = re.search(rf"^  {re.escape(key)}:\s*'?([^'\r\n]+)'?\s*$", text, re.MULTILINE)
        require(match is not None, f"native build record 필드가 없습니다: {path}:{key}")
        values[key] = match.group(1).strip()
    return values


def validate_native_record(path: Path, identity: dict[str, Any]) -> dict[str, str]:
    """! @brief native build record의 revision·source hash·toolchain을 검증합니다. """

    values = native_record_values(path)
    expected = {
        "core_revision": identity["source_revision"][:12],
        "board_revision": identity["board_revision"][:12],
        "ncs_revision": identity["ncs_revision"][:12],
        "zephyr_revision": identity["zephyr_revision"][:12],
        "board": "nrf54l15dk",
        "board_qualifiers": "nrf54l15/cpuapp/nu54dk",
        "toolchain_variant": "zephyr",
        "cxx_compiler": "GNU 14.3.0",
    }
    for key, value in expected.items():
        require(values[key] == value, f"native build record drift: {path}:{key}")
    for key in ("core_source_sha256", "application_source_sha256", "board_source_sha256"):
        require(SHA256.fullmatch(values[key]) is not None, f"native source hash 형식이 잘못됐습니다: {path}:{key}")
    suffix = f"/toolchains/{identity['toolchain_bundle_id']}/opt/zephyr-sdk"
    require(values["toolchain_path"].replace("\\", "/").casefold().endswith(suffix.casefold()), "native toolchain bundle이 다릅니다")
    return values


def validate_arduino_revision_provenance(
    record: dict[str, Any],
    identity: dict[str, Any],
    path: Path,
) -> dict[str, Any]:
    """! @brief Arduino library·feature·source graph와 revision identity를 결속합니다. """

    expected_revisions = {
        "NUCODE_CORE_REVISION": identity["source_revision"],
        "NUCODE_BOARD_REVISION": identity["board_revision"],
        "NUCODE_NCS_REVISION": identity["ncs_revision"],
        "NUCODE_ZEPHYR_REVISION": identity["zephyr_revision"],
    }
    source_inputs = record.get("source_inputs")
    context = record.get("context")
    cache = record.get("cache")
    require(
        isinstance(source_inputs, dict)
        and isinstance(context, dict)
        and isinstance(cache, dict),
        f"Arduino provenance root 형식이 잘못됐습니다: {path}",
    )
    selected_libraries = context.get("selected_libraries")
    require(
        isinstance(selected_libraries, list)
        and all(isinstance(value, str) and value
                for value in selected_libraries)
        and len(selected_libraries) == len(set(selected_libraries)),
        f"Arduino selected library 형식이 잘못됐습니다: {path}",
    )
    selected_revision_libraries = {
        value for value in selected_libraries
        if value in ARDUINO_REVISION_FAMILIES
    }
    expected_families = {
        ARDUINO_REVISION_FAMILIES[value]
        for value in selected_revision_libraries
    }
    input_manifest = cache.get("input_manifest")
    require(
        isinstance(input_manifest, dict),
        f"Arduino cache input manifest 형식이 잘못됐습니다: {path}",
    )
    configuration = input_manifest.get("configuration")
    selected_features = (
        configuration.get("selected_features")
        if isinstance(configuration, dict)
        else None
    )
    require(
        isinstance(selected_features, list),
        f"Arduino selected feature 형식이 잘못됐습니다: {path}",
    )
    feature_ids = [
        feature.get("id") if isinstance(feature, dict) else None
        for feature in selected_features
    ]
    require(
        all(isinstance(value, str) and value for value in feature_ids)
        and len(feature_ids) == len(set(feature_ids)),
        f"Arduino selected feature identity가 잘못됐습니다: {path}",
    )
    revision_feature_ids = {
        value for value in feature_ids
        if value in ARDUINO_REVISION_FEATURES.values()
    }
    expected_feature_ids = {
        ARDUINO_REVISION_FEATURES[value]
        for value in selected_revision_libraries
    }
    require(
        revision_feature_ids == expected_feature_ids,
        f"Arduino selected library/cache feature가 다릅니다: {path}",
    )

    platform_root_value = context.get("platform_root")
    require(
        isinstance(platform_root_value, str)
        and platform_root_value
        and Path(platform_root_value).is_absolute(),
        f"Arduino platform root 형식이 잘못됐습니다: {path}",
    )
    platform_root = Path(platform_root_value).resolve()
    source_rows = source_inputs.get("sources")
    require(
        isinstance(source_rows, list),
        f"Arduino source graph 형식이 잘못됐습니다: {path}",
    )
    source_libraries = set()
    logical_identities = set()
    source_paths = set()
    library_roots = {
        library: (platform_root / "libraries" / library).resolve()
        for library in ARDUINO_REVISION_FAMILIES
    }
    for row in source_rows:
        logical_identity = (
            row.get("logical_identity") if isinstance(row, dict) else None
        )
        source_path_value = (
            row.get("source_path") if isinstance(row, dict) else None
        )
        require(
            isinstance(logical_identity, str)
            and logical_identity
            and isinstance(source_path_value, str)
            and source_path_value
            and Path(source_path_value).is_absolute(),
            f"Arduino source graph identity/path 형식이 잘못됐습니다: {path}",
        )
        source_path = Path(source_path_value).resolve()
        source_key = source_path.as_posix().casefold()
        require(
            logical_identity not in logical_identities
            and source_key not in source_paths,
            f"Arduino source graph identity/path가 중복됐습니다: {path}",
        )
        logical_identities.add(logical_identity)
        source_paths.add(source_key)
        match = re.fullmatch(
            r"platform:libraries/([^/]+)/(.+)", logical_identity
        )
        logical_library = match.group(1) if match is not None else None
        path_library = None
        relative_source = None
        for library, library_root in library_roots.items():
            try:
                relative = source_path.relative_to(library_root)
            except ValueError:
                continue
            require(
                relative.parts,
                f"Arduino source path가 library file이 아닙니다: {path}",
            )
            path_library = library
            relative_source = relative
            break
        if logical_library in ARDUINO_REVISION_FAMILIES or path_library is not None:
            require(
                logical_library == path_library
                and relative_source is not None
                and logical_identity == (
                    f"platform:libraries/{path_library}/"
                    f"{relative_source.as_posix()}"
                ),
                f"Arduino source graph identity/path가 다릅니다: {path}",
            )
            source_libraries.add(str(path_library))
    require(
        source_libraries == selected_revision_libraries,
        f"Arduino selected library/source graph가 다릅니다: {path}",
    )

    unknown_families = {
        key for key in source_inputs
        if key.startswith("m31_")
        and key.endswith("_revisions")
        and key not in ARDUINO_REVISION_FAMILIES.values()
    }
    require(
        not unknown_families,
        f"Arduino unknown revision family가 있습니다: {path}",
    )
    revision_families = {
        key: source_inputs[key]
        for key in ARDUINO_REVISION_FAMILIES.values()
        if key in source_inputs
    }
    require(
        set(revision_families) == expected_families,
        f"Arduino selected library/revision family가 다릅니다: {path}",
    )
    require(
        all(values == expected_revisions
            for values in revision_families.values()),
        f"Arduino build revision이 다릅니다: {path}",
    )

    adapter = input_manifest.get("adapter")
    board_package = input_manifest.get("board_package")
    ncs = input_manifest.get("ncs")
    require(
        isinstance(adapter, dict)
        and isinstance(board_package, dict)
        and isinstance(ncs, dict),
        f"Arduino cache revision 형식이 잘못됐습니다: {path}",
    )
    cache_revisions = {
        "NUCODE_CORE_REVISION": adapter.get("embedded_core_revision"),
        "NUCODE_BOARD_REVISION": board_package.get("revision"),
        "NUCODE_NCS_REVISION": ncs.get("nrf_revision"),
        "NUCODE_ZEPHYR_REVISION": ncs.get("zephyr_revision"),
    }
    require(
        cache_revisions == expected_revisions,
        f"Arduino cache revision이 다릅니다: {path}",
    )
    return input_manifest


def validate_arduino_record(path: Path, image: Path, identity: dict[str, Any]) -> dict[str, Any]:
    """! @brief Arduino JSON build record의 exact input과 image byte를 검증합니다. """

    record = strict_json(path)
    input_manifest = validate_arduino_revision_provenance(
        record, identity, path
    )
    artifact = record.get("artifacts", {}).get("hex", {})
    require(isinstance(artifact, dict),
            f"Arduino build image descriptor가 잘못됐습니다: {path}")
    declared_image = Path(str(artifact.get("path", "")))
    portable_config = validate_arduino_portable_provenance(
        image, path, record, identity
    )
    require(
        (
            declared_image.resolve() == image.resolve()
            or portable_config is not None
        )
        and artifact.get("size") == image.stat().st_size
        and artifact.get("sha256") == file_sha256(image),
        f"Arduino build image identity가 다릅니다: {path}",
    )
    require(record.get("board") == BOARD_TARGET, f"Arduino build board가 다릅니다: {path}")
    bundle = input_manifest.get("toolchain", {}).get("bundle_id")
    require(bundle == identity["toolchain_bundle_id"], f"Arduino toolchain bundle이 다릅니다: {path}")
    return record


def validate_profile_record(
    path: Path,
    image: Path,
    identity: dict[str, Any],
    expected_family: str,
    expected_role: str,
    relocations: Sequence[dict[str, str]] = (),
) -> dict[str, Any]:
    """! @brief M33 profile build record를 image와 exact source에 결합합니다. """

    record = strict_json(path)
    require(
        record.get("schema") == "nucode-m33-profile-build-v1"
        and record.get("family") == expected_family
        and record.get("role") == expected_role,
        f"profile build record schema/family/role이 다릅니다: {path}",
    )
    require(record.get("source_revision") == identity["source_revision"], f"profile Core revision이 다릅니다: {path}")
    record_image = resolve_relocated_path(
        str(record.get("image", "")), relocations, "profile image"
    )
    require(
        record.get("development") is False
        and record_image == image.resolve()
        and record.get("sha256") == file_sha256(image),
        f"profile image identity가 다릅니다: {path}",
    )
    owned = record.get("owned_source_sha256")
    require(
        isinstance(owned, dict)
        and owned
        and all(isinstance(name, str) and SHA256.fullmatch(str(value)) is not None for name, value in owned.items()),
        f"profile source snapshot이 없습니다: {path}",
    )
    hil = REPOSITORY / "tests/hil/nu54dk"
    if str(hil) not in sys.path:
        sys.path.insert(0, str(hil))
    try:
        from m33_profile_build_record import owned_source_hashes

        require(owned == owned_source_hashes(), f"profile source snapshot이 현재 source와 다릅니다: {path}")
    except (OSError, RuntimeError, ValueError) as error:
        raise ArtifactFailure(f"profile source snapshot을 재검증하지 못했습니다: {path}: {error}") from error
    artifacts = record.get("artifacts")
    require(isinstance(artifacts, dict) and set(artifacts) == {"elf", "config", "sysbuild"}, f"profile artifact provenance가 다릅니다: {path}")
    for descriptor in artifacts.values():
        require(isinstance(descriptor, dict) and set(descriptor) == {"path", "sha256"}, f"profile artifact descriptor가 다릅니다: {path}")
        value = resolve_relocated_path(
            str(descriptor["path"]), relocations, "profile artifact"
        )
        require(value.is_file() and file_sha256(value) == descriptor["sha256"], f"profile artifact byte가 다릅니다: {value}")
    return record


def adjacent_build_record(image: Path) -> Path:
    """! @brief runner와 같은 상대경로 규칙으로 build record를 찾습니다. """

    arduino = image.with_suffix(".nu54-build.json")
    if arduino.is_file():
        return arduino
    native = image.parent.parent / "nucode_arduino_core_build.yml"
    require(native.is_file(), f"image의 인접 build record가 없습니다: {image}")
    return native


def validate_diagnostics_manifest(
    path: Path,
    image: Path,
    transport: str,
    identity: dict[str, Any],
) -> Path:
    """! @brief DTM route image를 diagnostics build manifest와 resolved config에 결합합니다. """

    manifest = strict_json(path)
    require(
        manifest.get("source_revision") == identity["source_revision"]
        and manifest.get("board_revision") == identity["board_revision"]
        and manifest.get("ncs_revision") == identity["ncs_revision"]
        and manifest.get("zephyr_revision") == identity["zephyr_revision"],
        f"diagnostics build revision이 다릅니다: {path}",
    )
    route = "dtm_twowire" if transport == "twowire" else "dtm_hci"
    rows = [row for row in manifest.get("results", []) if isinstance(row, dict) and row.get("route") == route]
    require(
        len(rows) == 1
        and rows[0].get("status") == "PASS"
        and rows[0].get("runtime") == "NOT_RUN"
        and rows[0].get("image_sha256") == file_sha256(image),
        f"diagnostics route image identity가 다릅니다: {path}:{route}",
    )
    config = image.parent / ".config"
    require(
        config.is_file() and rows[0].get("config_sha256") == file_sha256(config),
        f"diagnostics route config identity가 다릅니다: {path}:{route}",
    )
    return config


def config_files(path: Path) -> list[Path]:
    """! @brief file 또는 build tree에서 resolved config 파일을 수집합니다. """

    if path.is_file():
        candidate = path.parent / ".config"
        return [candidate] if candidate.is_file() else []
    return sorted(candidate for candidate in path.rglob(".config") if candidate.is_file())


def directory_sha256(path: Path) -> str:
    """! @brief directory의 relative path와 file byte를 고정 순서로 hash합니다. """

    root = _safe_directory_root(path, None, "artifact directory")
    files = _safe_directory_files(root, "artifact directory")
    require(files, f"빈 artifact directory입니다: {path}")
    value = "".join(
        f"{candidate.relative_to(root).as_posix()}:{file_sha256(candidate)}\n"
        for candidate in files
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_recipe_binding(source: Path, recipe: dict[str, Any]) -> None:
    """! @brief image 경로와 build cache가 plan의 역할·phase selector를 반영하는지 검사합니다. """

    builder = recipe.get("builder")
    if builder == "run_zephyr_build.py" and isinstance(recipe.get("scenario"), str):
        require(recipe["scenario"] in source.parts, f"HEX path가 plan scenario와 다릅니다: {source}")
    elif builder == "west_direct":
        selectors = recipe.get("selectors")
        require(isinstance(selectors, list) and selectors, "direct west selector가 없습니다")
        caches = [parent / "CMakeCache.txt" for parent in source.parents[:5]]
        matches = [path for path in caches if path.is_file()]
        require(matches, f"direct west CMakeCache가 없습니다: {source}")
        text = matches[0].read_text(encoding="utf-8", errors="strict")
        for selector in selectors:
            require(isinstance(selector, str) and "=" in selector, f"direct west selector가 잘못됐습니다: {selector}")
            key, value = selector.split("=", 1)
            require(
                re.search(rf"^{re.escape(key)}:[^=]+={re.escape(value)}$", text, re.MULTILINE) is not None,
                f"direct west role selector가 build cache와 다릅니다: {source}",
            )
    elif builder == "arduino-cli":
        record = strict_json(adjacent_build_record(source))
        fqbn = str(record.get("fqbn", ""))
        profile = str(recipe.get("profile", ""))
        sketch_root = Path(str(record.get("cache", {}).get("input_manifest", {}).get("sketch", {}).get("root", "")))
        require(
            fqbn.endswith(f":feature_set={profile}")
            and sketch_root.name == Path(str(recipe.get("application", ""))).name,
            f"Arduino sketch/profile binding이 다릅니다: {source}",
        )


def validate_build_tree_binding(source: Path, name: str, recipe: dict[str, Any]) -> None:
    """! @brief build tree가 plan의 scenario/route 집합을 실제로 포함하는지 검사합니다. """

    builder = recipe.get("builder")
    if builder == "run_zephyr_build.py":
        scenarios = recipe.get("scenarios")
        require(isinstance(scenarios, list) and scenarios, f"build tree scenario가 없습니다: {name}")
        for scenario in scenarios:
            if name == "build-outdir":
                candidate = source / PLATFORM_DIRECTORY / TOOLCHAIN_DIRECTORY / scenario
                require(candidate.is_dir(), f"aggregate build tree에 scenario가 없습니다: {scenario}")
            else:
                require(
                    scenario in source.parts
                    and (source / "domains.yaml").is_file(),
                    f"exact sysbuild tree가 scenario와 다릅니다: {name}:{scenario}",
                )
    elif builder == "m33_diagnostics.py":
        routes = recipe.get("routes")
        require(isinstance(routes, list) and routes, "diagnostics route가 없습니다")
        for route in routes:
            require(
                (source / route / "CMakeCache.txt").is_file()
                and (source / route / "zephyr/zephyr.hex").is_file(),
                f"diagnostics build tree route가 없습니다: {route}",
            )
    else:
        raise ArtifactFailure(f"build tree recipe를 검증할 수 없습니다: {builder}")


def validate_current_source_record(
    image: Path,
    application: str,
    identity: dict[str, Any],
) -> None:
    """! @brief 공용 HIL validator로 build record의 실제 source digest를 다시 계산합니다. """

    record = adjacent_build_record(image)
    if record.suffix.lower() == ".json" and _arduino_portable_root(image).is_dir():
        validate_arduino_record(record, image, identity)
        return
    hil = REPOSITORY / "tests/hil/nu54dk"
    if str(hil) not in sys.path:
        sys.path.insert(0, str(hil))
    try:
        from ble_pair_hil_common import validate_build_record

        validate_build_record(
            image,
            identity["source_revision"],
            identity["board_revision"],
            REPOSITORY / application,
        )
    except Exception as error:
        raise ArtifactFailure(f"build record source/config provenance가 다릅니다: {image}: {error}") from error


def validate_soak_build_provenance(
    image: Path,
    config: Path,
    record: Path,
    role: str,
    identity: dict[str, Any],
) -> None:
    """! @brief production soak runner의 full revision·current source 검사를 그대로 적용합니다. """

    require(role in SOAK_ROLES and
            config.resolve() == (image.parent / ".config").resolve() and
            record.resolve() ==
            (image.parent.parent / "m33_w06_build_record.json").resolve(),
            f"soak image/config/build record 인접성이 다릅니다: {role}")
    require(config.is_file() and config.stat().st_size > 0 and record.is_file(),
            f"soak config/build record가 없습니다: {role}")
    hil = REPOSITORY / "tests/hil/nu54dk"
    if str(hil) not in sys.path:
        sys.path.insert(0, str(hil))
    try:
        from m32_regression_soak_run import validate_m33_build_record

        validated = validate_m33_build_record(
            image,
            SimpleNamespace(
                core=identity["source_revision"],
                board=identity["board_revision"],
                ncs=identity["ncs_revision"],
                zephyr=identity["zephyr_revision"],
            ),
            role,
        )
        require(validated["record_sha256"] == file_sha256(record),
                f"soak build record hash가 다릅니다: {role}")
    except Exception as error:
        raise ArtifactFailure(
            f"soak runner build provenance가 다릅니다: {role}: {error}"
        ) from error


def validate_index(
    plan: dict[str, Any],
    index: dict[str, Any],
    validate_source_digests: bool = True,
    effective_source: dict[str, Any] | None = None,
    relocation_root: Path | None = None,
) -> list[dict[str, Any]]:
    """! @brief build index의 완전성·revision·HEX·config provenance를 검증합니다. """

    require(index.get("schema_version") == 1 and index.get("kind") == "m33_w06_build_index", "build index schema가 다릅니다")
    require(index.get("plan_sha256") == plan["contract_sha256"], "build index가 다른 plan을 참조합니다")
    require(index.get("source") == plan["source"], "build index source identity가 다릅니다")
    current = effective_source or plan["source"]
    require_source_binding(index, plan["source"], current, "build index")
    transfer_contract = index.get("transfer_contract")
    if transfer_contract is not None:
        validate_transfer_contract(transfer_contract)
    relocations = validate_relocations(index, relocation_root)
    entries = index.get("entries")
    require(isinstance(entries, list), "build index entries가 배열이 아닙니다")
    expected = build_artifacts(plan)
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    simple_fields = {"campaign_id", "name", "path"}
    relocated_fields = simple_fields | {
        "sha256", "origin_path", "relative_path",
        "shard_manifest_sha256", "shard_index", "run_id", "run_attempt",
        "artifact_name",
    }
    for entry in entries:
        require(isinstance(entry, dict) and set(entry) ==
                (relocated_fields if relocations else simple_fields),
                "build index entry 형식이 다릅니다")
        key = (entry["campaign_id"], entry["name"])
        require(key in expected and key not in by_key, f"build index key가 잘못됐습니다: {key}")
        by_key[key] = entry
    require(set(by_key) == set(expected), "build index가 부분 산출물이거나 불필요한 산출물을 포함합니다")
    resolved_sources: dict[tuple[str, str], Path] = {}
    for key, entry in by_key.items():
        if relocations:
            matches = [
                row for row in relocations
                if row["manifest_sha256"] == entry["shard_manifest_sha256"]
                and row["shard_index"] == entry["shard_index"]
                and row["run_id"] == entry["run_id"]
                and row["run_attempt"] == entry["run_attempt"]
                and row["artifact_name"] == entry["artifact_name"]
            ]
            require(len(matches) == 1,
                    f"build index entry shard identity가 다릅니다: {key}")
            relocation = matches[0]
            shard_manifest = strict_json(Path(relocation["manifest_path"]))
            shard_entries = [
                row for row in shard_manifest.get("entries", [])
                if isinstance(row, dict)
                and (row.get("campaign_id"), row.get("name")) == key
            ]
            require(
                len(shard_entries) == 1
                and shard_entries[0].get("sha256") == entry["sha256"]
                and shard_entries[0].get("origin_path") == entry["origin_path"]
                and shard_entries[0].get("path") == entry["relative_path"],
                f"build index entry가 original shard manifest와 다릅니다: {key}",
            )
            recorded_matches = [
                row for row in index["relocations"]
                if row["manifest_sha256"] == entry["shard_manifest_sha256"]
                and row["shard_index"] == entry["shard_index"]
            ]
            require(len(recorded_matches) == 1 and
                    Path(entry["path"]).resolve() ==
                    (Path(recorded_matches[0]["bundle_root"]) /
                     entry["relative_path"]).resolve(),
                    f"build index entry recorded path identity가 다릅니다: {key}")
            origin = Path(entry["origin_path"])
            require(
                origin.is_absolute()
                and origin == (Path(relocation["origin_root"]) /
                               entry["relative_path"]).resolve(),
                f"build index entry origin/relative identity가 다릅니다: {key}",
            )
            source = resolve_relocated_path(
                entry["origin_path"], relocations, f"artifact source {key}"
            )
            require(
                source == (Path(relocation["bundle_root"]) /
                           entry["relative_path"]).resolve()
                and SHA256.fullmatch(str(entry["sha256"])) is not None
                and _path_sha256(source) == entry["sha256"],
                f"artifact original shard byte/hash가 다릅니다: {key}",
            )
        else:
            source = Path(entry["path"]).resolve()
        resolved_sources[key] = source
    validated = []
    image_hashes: dict[str, dict[str, str]] = {}
    for key, artifact in expected.items():
        entry = by_key[key]
        source = resolved_sources[key]
        require(source.exists(), f"artifact source가 없습니다: {key}: {source}")
        if relocations:
            require(
                sum(source.is_relative_to(Path(row["bundle_root"]).resolve())
                    for row in relocations) == 1,
                f"artifact source가 relocation bundle에 유일하게 속하지 않습니다: {key}",
            )
        kind = artifact["kind"]
        row: dict[str, Any] = {
            "campaign_id": key[0],
            "name": key[1],
            "kind": kind,
            "source": source.as_posix(),
        }
        if relocations:
            row.update({
                field: entry[field]
                for field in sorted(relocated_fields - simple_fields)
            })
        if kind == "build_tree":
            require(source.is_dir(), f"build tree가 directory가 아닙니다: {key}")
            recipe = artifact.get("recipe")
            require(isinstance(recipe, dict), f"build tree recipe가 없습니다: {key}")
            validate_build_tree_binding(source, key[1], recipe)
            row["sha256"] = directory_sha256(source)
            configs = config_files(source)
            require(configs, f"build tree에 resolved .config가 없습니다: {key}")
            row["configs"] = [{"path": value.as_posix(), "sha256": file_sha256(value)} for value in configs]
        else:
            require(source.is_file() and source.stat().st_size > 0, f"artifact가 비어 있거나 file이 아닙니다: {key}")
            row["sha256"] = file_sha256(source)
            if kind == "target_image":
                validate_hex(source)
                if key[0] == SOAK_ARTIFACT_ID:
                    role = key[1].removeprefix("hex-")
                    record = resolved_sources[(key[0], f"build-record-{role}")]
                    config = resolved_sources[(key[0], f"{role}-config")]
                    validate_soak_build_provenance(
                        source, config, record, role, plan["source"]
                    )
                    configs = [config]
                    recipe = artifact.get("recipe")
                    require(isinstance(recipe, dict),
                            "soak image build recipe가 없습니다")
                    validate_recipe_binding(source, recipe)
                elif key[0] == "m33_diagnostics_dtm":
                    record = resolved_sources[(key[0], "build-manifest")]
                    transport = key[1].removesuffix("-hex")
                    configs = [validate_diagnostics_manifest(
                        record,
                        source,
                        transport,
                        plan["source"],
                    )]
                elif key[0] in {"m33_profiles_standard", "m33_profiles_native"}:
                    suffix = key[1].removeprefix("hex-")
                    record_key = (key[0], f"build-record-{suffix}")
                    record = resolved_sources[record_key]
                    recipe = artifact.get("recipe")
                    require(isinstance(recipe, dict), "profile image build recipe가 없습니다")
                    selectors = recipe.get("selectors")
                    require(isinstance(selectors, list), "profile image selector가 없습니다")
                    selector_values = dict(value.split("=", 1) for value in selectors)
                    profile = validate_profile_record(
                        record,
                        source,
                        plan["source"],
                        selector_values.get("M33_PROFILE_FAMILY", "standard"),
                        selector_values["M33_PROFILE_ROLE"],
                        relocations,
                    )
                    profile_config = resolve_relocated_path(
                        profile["artifacts"]["config"]["path"],
                        relocations,
                        "profile config",
                    )
                    configs = [profile_config]
                else:
                    record = adjacent_build_record(source)
                    if record.suffix.lower() == ".json":
                        arduino = validate_arduino_record(record, source, plan["source"])
                        configs = [arduino_config(arduino, record, source)]
                    else:
                        validate_native_record(record, plan["source"])
                        configs = config_files(source)
                    if validate_source_digests:
                        recipe = artifact.get("recipe")
                        require(isinstance(recipe, dict) and isinstance(recipe.get("application"), str), f"target image application binding이 없습니다: {key}")
                        validate_current_source_record(source, recipe["application"], plan["source"])
                        validate_recipe_binding(source, recipe)
                row["build_record"] = {"path": record.as_posix(), "sha256": file_sha256(record)}
                require(configs, f"target image의 resolved .config가 없습니다: {key}")
                row["configs"] = [{"path": value.as_posix(), "sha256": file_sha256(value)} for value in configs]
                campaign_images = image_hashes.setdefault(key[0], {})
                require(row["sha256"] not in campaign_images, f"한 campaign의 서로 다른 slot이 같은 HEX를 사용합니다: {campaign_images.get(row['sha256'])}, {key[1]}")
                campaign_images[row["sha256"]] = key[1]
            elif kind == "configuration":
                binding = key[1].removesuffix("-config")
                image_keys = [
                    image_key
                    for image_key, image_artifact in expected.items()
                    if image_key[0] == key[0]
                    and image_artifact["kind"] == "target_image"
                    and image_artifact["binding"].replace("-image", "") == binding
                ]
                require(len(image_keys) == 1, f"configuration image mapping이 모호합니다: {key}")
                image = resolved_sources[image_keys[0]]
                if key[0] == SOAK_ARTIFACT_ID:
                    require(source == (image.parent / ".config").resolve(),
                            f"soak configuration이 image build와 다릅니다: {key}")
                else:
                    record_path = adjacent_build_record(image)
                    record = strict_json(record_path)
                    require(
                        source == arduino_config(record, record_path, image),
                        f"configuration이 image build와 다릅니다: {key}",
                    )
            elif kind in {"fixture", "runtime_evidence", "flash_record", "build_record"} and source.suffix.lower() == ".json":
                document = strict_json(source)
                declared_revision = document.get("source_revision", document.get("core_revision"))
                if declared_revision is not None:
                    require(declared_revision == plan["source"]["source_revision"], f"JSON artifact source revision이 다릅니다: {key}")
        if relocations:
            require(_path_sha256(source) == entry["sha256"],
                    f"artifact byte가 검증 중 변경됐습니다: {key}")
        validated.append(row)
    return validated


def stage_artifacts(
    plan: dict[str, Any],
    index: dict[str, Any],
    artifact_root: Path,
    runtime_inputs: dict[str, Any] | None = None,
    validate_source_digests: bool = True,
    effective_source: dict[str, Any] | None = None,
    relocation_root: Path | None = None,
) -> dict[str, Any]:
    """! @brief 검증된 source를 가리키는 새 symlink artifact root를 원자적으로 만듭니다. """

    current = effective_source or plan["source"]
    artifact_root = require_external_fresh_root(
        artifact_root, current, "artifact"
    )
    validated = validate_index(
        plan,
        index,
        validate_source_digests,
        effective_source=current,
        relocation_root=relocation_root,
    )
    transfer_contract = index.get("transfer_contract")
    if runtime_artifacts(plan):
        require(runtime_inputs is not None, "완성된 runtime input manifest가 필요합니다")
        validated.extend(validate_runtime_inputs(
            plan,
            runtime_inputs,
            require_complete=True,
            effective_source=current,
            transfer_contract=transfer_contract,
        ))
    else:
        require(runtime_inputs is None, "불필요한 runtime input manifest가 제공됐습니다")
    temporary = artifact_root.with_name(artifact_root.name + f".staging-{os.getpid()}")
    require(not temporary.exists(), f"temporary artifact root가 이미 있습니다: {temporary}")
    created: list[Path] = []
    try:
        temporary.mkdir(parents=False)
        created.append(temporary)
        for row in validated:
            campaign = temporary / row["campaign_id"]
            if not campaign.exists():
                campaign.mkdir()
                created.append(campaign)
            destination = campaign / row["name"]
            source = Path(row["source"])
            if "shard_manifest_sha256" in row:
                require(_path_sha256(source) == row["sha256"],
                        f"artifact byte가 stage 직전 변경됐습니다: {source}")
            os.symlink(str(source), str(destination), target_is_directory=source.is_dir())
            created.append(destination)
        manifest = {
            "schema_version": 1,
            "kind": "m33_w06_artifact_root",
            "plan_sha256": plan["contract_sha256"],
            "source": plan["source"],
            "source_binding": validate_source_binding(plan["source"], current),
            "transfer_contract": transfer_contract,
            "policy": plan["policy"],
            "entries": validated,
            "relocations": validate_relocations(index, relocation_root),
        }
        manifest["manifest_sha256"] = canonical_sha256(manifest)
        manifest_path = temporary / "m33-w06-artifacts.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        created.append(manifest_path)
        temporary.replace(artifact_root)
        return manifest
    except Exception:
        for path in reversed(created):
            try:
                if path.is_symlink() or path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            except OSError:
                pass
        raise


def staged_build_index_entry(
    row: dict[str, Any],
    relocated: bool,
) -> dict[str, Any]:
    """! @brief staged build row를 local 또는 relocation index 형식으로 복원합니다. """

    entry = {
        "campaign_id": row["campaign_id"],
        "name": row["name"],
        "path": row["source"],
    }
    if relocated:
        for field in (
            "sha256", "origin_path", "relative_path",
            "shard_manifest_sha256", "shard_index", "run_id",
            "run_attempt", "artifact_name",
        ):
            if field in row:
                entry[field] = row[field]
    return entry


def validate_artifact_root(
    plan: dict[str, Any],
    artifact_root: Path,
    validate_source_digests: bool = True,
    effective_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """! @brief staged layout의 symlink target·hash·config가 변하지 않았는지 재검증합니다. """

    artifact_root = artifact_root.resolve()
    manifest = strict_json(artifact_root / "m33-w06-artifacts.json")
    require(manifest.get("schema_version") == 1 and manifest.get("kind") == "m33_w06_artifact_root", "artifact root manifest schema가 다릅니다")
    digest = manifest.get("manifest_sha256")
    clone = dict(manifest)
    clone.pop("manifest_sha256", None)
    require(SHA256.fullmatch(str(digest)) is not None and canonical_sha256(clone) == digest, "artifact root manifest hash가 다릅니다")
    require(manifest.get("plan_sha256") == plan["contract_sha256"] and manifest.get("source") == plan["source"], "artifact root plan/source가 다릅니다")
    current = effective_source or plan["source"]
    require_source_binding(manifest, plan["source"], current,
                           "artifact root manifest")
    transfer_contract = manifest.get("transfer_contract")
    if transfer_contract is not None:
        validate_transfer_contract(transfer_contract)
    expected = plan_artifacts(plan)
    build_expected = build_artifacts(plan)
    runtime_expected = runtime_artifacts(plan)
    entries = manifest.get("entries")
    require(isinstance(entries, list) and len(entries) == len(expected), "artifact root manifest가 부분 상태입니다")
    index_entries = []
    runtime_rows = []
    known: set[tuple[str, str]] = set()
    relocated = bool(manifest.get("relocations"))
    for row in entries:
        key = (row.get("campaign_id"), row.get("name"))
        require(key in expected and key not in known, f"artifact root entry가 잘못됐습니다: {key}")
        known.add(key)
        link = artifact_root / key[0] / key[1]
        require(link.is_symlink(), f"artifact layout은 exact source symlink여야 합니다: {link}")
        require(link.resolve().as_posix() == row.get("source"), f"artifact symlink target이 바뀌었습니다: {link}")
        if key in build_expected:
            index_entries.append(staged_build_index_entry(row, relocated))
        else:
            runtime_rows.append(row)
    expected_paths = {artifact_root / campaign / name for campaign, name in expected}
    actual_paths = {path for path in artifact_root.glob("*/*") if path.name != "m33-w06-artifacts.json"}
    require(actual_paths == expected_paths, "artifact root에 누락 또는 비계약 항목이 있습니다")
    revalidated = validate_index(
        plan,
        {
            "schema_version": 1,
            "kind": "m33_w06_build_index",
            "plan_sha256": plan["contract_sha256"],
            "source": plan["source"],
            "source_binding": manifest["source_binding"],
            "transfer_contract": transfer_contract,
            "entries": index_entries,
            "relocations": manifest.get("relocations", []),
        },
        validate_source_digests,
        effective_source=current,
    )
    expected_build_rows = [row for row in entries if (row["campaign_id"], row["name"]) in build_expected]
    require(revalidated == expected_build_rows, "artifact source/build/config byte가 staging 뒤 변경됐습니다")
    require(len(runtime_rows) == len(runtime_expected), "runtime artifact root가 부분 상태입니다")
    for row in runtime_rows:
        source = Path(row["source"])
        require(
            source.is_file()
            and source.stat().st_size > 0
            and file_sha256(source) == row["sha256"],
            f"runtime input byte가 staging 뒤 변경됐습니다: {source}",
        )
    return manifest


def write_json(path: Path, document: dict[str, Any]) -> None:
    """! @brief 기존 파일을 덮어쓰지 않고 JSON을 기록합니다. """

    atomic_write_json(path, document)


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief plan·Arduino 준비·build·runtime 결합·stage·validate 명령을 실행합니다. """

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--sdk-root", type=Path, required=True)
    plan_parser.add_argument("--toolchain-root", type=Path, required=True)
    plan_parser.add_argument("--revision")
    plan_parser.add_argument("--output", type=Path, required=True)
    arduino_parser = subparsers.add_parser("prepare-arduino")
    arduino_parser.add_argument("--plan", type=Path, required=True)
    arduino_parser.add_argument("--output-root", type=Path, required=True)
    inventory_parser = subparsers.add_parser("board-inventory")
    inventory_parser.add_argument("--plan", type=Path, required=True)
    inventory_parser.add_argument("--output", type=Path, required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--plan", type=Path, required=True)
    build_parser.add_argument("--work-root", type=Path, required=True)
    build_parser.add_argument("--index-output", type=Path, required=True)
    build_parser.add_argument("--runtime-inputs-output", type=Path, required=True)
    build_parser.add_argument("--arduino-cli", type=Path, required=True)
    build_parser.add_argument("--arduino-config", type=Path, required=True)
    build_parser.add_argument("--fqbn-prefix", default="nucode:zephyr:nu54dk")
    build_parser.add_argument("--timeout-seconds", type=int, default=3600)
    build_parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_BUILD_WORKERS,
        help=f"독립 build action 병렬 수(1~{MAX_BUILD_WORKERS}, 기본 {DEFAULT_BUILD_WORKERS})",
    )
    shard_plan_parser = subparsers.add_parser("shard-plan")
    shard_plan_parser.add_argument("--plan", type=Path, required=True)
    shard_plan_parser.add_argument("--work-root", type=Path, required=True)
    shard_plan_parser.add_argument("--arduino-cli", type=Path, required=True)
    shard_plan_parser.add_argument("--arduino-config", type=Path, required=True)
    shard_plan_parser.add_argument("--fqbn-prefix", default="nucode:zephyr:nu54dk")
    shard_plan_parser.add_argument("--shard-count", type=int, required=True)
    shard_plan_parser.add_argument("--output", type=Path, required=True)
    shard_build_parser = subparsers.add_parser("build-shard")
    shard_build_parser.add_argument("--plan", type=Path, required=True)
    shard_build_parser.add_argument("--shard-plan", type=Path, required=True)
    shard_build_parser.add_argument("--shard-index", type=int, required=True)
    shard_build_parser.add_argument("--work-root", type=Path, required=True)
    shard_build_parser.add_argument("--output", type=Path, required=True)
    shard_build_parser.add_argument("--arduino-cli", type=Path, required=True)
    shard_build_parser.add_argument("--arduino-config", type=Path, required=True)
    shard_build_parser.add_argument("--fqbn-prefix", default="nucode:zephyr:nu54dk")
    shard_build_parser.add_argument("--timeout-seconds", type=int, default=3600)
    shard_build_parser.add_argument("--max-workers", type=int,
                                    default=DEFAULT_BUILD_WORKERS)
    shard_build_parser.add_argument("--run-id")
    shard_build_parser.add_argument("--run-attempt")
    aggregate_parser = subparsers.add_parser("aggregate-shards")
    aggregate_parser.add_argument("--plan", type=Path, required=True)
    aggregate_parser.add_argument("--shard-plan", type=Path, required=True)
    aggregate_parser.add_argument("--shards-root", type=Path, required=True)
    aggregate_parser.add_argument("--work-root", type=Path, required=True)
    aggregate_parser.add_argument("--arduino-cli", type=Path, required=True)
    aggregate_parser.add_argument("--arduino-config", type=Path, required=True)
    aggregate_parser.add_argument("--fqbn-prefix", default="nucode:zephyr:nu54dk")
    aggregate_parser.add_argument("--index-output", type=Path, required=True)
    aggregate_parser.add_argument("--runtime-inputs-output", type=Path, required=True)
    aggregate_parser.add_argument("--output", type=Path, required=True)
    aggregate_parser.add_argument("--transfer-contract", type=Path, required=True)
    runtime_parser = subparsers.add_parser("bind-runtime")
    runtime_parser.add_argument("--plan", type=Path, required=True)
    runtime_parser.add_argument("--index", type=Path, required=True)
    runtime_parser.add_argument("--generated-root", type=Path, required=True)
    runtime_parser.add_argument("--client-flash-record", type=Path, required=True)
    runtime_parser.add_argument("--server-flash-record", type=Path, required=True)
    runtime_parser.add_argument("--runtime-producer", type=Path, required=True)
    runtime_parser.add_argument("--output", type=Path, required=True)
    runtime_parser.add_argument("--shards-root", type=Path)
    stage_parser = subparsers.add_parser("stage")
    stage_parser.add_argument("--plan", type=Path, required=True)
    stage_parser.add_argument("--index", type=Path, required=True)
    stage_parser.add_argument("--runtime-inputs", type=Path)
    stage_parser.add_argument("--artifact-root", type=Path, required=True)
    stage_parser.add_argument("--shards-root", type=Path)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--plan", type=Path, required=True)
    validate_parser.add_argument("--artifact-root", type=Path, required=True)
    for source_parser in (
        arduino_parser,
        inventory_parser,
        build_parser,
        shard_plan_parser,
        shard_build_parser,
        aggregate_parser,
        runtime_parser,
        stage_parser,
        validate_parser,
    ):
        source_parser.add_argument("--sdk-root", type=Path)
        source_parser.add_argument("--toolchain-root", type=Path)
    args = parser.parse_args(arguments)
    if args.command == "plan":
        identity = validate_source_lock(REPOSITORY, args.sdk_root, args.toolchain_root, args.revision)
        plan = build_plan(identity)
        write_json(require_external_output(args.output, identity, "plan"), plan)
        print(
            f"M33_W06_ARTIFACT_PLAN_PASS={plan['expected_campaign_count']};"
            f"SHA256={plan['contract_sha256']}"
        )
        return 0
    plan = strict_json(args.plan.resolve())
    validate_plan(plan)
    source = plan["source"]
    active_sdk_root = (
        args.sdk_root.resolve()
        if getattr(args, "sdk_root", None) is not None
        else Path(source["sdk_root"]).resolve()
    )
    active_toolchain_root = (
        args.toolchain_root.resolve()
        if getattr(args, "toolchain_root", None) is not None
        else Path(source["toolchain_root"]).resolve()
    )
    active_source = validate_source_lock(
        REPOSITORY,
        active_sdk_root,
        active_toolchain_root,
        source["source_revision"],
    )
    validate_source_binding(source, active_source)
    if args.command == "prepare-arduino":
        prepared = prepare_arduino_checkout(
            active_source, args.output_root, planned_identity=source
        )
        print(
            "M33_W06_ARDUINO_CHECKOUT_PASS=1;"
            f"SHA256={prepared['manifest_sha256']}"
        )
        return 0
    if args.command == "board-inventory":
        output = require_external_output(
            args.output, active_source, "board inventory"
        )
        inventory = current_board_inventory(plan, effective_source=active_source)
        write_json(output, inventory)
        print(
            "M33_W06_BOARD_INVENTORY_READY=3;"
            f"SHA256={canonical_sha256(inventory)}"
        )
        return 0
    if args.command == "shard-plan":
        require(args.arduino_cli.resolve().is_file() and
                args.arduino_config.resolve().is_file(),
                "shard plan Arduino CLI/config가 없습니다")
        work_root = require_external_root(
            args.work_root, active_source, "shard plan work"
        )
        actions = create_shard_build_actions(
            plan,
            work_root,
            active_sdk_root,
            active_toolchain_root,
            args.arduino_cli.resolve(),
            args.arduino_config.resolve(),
            args.fqbn_prefix,
        )
        shard_plan = create_build_shard_plan(
            plan, actions, args.shard_count
        )
        write_json(
            require_external_output(args.output, active_source, "shard plan"),
            shard_plan,
        )
        print(
            f"M33_W06_SHARD_PLAN_PASS={shard_plan['shard_count']};"
            f"ACTIONS={shard_plan['action_count']};"
            f"SHA256={shard_plan['contract_sha256']}"
        )
        return 0
    if args.command == "build":
        index = build_from_plan(
            plan,
            args.work_root,
            args.index_output,
            args.runtime_inputs_output,
            args.arduino_cli,
            args.arduino_config,
            args.fqbn_prefix,
            args.timeout_seconds,
            args.max_workers,
            sdk_root=active_sdk_root,
            toolchain_root=active_toolchain_root,
        )
        print(f"M33_W06_ARTIFACT_BUILD_PASS={len(index['entries'])};ACTIONS={len(index['actions'])}")
        return 0
    if args.command == "build-shard":
        shard_plan = strict_json(args.shard_plan.resolve())
        result = build_shard_from_plan(
            plan,
            shard_plan,
            args.shard_index,
            args.work_root,
            args.output,
            args.arduino_cli,
            args.arduino_config,
            args.fqbn_prefix,
            args.timeout_seconds,
            args.max_workers,
            sdk_root=active_sdk_root,
            toolchain_root=active_toolchain_root,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
        )
        print(
            f"M33_W06_BUILD_SHARD_ONLY={result['shard_index']};"
            f"SLOTS={result['build_slot_count']};"
            f"SHA256={result['manifest_sha256']};HIL=NOT_RUN"
        )
        return 0
    if args.command == "aggregate-shards":
        shard_plan = strict_json(args.shard_plan.resolve())
        require(args.arduino_cli.resolve().is_file() and
                args.arduino_config.resolve().is_file(),
                "aggregate Arduino CLI/config가 없습니다")
        work_root = require_external_root(
            args.work_root, active_source, "aggregate action model"
        )
        transfer_contract = parse_transfer_contract(args.transfer_contract)
        actions = create_shard_build_actions(
            plan=plan,
            work_root=work_root,
            sdk_root=active_sdk_root,
            toolchain_root=active_toolchain_root,
            arduino_cli=args.arduino_cli.resolve(),
            arduino_config=args.arduino_config.resolve(),
            fqbn_prefix=args.fqbn_prefix,
        )
        result = aggregate_build_shards(
            plan=plan,
            shard_plan=shard_plan,
            shards_root=args.shards_root,
            output=args.output,
            index_output=args.index_output,
            runtime_output=args.runtime_inputs_output,
            actions=actions,
            sdk_root=active_sdk_root,
            toolchain_root=active_toolchain_root,
            transfer_contract=transfer_contract,
        )
        print(
            f"M33_W06_CI_BUILD_ONLY={result['build_slot_count']};"
            f"RUNTIME_NOT_PROVIDED={result['runtime_slot_count']};"
            f"SHA256={result['aggregate_sha256']};HIL=NOT_RUN"
        )
        return 0
    if args.command == "bind-runtime":
        index = strict_json(args.index.resolve())
        relocation_root = discover_relocation_root(
            args.index, index, args.shards_root
        )
        output = require_external_output(args.output, active_source, "runtime bind")
        runtime = bind_prepared_runtime_inputs(
            plan,
            index,
            args.generated_root,
            args.client_flash_record,
            args.server_flash_record,
            args.runtime_producer,
            effective_source=active_source,
            relocation_root=relocation_root,
        )
        write_json(output, runtime)
        print(
            f"M33_W06_RUNTIME_BIND_PASS={len(runtime['entries'])};"
            f"SHA256={runtime['manifest_sha256']}"
        )
        return 0
    if args.command == "stage":
        index = strict_json(args.index.resolve())
        relocation_root = discover_relocation_root(
            args.index, index, args.shards_root
        )
        runtime_inputs = strict_json(args.runtime_inputs.resolve()) if args.runtime_inputs else None
        manifest = stage_artifacts(
            plan,
            index,
            args.artifact_root,
            runtime_inputs,
            effective_source=active_source,
            relocation_root=relocation_root,
        )
        print(f"M33_W06_ARTIFACT_STAGE_PASS={len(manifest['entries'])};SHA256={manifest['manifest_sha256']}")
        return 0
    manifest = validate_artifact_root(
        plan, args.artifact_root, effective_source=active_source
    )
    print(f"M33_W06_ARTIFACT_VALIDATE_PASS={len(manifest['entries'])};SHA256={manifest['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ArtifactFailure as error:
        print(f"M33_W06_ARTIFACT_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
