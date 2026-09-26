#!/usr/bin/env python3
"""! @brief RC2 변경 영향 classifier의 fail-closed 경계를 검증합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "rc2_change_classifier", ROOT / "tools" / "ci" / "rc2_change_classifier.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("RC2 classifier를 불러올 수 없습니다")
CLASSIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLASSIFIER)


class Rc2ChangeClassifierTests(unittest.TestCase):
    """! @brief 문서와 제품 변경의 build 범위를 검사합니다. """

    def test_document_only_change_skips_build_without_skipping_contract(self) -> None:
        """! @brief 문서 변경도 contract는 수행하되 firmware build는 생략합니다. """

        result = CLASSIFIER.classify(("README.md", "00_Docs/TODO_v0.5.0-RC2.md"))
        self.assertTrue(result["docs_only"])
        self.assertTrue(result["run_contract"])
        self.assertFalse(result["run_six_profiles"])
        self.assertFalse(result["run_all_examples"])

    def test_builder_board_and_profile_changes_are_full_and_release_sensitive(self) -> None:
        """! @brief 공통 build 입력 변경은 113개 Full RC를 요구합니다. """

        for path in (
            "tools/nu54-builder/src/nu54_builder.py",
            "board_package/NU54DK_Zephyr_DTS/boards/nucode/nu54dk/board.yml",
            "variants/nu54dk/profiles/ble/prj.conf",
            "platform.txt",
        ):
            with self.subTest(path=path):
                result = CLASSIFIER.classify((path,))
                self.assertTrue(result["run_six_profiles"])
                self.assertTrue(result["run_all_examples"])
                self.assertTrue(result["release_sensitive"])

    def test_example_change_tracks_identity_and_profile(self) -> None:
        """! @brief 예제 변경은 identity와 기본 profile을 좁혀 반환합니다. """

        result = CLASSIFIER.classify((
            "libraries/NUCODE_BLE_ChannelSounding/examples/RasInitiator/RasInitiator.ino",
        ))
        self.assertEqual(result["affected_examples"], [
            "NUCODE_BLE_ChannelSounding/RasInitiator"
        ])
        self.assertEqual(result["profiles"], ["ble"])
        self.assertFalse(result["run_all_examples"])

    def test_unknown_path_fails_closed_to_full_examples(self) -> None:
        """! @brief 새 최상위 경로는 전수 build로 보수 분류합니다. """

        result = CLASSIFIER.classify(("new-product-input.bin",))
        self.assertEqual(result["categories"], ["unknown"])
        self.assertTrue(result["run_all_examples"])
        self.assertEqual(result["profiles"], list(CLASSIFIER.ALL_PROFILES))


if __name__ == "__main__":
    unittest.main()
