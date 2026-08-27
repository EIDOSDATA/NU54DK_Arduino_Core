#!/usr/bin/env python3
"""! @brief M11 저장소 소유 고정 gate runner의 fail-closed 계약을 검증합니다. """

from __future__ import annotations

from contextlib import redirect_stderr
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY / "tools" / "release" / "run_fixed_gate.py"
SPECIFICATION = importlib.util.spec_from_file_location("nu54_test_fixed_gate", MODULE_PATH)
assert SPECIFICATION is not None and SPECIFICATION.loader is not None
MODULE = importlib.util.module_from_spec(SPECIFICATION)
sys.modules[SPECIFICATION.name] = MODULE
SPECIFICATION.loader.exec_module(MODULE)


class FixedGateRunnerTests(unittest.TestCase):
    """! @brief package identity와 exact scope의 음성 경계를 검증합니다. """

    CORE_REVISION = "1" * 40
    BOARD_REVISION = "2" * 40

    ## @brief M11 smoke 목록이 M9 호환 별칭을 중복 실행하지 않는지 검증합니다.
    def test_smoke_scope_uses_only_canonical_m9_name(self) -> None:
        self.assertEqual(
            MODULE.SMOKE_TESTS,
            (
                "blink",
                "library",
                "config",
                "error",
                "parallel",
                "m6",
                "m7",
                "m8",
                "m9",
                "m11",
            ),
        )

    ## @brief 최소 RC package tree와 외부 expected identity를 생성합니다.
    def make_platform(self, parent: Path) -> tuple[Path, dict[str, str]]:
        root = parent / f"nucode-nu54dk-zephyr-{MODULE.RELEASE_VERSION}"
        root.mkdir()
        payload = b"name=NUCODE\nversion=0.1.0-rc.1\n"
        payload_digest = hashlib.sha256(payload).hexdigest()
        runtime_digest = MODULE.runtime_payload_sha256(
            (("platform.txt", payload, 0o644),)
        )
        manifest = {
            "schema_version": 1,
            "version": MODULE.RELEASE_VERSION,
            "core_revision": self.CORE_REVISION,
            "board_revision": self.BOARD_REVISION,
            "runtime_payload_sha256": runtime_digest,
            "archive_root": root.name,
            "generated_metadata": list(MODULE.METADATA_FILES),
            "file_count": 1,
            "total_size": len(payload),
            "files": [
                {
                    "git_object": "3" * 40,
                    "mode": "0644",
                    "origin": "core",
                    "path": "platform.txt",
                    "sha256": payload_digest,
                    "size": len(payload),
                    "transformation": "platform-version",
                }
            ],
            "file_hashes": {"platform.txt": payload_digest},
        }
        (root / "platform.txt").write_bytes(payload)
        (root / "release-manifest.json").write_bytes(MODULE.canonical_json(manifest))
        (root / "sbom.spdx.json").write_text("{}\n", encoding="utf-8")
        (root / "license-inventory.json").write_text("{}\n", encoding="utf-8")
        (root / "THIRD_PARTY_NOTICES.md").write_text("notice\n", encoding="utf-8")
        checksum_paths = sorted(
            path.name for path in root.iterdir() if path.name != "CHECKSUMS.sha256"
        )
        checksums = "".join(
            f"{MODULE.file_sha256(root / name)}  {name}\n" for name in checksum_paths
        )
        (root / "CHECKSUMS.sha256").write_text(checksums, encoding="utf-8")
        expected = {
            "expected_version": MODULE.RELEASE_VERSION,
            "expected_core_revision": self.CORE_REVISION,
            "expected_board_revision": self.BOARD_REVISION,
            "expected_runtime_payload_sha256": runtime_digest,
            "expected_release_manifest_sha256": MODULE.file_sha256(
                root / "release-manifest.json"
            ),
        }
        return root, expected

    ## @brief 실제 byte와 모든 외부 expected identity가 같을 때만 승인합니다.
    def test_validate_platform_accepts_exact_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root, expected = self.make_platform(Path(temporary_name))
            identity = MODULE.validate_platform(root, **expected)
            self.assertEqual(
                identity["runtime_payload_sha256"],
                expected["expected_runtime_payload_sha256"],
            )

    ## @brief manifest를 유지한 payload 변조를 checksum 이전에도 거부합니다.
    def test_validate_platform_rejects_payload_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root, expected = self.make_platform(Path(temporary_name))
            (root / "platform.txt").write_bytes(b"tampered\n")
            with self.assertRaises(MODULE.FixedGateFailure):
                MODULE.validate_platform(root, **expected)

    ## @brief version만 다른 platform.txt가 같은 runtime fingerprint를 갖는지 검증합니다.
    def test_runtime_fingerprint_normalizes_only_platform_version(self) -> None:
        first = MODULE.runtime_payload_sha256(
            (("platform.txt", b"name=N\nversion=0.0.97\n", 0o644),)
        )
        second = MODULE.runtime_payload_sha256(
            (("platform.txt", b"name=N\nversion=0.1.0-rc.1\n", 0o644),)
        )
        changed = MODULE.runtime_payload_sha256(
            (("platform.txt", b"name=CHANGED\nversion=0.1.0-rc.1\n", 0o644),)
        )
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)

    ## @brief Twister가 정확한 네 suite의 build-only 성공만 승인하는지 검증합니다.
    def test_twister_result_requires_exact_build_only_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            report = root / "o" / "twister.json"
            report.parent.mkdir()
            document = {
                "environment": {
                    "zephyr_version": "ncs-v3.4.0",
                    "options": {
                        "testsuite_root": [
                            str(root / "p" / "tests" / "zephyr" / directory)
                            for directory, _scenario in MODULE.ZEPHYR_SUITES
                        ],
                        "platform": [MODULE.BOARD_TARGET],
                        "test": [
                            scenario for _directory, scenario in MODULE.ZEPHYR_SUITES
                        ],
                        "build_only": True,
                        "detailed_test_id": True,
                        "outdir": str(root / "o"),
                    },
                },
                "testsuites": [
                    {
                        "name": scenario,
                        "platform": MODULE.BOARD_TARGET,
                        "arch": "arm",
                        "status": "not run",
                        "testcases": [
                            {
                                "identifier": f"{scenario}.contract",
                                "status": "not run",
                                "reason": "Test was built only",
                            }
                        ],
                    }
                    for _directory, scenario in MODULE.ZEPHYR_SUITES
                ],
            }
            report.write_text(json.dumps(document), encoding="utf-8")
            MODULE.validate_twister_result(report)
            document["testsuites"].pop()
            report.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(MODULE.FixedGateFailure):
                MODULE.validate_twister_result(report)

    ## @brief 실행된 testcase PASS를 build-only 성공으로 오인하지 않는지 검증합니다.
    def test_twister_result_rejects_non_build_only_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            report = root / "o" / "twister.json"
            report.parent.mkdir()
            document = {
                "environment": {
                    "zephyr_version": "ncs-v3.4.0",
                    "options": {
                        "testsuite_root": [
                            str(root / "p" / "tests" / "zephyr" / directory)
                            for directory, _scenario in MODULE.ZEPHYR_SUITES
                        ],
                        "platform": [MODULE.BOARD_TARGET],
                        "test": [
                            scenario for _directory, scenario in MODULE.ZEPHYR_SUITES
                        ],
                        "build_only": True,
                        "detailed_test_id": True,
                        "outdir": str(root / "o"),
                    },
                },
                "testsuites": [
                    {
                        "name": scenario,
                        "platform": MODULE.BOARD_TARGET,
                        "arch": "arm",
                        "status": "passed",
                        "testcases": [
                            {
                                "identifier": f"{scenario}.contract",
                                "status": "passed",
                            }
                        ],
                    }
                    for _directory, scenario in MODULE.ZEPHYR_SUITES
                ],
            }
            report.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(MODULE.FixedGateFailure):
                MODULE.validate_twister_result(report)

    ## @brief Twister 명령이 junction 없이 정확한 네 root와 scenario를 사용하는지 검증합니다.
    def test_zephyr_command_uses_short_non_junction_contract(self) -> None:
        root = Path("C:/Users/nu54ci/.z1")
        test_roots = tuple(
            root / "p" / "tests" / "zephyr" / directory
            for directory, _scenario in MODULE.ZEPHYR_SUITES
        )
        command = [
            str(value)
            for value in MODULE.zephyr_twister_command(
                python=root / "python.exe",
                twister=root / "twister",
                staged=root / "p",
                test_roots=test_roots,
                outdir=root / "o",
            )
        ]
        self.assertNotIn("--short-build-path", command)
        self.assertEqual(command.count("--ninja"), 1)
        self.assertEqual(command.count("--detailed-test-id"), 1)
        self.assertEqual(command.count("--testsuite-root"), len(MODULE.ZEPHYR_SUITES))
        self.assertEqual(command.count("--scenario"), len(MODULE.ZEPHYR_SUITES))
        roots = [
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--testsuite-root"
        ]
        scenarios = [
            command[index + 1]
            for index, value in enumerate(command)
            if value == "--scenario"
        ]
        self.assertEqual(roots, [str(path) for path in test_roots])
        self.assertEqual(
            scenarios,
            [scenario for _directory, scenario in MODULE.ZEPHYR_SUITES],
        )

    ## @brief 기존 slot은 보존하고 자신이 만든 다음 slot만 정리하는지 검증합니다.
    def test_short_workspace_preserves_existing_slot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            home = Path(temporary_name)
            existing = home / MODULE.ZEPHYR_SHORT_WORKSPACE_NAMES[0]
            existing.mkdir()
            marker = existing / "keep.txt"
            marker.write_text("keep\n", encoding="utf-8")
            expected = home / MODULE.ZEPHYR_SHORT_WORKSPACE_NAMES[1]
            with MODULE.short_zephyr_workspace(home, max_path_length=1024) as workspace:
                self.assertEqual(workspace, expected)
                (workspace / "owned.txt").write_text("owned\n", encoding="utf-8")
            self.assertFalse(expected.exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep\n")

    ## @brief 모든 짧은 slot이 이미 있으면 어느 것도 재사용하거나 삭제하지 않습니다.
    def test_short_workspace_rejects_exhausted_slots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            home = Path(temporary_name)
            markers: list[Path] = []
            for name in MODULE.ZEPHYR_SHORT_WORKSPACE_NAMES:
                slot = home / name
                slot.mkdir()
                marker = slot / "keep.txt"
                marker.write_text(name, encoding="utf-8")
                markers.append(marker)
            with self.assertRaises(MODULE.FixedGateFailure):
                with MODULE.short_zephyr_workspace(home, max_path_length=1024):
                    self.fail("소진된 slot에서 작업공간이 할당되었습니다.")
            self.assertTrue(all(marker.is_file() for marker in markers))

    ## @brief 긴 profile에서는 junction 없는 Twister를 시작하기 전에 실패하는지 검증합니다.
    def test_short_workspace_rejects_long_path_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            home = Path(temporary_name)
            with self.assertRaises(MODULE.FixedGateFailure):
                with MODULE.short_zephyr_workspace(home, max_path_length=8):
                    self.fail("경로 예산을 초과한 workspace가 할당되었습니다.")
            self.assertFalse(
                any((home / name).exists() for name in MODULE.ZEPHYR_SHORT_WORKSPACE_NAMES)
            )
        self.assertLessEqual(
            MODULE.ZEPHYR_WORKSPACE_MAX_PATH_LENGTH
            + MODULE.ZEPHYR_M3_INSTANCE_PREFIX_OVERHEAD
            + MODULE.ZEPHYR_M3_MAX_OBJECT_TAIL_LENGTH,
            MODULE.ZEPHYR_CMAKE_OBJECT_PATH_LIMIT,
        )

    ## @brief report가 실제 outdir와 다른 root를 주장하면 성공 결과도 거부합니다.
    def test_twister_result_binds_report_to_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            report = root / "o" / "twister.json"
            report.parent.mkdir()
            document = {
                "environment": {
                    "zephyr_version": "ncs-v3.4.0",
                    "options": {
                        "testsuite_root": [
                            str(root / "p" / "tests" / "zephyr" / directory)
                            for directory, _scenario in MODULE.ZEPHYR_SUITES
                        ],
                        "platform": [MODULE.BOARD_TARGET],
                        "test": [
                            scenario for _directory, scenario in MODULE.ZEPHYR_SUITES
                        ],
                        "build_only": True,
                        "detailed_test_id": True,
                        "outdir": str(root / "different" / "o"),
                    },
                },
                "testsuites": [
                    {
                        "name": scenario,
                        "platform": MODULE.BOARD_TARGET,
                        "arch": "arm",
                        "status": "not run",
                        "testcases": [
                            {
                                "identifier": f"{scenario}.contract",
                                "status": "not run",
                                "reason": "Test was built only",
                            }
                        ],
                    }
                    for _directory, scenario in MODULE.ZEPHYR_SUITES
                ],
            }
            report.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(MODULE.FixedGateFailure):
                MODULE.validate_twister_result(report)

    ## @brief 짧은 package 이름과 suite 상대경로 계약을 함께 보존하는지 검증합니다.
    def test_stage_zephyr_gate_tree_preserves_relative_core_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            platform, _expected = self.make_platform(root)
            destination = root / "workspace"
            destination.mkdir()
            staged, test_roots = MODULE.stage_zephyr_gate_tree(platform, destination)
            self.assertEqual(staged, destination / "p")
            self.assertEqual(
                test_roots,
                tuple(
                    destination / "p" / "tests" / "zephyr" / directory
                    for directory, _scenario in MODULE.ZEPHYR_SUITES
                ),
            )
            self.assertTrue(all((path / "testcase.yaml").is_file() for path in test_roots))
            self.assertEqual(
                (test_roots[0] / "../../..").resolve(),
                staged.resolve(),
            )

    ## @brief Windows Twister demangler shim이 고정 toolchain byte와 PATH를 쓰는지 검증합니다.
    def test_zephyr_environment_stages_fixed_demangler(self) -> None:
        if MODULE.os.name != "nt":
            self.skipTest("Windows 전용 M11 gate 계약입니다.")
        with tempfile.TemporaryDirectory() as temporary_name:
            root = Path(temporary_name)
            workspace = root / "workspace"
            workspace.mkdir()
            tool_bin = root / "toolchain" / "bin"
            tool_bin.mkdir(parents=True)
            compiler = tool_bin / "arm-zephyr-eabi-g++.exe"
            demangler = tool_bin / "arm-zephyr-eabi-c++filt.exe"
            compiler.write_bytes(b"compiler")
            demangler.write_bytes(b"demangler")
            environment = MODULE.zephyr_gate_environment(
                {
                    "compiler": compiler,
                    "environment": {"PATH": "existing-path"},
                },
                workspace,
            )
            shim = workspace / "x" / "c++filt.exe"
            self.assertEqual(shim.read_bytes(), b"demangler")
            self.assertEqual(
                environment["PATH"].split(MODULE.os.pathsep)[:2],
                [str(workspace / "x"), str(tool_bin.resolve())],
            )

    ## @brief public CLI가 임의 command tail을 받을 수 없음을 검증합니다.
    def test_parser_rejects_arbitrary_host_command(self) -> None:
        parser = MODULE.build_parser()
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(
                    (
                        "host",
                        "--repo-root",
                        str(REPOSITORY),
                        "python",
                        "-c",
                        "raise SystemExit(0)",
                    )
                )

    ## @brief runner를 소유하지 않은 다른 저장소 root를 명령 대상으로 사용할 수 없습니다.
    def test_main_rejects_different_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            with self.assertRaises(MODULE.FixedGateFailure):
                MODULE.main(("host", "--repo-root", temporary_name))


if __name__ == "__main__":
    unittest.main()
