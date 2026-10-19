#!/usr/bin/env python3
"""! @brief M32-W08 signed Mesh DFU HIL 계약을 검증합니다. """

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_mesh_dfu_run as runner  # noqa: E402


class M32MeshDfuHilTests(unittest.TestCase):
    """! @brief 5회·10 target·서명·rollback·V2 안전장치를 고정합니다. """

    def test_capacity_preflight_accounts_for_local_distributor(self) -> None:
        """! @brief local Distributor를 제외한 두 remote Target slot을 요구합니다. """

        capacity = runner.validate_capacity(
            {"cdb_node_slots": "3", "cdb_local_slots": "1"}
        )
        self.assertEqual(2, capacity["cdb_remote_capacity"])
        with self.assertRaisesRegex(runner.MeshDfuFailure, "capacity mismatch"):
            runner.validate_capacity(
                {"cdb_node_slots": "2", "cdb_local_slots": "1"}
            )

    def test_runner_rejects_target_stack_fault(self) -> None:
        """! @brief UART fault를 장시간 timeout으로 숨기지 않습니다. """

        with self.assertRaisesRegex(runner.MeshDfuFailure, "target fault"):
            runner.reject_target_fault("target_a", "Fatal error")

    def test_vcom_question_prefix_recovers_boot_and_dispatches_apply(self) -> None:
        """! @brief 제한된 VCOM 접두사 뒤 BOOT도 APPLY까지 진행합니다. """

        marker = runner.PROTOCOL + "|"
        canonical = marker + "BOOT|role=target_b"
        for prefix in ("?", "??"):
            self.assertEqual(
                (canonical, prefix),
                runner.recover_vcom_protocol_prefix(prefix + canonical),
            )
        self.assertEqual(
            (canonical, None), runner.recover_vcom_protocol_prefix(canonical)
        )
        for prefix in ("x", "???", "noise "):
            line = prefix + canonical
            self.assertEqual(
                (line, None), runner.recover_vcom_protocol_prefix(line)
            )

        class FakePort:
            """! @brief 수신 레코드와 송신 명령을 보존하는 직렬 포트입니다. """

            def __init__(self, lines: list[str]) -> None:
                self.lines = [(line + "\n").encode("ascii") for line in lines]
                self.writes: list[bytes] = []

            def readline(self) -> bytes:
                """! @brief 대기 중인 한 줄을 반환합니다. """

                if self.lines:
                    return self.lines.pop(0)
                return b""

            def write(self, payload: bytes) -> int:
                """! @brief 전송 명령을 기록합니다. """

                self.writes.append(payload)
                return len(payload)

            def flush(self) -> None:
                """! @brief 실제 버퍼가 없는 테스트 포트의 flush를 모사합니다. """

        nonce = "test-nonce"
        core = "a" * 40
        digest = "b" * 64
        size = 55039
        ports = {
            "distributor": FakePort(
                [
                    f"{marker}ITERATION|role=distributor|iteration=1|targets=2"
                    f"|version=2.0.0+0|signed_sha256={digest}|image_size={size}"
                    f"|nonce={nonce}|core={core}"
                ]
            ),
            "target_a": FakePort(
                [
                    f"{marker}BOOT|role=target_a|version=2.0.0+0|confirmed=0"
                    f"|nonce={nonce}|core={core}",
                    f"{marker}APPLIED|role=target_a|iteration=1|confirmed=0"
                    f"|nonce={nonce}|core={core}",
                ]
            ),
            "target_b": FakePort(
                [
                    f"?{marker}BOOT|role=target_b|version=2.0.0+0|confirmed=0"
                    f"|nonce={nonce}|core={core}",
                    f"{marker}APPLIED|role=target_b|iteration=1|confirmed=0"
                    f"|nonce={nonce}|core={core}",
                ]
            ),
        }
        candidate = runner.ImageInput(
            Path("candidate.bin"), size, digest, runner.CANDIDATE_VERSION
        )
        transcript: list[str] = []
        _boots, _result, _end, details = runner.collect_iteration(
            ports,
            1,
            nonce,
            core,
            candidate,
            transcript,
            time.monotonic() + 1.0,
        )
        target_b_writes = b"".join(ports["target_b"].writes)
        self.assertIn(f"{marker}APPLY|".encode("ascii"), target_b_writes)
        self.assertEqual({"target_a", "target_b"}, set(details["boots"]))
        self.assertEqual({"target_a", "target_b"}, set(details["applied"]))
        self.assertIn("target_b-raw-prefix: ?", transcript)

    def test_domains_accepts_relocated_sysbuild_root(self) -> None:
        """! @brief artifact 이동 뒤에도 원래 domain 상대 identity를 검증합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "downloaded-sysbuild"
            for name in (runner.APPLICATION_DOMAIN, runner.BOOT_DOMAIN):
                (root / name).mkdir(parents=True)
            root.joinpath("domains.yaml").write_text(
                "default: m32_mesh_dfu_hil\n"
                "build_dir: D:/ci/twister_links/test_7\n"
                "domains:\n"
                "  - name: m32_mesh_dfu_hil\n"
                "    build_dir: D:/ci/twister_links/test_7/m32_mesh_dfu_hil\n"
                "  - name: mcuboot\n"
                "    build_dir: D:/ci/twister_links/test_7/mcuboot\n"
                "flash_order:\n"
                "  - mcuboot\n"
                "  - m32_mesh_dfu_hil\n",
                encoding="utf-8",
            )
            runner.validate_domains(root)

    def boot_query_fixture(self, reply_changes=None, reply_mode="canonical", noise_prefix=None):
        """! @brief 손상 BOOT 뒤 조회에만 새 canonical record를 내는 유한 포트를 구성합니다. """

        marker = runner.PROTOCOL + "|"
        nonce, core, digest = "query-nonce", "a" * 40, "b" * 64
        values = {"role": "target_b", "version": "2.0.0+0", "confirmed": "0",
                  "nonce": nonce, "core": core}
        values.update(reply_changes or {})
        canonical = marker + "BOOT|" + "|".join(f"{key}={value}" for key, value in values.items())
        noisy = ("?" * 22 if noise_prefix is None else noise_prefix) + canonical

        class Port:
            """! @brief 조회·APPLY 순서와 원래 응답 byte를 보존하는 모의 UART입니다. """

            def __init__(self, lines, queried=False):
                self.lines = [(line + "\n").encode("ascii") for line in lines]
                self.writes = []
                self.queried = queried

            def readline(self):
                return self.lines.pop(0) if self.lines else b""

            def write(self, payload):
                self.writes.append(payload)
                if self.queried and b"|QUERY_BOOT|" in payload:
                    if reply_mode == "canonical":
                        self.lines.append((canonical + "\n").encode("ascii"))
                    elif reply_mode == "corrupt":
                        self.lines.append((noisy + "\n").encode("ascii"))
                    elif reply_mode == "duplicate":
                        self.lines.extend([(canonical + "\n").encode("ascii")] * 2)
                elif self.queried and b"|APPLY|" in payload:
                    self.lines.append((f"{marker}APPLIED|role=target_b|iteration=1|confirmed=0"
                                       f"|nonce={nonce}|core={core}\n").encode("ascii"))
                return len(payload)

            def flush(self):
                pass

        ports = {
            "distributor": Port([f"{marker}ITERATION|role=distributor|iteration=1|targets=2"
                                 f"|version=2.0.0+0|signed_sha256={digest}|image_size=55038"
                                 f"|nonce={nonce}|core={core}"]),
            "target_a": Port([f"{marker}BOOT|role=target_a|version=2.0.0+0|confirmed=0|nonce={nonce}|core={core}",
                              f"{marker}APPLIED|role=target_a|iteration=1|confirmed=0|nonce={nonce}|core={core}"]),
            "target_b": Port([noisy], queried=True),
        }
        candidate = runner.ImageInput(Path("candidate.bin"), 55038, digest, runner.CANDIDATE_VERSION)
        return ports, nonce, core, candidate, noisy

    def test_noisy_boot_requires_fresh_session_bound_record_before_apply(self) -> None:
        """! @brief 원본22물음표 BOOT는 거부하고 새 조회 응답을 받은 뒤에만 APPLY합니다. """

        ports, nonce, core, candidate, noisy = self.boot_query_fixture()
        self.assertEqual((noisy, None), runner.recover_vcom_protocol_prefix(noisy))
        self.assertTrue(runner.rejected_candidate_boot(noisy))
        for line in ("?" * 33 + noisy[22:], "noise " + noisy[22:], noisy[22:],
                     "???" + runner.PROTOCOL + "|FAIL|stage=boot"):
            self.assertFalse(runner.rejected_candidate_boot(line))
        transcript = []
        _boots, _result, _end, details = runner.collect_iteration(
            ports, 1, nonce, core, candidate, transcript, time.monotonic() + 1.0
        )
        self.assertEqual({"target_a", "target_b"}, set(details["boots"]))
        self.assertEqual({"target_a", "target_b"}, set(details["applied"]))
        self.assertEqual([
            f"{runner.PROTOCOL}|QUERY_BOOT|nonce={nonce}|core={core}\n".encode("ascii"),
            f"{runner.PROTOCOL}|APPLY|nonce={nonce}|iteration=1|confirm=0|core={core}\n".encode("ascii"),
        ], ports["target_b"].writes)
        self.assertIn("target_b-raw: " + noisy, transcript)
        self.assertIn("target_b-raw: BOOT_QUERY attempt=1", transcript)
        self.assertEqual(1, sum(line.startswith(f"target_b: {runner.PROTOCOL}|BOOT|") for line in transcript))

    def test_boot_query_rejects_wrong_identity_or_boot_state(self) -> None:
        """! @brief 재조회도 role·nonce·core·version·confirm 오류면 APPLY를 전송하지 않습니다. """

        for changes in ({"role": "target_a"}, {"nonce": "wrong"}, {"core": "c" * 40},
                        {"version": "0.0.0+0"}, {"confirmed": "1"}):
            with self.subTest(changes=changes):
                ports, nonce, core, candidate, _noisy = self.boot_query_fixture(changes)
                with self.assertRaises(runner.MeshDfuFailure):
                    runner.collect_iteration(ports, 1, nonce, core, candidate, [], time.monotonic() + 0.1)
                self.assertEqual(1, len(ports["target_b"].writes))
                self.assertIn(b"|QUERY_BOOT|", ports["target_b"].writes[0])

    def test_mixed_corrupt_boot_queries_fresh_record_without_recovering_noise(self) -> None:
        """! @brief 실제 혼합 손상 접두사도 거부한 채 새 BOOT를 조회하고 그 응답 뒤에만 APPLY합니다. """

        prefix = "\x00?w?w????_XE?\x1e?]???U??w??"
        ports, nonce, core, candidate, noisy = self.boot_query_fixture(noise_prefix=prefix)
        self.assertEqual((noisy, None), runner.recover_vcom_protocol_prefix(noisy))
        self.assertTrue(runner.rejected_candidate_boot(noisy))
        transcript = []
        _boots, _result, _end, details = runner.collect_iteration(
            ports, 1, nonce, core, candidate, transcript, time.monotonic() + 1.0
        )
        self.assertEqual({"target_a", "target_b"}, set(details["applied"]))
        self.assertEqual([b"QUERY_BOOT", b"APPLY"],
                         [payload.split(b"|")[2] for payload in ports["target_b"].writes])
        self.assertIn("target_b-raw: " + noisy, transcript)
        self.assertEqual(1, sum(line.startswith(f"target_b: {runner.PROTOCOL}|BOOT|") for line in transcript))
        for mode in ("none", "corrupt"):
            with self.subTest(reply_mode=mode):
                ports, nonce, core, candidate, _noisy = self.boot_query_fixture(
                    reply_mode=mode, noise_prefix=prefix
                )
                with self.assertRaises(runner.MeshDfuFailure):
                    runner.collect_iteration(ports, 1, nonce, core, candidate, [], time.monotonic() + 0.05)
                self.assertEqual([b"QUERY_BOOT"], [payload.split(b"|")[2] for payload in ports["target_b"].writes])

    def test_non_ascii_uart_decode_queries_fresh_boot_before_apply(self) -> None:
        """! @brief 실제 수신 decode의 대체문자는 저장 로그의 물음표와 구분해 새 응답만 검증합니다. """

        marker = (runner.PROTOCOL + "|").encode("ascii")
        for high_byte in (b"\x80", b"\xff"):
            prefix = b"\x00" + high_byte * 6 + b"_XE\x1e" + high_byte * 5
            decoded_prefix = prefix.decode("ascii", errors="replace")
            stored_prefix = decoded_prefix.encode("ascii", errors="replace").decode("ascii")
            self.assertNotIn("?", decoded_prefix)
            self.assertIn("\ufffd", decoded_prefix)
            for mode in ("canonical", "none", "corrupt", "duplicate"):
                with self.subTest(high_byte=high_byte.hex(), reply_mode=mode):
                    ports, nonce, core, candidate, stored = self.boot_query_fixture(
                        reply_mode=mode, noise_prefix=stored_prefix
                    )
                    canonical = marker + stored.encode("ascii").partition(marker)[2]
                    wire = prefix + canonical + b"\n"
                    decoded = wire.decode("ascii", errors="replace").strip()
                    self.assertEqual(stored, decoded.encode("ascii", errors="replace").decode("ascii"))
                    self.assertEqual((decoded, None), runner.recover_vcom_protocol_prefix(decoded))
                    self.assertTrue(runner.rejected_candidate_boot(decoded))
                    ports["target_b"].lines = [wire]
                    transcript = []
                    if mode == "canonical":
                        _boots, _result, _end, details = runner.collect_iteration(
                            ports, 1, nonce, core, candidate, transcript, time.monotonic() + 0.1
                        )
                        self.assertEqual({"target_a", "target_b"}, set(details["applied"]))
                        self.assertEqual([b"QUERY_BOOT", b"APPLY"],
                                         [payload.split(b"|")[2] for payload in ports["target_b"].writes])
                        self.assertIn("target_b-raw: " + decoded, transcript)
                    else:
                        with self.assertRaises(runner.MeshDfuFailure):
                            runner.collect_iteration(
                                ports, 1, nonce, core, candidate, transcript, time.monotonic() + 0.05
                            )
                        self.assertEqual(1, sum(b"|QUERY_BOOT|" in payload
                                                for payload in ports["target_b"].writes))
                        if mode != "duplicate":
                            self.assertFalse(any(b"|APPLY|" in payload for payload in ports["target_b"].writes))
            for length in (2, 33):
                self.assertFalse(runner.rejected_candidate_boot(
                    "\ufffd" * length + runner.PROTOCOL + "|BOOT|role=target_b"
                ))

    def test_boot_query_is_bounded_and_rejects_corrupt_or_duplicate_reply(self) -> None:
        """! @brief 무응답·다시 손상된 BOOT·중복 BOOT는 한 조회 뒤 실패하며 무한 재시도하지 않습니다. """

        for mode in ("none", "corrupt", "duplicate"):
            with self.subTest(mode=mode):
                ports, nonce, core, candidate, _noisy = self.boot_query_fixture(reply_mode=mode)
                with self.assertRaises(runner.MeshDfuFailure):
                    runner.collect_iteration(ports, 1, nonce, core, candidate, [], time.monotonic() + 0.05)
                self.assertEqual(1, sum(b"|QUERY_BOOT|" in payload for payload in ports["target_b"].writes))
                if mode != "duplicate":
                    self.assertFalse(any(b"|APPLY|" in payload for payload in ports["target_b"].writes))

    def test_mcuboot_version_parser(self) -> None:
        """! @brief MCUboot v1 header에서 exact semantic version을 읽습니다. """

        header = bytearray(32)
        struct.pack_into("<I", header, 0, runner.MCUBOOT_MAGIC)
        struct.pack_into("<H", header, 8, 0x800)
        struct.pack_into("<BBHI", header, 20, 2, 3, 4, 5)
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "signed.bin"
            image.write_bytes(header)
            self.assertEqual(runner.parse_mcuboot_version(image), (2, 3, 4, 5))

    def test_final_result_denominators_and_negatives(self) -> None:
        """! @brief 5회·10 target와 세 image negative를 모두 요구합니다. """

        candidate = runner.ImageInput(
            Path("candidate.bin"), 343280, "a" * 64, runner.CANDIDATE_VERSION
        )
        result = {
            "iterations": "5",
            "targets": "10",
            "image_size": str(candidate.size),
            "wrong_key_rejected": "1",
            "wrong_image_rejected": "1",
            "partial_image_rejected": "1",
            "version": "2.0.0+0",
            "signed_sha256": candidate.sha256,
        }
        runner.validate_final_result(result, {"status": "pass"}, candidate)
        with self.assertRaisesRegex(runner.MeshDfuFailure, "targets"):
            runner.validate_final_result({**result, "targets": "9"}, {"status": "pass"}, candidate)

    def test_dispatch_denominator_expands_five_iterations_to_ten_targets(self) -> None:
        """! @brief signed update와 rollback raw 범위를 target별 10회로 펼칩니다. """

        candidate = runner.ImageInput(
            Path("candidate.bin"), 343280, "a" * 64, runner.CANDIDATE_VERSION
        )
        transcript = [f"iteration-{iteration}" for iteration in range(1, 6)]
        iterations = []
        for iteration, line in enumerate(transcript, start=1):
            raw = (line + "\n").encode("ascii")
            iterations.append(
                {
                    "iteration": iteration,
                    "transcript_line_start": iteration,
                    "transcript_line_end": iteration,
                    "transcript_sha256": hashlib.sha256(raw).hexdigest(),
                    "details": {
                        "boots": {"target_a": {}, "target_b": {}},
                        "applied": {"target_a": {}, "target_b": {}},
                        "distributor": {
                            "targets": "2",
                            "signed_sha256": candidate.sha256,
                        },
                    },
                }
            )
        rollbacks = [
            {"iteration": iteration, "roles": ["target_a", "target_b"]}
            for iteration in range(1, 5)
        ] + [{"iteration": 5, "roles": ["target_b"]}]
        records = runner.build_dispatch_cycle_records(
            iterations, rollbacks, transcript, candidate
        )
        self.assertEqual(10, len(records))
        self.assertEqual(9, sum(row["final_state"] == "rolled_back" for row in records))
        self.assertEqual(
            {"NOT_APPLICABLE"},
            {row["semantics"]["active_watchdog_condition"] for row in records},
        )

    def test_watchdog_condition_uses_exact_disabled_kconfig_value(self) -> None:
        """! @brief 주석형 Kconfig n을 읽고 y·n 중복은 fail-closed 처리합니다. """

        self.assertEqual(
            "n", runner.config_symbol("# CONFIG_WATCHDOG is not set\n", "CONFIG_WATCHDOG")
        )
        self.assertEqual("y", runner.config_symbol("CONFIG_WATCHDOG=y\n", "CONFIG_WATCHDOG"))
        with self.assertRaisesRegex(runner.MeshDfuFailure, "판정할 수 없습니다"):
            runner.config_symbol(
                "CONFIG_WATCHDOG=y\n# CONFIG_WATCHDOG is not set\n",
                "CONFIG_WATCHDOG",
            )
        source = (HIL / "m32_mesh_dfu_run.py").read_text(encoding="utf-8")
        self.assertIn('"condition": "application_watchdog_disabled"', source)
        self.assertIn('"active_watchdog_condition": "NOT_APPLICABLE"', source)
        self.assertIn('dispatch_attestation(\n        "m32_mesh_dfu"', source)

    def test_watchdog_condition_copies_all_exact_config_and_build_bytes(self) -> None:
        """! @brief 세 runtime 역할과 candidate의 인접 config/build byte를 모두 결합합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            builds = {}
            classifications = {}
            for role in (*runner.ROLES, "candidate"):
                build_root = root / role
                application = build_root / runner.APPLICATION_DOMAIN / "zephyr"
                boot = build_root / runner.BOOT_DOMAIN / "zephyr"
                application.mkdir(parents=True)
                boot.mkdir(parents=True)
                application_config = application / ".config"
                boot_config = boot / ".config"
                application_config.write_text(
                    "# CONFIG_WATCHDOG is not set\n", encoding="utf-8"
                )
                boot_config.write_text(
                    "CONFIG_BOOT_WATCHDOG_FEED=y\n", encoding="utf-8"
                )
                signed = application / "zephyr.signed.hex"
                signed.write_bytes(b":00000001FF\n")
                record = application.parent / "nucode_arduino_core_build.yml"
                record.write_text(f"role: {role}\n", encoding="utf-8")
                image = runner.ImageInput(
                    signed,
                    signed.stat().st_size,
                    hashlib.sha256(signed.read_bytes()).hexdigest(),
                    None,
                )
                builds[role] = runner.BuildInput(
                    role,
                    build_root,
                    image,
                    image,
                    image,
                    image,
                    "b" * 64,
                    {
                        "record_name": record.name,
                        "record_sha256": hashlib.sha256(record.read_bytes()).hexdigest(),
                    },
                    None,
                    None,
                )
                classifications[role] = runner.classify_mcuboot_watchdog(
                    application_config.read_text(encoding="utf-8"),
                    boot_config.read_text(encoding="utf-8"),
                )
            evidence = runner.copy_watchdog_condition_evidence(
                root / "attempt.json", builds, classifications
            )
            self.assertEqual("NOT_APPLICABLE", evidence["status"])
            self.assertEqual(set(builds), set(evidence["builds"]))
            for row in evidence["builds"].values():
                self.assertEqual("n", row["symbols"]["CONFIG_WATCHDOG"])
                for label in (
                    "application_config",
                    "mcuboot_config",
                    "build_record",
                ):
                    path = root / row[label]["path"]
                    self.assertTrue(path.is_file())
                    self.assertEqual(
                        row[label]["sha256"],
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                    )

    def test_target_source_covers_signed_distribution_and_rollback(self) -> None:
        """! @brief 세 역할 target가 5회 배포·confirm·rollback 경계를 포함합니다. """

        source = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_mesh_dfu_hil"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "distribution_iteration_target = 5U",
            "provisioning_links_closed < 2U",
            "provisioning_attempt_limit = 6U",
            "provisioning_pending = false;",
            "NUCODEMesh.lastDriverError() == -ETIMEDOUT",
            "NUCODEMeshUpdate.startDistribution",
            "NUCODEMeshUpdate.confirmRunningImage",
            "bt_mesh_dfu_srv_applied",
            '"wrong_image_accept"',
            '"partial_image_accept"',
            "wrong_key_rejected",
            "M32MDFU|1|APPLY|nonce=",
            "M32MDFU|1|NEXT|nonce=",
            'Serial.print("|RESULT|role=distributor|iterations=5|targets=10',
            "partial_image_size_limit = 4096U",
            "distribution.preserve_composition = false;",
            "BT_MESH_DFU_EFFECT_UNPROV",
            "settings_save_one(role_setting",
        ):
            self.assertIn(token, source)

        candidate = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_mesh_dfu_hil"
            / "src"
            / "candidate.cpp"
        ).read_text(encoding="utf-8")
        for token in (
            "boot_write_img_confirmed",
            'settings_load_subtree_direct("m32mdfu"',
            '"M32MDFU|1|QUERY_BOOT|nonce="',
            "hasSessionPrefix(boot_query_prefix)",
            '"|core=" M32_MDFU_CORE_REVISION',
            'Serial.print("|BOOT|role=")',
            'Serial.print("|APPLIED|role=")',
            'Serial.print("|STOPPED|role=")',
        ):
            self.assertIn(token, candidate)

        candidate_configuration = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_mesh_dfu_hil"
            / "candidate.conf"
        ).read_text(encoding="utf-8")
        self.assertNotIn("CONFIG_BT=y", candidate_configuration)

    def test_apply_reboots_and_timeout_covers_bounded_mesh_transfer(self) -> None:
        """! @brief Apply 응답 뒤 재부팅과 3시간 유한 실행 상한을 고정합니다. """

        update_source = (
            REPOSITORY
            / "libraries"
            / "NUCODE_BLE_Mesh_Update"
            / "src"
            / "NUCODE_BLE_Mesh_Update.cpp"
        ).read_text(encoding="utf-8")
        target_source = (
            REPOSITORY
            / "tests"
            / "zephyr"
            / "m32_mesh_dfu_hil"
            / "src"
            / "main.cpp"
        ).read_text(encoding="utf-8")
        runner_source = (HIL / "m32_mesh_dfu_run.py").read_text(encoding="utf-8")
        self.assertIn("sys_reboot(SYS_REBOOT_WARM);", update_source)
        self.assertIn("boot_is_img_confirmed()", update_source)
        self.assertIn("BT_MESH_DFU_PHASE_APPLYING", update_source)
        self.assertIn("bt_mesh_dfu_srv_applied", update_source)
        self.assertIn("session_timeout_ms = 10800000", target_source)
        self.assertIn('default=10800.0', runner_source)
        self.assertIn('args.result_timeout <= 10800.0', runner_source)

    def test_hil_configuration_has_two_remote_node_capacity_and_stack_budget(self) -> None:
        """! @brief 세 보드 topology와 Mesh worker stack 예산을 고정합니다. """

        configuration_root = REPOSITORY / "tests" / "zephyr" / "m32_mesh_dfu_hil"
        configuration = (
            (configuration_root / "prj.conf").read_text(encoding="utf-8")
            + (configuration_root / "mesh.conf").read_text(encoding="utf-8")
        )
        for token in (
            "CONFIG_BT_MESH_CDB_NODE_COUNT=3",
            "CONFIG_BT_MESH_LPN_AUTO=n",
            "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=4800",
            "CONFIG_BT_MESH_SETTINGS_WORKQ_STACK_SIZE=1700",
            "CONFIG_BT_MESH_ADV_STACK_SIZE=4000",
            "CONFIG_MAIN_STACK_SIZE=8192",
        ):
            self.assertIn(token, configuration)

    def test_runner_is_v2_only_exact_sector_and_clean(self) -> None:
        """! @brief V1·mass erase·recover 없이 exact clean V2 경로만 허용합니다. """

        source = (HIL / "m32_mesh_dfu_run.py").read_text(encoding="utf-8")
        for token in (
            "collect_register_identity_sha256",
            "discover_live",
            "flash_image_pyocd_sha256",
            "flash_binary_pyocd_sha256",
            "erase_nrf54l_rram_pyocd_sha256",
            "reset_target_pyocd_sha256",
            "defer_reset=True",
            "reset_and_halt_before_program=True",
            "clear_nrf54l_rram_pyocd_sha256",
            "access_preserving_reset",
            "validate_source_clean",
            '"M32-MDFU-01:primary"',
            '"rollback": "observed"',
            'failure_evidence["failure"]',
            "save_attempt(",
        ):
            self.assertIn(token, source)
        self.assertNotIn("cmsis_dap_v1=True", source)
        self.assertNotIn("prefer_v1=true", source)
        self.assertNotIn('"under-reset"', source)
        self.assertNotIn('"--method", "hw"', source)
        self.assertNotIn("software_reset_barrier", source)
        self.assertNotIn('"--uid"', source)
        self.assertNotIn("subprocess.run", source)
        self.assertNotIn("--erase chip", source)
        self.assertNotIn('"recover"', source.casefold())
        self.assertNotIn("--recover", source.casefold())

    def test_native_group_builds_all_four_roles(self) -> None:
        """! @brief native 회귀가 Distributor·두 Target·candidate를 모두 빌드합니다. """

        source = (REPOSITORY / "tools" / "ci" / "run_zephyr_build.py").read_text(
            encoding="utf-8"
        )
        for suite in (
            "nucode.m32.mesh_dfu_hil.distributor",
            "nucode.m32.mesh_dfu_hil.target_a",
            "nucode.m32.mesh_dfu_hil.target_b",
            "nucode.m32.mesh_dfu_hil.candidate",
        ):
            self.assertIn(suite, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
