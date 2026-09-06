#!/usr/bin/env python3
"""! @brief 릴리스 도입 기능군 병렬 build runner 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import yaml


REPOSITORY = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path) -> object:
    """! @brief dataclass module도 안전하게 import할 수 있도록 등록합니다. """
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


MATRIX = load_module(
    "nu54_build_matrix_test", REPOSITORY / "tools" / "ci" / "run_build_matrix.py"
)
ZEPHYR = load_module(
    "nu54_zephyr_groups_test", REPOSITORY / "tools" / "ci" / "run_zephyr_build.py"
)
ARDUINO = load_module(
    "nu54_arduino_groups_test", REPOSITORY / "tests" / "arduino-cli" / "run_smoke.py"
)


class BuildMatrixRunnerTests(unittest.TestCase):
    """! @brief 릴리스 기능군 범위·명령·진단 경계를 검증합니다. """

    ## @brief Zephyr 60개 시나리오가 중복·누락 없이 4/10/19/27로 분리됩니다.
    def test_zephyr_groups_partition_every_suite_once(self) -> None:
        self.assertEqual(
            {name: len(suites) for name, suites in ZEPHYR.SUITE_GROUPS.items()},
            {"v0.1.0": 4, "v0.2.0": 10, "v0.3.0": 19, "v0.4.0": 27},
        )
        flattened = tuple(
            suite for suites in ZEPHYR.SUITE_GROUPS.values() for suite in suites
        )
        self.assertEqual(flattened, ZEPHYR.SUITES)
        self.assertEqual(len(set(flattened)), len(flattened))

    def test_all_nu54dk_testcase_metadata_is_in_canonical_runner(self) -> None:
        """! @brief 독립 testcase YAML을 대조하여 새 target의 canonical 목록 누락을 거부합니다. """
        expected = set()
        excluded = set()
        for path in (REPOSITORY / "tests/zephyr").glob("*/testcase.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            common = document.get("common", {})
            for name, test in document["tests"].items():
                platforms = test.get("platform_allow", common.get("platform_allow", []))
                if ZEPHYR.BOARD_TARGET in platforms:
                    expected.add((path.parent.name, name))
                else:
                    excluded.add(name)
        self.assertEqual(set(ZEPHYR.SUITES), expected)
        self.assertEqual(excluded, {"nucode.m14.cpp_policy"})

    def test_target_subset_never_silently_escapes_group(self) -> None:
        names = ("nucode.v04.pair_dut", "nucode.v04.pair_peer")
        chosen = ZEPHYR.select_suites("v0.4.0", names)
        self.assertEqual({name for _, name in chosen}, set(names))
        self.assertEqual(ZEPHYR.select_suites("v0.4.0"), tuple(ZEPHYR.SUITE_GROUPS["v0.4.0"]))
        for group, invalid in (("v0.3.0", names), ("v0.4.0", names + names), ("v0.4.0", ("missing",))):
            with self.assertRaises(ZEPHYR.BuildFailure): ZEPHYR.select_suites(group, invalid)
        self.assertIn('"m12-zephyr-build-subset" if args.suite',
                      (REPOSITORY / "tools/ci/run_zephyr_build.py").read_text(encoding="utf-8"))

    ## @brief 꺼진 CONFIG·잘못된 target·중복 object·누락 symbol은 build PASS로 처리하지 않습니다.
    def test_serial_source_validator_rejects_false_positive_builds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nu54-r01-validator-") as temporary:
            outdir = Path(temporary)
            app = outdir / ZEPHYR.BOARD_TARGET.replace("/", "_") / "zephyr_gnu/nucode.r01.spim/r01_serial"
            (app / "zephyr").mkdir(parents=True)
            config = "".join(f"CONFIG_NUCODE_ARDUINO_{name}=y\n" for name in
                             ("CORE", "API", "IO_OWNERSHIP", "GPIO", "SERIAL_FABRIC", "SERIAL_FABRIC_SPIM"))
            (app / "zephyr/.config").write_text(config, encoding="utf-8")
            (app / "zephyr/zephyr.elf").write_bytes(b"test ELF input")
            (app / "CMakeCache.txt").write_text("CMAKE_NM:FILEPATH=exact-nm\n", encoding="utf-8")
            command = {"file": "/checkout/cores/arduino/SpimFabric.cpp",
                       "command": "c++ -o modules/core/CMakeFiles/nucode_arduino_core.dir/SpimFabric.cpp.obj"}
            commands = app / "compile_commands.json"
            commands.write_text(json.dumps([command]), encoding="utf-8")
            selection = (("r01_serial", "nucode.r01.spim"),)
            completed = subprocess.CompletedProcess([], 0, "nucode::arduino::SpimHandle::configure(config)\n", "")
            with mock.patch.object(ZEPHYR.subprocess, "run", return_value=completed):
                self.assertEqual(ZEPHYR.validate_serial_source_builds(outdir, selection)[0]["resolved_personalities"], ["SPIM"])
                for invalid in ([], [command, command], [{**command, "command": "c++ -o zephyr.dir/SpimFabric.cpp.obj"}]):
                    commands.write_text(json.dumps(invalid), encoding="utf-8")
                    with self.assertRaises(ZEPHYR.BuildFailure):
                        ZEPHYR.validate_serial_source_builds(outdir, selection)
                commands.write_text(json.dumps([command]), encoding="utf-8")
                (app / "zephyr/.config").write_text(config.replace("SERIAL_FABRIC_SPIM=y", "SERIAL_FABRIC_SPIM=n"), encoding="utf-8")
                with self.assertRaises(ZEPHYR.BuildFailure):
                    ZEPHYR.validate_serial_source_builds(outdir, selection)
                (app / "zephyr/.config").write_text(config, encoding="utf-8")
                completed.stdout = ""
                with self.assertRaises(ZEPHYR.BuildFailure):
                    ZEPHYR.validate_serial_source_builds(outdir, selection)

    ## @brief Arduino 예제 기능군도 각 지원 릴리스에서 도입한 범위로 고정됩니다.
    def test_arduino_groups_are_explicit_and_disjoint(self) -> None:
        self.assertEqual(
            ARDUINO.ARDUINO_GROUPS,
            {
                "v0.1.0": ("blink", "m6", "m7"),
                "v0.2.0": ("m15", "m16"),
                "v0.3.0": ("m19m20", "m21", "ac02b", "ac03", "examples"),
            },
        )
        self.assertEqual(
            ARDUINO.ARDUINO_MATRIX_GROUPS,
            {
                "v0.1.0": ("blink", "m6", "m7"),
                "v0.2.0": ("m15", "m16"),
                "v0.3.0-ble": ("m19m20", "m21"),
                "v0.3.0-compat": ("ac02b", "ac03", "examples"),
            },
        )
        flattened = tuple(
            test for tests in ARDUINO.ARDUINO_MATRIX_GROUPS.values() for test in tests
        )
        self.assertEqual(len(set(flattened)), len(flattened))
        self.assertTrue(set(flattened).issubset(set(ARDUINO.ARDUINO_TESTS)))
        self.assertEqual(MATRIX.ARDUINO_GROUPS, tuple(ARDUINO.ARDUINO_MATRIX_GROUPS))

    ## @brief 로컬 Zephyr matrix가 짧고 서로 다른 outdir와 group 인자를 만듭니다.
    def test_zephyr_plan_uses_short_isolated_outdirs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / "evidence"
            tasks = MATRIX.build_tasks(
                runner="zephyr",
                groups=MATRIX.ZEPHYR_GROUPS,
                python=Path("C:/ncs/python.exe"),
                workspace=Path("C:/ncs/v3.4.0"),
                out_root=Path("C:/t"),
                evidence_dir=evidence,
            )
        self.assertEqual(len(tasks), 4)
        outdirs = []
        for task in tasks:
            command = list(task.command)
            self.assertEqual(command[command.index("--group") + 1], task.group)
            outdirs.append(command[command.index("--outdir") + 1])
        self.assertEqual(len(set(outdirs)), 4)
        self.assertTrue(all(len(outdir) <= 8 for outdir in outdirs))

    ## @brief 실패한 Twister suite의 이름·상태·사유가 즉시 표시됩니다.
    def test_zephyr_failure_summary_identifies_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "twister.json"
            report.write_text(
                '{"testsuites":[{"name":"nucode.bad","status":"error",'
                '"reason":"build failed"}]}',
                encoding="utf-8",
            )
            summary = ZEPHYR.failure_summary(report)
        self.assertEqual(summary, "nucode.bad: error (build failed)")

    ## @brief 긴 하위 build의 현재 단계가 pipe buffering 없이 즉시 전달됩니다.
    def test_child_python_output_is_unbuffered(self) -> None:
        source = (
            REPOSITORY / "tools" / "ci" / "run_build_matrix.py"
        ).read_text(encoding="utf-8")
        self.assertIn('environment["PYTHONUNBUFFERED"] = "1"', source)
        self.assertIn("env=environment", source)

    ## @brief 일시적 Arduino CLI builtin bootstrap 실패만 제한 재시도합니다.
    @mock.patch.object(ARDUINO.time, "sleep")
    @mock.patch.object(ARDUINO.subprocess, "run")
    def test_arduino_compile_retries_only_bootstrap_failure(
        self, run: mock.Mock, sleep: mock.Mock
    ) -> None:
        run.side_effect = (
            subprocess.CompletedProcess(
                args=(), returncode=1, stdout="Download failed: temporary network error"
            ),
            subprocess.CompletedProcess(args=(), returncode=0, stdout="compiled"),
        )
        code, output = ARDUINO.run(("arduino-cli", "compile", "Blink"))
        self.assertEqual((code, output), (0, "compiled"))
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(2)

        run.reset_mock()
        run.side_effect = None
        sleep.reset_mock()
        run.return_value = subprocess.CompletedProcess(
            args=(), returncode=1, stdout="source.cpp: error: bad API"
        )
        with self.assertRaises(ARDUINO.SmokeFailure):
            ARDUINO.run(("arduino-cli", "compile", "Broken"))
        self.assertEqual(run.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
