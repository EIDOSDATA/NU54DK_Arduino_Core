#!/usr/bin/env python3
"""! @brief M13 구성 profile, feature allowlist와 공개 예제 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "nu54-builder" / "src" / "nu54_builder.py"
SPEC = importlib.util.spec_from_file_location("nu54_builder_m13", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Builder를 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M13ProfileContractTests(unittest.TestCase):
    """! @brief profile schema와 Arduino 공개 예제의 간결성을 검증합니다. """

    def test_standard_profile_and_allowlist(self) -> None:
        """! @brief 표준 profile과 세 bundled feature manifest를 검증합니다. """
        profile = MODULE.load_configuration_profile(ROOT, "standard")
        self.assertEqual(profile["features"], ["gpio", "serial", "wire", "spi", "adc", "pwm"])
        self.assertIsNone(MODULE.load_library_feature(ROOT, "ThirdParty"))
        self.assertEqual(
            {MODULE.load_library_feature(ROOT, name)["id"] for name in MODULE.FEATURE_ALLOWLIST},
            {"nucode.board", "nucode.wire", "nucode.spi"},
        )
        resolved = MODULE.resolve_library_features(ROOT, profile, ["Wire", "SPI", "ThirdParty"])
        self.assertEqual([item["id"] for item in resolved], ["nucode.spi", "nucode.wire"])

    def test_profile_rejects_wrong_fqbn_and_zephyr_board(self) -> None:
        """! @brief profile이 실제 Arduino 및 Zephyr target과 다르면 중단합니다. """

        with self.assertRaisesRegex(MODULE.AdapterError, "E_PROFILE_TARGET"):
            MODULE.load_configuration_profile(
                ROOT,
                "standard",
                fqbn="other:zephyr:nu54dk",
                zephyr_board=MODULE.DEFAULT_BOARD,
            )
        with self.assertRaisesRegex(MODULE.AdapterError, "E_PROFILE_TARGET"):
            MODULE.load_configuration_profile(
                ROOT,
                "standard",
                fqbn="nucode:zephyr:nu54dk:upload_probe=pyocd",
                zephyr_board="nrf54l15dk/nrf54l15/cpuflpr",
            )

    def test_canonical_examples_have_no_zephyr_sidecars(self) -> None:
        """! @brief 공개 예제 12개가 ino만으로 탐색 가능한지 확인합니다. """
        examples = sorted(ROOT.glob("libraries/*/examples/*/*.ino"))
        self.assertEqual(
            {sketch.parent.name for sketch in examples},
            {
                "AnalogReadA0",
                "Blink",
                "BoardInfo",
                "CounterAlarm",
                "InterruptButton",
                "PWMFade",
                "SPITransaction",
                "SerialEcho",
                "SettingsStorage",
                "SystemOffWake",
                "WatchdogBasic",
                "WirePmicId",
            },
        )
        for sketch in examples:
            self.assertFalse((sketch.parent / "prj.conf").exists())
            self.assertFalse((sketch.parent / "app.overlay").exists())

    def test_only_selected_bundled_library_is_resolved(self) -> None:
        """! @brief 실제 source record에 등장한 bundled library만 선택합니다. """
        records = [
            {"source": str(ROOT / "tests" / "sketch.cpp"), "include_dirs": [str(ROOT / "libraries" / "Wire" / "src")]},
            {"source": str(ROOT / "cores" / "arduino" / "main.cpp"), "include_dirs": []},
            {"source": str(ROOT.parent / "ThirdParty" / "source.cpp")},
        ]
        paths = {"platform_root": ROOT}
        self.assertEqual(MODULE.selected_bundled_libraries(paths, records), ["Wire"])
        profile = MODULE.load_configuration_profile(ROOT, "standard")
        self.assertEqual([item["id"] for item in MODULE.resolve_library_features(ROOT, profile, ["Wire", "Unknown"])], ["nucode.wire"])

    def test_schema_path_conflict_and_cache_key_contract(self) -> None:
        """! @brief 잘못된 manifest를 거부하고 feature 집합이 cache key를 바꾸는지 확인합니다. """
        with tempfile.TemporaryDirectory(prefix="n54-m13-") as temporary:
            fixture = Path(temporary)
            shutil.copytree(ROOT / "variants", fixture / "variants")
            shutil.copytree(ROOT / "libraries", fixture / "libraries")
            feature_path = fixture / "libraries" / "Wire" / "zephyr" / "feature.yml"
            document = json.loads(feature_path.read_text(encoding="utf-8"))
            document["command"] = "forbidden"
            feature_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(MODULE.AdapterError):
                MODULE.load_library_feature(fixture, "Wire")
            document.pop("command")
            document["conf"] = ["../escape.conf"]
            feature_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(MODULE.AdapterError):
                MODULE.load_library_feature(fixture, "Wire")
            document["conf"] = []
            document["conflicts"] = ["radio.locked"]
            feature_path.write_text(json.dumps(document), encoding="utf-8")
            profile_path = fixture / "variants" / "nu54dk" / "profiles" / "standard" / "profile.json"
            profile_document = json.loads(profile_path.read_text(encoding="utf-8"))
            profile_document["conflicts"] = ["radio.locked"]
            profile_path.write_text(json.dumps(profile_document), encoding="utf-8")
            profile = MODULE.load_configuration_profile(fixture, "standard")
            with self.assertRaisesRegex(
                MODULE.AdapterError,
                r"E_FEATURE_CONFLICT.*radio\.locked.*profile:standard.*nucode\.wire",
            ):
                MODULE.resolve_library_features(fixture, profile, ["Wire"])

            profile_document["conflicts"] = []
            profile_path.write_text(json.dumps(profile_document), encoding="utf-8")
            spi_path = fixture / "libraries" / "SPI" / "zephyr" / "feature.yml"
            spi_document = json.loads(spi_path.read_text(encoding="utf-8"))
            spi_document["conflicts"] = ["radio.locked"]
            spi_path.write_text(json.dumps(spi_document), encoding="utf-8")
            profile = MODULE.load_configuration_profile(fixture, "standard")
            with self.assertRaisesRegex(
                MODULE.AdapterError,
                r"E_FEATURE_CONFLICT.*radio\.locked.*nucode\.spi.*nucode\.wire",
            ):
                MODULE.resolve_library_features(fixture, profile, ["Wire", "SPI"])
        base = {"configuration": {"selected_features": []}}
        selected = {"configuration": {"selected_features": [{"id": "nucode.wire", "manifest": "sha256:x"}]}}
        self.assertNotEqual(MODULE.cache_key_for_manifest(base), MODULE.cache_key_for_manifest(selected))

    def test_duplicate_feature_key_uses_feature_schema_diagnostic(self) -> None:
        """! @brief feature manifest 중복 key를 profile 오류로 잘못 보고하지 않습니다. """
        with tempfile.TemporaryDirectory(prefix="n54-m13-duplicate-") as temporary:
            fixture = Path(temporary)
            shutil.copytree(ROOT / "libraries", fixture / "libraries")
            feature_path = fixture / "libraries" / "Wire" / "zephyr" / "feature.yml"
            feature_path.write_text(
                '{"schema_version":1,"schema_version":1,"id":"nucode.wire",'
                '"requires":[],"conf":[],"overlays":[],"conflicts":[],'
                '"compatible_profiles":["standard"]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MODULE.AdapterError, "E_FEATURE_SCHEMA"):
                MODULE.load_library_feature(fixture, "Wire")

    def test_feature_cache_collision_is_fail_closed(self) -> None:
        """! @brief 축약 cache directory의 다른 full key를 덮어쓰지 않습니다. """
        with tempfile.TemporaryDirectory(prefix="n54-m13-collision-") as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / "input-manifest.json").write_text(json.dumps({"different": True}), encoding="utf-8")
            session = {
                "platform_root": ROOT,
                "build_path": root / "build",
                "sketch_root": root / "sketch",
                "state_root": root / "build" / "nu54-zephyr",
                "context": root / "build" / "nu54-zephyr" / "context.json",
                "records": root / "build" / "nu54-zephyr" / "records",
            }
            context = {"cache_key": "0" * 64, "cache_root": str(root / "cache"), "board_root": str(ROOT / "board_package" / "NU54DK_Zephyr_DTS")}
            args = mock.Mock(profile="standard")
            with mock.patch.object(MODULE, "cache_workspace", return_value=workspace):
                with self.assertRaisesRegex(MODULE.AdapterError, "E_CACHE_KEY_COLLISION"):
                    MODULE.migrate_feature_workspace(session, args, {}, context, [], [], {"selected": True})

    def test_profile_string_types_and_windows_paths_are_rejected(self) -> None:
        """! @brief malformed scalar와 Windows 절대 경로를 schema 오류로 거부합니다. """
        with tempfile.TemporaryDirectory(prefix="n54-m13-profile-") as temporary:
            fixture = Path(temporary)
            shutil.copytree(ROOT / "variants", fixture / "variants")
            profile_path = fixture / "variants" / "nu54dk" / "profiles" / "standard" / "profile.json"
            original = json.loads(profile_path.read_text(encoding="utf-8"))
            for field in ("id", "display_name", "board", "zephyr_board", "ncs_version", "conf", "overlay"):
                malformed = dict(original)
                malformed[field] = 7
                profile_path.write_text(json.dumps(malformed), encoding="utf-8")
                with self.assertRaisesRegex(MODULE.AdapterError, "E_PROFILE_SCHEMA"):
                    MODULE.load_configuration_profile(fixture, "standard")
            for value in (r"C:\\escape.conf", r"\\server\share\escape.conf", "//server/share/escape.conf"):
                with self.assertRaisesRegex(MODULE.AdapterError, "E_PROFILE_PATH"):
                    MODULE.declared_path(fixture, value, "E_PROFILE_PATH")

    def test_selected_feature_fragments_merge_before_expert_override(self) -> None:
        """! @brief 선택 feature fragment와 sketch override의 병합 순서를 검증합니다. """
        with tempfile.TemporaryDirectory(prefix="n54-m13-merge-") as temporary:
            fixture = Path(temporary)
            for name in ("variants", "libraries"):
                shutil.copytree(ROOT / name, fixture / name)
            shutil.copytree(ROOT / "tools" / "nu54-builder" / "templates", fixture / "tools" / "nu54-builder" / "templates")
            feature_path = fixture / "libraries" / "Wire" / "zephyr" / "feature.yml"
            feature = json.loads(feature_path.read_text(encoding="utf-8"))
            feature["conf"] = ["wire.conf"]
            feature["overlays"] = ["wire.overlay"]
            feature_path.write_text(json.dumps(feature), encoding="utf-8")
            (feature_path.parent / "wire.conf").write_text("CONFIG_M13_FEATURE=y\n", encoding="utf-8")
            (feature_path.parent / "wire.overlay").write_text("/** feature overlay */\n", encoding="utf-8")
            sketch = fixture / "sketch"
            sketch.mkdir()
            (sketch / "prj.conf").write_text("CONFIG_M13_EXPERT=y\n", encoding="utf-8")
            (sketch / "app.overlay").write_text("/** expert overlay */\n", encoding="utf-8")
            paths = {"platform_root": fixture, "sketch_root": sketch, "app": fixture / "app"}
            MODULE.materialize_application(
                paths,
                mock.Mock(
                    profile="standard",
                    fqbn="nucode:zephyr:nu54dk",
                    board=MODULE.DEFAULT_BOARD,
                ),
                ["Wire"],
            )
            conf = (paths["app"] / "prj.conf").read_text(encoding="utf-8")
            overlay = (paths["app"] / "app.overlay").read_text(encoding="utf-8")
            self.assertLess(conf.index("CONFIG_M13_FEATURE=y"), conf.index("CONFIG_M13_EXPERT=y"))
            self.assertLess(overlay.index("feature overlay"), overlay.index("expert overlay"))

    def test_feature_configure_failure_marks_cache_failed(self) -> None:
        """! @brief 최종 configure 실패를 failed/configure-failed 상태로 보존합니다. """
        with tempfile.TemporaryDirectory(prefix="n54-m13-fail-") as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            sketch = root / "sketch"
            sketch.mkdir()
            session = {"platform_root": ROOT, "build_path": root / "build", "sketch_root": sketch, "state_root": root / "build" / "nu54-zephyr", "context": root / "build" / "nu54-zephyr" / "context.json", "records": root / "build" / "nu54-zephyr" / "records"}
            context = {"cache_key": "0" * 64, "cache_root": str(root / "cache"), "board_root": str(ROOT / "board_package" / "NU54DK_Zephyr_DTS")}
            tools = {"west": "west", "zephyr_base": ROOT, "ncs_root": ROOT, "environment": {}}
            with mock.patch.object(MODULE, "cache_workspace", return_value=workspace), mock.patch.object(MODULE, "run_checked", side_effect=MODULE.AdapterError("configure boom")):
                with self.assertRaises(MODULE.AdapterError):
                    MODULE.migrate_feature_workspace(
                        session,
                        mock.Mock(
                            profile="standard",
                            fqbn="nucode:zephyr:nu54dk",
                            board=MODULE.DEFAULT_BOARD,
                        ),
                        tools,
                        context,
                        [],
                        ["Wire"],
                        {"selected": "wire"},
                    )
            state = json.loads((workspace / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "failed")
            self.assertEqual(state["last_build_result"], "configure-failed")

    def test_arduino_cli_discovers_canonical_examples_when_installed(self) -> None:
        """! @brief 설치된 Arduino CLI가 공개 예제 12개를 노출하는지 확인합니다. """
        if os.environ.get("NUCODE_M13_CLI_DISCOVERY") != "1":
            self.skipTest("M13 package 설치 후 NUCODE_M13_CLI_DISCOVERY=1로 실행합니다.")
        cli = shutil.which("arduino-cli")
        if cli is None:
            self.skipTest("arduino-cli가 PATH에 없습니다.")
        result = subprocess.run(
            [cli, "lib", "examples", "--fqbn", "nucode:zephyr:nu54dk", "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(result.stdout)
        encoded = json.dumps(document)
        for name in (
            "AnalogReadA0",
            "Blink",
            "BoardInfo",
            "CounterAlarm",
            "InterruptButton",
            "PWMFade",
            "SPITransaction",
            "SerialEcho",
            "SettingsStorage",
            "SystemOffWake",
            "WatchdogBasic",
            "WirePmicId",
        ):
            self.assertIn(name, encoded)


if __name__ == "__main__":
    unittest.main()
