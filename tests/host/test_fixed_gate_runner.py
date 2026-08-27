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
            (("platform.txt", b"name=N\nversion=0.0.95\n", 0o644),)
        )
        second = MODULE.runtime_payload_sha256(
            (("platform.txt", b"name=N\nversion=0.1.0-rc.1\n", 0o644),)
        )
        changed = MODULE.runtime_payload_sha256(
            (("platform.txt", b"name=CHANGED\nversion=0.1.0-rc.1\n", 0o644),)
        )
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)

    ## @brief Twister가 고정 네 suite 이외를 생략하거나 추가하면 거부합니다.
    def test_twister_result_requires_exact_pass_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_name:
            report = Path(temporary_name) / "twister.json"
            document = {
                "environment": {"zephyr_version": "ncs-v3.4.0"},
                "testsuites": [
                    {
                        "name": scenario,
                        "platform": MODULE.BOARD_TARGET,
                        "arch": "arm",
                        "status": "passed",
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
