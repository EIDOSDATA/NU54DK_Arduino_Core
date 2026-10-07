#!/usr/bin/env python3
"""! @brief W06 current-S runtime fixture producer의 host 계약을 검증합니다. """
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "tests/hil/nu54dk/m33_w06_runtime_fixture.py"
SPEC = importlib.util.spec_from_file_location("m33_w06_runtime_fixture", TARGET)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("runtime fixture producer를 불러올 수 없습니다")
PRODUCER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PRODUCER
SPEC.loader.exec_module(PRODUCER)
from m33_profile_idle_fixture import resolve_idle_build_sources

HASHES = {
    "client": "1" * 64,
    "peer": "2" * 64,
    "third": "3" * 64,
}


def sha256(path: Path) -> str:
    """! @brief test file의 SHA-256을 반환합니다. """

    return hashlib.sha256(path.read_bytes()).hexdigest()


class RuntimeProducerContractTests(unittest.TestCase):
    """! @brief build index·명령·runtime manifest fail-closed 계약을 검증합니다. """

    def test_ecosystem_builder_keeps_cwd_and_cache_outside_sdk(self) -> None:
        """! @brief SDK와 작업 drive가 달라도 source cwd와 output cache를 명시합니다. """

        sys.path.insert(0, str(ROOT / "tools/nu54-builder/src"))
        from nu54_builder_impl import environment

        ecosystem = PRODUCER.ecosystem
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "ecosystem"
            args = argparse.Namespace(sdk=Path("C:/ncs/v3.4.0"),
                                      toolchain=Path("C:/ncs/toolchains/dcbdc366a1"),
                                      output=output, role="client", retry=False)

            def build(command, **kwargs):
                self.assertEqual(ecosystem.ROOT, kwargs["cwd"])
                self.assertNotEqual(args.sdk, kwargs["cwd"])
                self.assertIn("-B", command)
                self.assertIn("-DUSER_CACHE_DIR=" + (output / "cache").as_posix(), command)
                self.assertEqual(str(args.sdk.resolve() / "zephyr"), kwargs["env"]["ZEPHYR_BASE"])
                target = output / "build/zephyr"
                target.mkdir(parents=True)
                for name in ("zephyr.hex", "zephyr.elf", ".config"):
                    (target / name).write_bytes(b"fixture")
                return subprocess.CompletedProcess(command, 0, b"build ok", b"")

            with mock.patch.object(ecosystem, "validate_locked_sources", return_value={
                    "ncs": "a" * 40, "zephyr": "b" * 40, "board": "c" * 40}), \
                    mock.patch.object(ecosystem, "source_identity", return_value="a" * 104), \
                    mock.patch.object(ecosystem, "revision", return_value="a" * 40), \
                    mock.patch.object(ecosystem, "source_clean", return_value=True), \
                    mock.patch.object(environment, "apply_toolchain_environment", return_value={}), \
                    mock.patch.object(ecosystem.subprocess, "run", side_effect=build), \
                    mock.patch("builtins.print"):
                ecosystem.build(args)
            self.assertTrue((output / "build-manifest.json").is_file())

    def test_build_commands_are_sequential_and_forbid_dangerous_modes(self) -> None:
        """! @brief 두 ecosystem 역할만 고정 순서로 안전하게 build합니다. """

        commands = PRODUCER.build_ecosystem_commands(
            Path("C:/toolchain/python.exe"),
            Path("C:/ncs/v3.4.0"),
            Path("C:/ncs/toolchains/dcbdc366a1"),
            Path("C:/w06-runtime"),
        )
        self.assertEqual(
            [command[command.index("--role") + 1] for command in commands],
            ["client", "peer"],
        )
        for command in commands:
            PRODUCER.ensure_safe_command(command)
            text = " ".join(command).casefold()
            self.assertNotIn("mass-erase", text)
            self.assertNotIn("recover", text)
            self.assertNotIn("host", text)

    def test_profile_commands_use_only_probe_hashes(self) -> None:
        """! @brief 세 보드 입력은 raw UID 없이 SHA-256만 subprocess에 전달합니다. """

        profiles = {
            role: {
                "image": Path(f"C:/build/{role}.hex"),
                "build_record": Path(f"C:/build/{role}.json"),
            }
            for role in ("server", "client", "watcher")
        }
        source = {
            "sdk_root": "C:/ncs/v3.4.0",
            "source_revision": "a" * 40,
        }
        cleanup, run, export = PRODUCER.profile_commands(
            Path("C:/toolchain/python.exe"),
            source,
            profiles,
            HASHES,
            Path("C:/runtime"),
        )
        for value in HASHES.values():
            self.assertIn(value, cleanup)
            self.assertIn(value, run)
        self.assertEqual(
            cleanup[cleanup.index("--native-security-phase") + 1],
            "cleanup",
        )
        self.assertEqual(run[run.index("--native-security-phase") + 1], "fresh")
        self.assertNotIn("uid", " ".join(cleanup).casefold())
        self.assertNotIn("uid", " ".join(run).casefold())
        self.assertIn("--execute", cleanup)
        self.assertIn("--execute", run)
        self.assertNotIn("--execute", export)
        PRODUCER.ensure_safe_command(cleanup)
        PRODUCER.ensure_safe_command(run)
        PRODUCER.ensure_safe_command(export)

    def test_idle_fixture_resolves_moved_self_contained_build(self) -> None:
        """! @brief Actions 절대 경로가 사라져도 인접한 exact 산출물만 허용합니다. """

        with tempfile.TemporaryDirectory(prefix="nu54-idle-build-") as folder:
            root = Path(folder)
            record = root / "build-record.json"
            names = {
                "image": "image.hex",
                "elf": "image.elf",
                "config": "config.txt",
                "sysbuild": "sysbuild.txt",
            }
            for name in names.values():
                (root / name).write_bytes(name.encode("ascii"))
            build = {
                "image": "D:/runner/records/watcher/image.hex",
                "artifacts": {
                    key: {"path": f"D:/runner/records/watcher/{name}"}
                    for key, name in names.items()
                    if key != "image"
                },
            }
            observed = resolve_idle_build_sources(record, build)
            self.assertEqual(
                observed,
                {key: (root / name).resolve() for key, name in names.items()},
            )
            build["artifacts"]["elf"]["path"] = (
                "D:/runner/records/watcher/not-image.elf"
            )
            with self.assertRaises(ValueError):
                resolve_idle_build_sources(record, build)

    def test_ecosystem_programming_uses_hash_only_in_process_pyocd(self) -> None:
        """! @brief ecosystem 실물 경로가 raw UID subprocess argv를 만들지 않습니다. """

        source = TARGET.read_text(encoding="utf-8")
        self.assertIn("collect_register_identity_sha256(", source)
        self.assertIn("flash_image_pyocd_sha256(", source)
        self.assertIn("backend.session(mapped[2])", source)
        self.assertNotIn('"--uid"', source)
        self.assertNotIn("flash_image_pyocd(", source)
        self.assertEqual(source.count("python = runtime_python()"), 2)
        self.assertNotIn("python = artifacts.toolchain_python", source)

    def test_validated_index_rows_supply_hashes_not_raw_index(self) -> None:
        """! @brief raw build index에 hash가 없어도 validate_index 결과로 byte를 고정합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            index_path = root / "index.json"
            plan_path.write_text("{}", encoding="utf-8")
            index_path.write_text("{}", encoding="utf-8")
            source = {
                "source_revision": "a" * 40,
                "source_clean": True,
                "sdk_root": str(root / "sdk"),
                "toolchain_root": str(root / "toolchains/dcbdc366a1/opt/zephyr-sdk"),
            }
            planned_source = {
                **source,
                "sdk_root": "D:/ncs/v3.4.0",
                "toolchain_root": "D:/ncs/toolchains/dcbdc366a1/opt/zephyr-sdk",
            }
            plan = {"source": planned_source}
            relocations = [{"origin_root": "D:/build", "bundle_root": str(root)}]
            rows = []
            for image_key, record_key, _family, _role in PRODUCER.PROFILE_SLOTS.values():
                for key, suffix in ((image_key, ".hex"), (record_key, ".json")):
                    path = root / (key[0] + "-" + key[1] + suffix)
                    path.write_bytes((key[0] + ":" + key[1]).encode("ascii"))
                    rows.append({
                        "campaign_id": key[0],
                        "name": key[1],
                        "source": str(path),
                        "sha256": sha256(path),
                    })
            with (
                mock.patch.object(PRODUCER.artifacts, "strict_json", side_effect=[plan, {}]),
                mock.patch.object(PRODUCER.artifacts, "validate_plan"),
                mock.patch.object(
                    PRODUCER.artifacts,
                    "validate_index",
                    return_value=rows,
                ) as validate_index,
                mock.patch.object(PRODUCER.artifacts, "validate_source_lock", return_value=source),
                mock.patch.object(
                    PRODUCER.artifacts,
                    "validate_source_binding",
                    wraps=PRODUCER.artifacts.validate_source_binding,
                ) as binding,
                mock.patch.object(
                    PRODUCER.artifacts,
                    "validate_relocations",
                    return_value=relocations,
                ) as validate_relocations,
                mock.patch.object(
                    PRODUCER.artifacts,
                    "validate_profile_record",
                ) as validate_profile_record,
            ):
                profiles, observed = PRODUCER.load_profile_inputs(
                    plan_path,
                    index_path,
                    Path(source["sdk_root"]),
                    Path(source["toolchain_root"]),
                )
            self.assertEqual(observed, source)
            self.assertEqual(set(profiles), {"server", "client", "watcher"})
            binding.assert_called_once_with(planned_source, source)
            validate_index.assert_called_once_with(
                plan,
                {},
                effective_source=source,
            )
            validate_relocations.assert_called_once_with({})
            self.assertEqual(validate_profile_record.call_count, 3)
            for call in validate_profile_record.call_args_list:
                self.assertIs(call.args[-1], relocations)

    def test_probe_hashes_must_be_distinct_and_lowercase(self) -> None:
        """! @brief 세 실물 identity의 raw ID·중복·대문자를 거부합니다. """

        args = argparse.Namespace(
            client_probe_sha256=HASHES["client"],
            peer_probe_sha256=HASHES["peer"],
            third_probe_sha256=HASHES["peer"],
        )
        with self.assertRaises(PRODUCER.RuntimeFixtureFailure):
            PRODUCER.validate_probe_hashes(args)
        args.third_probe_sha256 = "A" * 64
        with self.assertRaises(PRODUCER.RuntimeFixtureFailure):
            PRODUCER.validate_probe_hashes(args)

    def test_plan_only_builds_without_physical_execution(self) -> None:
        """! @brief --execute가 없으면 build 뒤 NOT_RUN plan만 남깁니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "runtime"
            inputs = {}
            for role in ("client", "peer"):
                image = root / f"{role}.hex"
                record = root / f"{role}.json"
                image.write_text(":" + role, encoding="ascii")
                record.write_text("{}", encoding="utf-8")
                inputs[role] = {"image": image, "build_record": record}
            profiles = {
                role: {"image": root / f"profile-{role}.hex",
                       "build_record": root / f"profile-{role}.json"}
                for role in ("server", "client", "watcher")
            }
            source = {
                "source_revision": "a" * 40,
                "source_clean": True,
                "sdk_root": str(root / "sdk"),
                "toolchain_root": str(root / "toolchains/dcbdc366a1/opt/zephyr-sdk"),
            }
            args = argparse.Namespace(
                plan=root / "plan.json",
                build_index=root / "index.json",
                output=output,
                client_probe_sha256=HASHES["client"],
                peer_probe_sha256=HASHES["peer"],
                third_probe_sha256=HASHES["third"],
                timeout_seconds=60,
                execute=False,
                authorize_sector_program=False,
                authorize_software_reset=False,
                authorize_three_board_hil=False,
            )
            calls = []

            def executor(*arguments: object, **kwargs: object) -> subprocess.CompletedProcess:
                calls.append((arguments, kwargs))
                return subprocess.CompletedProcess([], 0)

            with (
                mock.patch.object(PRODUCER, "load_profile_inputs", return_value=(profiles, source)),
                mock.patch.object(PRODUCER, "build_ecosystem_inputs", return_value=inputs),
                mock.patch.object(
                    PRODUCER,
                    "runtime_python",
                    return_value=Path(sys.executable),
                ) as runtime_python,
            ):
                result = PRODUCER.produce(args, executor=executor)
            self.assertEqual(result["status"], "NOT_RUN")
            self.assertEqual(result["probe_sha256"], HASHES)
            self.assertEqual(calls, [])
            runtime_python.assert_called_once_with()
            self.assertTrue((output / "runtime-producer-plan.json").is_file())
            self.assertFalse((output / "runtime-producer.json").exists())

    def test_runtime_manifest_has_exact_two_absolute_hashed_outputs(self) -> None:
        """! @brief bind-runtime 계약 key·절대경로·hash를 정확히 생성합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ecosystem = root / "ecosystem.json"
            third = root / "third.json"
            ecosystem.write_text('{"fixture":"ecosystem"}\n', encoding="utf-8")
            third.write_text('{"fixture":"third"}\n', encoding="utf-8")
            result = PRODUCER.runtime_manifest(
                {"source_revision": "a" * 40},
                ecosystem,
                third,
            )
            self.assertEqual(result["kind"], "m33_w06_runtime_producer")
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(
                {(row["campaign_id"], row["name"]) for row in result["runtime_inputs"]},
                {
                    ("m33_ecosystem", "fixture"),
                    ("m33_diagnostics_dtm", "third-idle-fixture"),
                },
            )
            for row in result["runtime_inputs"]:
                self.assertTrue(Path(row["path"]).is_absolute())
                self.assertEqual(row["sha256"], sha256(Path(row["path"])))
            text = json.dumps(result).casefold()
            self.assertNotIn('"uid"', text)
            self.assertFalse(result["safety"]["mass_erase"])
            self.assertFalse(result["safety"]["automatic_recover"])
            self.assertFalse(result["safety"]["host_track"])

    def test_role_build_checkpoint_reuses_only_verified_role(self) -> None:
        """! @brief peer build 중단 후 client build를 반복하지 않고 손상은 거부합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {
                "source_revision": "a" * 40, "source_clean": True,
                "sdk_root": str(root / "sdk"),
                "toolchain_root": str(root / "toolchains/dcbdc366a1/opt/zephyr-sdk"),
            }
            calls = []
            fail_peer = True

            def executor(command, **_kwargs):
                nonlocal fail_peer
                role = command[command.index("--role") + 1]
                calls.append(role)
                if role == "peer" and fail_peer:
                    fail_peer = False
                    return subprocess.CompletedProcess(command, 1, b"", b"build interrupted")
                target = Path(command[command.index("--output") + 1])
                (target / "build/zephyr").mkdir(parents=True)
                manifest = {
                    "role": role, "identity": "identity", "identity_stable": True,
                    "source_revision": "a" * 40, "source_clean": True, "exit_code": 0,
                }
                for key, name in (("image", "zephyr.hex"), ("elf", "zephyr.elf"), ("config", ".config")):
                    file = target / "build/zephyr" / name
                    file.write_bytes((role + key).encode("ascii"))
                    manifest[key + "_sha256"] = sha256(file)
                (target / "build.log").write_bytes(b"build completed")
                (target / "build-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, b"build completed", b"")

            with mock.patch.object(PRODUCER.ecosystem, "source_identity", return_value="identity"):
                with self.assertRaises(PRODUCER.execution.ExecutionFailure):
                    PRODUCER.build_ecosystem_inputs(source, root, 60, executor)
                result = PRODUCER.build_ecosystem_inputs(source, root, 60, executor)
                self.assertEqual(["client", "peer", "peer"], calls)
                self.assertIn("attempt-0001", str(result["client"]["image"]))
                self.assertIn("attempt-0002", str(result["peer"]["image"]))
                result["client"]["image"].write_bytes(b"tampered")
                with self.assertRaises(PRODUCER.execution.ExecutionFailure):
                    PRODUCER.build_ecosystem_inputs(source, root, 60, executor)
                self.assertEqual(3, len(calls))

    def test_fixture_cycle_restart_preserves_failed_attempt(self) -> None:
        """! @brief producer 재호출은 부분 물리 상태를 재사용하지 않고 cycle만 새로 준비합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {
                "source_revision": "a" * 40, "source_clean": True,
                "sdk_root": str(root / "sdk"),
                "toolchain_root": str(root / "toolchains/dcbdc366a1/opt/zephyr-sdk"),
            }
            inputs = {}
            for role in ("client", "peer", "server", "watcher"):
                inputs[role] = {}
                for kind in ("image", "build_record"):
                    path = root / (role + "." + kind)
                    path.write_bytes((role + kind).encode("ascii"))
                    inputs[role][kind] = path
            profiles = {role: inputs[role] for role in ("server", "client", "watcher")}
            builds = {role: inputs[role] for role in ("client", "peer")}
            args = argparse.Namespace(
                plan=root / "plan.json", build_index=root / "index.json", output=root / "runtime",
                client_probe_sha256=HASHES["client"], peer_probe_sha256=HASHES["peer"],
                third_probe_sha256=HASHES["third"], timeout_seconds=60, execute=True,
                authorize_sector_program=True, authorize_software_reset=True,
                authorize_three_board_hil=True,
            )
            attempts = []

            def cycle(attempt, *_args):
                attempts.append(attempt)
                if len(attempts) == 1:
                    (attempt / "partial.log").write_bytes(b"interrupted physical preparation")
                    raise KeyboardInterrupt()
                for name in ("ecosystem.json", "third.json"):
                    (attempt / name).write_text("{}", encoding="utf-8")
                PRODUCER.write_new_json(attempt / "runtime-producer.json", PRODUCER.runtime_manifest(
                    source, attempt / "ecosystem.json", attempt / "third.json"))

            with mock.patch.object(PRODUCER, "load_profile_inputs", return_value=(profiles, source)), \
                    mock.patch.object(PRODUCER, "build_ecosystem_inputs", return_value=builds), \
                    mock.patch.object(PRODUCER, "_run_fixture_cycle", side_effect=cycle), \
                    mock.patch.object(PRODUCER.artifacts, "runtime_producer_paths", return_value={}):
                with self.assertRaises(KeyboardInterrupt):
                    PRODUCER.produce(args)
                first_failure = (attempts[0] / "failure.json").read_bytes()
                result = PRODUCER.produce(args)
                resumed = PRODUCER.produce(args)
            self.assertEqual(result, resumed)
            self.assertEqual(2, len(attempts))
            self.assertEqual("attempt-0002", attempts[-1].name)
            self.assertEqual(first_failure, (attempts[0] / "failure.json").read_bytes())
            self.assertTrue((attempts[0] / "partial.log").is_file())

    def test_command_failure_keeps_stdout_stderr_and_reason(self) -> None:
        """! @brief 실패 exit를 기능 실패로 단정하지 않고 실제 출력·명령 receipt를 남깁니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executor = mock.Mock(return_value=subprocess.CompletedProcess([], 7, b"specific stdout", b"specific stderr"))
            with self.assertRaises(PRODUCER.execution.ExecutionFailure) as raised:
                PRODUCER.run_checked([sys.executable, "-B", "runner.py"], 60, executor, log_root=root)
            self.assertEqual("INTERNAL", raised.exception.category)
            self.assertEqual(b"specific stderr", (root / "stderr.log").read_bytes())
            self.assertEqual(b"specific stdout", (root / "stdout.log").read_bytes())
            self.assertEqual(7, PRODUCER.execution.read_json(root / "command.json")["exit_code"])

    def test_physical_timeout_keeps_output_and_requires_safety_audit(self) -> None:
        """! @brief timeout은 보드 안전 상태 불명으로 분류하고 부분 출력을 보존합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executor = mock.Mock(side_effect=subprocess.TimeoutExpired([], 1, output=b"partial stdout", stderr=b"partial stderr"))
            with self.assertRaises(PRODUCER.execution.ExecutionFailure) as raised:
                PRODUCER.run_checked([sys.executable, "-B", "runner.py"], 1, executor,
                                     log_root=root, probe_hashes=set(HASHES.values()))
            self.assertEqual("SAFETY", raised.exception.category)
            self.assertEqual(b"partial stderr", (root / "stderr.log").read_bytes())
            self.assertTrue(PRODUCER.execution.read_json(root / "command.json")["timed_out"])

    def test_raw_probe_output_is_rejected_before_log_write(self) -> None:
        """! @brief 새 stderr 보존 경로도 raw UID 기록을 허용하지 않습니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executor = mock.Mock(return_value=subprocess.CompletedProcess([], 1, b"probe_uid=0123456789abcdef0123456789abcdef", b""))
            with self.assertRaisesRegex(ValueError, "raw probe identity"):
                PRODUCER.run_checked([sys.executable, "-B", "runner.py"], 60, executor, log_root=root)
            self.assertFalse((root / "stdout.log").exists())

    def test_protected_output_is_rejected_before_creating_lock(self) -> None:
        """! @brief source/SDK 아래에 lock이나 임시 결과를 만들기 전에 거부합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(plan=root / "plan", build_index=root / "index", output=root / "sdk/forbidden")
            source = {"sdk_root": str(root / "sdk"), "toolchain_root": str(root / "toolchains/dcbdc366a1/opt/zephyr-sdk")}
            with mock.patch.object(PRODUCER, "load_profile_inputs", return_value=({}, source)), \
                    self.assertRaisesRegex(PRODUCER.RuntimeFixtureFailure, "outside source/SDK"):
                PRODUCER.produce(args)
            self.assertFalse(args.output.exists())


if __name__ == "__main__":
    unittest.main()
