#!/usr/bin/env python3
"""! @brief M14 QEMU 실제 실행기의 fail-closed 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPOSITORY / "tools" / "ci" / "run_m14_qemu.py"
SPEC = importlib.util.spec_from_file_location("nu54_m14_qemu_test", RUNNER_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


## @brief 정상적인 QEMU runtime Twister report를 만듭니다.
def passing_report() -> dict[str, object]:
    return {
        "testsuites": [
            {
                "name": RUNNER.SCENARIO,
                "platform": RUNNER.PLATFORM_REPORT,
                "runnable": True,
                "status": "passed",
                "testcases": [
                    {"identifier": identifier, "status": "passed"}
                    for identifier in RUNNER.EXPECTED_TESTCASES
                ],
            }
        ]
    }


class M14QemuRunnerTests(unittest.TestCase):
    """! @brief QEMU 실행 명령과 결과 검증의 폐쇄형 계약을 검사합니다. """

    ## @brief Twister 명령이 정확한 scenario를 실제 실행하도록 구성되는지 검사합니다.
    def test_command_selects_exact_runtime_scenario_without_build_only(self) -> None:
        workspace = Path("/ncs-v3.4.0")
        outdir = Path("/evidence/m14-qemu")
        command = RUNNER.twister_command(workspace, outdir)
        self.assertNotIn("--build-only", command)
        self.assertEqual(command[command.index("--platform") + 1], RUNNER.PLATFORM_REQUEST)
        self.assertEqual(command[command.index("--scenario") + 1], RUNNER.SCENARIO)
        self.assertEqual(command[command.index("--testsuite-root") + 1], str(RUNNER.TEST_ROOT))
        self.assertIn("USE_CCACHE=0", command)

    ## @brief 정확한 scenario와 세 testcase의 실제 PASS report를 허용합니다.
    def test_validate_report_accepts_exact_runtime_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report_path = Path(temporary) / "twister.json"
            report_path.write_text(json.dumps(passing_report()), encoding="utf-8")
            RUNNER.validate_report(report_path)

    ## @brief build-only·부분 PASS·추가 testcase가 성공으로 오인되지 않게 합니다.
    def test_validate_report_rejects_non_runtime_or_inexact_results(self) -> None:
        invalid_reports: list[dict[str, object]] = []

        build_only = passing_report()
        build_only["testsuites"][0]["runnable"] = False  # type: ignore[index]
        build_only["testsuites"][0]["status"] = "not run"  # type: ignore[index]
        invalid_reports.append(build_only)

        failed_case = passing_report()
        failed_case["testsuites"][0]["testcases"][0]["status"] = "failed"  # type: ignore[index]
        invalid_reports.append(failed_case)

        missing_case = passing_report()
        missing_case["testsuites"][0]["testcases"].pop()  # type: ignore[index]
        invalid_reports.append(missing_case)

        extra_case = passing_report()
        extra_case["testsuites"][0]["testcases"].append(  # type: ignore[index]
            {"identifier": "nucode.m14.cpp_policy.unexpected", "status": "passed"}
        )
        invalid_reports.append(extra_case)

        wrong_platform = passing_report()
        wrong_platform["testsuites"][0]["platform"] = "qemu_cortex_m3"  # type: ignore[index]
        invalid_reports.append(wrong_platform)

        with tempfile.TemporaryDirectory() as temporary:
            report_path = Path(temporary) / "twister.json"
            for index, report in enumerate(invalid_reports):
                with self.subTest(index=index):
                    report_path.write_text(json.dumps(report), encoding="utf-8")
                    with self.assertRaises(RUNNER.RuntimeFailure):
                        RUNNER.validate_report(report_path)

    ## @brief 실행 전에 exact workspace를 검사하고 성공 후 report를 검증합니다.
    def test_run_runtime_validates_workspace_and_report(self) -> None:
        lock = {"ncs": {}, "zephyr": {}}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "ncs"
            outdir = root / "out"
            with (
                mock.patch.object(RUNNER.LOCK_MODULE, "validate_workspace") as validate_workspace,
                mock.patch.object(
                    RUNNER, "qemu_identity", return_value=("/usr/bin/qemu-system-arm", "QEMU 9.0")
                ),
                mock.patch.object(
                    RUNNER.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=0),
                ) as run,
                mock.patch.object(RUNNER, "validate_report") as validate_report,
            ):
                identity = RUNNER.run_runtime(workspace, outdir, lock)

            self.assertEqual(identity, ("/usr/bin/qemu-system-arm", "QEMU 9.0"))
            validate_workspace.assert_called_once_with(workspace, lock)
            validate_report.assert_called_once_with(outdir / "twister.json")
            command = run.call_args.args[0]
            self.assertNotIn("--build-only", command)
            self.assertEqual(run.call_args.kwargs["cwd"], workspace)
            self.assertEqual(
                run.call_args.kwargs["env"]["ZEPHYR_BASE"], str(workspace / "zephyr")
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
