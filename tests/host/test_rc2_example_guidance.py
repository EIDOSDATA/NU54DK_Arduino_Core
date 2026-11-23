"""! @brief RC2 공개 예제 metadata와 생성 안내 계약을 검증합니다. """

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools" / "examples" / "sync_example_guidance.py"


def load_tool():
    """! @brief 예제 설정 동기화 도구를 독립 모듈로 로드합니다. """

    specification = importlib.util.spec_from_file_location(
        "nu54_test_rc2_example_guidance", TOOL_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("예제 설정 동기화 도구를 로드하지 못했습니다.")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


GUIDANCE = load_tool()


class Rc2ExampleGuidanceTest(unittest.TestCase):
    """! @brief 현행 예제 설정 안내의 단일 원본과 drift 거부를 검사합니다. """

    def test_all_public_examples_have_valid_metadata_and_generated_guidance(self) -> None:
        """! @brief 공개 예제 204개가 metadata와 byte 일치하는 안내를 갖습니다. """

        examples = GUIDANCE.public_examples(ROOT)
        metadata = GUIDANCE.load_metadata(ROOT / "libraries" / "example-metadata.json")
        self.assertEqual(len(examples), 204)
        self.assertEqual(metadata["example_count"], 204)
        self.assertEqual(GUIDANCE.validate_metadata(metadata, examples, ROOT), [])
        self.assertEqual(GUIDANCE.synchronize(write=False, root=ROOT), [])

    def test_missing_identity_and_sidecar_drift_are_rejected(self) -> None:
        """! @brief identity 누락과 실제 sidecar 불일치를 각각 거부합니다. """

        examples = GUIDANCE.public_examples(ROOT)
        metadata = GUIDANCE.load_metadata(ROOT / "libraries" / "example-metadata.json")
        missing = copy.deepcopy(metadata)
        missing["examples"].pop("NUCODE_NU54DK/Blink")
        issues = GUIDANCE.validate_metadata(missing, examples, ROOT)
        self.assertTrue(any("metadata 누락: NUCODE_NU54DK/Blink" in issue for issue in issues))

        sidecar = copy.deepcopy(metadata)
        sidecar["examples"]["NUCODE_BLE_ChannelSounding/RasInitiator"]["sidecars"] = []
        issues = GUIDANCE.validate_metadata(sidecar, examples, ROOT)
        self.assertTrue(any("sidecar 불일치" in issue for issue in issues))

    def test_metadata_change_changes_rendered_digest(self) -> None:
        """! @brief 사용자 설정 변경이 생성 블록 hash와 본문을 함께 바꿉니다. """

        metadata = GUIDANCE.load_metadata(ROOT / "libraries" / "example-metadata.json")
        identity = "NUCODE_BLE_ChannelSounding/RasInitiator"
        original = metadata["examples"][identity]
        changed = json.loads(json.dumps(original, ensure_ascii=False))
        changed["board_count"] = 1
        changed["roles"] = ["잘못된 단일 역할"]
        self.assertNotEqual(
            GUIDANCE.render_guidance(identity, original),
            GUIDANCE.render_guidance(identity, changed),
        )

    def test_all_examples_have_seven_fields_and_traceability(self) -> None:
        """! @brief 204개 모두가 W05 사용자 안내·원본·수명주기 판정을 가집니다. """

        metadata = GUIDANCE.load_metadata(ROOT / "libraries" / "example-metadata.json")
        records = metadata["examples"]
        self.assertEqual(len(records), 204)
        for identity, record in records.items():
            for field in GUIDANCE.GUIDANCE_FIELDS:
                self.assertIn(field, record, f"{identity}: {field}")
            for field in GUIDANCE.TRACEABILITY_FIELDS:
                self.assertIn(field, record, f"{identity}: {field}")
            self.assertEqual(
                record["runtime_classification"],
                "procedure_documented_not_physical_pass",
            )
            self.assertIsNone(record["source_traceability"]["upstream_path"])

    def test_three_tier_guide_has_exact_denominators(self) -> None:
        """! @brief 사용자 안내가 12개 입구·29개 Recipe·204개 Reference를 보존합니다. """

        metadata = GUIDANCE.load_metadata(ROOT / "libraries" / "example-metadata.json")
        guide = GUIDANCE.render_example_guide(metadata, ROOT)
        self.assertEqual(guide.count("\n### "), 12 + 29)
        self.assertIn("## Start Here — 12개 사용 시나리오", guide)
        self.assertIn("## Functional Recipe — 29개 기능군", guide)
        self.assertIn("## Reference — 전체 204개", guide)
        self.assertEqual(
            (ROOT / "libraries" / "EXAMPLES.md").read_text(encoding="utf-8"),
            guide,
        )


if __name__ == "__main__":
    unittest.main()
