#!/usr/bin/env python3
"""! @brief M9 영구 cache key, lock, LRU와 source identity 계약을 검증합니다. """

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "nu54-builder"
    / "src"
    / "nu54_builder.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("nu54_builder_m9", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"nu54-builder module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)


class M9CacheContractTests(unittest.TestCase):
    """! @brief persistent build cache의 host-only 안전 계약을 검증합니다. """

    def setUp(self) -> None:
        """! @brief 시험마다 독립된 cache와 source fixture를 생성합니다. """

        self.temporary = tempfile.TemporaryDirectory(prefix="n54-m9-host-")
        self.root = Path(self.temporary.name)
        self.cache_root = self.root / "cache"

    def tearDown(self) -> None:
        """! @brief 환경 변수를 복원하고 임시 fixture를 제거합니다. """

        self.temporary.cleanup()

    def create_entry(
        self, key: str, *, access: str, size: int = 16, pinned: bool = False
    ) -> Path:
        """! @brief LRU 시험용 유효한 cache entry를 생성합니다. """

        entry = self.cache_root / "v1" / key[:2] / key[:32]
        entry.mkdir(parents=True)
        (entry / "payload.bin").write_bytes(b"x" * size)
        (entry / "access.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "cache_key": key,
                    "last_accessed_at_utc": access,
                }
            ),
            encoding="utf-8",
        )
        (entry / "state.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "cache_key": key,
                    "state": "ready",
                    "first_configure_complete": True,
                }
            ),
            encoding="utf-8",
        )
        if pinned:
            (entry / ".pin").write_text("pinned\n", encoding="utf-8")
        return entry

    def test_canonical_manifest_key_ignores_dictionary_order(self) -> None:
        """! @brief 같은 canonical JSON은 field 순서와 무관하게 같은 key를 얻습니다. """

        first = {"schema": 1, "target": {"board": "nu54dk", "fqbn": "nucode"}}
        second = {"target": {"fqbn": "nucode", "board": "nu54dk"}, "schema": 1}
        self.assertEqual(
            MODULE.cache_key_for_manifest(first), MODULE.cache_key_for_manifest(second)
        )

    def test_cache_workspace_uses_bounded_key_and_schema_namespace(self) -> None:
        """! @brief Windows 경로를 제한한 directory key가 schema namespace에 포함됩니다. """

        previous = os.environ.get("NUCODE_BUILD_CACHE_ROOT")
        os.environ["NUCODE_BUILD_CACHE_ROOT"] = str(self.cache_root)
        try:
            key = "ab" + "1" * 62
            workspace = MODULE.cache_workspace(key)
            self.assertEqual(workspace, self.cache_root / "v1" / "ab" / key[:32])
        finally:
            if previous is None:
                os.environ.pop("NUCODE_BUILD_CACHE_ROOT", None)
            else:
                os.environ["NUCODE_BUILD_CACHE_ROOT"] = previous

    def test_tree_content_hash_detects_content_and_path(self) -> None:
        """! @brief dirty Core 내용과 상대 경로 변경이 fingerprint에 반영됩니다. """

        source = self.root / "platform"
        (source / "cores").mkdir(parents=True)
        implementation = source / "cores" / "Arduino.cpp"
        implementation.write_text("first\n", encoding="utf-8")
        first = MODULE.tree_content_sha256(source, ("cores",))
        implementation.write_text("second\n", encoding="utf-8")
        second = MODULE.tree_content_sha256(source, ("cores",))
        self.assertNotEqual(first, second)

    def test_target_sdk_toolchain_and_board_identity_invalidate_key(self) -> None:
        """! @brief 비호환 target/tool identity 변경은 모두 다른 full key를 만듭니다. """

        baseline = {
            "schema_version": 1,
            "target": {"fqbn": "nucode:zephyr:nu54dk", "board": "nu54dk"},
            "board_package": {"revision": "board-a", "content": "sha256:board-a"},
            "ncs": {"nrf_revision": "nrf-a", "zephyr_revision": "zephyr-a"},
            "toolchain": {"bundle_id": "bundle-a", "compiler": "gcc-a"},
        }
        baseline_key = MODULE.cache_key_for_manifest(baseline)
        mutations = (
            ("target", "fqbn", "nucode:zephyr:nu54dk:menu=x"),
            ("board_package", "content", "sha256:board-b"),
            ("ncs", "nrf_revision", "nrf-b"),
            ("ncs", "zephyr_revision", "zephyr-b"),
            ("toolchain", "bundle_id", "bundle-b"),
            ("toolchain", "compiler", "gcc-b"),
        )
        for section, field, value in mutations:
            changed = json.loads(json.dumps(baseline))
            changed[section][field] = value
            self.assertNotEqual(
                MODULE.cache_key_for_manifest(changed),
                baseline_key,
                msg=f"cache key did not include {section}.{field}",
            )

    def test_actual_input_collector_tracks_board_sdk_and_toolchain_identity(self) -> None:
        """! @brief 실제 collector가 board/NCS/Zephyr/compiler 입력을 key에 포함합니다. """

        platform = self.root / "platform"
        sketch = self.root / "sketch"
        board = platform / "board_package" / "NU54DK_Zephyr_DTS"
        ncs = self.root / "ncs"
        toolchain = self.root / "toolchains" / "bundle-a"
        (board / "boards" / "nucode" / "nu54dk").mkdir(parents=True)
        (ncs / "nrf").mkdir(parents=True)
        (ncs / "zephyr").mkdir(parents=True)
        toolchain.mkdir(parents=True)
        sketch.mkdir()
        (platform / "platform.txt").write_text("version=a\n", encoding="utf-8")
        board_file = board / "boards" / "nucode" / "nu54dk" / "board.yml"
        board_file.write_text("board=a\n", encoding="utf-8")
        (ncs / "nrf" / "west.yml").write_text("manifest: a\n", encoding="utf-8")
        (ncs / "zephyr" / "VERSION").write_text("VERSION_MAJOR=4\n", encoding="utf-8")
        (toolchain / "environment.json").write_text("{}\n", encoding="utf-8")
        (toolchain / "manifest.json").write_text("{}\n", encoding="utf-8")
        compiler = toolchain / "g++.exe"
        compiler.write_bytes(b"fixture")
        paths = {
            "platform_root": platform,
            "sketch_root": sketch,
        }
        args = argparse.Namespace(fqbn="nucode:zephyr:nu54dk", board=MODULE.DEFAULT_BOARD)
        tools = {
            "ncs_root": ncs,
            "toolchain_root": toolchain,
            "compiler": compiler,
            "environment": {},
        }
        revisions = {
            MODULE.path_key(board): "a" * 40,
            MODULE.path_key(ncs / "nrf"): "b" * 40,
            MODULE.path_key(ncs / "zephyr"): "c" * 40,
        }

        def collect(*, compiler_identity: str = "gcc-a") -> dict[str, object]:
            with (
                mock.patch.object(
                    MODULE,
                    "exact_git_revision",
                    side_effect=lambda value: revisions[MODULE.path_key(value)],
                ),
                mock.patch.object(
                    MODULE, "compiler_version", return_value=compiler_identity
                ),
            ):
                return MODULE.cache_input_manifest(paths, args, tools)

        baseline = collect()
        baseline_key = MODULE.cache_key_for_manifest(baseline)
        self.assertEqual(baseline["board_package"]["revision"], "a" * 40)
        self.assertEqual(baseline["ncs"]["nrf_revision"], "b" * 40)
        self.assertEqual(baseline["ncs"]["zephyr_revision"], "c" * 40)
        self.assertEqual(baseline["toolchain"]["compiler"], "gcc-a")

        board_file.write_text("board=b\n", encoding="utf-8")
        self.assertNotEqual(MODULE.cache_key_for_manifest(collect()), baseline_key)
        board_file.write_text("board=a\n", encoding="utf-8")

        revisions[MODULE.path_key(ncs / "nrf")] = "d" * 40
        self.assertNotEqual(MODULE.cache_key_for_manifest(collect()), baseline_key)
        revisions[MODULE.path_key(ncs / "nrf")] = "b" * 40

        revisions[MODULE.path_key(ncs / "zephyr")] = "e" * 40
        self.assertNotEqual(MODULE.cache_key_for_manifest(collect()), baseline_key)
        revisions[MODULE.path_key(ncs / "zephyr")] = "c" * 40

        self.assertNotEqual(
            MODULE.cache_key_for_manifest(collect(compiler_identity="gcc-b")), baseline_key
        )
        (toolchain / "environment.json").write_text('{"changed":true}\n', encoding="utf-8")
        self.assertNotEqual(MODULE.cache_key_for_manifest(collect()), baseline_key)

    def test_generated_source_identity_is_build_path_independent(self) -> None:
        """! @brief 다른 Arduino 임시 build path가 같은 Sketch mirror 이름을 사용합니다. """

        sketch = self.root / "Sketch"
        platform_root = self.root / "platform"
        identities = []
        for name in ("build-a", "build-b"):
            build = self.root / name
            source = build / "sketch" / "Sketch.ino.cpp"
            source.parent.mkdir(parents=True)
            source.write_text("void setup() {}\n", encoding="utf-8")
            identities.append(
                MODULE.source_logical_identity(
                    source,
                    {
                        "build_path": build,
                        "sketch_root": sketch,
                        "platform_root": platform_root,
                    },
                )
            )
        self.assertEqual(identities[0], identities[1])

    def test_generated_source_categories_do_not_share_a_mirror(self) -> None:
        """! @brief sketch와 library의 같은 파일명이 별도 mirror source로 유지됩니다. """

        build = self.root / "build"
        sketch = self.root / "sketch"
        platform = self.root / "platform"
        app = self.root / "app"
        sketch.mkdir()
        first = build / "sketch" / "Shared.cpp"
        second = build / "libraries" / "Fixture" / "Shared.cpp"
        first.parent.mkdir(parents=True)
        second.parent.mkdir(parents=True)
        first.write_text("int sketch_shared = 1;\n", encoding="utf-8")
        second.write_text("int library_shared = 2;\n", encoding="utf-8")
        records = [
            {"source": first.as_posix(), "include_dirs": []},
            {"source": second.as_posix(), "include_dirs": []},
        ]
        sources, provenance, _ = MODULE.write_source_manifest(
            {
                "build_path": build,
                "sketch_root": sketch,
                "platform_root": platform,
                "app": app,
            },
            records,
        )
        compiled = [Path(item["compiled_path"]) for item in provenance["sources"]]
        self.assertEqual(sources, [first, second])
        self.assertEqual(len({MODULE.path_key(path) for path in compiled}), 2)
        self.assertEqual(compiled[0].read_bytes(), first.read_bytes())
        self.assertEqual(compiled[1].read_bytes(), second.read_bytes())

    def test_external_library_sources_keep_private_header_semantics(self) -> None:
        """! @brief 각 library source를 원본 경로에서 컴파일하고 include 순서를 보존합니다. """

        build = self.root / "build"
        sketch = self.root / "sketch"
        platform = self.root / "platform"
        app = self.root / "app"
        sketch.mkdir()
        libraries = []
        records = []
        for name, value in (("Alpha", 1), ("Beta", 2)):
            library = self.root / name
            library.mkdir()
            (library / "Config.h").write_text(f"#define VALUE {value}\n", encoding="utf-8")
            source = library / "Shared.cpp"
            source.write_text('#include "Config.h"\nint value = VALUE;\n', encoding="utf-8")
            libraries.append(library)
            records.append(
                {"source": source.as_posix(), "include_dirs": [library.as_posix()]}
            )
        _, provenance, _ = MODULE.write_source_manifest(
            {
                "build_path": build,
                "sketch_root": sketch,
                "platform_root": platform,
                "app": app,
            },
            records,
        )
        compiled = [Path(item["compiled_path"]) for item in provenance["sources"]]
        self.assertEqual([path.parent for path in compiled], libraries)
        include_paths = [Path(item["path"]) for item in provenance["include_roots"]]
        self.assertEqual(include_paths[:3], [sketch, libraries[0], libraries[1]])

    def test_parent_build_flags_are_removed_before_toolchain_environment(self) -> None:
        """! @brief shell의 build flag가 canonical key 밖에서 child build를 바꾸지 못합니다. """

        toolchain = self.root / "toolchain"
        toolchain.mkdir()
        (toolchain / "environment.json").write_text(
            json.dumps(
                {
                    "env_vars": [
                        {"key": "ZEPHYR_SDK_INSTALL_DIR", "type": "string", "value": "official"}
                    ]
                }
            ),
            encoding="utf-8",
        )
        overrides = {key: "untracked-value" for key in MODULE.BUILD_ENVIRONMENT_OVERRIDE_KEYS}
        with mock.patch.dict(os.environ, overrides, clear=False):
            environment = MODULE.apply_toolchain_environment(toolchain)
        for key in MODULE.BUILD_ENVIRONMENT_OVERRIDE_KEYS:
            self.assertNotIn(key, environment)
        self.assertEqual(environment["ZEPHYR_SDK_INSTALL_DIR"], "official")

    def test_probe_mutex_identity_does_not_depend_on_user_temp_path(self) -> None:
        """! @brief 같은 probe UID는 사용자별 TEMP가 달라도 같은 Global mutex를 사용합니다. """

        logical = "probe:cmsis-dap-v2-1234"
        first = MODULE.operating_system_lock_identity(self.root / "user-a", logical)
        second = MODULE.operating_system_lock_identity(self.root / "user-b", logical)
        self.assertEqual(first, second)

    def test_cache_root_inside_platform_fingerprint_is_rejected(self) -> None:
        """! @brief cache가 platform hash에 자기 자신을 포함하는 배치를 거부합니다. """

        platform = self.root / "platform"
        board = platform / "board_package" / "NU54DK_Zephyr_DTS" / "boards" / "nucode" / "nu54dk"
        board.mkdir(parents=True)
        (board / "board.yml").write_text("board: fixture\n", encoding="utf-8")
        sketch = self.root / "sketch"
        sketch.mkdir()
        args = argparse.Namespace(
            platform_root=str(platform),
            build_path=str(self.root / "build"),
            sketch_root=str(sketch),
            fqbn="nucode:zephyr:nu54dk",
            project_name="Fixture.ino",
            board=MODULE.DEFAULT_BOARD,
        )
        with mock.patch.dict(
            os.environ,
            {"NUCODE_BUILD_CACHE_ROOT": str(platform / "cache")},
            clear=False,
        ):
            with self.assertRaisesRegex(MODULE.AdapterError, "fingerprint"):
                MODULE.prepare(args)

    def test_prepare_graph_invalidation_removes_only_owned_placeholders(self) -> None:
        """! @brief library 재선택 전 record와 build 내부 placeholder만 무효화합니다. """

        build = self.root / "build"
        records = build / MODULE.CONTEXT_DIRECTORY / "records"
        records.mkdir(parents=True)
        object_path = build / "libraries" / "Fixture" / "Fixture.cpp.o"
        object_path.parent.mkdir(parents=True)
        object_path.write_bytes(b"")
        dependency = object_path.with_suffix(".d")
        dependency.write_text("old\n", encoding="utf-8")
        record = MODULE.record_path(records, object_path)
        MODULE.atomic_write_json(
            record,
            {
                "schema_version": MODULE.SOURCE_RECORD_SCHEMA_VERSION,
                "object": object_path.as_posix(),
            },
        )
        unrelated = build / "keep.txt"
        unrelated.write_text("keep\n", encoding="utf-8")
        MODULE.invalidate_source_records(
            {"records": records, "build_path": build}
        )
        self.assertFalse(record.exists())
        self.assertFalse(object_path.exists())
        self.assertFalse(dependency.exists())
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep\n")

    def test_dead_local_lock_is_recovered(self) -> None:
        """! @brief 종료된 같은 host PID의 stale lock만 자동 회수합니다. """

        lock_root = self.root / "lock"
        lock_root.mkdir()
        (lock_root / ".adapter.lock").write_text(
            json.dumps(
                {
                    "pid": 2_000_000_000,
                    "host": socket.gethostname(),
                    "token": "stale",
                }
            ),
            encoding="utf-8",
        )
        with MODULE.build_lock(lock_root, operation="unit-test", timeout_seconds=0.2):
            owner = MODULE.read_lock_document(lock_root / ".adapter.lock")
            self.assertEqual(owner["pid"], os.getpid())
        self.assertFalse((lock_root / ".adapter.lock").exists())

    def test_foreign_metadata_does_not_block_local_os_lock(self) -> None:
        """! @brief local-only cache에서는 stale 외부 metadata보다 OS lock을 신뢰합니다. """

        lock_root = self.root / "foreign-lock"
        lock_root.mkdir()
        lock_path = lock_root / ".adapter.lock"
        lock_path.write_text(
            json.dumps({"pid": 1, "host": "different-host", "token": "foreign"}),
            encoding="utf-8",
        )
        with MODULE.build_lock(lock_root, timeout_seconds=0.05):
            owner = MODULE.read_lock_document(lock_path)
            self.assertEqual(owner["host"], socket.gethostname())
        self.assertFalse(lock_path.exists())

    def test_live_lock_serializes_two_workers(self) -> None:
        """! @brief 같은 cache의 두 worker가 lock 임계구역에 동시에 진입하지 않습니다. """

        lock_root = self.root / "serialized-lock"
        first_entered = threading.Event()
        release_first = threading.Event()
        second_entered = threading.Event()

        def first_worker() -> None:
            with MODULE.build_lock(lock_root, operation="first", timeout_seconds=2.0):
                first_entered.set()
                release_first.wait(timeout=2.0)

        def second_worker() -> None:
            first_entered.wait(timeout=2.0)
            with MODULE.build_lock(lock_root, operation="second", timeout_seconds=2.0):
                second_entered.set()

        first_thread = threading.Thread(target=first_worker)
        second_thread = threading.Thread(target=second_worker)
        first_thread.start()
        second_thread.start()
        self.assertTrue(first_entered.wait(timeout=1.0))
        time.sleep(0.1)
        self.assertFalse(second_entered.is_set())
        release_first.set()
        first_thread.join(timeout=2.0)
        second_thread.join(timeout=2.0)
        self.assertTrue(second_entered.is_set())
        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())

    def test_os_lock_serializes_processes_and_recovers_after_termination(self) -> None:
        """! @brief 별도 process의 lock을 차단하고 owner 종료 뒤 OS가 자동 회수합니다. """

        lock_root = self.root / "process-lock"
        child_code = r'''
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location("nu54_child", Path(sys.argv[1]))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with module.build_lock(Path(sys.argv[2]), operation="child", timeout_seconds=2.0):
    print("READY", flush=True)
    sys.stdin.readline()
'''
        process = subprocess.Popen(
            [sys.executable, "-c", child_code, str(MODULE_PATH), str(lock_root)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(process.stdout.readline().strip(), "READY")
            with self.assertRaisesRegex(MODULE.AdapterError, "대기 시간이 초과"):
                with MODULE.build_lock(lock_root, timeout_seconds=0.05):
                    pass
            process.terminate()
            process.wait(timeout=3.0)
            with MODULE.build_lock(lock_root, operation="recovered", timeout_seconds=1.0):
                owner = MODULE.read_lock_document(lock_root / ".adapter.lock")
                self.assertEqual(owner["pid"], os.getpid())
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3.0)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()

    def test_lru_prune_preserves_current_and_pinned_entries(self) -> None:
        """! @brief quota 정리는 오래된 비보호 entry만 제거합니다. """

        oldest = "11" + "1" * 62
        current = "22" + "2" * 62
        pinned = "33" + "3" * 62
        oldest_path = self.create_entry(oldest, access="2026-01-01T00:00:00+00:00")
        current_path = self.create_entry(current, access="2026-01-02T00:00:00+00:00")
        pinned_path = self.create_entry(
            pinned, access="2025-01-01T00:00:00+00:00", pinned=True
        )
        result = MODULE.prune_build_cache(
            current_key=current,
            root=self.cache_root,
            max_bytes=10**9,
            max_entries=2,
        )
        self.assertFalse(oldest_path.exists())
        self.assertTrue(current_path.exists())
        self.assertTrue(pinned_path.exists())
        self.assertEqual([item["key"] for item in result["removed"]], [oldest])

    def test_byte_quota_prune_preserves_active_lock(self) -> None:
        """! @brief byte quota에서도 활성 lock을 건너뛰고 비활성 entry를 정리합니다. """

        locked_key = "77" + "7" * 62
        removable_key = "88" + "8" * 62
        locked = self.create_entry(
            locked_key, access="2025-01-01T00:00:00+00:00", size=64
        )
        removable = self.create_entry(
            removable_key, access="2026-01-01T00:00:00+00:00", size=64
        )
        entered = threading.Event()
        release = threading.Event()

        def worker() -> None:
            with MODULE.build_lock(locked, operation="active-build", timeout_seconds=2.0):
                entered.set()
                release.wait(timeout=2.0)

        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(entered.wait(timeout=1.0))
        try:
            result = MODULE.prune_build_cache(
                root=self.cache_root,
                max_bytes=1,
                max_entries=10,
            )
            self.assertTrue(locked.exists())
            self.assertFalse(removable.exists())
            self.assertEqual([item["key"] for item in result["removed"]], [removable_key])
            self.assertEqual(result["skipped"][0]["directory_key"], locked_key[:32])
        finally:
            release.set()
            thread.join(timeout=2.0)

    def test_removed_entry_can_be_recreated_without_compiler_cache(self) -> None:
        """! @brief 단일 tree 삭제 후 같은 key state를 다시 만들며 compiler cache를 보존합니다. """

        key = "99" + "9" * 62
        entry = self.create_entry(key, access="2026-01-01T00:00:00+00:00")
        compiler_cache = self.cache_root / "compiler-cache"
        compiler_cache.mkdir(parents=True)
        marker = compiler_cache / "marker"
        marker.write_text("keep\n", encoding="utf-8")
        MODULE.remove_cache_entry(key, root=self.cache_root)
        self.assertFalse(entry.exists())
        recreated = MODULE.transition_cache_state(entry, key, "configuring")
        self.assertEqual(recreated["cache_key"], key)
        self.assertTrue((entry / "state.json").is_file())
        self.assertTrue(marker.is_file())

    def test_remove_rejects_invalid_key_and_active_lock(self) -> None:
        """! @brief 모호한 경로와 활성 lock이 있는 entry 삭제를 차단합니다. """

        with self.assertRaisesRegex(MODULE.AdapterError, "형식"):
            MODULE.remove_cache_entry("../outside", root=self.cache_root)
        key = "44" + "4" * 62
        entry = self.create_entry(key, access="2026-01-01T00:00:00+00:00")
        entered = threading.Event()
        release = threading.Event()

        def worker() -> None:
            with MODULE.build_lock(entry, operation="active-build", timeout_seconds=2.0):
                entered.set()
                release.wait(timeout=2.0)

        thread = threading.Thread(target=worker)
        thread.start()
        self.assertTrue(entered.wait(timeout=1.0))
        try:
            with self.assertRaisesRegex(MODULE.AdapterError, "E_CACHE_BUSY"):
                MODULE.remove_cache_entry(key, root=self.cache_root, lock_timeout=0.05)
            self.assertTrue(entry.exists())
        finally:
            release.set()
            thread.join(timeout=2.0)

    def test_remove_rejects_truncated_key_collision(self) -> None:
        """! @brief 같은 128-bit prefix의 다른 전체 key를 대신 삭제하지 않습니다. """

        prefix = "66" + "6" * 30
        stored_key = prefix + "a" * 32
        requested_key = prefix + "b" * 32
        entry = self.create_entry(stored_key, access="2026-01-01T00:00:00+00:00")
        with self.assertRaisesRegex(MODULE.AdapterError, "E_CACHE_KEY_COLLISION"):
            MODULE.remove_cache_entry(requested_key, root=self.cache_root)
        self.assertTrue(entry.exists())

    def test_state_transition_preserves_created_time(self) -> None:
        """! @brief cache 상태 전이가 생성 시각과 누적 field를 보존합니다. """

        key = "55" + "5" * 62
        entry = self.cache_root / "v1" / key[:2] / key[:32]
        first = MODULE.transition_cache_state(entry, key, "configuring", recovery_count=0)
        second = MODULE.transition_cache_state(entry, key, "ready", first_configure_complete=True)
        self.assertEqual(first["created_at_utc"], second["created_at_utc"])
        self.assertEqual(second["state"], "ready")
        self.assertEqual(second["recovery_count"], 0)


if __name__ == "__main__":
    unittest.main()
