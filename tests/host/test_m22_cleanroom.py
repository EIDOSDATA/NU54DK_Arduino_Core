#!/usr/bin/env python3
"""! @brief M22 same-PC clean-room의 격리와 안전 cleanup 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
PATH = REPOSITORY / "tools" / "release" / "m22_cleanroom.py"
SPEC = importlib.util.spec_from_file_location("m22_cleanroom", PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"M22 clean-room을 읽지 못했습니다: {PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M22CleanroomTests(unittest.TestCase):
    """! @brief 환경 누출·공개 index·marker/reparse cleanup을 시험합니다. """

    def setUp(self) -> None:
        """! @brief exact run leaf와 외부 evidence fixture를 만듭니다. """

        self.temporary = tempfile.TemporaryDirectory(prefix="nu54-m22-cleanroom-")
        self.base = Path(self.temporary.name)
        self.parent = self.base / "parent"
        self.parent.mkdir()
        self.run_id = "m22-20260901T120000Z-deadbeef"
        self.run = self.parent / self.run_id
        self.run.mkdir()
        self.evidence = self.base / "outside" / "evidence.json"
        self.evidence.parent.mkdir()
        self.evidence.write_text("{}\n", encoding="utf-8")
        self.token = "1" * 64

    def tearDown(self) -> None:
        """! @brief 남은 임시 fixture를 정리합니다. """

        self.temporary.cleanup()

    def marker(self, *, status: str = "ready-to-clean") -> None:
        """! @brief 현재 evidence byte에 묶인 cleanup marker를 씁니다. """

        MODULE.write_json(
            self.run / MODULE.MARKER_NAME,
            {
                "schema_version": 1,
                "run_id": self.run_id,
                "cleanup_token": self.token,
                "status": status,
                "evidence_path": str(self.evidence.resolve()),
                "evidence_sha256": MODULE.file_sha256(self.evidence),
            },
        )

    def test_environment_rehomes_every_mutable_root(self) -> None:
        """! @brief 원래 Arduino15/NCS/PATH를 상속하지 않고 run leaf로 재배치합니다. """

        inherited = {
            "SystemRoot": r"C:\Windows",
            "USERPROFILE": r"C:\Users\real",
            "LOCALAPPDATA": r"C:\Users\real\AppData\Local",
            "PATH": r"C:\ncs\toolchain;C:\secret",
            "NUCODE_NCS_ROOT": r"C:\ncs\v3.4.0",
        }
        environment = MODULE.isolated_environment(self.run, inherited)
        run_key = MODULE.path_key(self.run.resolve())
        for name in (
            "USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP",
            "NUCODE_NCS_ROOT", "NUCODE_TOOLCHAIN_ROOT",
            "NUCODE_PREREQUISITE_STATE_ROOT", "NUCODE_BUILD_CACHE_ROOT",
            "ARDUINO_DIRECTORIES_DATA", "ARDUINO_DIRECTORIES_DOWNLOADS",
            "ARDUINO_DIRECTORIES_USER",
        ):
            self.assertTrue(MODULE.path_key(environment[name]).startswith(run_key + "/"), name)
        self.assertNotIn("secret", environment["PATH"].casefold())
        self.assertNotIn(r"C:\ncs".casefold(), environment["PATH"].casefold())

    def test_layout_does_not_precreate_nordic_install_leaves(self) -> None:
        """! @brief Nordic SDK와 Toolchain 설치 대상 leaf를 미리 만들지 않습니다. """

        run = self.parent / "layout-fixture"
        paths = MODULE.layout(run)
        MODULE.prepare_layout(paths)
        self.assertTrue(paths["ncs_base"].is_dir())
        self.assertTrue(paths["state"].is_dir())
        self.assertFalse(paths["ncs"].exists())
        self.assertFalse(paths["toolchain"].exists())
        paths["unexpected"] = run / "unexpected"
        with self.assertRaisesRegex(MODULE.CleanroomFailure, "allowlist"):
            MODULE.prepare_layout(paths)

    def test_runner_binding_requires_exact_release_commit_and_bytes(self) -> None:
        """! @brief clean-room runner가 exact plan commit과 byte에 묶이는지 확인합니다. """

        runner = self.base / "runner.py"
        runner.write_text("fixture\n", encoding="utf-8")
        revision = "a" * 40
        value = MODULE.validate_runner_binding(
            runner_revision=revision,
            core_revision=revision,
            runner_sha256=MODULE.file_sha256(runner),
            plan_sha256="b" * 64,
            runner_path=runner,
        )
        self.assertEqual(value["revision"], revision)
        with self.assertRaisesRegex(MODULE.CleanroomFailure, "runner"):
            MODULE.validate_runner_binding(
                runner_revision="c" * 40,
                core_revision=revision,
                runner_sha256=MODULE.file_sha256(runner),
                plan_sha256="b" * 64,
                runner_path=runner,
            )

    def test_layout_rejects_preexisting_nordic_install_leaf(self) -> None:
        """! @brief Nordic 설치 대상 leaf가 먼저 생기면 즉시 중단합니다. """

        for name in ("ncs", "toolchain"):
            with self.subTest(name=name):
                run = self.parent / f"preexisting-{name}"
                paths = MODULE.layout(run)
                paths[name].mkdir(parents=True)
                with self.assertRaisesRegex(MODULE.CleanroomFailure, "installer"):
                    MODULE.prepare_layout(paths)

    def test_rc_index_requires_exact_public_asset_identity(self) -> None:
        """! @brief 공개 RC URL/hash/size가 plan과 다르면 설치 전에 차단합니다. """

        digest = "a" * 64
        document = {
            "packages": [{
                "name": "nucode",
                "platforms": [{
                    "version": MODULE.VERSION,
                    "url": (
                        f"https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/{MODULE.TAG}/"
                        f"nucode-nu54dk-zephyr-{MODULE.VERSION}.zip"
                    ),
                    "checksum": f"SHA-256:{digest}",
                    "size": "123",
                }],
            }]
        }
        self.assertEqual(
            MODULE.validate_rc_index(document, archive_sha256=digest, archive_size=123)["version"],
            MODULE.VERSION,
        )
        document["packages"][0]["platforms"][0]["url"] = "https://example.invalid/archive.zip"
        with self.assertRaisesRegex(MODULE.CleanroomFailure, "URL/hash/size"):
            MODULE.validate_rc_index(document, archive_sha256=digest, archive_size=123)

    def test_cleanup_removes_only_exact_leaf_and_preserves_evidence(self) -> None:
        """! @brief marker와 외부 hash 확인 뒤 exact run leaf 하나만 제거합니다. """

        (self.run / "nested").mkdir()
        (self.run / "nested" / "artifact.txt").write_text("fixture\n", encoding="utf-8")
        sibling = self.parent / "keep-me"
        sibling.mkdir()
        self.marker()
        MODULE.safe_cleanup_run(self.parent, self.run, self.run_id, self.token, self.evidence)
        self.assertFalse(self.run.exists())
        self.assertTrue(sibling.is_dir())
        self.assertTrue(self.evidence.is_file())

    def test_cleanup_removes_windows_readonly_file_inside_exact_leaf(self) -> None:
        """! @brief 격리 NCS Git object와 같은 Windows 읽기 전용 파일도 안전하게 제거합니다. """

        readonly = self.run / "objects" / "pack" / "fixture.pack"
        readonly.parent.mkdir(parents=True)
        readonly.write_bytes(b"fixture\n")
        readonly.chmod(stat.S_IREAD)
        self.marker()
        MODULE.safe_cleanup_run(self.parent, self.run, self.run_id, self.token, self.evidence)
        self.assertFalse(self.run.exists())
        self.assertTrue(self.evidence.is_file())

    def test_readonly_retry_rejects_path_outside_exact_leaf(self) -> None:
        """! @brief 읽기 전용 복구 callback이 exact run leaf 밖 경로를 거부합니다. """

        outside = self.base / "outside-readonly.txt"
        outside.write_text("fixture\n", encoding="utf-8")
        outside.chmod(stat.S_IREAD)
        try:
            with self.assertRaisesRegex(MODULE.CleanroomFailure, "밖"):
                MODULE.retry_readonly_cleanup(
                    lambda _path: None,
                    str(outside),
                    PermissionError("fixture"),
                    self.run,
                )
        finally:
            outside.chmod(stat.S_IWRITE)

    def test_cleanup_rejects_parent_wrong_token_and_changed_evidence(self) -> None:
        """! @brief broad target, token mismatch, evidence 변경을 모두 fail-closed 처리합니다. """

        self.marker()
        with self.assertRaises(MODULE.CleanroomFailure):
            MODULE.validate_cleanup_target(
                self.parent, self.parent, self.run_id, self.token, self.evidence
            )
        with self.assertRaisesRegex(MODULE.CleanroomFailure, "marker"):
            MODULE.validate_cleanup_target(
                self.parent, self.run, self.run_id, "wrong", self.evidence
            )
        self.evidence.write_text('{"changed":true}\n', encoding="utf-8")
        with self.assertRaisesRegex(MODULE.CleanroomFailure, "marker"):
            MODULE.validate_cleanup_target(
                self.parent, self.run, self.run_id, self.token, self.evidence
            )

    def test_uid_and_user_path_are_redacted(self) -> None:
        """! @brief 외부 log에 probe UID와 실제 Windows 사용자명이 남지 않습니다. """

        uid = "ABCDEF0123456789"
        redacted = MODULE.redact_text(
            f"probe={uid} C:\\Users\\eidos\\AppData\\Local", (uid,)
        )
        self.assertNotIn(uid, redacted)
        self.assertNotIn("eidos", redacted)

    def test_dry_run_contract_has_no_side_effect_and_no_uid_field(self) -> None:
        """! @brief 실제 설치 전 exact URL·격리·수명주기·cleanup 정책을 고정합니다. """

        contract = MODULE.dry_run_contract(
            parent=self.parent,
            run_id=self.run_id,
            index_sha256="a" * 64,
            archive_sha256="b" * 64,
            archive_size=123,
        )
        self.assertEqual(contract["public_index"]["url"], MODULE.RC_INDEX_URL)
        self.assertTrue(contract["isolation"]["all_mutable_roots_under_exact_run_leaf"])
        self.assertFalse(contract["probe"]["uid_recorded"])
        self.assertEqual(contract["cleanup"]["target"], "exact-run-leaf-only")
        self.assertFalse(contract["network_or_filesystem_mutation_performed"])

    def test_core_list_uses_installed_version_field(self) -> None:
        """! @brief Arduino CLI 1.5 JSON의 installed_version을 exact 비교합니다. """

        MODULE.assert_core_version(
            json.dumps({"platforms": [{"id": "nucode:zephyr", "installed_version": MODULE.VERSION}]}),
            MODULE.VERSION,
        )
        with self.assertRaisesRegex(MODULE.CleanroomFailure, "exact lifecycle"):
            MODULE.assert_core_version(
                json.dumps({"platforms": [{"id": "nucode:zephyr", "installed_version": "0.2.0"}]}),
                MODULE.VERSION,
            )

    def test_flash_log_binds_exact_uid_and_non_destructive_options(self) -> None:
        """! @brief 설치본 upload가 exact UID·HEX를 쓰고 erase/recover를 금지합니다. """

        uid = "fixture-probe"
        hex_path = self.run / "Blink.ino.hex"
        hex_path.write_bytes(b":00000001FF\n")
        log = self.run / "flash.log"
        command = (
            f"west flash -r pyocd --no-rebuild --dt-flash=n "
            f"--tool-opt=-Osmart_flash=false "
            f"--dev-id {uid} -d build"
        )
        log.write_text(
            "\n".join((
                "runner=pyocd",
                f"probe_id={uid}",
                f"hex={hex_path.resolve().as_posix()}",
                f"hex_sha256={MODULE.file_sha256(hex_path)}",
                "dt_flash=false",
                "smart_flash=false",
                "mass_erase_requested=false",
                "recover_requested=false",
                f"command={command}",
                "exit_code=0",
            )) + "\n",
            encoding="utf-8",
        )
        evidence = MODULE.validate_flash_log(log, probe_id=uid, hex_path=hex_path)
        self.assertFalse(evidence["mass_erase_requested"])
        self.assertFalse(evidence["probe_id_recorded"])
        with self.assertRaisesRegex(MODULE.CleanroomFailure, "runner/UID"):
            MODULE.validate_flash_log(log, probe_id="other-probe", hex_path=hex_path)


if __name__ == "__main__":
    unittest.main()
