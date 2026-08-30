#!/usr/bin/env python3
"""! @brief M17 외부 Adafruit library compile runner 계약을 검증합니다. """

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile


REPOSITORY = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY / "tools" / "ci" / "run_m17_external_arduino.py"
SPEC = importlib.util.spec_from_file_location("nu54_m17_external", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M17ExternalArduinoTests(unittest.TestCase):
    """! @brief 외부 archive pin과 안전한 압축 해제를 검증합니다. """

    def test_repository_lock_is_exact(self) -> None:
        """! @brief 저장소 lock이 승인한 세 tag·commit·SHA만 포함하는지 확인합니다. """
        document = MODULE.load_lock(MODULE.DEFAULT_LOCK)
        self.assertEqual(len(document["libraries"]), 3)
        self.assertEqual(
            {record["name"] for record in document["libraries"]},
            set(MODULE.EXPECTED_LIBRARIES),
        )

    @mock.patch.object(MODULE.subprocess, "run")
    def test_arduino_cli_exact_version_and_sha_are_recorded(self, run: mock.Mock) -> None:
        """! @brief shell 없이 실행한 exact 1.5.1과 executable SHA를 정규화합니다. """
        run.return_value = mock.Mock(
            returncode=0,
            stdout=(
                "arduino-cli  Version: 1.5.1 Commit: 01f3d4f2b "
                "Date: 2026-06-05T10:22:12Z\n"
            ),
        )
        with tempfile.TemporaryDirectory(prefix="nu54-m17-cli-") as temporary_name:
            cli = Path(temporary_name) / "arduino-cli.exe"
            cli.write_bytes(b"exact-cli-fixture")
            identity = MODULE.validate_arduino_cli(cli)
        self.assertEqual(identity["version"], "1.5.1")
        self.assertEqual(
            identity["executable_sha256"],
            hashlib.sha256(b"exact-cli-fixture").hexdigest(),
        )
        self.assertEqual(run.call_args.args[0][1], "version")
        self.assertIs(run.call_args.kwargs["shell"], False)

    @mock.patch.object(MODULE.subprocess, "run")
    def test_arduino_cli_rejects_wrong_or_ambiguous_version(self, run: mock.Mock) -> None:
        """! @brief 다른 version과 version token 중복을 fail-closed로 거부합니다. """
        with tempfile.TemporaryDirectory(prefix="nu54-m17-cli-") as temporary_name:
            cli = Path(temporary_name) / "arduino-cli.exe"
            cli.write_bytes(b"cli")
            for output in (
                "arduino-cli Version: 1.5.0 Commit: old Date: now",
                "arduino-cli Version: 1.5.1 Version: 1.5.1",
            ):
                with self.subTest(output=output):
                    run.return_value = mock.Mock(returncode=0, stdout=output)
                    with self.assertRaisesRegex(
                        MODULE.ExternalArduinoFailure, "exact pin"
                    ):
                        MODULE.validate_arduino_cli(cli)

    def test_arduino_cli_replacement_is_rejected(self) -> None:
        """! @brief compile 중 executable byte가 바뀌면 종료 검증에서 거부합니다. """
        with tempfile.TemporaryDirectory(prefix="nu54-m17-cli-") as temporary_name:
            cli = Path(temporary_name) / "arduino-cli.exe"
            cli.write_bytes(b"before")
            identity = {
                "version": "1.5.1",
                "executable_sha256": hashlib.sha256(b"before").hexdigest(),
            }
            cli.write_bytes(b"after")
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "SHA-256이 변경"):
                MODULE.verify_arduino_cli_unchanged(cli, identity)

    def test_lock_rejects_changed_checksum_and_duplicate_key(self) -> None:
        """! @brief checksum 변경과 중복 JSON key를 fail-closed로 거부합니다. """
        original = json.loads(MODULE.DEFAULT_LOCK.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="nu54-m17-lock-") as temporary_name:
            path = Path(temporary_name) / "lock.json"
            original["libraries"][0]["sha256"] = "0" * 64
            path.write_text(json.dumps(original), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "exact allowlist"):
                MODULE.load_lock(path)
            path.write_text('{"schema_version":1,"schema_version":1,"libraries":[]}', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "중복 JSON key"):
                MODULE.load_lock(path)

    def test_safe_extract_accepts_single_root(self) -> None:
        """! @brief 정상 archive에서 root를 제거한 library tree만 생성합니다. """
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("library-tag/library.properties", "name=Fixture\nversion=1.0.0\n")
            archive.writestr("library-tag/src/Fixture.cpp", "int fixture;\n")
        with tempfile.TemporaryDirectory(prefix="nu54-m17-zip-") as temporary_name:
            destination = Path(temporary_name) / "Fixture"
            MODULE.extract_archive(buffer.getvalue(), destination)
            self.assertTrue((destination / "library.properties").is_file())
            self.assertTrue((destination / "src" / "Fixture.cpp").is_file())

    def test_safe_extract_rejects_traversal(self) -> None:
        """! @brief 상위 경로를 쓰는 ZIP member를 거부합니다. """
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("library-tag/../../escape.txt", "escape")
        with tempfile.TemporaryDirectory(prefix="nu54-m17-zip-") as temporary_name:
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "안전하지"):
                MODULE.extract_archive(buffer.getvalue(), Path(temporary_name) / "Fixture")

    def test_safe_extract_rejects_windows_drive_unc_and_ads(self) -> None:
        """! @brief drive-relative·drive absolute·UNC·ADS ZIP 경로를 모두 거부합니다. """
        malicious = (
            "C:library/file.txt",
            "C:/library/file.txt",
            "//server/share/file.txt",
            "\\\\server\\share\\file.txt",
            "library-tag/file.txt:stream",
        )
        for member in malicious:
            with self.subTest(member=member):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as archive:
                    archive.writestr(member, "escape")
                with tempfile.TemporaryDirectory(prefix="nu54-m17-zip-") as temporary_name:
                    with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "안전하지"):
                        MODULE.extract_archive(
                            buffer.getvalue(), Path(temporary_name) / "Fixture"
                        )

    def test_contained_target_rejects_destination_escape(self) -> None:
        """! @brief 최종 resolve 결과가 destination 밖이면 추출 전에 거부합니다. """
        with tempfile.TemporaryDirectory(prefix="nu54-m17-contained-") as temporary_name:
            destination = Path(temporary_name) / "Fixture"
            destination.mkdir()
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "destination"):
                MODULE.contained_target(destination, MODULE.PurePosixPath("../escape.txt"))

    def test_download_checksum_contract_matches_lock(self) -> None:
        """! @brief lock SHA가 64자리이며 evidence에 사용할 수 있는 digest인지 확인합니다. """
        document = MODULE.load_lock(MODULE.DEFAULT_LOCK)
        encoded = MODULE.DEFAULT_LOCK.read_bytes()
        self.assertRegex(hashlib.sha256(encoded).hexdigest(), r"^[0-9a-f]{64}$")
        for record in document["libraries"]:
            self.assertRegex(record["sha256"], r"^[0-9a-f]{64}$")

    def test_arduino_library_compatibility_contract_is_present(self) -> None:
        """! @brief 외부 Arduino library가 요구하는 macro, Print와 정수 GPIO overload를 고정합니다. """
        template = (
            REPOSITORY / "tools" / "nu54-builder" / "templates" / "zephyr-app" / "CMakeLists.txt"
        ).read_text(encoding="utf-8")
        print_header = (REPOSITORY / "cores" / "arduino" / "Print.h").read_text(
            encoding="utf-8"
        )
        arduino_header = (REPOSITORY / "cores" / "arduino" / "Arduino.h").read_text(
            encoding="utf-8"
        )
        for definition in ("ARDUINO=10607", "ARDUINO_ARCH_ZEPHYR", "ARDUINO_NUCODE_NU54DK"):
            self.assertIn(definition, template)
        self.assertIn("#include <api/Print.h>", print_header)
        self.assertIn("using arduino::Print;", print_header)
        self.assertIn("using arduino::digitalWrite;", arduino_header)
        self.assertIn("using arduino::pinMode;", arduino_header)

    def test_compile_sketch_targets_lsm6ds3trc(self) -> None:
        """! @brief compile gate가 NU54DK 검증 대상 LSM6DS3TR-C를 직접 사용하는지 확인합니다. """
        sketch = (MODULE.SKETCH / "m17_adafruit_lsm6ds_compile.ino").read_text(
            encoding="utf-8"
        )
        self.assertIn("#include <Adafruit_LSM6DS3TRC.h>", sketch)
        self.assertIn("Adafruit_LSM6DS3TRC sensor;", sketch)

    def test_exact_checkout_rejects_dirty_core_or_board(self) -> None:
        """! @brief Core 또는 board의 미커밋 변경은 compile 전에 거부합니다. """
        core_root = str(MODULE.REPOSITORY.resolve()) + "\n"
        board_root = str(
            (MODULE.REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS").resolve()
        ) + "\n"
        gitlink = (
            f"160000 commit {'b' * 40}\tboard_package/NU54DK_Zephyr_DTS\n"
        )
        with mock.patch.object(MODULE, "expected_board_revision", return_value="b" * 40), mock.patch.object(MODULE, "git_revision", side_effect=["a" * 40]), mock.patch.object(MODULE, "git_output", side_effect=[core_root, " M file\n"]):
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "tracked 미커밋"):
                MODULE.validate_exact_checkout()
        with mock.patch.object(MODULE, "expected_board_revision", return_value="b" * 40), mock.patch.object(MODULE, "git_revision", side_effect=["a" * 40, "b" * 40]), mock.patch.object(MODULE, "git_output", side_effect=[core_root, "", "", gitlink, board_root, "?? file\n"]):
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "board checkout에 미커밋"):
                MODULE.validate_exact_checkout()

    def test_exact_checkout_rejects_gitlink_or_checkout_mismatch(self) -> None:
        """! @brief parent gitlink 또는 실제 board HEAD가 exact pin과 다르면 거부합니다. """
        core_root = str(MODULE.REPOSITORY.resolve()) + "\n"
        board_root = str(
            (MODULE.REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS").resolve()
        ) + "\n"
        wrong_gitlink = (
            f"160000 commit {'c' * 40}\tboard_package/NU54DK_Zephyr_DTS\n"
        )
        with mock.patch.object(MODULE, "expected_board_revision", return_value="b" * 40), mock.patch.object(MODULE, "git_revision", return_value="a" * 40), mock.patch.object(MODULE, "git_output", side_effect=[core_root, "", "", wrong_gitlink]):
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "gitlink"):
                MODULE.validate_exact_checkout()
        correct_gitlink = (
            f"160000 commit {'b' * 40}\tboard_package/NU54DK_Zephyr_DTS\n"
        )
        with mock.patch.object(MODULE, "expected_board_revision", return_value="b" * 40), mock.patch.object(MODULE, "git_revision", side_effect=["a" * 40, "c" * 40]), mock.patch.object(MODULE, "git_output", side_effect=[core_root, "", "", correct_gitlink, board_root]):
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "board checkout"):
                MODULE.validate_exact_checkout()

    def test_exact_checkout_allows_only_untracked_ci_output_root(self) -> None:
        """! @brief 기존 CI evidence는 허용하되 다른 untracked source는 거부합니다. """
        core_root = str(MODULE.REPOSITORY.resolve()) + "\n"
        board_root = str(
            (MODULE.REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS").resolve()
        ) + "\n"
        gitlink = (
            f"160000 commit {'b' * 40}\tboard_package/NU54DK_Zephyr_DTS\n"
        )
        output_root = MODULE.REPOSITORY / "m12-evidence"
        with mock.patch.object(MODULE, "expected_board_revision", return_value="b" * 40), mock.patch.object(MODULE, "git_revision", side_effect=["a" * 40, "b" * 40]), mock.patch.object(MODULE, "git_output", side_effect=[core_root, "", "m12-evidence/prior.json\0", gitlink, board_root, ""]):
            identity = MODULE.validate_exact_checkout((output_root,))
        self.assertEqual(identity["board_revision"], "b" * 40)
        with mock.patch.object(MODULE, "expected_board_revision", return_value="b" * 40), mock.patch.object(MODULE, "git_revision", return_value="a" * 40), mock.patch.object(MODULE, "git_output", side_effect=[core_root, "", "cores/arduino/new.cpp\0"]):
            with self.assertRaisesRegex(MODULE.ExternalArduinoFailure, "허용하지 않은 untracked"):
                MODULE.validate_exact_checkout((output_root,))


if __name__ == "__main__":
    unittest.main()
