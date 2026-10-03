#!/usr/bin/env python3
"""! @brief M32-W11 열두 family closure 판정을 검증합니다. """

import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from m32_regression_closure import (  # noqa: E402
    FAMILY_TEST_IDS,
    RegressionClosureFailure,
    validate_manifest,
)


REVISION = "1" * 40


def _write_campaign(root: Path) -> Path:
    """! @brief 열두 family의 synthetic exact evidence와 manifest를 씁니다. """
    families = {}
    for index, (family, test_ids) in enumerate(FAMILY_TEST_IDS.items()):
        path = root / f"{index:02d}-{family}.json"
        path.write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "source_clean": True,
                    "identity": {"core": REVISION},
                    "test_ids": sorted(test_ids),
                }
            ),
            encoding="utf-8",
        )
        families[family] = [path.name]
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_revision": REVISION,
                "source_clean": True,
                "negative_classes": [
                    "cross_link",
                    "security_regression",
                    "cleanup",
                ],
                "families": families,
            }
        ),
        encoding="utf-8",
    )
    return manifest


class M32RegressionClosureTests(unittest.TestCase):
    """! @brief 누락·stale·비-clean 증거의 승격을 거부합니다. """

    def test_exact_twelve_family_manifest_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = _write_campaign(Path(temporary))
            result = validate_manifest(manifest, REVISION)
            self.assertEqual(12, len(result))
            self.assertTrue(all(item["status"] == "PASS" for item in result.values()))

    def test_missing_mdfu_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = _write_campaign(root)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            evidence = root / data["families"]["mesh_update"][0]
            document = json.loads(evidence.read_text(encoding="utf-8"))
            document["test_ids"].remove("M32-MDFU-01:primary")
            evidence.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(RegressionClosureFailure):
                validate_manifest(manifest, REVISION)

    def test_stale_dirty_and_duplicate_evidence_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = _write_campaign(root)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            capability = root / data["families"]["capability"][0]
            document = json.loads(capability.read_text(encoding="utf-8"))
            document["source_clean"] = False
            capability.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(RegressionClosureFailure):
                validate_manifest(manifest, REVISION)

            manifest = _write_campaign(root)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["families"]["privacy"] = data["families"]["advertising"]
            manifest.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(RegressionClosureFailure):
                validate_manifest(manifest, REVISION)

    def test_contract_requires_all_current_hil_groups(self) -> None:
        self.assertEqual(12, len(FAMILY_TEST_IDS))
        self.assertIn("M32-MDFU-01:primary", FAMILY_TEST_IDS["mesh_update"])
        self.assertEqual(
            3,
            len(FAMILY_TEST_IDS["coexistence"]),
        )


if __name__ == "__main__":
    unittest.main()
