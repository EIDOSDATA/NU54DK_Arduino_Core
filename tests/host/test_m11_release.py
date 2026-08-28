#!/usr/bin/env python3
"""! @brief M11 release candidate 자동화와 stable 공개 차단 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "tools" / "release" / "nu54_release.py"
SPEC = importlib.util.spec_from_file_location("nu54_release", MODULE_PATH)
assert SPEC and SPEC.loader
RELEASE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RELEASE
SPEC.loader.exec_module(RELEASE)


class M11ReleaseTests(unittest.TestCase):
    """! @brief 실제 RC package와 합성 실행 증거로 fail-closed release 계약을 시험합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        cls.commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
        cls.temporary = tempfile.TemporaryDirectory(prefix="nu54-m11-release-")
        cls.root = Path(cls.temporary.name)
        cls.artifact_root = cls.root / "artifacts"
        ## @note commit 전 shared worktree에서도 RC 구조를 시험하도록 과거 launcher의 한글 주석만
        ##       합성 fixture에서 제거합니다. 실제 통합 RC build는 commit된 ASCII source를 사용합니다.
        def fixture_windows_rewrite(data: bytes, _path: str) -> bytes:
            text = data.decode("utf-8").encode("ascii", "ignore").decode("ascii")
            normalized = text.replace("\r\n", "\n").replace("\r", "\n")
            return normalized.replace("\n", "\r\n").encode("ascii")

        with (
            mock.patch.object(RELEASE, "assert_source_state"),
            mock.patch.object(
                RELEASE.PACKAGE,
                "rewrite_windows_command_line_endings",
                side_effect=fixture_windows_rewrite,
            ),
        ):
            cls.paths = RELEASE.prepare_rc(
                REPO_ROOT, cls.artifact_root, "0.1.0-rc.2", cls.commit
            )
        cls.plan = RELEASE.validate_plan(cls.paths["plan"])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def evidence_path(self, name: str) -> Path:
        """! @brief 시험별 evidence 경로를 충돌 없이 반환합니다. """

        path = self.root / "evidence" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def run_pass_gate(self, gate_id: str, name: str) -> Path:
        """! @brief 빠른 PASS 명령으로 command evidence fixture를 만듭니다. """

        path = self.evidence_path(name)
        evidence, exit_code, contract = self.run_fixture_command(
            gate_id,
            path,
            [sys.executable, "-c", "print('M11_TEST_PASS')"],
            30,
        )
        if not hasattr(self, "fixture_contracts"):
            self.fixture_contracts: dict[Path, dict[str, object]] = {}
        self.fixture_contracts[path.resolve()] = contract
        self.assertEqual(exit_code, 0)
        self.assertEqual(evidence["status"], "passed")
        return path

    def run_fixture_command(
        self,
        gate_id: str,
        path: Path,
        command: list[str],
        timeout: int,
        source_state_side_effect: list[object] | None = None,
    ) -> tuple[dict[str, object], int, dict[str, object]]:
        """! @brief process 경계 시험에만 합성 명령을 주입하고 production API는 고정합니다. """

        contract: dict[str, object] = {
            "schema_version": 1,
            "gate_id": gate_id,
            "runner": {
                "path": "tests/fixture-runner.py",
                "git_object": "a" * 40,
                "sha256": "b" * 64,
            },
            "package": None,
            "arduino_cli": None,
            "command_template": [RELEASE.redact_text(value) for value in command],
            "scope": {"kind": "unit-test-process-fixture"},
        }
        with (
            mock.patch.object(
                RELEASE,
                "assert_source_state",
                side_effect=source_state_side_effect,
            ),
            mock.patch.object(
                RELEASE,
                "fixed_gate_invocation",
                return_value=(command, contract),
            ),
        ):
            evidence, exit_code = RELEASE.run_command_gate(
                REPO_ROOT,
                self.paths["plan"],
                gate_id,
                path,
                timeout,
            )
        return evidence, exit_code, contract

    def make_rc_hil_fixture(self, name: str) -> Path:
        """! @brief exact RC HIL JSON과 이를 참조하는 command evidence를 합성합니다. """

        evidence_path = self.evidence_path(name)
        result_path = evidence_path.with_suffix(".result.json")
        result = {
            "schema_version": 1,
            "milestone": "M11",
            "evidence_type": "rc-pyocd-hil",
            "status": "passed",
            "release": {
                "version": self.plan["version"],
                "core_revision": self.plan["core_revision"],
                "board_revision": self.plan["board_revision"],
                "runtime_payload_sha256": self.plan["runtime_payload_sha256"],
                "release_manifest_sha256": self.plan["artifacts"]["manifest"]["sha256"],
                "platform_tree_sha256": "d" * 64,
                "file_count": 42,
            },
            "platform": {"mode": "validated-extracted-rc", "staged_byte_exact": True},
            "sketch": {
                "repository_relative_path": "tests/arduino-cli/m8_upload/m8_upload.ino",
                "sha256": hashlib.sha256(
                    RELEASE.git_file_at_revision(
                        REPO_ROOT,
                        self.plan["core_revision"],
                        "tests/arduino-cli/m8_upload/m8_upload.ino",
                    )
                ).hexdigest(),
            },
            "arduino_cli": {"sha256": RELEASE.ARDUINO_CLI_SHA256},
            "build": {
                "fqbn": f"{RELEASE.M10_FQBN}:upload_probe=pyocd",
                "compile_seconds": 1.0,
                "manifest_sha256": "1" * 64,
                "hex_file_name": "zephyr.hex",
                "hex_sha256": "2" * 64,
                "hex_size": 1234,
            },
            "upload": {
                "runner": "pyocd",
                "attempts": 1,
                "smart_flash": False,
                "mass_erase_requested": False,
                "recover_requested": False,
                "flash_log_sha256": "3" * 64,
                "upload_seconds": 1.0,
                "hex_unchanged_after_upload": True,
            },
            "uart": {
                "port": "<redacted>",
                "candidate_count": 2,
                "ready_match_count": 1,
                "token": RELEASE.M11_READY_TOKEN,
                "ready": True,
                "transcript_bytes": 24,
                "transcript_sha256": "4" * 64,
                "timeout_seconds": 6.0,
            },
            "completed_at_utc": "2026-08-28T00:00:00+00:00",
        }
        result_path.write_bytes(RELEASE.canonical_json(result))
        hil_result = RELEASE.validate_rc_hil_result(result_path, self.plan)
        command = [
            sys.executable,
            "tests/hil/m8_upload.py",
            "--expected-core-revision",
            self.plan["core_revision"],
            "--expected-runtime-payload-sha256",
            self.plan["runtime_payload_sha256"],
        ]
        contract: dict[str, object] = {
            "schema_version": 1,
            "gate_id": "hil_rc_pyocd",
            "runner": {"path": "fixture", "git_object": "a" * 40, "sha256": "b" * 64},
            "package": None,
            "arduino_cli": None,
            "command_template": command,
            "scope": {"kind": "unit-test-rc-hil-fixture"},
        }
        log_path = evidence_path.with_suffix(".log")
        log_path.write_text("M8_UPLOAD_HIL_PASS\n", encoding="utf-8")
        evidence = {
            "schema_version": 1,
            "milestone": "M11",
            "evidence_type": "command-gate",
            "gate_id": "hil_rc_pyocd",
            "status": "passed",
            "plan_sha256": RELEASE.file_sha256(self.paths["plan"]),
            "release": RELEASE.release_binding(self.plan),
            "command_contract": contract,
            "started_at_utc": "2026-08-28T00:00:00+00:00",
            "completed_at_utc": "2026-08-28T00:00:01+00:00",
            "duration_seconds": 1.0,
            "command": command,
            "exit_code": 0,
            "timed_out": False,
            "log": {
                "file_name": log_path.name,
                "sha256": RELEASE.file_sha256(log_path),
                "size": log_path.stat().st_size,
                "redacted": True,
                "excerpt": "M8_UPLOAD_HIL_PASS\n",
            },
            "environment": {
                "os": "Windows",
                "os_release": "fixture",
                "machine": "AMD64",
                "python": "3.14",
            },
            "hil_result": hil_result,
        }
        evidence_path.write_bytes(RELEASE.canonical_json(evidence))
        if not hasattr(self, "fixture_contracts"):
            self.fixture_contracts: dict[Path, dict[str, object]] = {}
        self.fixture_contracts[evidence_path.resolve()] = contract
        return evidence_path

    def document_fixture(self) -> dict[str, Path]:
        """! @brief 필수 역할마다 서로 다른 exact-commit 문서를 배정합니다. """

        return {
            "readme": Path("README.md"),
            "license": Path("LICENSE"),
            "installation": Path("00_Docs/02_빌드 설계/03_Arduino_CLI_통합.md"),
            "api_matrix": Path("00_Docs/01_아두이노 코어 설계/04_Arduino_API_지원_범위.md"),
            "migration": Path("00_Docs/01_아두이노 코어 설계/01_저장소_폴더_구조.md"),
            "troubleshooting": Path("00_Docs/02_빌드 설계/05_업로드와_디버그.md"),
            "release_notes": Path("00_Docs/01_아두이노 코어 설계/02_구현_로드맵.md"),
            "known_issues": Path("00_Docs/03_펌웨어 설계/04_테스트와_검증.md"),
            "third_party_notices": Path("third_party/THIRD_PARTY_NOTICES.md"),
        }

    def record_documentation_fixture(self, path: Path) -> dict[str, object]:
        """! @brief shared dirty worktree와 무관하게 plan commit의 문서 blob을 시험합니다. """

        original_git_output = RELEASE.git_output

        def committed_checkout_hash(repo: Path, arguments: list[str]) -> str:
            if arguments[:2] == ["hash-object", "--path"]:
                relative = arguments[-1]
                return original_git_output(
                    repo, ["rev-parse", f"{self.plan['core_revision']}:{relative}"]
                )
            return original_git_output(repo, arguments)

        with (
            mock.patch.object(RELEASE, "assert_source_state"),
            mock.patch.object(RELEASE, "git_output", side_effect=committed_checkout_hash),
        ):
            return RELEASE.record_documentation_gate(
                REPO_ROOT,
                self.paths["plan"],
                path,
                self.document_fixture(),
            )

    def make_m10_fixture(self, *, clean: bool = True) -> tuple[Path, Path]:
        """! @brief RC archive에 정확히 묶인 M10 clean Windows evidence를 만듭니다. """

        safe_archives = {
            RELEASE.M10_SAFE_INITIAL_VERSION: {
                "file_name": RELEASE.PACKAGE.archive_filename(
                    RELEASE.M10_SAFE_INITIAL_VERSION
                ),
                "sha256": "4" * 64,
                "size": "700001",
                "core_revision": self.plan["core_revision"],
                "board_revision": self.plan["board_revision"],
                "runtime_payload_sha256": self.plan["runtime_payload_sha256"],
                "release_manifest_sha256": "5" * 64,
            },
            RELEASE.M10_SAFE_LATEST_VERSION: {
                "file_name": RELEASE.PACKAGE.archive_filename(
                    RELEASE.M10_SAFE_LATEST_VERSION
                ),
                "sha256": "6" * 64,
                "size": "700002",
                "core_revision": self.plan["core_revision"],
                "board_revision": self.plan["board_revision"],
                "runtime_payload_sha256": self.plan["runtime_payload_sha256"],
                "release_manifest_sha256": "7" * 64,
            },
        }
        step_names = (
            "preflight",
            "update_index",
            "install_initial",
            "board_details_initial",
            "blink_cold_compile",
            "blink_warm_compile",
            "probe_and_upload",
            "upgrade_latest",
            "downgrade_initial",
            "uninstall_preserves_ncs",
            "reinstall_latest",
        )
        steps = []
        for name in step_names:
            result: dict[str, object] = {}
            if name == "probe_and_upload":
                result = {
                    "attached": True,
                    "probe_count": 1,
                    "upload": "passed",
                    "upload_attempts": RELEASE.M11_PYOCD_UPLOAD_ATTEMPTS,
                }
            steps.append({"name": name, "status": "passed", "result": result})
        runner_sha256 = hashlib.sha256(
            RELEASE.git_file_at_revision(
                REPO_ROOT,
                self.plan["core_revision"],
                RELEASE.M10_TARGET_RUNNER_PATH,
            )
        ).hexdigest()
        target = {
            "schema_version": 2,
            "milestone": "M10",
            "run_id": "m10-m11-fixture",
            "status": "passed",
            "completed_at_utc": "2026-08-28T00:00:00+00:00",
            "configuration": {
                "index_url": RELEASE.M10_PREVIEW_INDEX_URL,
                "fqbn": RELEASE.M10_FQBN,
                "initial_version": RELEASE.M10_SAFE_INITIAL_VERSION,
                "latest_version": RELEASE.M10_SAFE_LATEST_VERSION,
                "ncs_version": self.plan["ncs_version"],
                "toolchain_bundle_id": self.plan["toolchain_bundle_id"],
                "require_probe": True,
                "index_sha256": "8" * 64,
                "target_runner_sha256": runner_sha256,
                "arduino_cli": {
                    "expected_version": RELEASE.ARDUINO_CLI_VERSION,
                    "expected_commit": RELEASE.ARDUINO_CLI_COMMIT,
                    "executable_sha256": RELEASE.ARDUINO_CLI_SHA256,
                },
                "archives": safe_archives,
            },
            "initial_environment": {
                "ncs_exists": not clean,
                "prerequisite_state_exists": False,
                "ready_marker_exists": False,
            },
            "steps": steps,
            "failure": None,
            "redaction": {"device_identifiers": True, "credentials": True},
        }
        target_path = self.evidence_path(f"m10-target-{'clean' if clean else 'dirty'}.json")
        target_path.write_bytes(RELEASE.canonical_json(target))
        target_hash = RELEASE.file_sha256(target_path)
        orchestrator = {
            "schema_version": 1,
            "milestone": "M10",
            "run_id": target["run_id"],
            "status": "passed",
            "remote_exit_code": 0,
            "public_index_sha256": target["configuration"]["index_sha256"],
            "public_index_url": RELEASE.M10_PREVIEW_INDEX_URL,
            "archives": target["configuration"]["archives"],
            "target_runner_sha256": runner_sha256,
            "expected_arduino_cli": {
                "version": RELEASE.ARDUINO_CLI_VERSION,
                "commit": RELEASE.ARDUINO_CLI_COMMIT,
                "sha256": RELEASE.ARDUINO_CLI_SHA256,
            },
            "target_evidence_sha256": target_hash,
        }
        orchestrator_path = self.evidence_path(
            f"m10-orchestrator-{'clean' if clean else 'dirty'}.json"
        )
        orchestrator_path.write_bytes(RELEASE.canonical_json(orchestrator))
        return target_path, orchestrator_path

    def test_01_rc_package_and_index_have_separate_identity(self) -> None:
        with self.assertRaisesRegex(RELEASE.PACKAGE.PackageError, "ASCII-only"):
            RELEASE.PACKAGE.rewrite_windows_command_line_endings(
                "rem 한글\n".encode("utf-8"), "fixture.cmd"
            )
        manifest = RELEASE.PACKAGE.validate_archive(
            self.paths["archive"],
            expected_version="0.1.0-rc.2",
            expected_commit=self.commit,
        )
        self.assertEqual(manifest["release_tag"], "v0.1.0-rc.2")
        self.assertEqual(self.paths["index"].name, RELEASE.PACKAGE.RC_INDEX_FILENAME)
        document = RELEASE.PACKAGE.validate_index(
            self.paths["index"], artifact_dir=self.artifact_root
        )
        self.assertEqual(document["packages"][0]["platforms"][0]["version"], "0.1.0-rc.2")
        self.assertIn("/releases/download/v0.1.0-rc.2/", manifest["release_url"])
        root = "nucode-nu54dk-zephyr-0.1.0-rc.2"
        with zipfile.ZipFile(self.paths["archive"], "r") as archive:
            packaged_manifest = json.loads(
                archive.read(f"{root}/release-manifest.json").decode("utf-8")
            )
            records = {record["path"]: record for record in packaged_manifest["files"]}
            scripts = [
                path
                for path in records
                if Path(path).suffix.casefold() in {".bat", ".cmd"}
            ]
            self.assertGreaterEqual(len(scripts), 2)
            for path in scripts:
                data = archive.read(f"{root}/{path}")
                self.assertTrue(data.isascii(), path)
                self.assertIn(b"\r\n", data, path)
                self.assertNotIn(b"\n", data.replace(b"\r\n", b""), path)
                self.assertEqual(records[path].get("transformation"), "windows-crlf")

    def test_02_stable_and_mixed_channels_are_fail_closed(self) -> None:
        with self.assertRaises(RELEASE.PACKAGE.PackageError):
            RELEASE.PACKAGE.build_package(REPO_ROOT, self.root / "stable", "0.1.0", self.commit)
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE.prepare_rc(REPO_ROOT, self.root / "stable", "0.1.0", self.commit)
        with self.assertRaises(RELEASE.PACKAGE.PackageError):
            RELEASE.PACKAGE.generate_index(
                self.artifact_root, ["0.0.93", "0.1.0-rc.2"]
            )

    def test_03_plan_binds_all_artifacts_and_human_boundary(self) -> None:
        plan = RELEASE.validate_plan(self.paths["plan"])
        self.assertEqual(plan["core_revision"], self.commit)
        self.assertEqual(plan["required_gates"], list(RELEASE.REQUIRED_GATES))
        self.assertFalse(plan["publication_boundary"]["stable_publication_allowed"])
        self.assertEqual(
            plan["publication_boundary"]["legal_review"], "required-human-approval"
        )
        self.assertEqual(
            plan["validation_scope"]["boards_manager_backend"]["version"],
            "1.5.2-rc.1",
        )
        self.assertEqual(
            plan["validation_scope"]["boards_manager_backend"][
                "m10_safe_preview_lifecycle"
            ],
            ["0.0.96", "0.0.97"],
        )
        self.assertFalse(plan["validation_scope"]["arduino_ide_gui"]["validated"])
        self.assertFalse(
            plan["validation_scope"]["arduino_ide_gui"]["pass_inference_allowed"]
        )
        for record in plan["artifacts"].values():
            self.assertRegex(record["sha256"], r"^[0-9a-f]{64}$")

    def test_04_plan_rejects_tampered_artifact(self) -> None:
        tampered_root = self.root / "tampered-plan"
        shutil.copytree(self.artifact_root, tampered_root)
        archive = tampered_root / self.plan["artifacts"]["archive"]["file_name"]
        archive.write_bytes(archive.read_bytes() + b"tampered")
        with self.assertRaisesRegex(RELEASE.ReleaseError, "byte identity"):
            RELEASE.validate_plan(tampered_root / "m11-rc-plan.json")

    def test_05_command_gate_redacts_output_and_binds_plan(self) -> None:
        evidence_path = self.evidence_path("host-redaction.json")
        command = [
            "{python}",
            "-c",
            "print('token=supersecret 0123456789abcdef0123456789abcdef')",
        ]
        expanded = [sys.executable if value == "{python}" else value for value in command]
        evidence, exit_code, contract = self.run_fixture_command(
            "host_regression", evidence_path, expanded, 30
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(evidence["plan_sha256"], RELEASE.file_sha256(self.paths["plan"]))
        log_path = evidence_path.with_suffix(".log")
        log = log_path.read_text(encoding="utf-8")
        self.assertNotIn("supersecret", log)
        self.assertNotIn("0123456789abcdef", log)
        self.assertIn("<redacted>", log)
        with mock.patch.object(RELEASE, "fixed_gate_contract", return_value=contract):
            RELEASE.validate_gate_evidence(self.paths["plan"], self.plan, evidence_path)

    def test_06_failed_command_never_becomes_pass_evidence(self) -> None:
        evidence_path = self.evidence_path("host-failed.json")
        evidence, exit_code, _ = self.run_fixture_command(
            "host_regression",
            evidence_path,
            [sys.executable, "-c", "raise SystemExit(7)"],
            30,
        )
        self.assertEqual(exit_code, 7)
        self.assertEqual(evidence["status"], "failed")
        self.assertEqual(evidence["exit_code"], 7)

    def test_07_extracted_package_placeholder_points_to_fixed_rc(self) -> None:
        evidence_path = self.evidence_path("archive-command.json")
        program = (
            "import json, pathlib, sys; "
            "p=pathlib.Path(sys.argv[1]); "
            "m=json.loads((p/'release-manifest.json').read_text(encoding='utf-8')); "
            "raise SystemExit(0 if m['version']=='0.1.0-rc.2' else 9)"
        )
        def package_fixture(
            _repo: Path,
            _plan: dict[str, object],
            _gate: str,
            platform_root: Path | None,
            _workspace: Path,
            _cli: Path | None,
            _serial: str,
        ) -> tuple[list[str], dict[str, object]]:
            self.assertIsNotNone(platform_root)
            command = [sys.executable, "-c", program, str(platform_root)]
            contract = {
                "schema_version": 1,
                "gate_id": "arduino_cli_fixed_package",
                "runner": {"path": "fixture", "git_object": "a" * 40, "sha256": "b" * 64},
                "package": None,
                "arduino_cli": None,
                "command_template": command,
                "scope": {"kind": "unit-test-package-fixture"},
            }
            return command, contract

        with (
            mock.patch.object(RELEASE, "assert_source_state"),
            mock.patch.object(RELEASE, "fixed_gate_invocation", side_effect=package_fixture),
        ):
            evidence, exit_code = RELEASE.run_command_gate(
                REPO_ROOT,
                self.paths["plan"],
                "arduino_cli_fixed_package",
                evidence_path,
                30,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(evidence["status"], "passed")

    def test_08_documentation_must_be_exact_committed_blob(self) -> None:
        evidence_path = self.evidence_path("documentation.json")
        evidence = self.record_documentation_fixture(evidence_path)
        self.assertEqual(
            [record["role"] for record in evidence["files"]],
            list(RELEASE.REQUIRED_DOCUMENT_ROLES),
        )
        self.assertEqual(evidence["status"], "passed")

        with mock.patch.object(RELEASE, "assert_source_state"):
            with self.assertRaisesRegex(RELEASE.ReleaseError, "불완전"):
                RELEASE.record_documentation_gate(
                    REPO_ROOT,
                    self.paths["plan"],
                    self.evidence_path("documentation-incomplete.json"),
                    {"license": Path("LICENSE")},
                )

    def test_09_m10_import_requires_clean_machine_and_safe_preview_generation(self) -> None:
        target, orchestrator = self.make_m10_fixture(clean=True)
        imported = RELEASE.import_m10_evidence(
            self.paths["plan"], target, self.evidence_path("m10-import"), orchestrator
        )
        self.assertEqual(set(imported), {"clean_windows", "hil_pyocd"})
        for gate_id, path in imported.items():
            evidence = RELEASE.validate_gate_evidence(self.paths["plan"], self.plan, path)
            self.assertEqual(evidence["gate_id"], gate_id)
            self.assertEqual(evidence["status"], "passed")

        dirty_target, dirty_orchestrator = self.make_m10_fixture(clean=False)
        with self.assertRaisesRegex(RELEASE.ReleaseError, "clean Windows"):
            RELEASE.import_m10_evidence(
                self.paths["plan"],
                dirty_target,
                self.evidence_path("m10-dirty-import"),
                dirty_orchestrator,
            )

    def test_10_finalize_reports_hold_when_required_gate_is_missing(self) -> None:
        output = self.evidence_path("incomplete-final.json")
        final, ready = RELEASE.finalize_evidence(
            self.paths["plan"], [self.paths["package_integrity_evidence"]], output
        )
        self.assertFalse(ready)
        self.assertEqual(final["status"], "hold")
        self.assertIn("host_regression", final["missing_required_gates"])
        self.assertFalse(final["human_approval_boundary"]["stable_publication_allowed"])

    def test_11_all_technical_gates_still_require_human_stable_approval(self) -> None:
        evidence_paths = [self.paths["package_integrity_evidence"]]
        evidence_paths.append(self.run_pass_gate("host_regression", "final-host.json"))
        evidence_paths.append(
            self.run_pass_gate("arduino_cli_fixed_package", "final-arduino.json")
        )
        evidence_paths.append(self.run_pass_gate("zephyr_regression", "final-zephyr.json"))
        evidence_paths.append(self.make_rc_hil_fixture("final-hil-rc-pyocd.json"))
        documentation = self.evidence_path("final-documentation.json")
        self.record_documentation_fixture(documentation)
        evidence_paths.append(documentation)
        target, orchestrator = self.make_m10_fixture(clean=True)
        imported = RELEASE.import_m10_evidence(
            self.paths["plan"], target, self.evidence_path("final-m10"), orchestrator
        )
        evidence_paths.extend(imported.values())
        output = self.evidence_path("complete-final.json")
        contracts_by_gate = {
            json.loads(path.read_text(encoding="utf-8"))["gate_id"]: self.fixture_contracts[
                path.resolve()
            ]
            for path in evidence_paths
            if path.resolve() in self.fixture_contracts
        }
        with mock.patch.object(
            RELEASE,
            "fixed_gate_contract",
            side_effect=lambda _repo, _plan, gate: contracts_by_gate[gate],
        ):
            final, ready = RELEASE.finalize_evidence(
                self.paths["plan"], evidence_paths, output
            )
        self.assertTrue(ready)
        self.assertEqual(final["status"], "ready-for-human-approval")
        self.assertTrue(final["technical_gates_passed"])
        self.assertFalse(final["human_approval_boundary"]["stable_publication_allowed"])
        self.assertEqual(
            final["human_approval_boundary"]["legal_review"], "pending-human-approval"
        )
        self.assertFalse(final["validation_scope"]["arduino_ide_gui"]["validated"])
        self.assertFalse(
            final["validation_scope"]["arduino_ide_gui"]["pass_inferred_from_backend"]
        )
        self.assertEqual(
            final["known_issues"][0]["id"],
            "M11-ARDUINO-IDE-GUI-NOT-INDEPENDENTLY-VALIDATED",
        )
        self.assertFalse(
            final["validation_scope"]["boards_manager_backend"][
                "release_candidate_direct_clean_install"
            ]
        )
        self.assertTrue(
            final["validation_scope"]["boards_manager_backend"][
                "release_candidate_direct_hil"
            ]
        )
        self.assertEqual(
            final["known_issues"][1]["id"],
            "M11-RC-CLEAN-WINDOWS-INHERITS-SAFE-PREVIEW",
        )

    def test_12_forged_evidence_type_is_rejected(self) -> None:
        forged = {
            "schema_version": 1,
            "milestone": "M11",
            "evidence_type": "file-gate",
            "gate_id": "clean_windows",
            "status": "passed",
            "plan_sha256": RELEASE.file_sha256(self.paths["plan"]),
            "release": RELEASE.release_binding(self.plan),
            "files": [],
        }
        path = self.evidence_path("forged.json")
        path.write_bytes(RELEASE.canonical_json(forged))
        with self.assertRaisesRegex(RELEASE.ReleaseError, "종류"):
            RELEASE.validate_gate_evidence(self.paths["plan"], self.plan, path)

    def test_13_documentation_cannot_be_replaced_by_a_command_gate(self) -> None:
        """! @brief 종료 코드 0인 임의 명령이 exact 문서 blob gate를 대신하지 못합니다. """

        with self.assertRaisesRegex(RELEASE.ReleaseError, "command로 실행할 수 없는"):
            RELEASE.run_command_gate(
                REPO_ROOT,
                self.paths["plan"],
                "documentation",
                self.evidence_path("documentation-command.json"),
                30,
            )

    def test_14_command_evidence_requires_redacted_log_and_full_schema(self) -> None:
        """! @brief log나 실행 field가 빠진 합성 PASS JSON을 finalize에서 거부합니다. """

        path = self.run_pass_gate("host_regression", "schema-source.json")
        document = json.loads(path.read_text(encoding="utf-8"))
        del document["log"]
        forged = self.evidence_path("schema-forged.json")
        forged.write_bytes(RELEASE.canonical_json(document))
        contract = self.fixture_contracts[path.resolve()]
        with (
            mock.patch.object(RELEASE, "fixed_gate_contract", return_value=contract),
            self.assertRaisesRegex(RELEASE.ReleaseError, "필수 field"),
        ):
            RELEASE.validate_gate_evidence(self.paths["plan"], self.plan, forged)

    def test_15_redaction_covers_bearer_json_and_github_environment_tokens(self) -> None:
        """! @brief 공개 log에 흔한 GitHub token 표기 변형을 모두 제거합니다. """

        original = (
            "Authorization: Bearer bearer-secret\n"
            '"token": "json-secret"\n'
            "GH_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz123456\n"
            "GITHUB_TOKEN=github_pat_abcdefghijklmnopqrstuvwxyz123456\n"
        )
        redacted = RELEASE.redact_text(original)
        for secret in (
            "bearer-secret",
            "json-secret",
            "ghp_abcdefghijklmnopqrstuvwxyz123456",
            "github_pat_abcdefghijklmnopqrstuvwxyz123456",
        ):
            self.assertNotIn(secret, redacted)
        self.assertGreaterEqual(redacted.count("<redacted>"), 4)

    def test_16_plan_and_archive_never_accept_an_empty_commit(self) -> None:
        """! @brief 빈 core revision으로 exact commit 비교를 우회하지 못합니다. """

        with self.assertRaises(RELEASE.PACKAGE.PackageError):
            RELEASE.PACKAGE.validate_archive(
                self.paths["archive"], expected_version="0.1.0-rc.2", expected_commit=""
            )
        tampered = self.root / "empty-core-plan"
        shutil.copytree(self.artifact_root, tampered)
        plan_path = tampered / "m11-rc-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["core_revision"] = ""
        plan_path.write_bytes(RELEASE.canonical_json(plan))
        with self.assertRaisesRegex(RELEASE.ReleaseError, "full Git commit"):
            RELEASE.validate_plan(plan_path)

    def test_17_documentation_evidence_is_rechecked_against_git_blob(self) -> None:
        """! @brief file evidence의 size·SHA·Git object를 finalize 시점에 다시 검증합니다. """

        path = self.evidence_path("docs-source.json")
        self.record_documentation_fixture(path)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["files"][0]["size"] += 1
        forged = self.evidence_path("docs-forged.json")
        forged.write_bytes(RELEASE.canonical_json(document))
        with self.assertRaisesRegex(RELEASE.ReleaseError, "exact Git blob"):
            RELEASE.validate_gate_evidence(self.paths["plan"], self.plan, forged)

    def test_18_imported_m10_gate_rechecks_frozen_raw_evidence(self) -> None:
        """! @brief import 뒤 원본 M10 JSON이 바뀌면 gate validation을 실패시킵니다. """

        target, orchestrator = self.make_m10_fixture(clean=True)
        output = self.evidence_path("m10-frozen-root")
        output.mkdir(parents=True, exist_ok=True)
        imported = RELEASE.import_m10_evidence(
            self.paths["plan"], target, output, orchestrator
        )
        source = output / "m10-target.source.json"
        source.write_bytes(source.read_bytes() + b" ")
        with self.assertRaises(RELEASE.ReleaseError):
            RELEASE.validate_gate_evidence(
                self.paths["plan"], self.plan, imported["clean_windows"]
            )

    def test_19_command_log_is_bounded_while_preserving_redaction(self) -> None:
        """! @brief 큰 command 출력도 공개 log 상한 안에서 정제해 기록합니다. """

        evidence_path = self.evidence_path("bounded-command.json")
        program = (
            "import os; "
            "os.write(1, b'x' * 4096); "
            "os.write(1, b'\\ntoken=bounded-secret\\n')"
        )
        with mock.patch.object(RELEASE, "MAX_COMMAND_LOG_BYTES", 1024):
            evidence, exit_code, contract = self.run_fixture_command(
                "host_regression",
                evidence_path,
                [sys.executable, "-c", program],
                30,
            )
        log_bytes = evidence_path.with_suffix(".log").read_bytes()
        self.assertEqual(exit_code, 0)
        self.assertEqual(evidence["status"], "passed")
        self.assertLessEqual(len(log_bytes), 1024)
        self.assertTrue(log_bytes.startswith(RELEASE.LOG_TRUNCATION_MARKER))
        self.assertNotIn(b"bounded-secret", log_bytes)
        self.assertIn(b"<redacted>", log_bytes)
        with (
            mock.patch.object(RELEASE, "MAX_COMMAND_LOG_BYTES", 1024),
            mock.patch.object(RELEASE, "fixed_gate_contract", return_value=contract),
        ):
            RELEASE.validate_gate_evidence(
                self.paths["plan"], self.plan, evidence_path
            )

        oversized_log = b"x" * 1025
        evidence_document = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence_document["log"]["size"] = len(oversized_log)
        evidence_document["log"]["sha256"] = hashlib.sha256(oversized_log).hexdigest()
        evidence_path.with_suffix(".log").write_bytes(oversized_log)
        evidence_path.write_bytes(RELEASE.canonical_json(evidence_document))
        with (
            mock.patch.object(RELEASE, "MAX_COMMAND_LOG_BYTES", 1024),
            mock.patch.object(RELEASE, "fixed_gate_contract", return_value=contract),
            self.assertRaisesRegex(RELEASE.ReleaseError, "redaction 계약"),
        ):
            RELEASE.validate_gate_evidence(
                self.paths["plan"], self.plan, evidence_path
            )

    def test_20_post_gate_source_failure_preserves_log_bound(self) -> None:
        """! @brief 실행 후 source 실패를 덧붙여도 공개 log byte 상한을 넘지 않습니다. """

        evidence_path = self.evidence_path("bounded-source-failure.json")
        source_error = RELEASE.ReleaseError("token=post-gate-secret")
        with mock.patch.object(RELEASE, "MAX_COMMAND_LOG_BYTES", 1024):
            evidence, exit_code, _ = self.run_fixture_command(
                "host_regression",
                evidence_path,
                [sys.executable, "-c", "import os; os.write(1, b'x' * 4096)"],
                30,
                [None, source_error],
            )
        log_bytes = evidence_path.with_suffix(".log").read_bytes()
        self.assertEqual(exit_code, 125)
        self.assertEqual(evidence["status"], "failed")
        self.assertLessEqual(len(log_bytes), 1024)
        self.assertNotIn(b"post-gate-secret", log_bytes)
        self.assertIn(b"<redacted>", log_bytes)

    def test_21_timeout_terminates_descendant_processes(self) -> None:
        """! @brief timeout 시 직접 자식뿐 아니라 command의 후손 process도 종료합니다. """

        evidence_path = self.evidence_path("timeout-tree.json")
        survivor = self.root / "timeout-descendant-survived.txt"
        child = (
            "import pathlib,sys,time; "
            "time.sleep(1.5); "
            "pathlib.Path(sys.argv[1]).write_text('survived', encoding='utf-8')"
        )
        parent = (
            "import subprocess,sys,time; "
            "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
            "time.sleep(30)"
        )
        evidence, exit_code, _ = self.run_fixture_command(
            "host_regression",
            evidence_path,
            [sys.executable, "-c", parent, child, str(survivor)],
            1,
        )
        time.sleep(2)
        self.assertEqual(exit_code, 124)
        self.assertEqual(evidence["status"], "failed")
        self.assertTrue(evidence["timed_out"])
        self.assertFalse(survivor.exists())

    def test_22_m10_followup_allows_only_ancestor_documentation_and_tests(self) -> None:
        """! @brief M10 이후 허용 경로만 바뀐 ancestor 이력을 수용합니다. """

        with (
            mock.patch.object(RELEASE, "git_is_ancestor", return_value=True),
            mock.patch.object(
                RELEASE,
                "git_output",
                return_value=(
                    "00_Docs/05_릴리스/릴리스.md\0"
                    "package_nucode_nu54dk_preview_index.json\0"
                    "tests/host/test_release.py\0"
                ),
            ),
        ):
            changed = RELEASE.validate_m10_followup_changes(
                REPO_ROOT, "1" * 40, "2" * 40
            )
        self.assertEqual(
            changed,
            [
                "00_Docs/05_릴리스/릴리스.md",
                "package_nucode_nu54dk_preview_index.json",
                "tests/host/test_release.py",
            ],
        )

        with (
            mock.patch.object(RELEASE, "git_is_ancestor", return_value=True),
            mock.patch.object(
                RELEASE,
                "git_output",
                return_value="cores/arduino/Arduino.h\0",
            ),
            self.assertRaisesRegex(RELEASE.ReleaseError, "허용되지 않은 source 변경"),
        ):
            RELEASE.validate_m10_followup_changes(REPO_ROOT, "1" * 40, "2" * 40)

        with (
            mock.patch.object(RELEASE, "git_is_ancestor", return_value=False),
            self.assertRaisesRegex(RELEASE.ReleaseError, "ancestor"),
        ):
            RELEASE.validate_m10_followup_changes(REPO_ROOT, "1" * 40, "2" * 40)

    def test_23_m10_runtime_payload_mismatch_is_rejected(self) -> None:
        """! @brief archive 이름과 commit을 맞춰도 runtime payload가 다르면 거부합니다. """

        target_path, orchestrator_path = self.make_m10_fixture(clean=True)
        target = json.loads(target_path.read_text(encoding="utf-8"))
        for identity in target["configuration"]["archives"].values():
            identity["runtime_payload_sha256"] = "f" * 64
        target_path.write_bytes(RELEASE.canonical_json(target))
        orchestrator = json.loads(orchestrator_path.read_text(encoding="utf-8"))
        orchestrator["archives"] = target["configuration"]["archives"]
        orchestrator["target_evidence_sha256"] = RELEASE.file_sha256(target_path)
        orchestrator_path.write_bytes(RELEASE.canonical_json(orchestrator))
        with self.assertRaisesRegex(RELEASE.ReleaseError, "runtime payload fingerprint"):
            RELEASE.validate_m10_source_evidence(
                self.plan, target_path, orchestrator_path
            )

    def test_24_imported_m10_records_runtime_provenance(self) -> None:
        """! @brief 가져온 gate가 M10/RC revision과 허용 diff를 동결합니다. """

        target, orchestrator = self.make_m10_fixture(clean=True)
        imported = RELEASE.import_m10_evidence(
            self.paths["plan"],
            target,
            self.evidence_path("m10-provenance"),
            orchestrator,
        )
        evidence = RELEASE.validate_gate_evidence(
            self.paths["plan"], self.plan, imported["clean_windows"]
        )
        source = evidence["source"]
        self.assertEqual(source["m10_source_revision"], self.plan["core_revision"])
        self.assertEqual(source["rc_source_revision"], self.plan["core_revision"])
        self.assertEqual(
            source["runtime_payload_sha256"], self.plan["runtime_payload_sha256"]
        )
        self.assertEqual(source["allowed_followup_changes"], [])

    def test_25_run_gate_cli_rejects_arbitrary_command_tail(self) -> None:
        """! @brief 종료 코드 0인 임의 argv를 public gate CLI에 주입할 수 없습니다. """

        arguments = [
            "run-gate",
            "--plan",
            str(self.paths["plan"]),
            "--gate",
            "host_regression",
            "--output",
            str(self.evidence_path("forged-tail.json")),
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(0)",
        ]
        with self.assertRaises(SystemExit):
            RELEASE.build_parser().parse_args(arguments)

    def test_26_fixed_gate_contract_pins_repo_runner_and_exact_scope(self) -> None:
        """! @brief gate 계약이 runner blob·archive·CLI·시험 범위를 모두 고정합니다. """

        runner = {"path": "runner.py", "git_object": "a" * 40, "sha256": "b" * 64}
        with mock.patch.object(RELEASE, "committed_runner_record", return_value=runner):
            arduino = RELEASE.fixed_gate_contract(
                REPO_ROOT, self.plan, "arduino_cli_fixed_package"
            )
            zephyr = RELEASE.fixed_gate_contract(
                REPO_ROOT, self.plan, "zephyr_regression"
            )
            hil = RELEASE.fixed_gate_contract(REPO_ROOT, self.plan, "hil_rc_pyocd")
        self.assertEqual(arduino["runner"], runner)
        self.assertEqual(
            arduino["arduino_cli"]["executable_sha256"], RELEASE.ARDUINO_CLI_SHA256
        )
        self.assertEqual(
            arduino["package"]["runtime_payload_sha256"],
            self.plan["runtime_payload_sha256"],
        )
        self.assertEqual(
            arduino["scope"]["scenarios"],
            ["blink", "library", "config", "error", "parallel", "m6", "m7", "m8", "m9", "m11"],
        )
        self.assertEqual(zephyr["scope"]["test_root"], "tests/zephyr")
        self.assertEqual(
            zephyr["scope"]["scenarios"],
            [
                "nucode.m3.runtime",
                "nucode.m4.api_contract",
                "nucode.m6.core_api",
                "nucode.m7.core_api",
            ],
        )
        self.assertTrue(zephyr["scope"]["build_only"])
        self.assertEqual(zephyr["scope"]["result_contract"], "built-not-run")
        self.assertTrue(zephyr["scope"]["detailed_test_id"])
        self.assertFalse(zephyr["scope"]["short_build_path"])
        self.assertEqual(hil["scope"]["upload_attempts"], 1)
        self.assertEqual(hil["scope"]["ready_token"], RELEASE.M11_READY_TOKEN)
        self.assertIn(self.plan["core_revision"], hil["command_template"])
        self.assertIn(self.plan["runtime_payload_sha256"], hil["command_template"])
        self.assertIn("{serial_port}", hil["command_template"])

    def test_27_rc_hil_result_byte_tamper_is_rejected(self) -> None:
        """! @brief 동결한 HIL result JSON의 사후 변경을 evidence checksum이 차단합니다. """

        path = self.make_rc_hil_fixture("hil-result-source.json")
        result_path = path.with_suffix(".result.json")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["build"]["hex_sha256"] = "9" * 64
        result_path.write_bytes(RELEASE.canonical_json(result))
        contract = self.fixture_contracts[path.resolve()]
        with (
            mock.patch.object(RELEASE, "fixed_gate_contract", return_value=contract),
            self.assertRaisesRegex(RELEASE.ReleaseError, "동결 HIL result"),
        ):
            RELEASE.validate_gate_evidence(self.paths["plan"], self.plan, path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
