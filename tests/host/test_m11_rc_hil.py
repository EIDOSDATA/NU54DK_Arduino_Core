#!/usr/bin/env python3
"""! @brief 해제된 M11 RC package의 pyOCD 1회 HIL 안전 계약을 검증합니다. """

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "tests" / "hil" / "nu54dk" / "m8_upload.py"
SPEC = importlib.util.spec_from_file_location("nu54_m11_rc_hil", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeSerialStream:
    """! @brief auto UART 판별 시험에 사용할 nonblocking serial stream입니다. """

    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)
        self.closed = False
        self.reset_called = False

    @property
    def in_waiting(self) -> int:
        """! @brief 다음 수신 block의 byte 수를 반환합니다. """

        return len(self.chunks[0]) if self.chunks else 0

    def reset_input_buffer(self) -> None:
        """! @brief 실제 포트와 같은 reset 호출 여부를 기록합니다. """

        self.reset_called = True

    def read(self, _size: int) -> bytes:
        """! @brief 준비된 block을 순서대로 반환합니다. """

        return self.chunks.pop(0) if self.chunks else b""

    def close(self) -> None:
        """! @brief 동시 open된 모든 후보가 정리되었음을 기록합니다. """

        self.closed = True


class FakeSerialModule:
    """! @brief port별 stream 또는 점유 오류를 제공하는 pySerial 대역입니다. """

    def __init__(self, streams: dict[str, FakeSerialStream], blocked: set[str] | None = None) -> None:
        self.streams = streams
        self.blocked = blocked or set()
        self.opened: list[str] = []

    def Serial(self, *, port: str, baudrate: int, timeout: float) -> FakeSerialStream:
        """! @brief 설정을 검증하고 지정 port를 엽니다. """

        if baudrate != 115200 or timeout != 0:
            raise AssertionError("auto UART는 115200 nonblocking이어야 합니다.")
        if port in self.blocked:
            raise OSError("occupied")
        self.opened.append(port)
        return self.streams[port]


