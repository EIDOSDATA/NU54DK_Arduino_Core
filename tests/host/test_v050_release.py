#!/usr/bin/env python3
"""! @brief v0.5.0 정식 릴리스의 fail-closed 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "release" / "v050_release.py"
SPEC = importlib.util.spec_from_file_location("nu54_v050_release_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class V050ReleaseTests(unittest.TestCase):
    """! @brief 준비·승인·공개·단일 catalog 경계를 검사합니다. """

    def test_parser_separates_publication_commands(self) -> None:
        """! @brief 게시 단계마다 승인 문서가 필요한지 확인합니다. """
        parser = MODULE.build_parser()
        action = next(item for item in parser._actions if getattr(item, "choices", None))
        self.assertEqual(
            {
                "contract",
                "prepare",
                "validate-plan",
                "publication-dry-run",
                "publish-release",
                "publish-index",
            },
            set(action.choices),
        )
        for command in ("publication-dry-run", "publish-release", "publish-index"):
            with self.subTest(command=command):
                with self.assertRaises(SystemExit):
                    parser.parse_args((command, "--plan", "plan.json"))

    def test_stable_configuration_is_process_local(self) -> None:
        """! @brief 공개 전 v0.5.0이 영구 허용목록을 바꾸지 않는지 확인합니다. """
        package = MODULE.load_module("nu54_v050_test_package", MODULE.PACKAGE_MODULE)
        before = tuple(package.STABLE_VERSIONS)
        MODULE.configure_stable_package(package, "a" * 40)
        self.assertNotIn(MODULE.VERSION, before)
        self.assertIn(MODULE.VERSION, package.STABLE_VERSIONS)
        fresh = MODULE.load_module("nu54_v050_test_package_fresh", MODULE.PACKAGE_MODULE)
        self.assertEqual(before, tuple(fresh.STABLE_VERSIONS))

    def test_readiness_requires_all_pre_stable_gates(self) -> None:
        """! @brief 기술 gate 하나가 HOLD이면 정식 준비를 거부합니다. """
        m31 = json.loads((ROOT / MODULE.M31_READINESS_PATH.relative_to(ROOT)).read_text(encoding="utf-8"))
        release = json.loads((ROOT / MODULE.RELEASE_READINESS_PATH.relative_to(ROOT)).read_text(encoding="utf-8"))
        release["gates"][0]["status"] = "HOLD"
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            (work / MODULE.M31_READINESS_PATH.relative_to(ROOT).parent).mkdir(parents=True)
            (work / MODULE.M31_READINESS_PATH.relative_to(ROOT)).write_text(
                json.dumps(m31, ensure_ascii=False), encoding="utf-8"
            )
            (work / MODULE.RELEASE_READINESS_PATH.relative_to(ROOT)).write_text(
                json.dumps(release, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(MODULE.StableReleaseFailure, "m31_functionality"):
                MODULE.validate_technical_readiness(work)

    def test_approval_binds_exact_plan(self) -> None:
        """! @brief 승인 hash와 target commit이 plan에 정확히 결합되는지 확인합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            plan_path.write_text('{"plan":"exact"}\n', encoding="utf-8")
            plan = {"target_commit": "b" * 40}
            approval = {
                "schema_version": 1,
                "milestone": "v0.5.0",
                "decision": "approved",
                "version": MODULE.VERSION,
                "target_commit": plan["target_commit"],
                "stable_plan_sha256": MODULE.sha256_file(plan_path),
                "approver_role": "project-owner",
                "approval_source": "explicit-project-owner-approval",
                "approved_at_utc": "2026-09-27T00:00:00+00:00",
            }
            approval_path = root / "approval.json"
            approval_path.write_text(json.dumps(approval), encoding="utf-8")
            self.assertEqual(approval, MODULE.validate_approval(plan_path, approval_path, plan))
            approval["stable_plan_sha256"] = "0" * 64
            approval_path.write_text(json.dumps(approval), encoding="utf-8")
            with self.assertRaises(MODULE.StableReleaseFailure):
                MODULE.validate_approval(plan_path, approval_path, plan)

    def test_release_upload_excludes_root_index(self) -> None:
        """! @brief root index가 Release asset과 분리되는지 확인합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifacts = {}
            for role in MODULE.ASSET_ROLES:
                path = root / f"{role}.dat"
                path.write_bytes(role.encode("ascii"))
                artifacts[role] = {
                    "path": path.name,
                    "size": path.stat().st_size,
                    "sha256": MODULE.sha256_file(path),
                }
            plan = {"target_commit": "c" * 40, "artifacts": artifacts}
            calls = []

            def runner(arguments, _cwd):
                calls.append(tuple(arguments))
                return MODULE.CommandResult(0, b"", b"")

            with mock.patch.object(MODULE, "publication_dry_run", return_value=plan):
                MODULE.publish_release(root / "plan.json", root / "approval.json", runner=runner)
            uploaded = {Path(item).resolve() for item in calls[0][calls[0].index("--latest") + 1 :]}
            self.assertNotIn((root / artifacts["index"]["path"]).resolve(), uploaded)


if __name__ == "__main__":
    unittest.main(verbosity=2)
