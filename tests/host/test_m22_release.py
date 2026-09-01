#!/usr/bin/env python3
"""! @brief M22 RC1 release 수명주기의 고정 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
PATH = REPOSITORY / "tools" / "release" / "m22_release.py"
SPEC = importlib.util.spec_from_file_location("m22_release", PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"M22 release를 읽지 못했습니다: {PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M22ReleaseTests(unittest.TestCase):
    """! @brief allowlist·재현 build·필수 gate·publication 부재를 시험합니다. """

    def setUp(self) -> None:
        """! @brief 임시 plan/evidence 공간을 만듭니다. """

        self.temporary = tempfile.TemporaryDirectory(prefix="nu54-m22-release-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        """! @brief 임시 evidence를 정리합니다. """

        self.temporary.cleanup()

    def test_package_contract_contains_only_exact_new_rc(self) -> None:
        """! @brief 0.3.0-rc.1이 과거 RC/stable 계약 뒤에 정확히 추가됩니다. """

        MODULE.assert_package_contract()
        self.assertEqual(MODULE.EXPECTED_RC_VERSIONS[-1], MODULE.VERSION)
        self.assertEqual(MODULE.VERSION, "0.3.0-rc.1")

    def test_two_builds_must_be_byte_identical(self) -> None:
        """! @brief 독립 build 중 한 byte라도 다르면 prepare가 진행되지 않습니다. """

        first: dict[str, Path] = {}
        second: dict[str, Path] = {}
        for role in MODULE.PACKAGE_ROLES:
            left = self.root / "a" / f"{role}.bin"
            right = self.root / "b" / f"{role}.bin"
            left.parent.mkdir(exist_ok=True)
            right.parent.mkdir(exist_ok=True)
            left.write_bytes(role.encode())
            right.write_bytes(role.encode())
            first[role], second[role] = left, right
        self.assertEqual(set(MODULE.compare_builds(first, second)), set(MODULE.PACKAGE_ROLES))
        second["archive"].write_bytes(b"changed")
        with self.assertRaisesRegex(MODULE.M22ReleaseFailure, "재현되지"):
            MODULE.compare_builds(first, second)

    def test_parser_exposes_no_publish_or_push_command(self) -> None:
        """! @brief M22 자동화가 GitHub Release 조작 경로를 제공하지 않습니다. """

        help_text = MODULE.build_parser().format_help().casefold()
        self.assertNotIn("publish", help_text)
        self.assertNotIn("push", help_text)
        for command in ("prepare", "validate", "run-gate", "run-cleanroom", "finalize"):
            self.assertIn(command, help_text)

    def test_finalize_requires_exact_four_passed_gates(self) -> None:
        """! @brief host/examples/upload/clean-room 모두 있어야 RC1 ready가 됩니다. """

        plan = self.root / "plan.json"
        plan.write_text("{}\n", encoding="utf-8")
        plan_value = {
            "target_commit": "a" * 40,
            "board_revision": "b" * 40,
            "runners": {
                "tools/release/run_m22_fixed_gate.py": {
                    "sha256": MODULE.file_sha256(
                        REPOSITORY / "tools" / "release" / "run_m22_fixed_gate.py"
                    ),
                    "size": (
                        REPOSITORY / "tools" / "release" / "run_m22_fixed_gate.py"
                    ).stat().st_size,
                }
            },
        }
        evidences: list[Path] = []
        for gate in ("host", "package-examples", "rc-upload"):
            path = self.root / f"{gate}.json"
            value = {
                "schema_version": 1,
                "milestone": "M22",
                "evidence_type": "fixed-gate",
                "gate_id": gate,
                "status": "passed",
                "release_version": MODULE.VERSION,
                "command_contract": {"probe_id_recorded": False},
                "release_binding": {
                    "plan_sha256": MODULE.file_sha256(plan),
                    "core_revision": plan_value["target_commit"],
                },
                "runner": {
                    "repository_relative_path": "tools/release/run_m22_fixed_gate.py",
                    "sha256": plan_value["runners"]["tools/release/run_m22_fixed_gate.py"]["sha256"],
                },
            }
            path.write_text(json.dumps(value) + "\n", encoding="utf-8")
            evidences.append(path)
        clean = self.root / "cleanroom.json"
        clean.write_text(
            json.dumps({
                "schema_version": 1,
                "milestone": "M22",
                "evidence_type": "same-pc-isolated-cleanroom",
                "status": "passed",
                "release_version": MODULE.VERSION,
                "cleanup": {"status": "passed", "external_evidence_preserved": True},
                "isolation": {"existing_path_leakage": False, "probe_id_recorded": False},
                "installed_release": {
                    "core_revision": plan_value["target_commit"],
                    "board_revision": plan_value["board_revision"],
                },
            }) + "\n",
            encoding="utf-8",
        )
        with mock.patch.object(MODULE, "validate_plan", return_value=plan_value):
            with self.assertRaisesRegex(MODULE.M22ReleaseFailure, "완성되지"):
                MODULE.finalize_evidence(plan, evidences, self.root / "incomplete.json")
            final = MODULE.finalize_evidence(
                plan, [*evidences, clean], self.root / "final.json"
            )
        self.assertEqual(final["state"], "rc1-validated-ready-for-owner-publication")
        self.assertFalse(final["publication_performed"])


if __name__ == "__main__":
    unittest.main()
