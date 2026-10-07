#!/usr/bin/env python3
"""! @brief DTM production parser·Host oracle·mapping과 template 계획을 검사한다. """
from concurrent.futures import ThreadPoolExecutor
import copy
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from host_compiler import compiler_command, run_executable

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("m33_diagnostics", ROOT / "tools/bluetooth/m33_diagnostics.py")
DIAG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAG)


class FakeSerial:
    """! @brief 실제 RF와 구분된 wire byte 입력을 제공한다. """
    def __init__(self, received):
        self.received = io.BytesIO(received)
        self.sent = bytearray()

    def read(self, count):
        return self.received.read(count)

    def write(self, data):
        self.sent.extend(data)


class DiagnosticsTests(unittest.TestCase):
    """! @brief source/build 준비를 runtime PASS로 승격하지 않는 음성 검사. """

    def test_private_debug_output_serializes_process_global_state(self):
        """! @brief 병렬 pyOCD 작업이 cwd·logging·stream 전역 상태를 겹치지 않게 합니다. """

        first_entered = threading.Event()
        release_first = threading.Event()
        second_attempting = threading.Event()
        second_entered = threading.Event()

        def first_worker():
            """! @brief 첫 private 구간을 고정해 두 번째 진입 차단을 관측합니다. """

            with DIAG.private_debug_output():
                first_entered.set()
                release_first.wait(2.0)

        def second_worker():
            """! @brief 첫 구간이 끝난 뒤에만 두 번째 private 구간에 진입합니다. """

            second_attempting.set()
            with DIAG.private_debug_output():
                second_entered.set()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(first_worker)
            self.assertTrue(first_entered.wait(1.0))
            second = executor.submit(second_worker)
            self.assertTrue(second_attempting.wait(1.0))
            self.assertFalse(second_entered.wait(0.1))
            release_first.set()
            first.result(timeout=2.0)
            second.result(timeout=2.0)
        self.assertTrue(second_entered.is_set())

    def test_production_parser_boundaries(self):
        with tempfile.TemporaryDirectory(prefix="nu54-diagnostic-") as temporary:
            binary = Path(temporary) / "protocol.exe"
            command = [*compiler_command(), "-std=c++17", "-Wall", "-Wextra", "-Werror",
                       "-I", str(DIAG.TEMPLATES / "dtm/src"), str(ROOT / "tests/host/m33_diagnostics_protocol_main.cpp"), "-o", str(binary)]
            compiled = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr.decode(errors="replace"))
            runtime = run_executable([str(binary)], capture_output=True, timeout=15)
            self.assertEqual(runtime.returncode, 0, runtime.stderr.decode(errors="replace"))

    def test_packet_report_not_status(self):
        self.assertEqual(DIAG.packet_count(bytes.fromhex("8123")), 291)
        for payload in (b"", b"\x80", b"\x00\x00", b"\x00\x01", b"\x80\x00\x00"):
            with self.assertRaises(ValueError):
                DIAG.packet_count(payload)

    def test_hci_oracle_known_counter_and_stale_opcode(self):
        port = FakeSerial(bytes.fromhex("040e06011f20002301"))
        endpoint = DIAG.DtmPort(port, True)
        self.assertEqual(endpoint.stop(), 291)
        self.assertEqual(port.sent.hex(), "011f2000")
        for response in ("040e06011e20002301", "040e06011f20012301", "5374617274696e6721", "040e06011f"):
            with self.assertRaises((ValueError, TimeoutError)):
                DIAG.DtmPort(FakeSerial(bytes.fromhex(response)), True).stop()

    def test_automatic_stop_requires_controller_report(self):
        self.assertEqual(DIAG.DtmPort(FakeSerial(bytes.fromhex("8000")), False).automatic_stop(), 0)
        self.assertEqual(DIAG.DtmPort(FakeSerial(bytes.fromhex("040e06011f20000200")), True).automatic_stop(), 2)
        with self.assertRaises(ValueError):
            DIAG.DtmPort(FakeSerial(bytes.fromhex("0000")), False).automatic_stop()

    def test_full_identity_from_both_transports(self):
        identity = "a" * 40 + "b" * 64
        wire = b"".join((ord(character) << 1).to_bytes(2, "big") for character in identity)
        self.assertEqual(DIAG.DtmPort(FakeSerial(wire), False).identity(), identity)
        response = bytes.fromhex("040e6c0180fc00") + identity.encode()
        self.assertEqual(DIAG.DtmPort(FakeSerial(response), True).identity(), identity)
        with self.assertRaises(ValueError):
            DIAG.DtmPort(FakeSerial(b"\x00\x01"), False).identity()

    def test_fixture_requires_distinct_images_and_third_board_isolation(self):
        fixture = {"schema_version": 1, "third_board_state": "halted_verified", "third_radio_state": "disabled_verified", "firmware_identity": "e" * 104,
                   "preflight_evidence_sha256": "f" * 64,
                   "boards": [{"probe_sha256": str(index) * 64, "image_sha256": "a" * 64, "port": f"COM{index}"} for index in (1, 2, 3)]}
        DIAG.validate_fixture(fixture)
        for key, value in (("third_board_state", "assumed"), ("third_radio_state", "unknown"), ("preflight_evidence_sha256", ""), ("firmware_identity", "unverified")):
            changed = copy.deepcopy(fixture)
            changed[key] = value
            with self.assertRaises(ValueError):
                DIAG.validate_fixture(changed)
        changed = copy.deepcopy(fixture)
        changed["boards"][1]["probe_sha256"] = changed["boards"][0]["probe_sha256"]
        with self.assertRaises(ValueError):
            DIAG.validate_fixture(changed)
        changed = copy.deepcopy(fixture)
        changed["boards"][1]["port"] = changed["boards"][0]["port"]
        with self.assertRaises(ValueError):
            DIAG.validate_fixture(changed)

    def test_watcher_stop_requires_runner_serial_close(self):
        """! @brief target 정지 분모와 runner serial close 증거를 같이 고정합니다. """

        stopped = {
            "role": "watcher",
            "nonce": "a" * 32,
            "core": "b" * 40,
            **{
                key: "0"
                for key in (
                    "native_links", "links", "pending", "scan", "advertising", "watchdog"
                )
            },
        }
        evidence = {
            "cleanup": {"watcher": {**stopped, "serial_close": "PASS"}}
        }
        DIAG.validate_watcher_stopped_evidence(stopped, evidence)
        for cleanup in (
                stopped,
                {**stopped, "serial_close": "FAIL"},
                {**stopped, "serial_close": "PASS", "unexpected": "1"},
                {**stopped, "serial_close": "PASS", "links": "1"}):
            with self.subTest(cleanup=cleanup), self.assertRaisesRegex(
                    ValueError, "zero-resource"):
                DIAG.validate_watcher_stopped_evidence(
                    stopped, {"cleanup": {"watcher": cleanup}}
                )

    def test_route_build_plan_has_real_transport_and_no_flash(self):
        for route, (_, delivery, _) in DIAG.ROUTES.items():
            if delivery == "excluded":
                with self.assertRaises(ValueError):
                    DIAG.build_plan(route, Path("sdk"), Path("toolchain"), Path("build"))
                continue
            argv = DIAG.build_plan(route, Path("sdk"), Path("toolchain"), Path("build"))
            self.assertIn("build", argv)
            self.assertNotIn("flash", argv)
            self.assertNotIn("--pristine", argv)
            self.assertNotIn("recover", " ".join(argv))
        spi = DIAG.build_plan("spi", Path("sdk"), Path("toolchain"), Path("build"))
        self.assertTrue(any("spi.overlay" in argument for argument in spi))

    def test_reuse_build_root_rejects_protected_and_overlapping_paths(self):
        """! @brief 재사용 build root가 source·SDK·toolchain·output과 겹치면 build 전에 거부합니다. """
        with tempfile.TemporaryDirectory(prefix="m33-diagnostics-roots-") as temporary:
            base = Path(temporary)
            sdk = base / "sdk"
            sdk.mkdir()
            toolchain = base / DIAG.LOCK["windows_toolchain"]["bundle_id"]
            toolchain.mkdir()
            output = base / "evidence"
            cases = (DIAG.ROOT, sdk, toolchain, output.parent)
            for reuse in cases:
                with self.subTest(reuse=reuse):
                    args = SimpleNamespace(
                        sdk=sdk,
                        toolchain=toolchain,
                        output=output,
                        reuse_build_root=reuse,
                        routes=["controller"],
                        jobs=1,
                    )
                    with mock.patch.object(
                            DIAG, "validate_locked_sources",
                            side_effect=AssertionError("source validation must not run")):
                        with self.assertRaises(ValueError):
                            DIAG.build(args)

    def test_reuse_route_symlink_cannot_escape_to_sdk(self):
        """! @brief route symlink/junction의 resolve 결과가 SDK이면 build 전에 거부합니다. """
        with tempfile.TemporaryDirectory(prefix="m33-diagnostics-link-") as temporary:
            base = Path(temporary)
            sdk = base / "sdk"
            sdk.mkdir()
            toolchain = base / DIAG.LOCK["windows_toolchain"]["bundle_id"]
            toolchain.mkdir()
            external = base / "external"
            external.mkdir()
            output = base / "evidence"
            escaped = external / "controller"
            args = SimpleNamespace(
                sdk=sdk,
                toolchain=toolchain,
                output=output,
                reuse_build_root=external,
                routes=["controller"],
                jobs=1,
            )
            original_resolve = Path.resolve

            def resolve_with_escape(path, *arguments, **keywords):
                """! @brief 권한과 무관하게 junction의 resolve 탈출 결과를 재현합니다. """
                if path == escaped:
                    return original_resolve(sdk, *arguments, **keywords)
                return original_resolve(path, *arguments, **keywords)

            with mock.patch.object(Path, "resolve", resolve_with_escape):
                with mock.patch.object(
                        DIAG, "validate_locked_sources",
                        side_effect=AssertionError("source validation must not run")):
                    with self.assertRaisesRegex(ValueError, "보호 경로"):
                        DIAG.build(args)

    def test_uart_output_ownership_and_finite_firmware(self):
        source = (DIAG.TEMPLATES / "dtm/src/main.c").read_text(encoding="utf-8")
        self.assertNotIn("printk(", source)
        self.assertNotIn("K_FOREVER", source)
        self.assertIn("RF_LEASE_MS 3000", source)
        self.assertIn("wdt_feed", source)
        self.assertIn("stop_test(true)", source)
        self.assertIn("CONFIG_NUCODE_ARDUINO_CORE", source)
        guard = (DIAG.TEMPLATES / "controller/src/main.c").read_text(encoding="utf-8")
        self.assertIn("RESET_WATCHDOG", guard)
        self.assertIn("120000", guard)
        self.assertNotIn("wdt_feed", guard)


if __name__ == "__main__":
    unittest.main(verbosity=2)
