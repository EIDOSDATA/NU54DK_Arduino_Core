#!/usr/bin/env python3
"""! @brief M30-POWER-01 준비·실제 USB 소실·재개 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest import mock
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPOSITORY / "tests/hil/nu54dk/m30_power_loss.py"
TARGET = REPOSITORY / "tests/zephyr/m30_ble_dfu_hil"
SPEC = importlib.util.spec_from_file_location("m30_power_loss_runner", RUNNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"M30 power HIL runner를 불러올 수 없습니다: {RUNNER_PATH}")
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


class FakeClock:
    """! @brief 실제 대기 없이 안정 구간 시간을 진행합니다. """

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        """! @brief 현재 가상 시간을 반환합니다. """

        return self.now

    def sleep(self, seconds: float) -> None:
        """! @brief 가상 시간만 진행합니다. """

        self.now += seconds


class M30PowerLossTests(unittest.TestCase):
    """! @brief 전원 차단을 reset·키 입력으로 대체하지 못하게 고정합니다. """

    def manifest_documents(self) -> tuple[dict[str, object], dict[str, object]]:
        """! @brief manifest 재사용 검증용 정상 expected·prepared 문서를 만듭니다. """

        expected: dict[str, object] = {
            key: {"identity": key} for key in RUNNER.MANIFEST_IDENTITY_KEYS
        }
        expected["input_identity_sha256"] = RUNNER.manifest_input_identity(expected)
        expected["preflight"] = {
            "status": "not_run",
            "physical_power_cuts": 0,
        }
        manifest = json.loads(json.dumps(expected))
        manifest["preflight"] = {
            "status": "passed",
            "flash_backend": "pyocd-exact-sector",
            "flash_results": {
                "peripheral_bootloader": ["pyocd-sector", "100"],
                "peripheral_primary": ["pyocd-sector", "200"],
                "central": ["pyocd-sector", "300"],
            },
            "security_level": 4,
            "encryption_key_bytes": 16,
            "state": {
                "bond_count": 1,
                "rejected_bonds": 0,
                "bonded": 1,
                "settings_valid": 1,
            },
            "dfu_retry": {"requests": 10, "image_hash": "a" * 64},
            "bond_storage_reset": {
                "performed": True,
                "boards": 2,
                "offset": RUNNER.STORAGE_OFFSET,
                "size": RUNNER.STORAGE_SIZE,
            },
            "physical_power_cuts": 0,
            "input_identity_sha256": expected["input_identity_sha256"],
        }
        return manifest, expected

    def test_plan_is_exactly_four_points_and_three_cuts(self) -> None:
        """! @brief 계약의 4x3 순서와 image version을 고정합니다. """

        self.assertEqual(
            RUNNER.INJECTION_POINTS,
            (
                "slot1_transfer",
                "image_validation_write",
                "mcuboot_test_swap",
                "new_image_first_boot",
            ),
        )
        self.assertEqual(RUNNER.CUTS_PER_POINT, 3)
        self.assertEqual(RUNNER.TOTAL_CUTS, 12)
        self.assertLess(RUNNER.CONFIRMED_VERSION, RUNNER.UNCONFIRMED_VERSION)
        self.assertLess(RUNNER.UNCONFIRMED_VERSION, RUNNER.RETRY_VERSION)

    def test_runner_requires_explicit_mode_and_outputs_for_execution(self) -> None:
        """! @brief 실제 실행은 명시 flag·journal·evidence 없이는 시작하지 않습니다. """

        base = SimpleNamespace(
            discover_only=False,
            prepare_only=False,
            execute_power_cuts=False,
            flash_preflight=False,
            reset_bond_storage=False,
            journal=None,
            evidence=None,
            phase_timeout=1800.0,
            flash_timeout=120.0,
            power_cycle_timeout=120.0,
            absence_stable=0.75,
            window_cut_timeout=12.0,
        )
        with self.assertRaisesRegex(RUNNER.M30PowerFailure, "mode"):
            RUNNER.validate_options(base)
        base.execute_power_cuts = True
        with self.assertRaisesRegex(RUNNER.M30PowerFailure, "journal"):
            RUNNER.validate_options(base)
        base.journal = "journal.json"
        base.evidence = "evidence.json"
        RUNNER.validate_options(base)
        base.execute_power_cuts = False
        base.prepare_only = True
        base.reset_bond_storage = True
        with self.assertRaisesRegex(RUNNER.M30PowerFailure, "flash-preflight"):
            RUNNER.validate_options(base)

    def test_bond_storage_reset_is_exact_sector_only(self) -> None:
        """! @brief stale bond 정리는 고정 storage 범위를 0xff로 기록·검증합니다. """

        result = SimpleNamespace(
            returncode=0,
            stdout=f"M30_STORAGE_RESET_PASS={RUNNER.STORAGE_SIZE}\n".encode(),
            stderr=b"",
        )
        with mock.patch.object(RUNNER.subprocess, "run", return_value=result) as run:
            RUNNER.reset_bond_storage("secret-board", 30.0)
        command = run.call_args.args[0]
        program = command[3]
        self.assertEqual(command[-1], "secret-board")
        self.assertIn("target.reset_and_halt()", program)
        self.assertIn("flash.Operation.PROGRAM", program)
        self.assertIn(
            f"{RUNNER.STORAGE_OFFSET}, {RUNNER.STORAGE_OFFSET + RUNNER.STORAGE_SIZE}, 4096",
            program,
        )
        self.assertIn("flash.program_page(address", program)
        self.assertIn(f"read_memory_block8({RUNNER.STORAGE_OFFSET}", program)
        for forbidden in ("--mass", "Operation.ERASE", "--recover"):
            self.assertNotIn(forbidden, program)

    def test_physical_cycle_requires_both_interfaces_to_disappear(self) -> None:
        """! @brief reset처럼 MSD·UART가 유지되면 실제 power cycle로 인정하지 않습니다. """

        clock = FakeClock()
        with mock.patch.object(RUNNER.time, "monotonic", clock.monotonic), mock.patch.object(
            RUNNER.time, "sleep", clock.sleep
        ):
            with self.assertRaisesRegex(RUNNER.M30PowerFailure, "reset"):
                RUNNER.wait_for_physical_cycle(
                    lambda: RUNNER.Presence(True, True), 1.0, 1.0, 0.5
                )

    def test_physical_cycle_accepts_stable_dual_loss_and_restore(self) -> None:
        """! @brief 두 interface의 안정 소실·동일 endpoint 복귀만 통과합니다. """

        clock = FakeClock()

        def sample() -> RUNNER.Presence:
            if clock.now < 0.2:
                return RUNNER.Presence(True, True)
            if clock.now < 1.0:
                return RUNNER.Presence(False, False)
            return RUNNER.Presence(True, True)

        with mock.patch.object(RUNNER.time, "monotonic", clock.monotonic), mock.patch.object(
            RUNNER.time, "sleep", clock.sleep
        ):
            cycle = RUNNER.wait_for_physical_cycle(sample, 2.0, 2.0, 0.5)
        self.assertGreaterEqual(cycle.absent_stable_seconds, 0.5)
        self.assertGreater(cycle.restored_after_seconds, cycle.absent_after_seconds)

    def test_journal_rejects_reordered_or_ambiguous_resume(self) -> None:
        """! @brief attempt 순서 변경과 armed 중단 뒤 자동 재개를 거부합니다. """

        with tempfile.TemporaryDirectory(prefix="n54-m30-power-journal-") as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text("{}\n", encoding="utf-8")
            revision = "a" * 40
            journal = RUNNER.initial_journal(manifest, revision)
            journal["completed_attempts"] = [
                {"point": "image_validation_write", "attempt": 1}
            ]
            journal["physical_cuts"] = 1
            with self.assertRaisesRegex(RUNNER.M30PowerFailure, "순서"):
                RUNNER.validate_journal(journal, manifest, revision)
            journal = RUNNER.initial_journal(manifest, revision)
            journal["current_attempt"] = {
                "point": "slot1_transfer",
                "attempt": 1,
                "status": "armed",
            }
            with self.assertRaisesRegex(RUNNER.M30PowerFailure, "audit"):
                RUNNER.validate_journal(journal, manifest, revision)

    def test_manifest_redacts_probe_uid_and_stays_not_run(self) -> None:
        """! @brief 준비 manifest는 raw UID와 실제 cut 완료 주장을 저장하지 않습니다. """

        endpoint = SimpleNamespace(
            board_id="super-secret-probe-id",
            volume=SimpleNamespace(
                root=Path("E:/"),
                details=(
                    "Target Detect: NU54DK\n"
                    "Version: 0257\n"
                    "Git Commit SHA: abcdef\n"
                ),
            ),
            port_name="COM13",
        )
        evidence = RUNNER.daplink_identity(endpoint)
        serialized = json.dumps(evidence)
        self.assertNotIn(endpoint.board_id, serialized)
        self.assertRegex(evidence["board_id_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("board_id", evidence)

    def test_manifest_accepts_exact_inputs_and_completed_preflight(self) -> None:
        """! @brief 준비 manifest의 모든 입력과 완료 preflight가 같으면 통과합니다. """

        manifest, expected = self.manifest_documents()
        RUNNER.validate_manifest(manifest, expected)

    def test_manifest_rejects_changed_build_key_plan_and_helper(self) -> None:
        """! @brief build·키·계획·helper identity 중 하나라도 다르면 재사용을 거부합니다. """

        for key in (
            "build_records",
            "trust_public_key_source_sha256",
            "injection_plan",
            "criteria",
            "runner",
        ):
            with self.subTest(key=key):
                manifest, expected = self.manifest_documents()
                manifest[key] = {"changed": key}
                with self.assertRaisesRegex(RUNNER.M30PowerFailure, key):
                    RUNNER.validate_manifest(manifest, expected)

    def test_manifest_rejects_incomplete_or_unbound_preflight(self) -> None:
        """! @brief 미완료·다른 입력에 결합된 preflight를 실제 cut 전에 거부합니다. """

        for key, value in (
            ("status", "not_run"),
            ("security_level", 2),
            ("physical_power_cuts", 1),
            ("input_identity_sha256", "b" * 64),
        ):
            with self.subTest(key=key):
                manifest, expected = self.manifest_documents()
                manifest["preflight"][key] = value
                with self.assertRaisesRegex(RUNNER.M30PowerFailure, "preflight"):
                    RUNNER.validate_manifest(manifest, expected)

    def test_runner_identity_covers_transitive_local_helpers(self) -> None:
        """! @brief power runner의 직접·간접 로컬 import를 모두 manifest에 결합합니다. """

        identity = RUNNER.runner_identity()
        paths = {entry["path"] for entry in identity["files"]}
        self.assertEqual(
            paths,
            {
                path.relative_to(REPOSITORY).as_posix()
                for path in RUNNER.RUNNER_DEPENDENCIES
            },
        )
        self.assertTrue(
            all(
                re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                for entry in identity["files"]
            )
        )

    def test_source_digest_ignores_docs_but_tracks_compiler_inputs(self) -> None:
        """! @brief 비컴파일 문서와 실제 compiler 입력 변경을 구분합니다. """

        with tempfile.TemporaryDirectory(prefix="n54-m30-source-digest-") as directory:
            root = Path(directory)
            source = root / "main.cpp"
            document = root / "README.md"
            source.write_text("int value = 1;\n", encoding="utf-8")
            document.write_text("first\n", encoding="utf-8")
            initial = RUNNER.source_files_digest(root, (root,))
            document.write_text("second\n", encoding="utf-8")
            self.assertEqual(initial, RUNNER.source_files_digest(root, (root,)))
            source.write_text("int value = 2;\n", encoding="utf-8")
            self.assertNotEqual(initial, RUNNER.source_files_digest(root, (root,)))

    def test_target_has_bounded_validation_and_swap_windows(self) -> None:
        """! @brief 전원 전용 app·MCUboot marker와 15초 유한 창을 검사합니다. """

        source = (TARGET / "src/main.cpp").read_text(encoding="utf-8")
        hook = (REPOSITORY / "zephyr/m30_power_mcuboot_hook.c").read_text(
            encoding="utf-8"
        )
        power_conf = (TARGET / "sysbuild/mcuboot-power.conf").read_text(
            encoding="utf-8"
        )
        self.assertIn("MGMT_EVT_OP_IMG_MGMT_DFU_PENDING", source)
        self.assertIn("M30POWER|1|WINDOW|point=image_validation_write", source)
        self.assertIn("k_msleep(15000)", source)
        self.assertIn("MCUBOOT_STATUS_UPGRADING", hook)
        self.assertIn("M30POWER|1|WINDOW|point=mcuboot_test_swap", hook)
        self.assertIn("k_sleep(K_SECONDS(15))", hook)
        self.assertIn("CONFIG_MCUBOOT_ACTION_HOOKS=y", power_conf)
        boot_conf = (TARGET / "sysbuild/mcuboot.conf").read_text(encoding="utf-8")
        self.assertIn("CONFIG_FLASH=y", boot_conf)

    def test_power_build_scenarios_are_separate_from_normal_dfu(self) -> None:
        """! @brief confirmed·unconfirmed 전원 image만 power hook define을 받습니다. """

        scenarios = (TARGET / "testcase.yaml").read_text(encoding="utf-8")
        self.assertEqual(scenarios.count("M30_DFU_POWER_HIL=1"), 2)
        self.assertIn("nucode.m30.power.confirmed", scenarios)
        self.assertIn("nucode.m30.power.unconfirmed", scenarios)
        normal = scenarios.split("nucode.m30.dfu.central", 1)[0]
        self.assertNotIn("M30_DFU_POWER_HIL=1", normal)
        matrix = (REPOSITORY / "tools/ci/run_zephyr_build.py").read_text(
            encoding="utf-8"
        )
        for scenario in (
            "nucode.m30.power.confirmed",
            "nucode.m30.power.unconfirmed",
        ):
            self.assertIn(f'("m30_ble_dfu_hil", "{scenario}")', matrix)

    def test_runner_contains_no_reset_or_destructive_erase_shortcut(self) -> None:
        """! @brief pyOCD reset·mass/chip/recover와 키 입력 성공 경로를 금지합니다. """

        source = RUNNER_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "pyocd reset",
            '"--mass"',
            '"--chip"',
            '"--recover"',
            "input(",
        ):
            self.assertNotIn(forbidden, source.casefold())
        self.assertIn("requires_msd_and_uart_absence", source)


if __name__ == "__main__":
    unittest.main()
