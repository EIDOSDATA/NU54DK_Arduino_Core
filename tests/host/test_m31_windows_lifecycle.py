"""! @brief M31 Windows lifecycle 예제 분모와 profile 선택을 검사합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


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

    def test_secure_dfu_and_ble_profiles_are_separate(self) -> None:
        """! @brief DFU sysbuild와 일반 BLE 예제의 profile을 합치지 않습니다. """
        profiles = {identity: profile for identity, _path, profile in MODULE.installed_examples(ROOT)}
        self.assertEqual("secure_ble_dfu", profiles["NUCODE_BLE_DFU/SecureDfuPeripheral"])
        self.assertEqual("ble", profiles["NUCODE_BLE_DirectionFinding/CteBeacon"])
        self.assertEqual("standard", profiles["NUCODE_NU54DK/Blink"])

    def test_lifecycle_runner_has_no_publication_command(self) -> None:
        """! @brief 설치 검증기가 tag·Release·catalog를 게시하지 않습니다. """
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("publish-release", source)
        self.assertNotIn("publish-index", source)
        self.assertIn("unknown_version_rejected", source)


if __name__ == "__main__":
    unittest.main()
