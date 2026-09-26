"""! @brief M31 Windows lifecycle 예제 분모와 profile 선택을 검사합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "release" / "m31_windows_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("m31_windows_lifecycle_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class M31WindowsLifecycleTests(unittest.TestCase):
    """! @brief source tree를 package layout으로 사용해 분모 규칙을 확인합니다. """

    def test_source_library_examples_have_exact_release_denominator(self) -> None:
        """! @brief 공개 library 예제 113개를 누락 없이 열거합니다. """
        examples = MODULE.installed_examples(ROOT)
        self.assertEqual(MODULE.EXPECTED_EXAMPLES, len(examples))
        self.assertEqual(MODULE.EXPECTED_EXAMPLES, len({item[0] for item in examples}))

    def test_profile_specific_examples_are_separate(self) -> None:
        """! @brief DFU·외장 audio·Fabric과 일반 BLE profile을 합치지 않습니다. """
        profiles = {identity: profile for identity, _path, profile in MODULE.installed_examples(ROOT)}
        self.assertEqual("secure_ble_dfu", profiles["NUCODE_BLE_DFU/SecureDfuPeripheral"])
        self.assertEqual(
            "ble_audio_io",
            profiles["NUCODE_BLE_Audio/ExternalPdmMicrophoneSource"],
        )
        self.assertEqual(
            "ble_audio_io",
            profiles["NUCODE_BLE_Audio/ExternalI2sSpeakerSink"],
        )
        self.assertEqual(
            "fabric",
            profiles["NUCODE_Peripheral_Fabric/FabricCapabilities"],
        )
        self.assertEqual("ble", profiles["NUCODE_BLE_DirectionFinding/CteBeacon"])
        self.assertEqual("standard", profiles["NUCODE_NU54DK/Blink"])

    def test_example_build_relative_path_stays_under_build_root(self) -> None:
        """! @brief lifecycle artifact 경로가 workspace/build 아래에서 해석됩니다. """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "build"
            expected = (root / "examples" / "DirectionFinding__CteBeacon").resolve()
            actual = MODULE.resolve_example_build(
                root,
                "examples/DirectionFinding__CteBeacon",
            )
            self.assertEqual(expected, actual)
            with self.assertRaises(MODULE.M31LifecycleFailure):
                MODULE.resolve_example_build(root, "../outside")

    def test_lifecycle_runner_has_no_publication_command(self) -> None:
        """! @brief 설치 검증기가 tag·Release·catalog를 게시하지 않습니다. """
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("publish-release", source)
        self.assertNotIn("publish-index", source)
        self.assertIn("unknown_version_rejected", source)

    def test_prerequisite_snapshot_is_taken_after_post_install(self) -> None:
        """! @brief 갱신 가능한 post_install 뒤 byte를 uninstall 보존 기준으로 사용합니다. """
        source = MODULE_PATH.read_text(encoding="utf-8")
        snapshot = source.index("prerequisite_before = sha256_file(ready_path)")
        upgrade = source.index('"upgrade_candidate"')
        uninstall = source.index('"uninstall_candidate"')
        self.assertLess(upgrade, snapshot)
        self.assertLess(snapshot, uninstall)

    def test_parallel_workers_use_independent_cache_roots(self) -> None:
        """! @brief 병렬 worker가 같은 build cache를 공유하지 않습니다. """
        examples = [
            (f"Library/Example{index}", ROOT, "standard")
            for index in range(4)
        ]
        observed: list[tuple[str, str]] = []

        def compile_stub(
            _cli: Path, _config: Path, environment: dict[str, str],
            _build_root: Path, _log_root: Path, identity: str,
            _sketch: Path, _profile: str,
        ) -> dict[str, str]:
            observed.append((identity, environment["NUCODE_BUILD_CACHE_ROOT"]))
            return {"identity": identity, "status": "PASS"}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = {"NUCODE_BUILD_CACHE_ROOT": str(root / "shared")}
            with mock.patch.object(MODULE, "compile_example", side_effect=compile_stub):
                results, execution = MODULE.compile_examples(
                    root / "arduino-cli.exe",
                    root / "arduino-cli.yaml",
                    environment,
                    root / "build",
                    root / "logs",
                    examples,
                    2,
                    root / "cache",
                )
        self.assertEqual(4, len(results))
        self.assertEqual("parallel_isolated_worker_caches", execution["mode"])
        self.assertEqual(2, execution["workers"])
        self.assertEqual(2, execution["cache_roots"])
        roots = {cache for _identity, cache in observed}
        self.assertEqual(2, len(roots))
        self.assertNotIn(environment["NUCODE_BUILD_CACHE_ROOT"], roots)


if __name__ == "__main__":
    unittest.main()