class M11RcHilTests(unittest.TestCase):
    """! @brief RC root·build artifact·runner·UART를 fail-closed 방식으로 시험합니다. """

    def setUp(self) -> None:
        """! @brief 최소 exact RC platform fixture를 생성합니다. """

        self.temporary = tempfile.TemporaryDirectory(prefix="nu54-m11-rc-hil-")
        self.root = Path(self.temporary.name)
        self.version = "0.1.0-rc.2"
        self.core_revision = "a" * 40
        self.board_revision = "b" * 40
        self.runtime_payload_sha256 = ""
        self.platform = self.root / f"nucode-nu54dk-zephyr-{self.version}"
        self.platform.mkdir()
        self.write_rc_platform()

    def tearDown(self) -> None:
        """! @brief 시험별 임시 파일을 제거합니다. """

        self.temporary.cleanup()

    def write_rc_platform(self) -> None:
        """! @brief payload와 generated metadata가 서로 묶인 RC root를 기록합니다. """

        payload = {
            "boards.txt": b"nu54dk.name=NU54DK\n",
            "platform.txt": f"name=NU54DK\nversion={self.version}\n".encode("utf-8"),
        }
        for relative, data in payload.items():
            target = self.platform / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for name, data in {
            "sbom.spdx.json": b"{}\n",
            "license-inventory.json": b"{}\n",
            "THIRD_PARTY_NOTICES.md": b"fixture\n",
        }.items():
            (self.platform / name).write_bytes(data)
        records = []
        file_hashes = {}
        for relative in sorted(payload, key=lambda item: item.encode("utf-8")):
            data = payload[relative]
            digest = hashlib.sha256(data).hexdigest()
            records.append(
                {
                    "git_object": "c" * 40,
                    "mode": "0644",
                    "origin": "core",
                    "path": relative,
                    "sha256": digest,
                    "size": len(data),
                }
            )
            file_hashes[relative] = digest
        self.runtime_payload_sha256 = MODULE.runtime_payload_fingerprint(
            [
                (relative, payload[relative], "0644")
                for relative in sorted(payload, key=lambda item: item.encode("utf-8"))
            ]
        )
        manifest = {
            "schema_version": 1,
            "version": self.version,
            "core_revision": self.core_revision,
            "runtime_payload_sha256": self.runtime_payload_sha256,
            "board_revision": self.board_revision,
            "archive_root": self.platform.name,
            "generated_metadata": list(MODULE.RC_METADATA_FILES),
            "file_count": len(records),
            "total_size": sum(len(data) for data in payload.values()),
            "files": records,
            "file_hashes": file_hashes,
        }
        (self.platform / "release-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.write_internal_checksums()

    def write_internal_checksums(self) -> None:
        """! @brief fixture metadata의 현재 byte에 맞춰 내부 checksum을 갱신합니다. """

        checksum_paths = sorted(
            [path for path in self.platform.iterdir() if path.name != "CHECKSUMS.sha256"],
            key=lambda path: path.name.encode("utf-8"),
        )
        (self.platform / "CHECKSUMS.sha256").write_text(
            "".join(f"{MODULE.file_sha256(path)}  {path.name}\n" for path in checksum_paths),
            encoding="utf-8",
        )

    def make_build_manifest(
        self, build: Path, staged_platform: Path, sketch: Path
    ) -> tuple[Path, Path]:
        """! @brief exact RC build context와 HEX record fixture를 만듭니다. """

        build.mkdir(parents=True, exist_ok=True)
        zephyr_build = self.root / "persistent-cache" / "zephyr-build"
        zephyr_build.mkdir(parents=True, exist_ok=True)
        hex_path = build / "m8_upload.ino.hex"
        hex_path.write_bytes(b":020000040000FA\n:00000001FF\n")
        manifest_path = build / "m8_upload.ino.nu54-build.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": MODULE.ARTIFACT_MANIFEST_SCHEMA_VERSION,
                    "fqbn": f"{MODULE.FQBN}:upload_probe=pyocd",
                    "sysbuild": False,
                    "context": {
                        "schema_version": MODULE.SESSION_CONTEXT_SCHEMA_VERSION,
                        "state": "built",
                        "fqbn": f"{MODULE.FQBN}:upload_probe=pyocd",
                        "build_path": build.resolve().as_posix(),
                        "platform_root": staged_platform.resolve().as_posix(),
                        "sketch_root": sketch.resolve().as_posix(),
                        "zephyr_build_dir": zephyr_build.resolve().as_posix(),
                    },
                    "artifacts": {
                        "hex": {
                            "path": hex_path.resolve().as_posix(),
                            "sha256": MODULE.file_sha256(hex_path),
                            "size": hex_path.stat().st_size,
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return manifest_path, hex_path

    def test_validates_and_byte_exactly_stages_rc_platform(self) -> None:
        """! @brief 원본과 staged root가 같은 tree identity를 가져야 합니다. """

        identity = MODULE.validate_rc_platform(
            self.platform,
            self.version,
            self.core_revision,
            self.runtime_payload_sha256,
        )
        staged, staged_identity = MODULE.stage_rc_platform(
            self.platform,
            self.root / "user",
            self.version,
            self.core_revision,
            self.runtime_payload_sha256,
        )
        self.assertEqual(identity, staged_identity)
        self.assertEqual(staged.name, "zephyr")
        self.assertRegex(identity["platform_tree_sha256"], r"^[0-9a-f]{64}$")
        with self.assertRaisesRegex(MODULE.UploadHilFailure, "manifest identity"):
            MODULE.validate_rc_platform(
                self.platform,
                self.version,
                self.core_revision,
                "f" * 64,
            )

        manifest_path = self.platform / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["runtime_payload_sha256"] = "f" * 64
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.write_internal_checksums()
        with self.assertRaisesRegex(MODULE.UploadHilFailure, "실제 payload byte"):
            MODULE.validate_rc_platform(
                self.platform,
                self.version,
                self.core_revision,
                "f" * 64,
            )

    def test_argument_defaults_preserve_source_mode_and_force_one_rc_upload(self) -> None:
        """! @brief source mode 10회와 RC mode 1회 기본값을 분리해 보존합니다. """

        source = MODULE.parse_arguments([])
        rc = MODULE.parse_arguments(
            ["--rc-platform-root", str(self.platform)]
        )
        self.assertEqual(source.repetitions, 10)
        self.assertEqual(rc.repetitions, 1)
        self.assertEqual(rc.serial_port, "auto")
        with self.assertRaisesRegex(MODULE.UploadHilFailure, "정확히 1회"):
            MODULE.main(
                [
                    "--rc-platform-root",
                    str(self.platform),
                    "--repetitions",
                    "2",
                ]
            )

    def test_rejects_manifest_path_traversal_and_unexpected_file(self) -> None:
        """! @brief manifest traversal과 package 밖 추가 payload를 모두 거부합니다. """

        manifest_path = self.platform / "release-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"][0]["path"] = "../boards.txt"
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.UploadHilFailure, "상대 경로"):
            MODULE.validate_rc_platform(
                self.platform,
                self.version,
                self.core_revision,
                self.runtime_payload_sha256,
            )

        self.write_rc_platform()
        (self.platform / "unexpected.bin").write_bytes(b"unexpected")
        with self.assertRaisesRegex(MODULE.UploadHilFailure, "허용목록"):
            MODULE.validate_rc_platform(
                self.platform,
                self.version,
                self.core_revision,
                self.runtime_payload_sha256,
            )
        (self.platform / "unexpected.bin").unlink()
        (self.platform / "empty-unexpected-directory").mkdir()
        with self.assertRaisesRegex(MODULE.UploadHilFailure, "directory 집합"):
            MODULE.validate_rc_platform(
                self.platform,
                self.version,
                self.core_revision,
                self.runtime_payload_sha256,
            )
        for unsafe in ("boards.txt:stream", "CON.txt", "folder./file"):
            with self.assertRaises(MODULE.UploadHilFailure):
                MODULE.ensure_safe_relative_path(unsafe)

    def test_build_manifest_rejects_hex_outside_build_and_hash_change(self) -> None:
        """! @brief HEX path traversal과 compile 뒤 byte 변경을 거부합니다. """

        build = self.root / "build"
        staged = self.root / "staged"
        sketch = self.root / "sketch"
        staged.mkdir()
        sketch.mkdir()
        manifest_path, hex_path = self.make_build_manifest(build, staged, sketch)
        MODULE.validate_build_manifest(manifest_path, build, staged, sketch, "pyocd")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["schema_version"] = 1
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.UploadHilFailure, "기본 계약"):
            MODULE.validate_build_manifest(manifest_path, build, staged, sketch, "pyocd")

        manifest_path, hex_path = self.make_build_manifest(build, staged, sketch)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        outside = self.root / "outside.hex"
        outside.write_bytes(hex_path.read_bytes())
        manifest["artifacts"]["hex"]["path"] = outside.as_posix()
        manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.UploadHilFailure, "밖"):
            MODULE.validate_build_manifest(manifest_path, build, staged, sketch, "pyocd")

        manifest_path, hex_path = self.make_build_manifest(build, staged, sketch)
        hex_path.write_bytes(hex_path.read_bytes() + b"tampered")
        with self.assertRaisesRegex(MODULE.UploadHilFailure, "manifest"):
            MODULE.validate_build_manifest(manifest_path, build, staged, sketch, "pyocd")

    def test_flash_log_requires_one_safe_pyocd_upload(self) -> None:
        """! @brief exact HEX의 비파괴 pyOCD command 한 건만 승인합니다. """

        digest = "d" * 64
        log = self.root / "nu54-zephyr" / "logs" / "flash.log"
        log.parent.mkdir(parents=True)
        zephyr_build = self.root / "persistent-cache" / "zephyr-build"
        zephyr_build.mkdir(parents=True)
        hex_path = self.root / "firmware.hex"
        hex_path.write_bytes(b"hex")
        safe = (
            "started_at_utc=2026-08-28T00:00:00+00:00\n"
            "runner=pyocd\n"
            "probe_id=fixture-probe\n"
            f"hex={hex_path.resolve().as_posix()}\n"
            f"hex_sha256={digest}\n"
            "smart_flash=false\n"
            "mass_erase_requested=false\n"
            "recover_requested=false\n"
            "exit_code=0\n"
            f"command=west flash -d {zephyr_build.resolve().as_posix()} "
            "-r pyocd "
            "--no-rebuild --dev-id fixture-probe "
            "--tool-opt=-Osmart_flash=false\n"
        )
        log.write_text(safe, encoding="utf-8")
        result = MODULE.validate_pyocd_flash_log(log, digest, hex_path, zephyr_build)
        self.assertEqual(result["attempts"], 1)

        log.write_text(safe.replace("--no-rebuild", "--no-rebuild --erase"), encoding="utf-8")
        with self.assertRaisesRegex(MODULE.UploadHilFailure, "파괴 option"):
            MODULE.validate_pyocd_flash_log(log, digest, hex_path, zephyr_build)

        log.write_text(safe, encoding="utf-8")
        with mock.patch.object(MODULE, "MAX_FLASH_LOG_BYTES", len(safe.encode("utf-8")) - 1):
            with self.assertRaisesRegex(MODULE.UploadHilFailure, "허용 크기"):
                MODULE.validate_pyocd_flash_log(log, digest, hex_path, zephyr_build)

    def test_auto_uart_opens_all_candidates_and_selects_unique_token(self) -> None:
        """! @brief COM3·COM4를 동시에 열고 READY가 있는 하나만 승인합니다. """

        ports = [
            SimpleNamespace(device="COM3", vid=MODULE.DAPLINK_VID, pid=MODULE.DAPLINK_PID),
            SimpleNamespace(device="COM4", vid=MODULE.DAPLINK_VID, pid=MODULE.DAPLINK_PID),
        ]
        streams = {
            "COM3": FakeSerialStream([b"debug-only"]),
            "COM4": FakeSerialStream([b"prefix-" + MODULE.READY_TOKEN]),
        }
        serial_module = FakeSerialModule(streams)
        list_ports = SimpleNamespace(comports=lambda: ports)
        with (
            mock.patch.object(
                MODULE, "import_pyserial", return_value=(serial_module, list_ports)
            ),
            mock.patch.object(MODULE, "UART_AMBIGUITY_WINDOW_SECONDS", 0.0),
        ):
            transcript, candidate_count = MODULE.wait_for_ready_auto(1.0)
        self.assertEqual(serial_module.opened, ["COM3", "COM4"])
        self.assertEqual(candidate_count, 2)
        self.assertIn(MODULE.READY_TOKEN, transcript)
        self.assertTrue(all(stream.closed for stream in streams.values()))

    def test_auto_uart_rejects_ambiguous_or_occupied_candidates(self) -> None:
        """! @brief READY 중복과 후보 port 점유를 모두 fail-closed 처리합니다. """

        ports = [
            SimpleNamespace(device="COM3", vid=MODULE.DAPLINK_VID, pid=MODULE.DAPLINK_PID),
            SimpleNamespace(device="COM4", vid=MODULE.DAPLINK_VID, pid=MODULE.DAPLINK_PID),
        ]
        list_ports = SimpleNamespace(comports=lambda: ports)
        ambiguous_streams = {
            "COM3": FakeSerialStream([MODULE.READY_TOKEN]),
            "COM4": FakeSerialStream([MODULE.READY_TOKEN]),
        }
        with mock.patch.object(
            MODULE,
            "import_pyserial",
            return_value=(FakeSerialModule(ambiguous_streams), list_ports),
        ):
            with self.assertRaisesRegex(MODULE.UploadHilFailure, "둘 이상의"):
                MODULE.wait_for_ready_auto(1.0)

        occupied_streams = {
            "COM3": FakeSerialStream([b""]),
            "COM4": FakeSerialStream([MODULE.READY_TOKEN]),
        }
        serial_module = FakeSerialModule(occupied_streams, blocked={"COM4"})
        with mock.patch.object(
            MODULE, "import_pyserial", return_value=(serial_module, list_ports)
        ):
            with self.assertRaisesRegex(MODULE.UploadHilFailure, "동시에 점유"):
                MODULE.wait_for_ready_auto(1.0)
        self.assertTrue(occupied_streams["COM3"].closed)

    def test_rc_main_compiles_uploads_once_and_writes_identity_evidence(self) -> None:
        """! @brief RC root→compile→pyOCD 1회→UART 순서를 JSON evidence에 고정합니다. """

        cli = self.root / "arduino-cli.exe"
        cli.write_bytes(b"arduino-cli-fixture")
        workspace = self.root / "workspace"
        calls: list[str] = []

        def fake_run(
            command: list[Path | str], *, timeout_seconds: int
        ) -> tuple[int, str, float]:
            self.assertGreater(timeout_seconds, 0)
            operation = str(command[1])
            calls.append(operation)
            build = Path(command[command.index("--build-path") + 1])
            sketch = Path(command[-1])
            staged = build.parent / "user" / "hardware" / "nucode" / "zephyr"
            if operation == "compile":
                self.make_build_manifest(build, staged, sketch)
                return 0, "compile passed", 0.1
            digest = MODULE.file_sha256(build / "m8_upload.ino.hex")
            manifest = json.loads(
                (build / "m8_upload.ino.nu54-build.json").read_text(encoding="utf-8")
            )
            zephyr_build = Path(manifest["context"]["zephyr_build_dir"])
            flash_log = build / "nu54-zephyr" / "logs" / "flash.log"
            flash_log.parent.mkdir(parents=True, exist_ok=True)
            flash_log.write_text(
                "started_at_utc=2026-08-28T00:00:00+00:00\n"
                "runner=pyocd\n"
                "probe_id=fixture-probe\n"
                f"hex={(build / 'm8_upload.ino.hex').resolve().as_posix()}\n"
                f"hex_sha256={digest}\n"
                "smart_flash=false\n"
                "mass_erase_requested=false\n"
                "recover_requested=false\n"
                "exit_code=0\n"
                f"command=west flash -d {zephyr_build.resolve().as_posix()} "
                "-r pyocd --no-rebuild --dev-id fixture-probe "
                "--tool-opt=-Osmart_flash=false\n",
                encoding="utf-8",
            )
            return 0, "NU54_UPLOAD_PASS runner=pyocd probe=redacted", 0.2

        with (
            mock.patch.object(MODULE, "run", side_effect=fake_run),
            mock.patch.object(
                MODULE,
                "collect_ready_evidence",
                return_value=(
                    MODULE.READY_TOKEN,
                    {
                        "selection": "auto-daplink-token",
                        "candidate_count": 2,
                        "ready_match_count": 1,
                    },
                ),
            ),
            mock.patch.object(
                MODULE,
                "committed_file_sha256",
                return_value="d" * 64,
            ),
        ):
            result = MODULE.main(
                [
                    "--cli",
                    str(cli),
                    "--repository",
                    str(REPO_ROOT),
                    "--workspace",
                    str(workspace),
                    "--rc-platform-root",
                    str(self.platform),
                    "--expected-version",
                    self.version,
                    "--expected-core-revision",
                    self.core_revision,
                    "--expected-runtime-payload-sha256",
                    self.runtime_payload_sha256,
                ]
            )
        self.assertEqual(result, 0)
        self.assertEqual(calls, ["compile", "upload"])
        summaries = list(workspace.glob("*/m8-upload-result.json"))
        self.assertEqual(len(summaries), 1)
        evidence = json.loads(summaries[0].read_text(encoding="utf-8"))
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(evidence["release"]["core_revision"], self.core_revision)
        self.assertEqual(
            evidence["release"]["runtime_payload_sha256"],
            self.runtime_payload_sha256,
        )
        self.assertEqual(evidence["upload"]["attempts"], 1)
        self.assertEqual(evidence["uart"]["candidate_count"], 2)
        self.assertEqual(
            evidence["sketch"],
            {
                "repository_relative_path": MODULE.M8_SKETCH_RELATIVE_PATH,
                "sha256": "d" * 64,
            },
        )
        self.assertNotIn("serial_port", evidence)
        self.assertNotIn("probe_id", evidence)

    def test_committed_file_hash_ignores_worktree_crlf_conversion(self) -> None:
        """! @brief LF Git blob을 CRLF 작업 파일과 독립적으로 구분합니다. """

        repository = self.root / "line-ending-repository"
        repository.mkdir()
        commands = (
            ("git", "init", "--quiet"),
            ("git", "config", "user.name", "NU54 Test"),
            ("git", "config", "user.email", "nu54-test@example.invalid"),
            ("git", "config", "core.autocrlf", "false"),
        )
        for command in commands:
            subprocess.run(
                command,
                cwd=repository,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        relative_path = "fixture/m8_upload.ino"
        fixture = repository / Path(relative_path)
        fixture.parent.mkdir()
        committed_bytes = b"void setup() {\n}\nvoid loop() {\n}\n"
        fixture.write_bytes(committed_bytes)
        for command in (
            ("git", "add", "--", relative_path),
            ("git", "commit", "--quiet", "-m", "fixture"),
        ):
            subprocess.run(
                command,
                cwd=repository,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        fixture.write_bytes(committed_bytes.replace(b"\n", b"\r\n"))
        expected = hashlib.sha256(committed_bytes).hexdigest()
        self.assertNotEqual(MODULE.file_sha256(fixture), expected)
        self.assertEqual(
            MODULE.committed_file_sha256(repository, relative_path), expected
        )
        with self.assertRaisesRegex(MODULE.UploadHilFailure, "exact checkout"):
            MODULE.committed_file_sha256(repository, "fixture/missing.ino")

    def test_command_output_is_bounded_and_keeps_upload_pass_tail(self) -> None:
        """! @brief 큰 출력은 disk에 spool하고 마지막 upload PASS 표식은 보존합니다. """

        program = (
            "import os; os.write(1, b'x' * 4096); "
            "os.write(1, b'\\nNU54_UPLOAD_PASS runner=pyocd\\n')"
        )
        with mock.patch.object(MODULE, "MAX_COMMAND_OUTPUT_BYTES", 1024):
            return_code, output, _ = MODULE.run(
                [MODULE.sys.executable, "-c", program], timeout_seconds=30
            )
        self.assertEqual(return_code, 0)
        self.assertLessEqual(len(output.encode("utf-8")), 1024)
        self.assertTrue(output.startswith(MODULE.COMMAND_TRUNCATION_MARKER.decode("ascii")))
        self.assertIn("NU54_UPLOAD_PASS runner=pyocd", output)

    def test_command_timeout_terminates_descendant_process(self) -> None:
        """! @brief timeout된 HIL command의 후손 process가 실행을 계속하지 못합니다. """

        survivor = self.root / "hil-timeout-descendant.txt"
        child = (
            "import pathlib,sys,time; time.sleep(1.5); "
            "pathlib.Path(sys.argv[1]).write_text('survived', encoding='utf-8')"
        )
        parent = (
            "import subprocess,sys,time; "
            "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
            "time.sleep(30)"
        )
        return_code, _, _ = MODULE.run(
            [MODULE.sys.executable, "-c", parent, child, str(survivor)],
            timeout_seconds=1,
        )
        time.sleep(2)
        self.assertEqual(return_code, 124)
        self.assertFalse(survivor.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
