#!/usr/bin/env python3
"""! @brief M33-W06 exact artifact plan·staging의 fail-closed 계약을 검증합니다. """

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "tools/ci"
if str(CI) not in sys.path:
    sys.path.insert(0, str(CI))

import m33_w06_artifacts as artifacts  # noqa: E402


SOURCE = {
    "source_revision": "1" * 40,
    "source_clean": True,
    "board_revision": "2" * 40,
    "board_clean": True,
    "ncs_version": "3.4.0",
    "ncs_revision": "3" * 40,
    "ncs_clean": True,
    "zephyr_revision": "4" * 40,
    "zephyr_clean": True,
    "toolchain_bundle_id": "dcbdc366a1",
    "sdk_root": "C:/ncs/v3.4.0",
    "toolchain_root": "C:/ncs/toolchains/dcbdc366a1/opt/zephyr-sdk",
    "lock_sha256": "5" * 64,
}
ARDUINO_TEST_FAMILIES = {
    "NUCODE_BLE_ISO": ("nucode.ble.iso", "m31_iso_revisions"),
    "NUCODE_BLE_Audio": ("nucode.ble.audio", "m31_audio_revisions"),
    "NUCODE_BLE_DirectionFinding": (
        "nucode.ble.direction_finding", "m31_df_revisions"
    ),
    "NUCODE_BLE_ChannelSounding": (
        "nucode.ble.channel_sounding", "m31_cs_revisions"
    ),
}


def native_record() -> str:
    """! @brief 합성 build tree용 exact native record를 반환합니다. """

    values = {
        "core_revision": SOURCE["source_revision"][:12],
        "core_source_sha256": "6" * 64,
        "application_source_sha256": "7" * 64,
        "board_revision": SOURCE["board_revision"][:12],
        "board_source_sha256": "8" * 64,
        "ncs_revision": SOURCE["ncs_revision"][:12],
        "zephyr_revision": SOURCE["zephyr_revision"][:12],
        "board": "nrf54l15dk",
        "board_qualifiers": "nrf54l15/cpuapp/nu54dk",
        "toolchain_variant": "zephyr",
        "toolchain_path": SOURCE["toolchain_root"],
        "cxx_compiler": "GNU 14.3.0",
    }
    return "\n".join(f"  {key}: '{value}'" for key, value in values.items()) + "\n"


def arduino_record(
    image: Path,
    platform_root: Path,
    libraries: tuple[str, ...],
) -> dict:
    """! @brief exact library·feature·source·revision을 가진 Arduino record를 만듭니다. """

    revisions = {
        "NUCODE_CORE_REVISION": SOURCE["source_revision"],
        "NUCODE_BOARD_REVISION": SOURCE["board_revision"],
        "NUCODE_NCS_REVISION": SOURCE["ncs_revision"],
        "NUCODE_ZEPHYR_REVISION": SOURCE["zephyr_revision"],
    }
    source_inputs = {
        "sources": [
            {
                "logical_identity": (
                    f"platform:libraries/{library}/src/fixture.cpp"
                ),
                "source_path": (
                    platform_root / "libraries" / library / "src/fixture.cpp"
                ).as_posix(),
                "compiled_path": "C:/generated/fixture.cpp",
                "sha256": "6" * 64,
            }
            for library in libraries
        ],
    }
    for library in libraries:
        source_inputs[ARDUINO_TEST_FAMILIES[library][1]] = dict(revisions)
    return {
        "source_inputs": source_inputs,
        "artifacts": {
            "hex": {
                "path": image.as_posix(),
                "size": image.stat().st_size,
                "sha256": artifacts.file_sha256(image),
            }
        },
        "board": artifacts.BOARD_TARGET,
        "context": {
            "platform_root": platform_root.as_posix(),
            "selected_libraries": list(libraries),
        },
        "cache": {
            "input_manifest": {
                "adapter": {
                    "embedded_core_revision": SOURCE["source_revision"]
                },
                "board_package": {"revision": SOURCE["board_revision"]},
                "ncs": {
                    "nrf_revision": SOURCE["ncs_revision"],
                    "zephyr_revision": SOURCE["zephyr_revision"],
                },
                "configuration": {
                    "selected_features": [
                        {"id": ARDUINO_TEST_FAMILIES[library][0]}
                        for library in libraries
                    ]
                },
                "toolchain": {"bundle_id": SOURCE["toolchain_bundle_id"]},
            }
        },
    }


def write_native_image(root: Path, name: str, data_line: str) -> Path:
    """! @brief native build record와 config가 인접한 Intel HEX를 만듭니다. """

    app = root / name / "app"
    zephyr = app / "zephyr"
    zephyr.mkdir(parents=True)
    image = zephyr / "zephyr.hex"
    image.write_text(data_line + "\n:00000001FF\n", encoding="ascii")
    (zephyr / ".config").write_text("CONFIG_TEST=y\n", encoding="utf-8")
    (app / "nucode_arduino_core_build.yml").write_text(native_record(), encoding="utf-8")
    return image


def small_plan() -> dict:
    """! @brief 두 역할 image만 가진 staging 단위 시험 plan을 만듭니다. """

    plan = {
        "schema_version": 1,
        "kind": "m33_w06_artifact_plan",
        "source": SOURCE,
        "policy": {
            "ncs_version": "3.4.0",
            "maximum_parallel_jobs": 2,
            "default_parallel_actions": artifacts.DEFAULT_BUILD_WORKERS,
            "maximum_parallel_actions": artifacts.MAX_BUILD_WORKERS,
            "flash": False,
            "mass_erase": False,
            "auto_unlock": False,
            "automatic_recover": False,
        },
        "campaigns": [{
            "id": "fixture_campaign",
            "runner": "fixture.py",
            "applications": ["fixture"],
            "roles": ["central", "peripheral"],
            "verification": "physical_hil",
            "artifacts": [
                {
                    "name": "hex-central",
                    "kind": "target_image",
                    "role": "central",
                    "binding": "central",
                    "required_for_dispatch": True,
                    "recipe": {"builder": "fixture", "application": "fixture", "jobs": 1},
                },
                {
                    "name": "hex-peripheral",
                    "kind": "target_image",
                    "role": "peripheral",
                    "binding": "peripheral",
                    "required_for_dispatch": True,
                    "recipe": {"builder": "fixture", "application": "fixture", "jobs": 1},
                },
            ],
        }],
    }
    plan["contract_sha256"] = artifacts.canonical_sha256(plan)
    return plan


def build_index(plan: dict, central: Path, peripheral: Path) -> dict:
    """! @brief 두 image를 모두 포함한 exact build index를 반환합니다. """

    return {
        "schema_version": 1,
        "kind": "m33_w06_build_index",
        "plan_sha256": plan["contract_sha256"],
        "source": SOURCE,
        "source_binding": artifacts.validate_source_binding(SOURCE, SOURCE),
        "transfer_contract": None,
        "entries": [
            {"campaign_id": "fixture_campaign", "name": "hex-central", "path": str(central)},
            {"campaign_id": "fixture_campaign", "name": "hex-peripheral", "path": str(peripheral)},
        ],
    }


