#!/usr/bin/env python3
"""! @brief M9 export, 복구, CLI와 flash 동시성 안전 계약을 검증합니다. """

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path, PureWindowsPath
import tempfile
import unittest
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "nu54-builder"
    / "src"
    / "nu54_builder.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("nu54_builder_m9_safety", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"nu54-builder module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)


class M9SafetyContractTests(unittest.TestCase):
    """! @brief 실패 및 경합 상황에서 공개 artifact와 cache를 보호하는지 검증합니다. """

    def setUp(self) -> None:
        """! @brief 시험별 독립 directory를 생성하고 cache 환경을 보존합니다. """

        self.temporary = tempfile.TemporaryDirectory(prefix="n54-m9-safety-")
        self.root = Path(self.temporary.name)
        self.previous_cache_root = os.environ.get("NUCODE_BUILD_CACHE_ROOT")
        os.environ["NUCODE_BUILD_CACHE_ROOT"] = str(self.root / "cache")

    def tearDown(self) -> None:
        """! @brief cache 환경과 임시 directory를 복원합니다. """

        if self.previous_cache_root is None:
            os.environ.pop("NUCODE_BUILD_CACHE_ROOT", None)
        else:
            os.environ["NUCODE_BUILD_CACHE_ROOT"] = self.previous_cache_root
        self.temporary.cleanup()

    def create_artifact_fixture(self) -> tuple[Path, dict[str, Path]]:
        """! @brief 네 종류 native artifact와 기존 export generation을 만듭니다. """

        build = self.root / "build"
        native = self.root / "native"
        build.mkdir()
        native.mkdir()
        artifacts: dict[str, Path] = {}
        for extension in ("elf", "hex", "bin", "map"):
            source = native / f"zephyr.{extension}"
            source.write_bytes(f"new-{extension}".encode("ascii"))
            artifacts[extension] = source
            (build / f"Blink.ino.{extension}").write_bytes(
                f"old-{extension}".encode("ascii")
            )
        return build, artifacts

    def test_transactional_export_publishes_one_verified_generation(self) -> None:
        """! @brief staging이 모두 끝난 뒤 네 artifact를 검증된 generation으로 교체합니다. """

        build, artifacts = self.create_artifact_fixture()
        exported = MODULE.export_artifacts_transactionally(artifacts, build, "Blink.ino")
        for extension, source in artifacts.items():
            destination = build / f"Blink.ino.{extension}"
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertEqual(exported[extension]["sha256"], MODULE.file_sha256(destination))
            self.assertEqual(exported[extension]["size"], destination.stat().st_size)
        staging = build / MODULE.CONTEXT_DIRECTORY / "artifact-staging"
        self.assertEqual(list(staging.iterdir()), [])

    def test_transactional_export_restores_old_generation_on_commit_failure(self) -> None:
        """! @brief 두 번째 artifact 교체 실패 시 이미 교체한 파일도 이전 값으로 복원합니다. """

        build, artifacts = self.create_artifact_fixture()
        old = {
            extension: (build / f"Blink.ino.{extension}").read_bytes()
            for extension in artifacts
        }
        real_replace = os.replace
        commit_count = 0
        injected = False

        def fail_second_commit(source: str | Path, destination: str | Path) -> None:
            nonlocal commit_count, injected
            target = Path(destination)
            if target.parent == build and target.name.startswith("Blink.ino.") and not injected:
                commit_count += 1
                if commit_count == 2:
                    injected = True
                    raise OSError("injected export failure")
            real_replace(source, destination)

        with mock.patch.object(MODULE.os, "replace", side_effect=fail_second_commit):
            with self.assertRaisesRegex(OSError, "injected export failure"):
                MODULE.export_artifacts_transactionally(artifacts, build, "Blink.ino")
        for extension, content in old.items():
            self.assertEqual((build / f"Blink.ino.{extension}").read_bytes(), content)

    def test_publish_metadata_failure_restores_artifacts_manifest_and_context(self) -> None:
        """! @brief export 뒤 metadata 실패도 이전 공개 generation 전체를 복구합니다. """

        build, artifacts = self.create_artifact_fixture()
        manifest = build / "Blink.ino.nu54-build.json"
        context_path = build / MODULE.CONTEXT_DIRECTORY / "context.json"
        old_context = {"schema_version": 2, "state": "built", "generation": "old"}
        new_context = {"schema_version": 2, "state": "built", "generation": "new"}
        old_manifest = {"schema_version": 2, "context": old_context, "generation": "old"}
        MODULE.atomic_write_json(manifest, old_manifest)
        MODULE.atomic_write_json(context_path, {"state": "configured", "generation": "new"})
        old_artifacts = {
            extension: (build / f"Blink.ino.{extension}").read_bytes()
            for extension in artifacts
        }

        with self.assertRaisesRegex(OSError, "injected metadata failure"):
            with MODULE.publish_artifact_generation(
                artifacts,
                build,
                "Blink.ino",
                manifest,
                context_path,
                old_context,
            ):
                MODULE.atomic_write_json(context_path, new_context)
                MODULE.atomic_write_json(
                    manifest,
                    {"schema_version": 2, "context": new_context, "generation": "new"},
                )
                raise OSError("injected metadata failure")

        for extension, content in old_artifacts.items():
            self.assertEqual((build / f"Blink.ino.{extension}").read_bytes(), content)
        self.assertEqual(
            MODULE.load_json_object(manifest, "E_TEST"), old_manifest
        )
        self.assertEqual(
            MODULE.load_json_object(context_path, "E_TEST"), old_context
        )

    def test_publish_keyboard_interrupt_restores_previous_generation(self) -> None:
        """! @brief metadata commit 중 Ctrl+C도 이전 공개 generation을 보존합니다. """

        build, artifacts = self.create_artifact_fixture()
        manifest = build / "Blink.ino.nu54-build.json"
        context_path = build / MODULE.CONTEXT_DIRECTORY / "context.json"
        old_context = {"schema_version": 2, "state": "built", "generation": "old"}
        old_manifest = {"schema_version": 2, "context": old_context, "generation": "old"}
        MODULE.atomic_write_json(manifest, old_manifest)
        MODULE.atomic_write_json(context_path, old_context)
        old_artifacts = {
            extension: (build / f"Blink.ino.{extension}").read_bytes()
            for extension in artifacts
        }
        with self.assertRaises(KeyboardInterrupt):
            with MODULE.publish_artifact_generation(
                artifacts,
                build,
                "Blink.ino",
                manifest,
                context_path,
                old_context,
            ):
                MODULE.atomic_write_json(context_path, {"generation": "interrupted"})
                raise KeyboardInterrupt
        for extension, content in old_artifacts.items():
            self.assertEqual((build / f"Blink.ino.{extension}").read_bytes(), content)
        self.assertEqual(MODULE.load_json_object(manifest, "E_TEST"), old_manifest)
        self.assertEqual(MODULE.load_json_object(context_path, "E_TEST"), old_context)

    def prepare_fixture(self) -> tuple[argparse.Namespace, Path, str, dict[str, object]]:
        """! @brief configure-failed cache 복구에 필요한 최소 fixture를 만듭니다. """

        platform = self.root / "platform"
        board_root = platform / "board_package" / "NU54DK_Zephyr_DTS"
        (board_root / "boards" / "nucode" / "nu54dk").mkdir(parents=True)
        (board_root / "boards" / "nucode" / "nu54dk" / "board.yml").write_text(
            "board: fixture\n", encoding="utf-8"
        )
        build = self.root / "arduino-build"
        sketch = self.root / "sketch"
        sketch.mkdir()
        args = argparse.Namespace(
            platform_root=str(platform),
            build_path=str(build),
            sketch_root=str(sketch),
            fqbn="nucode:zephyr:nu54dk",
            project_name="Blink.ino",
            board=MODULE.DEFAULT_BOARD,
        )
        input_manifest = {"schema_version": MODULE.CACHE_SCHEMA_VERSION, "fixture": "recovery"}
        cache_key = MODULE.cache_key_for_manifest(input_manifest)
        workspace = MODULE.cache_workspace(cache_key)
        (workspace / "build").mkdir(parents=True)
        (workspace / "build" / "CMakeCache.txt").write_text("old\n", encoding="utf-8")
        (workspace / "build" / "build.ninja").write_text("old\n", encoding="utf-8")
        MODULE.atomic_write_json(workspace / "input-manifest.json", input_manifest)
        MODULE.atomic_write_json(
            workspace / "state.json",
            {
                "schema_version": MODULE.CACHE_SCHEMA_VERSION,
                "cache_key": cache_key,
                "state": "failed",
                "first_configure_complete": False,
                "last_build_result": "configure-failed",
                "failure": "old failure",
                "pristine_configure_count": 1,
                "recovery_count": 0,
            },
        )
        tools: dict[str, object] = {
            "ncs_root": self.root / "ncs",
            "toolchain_root": self.root / "toolchain",
            "compiler": self.root / "toolchain" / "g++.exe",
            "size": self.root / "toolchain" / "size.exe",
            "ccache": None,
            "ccache_root": self.root / "cache" / "compiler-cache",
            "environment": {},
        }
        return args, workspace, cache_key, tools

    def test_west_build_working_directory_rejects_split_cache_volumes(self) -> None:
        """! @brief application과 build가 서로 다른 Windows volume이면 명시적으로 거부합니다. """

        paths = {
            "app": PureWindowsPath("C:/nu54-cache/app"),
            "zephyr_build": PureWindowsPath("D:/nu54-cache/build"),
        }
        with self.assertRaisesRegex(MODULE.AdapterError, "E_BUILD_VOLUME"):
            MODULE.west_build_working_directory(paths)

    def test_prepare_configure_uses_application_volume_across_windows_drives(self) -> None:
        """! @brief NCS와 cache drive가 달라도 configure의 cwd는 application 쪽을 사용합니다. """

        args, workspace, _, tools = self.prepare_fixture()
        tools["ncs_root"] = Path("D:/ncs/v3.4.0")
        with (
            mock.patch.object(MODULE, "tool_environment", return_value=tools),
            mock.patch.object(
                MODULE,
                "cache_input_manifest",
                return_value={
                    "schema_version": MODULE.CACHE_SCHEMA_VERSION,
                    "fixture": "recovery",
                },
            ),
            mock.patch.object(MODULE, "materialize_application"),
            mock.patch.object(MODULE, "configure_command", return_value=["configure"]),
            mock.patch.object(MODULE, "run_checked") as run_checked,
        ):
            MODULE.prepare(args)
        run_checked.assert_called_once()
        self.assertEqual(run_checked.call_args.kwargs["cwd"], workspace / "app")
        self.assertNotEqual(
            PureWindowsPath(str(run_checked.call_args.kwargs["cwd"])).drive.casefold(),
            PureWindowsPath(str(tools["ncs_root"])).drive.casefold(),
        )

    def test_configure_failed_tree_recovers_once_then_becomes_cache_hit(self) -> None:
        """! @brief 실패 cache는 pristine 1회 복구 후 configure-failed를 유지하지 않습니다. """

        args, workspace, cache_key, tools = self.prepare_fixture()
        with (
            mock.patch.object(MODULE, "tool_environment", return_value=tools),
            mock.patch.object(
                MODULE,
                "cache_input_manifest",
                return_value={"schema_version": MODULE.CACHE_SCHEMA_VERSION, "fixture": "recovery"},
            ),
            mock.patch.object(MODULE, "materialize_application"),
            mock.patch.object(MODULE, "configure_command", return_value=["configure"]),
            mock.patch.object(MODULE, "run_checked") as run_checked,
        ):
            first = MODULE.prepare(args)
            second = MODULE.prepare(args)
        self.assertEqual(run_checked.call_count, 1)
        self.assertEqual(first["configure_reason"], "state-recovery")
        self.assertEqual(second["configure_reason"], "cache-hit")
        state = MODULE.load_json_object(workspace / "state.json", "E_TEST")
        self.assertEqual(state["cache_key"], cache_key)
        self.assertEqual(state["state"], "ready")
        self.assertEqual(state["last_build_result"], "not-built")
        self.assertNotIn("failure", state)
        self.assertEqual(state["pristine_configure_count"], 2)
        self.assertEqual(state["recovery_count"], 1)

    def test_configure_failure_marks_cache_unusable(self) -> None:
        """! @brief pristine configure 실패 시 first-complete를 false로 고정하고 실패를 기록합니다. """

        args, workspace, _, tools = self.prepare_fixture()
        with (
            mock.patch.object(MODULE, "tool_environment", return_value=tools),
            mock.patch.object(
                MODULE,
                "cache_input_manifest",
                return_value={"schema_version": MODULE.CACHE_SCHEMA_VERSION, "fixture": "recovery"},
            ),
            mock.patch.object(MODULE, "materialize_application"),
            mock.patch.object(MODULE, "configure_command", return_value=["configure"]),
            mock.patch.object(MODULE, "run_checked", side_effect=RuntimeError("configure failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "configure failed"):
                MODULE.prepare(args)
        state = MODULE.load_json_object(workspace / "state.json", "E_TEST")
        self.assertEqual(state["state"], "failed")
        self.assertEqual(state["last_build_result"], "configure-failed")
        self.assertFalse(state["first_configure_complete"])

    def test_unknown_cache_option_fails_closed_before_dispatch(self) -> None:
        """! @brief destructive cache CLI의 오타를 무시하지 않고 action 호출 전에 거부합니다. """

        with (
            mock.patch.object(MODULE, "manage_cache") as manage_cache,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            result = MODULE.main(["cache", "clear", "--cache-rooot", str(self.root)])
        self.assertEqual(result, 2)
        manage_cache.assert_not_called()

    def test_passthrough_allowlist_is_exact(self) -> None:
        """! @brief include와 object 전달만 허용하고 option 오타를 거부합니다. """

        MODULE.validate_passthrough(
            "preprocess",
            ["-IC:/library/include", "-I", "C:/core", "-MMD", "-MF", "C:/build/a.d"],
        )
        MODULE.validate_passthrough("record", ["-IC:/library/include"])
        MODULE.validate_passthrough("link", ["C:/build/sketch.o", "C:/build/library.obj"])
        for command, values in (
            ("prepare", ["--verbsoe"]),
            ("preprocess", ["--typo"]),
            ("record", ["-I"]),
            ("link", ["--objects-typo"]),
            ("cache", ["--cache-rooot"]),
        ):
            with self.subTest(command=command, values=values):
                with self.assertRaises(MODULE.AdapterError):
                    MODULE.validate_passthrough(command, values)

    def test_flash_holds_session_cache_and_probe_locks_during_validation(self) -> None:
        """! @brief flash 검증과 write 전체가 session→cache→probe lock 순서를 유지합니다. """

        build = self.root / "flash-build"
        platform = self.root / "platform"
        sketch = self.root / "sketch"
        cache_key = "ab" + "1" * 62
        cache_root = self.root / "cache"
        workspace = MODULE.cache_workspace(cache_key, root=cache_root)
        context = {
            "schema_version": MODULE.SESSION_CONTEXT_SCHEMA_VERSION,
            "cache_root": cache_root.as_posix(),
            "cache_key": cache_key,
            "cache_dir": workspace.as_posix(),
            "ncs_root": (self.root / "ncs").as_posix(),
            "toolchain_root": (self.root / "toolchain").as_posix(),
            "toolchain_bundle_id": "toolchain",
            "cxx_compiler": (self.root / "toolchain" / "g++.exe").as_posix(),
        }
        args = argparse.Namespace(
            platform_root=str(platform),
            build_path=str(build),
            sketch_root=str(sketch),
            fqbn="nucode:zephyr:nu54dk",
            project_name="Blink.ino",
            board=MODULE.DEFAULT_BOARD,
            manifest=str(build / "Blink.ino.nu54-build.json"),
            runner="pyocd",
            probe_id=None,
            verbose=False,
        )
        active: list[str] = []
        events: list[str] = []

        @contextlib.contextmanager
        def fake_build_lock(root: Path, *, operation: str = "build", timeout_seconds: float = 1.0):
            del root, timeout_seconds
            active.append(operation)
            events.append(f"enter:{operation}")
            try:
                yield
            finally:
                events.append(f"exit:{operation}")
                active.remove(operation)

        @contextlib.contextmanager
        def fake_probe_lock(probe_id: str, timeout_seconds: float = 1.0):
            del probe_id, timeout_seconds
            active.append("probe")
            events.append("enter:probe")
            try:
                yield
            finally:
                events.append("exit:probe")
                active.remove("probe")

        def validate(_args: argparse.Namespace) -> dict[str, object]:
            self.assertEqual(active, ["flash-session", "flash-cache"])
            return {
                "manifest": {"context": context},
                "zephyr_build": workspace / "build",
                "build_path": build,
                "hex": build / "Blink.ino.hex",
                "hex_sha256": "1" * 64,
            }

        def write(*_args: object, **_kwargs: object) -> None:
            self.assertEqual(active, ["flash-session", "flash-cache", "probe"])

        tools = {
            "ncs_root": self.root / "ncs",
            "toolchain_root": self.root / "toolchain",
            "compiler": self.root / "toolchain" / "g++.exe",
            "environment": {},
        }
        with (
            mock.patch.object(MODULE, "build_lock", side_effect=fake_build_lock),
            mock.patch.object(MODULE, "probe_lock", side_effect=fake_probe_lock),
            mock.patch.object(MODULE, "tool_environment", return_value=tools),
            mock.patch.object(MODULE, "flash_environment", return_value={}),
            mock.patch.object(MODULE, "load_context", return_value=context),
            mock.patch.object(MODULE, "validate_flash_manifest", side_effect=validate),
            mock.patch.object(MODULE, "validate_runner_configuration"),
            mock.patch.object(MODULE, "select_pyocd_probe", return_value="PROBE"),
            mock.patch.object(MODULE, "build_flash_command", return_value=["flash"]),
            mock.patch.object(MODULE, "run_flash_process", side_effect=write),
        ):
            MODULE.flash(args)
        self.assertEqual(
            events,
            [
                "enter:flash-session",
                "enter:flash-cache",
                "enter:probe",
                "exit:probe",
                "exit:flash-cache",
                "exit:flash-session",
            ],
        )
        self.assertEqual(active, [])

    def test_flash_rejects_current_toolchain_identity_mismatch(self) -> None:
        """! @brief build와 다른 NCS/toolchain으로 flash하는 요청을 거부합니다. """

        context = {
            "ncs_root": (self.root / "ncs-a").as_posix(),
            "toolchain_root": (self.root / "toolchain-a").as_posix(),
            "toolchain_bundle_id": "toolchain-a",
            "cxx_compiler": (self.root / "toolchain-a" / "g++.exe").as_posix(),
        }
        tools = {
            "ncs_root": self.root / "ncs-b",
            "toolchain_root": self.root / "toolchain-b",
            "compiler": self.root / "toolchain-b" / "g++.exe",
        }
        with self.assertRaisesRegex(MODULE.AdapterError, "E_FLASH_TOOLCHAIN_MISMATCH"):
            MODULE.validate_flash_tool_identity(context, tools)


if __name__ == "__main__":
    unittest.main()
