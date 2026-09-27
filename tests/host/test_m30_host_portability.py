#!/usr/bin/env python3
"""! @brief M30 HOST-W01~W03의 Host 판별·resolver·launcher 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
INVENTORY_PATH = REPOSITORY / "tools" / "nu54-builder" / "host-portability-inventory.json"
BUILDER_PATH = REPOSITORY / "tools" / "nu54-builder" / "src" / "nu54_builder.py"


def load_builder():
    """! @brief 격리 진입점과 같은 방식으로 production builder를 읽습니다. """

    name = "nu54_m30_host_portability"
    specification = importlib.util.spec_from_file_location(name, BUILDER_PATH)
    if specification is None or specification.loader is None:
        raise RuntimeError("builder module을 읽을 수 없습니다.")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


BUILDER = load_builder()


class M30HostPortabilityTests(unittest.TestCase):
    """! @brief 세 Host 공통 backend의 fail-closed 정적·unit gate입니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief 기계 inventory를 한 번 읽습니다. """

        cls.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    def test_inventory_is_complete_and_finite(self) -> None:
        """! @brief HOST-W01 항목의 고유 ID·상태·합계를 검사합니다. """

        self.assertEqual(self.inventory["schema_version"], 1)
        self.assertEqual(self.inventory["work_package"], "HOST-W01")
        items = self.inventory["items"]
        self.assertEqual(len(items), 12)
        self.assertEqual(len({entry["id"] for entry in items}), len(items))
        self.assertEqual({entry["status"] for entry in items}, {"resolved", "retained", "deferred"})
        counts = {status: sum(entry["status"] == status for entry in items)
                  for status in ("resolved", "retained", "deferred")}
        completion = self.inventory["completion"]
        self.assertTrue(completion["inventory_complete"])
        self.assertEqual(completion["unknown_items"], 0)
        for status, count in counts.items():
            self.assertEqual(completion[f"{status}_items"], count)
        for entry in items:
            for relative in entry["sources"]:
                self.assertTrue((REPOSITORY / relative).is_file(), relative)

    def test_runtime_windows_tokens_are_owned_by_inventory(self) -> None:
        """! @brief runtime의 Windows token이 inventory 밖에 새로 생기지 못하게 합니다. """

        owned = set(self.inventory["runtime_token_files"])
        roots = [
            REPOSITORY / "platform.txt",
            REPOSITORY / "tools" / "nu54-builder" / "nu54-builder.cmd",
            REPOSITORY / "tools" / "nu54-builder" / "nu54-builder.sh",
        ]
        roots.extend(sorted((REPOSITORY / "tools" / "nu54-builder" / "src").rglob("*.py")))
        tokens = (".exe", "LOCALAPPDATA", "USERPROFILE", "C:/", "Program Files", "PureWindowsPath")
        discovered = {
            path.relative_to(REPOSITORY).as_posix()
            for path in roots
            if any(token in path.read_text(encoding="utf-8") for token in tokens)
        }
        self.assertEqual(discovered - owned, set())

    def test_supported_host_matrix_is_explicit(self) -> None:
        """! @brief 승인한 세 Host와 제외 architecture를 정확히 판정합니다. """

        cases = (
            ({"system_name": "Windows", "machine": "AMD64", "version": "10"}, True),
            ({"system_name": "Linux", "machine": "x86_64", "distribution": "ubuntu", "version": "24.04"}, True),
            ({"system_name": "Darwin", "machine": "arm64", "version": "26.0"}, True),
            ({"system_name": "Windows", "machine": "arm64", "version": "11"}, False),
            ({"system_name": "Linux", "machine": "aarch64", "distribution": "ubuntu", "version": "26.04"}, False),
            ({"system_name": "Linux", "machine": "x86_64", "distribution": "fedora", "version": "42"}, False),
            ({"system_name": "Darwin", "machine": "x86_64", "version": "26.0"}, False),
            ({"system_name": "Darwin", "machine": "arm64", "version": "25.9"}, False),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                self.assertEqual(BUILDER.describe_host(**arguments)["supported"], expected)
        emulated = BUILDER.describe_host(
            system_name="Darwin", machine="arm64", version="26.0", native=False
        )
        self.assertFalse(emulated["supported"])

    def test_unknown_os_and_architecture_fail_closed(self) -> None:
        """! @brief 알 수 없는 OS·architecture와 미지원 설명자를 거부합니다. """

        with self.assertRaisesRegex(BUILDER.AdapterError, "E_HOST_OS"):
            BUILDER.canonical_host_os("Plan9")
        with self.assertRaisesRegex(BUILDER.AdapterError, "E_HOST_ARCH"):
            BUILDER.canonical_architecture("riscv64")
        descriptor = BUILDER.describe_host(
            system_name="Linux", machine="x86_64", distribution="ubuntu", version="22.04"
        )
        with self.assertRaisesRegex(BUILDER.AdapterError, "E_HOST_UNSUPPORTED"):
            BUILDER.require_supported_host(descriptor)

    def test_executable_resolver_uses_host_specific_names(self) -> None:
        """! @brief .exe와 POSIX 실행 권한을 같은 resolver에서 판정합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-host-tools-") as directory:
            root = Path(directory)
            windows_python = root / "opt" / "bin" / "python.exe"
            windows_python.parent.mkdir(parents=True)
            windows_python.write_bytes(b"MZ")
            self.assertEqual(
                BUILDER.resolve_toolchain_executable(root, "python", host_os="windows"),
                windows_python.resolve(),
            )
            windows_python.unlink()
            posix_python = root / "opt" / "bin" / "python3"
            posix_python.write_text("#!/bin/sh\n", encoding="utf-8")
            posix_python.chmod(posix_python.stat().st_mode | stat.S_IXUSR)
            self.assertEqual(
                BUILDER.resolve_toolchain_executable(root, "python", host_os="linux"),
                posix_python.resolve(),
            )
            with self.assertRaisesRegex(BUILDER.AdapterError, "E_TOOL_EXECUTABLE"):
                BUILDER.resolve_toolchain_executable(root, "west", host_os="linux")

    def test_user_roots_follow_each_host_contract(self) -> None:
        """! @brief LOCALAPPDATA·XDG·macOS Library root를 분리합니다. """

        home = Path("/users/nucode")
        windows = BUILDER.describe_host(system_name="Windows", machine="AMD64", version="10")
        linux = BUILDER.describe_host(
            system_name="Linux", machine="x86_64", distribution="ubuntu", version="24.04"
        )
        macos = BUILDER.describe_host(system_name="Darwin", machine="arm64", version="26")
        self.assertEqual(
            BUILDER.user_cache_root(windows, {"LOCALAPPDATA": "C:/Users/n/AppData/Local"}, home),
            Path("C:/Users/n/AppData/Local").resolve(),
        )
        self.assertEqual(
            BUILDER.user_cache_root(linux, {"XDG_CACHE_HOME": "/cache/n"}, home),
            Path("/cache/n").resolve(),
        )
        resolved_home = home.resolve()
        self.assertEqual(
            BUILDER.user_cache_root(macos, {}, home), resolved_home / "Library" / "Caches"
        )
        self.assertEqual(
            BUILDER.application_data_root(linux, {}, home), resolved_home / ".local" / "share"
        )

    def test_launchers_forward_to_one_backend_without_eval(self) -> None:
        """! @brief OS별 얇은 진입점과 동일 Python backend를 검사합니다. """

        properties = dict(
            line.split("=", 1)
            for line in (REPOSITORY / "platform.txt").read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#") and "=" in line
        )
        self.assertIn("nu54-builder.cmd", properties["nu54.builder.windows"])
        self.assertIn("nu54-builder.sh", properties["nu54.builder.linux"])
        self.assertIn("nu54-builder.sh", properties["nu54.builder.macosx"])
        shell = (REPOSITORY / "tools" / "nu54-builder" / "nu54-builder.sh").read_text(encoding="utf-8")
        batch = (REPOSITORY / "tools" / "nu54-builder" / "nu54-builder.cmd").read_text(encoding="utf-8")
        self.assertNotIn("eval ", shell)
        self.assertIn('"$@"', shell)
        self.assertIn("src/nu54_builder.py", shell)
        self.assertIn("src\\nu54_builder.py", batch)


if __name__ == "__main__":
    unittest.main()
