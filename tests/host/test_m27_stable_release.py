#!/usr/bin/env python3
"""! @brief T18 stable 준비와 승인 전 공개 차단 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "tools" / "release" / "m27_stable_release.py"
SPEC = importlib.util.spec_from_file_location("nu54_m27_stable_release_test", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class M27StableReleaseTests(unittest.TestCase):
    """! @brief 공개 전·후 경계를 fail-closed 방식으로 검사합니다. """

    def test_parser_separates_prepare_dry_run_and_publication(self) -> None:
        """! @brief 각 단계가 서로 다른 명령이며 게시에는 승인 파일이 필수입니다. """
        parser = MODULE.build_parser()
        action = next(item for item in parser._actions if getattr(item, "choices", None))
        self.assertEqual(
            set(action.choices),
            {
                "contract",
                "prepare",
                "validate-plan",
                "publication-dry-run",
                "publish-release",
                "publish-index",
            },
        )
        for command in ("publication-dry-run", "publish-release", "publish-index"):
            with self.subTest(command=command):
                with self.assertRaises(SystemExit):
                    parser.parse_args((command, "--plan", "plan.json"))

    def test_published_stable_cannot_be_reconfigured(self) -> None:
        """! @brief 공개된 v0.4.0을 다른 commit으로 다시 구성하지 못하게 합니다. """
        commit = "a" * 40
        package = MODULE.load_module("nu54_m27_stable_config_a", MODULE.PACKAGE_MODULE)
        self.assertIn(MODULE.VERSION, package.STABLE_VERSIONS)
        self.assertEqual(
            package.STABLE_RELEASE_COMMITS[MODULE.VERSION],
            "ad829439e570c7510fce2f8cc7252e5b9ef32b04",
        )
        with self.assertRaisesRegex(MODULE.StableReleaseFailure, "already"):
            MODULE.configure_stable_package(package, commit)
        fresh = MODULE.load_module("nu54_m27_stable_config_b", MODULE.PACKAGE_MODULE)
        self.assertEqual(fresh.STABLE_VERSIONS, ("0.1.0", "0.2.0", "0.3.0", "0.4.0"))
        self.assertIn(MODULE.VERSION, fresh.PACKAGE_VERSIONS)

    def test_wrong_version_or_commit_is_rejected(self) -> None:
        """! @brief 기존 version과 비정규 commit 입력을 거부합니다. """
        package = MODULE.load_module("nu54_m27_stable_bad", MODULE.PACKAGE_MODULE)
        with self.assertRaises(MODULE.StableReleaseFailure):
            MODULE.configure_stable_package(package, "not-a-commit")
        with self.assertRaises(package.PackageError):
            package.configure_unpublished_stable("0.3.0", "a" * 40)
        with self.assertRaises(package.PackageError):
            package.configure_unpublished_stable("0.4.0-rc.1", "a" * 40)

    def test_every_technical_gate_is_required_before_stable_prepare(self) -> None:
        """! @brief 하나라도 pending이면 stable 준비를 차단합니다. """
        gates = [
            {"id": gate_id, "state": "passed", "kind": "automated", "required": True}
            for gate_id in MODULE.TECHNICAL_GATE_IDS
        ]
        gates.append(
            {
                "id": "project_owner_approval",
                "state": "hold",
                "kind": "human",
                "required": True,
            }
        )

        class FakeM27:
            M27ReleaseFailure = RuntimeError
            REQUIRED_GATE_IDS = tuple(gate["id"] for gate in gates)

            @staticmethod
            def validate_contract(_repository: Path) -> dict[str, object]:
                return {"gates": gates}

        with mock.patch.object(MODULE, "load_module", return_value=FakeM27):
            ledger = MODULE.validate_technical_readiness(REPOSITORY)
            self.assertEqual(len(ledger["gates"]), len(MODULE.TECHNICAL_GATE_IDS) + 1)
            gates[4]["state"] = "pending"
            with self.assertRaisesRegex(
                MODULE.StableReleaseFailure, MODULE.TECHNICAL_GATE_IDS[4]
            ):
                MODULE.validate_technical_readiness(REPOSITORY)

    def test_approval_must_bind_exact_plan_commit_and_hash(self) -> None:
        """! @brief 다른 plan에 대한 승인과 불완전한 승인을 거부합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            plan_path.write_text('{"plan":"exact"}\n', encoding="utf-8")
            plan = {"target_commit": "b" * 40}
            approval = {
                "schema_version": 1,
                "milestone": "T22",
                "decision": "approved",
                "version": MODULE.VERSION,
                "target_commit": plan["target_commit"],
                "stable_plan_sha256": MODULE.sha256_file(plan_path),
                "approver_role": "project-owner",
                "approval_source": "explicit-project-owner-approval",
                "approved_at_utc": "2026-09-10T00:00:00+00:00",
            }
            approval_path = root / "approval.json"
            approval_path.write_text(json.dumps(approval), encoding="utf-8")
            self.assertEqual(
                MODULE.validate_approval(plan_path, approval_path, plan), approval
            )
            approval["stable_plan_sha256"] = "0" * 64
            approval_path.write_text(json.dumps(approval), encoding="utf-8")
            with self.assertRaises(MODULE.StableReleaseFailure):
                MODULE.validate_approval(plan_path, approval_path, plan)

    def test_publication_does_not_reach_runner_without_approval(self) -> None:
        """! @brief 승인 증거가 없으면 외부 쓰기 전 읽기 명령도 실행하지 않습니다. """
        calls: list[tuple[str, ...]] = []

        def runner(arguments: object, _cwd: Path | None) -> MODULE.CommandResult:
            calls.append(tuple(arguments))
            return MODULE.CommandResult(0, b"", b"")

        plan = {"target_commit": "c" * 40}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            plan_path.write_text("{}\n", encoding="utf-8")
            missing = root / "missing-approval.json"
            with mock.patch.object(MODULE, "validate_plan", return_value=plan):
                with self.assertRaises(MODULE.StableReleaseFailure):
                    MODULE.publish_release(plan_path, missing, runner=runner)
        self.assertEqual(calls, [])

    def test_existing_remote_tag_or_release_is_never_overwritten(self) -> None:
        """! @brief 기존 tag/Release를 발견하면 create 단계 전에 중단합니다. """
        plan = {"target_commit": "d" * 40}
        approval = {
            "schema_version": 1,
            "milestone": "T22",
            "decision": "approved",
            "version": MODULE.VERSION,
            "target_commit": plan["target_commit"],
            "stable_plan_sha256": "unused",
            "approver_role": "project-owner",
            "approval_source": "explicit-project-owner-approval",
            "approved_at_utc": "2026-09-10T00:00:00Z",
        }
        responses = iter(
            (
                MODULE.CommandResult(0, b"main\n", b""),
                MODULE.CommandResult(
                    0,
                    f"{'d' * 40}\trefs/heads/main\n".encode("ascii"),
                    b"",
                ),
                MODULE.CommandResult(
                    0,
                    f"{'e' * 40}\trefs/tags/{MODULE.TAG}\n".encode("ascii"),
                    b"",
                ),
            )
        )

        def runner(_arguments: object, _cwd: Path | None) -> MODULE.CommandResult:
            return next(responses)

        with mock.patch.object(MODULE, "validate_plan", return_value=plan):
            with mock.patch.object(MODULE, "validate_approval", return_value=approval):
                with self.assertRaisesRegex(MODULE.StableReleaseFailure, "tag already"):
                    MODULE.publication_dry_run(
                        Path("plan.json"), Path("approval.json"), runner=runner
                    )

    def test_release_upload_excludes_root_index(self) -> None:
        """! @brief stable root index는 Release asset과 별도 게시됩니다. """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifacts: dict[str, dict[str, object]] = {}
            for role in MODULE.ASSET_ROLES:
                path = root / f"{role}.dat"
                path.write_bytes(role.encode("ascii"))
                artifacts[role] = {
                    "path": path.name,
                    "size": path.stat().st_size,
                    "sha256": MODULE.sha256_file(path),
                }
            plan = {"target_commit": "f" * 40, "artifacts": artifacts}
            calls: list[tuple[str, ...]] = []

            def runner(arguments: object, _cwd: Path | None) -> MODULE.CommandResult:
                calls.append(tuple(arguments))
                return MODULE.CommandResult(0, b"", b"")

            with mock.patch.object(MODULE, "publication_dry_run", return_value=plan):
                MODULE.publish_release(root / "plan.json", root / "approval.json", runner=runner)
            self.assertEqual(len(calls), 1)
            command = calls[0]
            self.assertEqual(command[:3], ("gh", "release", "create"))
            upload_arguments = command[command.index("--latest") + 1 :]
            uploaded_paths = {Path(argument).resolve() for argument in upload_arguments}
            self.assertNotIn(
                (root / artifacts["index"]["path"]).resolve(), uploaded_paths
            )
            for role in MODULE.PACKAGE_ROLES + tuple(MODULE.DOCUMENT_PATHS):
                self.assertIn(
                    (root / artifacts[role]["path"]).resolve(), uploaded_paths
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
