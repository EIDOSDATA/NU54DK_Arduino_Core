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
            with mock.patch.object(MODULE.LOCK_MODULE, "strict_json_object", return_value=lock), mock.patch.object(MODULE.LOCK_MODULE, "validate_lock"), mock.patch.object(MODULE.LOCK_MODULE, "validate_workspace"), mock.patch.object(MODULE, "run_build", side_effect=lambda *_args: next(outcomes)):
                evidence, passed = MODULE.execute(workspace, workspace / "out", "west")
        self.assertFalse(passed)
        self.assertEqual(evidence["control_gate"], "fail")
        self.assertEqual(len(evidence["samples"]), 4)
        self.assertEqual(evidence["samples"][1]["builds"]["nu54dk_applicability"]["return_code"], 1)


if __name__ == "__main__":
    unittest.main()
