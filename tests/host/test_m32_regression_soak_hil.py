#!/usr/bin/env python3
"""! @brief M32-W11 세 보드 유한 soak 계약을 검증합니다. """

from pathlib import Path
import hashlib
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
APPLICATION = REPOSITORY / "tests" / "zephyr" / "m32_regression_soak_hil"
M28_SOURCE = REPOSITORY / "tests" / "zephyr" / "m28_ble_3board_hil" / "src" / "main.cpp"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import BlePairHilFailure  # noqa: E402
import m32_regression_soak_run as RUNNER  # noqa: E402
sys.path.insert(0, str(APPLICATION))
import m33_w06_manifest as MANIFEST  # noqa: E402
from m32_regression_soak_run import (  # noqa: E402
    RegressionSoakFailure,
    _parse_role,
    source_manifest,
    validate_m33_build_record,
)


NONCE = "0123456789abcdef0123456789abcdef"


def _transcript(
    role: str,
    gap_ms: int = 180,
    cleanup_ms: int = 10,
    ready_replays: int = 0,
) -> bytes:
    """! @brief 한 역할의 정상 W11 soak protocol 원본을 만듭니다. """
    suffix = f":nonce={NONCE}"
    transmitted = 10000 if role in ("mixed", "central") else 0
    received = 10000 if role in ("peripheral", "mixed") else 0
    links = 2 if role == "mixed" else 1
    sequence = "sequence_per_link" if role == "mixed" else "sequence"
    ready = f"NUCODE_M28B3_READY:role={role}:test=SOAK"
    lines = [ready] * (ready_replays + 1)
    if role in ("peripheral", "mixed"):
        lines.append(
            f"NUCODE_M28B3_{role}:ADVERTISE:PASS:test=SOAK{suffix}"
        )
    lines.extend(
        (
            f"NUCODE_M28B3_{role}:TRACE:PASS:test=SOAK:source=rf-gatt"
            f":tx={transmitted}:rx={received}{suffix}",
            f"NUCODE_M28B3_{role}:SOAK:PASS:duration_s=1800:links={links}"
            f":{sequence}=10000:loss=0:corrupt=0:duplicate=0"
            ":unexpected_disconnect=0:recovery_failures=0:drops=0"
            f":max_gap_ms={gap_ms}:cleanup_ms={cleanup_ms}:cleanup=pass{suffix}",
            f"NUCODE_M28B3_{role}:FINAL:PASS:test=SOAK{suffix}",
        )
    )
    return ("boot noise\r\n" + "\r\n".join(lines) + "\r\n").encode("ascii")


