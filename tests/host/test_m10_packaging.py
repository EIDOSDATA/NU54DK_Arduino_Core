#!/usr/bin/env python3
"""! @brief M10 Boards Manager 재현 패키지 계약을 검증합니다. """

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "packaging" / "boards-manager" / "nu54_package.py"
SPEC = importlib.util.spec_from_file_location("nu54_package", MODULE_PATH)
assert SPEC and SPEC.loader
PACKAGE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PACKAGE
SPEC.loader.exec_module(PACKAGE)


class M10PackagingTests(unittest.TestCase):
    """! @brief 실제 Git commit을 이용해 생성·변조·index 계약을 시험합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        cls.commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
        cls.temporary = tempfile.TemporaryDirectory(prefix="nu54-m10-package-")
        cls.output = Path(cls.temporary.name) / "out"
        cls.repeat = Path(cls.temporary.name) / "repeat"
        cls.artifacts_90 = PACKAGE.build_package(REPO_ROOT, cls.output, "0.0.90", cls.commit)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_01_manifest_contract_and_exact_git_revisions(self) -> None:
        manifest = PACKAGE.validate_archive(
            self.artifacts_90["archive"], expected_version="0.0.90", expected_commit=self.commit
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["core_revision"], self.commit)
        self.assertRegex(manifest["board_revision"], r"^[0-9a-f]{40}$")
        self.assertEqual(manifest["ncs_revision"], PACKAGE.NCS_REVISION)
        self.assertEqual(manifest["zephyr_revision"], PACKAGE.ZEPHYR_REVISION)
        self.assertEqual(manifest["toolchain_bundle_id"], "dcbdc366a1")
        self.assertRegex(manifest["prerequisites_pins_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("runtime_payload_sha256", manifest)

    def test_02_archive_is_byte_reproducible(self) -> None:
        repeated = PACKAGE.build_package(REPO_ROOT, self.repeat, "0.0.90", self.commit)
        self.assertEqual(self.artifacts_90["archive"].read_bytes(), repeated["archive"].read_bytes())
        self.assertEqual(self.artifacts_90["manifest"].read_bytes(), repeated["manifest"].read_bytes())
        self.assertEqual(self.artifacts_90["sbom"].read_bytes(), repeated["sbom"].read_bytes())

    def test_03_archive_has_one_root_and_excludes_development_inputs(self) -> None:
        with zipfile.ZipFile(self.artifacts_90["archive"], "r") as archive:
            names = archive.namelist()
        roots = {name.split("/", 1)[0] for name in names}
        self.assertEqual(roots, {"nucode-nu54dk-zephyr-0.0.90"})
        forbidden = ("/00_Docs/", "/tests/", "/samples/", "/packaging/", "/build/", ".pdf", "/.git/")
        for name in names:
            self.assertFalse(any(token in name for token in forbidden), name)
        self.assertFalse(any("tools/remote-windows" in name for name in names))
        self.assertTrue(any("board_package/NU54DK_Zephyr_DTS/boards/" in name for name in names))
        self.assertFalse(any("board_package/NU54DK_Zephyr_DTS/00_Docs/" in name for name in names))
        root = "nucode-nu54dk-zephyr-0.0.90"
        expected_examples = {
            f"{root}/libraries/NUCODE_NU54DK/examples/Blink/Blink.ino",
            f"{root}/libraries/NUCODE_NU54DK/examples/InterruptButton/InterruptButton.ino",
            f"{root}/libraries/NUCODE_NU54DK/examples/AnalogReadA0/AnalogReadA0.ino",
            f"{root}/libraries/NUCODE_NU54DK/examples/PWMFade/PWMFade.ino",
            f"{root}/libraries/NUCODE_NU54DK/examples/SerialEcho/SerialEcho.ino",
            f"{root}/libraries/SPI/examples/SPITransaction/SPITransaction.ino",
            f"{root}/libraries/Wire/examples/WirePmicId/WirePmicId.ino",
        }
        self.assertTrue(expected_examples.issubset(set(names)))
        self.assertFalse(any(name.startswith(f"{root}/examples/") for name in names))

    def test_03b_windows_command_scripts_use_strict_crlf(self) -> None:
        """! @brief RC command script 변환의 ASCII·CRLF 계약을 검증합니다. """
        expected_scripts = (
            "post_install.bat",
            "tools/nu54-builder/nu54-builder.cmd",
        )
        for script in expected_scripts:
            data = PACKAGE.rewrite_windows_command_line_endings(
                (REPO_ROOT / script).read_bytes(), script
            )
            self.assertTrue(data.isascii(), f"non-ASCII launcher bytes: {script}")
            self.assertIn(b"\r\n", data)
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""))
        with self.assertRaises(PACKAGE.PackageError):
            PACKAGE.rewrite_windows_command_line_endings(
                "한글 주석\n".encode("utf-8"), "unsafe.cmd"
            )

    def test_04_platform_is_exact_commit_content_except_version(self) -> None:
        original = subprocess.check_output(
            ["git", "show", f"{self.commit}:platform.txt"], cwd=REPO_ROOT
        ).decode("utf-8")
        root = "nucode-nu54dk-zephyr-0.0.90"
        with zipfile.ZipFile(self.artifacts_90["archive"], "r") as archive:
            packaged = archive.read(f"{root}/platform.txt").decode("utf-8")
        original_without_version = "\n".join(
            line for line in original.splitlines() if not line.startswith("version=")
        )
        packaged_without_version = "\n".join(
            line for line in packaged.splitlines() if not line.startswith("version=")
        )
        self.assertEqual(original_without_version, packaged_without_version)
        self.assertIn("version=0.0.90", packaged.splitlines())

    def test_05_sbom_license_and_checksum_sidecars_are_present(self) -> None:
        root = "nucode-nu54dk-zephyr-0.0.90"
        with zipfile.ZipFile(self.artifacts_90["archive"], "r") as archive:
            sbom = json.loads(archive.read(f"{root}/sbom.spdx.json"))
            inventory = json.loads(archive.read(f"{root}/license-inventory.json"))
            checksums = archive.read(f"{root}/CHECKSUMS.sha256").decode("utf-8")
        self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
        self.assertGreater(len(sbom["files"]), 20)
        self.assertEqual(inventory["legal_review_status"], "required-before-final-public-release")
        self.assertEqual(len(inventory["components"]), 4)
        self.assertIn("release-manifest.json", checksums)
        for path in self.artifacts_90.values():
            self.assertTrue(path.is_file(), path)

    def test_06_board_license_scopes_are_split_and_noticed(self) -> None:
        root = "nucode-nu54dk-zephyr-0.0.90"
        with zipfile.ZipFile(self.artifacts_90["archive"], "r") as archive:
            inventory = json.loads(archive.read(f"{root}/license-inventory.json"))
            sbom = json.loads(archive.read(f"{root}/sbom.spdx.json"))
            notices = archive.read(f"{root}/THIRD_PARTY_NOTICES.md").decode("utf-8")
        components = {item["name"]: item for item in inventory["components"]}
        self.assertEqual(components["NU54DK Zephyr DTS repository"]["license_expression"], "MIT")
        derived = components["NU54DK Zephyr derived board definition"]
        self.assertEqual(derived["license_expression"], "Apache-2.0")
        self.assertEqual(
            derived["scope"], ["board_package/NU54DK_Zephyr_DTS/boards/nucode/nu54dk/**"]
        )
        license_files = {item["path"]: item for item in inventory["license_files"]}
        self.assertEqual(
            license_files["board_package/NU54DK_Zephyr_DTS/LICENSE"]["license_expression"], "MIT"
        )
        self.assertEqual(
            license_files["board_package/NU54DK_Zephyr_DTS/LICENSES/Apache-2.0.txt"][
                "license_expression"
            ],
            "Apache-2.0",
        )
        self.assertIn(
            "board_package/NU54DK_Zephyr_DTS/NOTICE",
            {item["path"] for item in inventory["notice_files"]},
        )
        spdx_files = {
            item["fileName"].removeprefix("./"): item for item in sbom["files"]
        }
        self.assertEqual(
            spdx_files["board_package/NU54DK_Zephyr_DTS/LICENSE"]["licenseConcluded"], "MIT"
        )
        derived_files = [
            item
            for path, item in spdx_files.items()
            if path.startswith("board_package/NU54DK_Zephyr_DTS/boards/nucode/nu54dk/")
        ]
        self.assertTrue(derived_files)
        self.assertTrue(all(item["licenseConcluded"] == "Apache-2.0" for item in derived_files))
        self.assertIn("MIT AND Apache-2.0", notices)

    def test_07_external_prerequisites_are_not_marked_as_redistributed(self) -> None:
        root = "nucode-nu54dk-zephyr-0.0.90"
        with zipfile.ZipFile(self.artifacts_90["archive"], "r") as archive:
            inventory = json.loads(archive.read(f"{root}/license-inventory.json"))
            sbom = json.loads(archive.read(f"{root}/sbom.spdx.json"))
        prerequisites = {item["name"]: item for item in inventory["external_prerequisites"]}
        self.assertEqual(
            set(prerequisites),
            {
                "nRF Util",
                "nRF Util sdk-manager",
                "nRF Connect SDK",
                "Zephyr",
                "nRF Connect SDK Toolchain",
                "pyOCD",
                "SEGGER J-Link Software",
            },
        )
        self.assertTrue(
            all(item["distribution"] == "external-not-redistributed" for item in prerequisites.values())
        )
        self.assertTrue(all(item["license_expression"] == "NOASSERTION" for item in prerequisites.values()))
        self.assertEqual(prerequisites["nRF Util"]["version"], "8.2.1")
        self.assertRegex(prerequisites["nRF Util"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(prerequisites["nRF Util sdk-manager"]["version"], "1.16.1")
        self.assertEqual(prerequisites["nRF Connect SDK"]["revision"], PACKAGE.NCS_REVISION)
        self.assertEqual(prerequisites["Zephyr"]["revision"], PACKAGE.ZEPHYR_REVISION)
        self.assertEqual(prerequisites["nRF Connect SDK Toolchain"]["bundle_id"], "dcbdc366a1")
        self.assertEqual(prerequisites["pyOCD"]["version"], "0.45.1")
        self.assertFalse(prerequisites["SEGGER J-Link Software"]["required"])
        external_spdx = [package for package in sbom["packages"] if package["name"] in prerequisites]
        self.assertEqual(len(external_spdx), 7)
        self.assertTrue(all(package["licenseDeclared"] == "NOASSERTION" for package in external_spdx))
        self.assertTrue(all("external-not-redistributed" in package["comment"] for package in external_spdx))
        relationships = {item["relationshipType"] for item in sbom["relationships"]}
        self.assertIn("DEPENDS_ON", relationships)
        self.assertIn("OPTIONAL_DEPENDENCY_OF", relationships)

    def test_08_validator_rejects_tampered_payload(self) -> None:
        source = self.artifacts_90["archive"]
        tampered = Path(self.temporary.name) / source.name
        with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(
            tampered, "w", compression=zipfile.ZIP_DEFLATED
        ) as output:
            for info in original.infolist():
                data = original.read(info)
                if info.filename.endswith("/platform.txt"):
                    data = data.replace(b"version=0.0.90", b"version=0.0.91")
                output.writestr(info, data)
        with self.assertRaises(PACKAGE.PackageError):
            PACKAGE.validate_archive(tampered, expected_version="0.0.90")

    def test_09_index_contains_both_versions_in_latest_first_order(self) -> None:
        PACKAGE.build_package(REPO_ROOT, self.output, "0.0.92", self.commit)
        PACKAGE.build_package(REPO_ROOT, self.output, "0.0.93", self.commit)
        index_path = PACKAGE.generate_index(self.output, ["0.0.92", "0.0.93"])
        document = PACKAGE.validate_index(index_path, artifact_dir=self.output)
        package = document["packages"][0]
        self.assertEqual(package["name"], "nucode")
        self.assertEqual(package["maintainer"], "NUCODE / Quantum")
        self.assertEqual(package["email"], "EIDOSDATA@users.noreply.github.com")
        self.assertEqual(
            [platform["version"] for platform in package["platforms"]], ["0.0.93", "0.0.92"]
        )
        for platform in package["platforms"]:
            self.assertTrue(platform["url"].startswith(PACKAGE.REPOSITORY_URL + "/releases/download/"))
            self.assertEqual(platform["toolsDependencies"], [])

    def test_10_index_validator_rejects_wrong_public_identity(self) -> None:
        index_path = self.output / PACKAGE.INDEX_FILENAME
        document = json.loads(index_path.read_text(encoding="utf-8"))
        document["packages"][0]["websiteURL"] = "https://github.com/Nucode01/NU54DK_Arduino_Core"
        broken = Path(self.temporary.name) / "broken-index.json"
        broken.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(PACKAGE.PackageError):
            PACKAGE.validate_index(broken, artifact_dir=self.output)

    def test_10a_checked_in_stable_index_has_current_public_identity(self) -> None:
        """! @brief 장기 사용자 endpoint의 stable index identity를 검증합니다. """

        index = REPO_ROOT / PACKAGE.STABLE_INDEX_FILENAME
        self.assertEqual(index.stat().st_size, 1877)
        self.assertEqual(
            hashlib.sha256(index.read_bytes()).hexdigest(),
            "5ae7fbe13f71c52950879064685694cf4b062557572f187e81476639724e5344",
        )
        self.assertNotEqual(PACKAGE.RC_INDEX_FILENAME, PACKAGE.STABLE_INDEX_FILENAME)
        document = PACKAGE.validate_index(index)
        platforms = document["packages"][0]["platforms"]
        self.assertEqual(
            [platform["version"] for platform in platforms],
            ["0.2.0", "0.1.0"],
        )
        for platform, version in zip(platforms, ("0.2.0", "0.1.0"), strict=True):
            identity = PACKAGE.PUBLISHED_STABLE_ARCHIVE_IDENTITIES[version]
            self.assertEqual(platform["archiveFileName"], PACKAGE.archive_filename(version))
            self.assertEqual(
                platform["url"],
                PACKAGE.release_asset_url(version, PACKAGE.archive_filename(version)),
            )
            self.assertEqual(platform["checksum"], f"SHA-256:{identity['sha256']}")
            self.assertEqual(platform["size"], str(identity["size"]))

    def test_10aa_stable_index_checkout_is_forced_to_lf(self) -> None:
        """! @brief 공개 stable index의 Git checkout 줄바꿈 계약을 검증합니다. """

        relative = PACKAGE.STABLE_INDEX_FILENAME
        attributes = subprocess.check_output(
            ["git", "check-attr", "text", "eol", "--", relative],
            cwd=REPO_ROOT,
            text=True,
        ).splitlines()
        self.assertEqual(
            attributes,
            [
                f"{relative}: text: set",
                f"{relative}: eol: lf",
            ],
        )

        stable_bytes = (REPO_ROOT / relative).read_bytes()
        self.assertIn(b"\n", stable_bytes)
        self.assertNotIn(b"\r\n", stable_bytes)
        crlf_bytes = stable_bytes.replace(b"\n", b"\r\n")
        self.assertNotEqual(
            hashlib.sha256(crlf_bytes).hexdigest(),
            "5ae7fbe13f71c52950879064685694cf4b062557572f187e81476639724e5344",
        )

    def test_11_supported_versions_are_fail_closed(self) -> None:
        self.assertEqual(PACKAGE.LEGACY_PREVIEW_VERSIONS[-2:], ("0.0.92", "0.0.93"))
        self.assertEqual(PACKAGE.FAILED_M10_PREVIEW_VERSIONS, ("0.0.94", "0.0.95"))
        self.assertEqual(PACKAGE.SAFE_PREVIEW_VERSIONS, ("0.0.96", "0.0.97"))
        self.assertEqual(PACKAGE.SUPPORTED_VERSIONS[-2:], ("0.0.96", "0.0.97"))
        self.assertEqual(
            PACKAGE.RELEASE_CANDIDATE_VERSIONS,
            ("0.1.0-rc.2", "0.2.0-rc.1", "0.2.0-rc.2", "0.3.0-rc.1", "0.3.0-rc.2"),
        )
        self.assertEqual(PACKAGE.STABLE_VERSIONS, ("0.1.0", "0.2.0"))
        self.assertTrue(
            set(PACKAGE.FAILED_M10_PREVIEW_VERSIONS).issubset(
                PACKAGE.WINDOWS_SAFE_VERSIONS
            )
        )
        for version in PACKAGE.FAILED_M10_PREVIEW_VERSIONS:
            self.assertEqual(PACKAGE.release_tag(version), f"m10-preview-{version}")
            self.assertIn(
                f"/releases/download/m10-preview-{version}/",
                PACKAGE.release_asset_url(version, PACKAGE.archive_filename(version)),
            )
        preview_wrapper = (
            REPO_ROOT / "packaging" / "boards-manager" / "build-preview.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("[ValidateSet('0.0.96', '0.0.97')]", preview_wrapper)
        self.assertNotIn("'0.0.94'", preview_wrapper)
        self.assertNotIn("'0.0.95'", preview_wrapper)
        with self.assertRaises(PACKAGE.PackageError):
            PACKAGE.build_package(REPO_ROOT, self.output, "0.1.1", self.commit)

    def test_11a_stable_package_has_approved_identity_and_own_index(self) -> None:
        """! @brief 승인된 stable 버전이 RC와 분리된 공개 identity를 갖는지 검증합니다. """

        self.assertEqual(
            PACKAGE.STABLE_RELEASE_COMMITS,
            {
                "0.1.0": "5dbc5e37270e477d21f578dd877f4b5226b44a0d",
                "0.2.0": "41fc44e452d2b6eef4b46307af6c277499f8d2d5",
            },
        )
        index = REPO_ROOT / PACKAGE.STABLE_INDEX_FILENAME
        document = PACKAGE.validate_index(index)
        self.assertEqual(PACKAGE.release_channel("0.1.0"), "stable")
        self.assertEqual(PACKAGE.release_tag("0.1.0"), "v0.1.0")
        self.assertEqual(index.name, PACKAGE.STABLE_INDEX_FILENAME)
        platforms = document["packages"][0]["platforms"]
        self.assertEqual(
            [platform["version"] for platform in platforms],
            ["0.2.0", "0.1.0"],
        )
        self.assertEqual(
            platforms[0]["url"],
            "https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/"
            "v0.2.0/nucode-nu54dk-zephyr-0.2.0.zip",
        )
        self.assertEqual(
            PACKAGE.legal_review_status("0.1.0"),
            "project-owner-approved-for-final-public-release",
        )
        stable_wrapper = (
            REPO_ROOT / "packaging" / "boards-manager" / "build-stable.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("[ValidateSet('0.1.0', '0.2.0')]", stable_wrapper)
        self.assertIn('$Commit = "v$Version"', stable_wrapper)
        self.assertIn("nucode-nu54dk-zephyr-0.1.0.zip", stable_wrapper)
        self.assertIn("@('0.2.0', '0.1.0')", stable_wrapper)
        self.assertNotIn("--update-index", stable_wrapper)
        self.assertEqual(
            PACKAGE.legal_review_status("0.2.0"),
            "project-owner-approved-for-final-public-release",
        )
        self.assertEqual(PACKAGE.release_channel("0.2.0"), "stable")
        self.assertEqual(PACKAGE.release_tag("0.2.0"), "v0.2.0")
        self.assertEqual(
            PACKAGE.PUBLISHED_STABLE_ARCHIVE_IDENTITIES["0.1.0"],
            {
                "size": 760412,
                "sha256": "722a46685b97aff42a75fb84db8ea74de75f3c32f59ea58225cd86d5acd141a6",
            },
        )
        self.assertEqual(
            PACKAGE.PUBLISHED_STABLE_ARCHIVE_IDENTITIES["0.2.0"],
            {
                "size": 932376,
                "sha256": "1c2b4dddd6da0c1530f9d32630ec7d5b5285cff28c826a9a95c864226aeaea6e",
            },
        )

    def test_11aaa_published_stable_index_archive_uses_exact_bytes(self) -> None:
        """! @brief 과거 stable은 최신 source 허용목록 대신 공개 byte identity로 검증합니다. """

        for version in PACKAGE.STABLE_VERSIONS:
            with self.subTest(version=version):
                archive = Path(self.temporary.name) / PACKAGE.archive_filename(version)
                original = PACKAGE.PUBLISHED_STABLE_ARCHIVE_IDENTITIES[version]
                published = f"published-stable-archive-{version}".encode("ascii")
                archive.write_bytes(published)
                PACKAGE.PUBLISHED_STABLE_ARCHIVE_IDENTITIES[version] = {
                    "size": len(published),
                    "sha256": hashlib.sha256(published).hexdigest(),
                }
                try:
                    PACKAGE.validate_index_archive(archive, version)
                    archive.write_bytes(published + b"-tampered")
                    with self.assertRaises(PACKAGE.PackageError):
                        PACKAGE.validate_index_archive(archive, version)
                finally:
                    PACKAGE.PUBLISHED_STABLE_ARCHIVE_IDENTITIES[version] = original

    def test_11ab_published_v020_runtime_matches_public_rc2(self) -> None:
        """! @brief 공개 stable과 RC2의 version-independent runtime payload를 검증합니다. """

        stable_files, _ = PACKAGE.collect_source_files(
            REPO_ROOT,
            PACKAGE.STABLE_RELEASE_COMMITS["0.2.0"],
            "0.2.0",
        )
        rc_files, _ = PACKAGE.collect_source_files(
            REPO_ROOT,
            "1c5dcecfc0dba2ef25e06963dcba61c63f454db9",
            "0.2.0-rc.2",
        )
        stable_runtime = PACKAGE.runtime_payload_sha256(
            (item.path, item.data, item.mode) for item in stable_files
        )
        rc_runtime = PACKAGE.runtime_payload_sha256(
            (item.path, item.data, item.mode) for item in rc_files
        )
        self.assertEqual(
            stable_runtime,
            "ec604501b2ba58b622c3490925a79c8ac716bba93f0938840e49c624a16998c8",
        )
        self.assertEqual(stable_runtime, rc_runtime)

    def test_11aa_stable_package_rejects_a_different_commit(self) -> None:
        """! @brief 공개 stable 이름으로 다른 source byte를 생성하지 못하게 합니다. """

        for version in PACKAGE.STABLE_VERSIONS:
            with self.subTest(version=version), self.assertRaises(PACKAGE.PackageError):
                PACKAGE.build_package(
                    REPO_ROOT,
                    Path(self.temporary.name) / f"forbidden-stable-{version}",
                    version,
                    "1c5dcecfc0dba2ef25e06963dcba61c63f454db9",
                )

    def test_11b_current_safe_pair_has_one_runtime_payload(self) -> None:
        """! @brief 새 immutable preview 두 개가 같은 source와 runtime payload를 사용합니다. """

        safe_output = Path(self.temporary.name) / "current-safe"
        manifests = []
        for version in PACKAGE.SAFE_PREVIEW_VERSIONS:
            paths = PACKAGE.build_package(
                REPO_ROOT, safe_output, version, self.commit
            )
            manifests.append(
                PACKAGE.validate_archive(
                    paths["archive"],
                    expected_version=version,
                    expected_commit=self.commit,
                )
            )
        self.assertEqual(
            {manifest["core_revision"] for manifest in manifests}, {self.commit}
        )
        self.assertEqual(
            len({manifest["runtime_payload_sha256"] for manifest in manifests}), 1
        )
        self.assertTrue(
            all(
                "windows-crlf-rewrites" in manifest["source_policy"]
                for manifest in manifests
            )
        )

    def test_12_runtime_payload_fingerprint_ignores_only_platform_version(self) -> None:
        """! @brief 버전 문자열만 다른 동일 payload와 실제 byte 변경을 구분합니다. """

        first = (
            ("platform.txt", b"name=NU54DK\nversion=0.0.96\n", 0o644),
            ("cores/arduino/Arduino.h", b"payload\n", 0o644),
        )
        second = (
            ("platform.txt", b"name=NU54DK\nversion=0.1.0-rc.1\n", 0o644),
            ("cores/arduino/Arduino.h", b"payload\n", 0o644),
        )
        changed = (
            ("platform.txt", b"name=NU54DK\nversion=0.1.0-rc.1\n", 0o644),
            ("cores/arduino/Arduino.h", b"payload changed\n", 0o644),
        )
        self.assertEqual(
            PACKAGE.runtime_payload_sha256(first),
            PACKAGE.runtime_payload_sha256(second),
        )
        self.assertNotEqual(
            PACKAGE.runtime_payload_sha256(first),
            PACKAGE.runtime_payload_sha256(changed),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
