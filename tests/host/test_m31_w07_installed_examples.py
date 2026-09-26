"""! @brief M31 W07 설치 예제 전수 빌드 도구의 fail-closed 계약을 검사합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "ci" / "m31_w07_installed_examples.py"
SPEC = importlib.util.spec_from_file_location("m31_w07_installed_examples", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M31W07InstalledExamplesTests(unittest.TestCase):
    """! @brief 채택 예제 분모와 설치 tree hash 계산을 고정합니다. """

    def test_readiness_resolves_49_unique_adopted_sketches(self) -> None:
        """! @brief 43개 역할이 참조하는 중복 제거 sketch 49개를 요구합니다. """
        readiness = json.loads(
            (ROOT / "variants/nu54dk/m31-ble-readiness.json").read_text(
                encoding="utf-8"
            )
        )
        sketches = MODULE.expected_sketches(readiness)
        self.assertEqual(49, len(sketches))
        self.assertEqual(49, len(set(sketches)))
        self.assertTrue(
            all(path.startswith("libraries/NUCODE_BLE_") for path in sketches)
        )

    def test_related_sketch_is_included_in_denominator(self) -> None:
        """! @brief 같은 역할의 추가 공개 예제를 누락할 수 없습니다. """
        readiness = {
            "example_roles": [
                {
                    "actual_sketch": "libraries/A/examples/Main/Main.ino",
                    "related_sketches": [
                        "libraries/A/examples/Related/Related.ino"
                    ],
                }
            ]
        }
        self.assertEqual(
            [
                "libraries/A/examples/Main/Main.ino",
                "libraries/A/examples/Related/Related.ino",
            ],
            MODULE.expected_sketches(readiness),
        )

    def test_tree_fingerprint_changes_with_content(self) -> None:
        """! @brief 설치본 byte가 달라지면 tree 지문도 달라져야 합니다. """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "example.txt"
            path.write_text("first\n", encoding="utf-8")
            first = MODULE.tree_fingerprint(root)
            path.write_text("second\n", encoding="utf-8")
            second = MODULE.tree_fingerprint(root)
        self.assertEqual(first[0], second[0])
        self.assertNotEqual(first[1], second[1])


if __name__ == "__main__":
    unittest.main()