class M32RegressionSoakHilTests(unittest.TestCase):
    """! @brief 분모·상한·V2 안전 경계를 고정합니다. """

    def test_all_three_roles_require_exact_denominators(self) -> None:
        for role in ("peripheral", "mixed", "central"):
            with self.subTest(role=role):
                gap = 0 if role == "central" else 180
                result = _parse_role(_transcript(role, gap), NONCE, role)
                self.assertEqual(role, result["role"])
                self.assertEqual(0, result["loss"])
                self.assertEqual("pass", result["cleanup"])

    def test_gap_cleanup_and_packet_changes_are_rejected(self) -> None:
        invalid = (
            _transcript("mixed", 501),
            _transcript("mixed", 180, 30001),
            _transcript("mixed").replace(b"sequence_per_link=10000", b"sequence_per_link=9999"),
            _transcript("mixed").replace(b"corrupt=0", b"corrupt=1"),
        )
        for payload in invalid:
            with self.subTest(payload=payload[-180:]), self.assertRaises(
                BlePairHilFailure
            ):
                _parse_role(payload, NONCE, "mixed")

    def test_pre_start_ready_replay_is_bounded_and_post_start_reset_is_rejected(self) -> None:
        """! @brief START 전 동일 READY만 허용하고 실행 중 reset은 거부합니다. """
        result = _parse_role(
            _transcript("peripheral", ready_replays=1), NONCE, "peripheral"
        )
        self.assertEqual(10000, result["received"])
        ready = b"NUCODE_M28B3_READY:role=peripheral:test=SOAK"
        advertising = (
            b"NUCODE_M28B3_peripheral:ADVERTISE:PASS:test=SOAK:nonce="
            + NONCE.encode("ascii")
        )
        reset_during_test = _transcript("peripheral").replace(
            advertising, advertising + b"\r\n" + ready
        )
        with self.assertRaises(BlePairHilFailure):
            _parse_role(reset_during_test, NONCE, "peripheral")

    def test_target_uses_bounded_gap_and_cleanup(self) -> None:
        source = M28_SOURCE.read_text(encoding="utf-8")
        cmake = (APPLICATION / "CMakeLists.txt").read_text(encoding="utf-8")
        generator = (APPLICATION / "m33_w06_manifest.py").read_text(encoding="utf-8")
        cases = (APPLICATION / "testcase.yaml").read_text(encoding="utf-8")
        for value in (
            "constexpr std::int64_t soak_gap_limit_ms = 500;",
            "constexpr std::int64_t cleanup_timeout_ms = 30000;",
            'fail("soak-service-gap")',
            'fail("soak-bounded-recovery")',
            'Serial.print(":max_gap_ms=")',
            'Serial.print(":cleanup=pass")',
        ):
            self.assertIn(value, source)
        self.assertIn("NUCODE_M32_W11_SOAK=1", cmake)
        self.assertIn("NUCODE_M28_B3_TEST_SOAK=1", cmake)
        self.assertIn("m33_w06_build_record.json", cmake)
        self.assertIn("m33-w06-original-build-record", generator)
        self.assertIn("m33_w06_manifest.py", cmake)
        for value in (
            "M32_W11_BOARD_REVISION",
            "M32_W11_NCS_REVISION",
            "M32_W11_ZEPHYR_REVISION",
            "M32_W11_CORE_SOURCE_SHA256",
            "M32_W11_APPLICATION_SOURCE_SHA256",
            "M32_W11_BOARD_SOURCE_SHA256",
            "M32_W11_FIRMWARE_SOURCE_SHA256",
            "M32_W11_APPLICATION_CMAKE_SHA256",
            "M32_W11_APPLICATION_CONFIG_SHA256",
            "M32_W11_SOURCE_MANIFEST_SHA256",
        ):
            self.assertIn(value, cmake)
            self.assertIn(value, source)
        cleanup = source.index("BLEDevice.end();", source.index("void finishSoak()"))
        zero = source.index("BLEDevice.initialized() || BLEConnection.count() != 0U", cleanup)
        final = source.index(":FINAL:PASS:test=SOAK", zero)
        self.assertLess(cleanup, zero)
        self.assertLess(zero, final)
        self.assertEqual(3, cases.count("  nucode.m32.regression_soak_hil."))

    def test_source_manifest_requires_identical_actual_build_digests(self) -> None:
        """! @brief 세 image의 원본 build source digest가 다르면 manifest 생성을 거부합니다. """
        identity = SimpleNamespace(
            core="1" * 40,
            board="2" * 40,
            ncs="3" * 40,
            zephyr="4" * 40,
        )
        source_proof = {
            "core_source_sha256": "5" * 64,
            "application_source_sha256": "6" * 64,
            "board_source_sha256": "7" * 64,
        }
        records = {
            role: dict(source_proof) for role in ("peripheral", "mixed", "central")
        }
        manifest = source_manifest(identity, records)
        for key, value in source_proof.items():
            self.assertEqual(value, manifest[key])
        records["central"]["core_source_sha256"] = "8" * 64
        with self.assertRaises(RegressionSoakFailure):
            source_manifest(identity, records)

    def test_single_manifest_generator_includes_overlay_and_matches_outputs(self) -> None:
        """! @brief CMake/runner가 공유하는 generator가 overlay byte를 record에 반영합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            core, board, application = root / "core", root / "board", root / "app"
            firmware = root / "firmware.cpp"
            for path in (core / "cores/arduino", board / "boards/nucode/nu54dk",
                         application):
                path.mkdir(parents=True)
            (core / "cores/arduino/core.cpp").write_text("int core;\n", encoding="utf-8")
            (board / "boards/nucode/nu54dk/board.dts").write_text(
                "/dts-v1/;\n", encoding="utf-8"
            )
            (application / "CMakeLists.txt").write_text("project(test)\n", encoding="utf-8")
            (application / "prj.conf").write_text("CONFIG_BT=y\n", encoding="utf-8")
            overlay = application / "nu54dk.overlay"
            overlay.write_text("/ { chosen {}; };\n", encoding="utf-8")
            firmware.write_text("int main() { return 0; }\n", encoding="utf-8")
            revisions = {name: str(index) * 40 for index, name in enumerate(
                ("core", "board", "ncs", "zephyr"), 1
            )}
            first = MANIFEST.generate_record(
                core, board, application, firmware, revisions, "central"
            )
            json_output, cmake_output = root / "record.json", root / "record.cmake"
            MANIFEST.write_outputs(first, json_output, cmake_output)
            self.assertEqual(first, json.loads(json_output.read_text(encoding="utf-8")))
            self.assertIn(first["application_source_sha256"],
                          cmake_output.read_text(encoding="utf-8"))
            overlay.write_text("/ { aliases {}; };\n", encoding="utf-8")
            second = MANIFEST.generate_record(
                core, board, application, firmware, revisions, "central"
            )
            self.assertNotEqual(first["application_source_sha256"],
                                second["application_source_sha256"])

    def test_full_build_record_rejects_legacy_revision_promotion(self) -> None:
        """! @brief CMake 원본 record의 12자리 revision을 사후 full 값으로 승격하지 않습니다. """
        identity = SimpleNamespace(
            core="1" * 40,
            board="2" * 40,
            ncs="3" * 40,
            zephyr="4" * 40,
        )
        source_proof = {
            "core_source_sha256": "5" * 64,
            "application_source_sha256": "6" * 64,
            "board_source_sha256": "7" * 64,
        }
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary) / "build"
            image = build / "zephyr" / "zephyr.hex"
            image.parent.mkdir(parents=True)
            image.write_text(":00000001FF\n", encoding="ascii")
            record = {
                "schema_version": 1,
                "kind": "m33-w06-original-build-record",
                "role": "central",
                "core_revision": identity.core,
                "board_revision": identity.board,
                "ncs_revision": identity.ncs,
                "zephyr_revision": identity.zephyr,
                **source_proof,
                "firmware_source_sha256": RUNNER.file_sha256(RUNNER.FIRMWARE_SOURCE),
                "application_cmake_sha256": RUNNER.file_sha256(
                    RUNNER.APPLICATION_ROOT / "CMakeLists.txt"
                ),
                "application_config_sha256": RUNNER.file_sha256(
                    RUNNER.APPLICATION_ROOT / "prj.conf"
                ),
            }
            encoded = "\n".join(
                f"{key}={record[key]}" for key in RUNNER.SOURCE_MANIFEST_FIELDS
            )
            record["source_manifest_sha256"] = hashlib.sha256(
                encoded.encode("ascii")
            ).hexdigest()
            record_path = build / "m33_w06_build_record.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            with mock.patch.object(
                    RUNNER, "current_source_digests", return_value=source_proof):
                result = validate_m33_build_record(image, identity, "central")
                self.assertEqual(identity.core, result["core_revision"])
                record["core_revision"] = identity.core[:12]
                record_path.write_text(json.dumps(record), encoding="utf-8")
                with self.assertRaises(RegressionSoakFailure):
                    validate_m33_build_record(image, identity, "central")

    def test_runner_is_v2_only_sector_flash_with_access_preserving_reset(self) -> None:
        """! @brief nRF54L 접근 보호를 보존하는 reset 계약을 고정합니다. """

        runner = (HIL / "m32_regression_soak_run.py").read_text(encoding="utf-8")
        shared = (HIL / "m28_ble_3board.py").read_text(encoding="utf-8")
        for value in (
            '"cmsis_dap": "v2-only"',
            '"auto_unlock": False',
            '"erase": "sector"',
            '"reset": "software"',
            "ready_replay_settle_seconds=0.25",
            '"host_monotonic_scope": "central_start_to_all_final"',
            "active_timing_callback=record_active_interval",
            "halt_and_wait(session.target)",
            "monitor=monitor",
            "wait_for_target_state(",
            '{"RUNNING", "SLEEPING"}',
            'TEST_ID = "M32-SOAK-01:primary"',
        ):
            self.assertIn(value, runner)
        self.assertIn("flash_image_pyocd_sha256", shared)
        self.assertIn("probe_sha256(endpoints[role].board_id)", shared)
        self.assertNotIn('"--uid"', shared)
        active_start = shared.index("active_started_ns = time.monotonic_ns()")
        central_start = shared.index('write_start_command(ports["central"]', active_start)
        active_finish = shared.index("active_finished_ns = time.monotonic_ns()", central_start)
        self.assertLess(active_start, central_start)
        self.assertLess(central_start, active_finish)
        self.assertNotIn("cmsis_dap_v1=True", runner)


if __name__ == "__main__":
    unittest.main()
