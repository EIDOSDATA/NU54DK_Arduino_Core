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
    """! @brief 113개 예제 설정 안내의 단일 원본과 drift 거부를 검사합니다. """

    def test_all_public_examples_have_valid_metadata_and_generated_guidance(self) -> None:
        """! @brief 공개 예제 113개가 metadata와 byte 일치하는 안내를 갖습니다. """

        examples = GUIDANCE.public_examples(ROOT)
        metadata = GUIDANCE.load_metadata(ROOT / "libraries" / "example-metadata.json")
        self.assertEqual(len(examples), 113)
        self.assertEqual(metadata["example_count"], 113)
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


if __name__ == "__main__":
    unittest.main()
