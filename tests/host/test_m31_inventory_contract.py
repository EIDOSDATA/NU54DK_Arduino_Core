"""! @brief M31 sample 원장의 누락·target 오판·증거 승격을 거부합니다. """

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/bluetooth/m31_inventory.py"
SPEC = importlib.util.spec_from_file_location("m31_inventory_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class M31InventoryTests(unittest.TestCase):
    """! @brief 고정 revision·metadata merge·지원 상태 경계를 검사합니다. """

    def test_exact_l15_qualifier_does_not_accept_l05_or_l10(self) -> None:
        """! @brief 이름에 L15DK가 들어간 작은 SoC를 L15 근거로 세지 않습니다. """
        metadata = MODULE.target_metadata({
            "platform_allow": ["nrf54l15dk/nrf54l05/cpuapp", "nrf54l15dk/nrf54l10/cpuapp"],
            "integration_platforms": ["nrf54l15dk/nrf54l05/cpuapp"],
            "build_only": True,
        })
        self.assertFalse(metadata["platform_allow_exact"])
        self.assertFalse(metadata["integration_platform_exact"])
        self.assertIsNone(metadata["platform_exclude_exact"])

    def test_common_override_and_missing_metadata_remain_separate(self) -> None:
        """! @brief common과 test override 원본·해석 값을 각각 보존합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            sdk = Path(temporary)
            sample = sdk / "nrf/samples/bluetooth/iso_central"
            sample.mkdir(parents=True)
            (sample / "sample.yaml").write_text(
                "common:\n  build_only: true\n  platform_allow:\n"
                "    - nrf54l15dk/nrf54l05/cpuapp\n"
                "tests:\n  sample.bluetooth.iso.central:\n"
                "    build_only: false\n"
                "    platform_allow:\n"
                "      - nrf54l15dk/nrf54l15/cpuapp\n",
                encoding="utf-8",
            )
            (sdk / "zephyr/samples/bluetooth").mkdir(parents=True)
            with mock.patch.object(MODULE, "revision", side_effect=lambda path: MODULE.MODULES[path.name]):
                doc = MODULE.collect(sdk, ROOT)
            self.assertEqual(doc["counts"]["samples"], 1)
            self.assertEqual(doc["counts"]["variants"], 1)
            variant = doc["variants"][0]
            self.assertTrue(variant["metadata_common"]["build_only"])
            self.assertFalse(variant["metadata_override"]["build_only"])
            self.assertFalse(variant["metadata_effective"]["build_only"])
            self.assertTrue(variant["target_metadata"]["platform_allow_exact"])
            self.assertIsNone(variant["metadata_effective"]["sysbuild"])
            self.assertEqual(variant["results"]["runtime"]["status"], "NOT_RUN")

    def test_duplicate_and_orphan_variants_are_rejected(self) -> None:
        """! @brief 중복 identity와 부모 sample 누락을 gate 오류로 만듭니다. """
        doc = self._minimal_doc()
        duplicate = copy.deepcopy(doc)
        duplicate["variants"].append(copy.deepcopy(duplicate["variants"][0]))
        duplicate["counts"]["variants"] += 1
        with self.assertRaisesRegex(ValueError, "duplicate/orphan"):
            MODULE.validate(duplicate)
        orphan = copy.deepcopy(doc)
        orphan["variants"][0]["parent_sample_id"] = "nrf:missing"
        with self.assertRaisesRegex(ValueError, "duplicate/orphan"):
            MODULE.validate(orphan)

    def test_runtime_pass_requires_target_build_and_exact_evidence(self) -> None:
        """! @brief source 또는 target build 하나를 실기 PASS로 승격하지 않습니다. """
        doc = self._minimal_doc()
        result = doc["variants"][0]["results"]["runtime"]
        result.update(status="PASS", source_revision="a" * 40, evidence="proof.json")
        with self.assertRaisesRegex(ValueError, "runtime PASS without target"):
            MODULE.validate(doc)
        doc["variants"][0]["results"]["nu54dk_build"].update(
            status="PASS", source_revision="a" * 40, evidence="README.md"
        )
        result["evidence"] = None
        with self.assertRaisesRegex(ValueError, "PASS without exact"):
            MODULE.validate(doc)

    def test_follow_up_policy_and_reasonless_exclusion_are_rejected(self) -> None:
        """! @brief 사용자 후속 실물을 blocker로 만들거나 제외 이유를 지우지 않습니다. """
        doc = self._minimal_doc()
        follow_up = doc["variants"][0]["verification_cases"][0]
        follow_up.update(verification_owner="user", verification_stage="user_follow_up",
                         development_blocker=False, release_blocker=True)
        with self.assertRaisesRegex(ValueError, "follow-up scope"):
            MODULE.validate(doc)
        follow_up.update(verification_owner="developer", verification_stage="development",
                         development_blocker=True, release_blocker=True)
        doc["variants"][0]["route"] = "excluded"
        doc["variants"][0]["exclusion_reason"] = None
        with self.assertRaisesRegex(ValueError, "reasonless exclusion"):
            MODULE.validate(doc)

    def _minimal_doc(self) -> dict:
        """! @brief 검증기 단위 시험에 필요한 한 sample·한 variant를 구성합니다. """
        source = json.loads((ROOT / "variants/nu54dk/ncs-v3.4.0-bluetooth-sample-parity.json").read_text(
            encoding="utf-8"
        ))
        variant = copy.deepcopy(next(item for item in source["variants"] if item["owner_work_id"] == "M31-W02"))
        sample = copy.deepcopy(next(item for item in source["samples"] if item["id"] == variant["parent_sample_id"]))
        variant["target_applicability"] = "applicable"
        source["samples"] = [sample]
        source["variants"] = [variant]
        source["source_only_features"] = []
        source["counts"] = {"samples": 1, "variants": 1, "source_only_features": 0}
        return source


if __name__ == "__main__":
    unittest.main()