class M33W06ArtifactTests(unittest.TestCase):
    """! @brief 48-campaign 파생과 artifact 무결성을 검사합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief 실제 runner source에서 plan을 한 번만 파생합니다. """

        cls.plan = artifacts.build_plan(dict(SOURCE))

    def test_actual_registry_produces_complete_safe_plan(self) -> None:
        """! @brief 48개 registry와 runner input을 누락 없이 고정합니다. """

        runner = ROOT / "tests/hil/nu54dk/m32_mesh_dfu_run.py"
        with mock.patch.object(
            artifacts.subprocess,
            "run",
            side_effect=AssertionError("runner를 실행하면 안 됩니다"),
        ):
            options = artifacts.runner_options(runner)
        self.assertIn("--probe-distributor-sha256", options)
        self.assertIn("--build-target-b", options)
        diagnostics = ROOT / "tools/bluetooth/m33_diagnostics.py"
        with mock.patch.object(
            artifacts.subprocess,
            "run",
            side_effect=AssertionError("runner를 실행하면 안 됩니다"),
        ):
            options = artifacts.runner_options(diagnostics, "build")
        self.assertIn("--sdk", options)
        self.assertIn("--routes", options)
        self.assertNotIn("--fixture", options)
        self.assertNotIn("--authorize-sector-program", options)
        self.assertEqual(len(self.plan["campaigns"]), self.plan["expected_campaign_count"])
        self.assertEqual(
            len(artifacts.plan_artifacts(self.plan)),
            len(artifacts.build_artifacts(self.plan)) + len(artifacts.runtime_artifacts(self.plan)),
        )
        self.assertEqual(self.plan["policy"]["ncs_version"], "3.4.0")
        self.assertEqual(self.plan["policy"]["maximum_parallel_jobs"], 2)
        self.assertEqual(
            self.plan["policy"]["default_parallel_actions"], 2
        )

        self.assertEqual(
            self.plan["policy"]["maximum_parallel_actions"], 4
        )
        self.assertFalse(self.plan["policy"]["flash"])
        self.assertFalse(self.plan["policy"]["mass_erase"])
        delta = self.plan["source_delta"]
        self.assertEqual(delta["w05_adb"]["completed"], "204/204")
        self.assertEqual(
            delta["w05_adb"]["current_source_status"], "NOT_VERIFIED"
        )
        self.assertTrue(delta["current_source_build_required"])
        self.assertEqual(len(delta["files"]), 4)
        self.assertEqual(len(delta["build_slots"]), 4)
        for path, checksum in delta["files"].items():
            self.assertEqual(artifacts.file_sha256(ROOT / path), checksum)
        for campaign in self.plan["campaigns"]:
            for artifact in campaign["artifacts"]:
                if artifact["kind"] in {"target_image", "build_tree"}:
                    self.assertIsNotNone(artifact["recipe"])
                    self.assertLessEqual(artifact["recipe"]["jobs"], 2)

        recipes = {
            (campaign["id"], artifact["name"]): artifact["recipe"]
            for campaign in self.plan["campaigns"]
            for artifact in campaign["artifacts"]
            if artifact["recipe"] is not None
        }
        risk_profiles = {
            name: recipes[("m33_cs_acl_radio_risk", name)]["profile"]
            for name in ("hex-initiator", "hex-reflector")
        }
        self.assertEqual({
            "hex-initiator": "adaptive",
            "hex-reflector": "adaptive",
        }, risk_profiles)
        unrelated_cs_profiles = {
            recipe["profile"]
            for (campaign_id, _name), recipe in recipes.items()
            if campaign_id.startswith("m31_cs_")
            and recipe["builder"] == "arduino-cli"
        }
        self.assertEqual({"ble"}, unrelated_cs_profiles)

        adaptive = artifacts.strict_json(
            ROOT / "variants/nu54dk/profiles/adaptive/profile.json"
        )
        cs_feature = artifacts.strict_json(
            ROOT / "libraries/NUCODE_BLE_ChannelSounding/zephyr/feature.yml"
        )
        self.assertEqual("resolved", adaptive["capability_mode"])
        self.assertIn("adaptive", cs_feature["compatible_profiles"])
        self.assertEqual(
            ["nucode.ble.channel-sounding-api"],
            cs_feature["capabilities"],
        )

    def test_arduino_record_accepts_each_embedded_m31_revision_family(self) -> None:
        """! @brief 네 M31 family와 복수 선택이 exact provenance로 검증됩니다. """

        with tempfile.TemporaryDirectory(prefix="m33-w06-arduino-record-") as temporary:
            root = Path(temporary)
            image = root / "fixture.hex"
            image.write_bytes(b":00000001FF\n")
            record_path = root / "fixture.nu54-build.json"
            platform_root = root / "nonexistent-platform"
            for library in ARDUINO_TEST_FAMILIES:
                record = arduino_record(image, platform_root, (library,))
                record_path.write_text(
                    json.dumps(record, ensure_ascii=False), encoding="utf-8"
                )
                self.assertEqual(
                    artifacts.validate_arduino_record(record_path, image, SOURCE),
                    record,
                )
            combined = arduino_record(
                image,
                platform_root,
                ("NUCODE_BLE_ChannelSounding", "NUCODE_BLE_Audio"),
            )
            record_path.write_text(
                json.dumps(combined, ensure_ascii=False), encoding="utf-8"
            )
            self.assertEqual(
                combined,
                artifacts.validate_arduino_record(record_path, image, SOURCE),
            )

    def test_arduino_record_accepts_base_library_without_m31_revision_family(self) -> None:
        """! @brief 일반 BLE fixture는 선택하지 않은 M31 family를 요구하지 않습니다. """

        with tempfile.TemporaryDirectory(prefix="m33-w06-arduino-base-") as temporary:
            root = Path(temporary)
            image = root / "fixture.hex"
            image.write_bytes(b":00000001FF\n")
            record_path = root / "fixture.nu54-build.json"
            platform_root = root / "nonexistent-platform"
            record = arduino_record(image, platform_root, ())
            record["context"]["selected_libraries"] = ["NUCODE_BLE"]
            record["source_inputs"]["sources"] = [{
                "logical_identity": "platform:libraries/NUCODE_BLE/src/fixture.cpp",
                "source_path": (
                    platform_root / "libraries/NUCODE_BLE/src/fixture.cpp"
                ).as_posix(),
                "compiled_path": "C:/generated/fixture.cpp",
                "sha256": "6" * 64,
            }]
            record["cache"]["input_manifest"]["configuration"][
                "selected_features"
            ] = [{"id": "nucode.ble.nus"}]
            record_path.write_text(
                json.dumps(record, ensure_ascii=False), encoding="utf-8"
            )

            self.assertEqual(
                record,
                artifacts.validate_arduino_record(record_path, image, SOURCE),
            )

    def test_arduino_record_rejects_missing_embedded_revision(self) -> None:
        """! @brief 일반 build 성공을 exact M31 provenance로 승격하지 않습니다. """

        with tempfile.TemporaryDirectory(prefix="m33-w06-arduino-record-") as temporary:
            root = Path(temporary)
            image = root / "fixture.hex"
            image.write_bytes(b":00000001FF\n")
            record_path = root / "fixture.nu54-build.json"
            platform_root = root / "nonexistent-platform"
            base = arduino_record(
                image, platform_root, ("NUCODE_BLE_ChannelSounding",)
            )
            mutations = []

            missing_family = copy.deepcopy(base)
            missing_family["source_inputs"].pop("m31_cs_revisions")
            mutations.append((missing_family, "revision family"))

            spoofed_library = copy.deepcopy(base)
            spoofed_library["context"]["selected_libraries"] = [
                "NUCODE_BLE_Audio"
            ]
            mutations.append((spoofed_library, "library/cache feature"))

            extra_family = copy.deepcopy(base)
            extra_family["source_inputs"]["m31_audio_revisions"] = dict(
                base["source_inputs"]["m31_cs_revisions"]
            )
            mutations.append((extra_family, "revision family"))

            unknown_family = copy.deepcopy(base)
            unknown_family["source_inputs"]["m31_typo_revisions"] = dict(
                base["source_inputs"]["m31_cs_revisions"]
            )
            mutations.append((unknown_family, "unknown revision family"))

            missing_feature = copy.deepcopy(base)
            missing_feature["cache"]["input_manifest"]["configuration"][
                "selected_features"
            ] = []
            mutations.append((missing_feature, "library/cache feature"))

            extra_feature = copy.deepcopy(base)
            extra_feature["cache"]["input_manifest"]["configuration"][
                "selected_features"
            ].append({"id": "nucode.ble.audio"})
            mutations.append((extra_feature, "library/cache feature"))

            missing_source = copy.deepcopy(base)
            missing_source["source_inputs"]["sources"] = []
            mutations.append((missing_source, "library/source graph"))

            extra_source = copy.deepcopy(base)
            extra_source["source_inputs"]["sources"].append({
                "logical_identity": (
                    "platform:libraries/NUCODE_BLE_Audio/src/fixture.cpp"
                ),
                "source_path": (
                    platform_root
                    / "libraries/NUCODE_BLE_Audio/src/fixture.cpp"
                ).as_posix(),
                "compiled_path": "C:/generated/audio.cpp",
                "sha256": "7" * 64,
            })
            mutations.append((extra_source, "library/source graph"))

            spoofed_source = copy.deepcopy(base)
            spoofed_source["source_inputs"]["sources"][0]["source_path"] = (
                platform_root / "libraries/NUCODE_BLE_Audio/src/fixture.cpp"
            ).as_posix()
            mutations.append((spoofed_source, "identity/path"))

            stale_cache = copy.deepcopy(base)
            stale_cache["cache"]["input_manifest"]["ncs"][
                "zephyr_revision"
            ] = "9" * 40
            mutations.append((stale_cache, "cache revision"))

            for document, message in mutations:
                with self.subTest(message=message):
                    record_path.write_text(
                        json.dumps(document, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        artifacts.ArtifactFailure, message
                    ):
                        artifacts.validate_arduino_record(
                            record_path, image, SOURCE
                        )

    def test_arduino_provenance_survives_real_directory_relocation(self) -> None:
        """! @brief mock 없이 shard 이동 뒤 원본 record/config byte를 재검증합니다. """

        with tempfile.TemporaryDirectory(prefix="m33-w06-relocation-") as temporary:
            root = Path(temporary)
            producer = root / "producer-shard"
            build = producer / "builds/arduino-fixture"
            build.mkdir(parents=True)
            image = build / "Fixture.ino.hex"
            image.write_text(":0400000001020304F2\n:00000001FF\n", encoding="ascii")
            live = root / "builder-cache/build/nucode_arduino_core_build.yml"
            config = live.parent / "zephyr/.config"
            config.parent.mkdir(parents=True)
            live.write_text(native_record(), encoding="utf-8")
            config.write_text("CONFIG_TEST=y\n", encoding="utf-8")
            platform_root = root / "removed-original-platform"
            record = arduino_record(
                image, platform_root, ("NUCODE_BLE_ChannelSounding",)
            )
            record["source_inputs"]["live_build_record"] = {
                "path": live.as_posix(),
                "sha256": artifacts.file_sha256(live),
            }
            record["context"]["resource_audit"] = {
                "inputs": {
                    "config": {
                        "path": config.as_posix(),
                        "sha256": artifacts.file_sha256(config),
                    }
                }
            }
            record_path = image.with_suffix(".nu54-build.json")
            record_path.write_text(json.dumps(record), encoding="utf-8")
            entries = [{
                "campaign_id": "fixture",
                "name": "hex-fixture",
                "path": image.as_posix(),
            }]
            artifacts.freeze_arduino_provenance(entries)
            downloaded = root / "downloaded-shard"
            producer.rename(downloaded)
            moved_image = downloaded / "builds/arduino-fixture/Fixture.ino.hex"
            moved_record = moved_image.with_suffix(".nu54-build.json")
            validated = artifacts.validate_arduino_record(
                moved_record, moved_image, SOURCE
            )
            moved_config = artifacts.arduino_config(
                validated, moved_record, moved_image
            )
            self.assertEqual(
                moved_image.parent / ".m33-w06-portable/Fixture.ino.hex/zephyr/.config",
                moved_config,
            )
            self.assertFalse(platform_root.exists())

            spoofed = copy.deepcopy(record)
            spoofed["source_inputs"]["m31_audio_revisions"] = (
                spoofed["source_inputs"].pop("m31_cs_revisions")
            )
            moved_record.write_text(json.dumps(spoofed), encoding="utf-8")
            portable_manifest_path = (
                moved_image.parent
                / ".m33-w06-portable/Fixture.ino.hex/manifest.json"
            )
            portable_manifest = artifacts.strict_json(portable_manifest_path)
            portable_manifest["arduino_record"]["sha256"] = (
                artifacts.file_sha256(moved_record)
            )
            portable_manifest.pop("manifest_sha256")
            portable_manifest["manifest_sha256"] = artifacts.canonical_sha256(
                portable_manifest
            )
            portable_manifest_path.unlink()
            artifacts.atomic_write_json(
                portable_manifest_path, portable_manifest
            )
            self.assertEqual(
                moved_config,
                artifacts.validate_arduino_portable_provenance(
                    moved_image, moved_record, spoofed, SOURCE
                ),
            )
            with self.assertRaisesRegex(
                artifacts.ArtifactFailure, "revision family"
            ):
                artifacts.validate_arduino_record(
                    moved_record, moved_image, SOURCE
                )

            moved_record.write_text(json.dumps(record), encoding="utf-8")
            portable_manifest["arduino_record"]["sha256"] = (
                artifacts.file_sha256(moved_record)
            )
            portable_manifest.pop("manifest_sha256")
            portable_manifest["manifest_sha256"] = artifacts.canonical_sha256(
                portable_manifest
            )
            portable_manifest_path.unlink()
            artifacts.atomic_write_json(
                portable_manifest_path, portable_manifest
            )
            moved_config.write_text("CONFIG_TEST=n\n", encoding="utf-8")
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "config byte"):
                artifacts.validate_arduino_record(
                    moved_record, moved_image, SOURCE
                )

    def test_freeze_arduino_provenance_skips_profile_image(self) -> None:
        """! @brief Arduino manifest가 없는 profile HEX는 동결 대상에서 제외합니다. """

        with tempfile.TemporaryDirectory(prefix="m33-w06-profile-freeze-") as temporary:
            output = Path(temporary) / "records/profile-native-client"
            output.mkdir(parents=True)
            image = output / "image.hex"
            image.write_text(":0400000001020304F2\n:00000001FF\n", encoding="ascii")
            (output / "build-record.json").write_text("{}\n", encoding="utf-8")
            entries = [{
                "campaign_id": "m33_profiles_native",
                "name": "hex-client",
                "path": image.as_posix(),
            }]

            artifacts.freeze_arduino_provenance(entries)

            self.assertFalse((output / ".m33-w06-portable").exists())

    def test_source_path_rebinding_preserves_all_non_location_identity(self) -> None:
        """! @brief SDK 위치만 달라질 수 있고 revision/hash drift는 거부합니다. """

        planned = {
            **SOURCE,
            "sdk_root": "D:/ncs/v3.4.0",
            "toolchain_root": "D:/ncs/toolchains/dcbdc366a1",
        }
        binding = artifacts.validate_source_binding(planned, SOURCE)
        self.assertEqual("D:/ncs/v3.4.0", binding["planned"]["sdk_root"])
        self.assertEqual("C:/ncs/v3.4.0", binding["current"]["sdk_root"])
        drifted = {**SOURCE, "ncs_revision": "9" * 40}
        with self.assertRaisesRegex(artifacts.ArtifactFailure, "identity"):
            artifacts.validate_source_binding(planned, drifted)

    def test_transfer_contract_rejects_mixed_run_and_incomplete_denominator(self) -> None:
        """! @brief transfer control file이 다른 run 또는 4개 미만 shard를 거부합니다. """

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TRANSFER-CONTRACT.txt"
            base = (
                "SCHEMA=m33-w06-transfer-v1\n"
                "RUN_ID=123\n"
                "RUN_ATTEMPT=7\n"
                "SHARD_COUNT=4\n"
                "AGGREGATE_ONLY_SUFFICIENT=0\n"
                "SHARD_0=m33-w06-build-shard-0-123-attempt-7\n"
                "SHARD_1=m33-w06-build-shard-1-123-attempt-7\n"
                "SHARD_2=m33-w06-build-shard-2-123-attempt-7\n"
            )
            path.write_text(
                base + "SHARD_3=m33-w06-build-shard-3-123-attempt-8\n",
                encoding="ascii",
            )
            with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                        "shard artifact"):
                artifacts.parse_transfer_contract(path)
            path.write_text(base, encoding="ascii")
            with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                        "schema/run/count"):
                artifacts.parse_transfer_contract(path)

    def test_shard_origin_relocation_uses_manifest_and_relative_identity(self) -> None:
        """! @brief mock 없이 origin suffix를 download bundle의 같은 byte로 재결합합니다. """

        with tempfile.TemporaryDirectory(prefix="m33-w06-origin-") as temporary:
            root = Path(temporary)
            bundle = root / "downloaded"
            target = bundle / "builds/profile/zephyr/zephyr.elf"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"exact-elf-byte")
            origin = (root / "origin-shard").resolve()
            manifest = {
                "schema_version": 1,
                "kind": "m33_w06_build_shard_result",
                "origin_root": origin.as_posix(),
                "shard_index": 0,
                "run_id": None,
                "run_attempt": None,
                "entries": [{
                    "path": target.relative_to(bundle).as_posix(),
                    "origin_path": (
                        origin / target.relative_to(bundle)
                    ).as_posix(),
                    "sha256": artifacts.file_sha256(target),
                    "provenance": [],
                }],
            }
            manifest["manifest_sha256"] = artifacts.canonical_sha256(manifest)
            manifest_path = bundle / "m33-w06-shard-0.json"
            artifacts.atomic_write_json(manifest_path, manifest)
            index = {"transfer_contract": None, "relocations": [{
                "origin_root": origin.as_posix(),
                "bundle_root": bundle.as_posix(),
                "manifest_sha256": manifest["manifest_sha256"],
                "manifest_path": manifest_path.as_posix(),
                "shard_index": 0,
                "run_id": None,
                "run_attempt": None,
                "artifact_name": bundle.name,
            }]}
            rows = artifacts.validate_relocations(index)
            resolved = artifacts.resolve_relocated_path(
                (origin / "builds/profile/zephyr/zephyr.elf").as_posix(),
                rows,
                "fixture ELF",
            )
            self.assertEqual(target.resolve(), resolved)
            image = bundle / "builds/profile/zephyr/zephyr.hex"
            config = bundle / "builds/profile/zephyr/.config"
            sysbuild = bundle / "builds/profile/zephyr/sysbuild.config"
            image.write_bytes(b"image")
            config.write_bytes(b"config")
            sysbuild.write_bytes(b"sysbuild")
            hil = ROOT / "tests/hil/nu54dk"
            if str(hil) not in sys.path:
                sys.path.insert(0, str(hil))
            namespace = artifacts.runpy.run_path(
                str(ROOT / "tests/hil/nu54dk/m33_profile_build_record.py")
            )
            record = {
                "schema": "nucode-m33-profile-build-v1",
                "family": "standard",
                "role": "client",
                "source_revision": SOURCE["source_revision"],
                "development": False,
                "image": (origin / "builds/profile/zephyr/zephyr.hex").as_posix(),
                "sha256": artifacts.file_sha256(image),
                "owned_source_sha256": namespace["owned_source_hashes"](),
                "artifacts": {
                    "elf": {
                        "path": (origin / "builds/profile/zephyr/zephyr.elf").as_posix(),
                        "sha256": artifacts.file_sha256(target),
                    },
                    "config": {
                        "path": (origin / "builds/profile/zephyr/.config").as_posix(),
                        "sha256": artifacts.file_sha256(config),
                    },
                    "sysbuild": {
                        "path": (origin / "builds/profile/zephyr/sysbuild.config").as_posix(),
                        "sha256": artifacts.file_sha256(sysbuild),
                    },
                },
            }
            record_path = bundle / "records/profile/build-record.json"
            record_path.parent.mkdir(parents=True)
            record_path.write_text(json.dumps(record), encoding="utf-8")
            artifacts.validate_profile_record(
                record_path, image, SOURCE, "standard", "client", rows
            )
            manifest["origin_root"] = (root / "different-origin").as_posix()
            manifest.pop("manifest_sha256")
            manifest["manifest_sha256"] = artifacts.canonical_sha256(manifest)
            manifest_path.unlink()
            artifacts.atomic_write_json(manifest_path, manifest)
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "identity/hash"):
                artifacts.validate_relocations(index)

    def test_shard_boundaries_reject_symlink_junction_and_dangling_nodes(self) -> None:
        """! @brief manifest·artifact tree가 link/reparse를 통해 외부 byte를 읽지 못하게 합니다. """

        with tempfile.TemporaryDirectory(prefix="m33-w06-links-") as directory:
            root = Path(directory)

            def make_directory_link(link: Path, target: Path) -> None:
                """! @brief 현재 OS에서 directory link fixture를 만듭니다. """

                if os.name == "nt":
                    completed = subprocess.run(
                        ["cmd.exe", "/d", "/c", "mklink", "/J",
                         str(link), str(target)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(
                        0, completed.returncode, completed.stderr
                    )
                else:
                    link.symlink_to(target, target_is_directory=True)

            def remove_directory_link(link: Path) -> None:
                """! @brief fixture link 자체만 제거하고 target은 보존합니다. """

                if link.is_symlink():
                    link.unlink()
                else:
                    link.rmdir()

            twister = root / "twister-success"
            target = twister / "platform/toolchain/scenario"
            target.mkdir(parents=True)
            (target / "zephyr.hex").write_bytes(b"real-build")
            links = twister / "twister_links"
            links.mkdir()
            make_directory_link(links / "test_0", target)
            self.assertTrue(artifacts.sanitize_twister_output(twister))
            self.assertFalse(links.exists())
            self.assertEqual(b"real-build", (target / "zephyr.hex").read_bytes())

            escaped = root / "twister-escape"
            escaped.mkdir()
            escaped_links = escaped / "twister_links"
            escaped_links.mkdir()
            external_target = root / "external-twister-target"
            external_target.mkdir()
            escape_link = escaped_links / "test_0"
            make_directory_link(escape_link, external_target)
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "탈출"):
                artifacts.sanitize_twister_output(escaped)
            self.assertTrue(escaped_links.is_dir())
            remove_directory_link(escape_link)
            escaped_links.rmdir()

            unexpected = root / "twister-unexpected-link"
            unexpected_target = unexpected / "real"
            unexpected_target.mkdir(parents=True)
            unexpected_links = unexpected / "twister_links"
            unexpected_links.mkdir()
            make_directory_link(
                unexpected_links / "test_0", unexpected_target
            )
            unexpected_link = unexpected / "other_link"
            make_directory_link(unexpected_link, unexpected_target)
            with self.assertRaisesRegex(
                artifacts.ArtifactFailure, "symlink/junction/reparse"
            ):
                artifacts.sanitize_twister_output(unexpected)
            self.assertTrue(unexpected_links.is_dir())
            self.assertTrue((unexpected_links / "test_0").exists())
            remove_directory_link(unexpected_links / "test_0")
            unexpected_links.rmdir()
            remove_directory_link(unexpected_link)

            tree = root / "tree"
            tree.mkdir()
            (tree / "owned.bin").write_bytes(b"owned")
            file_link = tree / "linked.bin"
            file_link.write_bytes(b"external")
            original_is_symlink = Path.is_symlink

            def pretend_link(path: Path) -> bool:
                return path == file_link or original_is_symlink(path)

            with mock.patch.object(Path, "is_symlink", pretend_link):
                with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                            "symlink/junction/reparse"):
                    artifacts.directory_sha256(tree)
            file_link.unlink()

            dangling = tree / "dangling.bin"
            dangling.write_bytes(b"dangling-link-lstat-fixture")

            def pretend_dangling(path: Path) -> bool:
                return path == dangling or original_is_symlink(path)

            with mock.patch.object(Path, "is_symlink", pretend_dangling):
                with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                            "symlink/junction/reparse"):
                    artifacts.directory_sha256(tree)
            dangling.unlink()

            external_tree = root / "external-tree"
            external_tree.mkdir()
            (external_tree / "foreign.bin").write_bytes(b"foreign")
            if os.name == "nt":
                tree_junction = tree / "junction"
                completed = subprocess.run(
                    ["cmd.exe", "/d", "/c", "mklink", "/J",
                     str(tree_junction), str(external_tree)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                            "symlink/junction/reparse"):
                    artifacts.directory_sha256(tree)
                tree_junction.rmdir()

            download = root / "download"
            artifact_name = "m33-w06-build-shard-0-fixture"
            artifact_root = download / artifact_name
            artifact_root.mkdir(parents=True)
            origin = (root / "origin").resolve()
            manifest = {
                "origin_root": origin.as_posix(),
                "shard_index": 0,
                "run_id": None,
                "run_attempt": None,
                "entries": [],
            }
            manifest["manifest_sha256"] = artifacts.canonical_sha256(manifest)
            external_manifest = root / "external-manifest.json"
            artifacts.atomic_write_json(external_manifest, manifest)
            manifest_link = artifact_root / "m33-w06-shard-0.json"
            shutil.copy2(external_manifest, manifest_link)
            index = {
                "transfer_contract": None,
                "relocations": [{
                    "origin_root": origin.as_posix(),
                    "bundle_root": artifact_root.as_posix(),
                    "manifest_sha256": manifest["manifest_sha256"],
                    "manifest_path": manifest_link.as_posix(),
                    "shard_index": 0,
                    "run_id": None,
                    "run_attempt": None,
                    "artifact_name": artifact_name,
                }],
            }
            def pretend_manifest_link(path: Path) -> bool:
                return path == manifest_link or original_is_symlink(path)

            with mock.patch.object(Path, "is_symlink", pretend_manifest_link):
                with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                            "symlink/junction/reparse"):
                    artifacts.validate_relocations(index, download)
            manifest_link.unlink()
            manifest_link.write_bytes(b"dangling-link-lstat-fixture")
            with mock.patch.object(Path, "is_symlink", pretend_manifest_link):
                with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                            "symlink/junction/reparse"):
                    artifacts.validate_relocations(index, download)
            manifest_link.unlink()

            external_artifact = root / "external" / artifact_name
            external_artifact.mkdir(parents=True)
            artifacts.atomic_write_json(
                external_artifact / "m33-w06-shard-0.json", manifest
            )
            with mock.patch.object(
                    Path,
                    "is_symlink",
                    lambda path: path == artifact_root or original_is_symlink(path)):
                with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                            "symlink/junction/reparse"):
                    artifacts.validate_relocations(index, download)
            artifact_root.rmdir()

            if os.name == "nt":
                junction = download / artifact_name
                completed = subprocess.run(
                    ["cmd.exe", "/d", "/c", "mklink", "/J",
                     str(junction), str(external_artifact)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                            "symlink/junction/reparse"):
                    artifacts.validate_relocations(index, download)
                junction.rmdir()

    def test_non_campaign_soak_has_three_exact_role_provenance_sets(self) -> None:
        """! @brief 48 campaign 밖 soak가 역할별 image/config/build record를 모두 가집니다. """

        self.assertEqual(48, self.plan["expected_campaign_count"])
        soak = self.plan["soak"]
        self.assertFalse(soak["campaign"])
        self.assertEqual(list(artifacts.SOAK_ROLES), soak["roles"])
        self.assertEqual(artifacts.SOAK_RUNNER, soak["runner"]["path"])
        self.assertEqual(
            artifacts.file_sha256(ROOT / artifacts.SOAK_RUNNER),
            soak["runner"]["sha256"],
        )
        self.assertEqual(9, len(soak["artifacts"]))
        flattened = artifacts.plan_artifacts(self.plan)
        for role in artifacts.SOAK_ROLES:
            with self.subTest(role=role):
                image = flattened[(artifacts.SOAK_ARTIFACT_ID, f"hex-{role}")]
                self.assertEqual(
                    f"nucode.m32.regression_soak_hil.{role}",
                    image["recipe"]["scenario"],
                )
                self.assertIn(
                    (artifacts.SOAK_ARTIFACT_ID, f"{role}-config"), flattened
                )
                self.assertIn(
                    (artifacts.SOAK_ARTIFACT_ID, f"build-record-{role}"),
                    flattened,
                )
        changed = copy.deepcopy(self.plan)
        changed["soak"]["artifacts"][0]["recipe"]["scenario"] = "wrong"
        changed.pop("contract_sha256")
        changed["contract_sha256"] = artifacts.canonical_sha256(changed)
        with self.assertRaisesRegex(artifacts.ArtifactFailure, "soak"):
            artifacts.validate_plan(changed)

    def test_source_lock_rejects_each_dirty_checkout(self) -> None:
        """! @brief Core 외 board·nrf·zephyr dirty 상태도 각각 거부합니다. """

        lock = artifacts.strict_json(ROOT / "tools/ci/ncs-3.4.0.lock.json")
        revisions = {
            ROOT.resolve(): "1" * 40,
            (ROOT / "board_package/NU54DK_Zephyr_DTS").resolve(): lock["board"]["revision"],
            Path("C:/fixture-sdk/nrf").resolve(): lock["ncs"]["revision"],
            Path("C:/fixture-sdk/zephyr").resolve(): lock["zephyr"]["revision"],
        }
        for dirty_checkout in revisions:
            with self.subTest(dirty_checkout=dirty_checkout):
                def fake_git(checkout: Path, *arguments: str) -> str:
                    resolved = checkout.resolve()
                    if arguments[0] == "status":
                        return " M dirty" if resolved == dirty_checkout else ""
                    if arguments[0] == "rev-parse":
                        return revisions[resolved]
                    if arguments[0] == "ls-tree":
                        return f"160000 commit {lock['board']['revision']}\tboard_package/NU54DK_Zephyr_DTS"
                    raise AssertionError(arguments)

                with mock.patch.object(artifacts, "git_output", side_effect=fake_git):
                    with self.assertRaisesRegex(artifacts.ArtifactFailure, "clean exact"):
                        artifacts.validate_source_lock(
                            ROOT,
                            Path("C:/fixture-sdk"),
                            Path("C:/toolchains/dcbdc366a1/opt/zephyr-sdk"),
                        )
        dtm = artifacts.plan_artifacts(self.plan)
        self.assertEqual(
            dtm[("m33_diagnostics_dtm", "build-manifest")]["recipe"],
            {
                "builder": "m33_diagnostics.py",
                "application": "templates/bluetooth/diagnostics/dtm",
                "routes": ["dtm_twowire", "dtm_hci"],
                "jobs": 2,
            },
        )

    def test_cs_quiesce_delta_requires_four_current_source_builds(self) -> None:
        """! @brief 공개 pair와 P2 mirror를 W05 결과로 대체하지 않고 각각 재빌드합니다. """

        rows = artifacts.plan_artifacts(self.plan)
        for campaign_id, name, application in artifacts.CS_DELTA_BUILD_SLOTS:
            with self.subTest(campaign_id=campaign_id, name=name):
                recipe = rows[(campaign_id, name)]["recipe"]
                self.assertEqual(recipe["builder"], "arduino-cli")
                self.assertEqual(recipe["application"], application)
                self.assertEqual(recipe["jobs"], 1)
        changed = copy.deepcopy(self.plan)
        first = next(iter(changed["source_delta"]["files"]))
        changed["source_delta"]["files"][first] = "f" * 64
        changed.pop("contract_sha256")
        changed["contract_sha256"] = artifacts.canonical_sha256(changed)
        with self.assertRaisesRegex(artifacts.ArtifactFailure, "source delta"):
            artifacts.validate_plan(changed)

    def test_runtime_inputs_are_not_claimed_as_build_outputs(self) -> None:
        """! @brief 키·flash record·fixture는 NOT_PROVIDED manifest로 분리합니다. """

        runtime = artifacts.runtime_inputs_template(self.plan)
        expected = artifacts.runtime_artifacts(self.plan)
        self.assertEqual(len(runtime["entries"]), len(expected))
        self.assertTrue(runtime["entries"])
        self.assertTrue(all(row["status"] == "NOT_PROVIDED" for row in runtime["entries"]))
        self.assertTrue(all(row["path"] is None for row in runtime["entries"]))
        self.assertEqual(
            artifacts.validate_runtime_inputs(self.plan, runtime, require_complete=False),
            [],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            supplied = {}
            for index, key in enumerate(sorted(expected), 1):
                path = root / f"runtime-{index}.bin"
                path.write_bytes(f"runtime-{index}".encode("ascii"))
                supplied[key] = path
            completed = artifacts.bind_runtime_inputs(self.plan, supplied)
            self.assertEqual(
                len(artifacts.validate_runtime_inputs(self.plan, completed, require_complete=True)),
                len(expected),
            )

    def test_prepare_arduino_creates_exact_external_checkout_and_config(self) -> None:
        """! @brief source S와 board gitlink를 외부 hardware checkout에 고정합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "arduino"
            commands = []

            def executor(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
                commands.append((command, kwargs))
                if command[1] == "clone":
                    Path(command[-1]).mkdir(parents=True)
                if "submodule" in command:
                    (destination / "user/hardware/nucode/zephyr/board_package/NU54DK_Zephyr_DTS").mkdir(
                        parents=True
                    )
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            def identity_reader(checkout: Path, *arguments: str) -> str:
                if arguments[0] == "status":
                    return ""
                if checkout.name == "NU54DK_Zephyr_DTS":
                    return SOURCE["board_revision"]
                return SOURCE["source_revision"]

            document = artifacts.prepare_arduino_checkout(
                dict(SOURCE), destination, executor, identity_reader
            )
            config = destination / "arduino-cli.yaml"
            self.assertEqual(document["source_revision"], SOURCE["source_revision"])
            self.assertEqual(document["board_revision"], SOURCE["board_revision"])
            self.assertEqual(document["arduino_config_sha256"], artifacts.file_sha256(config))
            self.assertIn((destination / "user").as_posix(), config.read_text(encoding="utf-8"))
            self.assertTrue(all(call[1]["shell"] is False for call in commands))
            self.assertTrue(any("--no-hardlinks" in call[0] for call in commands))
            self.assertTrue(any("protocol.file.allow=always" in call[0] for call in commands))

    def test_board_inventory_hashes_current_connections_without_raw_uid(self) -> None:
        """! @brief 현재 세 보드를 hash 순서로 배치하고 raw UID는 직렬화하지 않습니다. """

        raw_uids = ("raw-probe-z", "raw-probe-a", "raw-probe-m")
        rows = [
            {
                "uid": uid,
                "probe_sha256": hashlib.sha256(uid.encode("ascii")).hexdigest(),
                "port": f"COM{index + 1}",
                "app": f"COM{index + 1}",
                "aux": f"COM{index + 11}",
                "volume": f"{chr(68 + index)}:/",
            }
            for index, uid in enumerate(raw_uids)
        ]
        inventory = artifacts.current_board_inventory(self.plan, lambda: rows)
        encoded = json.dumps(inventory)
        self.assertEqual(inventory["schema_version"], 2)
        self.assertEqual(
            [row["slot"] for row in inventory["physical_slots"]],
            ["board_1", "board_2", "board_3"],
        )
        self.assertEqual(
            [row["probe_sha256"] for row in inventory["physical_slots"]],
            sorted(row["probe_sha256"] for row in rows),
        )
        self.assertEqual(
            [row["campaign_id"] for row in inventory["campaign_bindings"]],
            [campaign["id"] for campaign in self.plan["campaigns"] if campaign["roles"]],
        )
        diagnostics = next(
            row for row in inventory["campaign_bindings"]
            if row["campaign_id"] == "m33_diagnostics_dtm"
        )
        self.assertEqual(
            [row["role"] for row in diagnostics["roles"]],
            ["tx", "rx", "third"],
        )
        for uid in raw_uids:
            self.assertNotIn(uid, encoded)
        self.assertNotIn('"uid"', encoded)
        self.assertTrue(all(row["app"] == row["port"] and row["aux"] != row["app"]
                            for row in inventory["physical_slots"]))
        for mutation in ("missing", "same", "cross_board"):
            changed = copy.deepcopy(rows)
            if mutation == "missing":
                changed[0].pop("aux")
            elif mutation == "same":
                changed[0]["aux"] = changed[0]["app"]
            else:
                changed[0]["aux"] = changed[1]["aux"]
            with self.subTest(mutation=mutation), self.assertRaises(artifacts.ArtifactFailure):
                artifacts.current_board_inventory(self.plan, lambda: changed)

    def test_live_board_uart_channels_require_exact_uid_and_both_interfaces(self) -> None:
        """! @brief USB 열거의 UID·VID/PID·interface와 APP/AUX 유일성을 함께 검사합니다. """

        def port(device, index, uid="probe-fixture"):
            return SimpleNamespace(device=device, serial_number=uid, vid=0x0D28,
                                   pid=0x0204, location=f"1-2:x.{index}", hwid="")

        ports = [port("COM5", 3), port("COM6", 1), port("COM8", 1, "other")]
        self.assertEqual({"app": "COM5", "aux": "COM6"},
                         artifacts.board_uart_channels("PROBE-FIXTURE", ports))
        for changed in (ports[:1], [ports[0], ports[0], ports[1]],
                        [ports[0], port("COM5", 1)], [ports[0], ports[2]]):
            with self.assertRaises(artifacts.ArtifactFailure):
                artifacts.board_uart_channels("probe-fixture", changed)
        bad_usb = copy.deepcopy(ports[:2])
        bad_usb[1].pid = 0xFFFF
        with self.assertRaises(artifacts.ArtifactFailure):
            artifacts.board_uart_channels("probe-fixture", bad_usb)
        hardware_ids = copy.deepcopy(ports[:2])
        for item, index in zip(hardware_ids, (3, 1)):
            item.location = None
            item.hwid = f"USB VID:PID=0D28:0204 MI_{index:02d}"
        self.assertEqual({"app": "COM5", "aux": "COM6"},
                         artifacts.board_uart_channels("probe-fixture", hardware_ids))

    def test_signing_keys_are_derived_from_all_mcuboot_configs(self) -> None:
        """! @brief build tree 전체가 동일하게 기록한 절대 signing key만 허용합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            planned_sdk = root / "removed-sdk"
            current_sdk = root / "current-sdk"
            relative_key = Path("bootloader/mcuboot/trust.pem")
            key = current_sdk / relative_key
            key.parent.mkdir(parents=True)
            key.write_text("private fixture\n", encoding="ascii")
            paths = {}
            names = ("first", "second", "third")
            for name in names:
                tree = root / name
                config = tree / "mcuboot/zephyr/.config"
                config.parent.mkdir(parents=True)
                config.write_text(
                    f'CONFIG_BOOT_SIGNATURE_KEY_FILE="{(planned_sdk / relative_key).as_posix()}"\n',
                    encoding="utf-8",
                )
                paths[("fixture", name)] = tree
            self.assertEqual(
                artifacts.signing_key_from_build_trees(
                    paths,
                    "fixture",
                    names,
                    planned_sdk,
                    current_sdk,
                ),
                key.resolve(),
            )
            other = root / "other.pem"
            other.write_text("other fixture\n", encoding="ascii")
            (root / "third/mcuboot/zephyr/.config").write_text(
                f'CONFIG_BOOT_SIGNATURE_KEY_FILE="{other.as_posix()}"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "서로 다릅니다"):
                artifacts.signing_key_from_build_trees(
                    paths,
                    "fixture",
                    names,
                    planned_sdk,
                    current_sdk,
                )

    def test_runtime_producer_requires_exact_two_hashed_current_s_outputs(self) -> None:
        """! @brief producer manifest의 두 fixture와 current-S identity를 fail-closed 검사합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ecosystem = root / "ecosystem.json"
            third = root / "third-idle.json"
            ecosystem.write_text(
                json.dumps({"identity": SOURCE["source_revision"] + "a" * 64}),
                encoding="utf-8",
            )
            third.write_text(
                json.dumps({"probe_sha256": "b" * 64, "revisions": {"core": SOURCE["source_revision"]}}),
                encoding="utf-8",
            )
            producer = {
                "schema_version": 1,
                "kind": "m33_w06_runtime_producer",
                "status": "PASS",
                "source_revision": SOURCE["source_revision"],
                "source_clean": True,
                "runtime_inputs": [
                    {
                        "campaign_id": "m33_ecosystem",
                        "name": "fixture",
                        "kind": "fixture",
                        "path": ecosystem.resolve().as_posix(),
                        "sha256": artifacts.file_sha256(ecosystem),
                    },
                    {
                        "campaign_id": "m33_diagnostics_dtm",
                        "name": "third-idle-fixture",
                        "kind": "fixture",
                        "path": third.resolve().as_posix(),
                        "sha256": artifacts.file_sha256(third),
                    },
                ],
            }
            manifest = root / "runtime-producer.json"
            manifest.write_text(json.dumps(producer), encoding="utf-8")

            def module(path: str) -> dict:
                if path.endswith("m33_ecosystem_hil.py"):
                    return {"validate_fixture": lambda _document: None}
                return {"load_watcher_fixture": lambda *_arguments: {}}

            with mock.patch.object(artifacts.runpy, "run_path", side_effect=module):
                paths = artifacts.runtime_producer_paths(self.plan, manifest)
            self.assertEqual(set(paths), {
                ("m33_ecosystem", "fixture"),
                ("m33_diagnostics_dtm", "third-idle-fixture"),
            })
            producer["runtime_inputs"][0]["sha256"] = "f" * 64
            manifest.write_text(json.dumps(producer), encoding="utf-8")
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "file/hash"):
                artifacts.runtime_producer_paths(self.plan, manifest)

    def test_flash_record_binds_current_image_config_and_hashed_probe(self) -> None:
        """! @brief flash record에서 raw UID를 거부하고 current-S build hash를 요구합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "client.hex"
            config = root / "client.config"
            image.write_bytes(b"image")
            config.write_bytes(b"config")
            paths = {
                ("m31_bap_duplex", "client-image"): image,
                ("m31_bap_duplex", "client-config"): config,
            }
            document = {
                "status": "FLASH_PREPARED",
                "source_clean": True,
                "core_revision": SOURCE["source_revision"],
                "client_flash": ["pyocd-sector-hw-reset", "4096"],
                "client_probe_sha256": "a" * 64,
                "client_image_sha256": artifacts.file_sha256(image),
                "client_config_sha256": artifacts.file_sha256(config),
            }
            record = root / "flash.json"
            record.write_text(json.dumps(document), encoding="utf-8")
            artifacts.validate_flash_record(record, "client", SOURCE, paths)
            document["raw_uid"] = "secret"
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "원시 probe UID"):
                artifacts.validate_flash_record(record, "client", SOURCE, paths)

    def test_auto_bind_generates_only_wrong_key_and_completes_nine_slots(self) -> None:
        """! @brief SDK key는 읽기만 하고 wrong key만 외부 root에 생성합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = copy.deepcopy(self.plan)
            sdk = root / "sdk"
            toolchain = root / "toolchain"
            imgtool = sdk / "bootloader/mcuboot/scripts/imgtool.py"
            python = toolchain / "opt/bin/python.exe"
            imgtool.parent.mkdir(parents=True)
            python.parent.mkdir(parents=True)
            imgtool.write_text("fixture\n", encoding="ascii")
            python.write_bytes(b"fixture")
            plan["source"]["sdk_root"] = sdk.as_posix()
            plan["source"]["toolchain_root"] = toolchain.as_posix()
            plan.pop("contract_sha256")
            plan["contract_sha256"] = artifacts.canonical_sha256(plan)
            trust = root / "trust.pem"
            mesh = root / "mesh.pem"
            client = root / "client-flash.json"
            server = root / "server-flash.json"
            ecosystem = root / "ecosystem.json"
            third = root / "third.json"
            producer = root / "producer.json"
            for path, value in (
                (trust, b"trust"), (mesh, b"mesh"), (client, b"client"),
                (server, b"server"), (ecosystem, b"ecosystem"),
                (third, b"third"), (producer, b"producer"),
            ):
                path.write_bytes(value)
            generated = root / "generated"
            key_commands = []

            def executor(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
                key_commands.append(command)
                Path(command[command.index("-k") + 1]).write_bytes(b"wrong")
                return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

            producer_paths = {
                ("m33_ecosystem", "fixture"): ecosystem,
                ("m33_diagnostics_dtm", "third-idle-fixture"): third,
            }
            with mock.patch.object(artifacts, "build_index_paths", return_value={}), \
                    mock.patch.object(
                        artifacts, "signing_key_from_build_trees", side_effect=(trust, mesh)
                    ), mock.patch.object(artifacts, "toolchain_python", return_value=python), \
                    mock.patch.object(artifacts, "toolchain_environment", return_value={}), \
                    mock.patch.object(
                        artifacts, "validate_flash_record", side_effect=("a" * 64, "b" * 64)
                    ), \
                    mock.patch.object(artifacts, "runtime_producer_paths", return_value=producer_paths):
                runtime = artifacts.bind_prepared_runtime_inputs(
                    plan, {}, generated, client, server, producer, executor
                )
            self.assertEqual(len(runtime["entries"]), 9)
            self.assertTrue(all(entry["status"] == "PROVIDED" for entry in runtime["entries"]))
            self.assertEqual(len(key_commands), 1)
            self.assertEqual(key_commands[0][1:3], [str(imgtool.resolve()), "keygen"])
            self.assertNotIn("--erase", key_commands[0])
            self.assertNotIn("--unlock", key_commands[0])

    def test_action_plan_uses_only_build_commands_and_two_jobs(self) -> None:
        """! @brief 실제 plan command가 build-only이고 jobs 2 이하인지 검사합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root / "toolchain/opt/bin/python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"fixture")
            (root / "toolchain/environment.json").write_text(
                '{"env_vars": []}\n',
                encoding="utf-8",
            )
            cli = root / "arduino-cli.exe"
            config = root / "arduino-cli.yaml"
            cli.write_bytes(b"fixture")
            config.write_text("fixture\n", encoding="utf-8")
            actions = artifacts.create_build_actions(
                self.plan,
                root / "work",
                root / "sdk",
                root / "toolchain",
                cli,
                config,
                "nucode:zephyr:nu54dk",
            )
            self.assertTrue(actions)
            for action in actions:
                if action["kind"] == "west_direct":
                    self.assertEqual(str(artifacts.REPOSITORY), action["cwd"])
                    self.assertIn("-B", action["command"])
            artifacts.validate_build_action_graph(actions, root / "work", 2)
            self.assertEqual(len({row["output"] for row in actions}), len(actions))
            self.assertEqual(
                len({row["cache_root"] for row in actions}), len(actions)
            )
            twister = [
                action for action in actions if action["kind"] == "twister"
            ]
            self.assertTrue(twister)
            self.assertEqual(
                len(twister),
                len({action["scratch_output"] for action in twister}),
            )
            for action in twister:
                short_output = Path(action["scratch_output"])
                self.assertLessEqual(len(str(short_output)), 4)
                self.assertEqual(
                    short_output.resolve(),
                    Path(
                        action["command"][
                            action["command"].index("--outdir") + 1
                        ]
                    ).resolve(),
                )
            selected = copy.deepcopy(twister[0])

            def executor(
                command: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess:
                scratch = Path(command[command.index("--outdir") + 1])
                scratch.mkdir()
                (scratch / "marker.bin").write_bytes(b"twister")
                return subprocess.CompletedProcess(
                    command, 0, stdout=b"stdout", stderr=b""
                )

            def make_directory_link(link: Path, target: Path) -> None:
                """! @brief 실패 output에 외부 directory link fixture를 만듭니다. """

                if os.name == "nt":
                    completed = subprocess.run(
                        ["cmd.exe", "/d", "/c", "mklink", "/J",
                         str(link), str(target)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(0, completed.returncode, completed.stderr)
                else:
                    link.symlink_to(target, target_is_directory=True)

            def remove_directory_link(link: Path) -> None:
                """! @brief fixture link만 제거하고 외부 target은 보존합니다. """

                if link.is_symlink():
                    link.unlink()
                else:
                    link.rmdir()

            receipts = artifacts.execute_build_actions(
                [selected], root / "work", 60, 1, executor
            )
            self.assertTrue(Path(selected["output"], "marker.bin").is_file())
            self.assertFalse(Path(selected["scratch_output"]).exists())
            self.assertTrue(receipts[0]["output_exists"])
            self.assertIsNone(receipts[0]["postprocess_error"])

            failed_work = root / "failed-work"
            failed = copy.deepcopy(selected)
            failed["output"] = str(failed_work / "builds/twister")
            failed["cache_root"] = str(failed_work / "caches/twister")
            for key in artifacts.ISOLATED_CACHE_ENVIRONMENTS:
                failed["environment"][key] = str(
                    failed_work / "caches/twister" / key.casefold()
                )
            with mock.patch.object(
                artifacts,
                "sanitize_twister_output",
                side_effect=artifacts.ArtifactFailure("unsafe Twister output"),
            ):
                with self.assertRaisesRegex(
                    artifacts.ArtifactFailure,
                    "postprocess=ArtifactFailure",
                ):
                    artifacts.execute_build_actions(
                        [failed], failed_work, 60, 1, executor
                    )
            failure = artifacts.strict_json(
                failed_work / "m33-w06-build-failure.json"
            )
            self.assertEqual(
                "ArtifactFailure",
                failure["actions"][0]["postprocess_error"],
            )
            self.assertFalse(Path(failed["output"]).exists())
            failed_scratch = Path(failed["scratch_output"])
            (failed_scratch / "marker.bin").unlink()
            failed_scratch.rmdir()

            preserved_work = root / "preserved-failure"
            preserved = copy.deepcopy(selected)
            preserved["output"] = str(preserved_work / "builds/twister")
            preserved["cache_root"] = str(preserved_work / "caches/twister")
            for key in artifacts.ISOLATED_CACHE_ENVIRONMENTS:
                preserved["environment"][key] = str(
                    preserved_work / "caches/twister" / key.casefold()
                )

            def failed_executor(
                command: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess:
                """! @brief 비영 종료의 raw report와 log를 원본 byte로 보존합니다. """

                scratch = Path(command[command.index("--outdir") + 1])
                scratch.mkdir()
                (scratch / "twister.json").write_bytes(b'{"status":"error"}')
                scenario = scratch / "failed-scenario"
                scenario.mkdir()
                (scenario / "build.log").write_bytes(b"full error path\n")
                links = scratch / "twister_links"
                links.mkdir()
                make_directory_link(links / "test_0", scenario)
                return subprocess.CompletedProcess(
                    command, 17, stdout=b"partial", stderr=b"failed"
                )

            with self.assertRaisesRegex(artifacts.ArtifactFailure, "exit=17"):
                artifacts.execute_build_actions(
                    [preserved], preserved_work, 60, 1, failed_executor
                )
            preserved_failure = artifacts.strict_json(
                preserved_work / "m33-w06-build-failure.json"
            )
            self.assertEqual("FAIL", preserved_failure["status"])
            preserved_receipt = preserved_failure["actions"][0]
            self.assertEqual(17, preserved_receipt["exit_code"])
            self.assertIsNone(preserved_receipt["postprocess_error"])
            self.assertTrue(preserved_receipt["output_exists"])
            preserved_output = Path(preserved["output"])
            self.assertEqual(
                b'{"status":"error"}', (preserved_output / "twister.json").read_bytes()
            )
            self.assertEqual(
                b"full error path\n", (preserved_output / "failed-scenario/build.log").read_bytes()
            )
            self.assertFalse((preserved_output / "twister_links").exists())
            self.assertFalse(Path(preserved["scratch_output"]).exists())

            for failure_kind in ("nonzero", "timeout"):
                unsafe_work = root / f"{failure_kind}-work"
                unsafe = copy.deepcopy(selected)
                unsafe["output"] = str(
                    unsafe_work / "builds/twister"
                )
                unsafe["cache_root"] = str(
                    unsafe_work / "caches/twister"
                )
                for key in artifacts.ISOLATED_CACHE_ENVIRONMENTS:
                    unsafe["environment"][key] = str(
                        unsafe_work
                        / "caches/twister"
                        / key.casefold()
                    )
                external_target = root / f"{failure_kind}-external"
                external_target.mkdir()

                def unsafe_executor(
                    command: list[str], **_kwargs: object
                ) -> subprocess.CompletedProcess:
                    scratch = Path(command[command.index("--outdir") + 1])
                    scratch.mkdir()
                    links = scratch / "twister_links"
                    links.mkdir()
                    make_directory_link(links / "test_0", external_target)
                    if failure_kind == "timeout":
                        raise subprocess.TimeoutExpired(
                            command, 60, output=b"partial", stderr=b"timeout"
                        )
                    return subprocess.CompletedProcess(
                        command, 17, stdout=b"partial", stderr=b"failed"
                    )

                expected_failure = (
                    "timeout=True" if failure_kind == "timeout" else "exit=17"
                )
                with self.subTest(failure_kind=failure_kind):
                    with self.assertRaisesRegex(
                        artifacts.ArtifactFailure, expected_failure
                    ):
                        artifacts.execute_build_actions(
                            [unsafe], unsafe_work, 60, 1, unsafe_executor
                        )
                    unsafe_receipt = artifacts.strict_json(
                        unsafe_work / "m33-w06-build-failure.json"
                    )["actions"][0]
                    self.assertFalse(unsafe_receipt["output_exists"])
                    self.assertFalse(Path(unsafe["output"]).exists())
                    unsafe_scratch = Path(unsafe["scratch_output"])
                    unsafe_link = unsafe_scratch / "twister_links/test_0"
                    self.assertTrue(unsafe_link.exists())
                    remove_directory_link(unsafe_link)
                    (unsafe_scratch / "twister_links").rmdir()
                    unsafe_scratch.rmdir()

            for action in actions:
                artifacts.validate_build_command(action)
                self.assertLessEqual(action["jobs"], 2)
                cache_root = Path(action["cache_root"]).resolve()
                for key in artifacts.ISOLATED_CACHE_ENVIRONMENTS:
                    self.assertTrue(
                        Path(action["environment"][key]).resolve()
                        .is_relative_to(cache_root)
                    )
            arduino_actions = [
                action for action in actions if action["kind"] == "arduino-cli"
            ]
            self.assertTrue(arduino_actions)
            expected_libraries = (ROOT / "tests/arduino-cli").resolve()
            for action in arduino_actions:
                libraries_index = action["command"].index("--libraries") + 1
                self.assertEqual(
                    Path(action["command"][libraries_index]).resolve(),
                    expected_libraries,
                )
                self.assertTrue(
                    Path(action["environment"]["NUCODE_BUILD_CACHE_ROOT"])
                    .resolve().is_relative_to(Path(action["cache_root"]).resolve())
                )
            self.assertEqual(
                len(arduino_actions),
                len({
                    action["environment"]["NUCODE_BUILD_CACHE_ROOT"]
                    for action in arduino_actions
                }),
            )
            profile_records = [
                action for action in actions
                if action["kind"] == "profile_record"
            ]
            self.assertTrue(profile_records)
            self.assertTrue(all(len(action["depends_on"]) == 1
                                for action in profile_records))

    def _actual_actions(self, root: Path) -> list[dict]:
        """! @brief production plan에서 path와 무관한 action/shard 계약을 만들 fixture를 준비합니다. """

        python = root / "toolchain/opt/bin/python.exe"
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_bytes(b"fixture")
        (root / "toolchain/environment.json").write_text(
            '{"env_vars": []}\n', encoding="utf-8"
        )
        cli = root / "arduino-cli.exe"
        config = root / "arduino-cli.yaml"
        cli.write_bytes(b"fixture")
        config.write_text("fixture\n", encoding="utf-8")
        return artifacts.create_shard_build_actions(
            self.plan, root / "work", root / "sdk", root / "toolchain",
            cli, config, "nucode:zephyr:nu54dk",
        )

    def test_shard_plan_is_deterministic_complete_and_dependency_closed(self) -> None:
        """! @brief 4-shard 계획은 141/9/150 slot과 모든 action을 정확히 한 번 고정합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actions = self._actual_actions(root / "first")
            other_actions = self._actual_actions(root / "second")
            shard_plan = artifacts.create_build_shard_plan(
                self.plan, actions, 4
            )
            self.assertEqual(
                shard_plan,
                artifacts.create_build_shard_plan(
                    self.plan, other_actions, 4
                ),
            )
            self.assertEqual(
                (141, 9, 150),
                (
                    shard_plan["build_slot_count"],
                    shard_plan["runtime_slot_count"],
                    shard_plan["total_slot_count"],
                ),
            )
            self.assertEqual(
                len(actions), shard_plan["action_count"]
            )
            assignments = {
                row["id"]: row for row in shard_plan["assignments"]
            }
            self.assertEqual(set(assignments), {row["id"] for row in actions})
            slots = [
                (slot["campaign_id"], slot["name"])
                for row in shard_plan["assignments"] for slot in row["slots"]
            ]
            self.assertEqual(141, len(slots))
            self.assertEqual(141, len(set(slots)))
            for row in shard_plan["assignments"]:
                for dependency in row["depends_on"]:
                    self.assertEqual(
                        row["shard"], assignments[dependency]["shard"]
                    )
            changed = copy.deepcopy(shard_plan)
            changed["assignments"][0]["shard"] = (
                changed["assignments"][0]["shard"] + 1
            ) % 4
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "shard plan"):
                artifacts.validate_build_shard_plan(
                    changed, self.plan, actions, 4
                )

    def test_shard_build_and_stage_reject_source_internal_roots(self) -> None:
        """! @brief shard build와 stage가 ignored 여부와 무관하게 source 내부 쓰기를 거부합니다. """

        shard_plan = {"shard_count": 1}
        sdk = Path(self.plan["source"]["sdk_root"]).resolve()
        toolchain = artifacts.toolchain_bundle_root(
            Path(self.plan["source"]["toolchain_root"])
        )
        forbidden = (ROOT, ROOT.parent, ROOT / ".m33-w06-forbidden",
                     sdk, toolchain)
        for shard_root in forbidden:
            with self.subTest(kind="shard", root=shard_root), \
                    self.assertRaisesRegex(
                        artifacts.ArtifactFailure, "source/SDK/toolchain"):
                artifacts.build_shard_from_plan(
                    self.plan,
                    shard_plan,
                    0,
                    shard_root,
                    shard_root / "result.json",
                    ROOT / "missing-arduino-cli.exe",
                    ROOT / "missing-arduino-cli.yaml",
                    "nucode:zephyr:nu54dk",
                    1,
                    plan_validator=lambda _plan: None,
                )
            with self.subTest(kind="stage", root=shard_root), \
                    self.assertRaisesRegex(
                        artifacts.ArtifactFailure, "source/SDK/toolchain"):
                artifacts.stage_artifacts(self.plan, {}, shard_root)

        link_like = mock.Mock()
        link_like.resolve.return_value = ROOT
        with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                    "source/SDK/toolchain"):
            artifacts.require_external_fresh_root(
                link_like, self.plan["source"], "symlink fixture"
            )

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "fresh-work"
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "바로 아래"):
                artifacts.build_shard_from_plan(
                    self.plan,
                    shard_plan,
                    0,
                    work,
                    ROOT / ".m33-w06-forbidden-output.json",
                    ROOT / "missing-arduino-cli.exe",
                    ROOT / "missing-arduino-cli.yaml",
                    "nucode:zephyr:nu54dk",
                    1,
                    plan_validator=lambda _plan: None,
                )
            self.assertFalse(work.exists())
            with self.assertRaisesRegex(
                    artifacts.ArtifactFailure, "source/SDK/toolchain"):
                artifacts.build_from_plan(
                    self.plan,
                    work,
                    ROOT / ".m33-w06-forbidden-index.json",
                    Path(directory) / "runtime.json",
                    ROOT / "missing-arduino-cli.exe",
                    ROOT / "missing-arduino-cli.yaml",
                    "nucode:zephyr:nu54dk",
                    60,
                    plan_validator=lambda _plan: None,
                )
            self.assertFalse(work.exists())
        with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                    "source/SDK/toolchain"):
            artifacts.require_external_output(
                ROOT / ".m33-w06-forbidden-control.json",
                self.plan["source"],
                "control",
            )

    def test_dtm_shard_keeps_manifest_with_dtm_action(self) -> None:
        """! @brief DTM build record는 diagnostics-build가 아닌 DTM action manifest를 가리킵니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actions = self._actual_actions(root)
            owners = artifacts.build_slot_action_owners(self.plan, actions)
            slot_keys = {
                key for key, owner in owners.items()
                if owner == "diagnostics-dtm"
            }
            partial = artifacts.partial_build_plan(self.plan, slot_keys)
            selected = [
                action for action in actions
                if action["id"] == "diagnostics-dtm"
            ]
            entries = artifacts.resolve_build_entries(partial, selected)
            by_key = {
                (entry["campaign_id"], entry["name"]): Path(entry["path"])
                for entry in entries
            }
            self.assertEqual(
                Path(selected[0]["output"]) / "manifest.json",
                by_key[("m33_diagnostics_dtm", "build-manifest")],
            )

    def _write_shard_packages(
        self,
        root: Path,
        shard_plan: dict,
    ) -> list[Path]:
        """! @brief aggregate 무결성 시험용 portable shard package를 만듭니다. """

        manifests = []
        for shard_index in range(shard_plan["shard_count"]):
            package = root / f"package-{shard_index}"
            package.mkdir(parents=True)
            expected_actions = [
                row for row in shard_plan["assignments"]
                if row["shard"] == shard_index
            ]
            action_rows = []
            entry_rows = []
            for assignment in expected_actions:
                output = package / "outputs" / assignment["id"]
                output.mkdir(parents=True)
                (output / "marker.bin").write_bytes(assignment["id"].encode())
                stdout = package / "logs" / f"{assignment['id']}.stdout.bin"
                stderr = package / "logs" / f"{assignment['id']}.stderr.bin"
                stdout.parent.mkdir(parents=True, exist_ok=True)
                stdout.write_bytes(b"stdout")
                stderr.write_bytes(b"")
                receipt = {
                    "ordinal": assignment["ordinal"],
                    "id": assignment["id"],
                    "kind": assignment["kind"],
                    "depends_on": assignment["depends_on"],
                    "command": ["fixture"],
                    "cwd": str(ROOT),
                    "output": str(output),
                    "cache_root": str(package / "cache" / assignment["id"]),
                    "shell": False,
                    "jobs": assignment["jobs"],
                    "timeout_seconds": 60,
                    "timed_out": False,
                    "exit_code": 0,
                    "launch_error": None,
                    "postprocess_error": None,
                    "output_exists": True,
                    "stdout": {"path": str(stdout), "sha256": artifacts.file_sha256(stdout)},
                    "stderr": {"path": str(stderr), "sha256": artifacts.file_sha256(stderr)},
                }
                action_rows.append({
                    "ordinal": assignment["ordinal"],
                    "id": assignment["id"],
                    "kind": assignment["kind"],
                    "depends_on": assignment["depends_on"],
                    "receipt": receipt,
                    "output": {
                        "path": output.relative_to(package).as_posix(),
                        "sha256": artifacts.directory_sha256(output),
                    },
                    "stdout": {
                        "path": stdout.relative_to(package).as_posix(),
                        "sha256": artifacts.file_sha256(stdout),
                    },
                    "stderr": {
                        "path": stderr.relative_to(package).as_posix(),
                        "sha256": artifacts.file_sha256(stderr),
                    },
                })
                for slot in assignment["slots"]:
                    entry = package / "entries" / slot["campaign_id"] / slot["name"]
                    entry.parent.mkdir(parents=True, exist_ok=True)
                    entry.write_bytes(
                        f"{slot['campaign_id']}:{slot['name']}".encode()
                    )
                    entry_rows.append({
                        **slot,
                        "path": entry.relative_to(package).as_posix(),
                        "origin_path": entry.resolve().as_posix(),
                        "sha256": artifacts.file_sha256(entry),
                        "provenance": ([{
                            "path": entry.relative_to(package).as_posix(),
                            "origin_path": entry.resolve().as_posix(),
                            "sha256": artifacts.file_sha256(entry),
                        }] if slot["kind"] == "target_image" else []),
                    })
            document = {
                "schema_version": 1,
                "kind": "m33_w06_build_shard_result",
                "status": "BUILD_ONLY",
                "functional_hil": "NOT_RUN",
                "source": self.plan["source"],
                "source_binding": artifacts.validate_source_binding(
                    self.plan["source"], self.plan["source"]
                ),
                "run_id": None,
                "run_attempt": None,
                "origin_root": package.as_posix(),
                "plan_sha256": self.plan["contract_sha256"],
                "shard_plan_sha256": shard_plan["contract_sha256"],
                "shard_index": shard_index,
                "shard_count": shard_plan["shard_count"],
                "action_count": len(action_rows),
                "build_slot_count": len(entry_rows),
                "actions": action_rows,
                "entries": entry_rows,
            }
            document["manifest_sha256"] = artifacts.canonical_sha256(document)
            manifest = package / f"m33-w06-shard-{shard_index}.json"
            artifacts.atomic_write_json(manifest, document)
            manifests.append(manifest)
        return manifests

    def test_shard_aggregate_is_build_only_complete_and_tamper_closed(self) -> None:
        """! @brief aggregate는 150/141/9를 고정하고 shard byte 변조를 거부합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actions = self._actual_actions(root / "model")
            shard_plan = artifacts.create_build_shard_plan(
                self.plan, actions, 4
            )
            self._write_shard_packages(root / "shards", shard_plan)
            identity = lambda *_args: dict(self.plan["source"])

            tampered_root = root / "tampered"
            tampered_actions = self._actual_actions(root / "tampered-model")
            tampered_plan = artifacts.create_build_shard_plan(
                self.plan, tampered_actions, 4
            )
            tampered = self._write_shard_packages(tampered_root, tampered_plan)
            first = artifacts.strict_json(tampered[0])["entries"][0]
            (tampered[0].parent / first["path"]).write_bytes(b"tampered")
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "hash"):
                artifacts.aggregate_build_shards(
                    self.plan,
                    tampered_plan,
                    tampered_root,
                    tampered_root / "aggregate.json",
                    tampered_root / "index.json",
                    tampered_root / "runtime.json",
                    tampered_actions,
                    identity_validator=identity,
                )

            missing_root = root / "missing"
            missing_actions = self._actual_actions(root / "missing-model")
            missing_plan = artifacts.create_build_shard_plan(
                self.plan, missing_actions, 4
            )
            missing = self._write_shard_packages(missing_root, missing_plan)
            missing[-1].unlink()
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "정확히 4개"):
                artifacts.aggregate_build_shards(
                    self.plan,
                    missing_plan,
                    missing_root,
                    missing_root / "aggregate.json",
                    missing_root / "index.json",
                    missing_root / "runtime.json",
                    missing_actions,
                    identity_validator=identity,
                )

            recipe_root = root / "recipe-tamper"
            recipe_actions = self._actual_actions(root / "recipe-model")
            recipe_plan = artifacts.create_build_shard_plan(
                self.plan, recipe_actions, 4
            )
            recipe_manifests = self._write_shard_packages(
                recipe_root, recipe_plan
            )
            recipe_document = artifacts.strict_json(recipe_manifests[0])
            recipe_document["entries"][0]["recipe_sha256"] = "0" * 64
            recipe_document.pop("manifest_sha256")
            recipe_document["manifest_sha256"] = artifacts.canonical_sha256(
                recipe_document
            )
            recipe_manifests[0].unlink()
            artifacts.atomic_write_json(recipe_manifests[0], recipe_document)
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "recipe"):
                artifacts.aggregate_build_shards(
                    self.plan,
                    recipe_plan,
                    recipe_root,
                    recipe_root / "aggregate.json",
                    recipe_root / "index.json",
                    recipe_root / "runtime.json",
                    recipe_actions,
                    identity_validator=identity,
                )

            receipt_root = root / "receipt-schema-tamper"
            receipt_actions = self._actual_actions(root / "receipt-model")
            receipt_plan = artifacts.create_build_shard_plan(
                self.plan, receipt_actions, 4
            )
            receipt_manifests = self._write_shard_packages(
                receipt_root, receipt_plan
            )
            receipt_document = artifacts.strict_json(receipt_manifests[0])
            receipt_document["actions"][0]["receipt"].pop(
                "postprocess_error"
            )
            receipt_document.pop("manifest_sha256")
            receipt_document["manifest_sha256"] = artifacts.canonical_sha256(
                receipt_document
            )
            receipt_manifests[0].unlink()
            artifacts.atomic_write_json(
                receipt_manifests[0], receipt_document
            )
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "receipt"):
                artifacts.aggregate_build_shards(
                    self.plan,
                    receipt_plan,
                    receipt_root,
                    receipt_root / "aggregate.json",
                    receipt_root / "index.json",
                    receipt_root / "runtime.json",
                    receipt_actions,
                    identity_validator=identity,
                )

    def test_production_aggregate_revalidates_after_real_relocation(self) -> None:
        """! @brief mock 없이 aggregate index를 이동한 뒤 원본 shard SHA까지 재검증합니다. """

        with tempfile.TemporaryDirectory(prefix="m33-w06-aggregate-") as directory:
            root = Path(directory)
            plan = small_plan()
            plan["source"] = {
                **SOURCE,
                "sdk_root": "D:/ncs/v3.4.0",
                "toolchain_root": "D:/ncs/toolchains/dcbdc366a1/opt/zephyr-sdk",
            }
            campaign = plan["campaigns"][0]
            campaign["artifacts"] = []
            actions = []
            for index in range(4):
                role = f"role-{index}"
                scenario = f"fixture.scenario.{index}"
                campaign["artifacts"].append({
                    "name": f"hex-{role}",
                    "kind": "target_image",
                    "role": role,
                    "binding": role,
                    "required_for_dispatch": True,
                    "recipe": {
                        "builder": "run_zephyr_build.py",
                        "application": "fixture",
                        "scenario": scenario,
                        "jobs": 1,
                    },
                })
                actions.append({
                    "plan_ordinal": index + 1,
                    "id": f"action-{index}",
                    "kind": "twister",
                    "depends_on": [],
                    "jobs": 1,
                    "scenarios": [scenario],
                })
            plan["contract_sha256"] = artifacts.canonical_sha256({
                key: value for key, value in plan.items()
                if key != "contract_sha256"
            })
            shard_plan = artifacts.create_build_shard_plan(plan, actions, 4)
            run_id = "123456"
            run_attempt = "3"
            contract_path = root / "TRANSFER-CONTRACT.txt"
            contract_path.write_text(
                "SCHEMA=m33-w06-transfer-v1\n"
                f"RUN_ID={run_id}\n"
                f"RUN_ATTEMPT={run_attempt}\n"
                "SHARD_COUNT=4\n"
                "AGGREGATE_ONLY_SUFFICIENT=0\n"
                + "".join(
                    f"SHARD_{index}=m33-w06-build-shard-{index}-{run_id}"
                    f"-attempt-{run_attempt}\n"
                    for index in range(4)
                ),
                encoding="ascii",
            )
            contract = artifacts.parse_transfer_contract(contract_path)
            shards = root / "shards"
            shards.mkdir()
            for shard_index in range(4):
                artifact_name = contract["artifacts"][shard_index]
                package = shards / artifact_name
                package.mkdir()
                assignment = next(
                    row for row in shard_plan["assignments"]
                    if row["shard"] == shard_index
                )
                output = package / "outputs" / assignment["id"]
                output.mkdir(parents=True)
                (output / "marker.bin").write_bytes(assignment["id"].encode())
                stdout = package / "logs/stdout.bin"
                stderr = package / "logs/stderr.bin"
                stdout.parent.mkdir()
                stdout.write_bytes(b"stdout")
                stderr.write_bytes(b"")
                receipt = {
                    "ordinal": assignment["ordinal"],
                    "id": assignment["id"],
                    "kind": assignment["kind"],
                    "depends_on": [],
                    "command": ["fixture"],
                    "cwd": str(ROOT),
                    "output": output.resolve().as_posix(),
                    "cache_root": (package / "cache").resolve().as_posix(),
                    "shell": False,
                    "jobs": 1,
                    "timeout_seconds": 60,
                    "timed_out": False,
                    "exit_code": 0,
                    "launch_error": None,
                    "postprocess_error": None,
                    "output_exists": True,
                    "stdout": {
                        "path": stdout.resolve().as_posix(),
                        "sha256": artifacts.file_sha256(stdout),
                    },
                    "stderr": {
                        "path": stderr.resolve().as_posix(),
                        "sha256": artifacts.file_sha256(stderr),
                    },
                }
                slot = assignment["slots"][0]
                image = write_native_image(
                    package / "entries",
                    f"slot-{shard_index}",
                    f":04000000010203{shard_index:02X}{(0xF6 - shard_index):02X}",
                )
                native_path = image.parent.parent / "nucode_arduino_core_build.yml"
                native_path.write_text(
                    native_path.read_text(encoding="utf-8").replace(
                        SOURCE["toolchain_root"],
                        plan["source"]["toolchain_root"],
                    ),
                    encoding="utf-8",
                )
                entry = {
                    **slot,
                    "path": image.relative_to(package).as_posix(),
                    "origin_path": image.resolve().as_posix(),
                    "sha256": artifacts.file_sha256(image),
                    "provenance": [
                        {
                            "path": path.relative_to(package).as_posix(),
                            "origin_path": path.resolve().as_posix(),
                            "sha256": artifacts.file_sha256(path),
                        }
                        for path in (
                            native_path,
                            image.parent / ".config",
                        )
                    ],
                }
                action = {
                    "ordinal": assignment["ordinal"],
                    "id": assignment["id"],
                    "kind": assignment["kind"],
                    "depends_on": [],
                    "receipt": receipt,
                    "output": {
                        "path": output.relative_to(package).as_posix(),
                        "sha256": artifacts.directory_sha256(output),
                    },
                    "stdout": {
                        "path": stdout.relative_to(package).as_posix(),
                        "sha256": artifacts.file_sha256(stdout),
                    },
                    "stderr": {
                        "path": stderr.relative_to(package).as_posix(),
                        "sha256": artifacts.file_sha256(stderr),
                    },
                }
                document = {
                    "schema_version": 1,
                    "kind": "m33_w06_build_shard_result",
                    "status": "BUILD_ONLY",
                    "functional_hil": "NOT_RUN",
                    "source": plan["source"],
                    "source_binding": artifacts.validate_source_binding(
                        plan["source"], plan["source"]
                    ),
                    "run_id": run_id,
                    "run_attempt": run_attempt,
                    "origin_root": package.resolve().as_posix(),
                    "plan_sha256": plan["contract_sha256"],
                    "shard_plan_sha256": shard_plan["contract_sha256"],
                    "shard_index": shard_index,
                    "shard_count": 4,
                    "action_count": 1,
                    "build_slot_count": 1,
                    "actions": [action],
                    "entries": [entry],
                }
                document["manifest_sha256"] = artifacts.canonical_sha256(document)
                artifacts.atomic_write_json(
                    package / f"m33-w06-shard-{shard_index}.json",
                    document,
                )
            failed_outputs = (
                shards / "failed-aggregate.json",
                shards / "failed-index.json",
                shards / "failed-runtime.json",
            )
            portable_path = artifacts._portable_path

            def fail_late(path: Path, base: Path, label: str) -> str:
                if label == "aggregate build entry":
                    raise artifacts.ArtifactFailure("late portable failure")
                return portable_path(path, base, label)

            with mock.patch.object(artifacts, "_portable_path",
                                   side_effect=fail_late):
                with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                            "late portable failure"):
                    artifacts.aggregate_build_shards(
                        plan,
                        shard_plan,
                        shards,
                        failed_outputs[0],
                        failed_outputs[1],
                        failed_outputs[2],
                        actions,
                        transfer_contract=contract,
                        identity_validator=lambda *_args: dict(SOURCE),
                        plan_validator=lambda _plan: None,
                        expected_denominator=(4, 4, 0),
                        validate_source_digests=False,
                    )
            self.assertTrue(all(not path.exists() for path in failed_outputs))
            plan_path = root / "plan.json"
            shard_plan_path = root / "shard-plan.json"
            actions_path = root / "actions.json"
            artifacts.atomic_write_json(plan_path, plan)
            artifacts.atomic_write_json(shard_plan_path, shard_plan)
            artifacts.atomic_write_json(actions_path, actions)
            cli = root / "arduino-cli.exe"
            config = root / "arduino-cli.yaml"
            cli.write_bytes(b"fixture")
            config.write_text("fixture\n", encoding="utf-8")
            harness = root / "aggregate-cli-harness.py"
            harness.write_text(
                "import json\n"
                "from pathlib import Path\n"
                "import sys\n"
                f"sys.path.insert(0, {str(CI)!r})\n"
                "import m33_w06_artifacts as module\n"
                f"source = json.loads({json.dumps(json.dumps(SOURCE))})\n"
                f"actions_path = Path({str(actions_path)!r})\n"
                "module.validate_source_lock = lambda *_args: dict(source)\n"
                "module.validate_plan = lambda _plan: None\n"
                "def action_factory(*, plan, work_root, sdk_root, "
                "toolchain_root, arduino_cli, arduino_config, fqbn_prefix):\n"
                "    assert Path(arduino_cli).name == 'arduino-cli.exe'\n"
                "    assert Path(arduino_config).name == 'arduino-cli.yaml'\n"
                "    return json.loads(actions_path.read_text(encoding='utf-8'))\n"
                "module.create_shard_build_actions = action_factory\n"
                "original = module.aggregate_build_shards\n"
                "def aggregate_factory(*, plan, shard_plan, shards_root, output, "
                "index_output, runtime_output, actions, sdk_root, toolchain_root, "
                "transfer_contract):\n"
                "    assert transfer_contract['run_id'] == '123456'\n"
                "    assert transfer_contract['run_attempt'] == '3'\n"
                "    return original(plan=plan, shard_plan=shard_plan, "
                "shards_root=shards_root, output=output, "
                "index_output=index_output, runtime_output=runtime_output, "
                "actions=actions, sdk_root=sdk_root, "
                "toolchain_root=toolchain_root, "
                "transfer_contract=transfer_contract, "
                "identity_validator=lambda *_args: dict(source), "
                "plan_validator=lambda _plan: None, "
                "expected_denominator=(4, 4, 0), "
                "validate_source_digests=False)\n"
                "module.aggregate_build_shards = aggregate_factory\n"
                "raise SystemExit(module.main(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(harness),
                    "aggregate-shards",
                    "--plan", str(plan_path),
                    "--shard-plan", str(shard_plan_path),
                    "--shards-root", str(shards),
                    "--work-root", str(root / "action-model/work"),
                    "--arduino-cli", str(cli),
                    "--arduino-config", str(config),
                    "--index-output", str(shards / "index.json"),
                    "--runtime-inputs-output", str(shards / "runtime.json"),
                    "--output", str(shards / "aggregate.json"),
                    "--transfer-contract", str(contract_path),
                    "--sdk-root", SOURCE["sdk_root"],
                    "--toolchain-root", SOURCE["toolchain_root"],
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn("M33_W06_CI_BUILD_ONLY=4", completed.stdout)
            result = artifacts.strict_json(shards / "aggregate.json")
            self.assertEqual(4, result["build_slot_count"])
            identity = lambda *_args: dict(SOURCE)
            relocated = root / "relocated"
            shards.rename(relocated)
            index = artifacts.strict_json(relocated / "index.json")
            validated = artifacts.validate_index(
                plan,
                index,
                validate_source_digests=False,
                effective_source=SOURCE,
                relocation_root=relocated,
            )
            self.assertEqual(4, len(validated))
            mixed = copy.deepcopy(index)
            mixed["relocations"][0]["run_attempt"] = "4"
            with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                        "transfer contract|manifest identity"):
                artifacts.validate_index(
                    plan,
                    mixed,
                    validate_source_digests=False,
                    effective_source=SOURCE,
                    relocation_root=relocated,
                )
            removed = copy.deepcopy(index)
            removed["relocations"] = []
            with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                        "relocation 분모|entry 형식"):
                artifacts.validate_index(
                    plan,
                    removed,
                    validate_source_digests=False,
                    effective_source=SOURCE,
                    relocation_root=relocated,
                )
            flattened = root / "flattened"
            flattened.mkdir()
            for manifest in relocated.glob("*/m33-w06-shard-*.json"):
                shutil.copy2(manifest, flattened / manifest.name)
            with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                        "artifact directory|별도 directory"):
                artifacts.aggregate_build_shards(
                    plan,
                    shard_plan,
                    flattened,
                    flattened / "aggregate.json",
                    flattened / "index.json",
                    flattened / "runtime.json",
                    actions,
                    transfer_contract=contract,
                    identity_validator=identity,
                    plan_validator=lambda _plan: None,
                    expected_denominator=(4, 4, 0),
                    validate_source_digests=False,
                )
            first_relocation = index["relocations"][0]
            first_manifest = artifacts.strict_json(
                relocated / first_relocation["artifact_name"] /
                Path(first_relocation["manifest_path"]).name
            )
            reference = first_manifest["entries"][0]["provenance"][0]
            provenance_path = (
                relocated / first_relocation["artifact_name"] /
                reference["path"]
            )
            original_provenance = provenance_path.read_bytes()
            provenance_path.write_bytes(b"tampered-provenance")
            with self.assertRaisesRegex(artifacts.ArtifactFailure,
                                        "provenance byte/hash"):
                artifacts.validate_index(
                    plan,
                    index,
                    validate_source_digests=False,
                    effective_source=SOURCE,
                    relocation_root=relocated,
                )
            provenance_path.write_bytes(original_provenance)
            tampered = Path(validated[0]["source"])
            tampered.write_bytes(b"tampered")
            with self.assertRaisesRegex(
                    artifacts.ArtifactFailure,
                    "shard entry byte/hash|shard byte/hash"):
                artifacts.validate_index(
                    plan,
                    index,
                    validate_source_digests=False,
                    effective_source=SOURCE,
                    relocation_root=relocated,
                )

    def test_github_shard_workflow_is_pinned_exact_and_build_only(self) -> None:
        """! @brief W06 Actions는 고정 pin/shard aggregate만 수행하고 HIL PASS를 만들지 않습니다. """

        workflow = (
            ROOT / ".github/workflows/m33-w06-build-shards.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("- Dev-0.6.0-M33", workflow)
        trigger = re.search(
            r"(?ms)^  push:\n"
            r"    branches:\n"
            r"      - Dev-0\.6\.0-M33\n"
            r"    paths:\n"
            r"(?P<paths>(?:      - [^\n]+\n)+)"
            r"  workflow_dispatch:",
            workflow,
        )
        self.assertIsNotNone(trigger)
        push_paths = {
            line.removeprefix("      - ").strip().strip('"')
            for line in trigger.group("paths").splitlines()
        }
        required_paths = {
            ".github/workflows/m33-w06-build-shards.yml",
            ".gitmodules",
            "board_package/NU54DK_Zephyr_DTS",
            "boards.txt",
            "platform.txt",
            "tools/ci/m33_w06*",
            "tools/ci/ncs-3.4.0.lock.json",
            "tools/ci/cmake/**",
            "tests/host/test_build_matrix_runner.py",
            "tools/bluetooth/m33_contract.py",
            "tools/bluetooth/m33_regression.py",
            "tools/bluetooth/m33_diagnostics.py",
            "tools/bluetooth/m33_diagnostics_campaign.py",
            "tools/bluetooth/m33_ecosystem_hil.py",
            "tests/hil/nu54dk/**",
            "tests/zephyr/**",
            "tests/arduino-cli/**",
            "libraries/**",
            "cores/**",
            "variants/**",
        }
        self.assertEqual(set(), required_paths - push_paths)
        self.assertNotIn("**", push_paths)
        self.assertFalse(any(path.startswith("00_Docs/") for path in push_paths))
        self.assertFalse(any("evidence" in path.lower() for path in push_paths))
        self.assertIn(
            "!variants/nu54dk/m33-release-readiness.json", push_paths
        )
        self.assertIn("shard: [0, 1, 2, 3]", workflow)
        self.assertIn("m33_regression.py snapshot", workflow)
        self.assertIn(
            'm33_contract.py --sdk-root "$env:NUCODE_NCS_ROOT" --check',
            workflow,
        )
        self.assertIn("prerequisite_blockers", workflow)
        self.assertIn("m33_w06_artifacts.py shard-plan", workflow)
        self.assertIn("m33_w06_artifacts.py build-shard", workflow)
        self.assertIn("m33_w06_artifacts.py aggregate-shards", workflow)
        self.assertIn("include-hidden-files: true", workflow)
        self.assertIn("--sdk-root $env:NUCODE_NCS_ROOT", workflow)
        self.assertIn("--toolchain-root $env:NUCODE_TOOLCHAIN_ROOT", workflow)
        self.assertIn("path: D:\\m33-w06-aggregate", workflow)
        self.assertIn("m33-w06-artifact-plan.json", workflow)
        self.assertIn("m33-w06-build-shard-plan.json", workflow)
        self.assertIn("AGGREGATE_ONLY_SUFFICIENT=0", workflow)
        self.assertIn("SCHEMA=m33-w06-transfer-v1", workflow)
        self.assertIn("SHARD_COUNT=4", workflow)
        self.assertIn("RUN_ATTEMPT=$env:GITHUB_RUN_ATTEMPT", workflow)
        self.assertIn("SHARD_0=m33-w06-build-shard-0-", workflow)
        self.assertIn("--transfer-contract", workflow)
        self.assertIn("TRANSFER-CONTRACT.txt", workflow)
        self.assertNotIn("merge-multiple: true", workflow)
        aggregate_job = workflow.split("\n  aggregate:\n", 1)[1]
        self.assertLess(
            aggregate_job.index("Reject incomplete upstream jobs before setup"),
            aggregate_job.index("Checkout exact source and board package"),
        )
        self.assertNotIn("Stage aggregate evidence only", workflow)
        self.assertNotIn("m33_regression_run.py", workflow)
        self.assertNotIn("m32_regression_soak_run.py", workflow)
        self.assertNotIn("--execute", workflow)
        uses = re.findall(r"(?m)^\s*uses:\s*([^\s]+)$", workflow)
        self.assertTrue(uses)
        self.assertTrue(all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", value)
                            for value in uses))

    def _fake_build_inputs(self, root: Path) -> tuple[dict, dict[str, Path]]:
        """! @brief fake subprocess용 source·tool path가 결합된 작은 plan을 만듭니다. """

        plan = small_plan()
        root.mkdir()
        sdk = root / "sdk"
        toolchain = root / "toolchain"
        sdk.mkdir()
        toolchain.mkdir()
        cli = root / "arduino-cli.exe"
        config = root / "arduino-cli.yaml"
        cli.write_bytes(b"fixture")
        config.write_text("fixture\n", encoding="utf-8")
        plan["source"] = {
            **SOURCE,
            "sdk_root": sdk.as_posix(),
            "toolchain_root": toolchain.as_posix(),
        }
        plan.pop("contract_sha256")
        plan["contract_sha256"] = artifacts.canonical_sha256(plan)
        return plan, {"cli": cli, "config": config}

    def _fake_actions(self, work_root: Path) -> list[dict]:
        """! @brief 성공/부분 실패 시험용 두 build action을 반환합니다. """

        actions = []
        for role in ("central", "peripheral"):
            cache_root = work_root / "caches" / role
            actions.append({
                "id": role,
                "kind": "fixture",
                "command": [sys.executable, "-c", "fixture", str(work_root / role)],
                "cwd": str(ROOT),
                "output": str(work_root / role),
                "cache_root": str(cache_root),
                "precreate_output": False,
                "environment": {
                    "XDG_CACHE_HOME": str(cache_root / "xdg"),
                    "CCACHE_DIR": str(cache_root / "ccache"),
                    "PIP_CACHE_DIR": str(cache_root / "pip"),
                    "PYTHONPYCACHEPREFIX": str(cache_root / "pycache"),
                    "TMP": str(cache_root / "tmp"),
                    "TEMP": str(cache_root / "tmp"),
                    "TMPDIR": str(cache_root / "tmp"),
                },
                "depends_on": [],
                "jobs": 1,
            })
        return actions

    def _run_fake_build(
        self,
        root: Path,
        executor: object,
        identity_calls: list[tuple[object, ...]] | None = None,
    ) -> tuple[Path, Path, Path]:
        """! @brief 주입한 subprocess 실행기로 작은 build transaction을 실행합니다. """

        plan, paths = self._fake_build_inputs(root / "protected")
        transaction = root / "transaction"
        transaction.mkdir()
        work = transaction / "work"
        index = transaction / "index.json"
        runtime = transaction / "runtime.json"

        def action_factory(*_args: object) -> list[dict]:
            return self._fake_actions(work)

        def resolver(_plan: dict, _actions: object) -> list[dict]:
            return [
                {"campaign_id": "fixture_campaign", "name": "hex-central", "path": str(work / "central")},
                {"campaign_id": "fixture_campaign", "name": "hex-peripheral", "path": str(work / "peripheral")},
            ]

        def identity_validator(*arguments: object) -> dict:
            if identity_calls is not None:
                identity_calls.append(arguments)
            return dict(plan["source"])

        artifacts.build_from_plan(
            plan,
            work,
            index,
            runtime,
            paths["cli"],
            paths["config"],
            "nucode:zephyr:nu54dk",
            60,
            executor=executor,
            identity_validator=identity_validator,
            action_factory=action_factory,
            entry_resolver=resolver,
            index_validator=lambda _plan, document: document["entries"],
            plan_validator=lambda _plan: None,
        )
        return work, index, runtime

    def test_fake_subprocess_creates_atomic_index_and_receipts(self) -> None:
        """! @brief shell 없는 명령·로그 hash·원자 index 생성을 검증합니다. """

        calls = []
        identity_calls = []

        def executor(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            calls.append((command, kwargs))
            Path(command[-1]).mkdir(parents=True)
            return subprocess.CompletedProcess(command, 0, stdout=b"stdout", stderr=b"stderr")

        with tempfile.TemporaryDirectory() as directory:
            work, index, runtime = self._run_fake_build(
                Path(directory), executor, identity_calls
            )
            document = artifacts.strict_json(index)
            self.assertEqual(len(document["actions"]), 2)
            self.assertTrue(runtime.is_file())
            self.assertFalse(list(index.parent.glob(f".{index.name}.tmp-*")))
            self.assertTrue(all(call[1]["shell"] is False for call in calls))
            self.assertTrue(all(call[1]["timeout"] == 60 for call in calls))
            self.assertFalse((work / "m33-w06-build-failure.json").exists())
            self.assertEqual(2, len(identity_calls))

    def test_parallel_build_is_isolated_and_receipts_keep_plan_order(self) -> None:
        """! @brief 독립 action은 동시에 실행돼도 cache와 receipt 순서를 공유하지 않습니다. """

        barrier = threading.Barrier(2)
        environments = {}

        def executor(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            role = Path(command[-1]).name
            environments[role] = dict(kwargs["env"])
            barrier.wait(timeout=5)
            Path(command[-1]).mkdir(parents=True)
            return subprocess.CompletedProcess(
                command, 0, stdout=role.encode(), stderr=b""
            )

        with tempfile.TemporaryDirectory() as directory:
            _work, index, _runtime = self._run_fake_build(
                Path(directory), executor
            )
            receipts = artifacts.strict_json(index)["actions"]
            self.assertEqual(
                [(row["ordinal"], row["id"]) for row in receipts],
                [(1, "central"), (2, "peripheral")],
            )
            self.assertNotEqual(
                environments["central"]["XDG_CACHE_HOME"],
                environments["peripheral"]["XDG_CACHE_HOME"],
            )

    def test_parallel_build_rejects_shared_cache_and_dependency_cycle(self) -> None:
        """! @brief cache 공유와 cycle은 어떤 subprocess도 시작하기 전에 거부합니다. """

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            actions = self._fake_actions(work)
            actions[1]["cache_root"] = actions[0]["cache_root"]
            for key in artifacts.ISOLATED_CACHE_ENVIRONMENTS:
                actions[1]["environment"][key] = actions[0]["environment"][key]
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "cache root"):
                artifacts.validate_build_action_graph(actions, work, 2)
            actions = self._fake_actions(work)
            actions[0]["depends_on"] = ["peripheral"]
            actions[1]["depends_on"] = ["central"]
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "cycle"):
                artifacts.validate_build_action_graph(actions, work, 2)

    def test_timeout_leaves_no_index_and_records_failure(self) -> None:
        """! @brief subprocess timeout은 부분 index 없이 FAIL receipt를 남깁니다. """

        def executor(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=b"partial")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "timeout=True"):
                self._run_fake_build(root, executor)
            self.assertFalse((root / "transaction/index.json").exists())
            self.assertFalse((root / "transaction/runtime.json").exists())
            failure = artifacts.strict_json(
                root / "transaction/work/m33-w06-build-failure.json"
            )
            self.assertTrue(failure["actions"][0]["timed_out"])

    def test_partial_subprocess_failure_leaves_no_index(self) -> None:
        """! @brief 앞 action 성공 뒤 실패해도 exact index를 만들지 않습니다. """

        identity_calls = []

        def executor(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
            Path(command[-1]).mkdir(parents=True)
            exit_code = 0 if Path(command[-1]).name == "central" else 7
            return subprocess.CompletedProcess(
                command, exit_code, stdout=b"", stderr=b"failed"
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "exit=7"):
                self._run_fake_build(root, executor, identity_calls)
            self.assertFalse((root / "transaction/index.json").exists())
            self.assertFalse((root / "transaction/runtime.json").exists())
            failure = artifacts.strict_json(
                root / "transaction/work/m33-w06-build-failure.json"
            )
            self.assertEqual([row["exit_code"] for row in failure["actions"]], [0, 7])
            self.assertEqual(2, len(identity_calls))

    def test_phase_images_bind_to_exact_scenarios(self) -> None:
        """! @brief 동일 app의 phase/role image를 다른 scenario로 혼동하지 않습니다. """

        rows = artifacts.plan_artifacts(self.plan)
        self.assertEqual(
            rows[("m32_standalone_radio", "hex-radio154-transmitter")]["recipe"]["scenario"],
            "nucode.m32.radio154_hil.transmitter",
        )
        self.assertEqual(
            rows[("m32_coexistence", "hex-ble-mesh-mesh-peer")]["recipe"]["scenario"],
            "nucode.m32.coexistence_hil.ble_mesh.mesh_peer",
        )
        self.assertEqual(
            rows[("m31_iso_combined", "hex-receiver")]["recipe"]["scenario"],
            "nucode.m31.iso_bis.receiver",
        )

    def test_partial_index_is_rejected(self) -> None:
        """! @brief 한 역할이라도 빠진 build index를 거부합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            central = write_native_image(root, "central", ":0400000001020304F2")
            peripheral = write_native_image(root, "peripheral", ":0400000005060708E2")
            plan = small_plan()
            index = build_index(plan, central, peripheral)
            index["entries"].pop()
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "부분"):
                artifacts.validate_index(plan, index, validate_source_digests=False)

    def test_same_image_for_two_roles_is_rejected(self) -> None:
        """! @brief 서로 다른 역할을 같은 HEX로 채우는 오류를 거부합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = write_native_image(root, "shared", ":0400000001020304F2")
            plan = small_plan()
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "같은 HEX"):
                artifacts.validate_index(
                    plan,
                    build_index(plan, image, image),
                    validate_source_digests=False,
                )

    def test_revision_drift_is_rejected(self) -> None:
        """! @brief build record가 다른 Core revision이면 거부합니다. """

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nucode_arduino_core_build.yml"
            path.write_text(native_record().replace("1" * 12, "9" * 12, 1), encoding="utf-8")
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "revision"):
                artifacts.validate_native_record(path, SOURCE)

    def test_wrong_phase_path_is_rejected(self) -> None:
        """! @brief 다른 Twister scenario의 HEX를 phase slot에 넣으면 거부합니다. """

        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "nucode.m32.esb_hil.prx" / "zephyr.hex"
            image.parent.mkdir()
            image.write_text(":0400000001020304F2\n:00000001FF\n", encoding="ascii")
            recipe = {
                "builder": "run_zephyr_build.py",
                "application": "tests/zephyr/m32_esb_hil",
                "scenario": "nucode.m32.esb_hil.ptx",
                "jobs": 2,
            }
            with self.assertRaisesRegex(artifacts.ArtifactFailure, "scenario"):
                artifacts.validate_recipe_binding(image, recipe)

    def test_config_drift_changes_validated_manifest(self) -> None:
        """! @brief resolved config가 바뀌면 재검증 byte manifest가 달라집니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            central = write_native_image(root, "central", ":0400000001020304F2")
            peripheral = write_native_image(root, "peripheral", ":0400000005060708E2")
            plan = small_plan()
            index = build_index(plan, central, peripheral)
            before = artifacts.validate_index(plan, index, validate_source_digests=False)
            (central.parent / ".config").write_text("CONFIG_TEST=n\n", encoding="utf-8")
            after = artifacts.validate_index(plan, index, validate_source_digests=False)
            self.assertNotEqual(before, after)

    def test_symlink_failure_leaves_no_partial_root(self) -> None:
        """! @brief file symlink 권한 오류가 나도 부분 artifact root를 남기지 않습니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            central = write_native_image(root, "central", ":0400000001020304F2")
            peripheral = write_native_image(root, "peripheral", ":0400000005060708E2")
            plan = small_plan()
            destination = root / "artifacts"
            with mock.patch.object(artifacts.os, "symlink", side_effect=OSError("denied")):
                with self.assertRaisesRegex(OSError, "denied"):
                    artifacts.stage_artifacts(
                        plan,
                        build_index(plan, central, peripheral),
                        destination,
                        validate_source_digests=False,
                    )
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_name(destination.name + f".staging-{artifacts.os.getpid()}").exists())

    def test_local_staged_row_restores_simple_build_index_entry(self) -> None:
        """! @brief local stage의 계산 hash를 relocation index field로 오인하지 않습니다. """

        row = {
            "campaign_id": "fixture_campaign",
            "name": "hex-central",
            "source": "C:/evidence/zephyr.hex",
            "sha256": "a" * 64,
            "kind": "target_image",
            "configs": [],
        }
        self.assertEqual(
            {
                "campaign_id": "fixture_campaign",
                "name": "hex-central",
                "path": "C:/evidence/zephyr.hex",
            },
            artifacts.staged_build_index_entry(row, relocated=False),
        )
        self.assertEqual(
            "a" * 64,
            artifacts.staged_build_index_entry(row, relocated=True)["sha256"],
        )

    def test_plan_json_round_trip_keeps_contract_hash(self) -> None:
        """! @brief plan JSON round-trip 뒤에도 hash 계약이 유지됩니다. """

        encoded = json.dumps(self.plan, ensure_ascii=False)
        decoded = json.loads(encoded)
        artifacts.validate_plan(decoded)

    def test_rehashed_recipe_drift_is_rejected(self) -> None:
        """! @brief hash를 다시 계산해도 다른 scenario recipe를 수락하지 않습니다. """

        drifted = json.loads(json.dumps(self.plan))
        row = next(campaign for campaign in drifted["campaigns"] if campaign["id"] == "m32_power")
        image = next(artifact for artifact in row["artifacts"] if artifact["name"] == "hex-central")
        image["recipe"]["scenario"] = "nucode.m32.ble_power_hil.peripheral"
        drifted.pop("contract_sha256")
        drifted["contract_sha256"] = artifacts.canonical_sha256(drifted)
        with self.assertRaisesRegex(artifacts.ArtifactFailure, "contract.*drift"):
            artifacts.validate_plan(drifted)


if __name__ == "__main__":
    unittest.main()
