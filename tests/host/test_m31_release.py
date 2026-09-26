"""! @brief M31 W08 비공개 Windows RC 준비의 fail-closed 계약을 검사합니다. """

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "release" / "m31_release.py"
SPEC = importlib.util.spec_from_file_location("m31_release_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class M31ReleaseTests(unittest.TestCase):
    """! @brief 공개 차단·분모·candidate 격리 계약을 확인합니다. """

    def test_contract_retains_owner_approval_and_public_smoke(self) -> None:
        """! @brief W08 준비가 공개 승인과 공개 URL smoke를 완료 처리하지 않습니다. """
        _m31, release = MODULE.validate_contract(ROOT)
        by_id = {gate["id"]: gate for gate in release["gates"]}
        self.assertEqual("HOLD", by_id["rc_review_and_owner_approval"]["status"])
        self.assertEqual("NOT_RUN", by_id["public_assets_and_download_smoke"]["status"])
        self.assertFalse(release["publication_allowed"])

    def test_process_local_candidate_does_not_change_public_allowlist(self) -> None:
        """! @brief 0.5.0-rc.1은 W08 process 안에서만 활성화됩니다. """
        package = MODULE.load_package_module()
        before = tuple(package.RELEASE_CANDIDATE_VERSIONS)
        MODULE.configure_candidate(package)
        self.assertNotIn(MODULE.VERSION, before)
        self.assertIn(MODULE.VERSION, package.RELEASE_CANDIDATE_VERSIONS)
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("publish-release", source)
        self.assertNotIn("publish-index", source)

    def test_package_pass_cannot_consume_remaining_gates(self) -> None:
        """! @brief package 이중 재현만으로 설치·수명주기·승인을 PASS로 만들지 않습니다. """
        _m31, release = MODULE.validate_contract(ROOT)
        remaining = MODULE.blockers(release, package_passed=True)
        self.assertNotIn("windows_package_reproducibility", remaining)
        self.assertIn("windows_clean_install_examples_upload", remaining)
        self.assertIn("windows_lifecycle", remaining)
        self.assertIn("rc_review_and_owner_approval", remaining)
        self.assertIn("public_assets_and_download_smoke", remaining)

    def test_pass_gate_requires_existing_evidence(self) -> None:
        """! @brief 증거 없는 PASS gate를 거부합니다. """
        source = json.loads((ROOT / MODULE.RELEASE_READINESS).read_text(encoding="utf-8"))
        changed = copy.deepcopy(source)
        changed["gates"][0]["status"] = "PASS"
        changed["gates"][0]["evidence"] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / MODULE.M31_READINESS.parent).mkdir(parents=True)
            (root / MODULE.RELEASE_READINESS.parent).mkdir(parents=True, exist_ok=True)
            (root / MODULE.M31_READINESS).write_bytes((ROOT / MODULE.M31_READINESS).read_bytes())
            (root / MODULE.RELEASE_READINESS).write_text(
                json.dumps(changed, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MODULE.M31ReleaseFailure, "증거가 없습니다"):
                MODULE.validate_contract(root)


if __name__ == "__main__":
    unittest.main()
