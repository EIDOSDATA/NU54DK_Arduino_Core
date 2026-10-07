#!/usr/bin/env python3
"""! @brief M33-W05 clean 설치 예제 runner의 fail-closed 계약을 검사합니다. """

from __future__ import annotations

from argparse import Namespace
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "ci" / "m33_w05_installed_examples.py"
SPEC = importlib.util.spec_from_file_location("m33_w05_installed_examples_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def make_platform(root: Path, *, profile: str = "standard", roles: list[str] | None = None) -> Path:
    """! @brief 단일 공개 예제를 가진 최소 platform fixture를 만듭니다. """

    platform = root
    library = platform / "libraries" / "ExampleLibrary"
    example = library / "examples" / "ExampleSketch"
    example.mkdir(parents=True)
    (library / "library.properties").write_text(
        "name=Example Library\narchitectures=zephyr\n", encoding="utf-8"
    )
    (example / "ExampleSketch.ino").write_text(
        "void setup() {}\nvoid loop() {}\n", encoding="utf-8"
    )
    selected_roles = roles if roles is not None else ["example role"]
    metadata = {
        "schema_version": 1,
        "example_count": 1,
        "examples": {
            "ExampleLibrary/ExampleSketch": {
                "path": "libraries/ExampleLibrary/examples/ExampleSketch/ExampleSketch.ino",
                "recommended_profile": profile,
                "alternative_profiles": [],
                "board_count": len(selected_roles),
                "roles": selected_roles,
                "serial_baud": None,
                "sidecars": [],
                "conditions": [],
            }
        },
    }
    (platform / "libraries" / "example-metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    return platform


def write_manifest(
    path: Path,
    build: Path,
    sketch: Path,
    fqbn: str,
    fixed: dict[str, str],
) -> Path:
    """! @brief 성공 build manifest와 primary HEX fixture를 기록합니다. """

    image = build / "ExampleSketch.ino.hex"
    image.write_bytes(b":020000040000FA\n")
    document = {
        "fqbn": fqbn,
        "board": MODULE.TARGET_BOARD,
        "cache": {
            "input_manifest": {
                "ncs": {
                    "nrf_revision": fixed["nrf_revision"],
                    "zephyr_revision": fixed["zephyr_revision"],
                },
                "board_package": {"revision": fixed["board_revision"]},
                "sketch": {"root": str(sketch)},
            }
        },
        "artifacts": {
            "hex": {
                "path": str(image),
                "sha256": MODULE.sha256_file(image),
            }
        },
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return image


class M33W05InstalledExampleTests(unittest.TestCase):
    """! @brief 설치 분리·분모·profile·timeout·manifest 검사를 검증합니다. """

    def test_repository_catalog_and_negative_matrix_are_finite(self) -> None:
        """! @brief 현행 204개와 유한 negative 행의 identity를 고정합니다. """

        catalog = MODULE.load_catalog(ROOT)
        self.assertEqual(MODULE.EXPECTED_EXAMPLES, len(catalog))
        self.assertEqual(9, len(MODULE.NEGATIVE_PROFILE_MATRIX))
        self.assertEqual(
            len(MODULE.NEGATIVE_PROFILE_MATRIX),
            len({case["id"] for case in MODULE.NEGATIVE_PROFILE_MATRIX}),
        )
        for case in MODULE.NEGATIVE_PROFILE_MATRIX:
            with self.subTest(case=case["id"]):
                self.assertIn(case["identity"], catalog)
                self.assertNotEqual(case["profile"], catalog[case["identity"]]["profile"])
                self.assertEqual("[NU54:E_FEATURE_PROFILE]", case["marker"])

    def test_eight_shards_partition_positive_and_negative_once(self) -> None:
        """! @brief 8개 shard가 204개 build와 9개 negative를 정확히 한 번 나눕니다. """

        catalog = MODULE.load_catalog(ROOT)
        positive: list[str] = []
        negative: list[str] = []
        for index in range(MODULE.CI_SHARD_COUNT):
            identities, cases = MODULE.selected_work(
                catalog, index, MODULE.CI_SHARD_COUNT
            )
            positive.extend(identities)
            negative.extend(case["id"] for case in cases)
            self.assertIn(len(identities), (25, 26))
            self.assertIn(len(cases), (1, 2))
        self.assertEqual(MODULE.EXPECTED_EXAMPLES, len(positive))
        self.assertEqual(MODULE.EXPECTED_EXAMPLES, len(set(positive)))
        self.assertEqual(set(catalog), set(positive))
        self.assertEqual(len(MODULE.NEGATIVE_PROFILE_MATRIX), len(negative))
        self.assertEqual(len(MODULE.NEGATIVE_PROFILE_MATRIX), len(set(negative)))

    def test_default_parser_preserves_non_sharded_mode(self) -> None:
        """! @brief shard option이 없으면 기존 전수 실행 mode를 유지합니다. """

        arguments = MODULE.argument_parser().parse_args([
            "--installed-platform", "C:/installed",
            "--sdk-root", "C:/ncs/v3.4.0",
            "--arduino-cli", "C:/bin/arduino-cli.exe",
            "--config-file", "C:/arduino/arduino-cli.yaml",
            "--build-root", "C:/build",
            "--output", "C:/evidence/installed-examples.json",
        ])
        self.assertIsNone(arguments.shard_index)
        self.assertEqual(MODULE.CI_SHARD_COUNT, arguments.shard_count)
        self.assertEqual(2, arguments.jobs)

    def test_catalog_rejects_count_role_and_profile_drift(self) -> None:
        """! @brief metadata 분모·역할·profile 오류를 각각 거부합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-w05-catalog-") as temporary:
            platform = make_platform(Path(temporary))
            self.assertEqual(1, len(MODULE.load_catalog(platform, expected_count=1)))
            path = platform / "libraries" / "example-metadata.json"
            valid = json.loads(path.read_text(encoding="utf-8"))
            for mutation in ("count", "roles", "profile"):
                with self.subTest(mutation=mutation):
                    broken = json.loads(json.dumps(valid))
                    record = broken["examples"]["ExampleLibrary/ExampleSketch"]
                    if mutation == "count":
                        broken["example_count"] = 2
                    elif mutation == "roles":
                        record["roles"] = []
                    else:
                        record["recommended_profile"] = "unknown"
                    path.write_text(json.dumps(broken), encoding="utf-8")
                    with self.assertRaises(MODULE.M33W05Failure):
                        MODULE.load_catalog(platform, expected_count=1)
            path.write_text(json.dumps(valid), encoding="utf-8")

    def test_tree_fingerprint_includes_relative_name_and_content(self) -> None:
        """! @brief 이름 또는 내용이 바뀌면 설치 tree 지문도 바뀝니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-w05-tree-") as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            (first / "a.txt").write_text("same", encoding="utf-8")
            (second / "a.txt").write_text("same", encoding="utf-8")
            self.assertEqual(
                MODULE.tree_fingerprint(first), MODULE.tree_fingerprint(second)
            )
            (second / "a.txt").write_text("changed", encoding="utf-8")
            self.assertNotEqual(
                MODULE.tree_fingerprint(first), MODULE.tree_fingerprint(second)
            )

    def test_discovery_requires_exact_separate_install_tree(self) -> None:
        """! @brief Arduino CLI가 source가 아닌 동일 hash 설치 library를 선택해야 합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-w05-discovery-") as temporary:
            root = Path(temporary)
            source = make_platform(root / "source")
            installed = make_platform(root / "installed")
            cli = root / "arduino-cli.exe"
            config = root / "arduino-cli.yaml"
            cli.write_bytes(b"cli")
            config.write_text("board_manager: {}\n", encoding="utf-8")
            installed_library = installed / "libraries" / "ExampleLibrary"
            listing = {
                "examples": [{
                    "library": {
                        "name": "Example Library",
                        "install_dir": str(installed_library),
                        "container_platform": "nucode:zephyr@0.6.0",
                    },
                    "examples": [str(installed_library / "examples" / "ExampleSketch")],
                }]
            }
            completed = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(listing), stderr=""
            )
            with mock.patch.object(MODULE.subprocess, "run", return_value=completed):
                row = MODULE.discover_library(
                    cli,
                    config,
                    source,
                    installed,
                    "ExampleLibrary",
                    {"ExampleLibrary/ExampleSketch"},
                )
            self.assertEqual(1, row["example_count"])
            self.assertEqual(
                MODULE.tree_fingerprint(source / "libraries" / "ExampleLibrary")[1],
                row["tree_sha256"],
            )

            (installed_library / "examples" / "ExampleSketch" / "extra.txt").write_text(
                "drift", encoding="utf-8"
            )
            with self.assertRaisesRegex(MODULE.M33W05Failure, "tree"):
                MODULE.discover_library(
                    cli,
                    config,
                    source,
                    installed,
                    "ExampleLibrary",
                    {"ExampleLibrary/ExampleSketch"},
                )

    def test_build_manifest_binds_installed_sketch_and_fixed_revisions(self) -> None:
        """! @brief 성공 artifact가 설치 sketch와 NCS 3.4.0 입력에 결합됩니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-w05-manifest-") as temporary:
            root = Path(temporary)
            sketch = root / "installed" / "ExampleSketch"
            build = root / "build"
            sketch.mkdir(parents=True)
            build.mkdir()
            fixed = {
                "nrf_revision": "1" * 40,
                "zephyr_revision": "2" * 40,
                "board_revision": "3" * 40,
            }
            selected_fqbn = "nucode:zephyr:nu54dk:feature_set=standard"
            manifest = build / "ExampleSketch.ino.nu54-build.json"
            image = write_manifest(manifest, build, sketch, selected_fqbn, fixed)
            manifest_hash, image_hash = MODULE.validate_build_manifest(
                manifest, build, sketch, selected_fqbn, fixed
            )
            self.assertEqual(MODULE.sha256_file(manifest), manifest_hash)
            self.assertEqual(MODULE.sha256_file(image), image_hash)

            broken = json.loads(manifest.read_text(encoding="utf-8"))
            broken["cache"]["input_manifest"]["board_package"]["revision"] = "4" * 40
            manifest.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.M33W05Failure, "revision"):
                MODULE.validate_build_manifest(
                    manifest, build, sketch, selected_fqbn, fixed
                )

    def test_positive_compile_requires_manifest_and_hex(self) -> None:
        """! @brief exit 0만으로 PASS하지 않고 manifest·HEX hash를 요구합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-w05-positive-") as temporary:
            root = Path(temporary)
            sketch = root / "installed" / "ExampleSketch"
            sketch.mkdir(parents=True)
            (sketch / "ExampleSketch.ino").write_text(
                "void setup() {}\nvoid loop() {}\n", encoding="utf-8"
            )
            cli = root / "arduino-cli.exe"
            config = root / "arduino-cli.yaml"
            cli.write_bytes(b"cli")
            config.write_text("board_manager: {}\n", encoding="utf-8")
            fixed = {
                "nrf_revision": "1" * 40,
                "zephyr_revision": "2" * 40,
                "board_revision": "3" * 40,
            }

            def successful_run(*_args, **_kwargs):
                build = root / "build"
                write_manifest(
                    build / "ExampleSketch.ino.nu54-build.json",
                    build,
                    sketch,
                    "nucode:zephyr:nu54dk:feature_set=standard",
                    fixed,
                )
                return subprocess.CompletedProcess([], 0, "build ok", "")

            with mock.patch.object(MODULE.subprocess, "run", side_effect=successful_run):
                row = MODULE.compile_example(
                    cli,
                    config,
                    "nucode:zephyr:nu54dk",
                    "ExampleLibrary/ExampleSketch",
                    sketch,
                    "standard",
                    root / "build",
                    root / "positive.log",
                    60,
                    fixed,
                    (root,),
                )
            self.assertEqual("PASS", row["status"])
            self.assertIsNotNone(row["manifest_sha256"])
            self.assertIsNotNone(row["hex_sha256"])

            with mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 0, "build ok", ""),
            ):
                failed = MODULE.compile_example(
                    cli,
                    config,
                    "nucode:zephyr:nu54dk",
                    "ExampleLibrary/ExampleSketch",
                    sketch,
                    "standard",
                    root / "missing-manifest",
                    root / "missing.log",
                    60,
                    fixed,
                    (root,),
                )
            self.assertEqual("FAIL", failed["status"])

    def test_negative_profile_requires_expected_marker_and_no_artifact(self) -> None:
        """! @brief 일반 compiler 오류를 의도한 profile 거부로 오인하지 않습니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-w05-negative-") as temporary:
            root = Path(temporary)
            sketch = root / "installed" / "ExampleSketch"
            sketch.mkdir(parents=True)
            cli = root / "arduino-cli.exe"
            config = root / "arduino-cli.yaml"
            cli.write_bytes(b"cli")
            config.write_text("board_manager: {}\n", encoding="utf-8")
            case = {
                "id": "wrong_profile",
                "identity": "ExampleLibrary/ExampleSketch",
                "profile": "ble",
                "marker": "[NU54:E_FEATURE_PROFILE]",
            }
            rejected = subprocess.CompletedProcess(
                [], 1, "", "[NU54:E_FEATURE_PROFILE] incompatible"
            )
            with mock.patch.object(MODULE.subprocess, "run", return_value=rejected):
                row = MODULE.compile_negative(
                    cli,
                    config,
                    "nucode:zephyr:nu54dk",
                    case,
                    sketch,
                    root / "rejected",
                    root / "rejected.log",
                    30,
                    (root,),
                )
            self.assertEqual("PASS", row["status"])

            generic = subprocess.CompletedProcess([], 1, "", "compiler missing")
            with mock.patch.object(MODULE.subprocess, "run", return_value=generic):
                row = MODULE.compile_negative(
                    cli,
                    config,
                    "nucode:zephyr:nu54dk",
                    case,
                    sketch,
                    root / "generic",
                    root / "generic.log",
                    30,
                    (root,),
                )
            self.assertEqual("FAIL", row["status"])

    def test_compile_timeout_is_a_failure(self) -> None:
        """! @brief timeout을 expected failure 또는 compile PASS로 세지 않습니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-w05-timeout-") as temporary:
            root = Path(temporary)
            sketch = root / "installed" / "ExampleSketch"
            sketch.mkdir(parents=True)
            cli = root / "arduino-cli.exe"
            config = root / "arduino-cli.yaml"
            cli.write_bytes(b"cli")
            config.write_text("board_manager: {}\n", encoding="utf-8")
            case = {
                "id": "timeout",
                "identity": "ExampleLibrary/ExampleSketch",
                "profile": "ble",
                "marker": "[NU54:E_FEATURE_PROFILE]",
            }
            with mock.patch.object(
                MODULE.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(["arduino-cli"], 30),
            ):
                row = MODULE.compile_negative(
                    cli,
                    config,
                    "nucode:zephyr:nu54dk",
                    case,
                    sketch,
                    root / "timeout-build",
                    root / "timeout.log",
                    30,
                    (root,),
                )
            self.assertEqual("FAIL", row["status"])
            self.assertTrue(row["timed_out"])

    def test_diagnostic_retest_is_single_and_preserves_initial_failure(self) -> None:
        """! @brief 최초 실패는 보존하고 동일 예제의 두 번째 재시험은 거부합니다. """

        initial = {
            "identity": "ExampleLibrary/ExampleSketch",
            "status": "FAIL",
            "failure": "compile_or_manifest_failure",
        }
        retry = {
            "identity": "ExampleLibrary/ExampleSketch",
            "status": "PASS",
            "failure": None,
        }
        document = {"builds": [initial], "diagnostic_retests": []}
        MODULE.apply_diagnostic_retest(document, initial, retry)
        self.assertEqual([retry], document["builds"])
        self.assertEqual(initial, document["diagnostic_retests"][0]["initial"])
        self.assertEqual(retry, document["diagnostic_retests"][0]["retry"])
        self.assertEqual(2, document["diagnostic_retests"][0]["attempt"])
        with self.assertRaisesRegex(MODULE.M33W05Failure, "횟수"):
            MODULE.apply_diagnostic_retest(document, initial, retry)

    def test_path_contract_rejects_reuse_and_more_than_two_jobs(self) -> None:
        """! @brief source/install 분리와 fresh output, jobs 상한을 강제합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-w05-paths-") as temporary:
            root = Path(temporary)
            source = root / "source"
            installed = root / "installed"
            sdk = root / "sdk"
            for directory in (source, installed, sdk):
                directory.mkdir()
            cli = root / "arduino-cli.exe"
            config = root / "arduino-cli.yaml"
            cli.write_bytes(b"cli")
            config.write_text("board_manager: {}\n", encoding="utf-8")
            arguments = Namespace(
                repository=source,
                installed_platform=installed,
                sdk_root=sdk,
                arduino_cli=cli,
                config_file=config,
                build_root=root / "build",
                output=root / "evidence.json",
                jobs=2,
                compile_timeout=1200,
                negative_timeout=120,
            )
            paths = MODULE.validate_paths(arguments)
            self.assertNotEqual(paths["source"], paths["installed"])
            arguments.jobs = 3
            with self.assertRaisesRegex(MODULE.M33W05Failure, "jobs"):
                MODULE.validate_paths(arguments)
            arguments.jobs = 2
            arguments.build_root.mkdir()
            with self.assertRaisesRegex(MODULE.M33W05Failure, "덮어쓰지"):
                MODULE.validate_paths(arguments)
            arguments.build_root = root / "fresh-build"
            arguments.output = arguments.build_root / "evidence.json"
            with self.assertRaisesRegex(MODULE.M33W05Failure, "build root 밖"):
                MODULE.validate_paths(arguments)

    def test_installed_snapshot_requires_clean_exact_revision(self) -> None:
        """! @brief 설치 checkout은 exact source와 같은 clean revision이어야 합니다. """

        installed = Path("C:/installed-platform")
        revision = "1" * 40

        with mock.patch.object(
            MODULE,
            "git_output",
            side_effect=("", revision),
        ):
            self.assertEqual(
                revision,
                MODULE.verify_installed_snapshot(installed, revision),
            )

        for outputs, message in (
            ((" M libraries/example-metadata.json",), "clean"),
            (("", "2" * 40), "revision"),
        ):
            with self.subTest(message=message):
                with mock.patch.object(
                    MODULE,
                    "git_output",
                    side_effect=outputs,
                ):
                    with self.assertRaisesRegex(MODULE.M33W05Failure, message):
                        MODULE.verify_installed_snapshot(installed, revision)

    def test_evidence_write_is_utf8_and_replaces_atomically(self) -> None:
        """! @brief JSON evidence가 완전한 UTF-8 문서로 교체됩니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-w05-evidence-") as temporary:
            output = Path(temporary) / "nested" / "evidence.json"
            MODULE.write_evidence(output, {"status": "IN_PROGRESS", "설명": "검사"})
            MODULE.write_evidence(output, {"status": "PASS", "count": 204})
            self.assertEqual(
                {"status": "PASS", "count": 204},
                json.loads(output.read_text(encoding="utf-8")),
            )
            self.assertFalse(output.with_suffix(".json.tmp").exists())

    def test_public_evidence_rejects_path_uid_and_secret(self) -> None:
        """! @brief 절대 경로·raw UID·secret은 shard artifact 기록 전에 거부합니다. """

        for value in (
            {"failure_tail": ["C:\\Users\\runner\\secret.txt"]},
            {"raw_uid": "0011223344556677"},
            {"failure_tail": ["token=do-not-publish"]},
        ):
            with self.subTest(value=value):
                with self.assertRaises(MODULE.M33W05Failure):
                    MODULE.validate_public_values(value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
