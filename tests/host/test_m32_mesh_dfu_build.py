#!/usr/bin/env python3
"""! @brief Mesh DFU 네 역할의 signed candidate byte-binding을 검증합니다. """

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / "tools/ci"
if str(CI) not in sys.path:
    sys.path.insert(0, str(CI))

import m32_mesh_dfu_build as producer  # noqa: E402
import m33_w06_artifacts as artifacts  # noqa: E402


REVISION = "1" * 40


class M32MeshDfuBuildTests(unittest.TestCase):
    """! @brief 실제 build 없이 producer의 순서와 fail-closed 경계를 검사합니다. """

    def setUp(self) -> None:
        """! @brief 유효 MCUboot header를 가진 임시 candidate fixture를 만듭니다. """

        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.calls: list[tuple[str, list[str]]] = []
        self.mutation = None
        data = bytearray(2200)
        struct.pack_into("<I", data, 0, 0x96F3B83D)
        struct.pack_into("<H", data, 8, 0x800)
        struct.pack_into("<BBHI", data, 20, 2, 0, 0, 0)
        data[-3:] = b"ABC"
        self.data = bytes(data)

    def tearDown(self) -> None:
        """! @brief 시험별 임시 fixture를 정리합니다. """

        self.temporary.cleanup()

    def fake_build(self, command: list[str], **keywords) -> SimpleNamespace:
        """! @brief 실제 명령 인자로 cache와 signed candidate fixture를 생성합니다. """

        self.assertIs(keywords["shell"], False)
        self.assertIs(keywords["check"], False)
        self.assertIn("--build-opt=-j2", command)
        self.assertIn("-s", command)
        self.assertIn("-P", command)
        self.assertNotIn("-I", command)
        role = next(
            value.split("=", 1)[1]
            for value in command
            if value.startswith("-DM32_MDFU_ROLE=")
        )
        root = Path(command[command.index("-d") + 1])
        root.mkdir()
        values = [
            value[2:].replace("=", ":UNINITIALIZED=", 1)
            for value in command
            if value.startswith("-DM32_MDFU_")
        ]
        (root / "CMakeCache.txt").write_text(
            "\n".join(values) + "\n", encoding="utf-8"
        )
        (root / "domains.yaml").write_text("fixture\n", encoding="utf-8")
        if role == "candidate":
            candidate = root / producer.SIGNED_BIN
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(self.data)
        self.calls.append((role, command))
        if self.mutation is not None:
            changed = self.mutation(role, root)
            if changed is not None:
                return changed
        return SimpleNamespace(returncode=0)

    def execute(self, content_reader=None):
        """! @brief 주입 executor로 실제 orchestration 함수를 실행합니다. """

        return producer.execute_set(
            self.root / "sdk",
            self.root / "output",
            REVISION,
            2,
            {},
            self.fake_build,
            lambda _path: REVISION,
            content_reader or (lambda _path: ()),
        )

    def test_all_roles_use_one_actual_candidate_binding(self) -> None:
        """! @brief candidate를 한 번 만들고 같은 실제 hash·size를 세 역할에 전달합니다. """

        result = self.execute()
        expected_sha256 = hashlib.sha256(self.data).hexdigest()

        self.assertEqual(list(producer.ROLES), [role for role, _ in self.calls])
        self.assertEqual(
            expected_sha256, result["binding"]["candidate_sha256"]
        )
        self.assertEqual(2200, result["binding"]["candidate_size"])
        self.assertFalse(result["functional_hil"])
        for _role, command in self.calls[1:]:
            self.assertIn(
                "-DM32_MDFU_CANDIDATE_SHA256=" + expected_sha256,
                command,
            )
            self.assertIn("-DM32_MDFU_CANDIDATE_SIZE=2200", command)
        self.assertTrue(
            (self.root / "output/mesh-dfu-build-binding.json").is_file()
        )

    def test_candidate_failure_stops_dependents(self) -> None:
        """! @brief candidate build 실패 뒤 consumer를 실행하거나 PASS를 저장하지 않습니다. """

        self.mutation = lambda _role, _root: SimpleNamespace(returncode=7)

        with self.assertRaisesRegex(artifacts.ArtifactFailure, "candidate.*exit=7"):
            self.execute()

        self.assertEqual(["candidate"], [role for role, _ in self.calls])
        self.assertFalse(
            (self.root / "output/mesh-dfu-build-binding.json").exists()
        )

    def test_dependent_failure_preserves_role_and_exit(self) -> None:
        """! @brief consumer 실패의 역할·exit를 보존하고 후속 역할을 실행하지 않습니다. """

        self.mutation = lambda role, _root: SimpleNamespace(
            returncode=9 if role == "target_a" else 0
        )

        with self.assertRaisesRegex(artifacts.ArtifactFailure, "target_a.*exit=9"):
            self.execute()

        self.assertEqual(
            ["candidate", "distributor", "target_a"],
            [role for role, _ in self.calls],
        )

    def test_candidate_mutation_is_rejected(self) -> None:
        """! @brief consumer build 중 candidate byte가 바뀌면 즉시 거부합니다. """

        def mutate(role: str, root: Path):
            if role == "distributor":
                candidate = root.parent / "candidate" / producer.SIGNED_BIN
                candidate.write_bytes(self.data[:-1] + b"D")
            return None

        self.mutation = mutate

        with self.assertRaisesRegex(artifacts.ArtifactFailure, "candidate.*변경"):
            self.execute()

        self.assertEqual(2, len(self.calls))

    def test_placeholder_consumer_cache_is_rejected(self) -> None:
        """! @brief 기존 0*64/1 compile-only 기본값을 실제 binding으로 인정하지 않습니다. """

        def replace_binding(role: str, root: Path):
            if role == "distributor":
                (root / "CMakeCache.txt").write_text(
                    "M32_MDFU_ROLE:UNINITIALIZED=distributor\n"
                    "M32_MDFU_CANDIDATE_SHA256:UNINITIALIZED=" +
                    "0" * 64 + "\n"
                    "M32_MDFU_CANDIDATE_SIZE:UNINITIALIZED=1\n",
                    encoding="utf-8",
                )
            return None

        self.mutation = replace_binding

        with self.assertRaisesRegex(
            artifacts.ArtifactFailure, "distributor.*SHA256"
        ):
            self.execute()

    def test_bad_candidate_header_stops_consumers(self) -> None:
        """! @brief 유효하지 않은 signed header는 consumer 전에 거부합니다. """

        self.data = b"bad image"

        with self.assertRaisesRegex(artifacts.ArtifactFailure, "header/version"):
            self.execute()

        self.assertEqual(["candidate"], [role for role, _ in self.calls])

    def test_dirty_source_before_start_does_not_create_output(self) -> None:
        """! @brief 같은 HEAD라도 Core dirty source면 output 생성 전에 거부합니다. """

        with self.assertRaisesRegex(artifacts.ArtifactFailure, "Core.*clean"):
            self.execute(
                lambda path: ("changed.cpp",)
                if path == producer.REPOSITORY else ()
            )

        self.assertFalse((self.root / "output").exists())
        self.assertEqual([], self.calls)

    def test_partial_role_set_is_rejected(self) -> None:
        """! @brief 네 역할 중 일부만 있는 index binding을 거부합니다. """

        with self.assertRaisesRegex(artifacts.ArtifactFailure, "네 역할"):
            artifacts.validate_mesh_dfu_bindings({"candidate": self.root})

    def test_pinned_environment_replaces_foreign_python_values(self) -> None:
        """! @brief 상속된 foreign Python HOME/PATH를 고정 bundle 값으로 교체합니다. """

        bundle = self.root / "mock-bundle-id"
        python = bundle / "opt/bin/python.exe"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"fixture")
        (bundle / "environment.json").write_text(json.dumps({
            "env_vars": [{
                "type": "relative_paths",
                "key": "PYTHONPATH",
                "values": [
                    "opt/bin",
                    "opt/bin/Lib",
                    "opt/bin/Lib/site-packages",
                ],
                "existing_value_treatment": "overwrite",
            }],
        }), encoding="utf-8")
        lock = {"windows_toolchain": {"bundle_id": "mock-bundle-id"}}

        with mock.patch.object(sys, "executable", str(python)):
            environment = producer.pinned_python_environment(
                self.root / "sdk",
                bundle,
                lock,
                {"PYTHONHOME": "foreign", "PYTHONPATH": "foreign"},
            )

        self.assertEqual(str(python.parent), environment["PYTHONHOME"])
        self.assertEqual("1", environment["PYTHONNOUSERSITE"])
        self.assertNotIn("foreign", environment["PYTHONPATH"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
