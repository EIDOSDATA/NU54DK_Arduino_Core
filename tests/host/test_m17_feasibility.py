#!/usr/bin/env python3
"""! @brief M17 무선 build feasibility runner 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY / "tools" / "ci" / "run_m17_feasibility.py"
SPEC = importlib.util.spec_from_file_location("nu54_m17_feasibility", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M17FeasibilityTests(unittest.TestCase):
    """! @brief official control과 NU54DK applicability 기록을 검증합니다. """

    def test_build_command_is_fixed_sysbuild(self) -> None:
        """! @brief 명령이 고정 board와 sysbuild 및 저장소 BOARD_ROOT를 사용합니다. """
        command = MODULE.build_command(
            "west", Path("source"), Path("build"), MODULE.NU54DK_BOARD
        )
        self.assertEqual(command[:2], ["west", "build"])
        self.assertIn("--sysbuild", command)
        self.assertEqual(command[command.index("-b") + 1], MODULE.NU54DK_BOARD)
        self.assertTrue(command[-1].startswith("-DBOARD_ROOT="))

    @mock.patch.object(MODULE.subprocess, "run")
    def test_run_build_hashes_normalized_log(self, run: mock.Mock) -> None:
        """! @brief 통합 stdout을 정규화해 exact log hash와 결과를 남깁니다. """
        run.return_value = mock.Mock(returncode=0, stdout="first\r\nsecond\r\n")
        with tempfile.TemporaryDirectory(prefix="nu54-m17-feasibility-") as name:
            log = Path(name) / "build.log"
            workspace = Path(name)
            result = MODULE.run_build(["west", "build"], log, workspace)
            self.assertEqual(result["result"], "pass")
            self.assertEqual(log.read_bytes(), b"first\nsecond\n")
            self.assertEqual(result["log_sha256"], MODULE.sha256_file(log))
            self.assertEqual(run.call_args.kwargs["cwd"], workspace)

    def test_declared_samples_and_support_boundary_are_exact(self) -> None:
        """! @brief 검토 대상은 공식 세 sample이며 지원 선언은 runner에 포함하지 않습니다. """
        self.assertEqual(
            MODULE.SAMPLES,
            (
                ("crypto_rng", "samples/crypto/rng", MODULE.CRYPTO_POLICY),
                ("802154_phy_test", "samples/peripheral/802154_phy_test", MODULE.NETWORK_POLICY),
                ("openthread_cli", "samples/openthread/cli", MODULE.NETWORK_POLICY),
                ("matter_template", "samples/matter/template", MODULE.NETWORK_POLICY),
            ),
        )
        self.assertEqual(MODULE.CRYPTO_POLICY["support_declaration"], "build-only")
        self.assertEqual(MODULE.CRYPTO_POLICY["validation_scope"], "build-only")
        self.assertEqual(MODULE.NETWORK_POLICY["support_declaration"], "deferred")
        self.assertEqual(MODULE.NETWORK_POLICY["validation_scope"], "build-feasibility-only")
        self.assertEqual(MODULE.CRYPTO_POLICY["hil"], "not-run")
        self.assertEqual(MODULE.NETWORK_POLICY["hil"], "not-run")

    def test_policy_rejects_networking_support_promotion(self) -> None:
        """! @brief networking sample을 build-only 또는 supported로 승격하지 못하게 합니다. """
        promoted = dict(MODULE.NETWORK_POLICY)
        promoted["support_declaration"] = "build-only"
        with self.assertRaisesRegex(MODULE.FeasibilityFailure, "승인하지 않은 sample 정책"):
            MODULE.validate_sample_policy("openthread_cli", promoted)

    def test_policy_rejects_crypto_deferred_or_hil(self) -> None:
        """! @brief crypto build-only 항목을 deferred로 낮추거나 HIL로 오표기하지 못하게 합니다. """
        wrong = dict(MODULE.CRYPTO_POLICY)
        wrong.update({"support_declaration": "deferred", "hil": "pass"})
        with self.assertRaisesRegex(MODULE.FeasibilityFailure, "승인하지 않은 sample 정책"):
            MODULE.validate_sample_policy("crypto_rng", wrong)

    def test_official_control_failure_is_gate_failure(self) -> None:
        """! @brief official control 실패가 있어도 두 역할의 evidence를 보존하고 gate를 실패시킵니다. """
        outcomes = iter(
            [
                {"return_code": 1}, {"return_code": 0},
                {"return_code": 0}, {"return_code": 1},
                {"return_code": 0}, {"return_code": 0},
                {"return_code": 0}, {"return_code": 0},
            ]
        )
        lock = {
            "ncs": {"tag": "v3.4.0", "revision": "a" * 40},
            "zephyr": {"revision": "b" * 40},
            "board": {"revision": "c" * 40},
        }
        with tempfile.TemporaryDirectory(prefix="nu54-m17-workspace-") as workspace_name:
            workspace = Path(workspace_name)
            for _name, relative, _policy in MODULE.SAMPLES:
                (workspace / "nrf" / relative).mkdir(parents=True)
            identity = {
                "ncs_revision": "a" * 40,
                "zephyr_revision": "b" * 40,
                "board_revision": "c" * 40,
            }
            with mock.patch.object(MODULE.LOCK_MODULE, "strict_json_object", return_value=lock), mock.patch.object(MODULE.LOCK_MODULE, "validate_lock"), mock.patch.object(MODULE, "validate_execution_inputs", return_value=identity), mock.patch.object(MODULE, "run_build", side_effect=lambda *_args: next(outcomes)):
                evidence, passed = MODULE.execute(workspace, workspace / "out", "west")
        self.assertFalse(passed)
        self.assertEqual(evidence["control_gate"], "fail")
        self.assertEqual(len(evidence["samples"]), 4)
        self.assertEqual(evidence["samples"][1]["builds"]["nu54dk_applicability"]["return_code"], 1)

    def test_crypto_nu54dk_failure_is_gate_failure(self) -> None:
        """! @brief crypto RNG는 official과 NU54DK가 모두 성공해야 gate를 통과합니다. """
        outcomes = iter(
            [
                {"return_code": 0}, {"return_code": 1},
                {"return_code": 0}, {"return_code": 1},
                {"return_code": 0}, {"return_code": 1},
                {"return_code": 0}, {"return_code": 1},
            ]
        )
        evidence, passed = self.execute_with_outcomes(outcomes)
        self.assertFalse(passed)
        self.assertEqual(evidence["control_gate"], "fail")

    def test_network_nu54dk_failure_is_recorded_but_not_gate_failure(self) -> None:
        """! @brief deferred networking은 official만 gate이며 NU54DK 실패는 evidence에 보존합니다. """
        outcomes = iter(
            [
                {"return_code": 0}, {"return_code": 0},
                {"return_code": 0}, {"return_code": 1},
                {"return_code": 0}, {"return_code": 1},
                {"return_code": 0}, {"return_code": 1},
            ]
        )
        evidence, passed = self.execute_with_outcomes(outcomes)
        self.assertTrue(passed)
        self.assertEqual(evidence["control_gate"], "pass")
        self.assertEqual(
            evidence["gate_contract"]["networking"], ["official_control"]
        )
        self.assertTrue(
            all(
                record["builds"]["nu54dk_applicability"]["return_code"] == 1
                for record in evidence["samples"][1:]
            )
        )

    def execute_with_outcomes(self, outcomes) -> tuple[dict, bool]:
        """! @brief 고정 입력에서 build 결과 배열을 실행하는 fixture입니다. """
        lock = {
            "ncs": {"tag": "v3.4.0", "revision": "a" * 40},
            "zephyr": {"revision": "b" * 40},
            "board": {"revision": "c" * 40},
        }
        identity = {
            "ncs_revision": "a" * 40,
            "zephyr_revision": "b" * 40,
            "board_revision": "c" * 40,
        }
        with tempfile.TemporaryDirectory(prefix="nu54-m17-workspace-") as workspace_name:
            workspace = Path(workspace_name)
            for _name, relative, _policy in MODULE.SAMPLES:
                (workspace / "nrf" / relative).mkdir(parents=True)
            with mock.patch.object(MODULE.LOCK_MODULE, "strict_json_object", return_value=lock), mock.patch.object(MODULE.LOCK_MODULE, "validate_lock"), mock.patch.object(MODULE, "validate_execution_inputs", return_value=identity), mock.patch.object(MODULE, "run_build", side_effect=lambda *_args: next(outcomes)):
                return MODULE.execute(workspace, workspace / "out", "west")

    def test_execution_inputs_reject_dirty_board(self) -> None:
        """! @brief exact revision이어도 board checkout이 dirty이면 build 전에 거부합니다. """
        lock = {
            "ncs": {"revision": "a" * 40},
            "zephyr": {"revision": "b" * 40},
            "board": {"revision": "c" * 40},
        }
        gitlink = (
            f"160000 commit {'c' * 40}\tboard_package/NU54DK_Zephyr_DTS\n"
        )
        with mock.patch.object(MODULE.LOCK_MODULE, "validate_workspace"), mock.patch.object(MODULE.LOCK_MODULE, "git_revision", return_value="c" * 40), mock.patch.object(MODULE, "git_output", side_effect=["", "", " M dirty.txt\n", gitlink]):
            with self.assertRaisesRegex(MODULE.FeasibilityFailure, "미커밋 변경"):
                MODULE.validate_execution_inputs(Path("workspace"), lock)

    def test_execution_inputs_reject_board_revision_or_gitlink_mismatch(self) -> None:
        """! @brief 실제 checkout과 부모 gitlink가 lock revision에서 벗어나면 거부합니다. """
        lock = {
            "ncs": {"revision": "a" * 40},
            "zephyr": {"revision": "b" * 40},
            "board": {"revision": "c" * 40},
        }
        with mock.patch.object(MODULE.LOCK_MODULE, "validate_workspace"), mock.patch.object(MODULE.LOCK_MODULE, "git_revision", return_value="d" * 40), mock.patch.object(MODULE, "git_output", side_effect=["", ""]):
            with self.assertRaisesRegex(MODULE.FeasibilityFailure, "checkout revision"):
                MODULE.validate_execution_inputs(Path("workspace"), lock)
        wrong_gitlink = (
            f"160000 commit {'d' * 40}\tboard_package/NU54DK_Zephyr_DTS\n"
        )
        with mock.patch.object(MODULE.LOCK_MODULE, "validate_workspace"), mock.patch.object(MODULE.LOCK_MODULE, "git_revision", return_value="c" * 40), mock.patch.object(MODULE, "git_output", side_effect=["", "", "", wrong_gitlink]):
            with self.assertRaisesRegex(MODULE.FeasibilityFailure, "gitlink"):
                MODULE.validate_execution_inputs(Path("workspace"), lock)

    def test_execution_inputs_reject_dirty_ncs_or_zephyr_workspace(self) -> None:
        """! @brief revision이 같아도 NCS·Zephyr source 변경은 exact workspace가 아닙니다. """
        lock = {
            "ncs": {"revision": "a" * 40},
            "zephyr": {"revision": "b" * 40},
            "board": {"revision": "c" * 40},
        }
        with mock.patch.object(MODULE.LOCK_MODULE, "validate_workspace"), mock.patch.object(MODULE, "git_output", side_effect=[" M sample.c\n"]):
            with self.assertRaisesRegex(MODULE.FeasibilityFailure, "NCS workspace"):
                MODULE.validate_execution_inputs(Path("workspace"), lock)
        with mock.patch.object(MODULE.LOCK_MODULE, "validate_workspace"), mock.patch.object(MODULE, "git_output", side_effect=["", "?? local.patch\n"]):
            with self.assertRaisesRegex(MODULE.FeasibilityFailure, "Zephyr workspace"):
                MODULE.validate_execution_inputs(Path("workspace"), lock)


if __name__ == "__main__":
    unittest.main()
