#!/usr/bin/env python3
"""! @brief ARF 예제의 실제 공개 header 문법·소유권·유한 실행·공개 경계를 검사한다. """
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "libraries/NUCODE_Peripheral_Fabric"
NAMES = ("UarteAsyncEcho", "SpiAsyncLoopback", "TwisTargetDoubleBuffer",
         "AdcContinuousDma", "PwmSequencePlayback", "ResourceConflictDemo")
SPEC = importlib.util.spec_from_file_location("arf_public_audit", ROOT / "tools/ci/m31_example_audit.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def sketch(name: str) -> Path:
    """! @brief 단일 원본 sketch 경로를 반환한다. """
    return LIBRARY / "examples" / name / (name + ".ino")


class ArfExampleTests(unittest.TestCase):
    """! @brief Host 결과를 실물 I/O PASS로 승격하지 않는 source 검사. """

    def test_six_metadata_records_match_generated_guidance(self):
        """! @brief 여섯 예제의 profile·역할·생성 안내를 metadata와 바이트 단위로 맞춘다. """
        guidance = AUDIT.load_example_guidance_tool()
        document = guidance.load_metadata()
        self.assertEqual(document["example_count"], 204)
        for name in NAMES:
            with self.subTest(name=name):
                identity = "NUCODE_Peripheral_Fabric/" + name
                record = document["examples"][identity]
                self.assertEqual(record["recommended_profile"], "fabric")
                self.assertEqual(record["board_count"], 1)
                self.assertEqual(record["serial_baud"], None)
                self.assertEqual(record["sidecars"], [])
                source = sketch(name).read_text(encoding="utf-8")
                self.assertTrue(source.startswith(guidance.render_guidance(identity, record)))

    def test_previous_public_boundary_findings_are_closed(self):
        """! @brief 기존 예제의 Zephyr 직접 사용과 마일스톤 식별자 회귀를 막는다. """
        relative_paths = (
            "libraries/NUCODE_BLE/examples/RadioEventTrigger/RadioEventTrigger.ino",
            "libraries/NUCODE_BLE/examples/ScalableBleResources/ScalableBleResources.ino",
            "libraries/NUCODE_BLE_Mesh_Update/examples/MeshBlobClient/MeshBlobClient.ino",
            "libraries/NUCODE_Radio_ESB/examples/EsbPrx/EsbPrx.ino",
            "libraries/NUCODE_Radio_ESB/examples/EsbPtx/EsbPtx.ino",
            "libraries/NUCODE_Radio_IEEE802154/examples/Radio154Receiver/Radio154Receiver.ino",
            "libraries/NUCODE_Radio_IEEE802154/examples/Radio154Transmitter/Radio154Transmitter.ino",
        )
        for relative_path in relative_paths:
            with self.subTest(path=relative_path):
                path = ROOT / relative_path
                report = AUDIT.inspect_sketch(path.parents[2], path)
                self.assertEqual(report["status"], "VISIBLE_CODE")

    def test_six_sketches_use_visible_public_code(self):
        for name in NAMES:
            with self.subTest(name=name):
                report = AUDIT.inspect_sketch(LIBRARY, sketch(name))
                self.assertEqual(report["status"], "VISIBLE_CODE")
                self.assertGreater(report["sketch_code_lines"], 70)
                source = sketch(name).read_text(encoding="utf-8")
                self.assertEqual(re.findall(r"#include\s+[<\"]([^>\"]+)", source),
                                 ["NUCODE_Peripheral_Fabric.h"])
                self.assertNotRegex(source, r"\b(?:Serial|Wire|SPI)\s*\.")
                self.assertNotRegex(source, r"\b(?:analogRead|analogWrite|bt_\w+|k_\w+)\s*\(")

    def test_actual_public_headers_compile_every_sketch(self):
        """! @brief backend mock 없이 실제 Serial/Analog 공개 선언으로 여섯 sketch를 컴파일한다. """
        with tempfile.TemporaryDirectory(prefix="nu54-arf-syntax-") as temporary:
            directory = Path(temporary)
            header = directory / "NUCODE_Peripheral_Fabric.h"
            pins = {"LED_BUILTIN": 0, "PIN_BUTTON0": 1, "PIN_PWM0": 3,
                    "PIN_P1_04": 20, "PIN_P1_05": 21, "PIN_P2_00": 25,
                    "PIN_P2_01": 26, "PIN_P2_02": 27, "PIN_P2_04": 29}
            variant = (ROOT / "variants/nu54dk/variant.h").read_text(encoding="utf-8")
            for name, value in pins.items():
                self.assertRegex(variant, rf"#define\s+{name}\s+{value}U\b")
            header.write_text(
                "#pragma once\n#include <nucode/SerialFabric.h>\n#include <nucode/AnalogFabric.h>\n" +
                "\n".join(f"#define {name} {value}U" for name, value in pins.items()) + "\n",
                encoding="utf-8")
            for name in NAMES:
                with self.subTest(name=name):
                    command = [*compiler_command(), "-std=c++17", "-Wall", "-Wextra", "-Werror",
                               "-x", "c++", "-fsyntax-only", "-I", str(directory),
                               "-I", str(ROOT / "cores/arduino"),
                               "-I", str(ROOT / "third_party/ArduinoCore-API"), str(sketch(name))]
                    result = subprocess.run(command, capture_output=True, timeout=60)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_button_gate_and_failed_stop_prevent_restart(self):
        for name in NAMES:
            with self.subTest(name=name):
                source = sketch(name).read_text(encoding="utf-8")
                setup = source.split("void setup()", 1)[1].split("void loop()", 1)[0]
                self.assertNotRegex(setup, r"(?:activate|startSession|demonstrateConflict|play)\(")
                self.assertIn("!previous_button", source)
                self.assertIn("!failed", source)
                self.assertIn("stop_result", source)
                self.assertIn("failed = !success || stop_result !=", source)
                self.assertIn("100000U", source)
                self.assertNotIn("while (true)", source)

    def test_async_paths_have_deadlines_cancel_and_event_budgets(self):
        for name, deadline, cancellation in (
                ("UarteAsyncEcho", "3000U", "cancelReceive"),
                ("SpiAsyncLoopback", "1000U", "cancelTransfer"),
                ("TwisTargetDoubleBuffer", "5000U", "cancelBuffers"),
                ("AdcContinuousDma", "2000U", ".stop("),
                ("PwmSequencePlayback", "3000U", "->stop(")):
            with self.subTest(name=name):
                source = sketch(name).read_text(encoding="utf-8")
                self.assertIn("millis() - started", source)
                self.assertIn(deadline, source)
                self.assertIn(cancellation, source)
                self.assertIn("count < 16U", source)
                self.assertIn("takeEvent(event)", source)
                self.assertIn("alignas(4)", source)

    def test_uart_and_spi_payload_stays_visible(self):
        uart = sketch("UarteAsyncEcho").read_text(encoding="utf-8")
        self.assertIn("receiveAsync(payload, sizeof(payload))", uart)
        self.assertIn("transmitAsync(payload, event.transferred)", uart)
        self.assertIn("event.transferred != sizeof(payload)", uart)
        spi = sketch("SpiAsyncLoopback").read_text(encoding="utf-8")
        self.assertIn("tx[index] == rx[index]", spi)
        self.assertIn("event.rx_transferred == sizeof(rx)", spi)
        self.assertIn("event.rx_buffer == rx", spi)

    def test_twis_two_pairs_and_received_data_are_not_synthetic(self):
        source = sketch("TwisTargetDoubleBuffer").read_text(encoding="utf-8")
        self.assertIn("queueBuffers(buffers[0],16U,buffers[2],16U,buffers[1],16U,buffers[3],16U)",
                      re.sub(r"\s+", "", source))
        self.assertIn("reads >= 2U", source)
        self.assertIn("writes >= 2U", source)
        self.assertIn("received_sum += received[index]", source)
        self.assertIn("reads == 2U && writes == 2U", source)

    def test_adc_and_pwm_buffers_are_real_ram_and_finite(self):
        adc = sketch("AdcContinuousDma").read_text(encoding="utf-8")
        self.assertIn("SaadcInput::vdd,", adc)
        self.assertIn("SaadcGain::one_quarter", adc)
        self.assertNotIn("SaadcInput::vdd_div2", adc)
        self.assertIn("adc.configure({&channel, 1U, 12U, 1U, 128U})", adc)
        self.assertIn("adc.queueBuffer(event.buffer, event.samples)", adc)
        self.assertIn("sum += event.buffer[index]", adc)
        self.assertIn("completed_buffers == 8U", adc)
        pwm = sketch("PwmSequencePlayback").read_text(encoding="utf-8")
        self.assertIn("std::uint16_t duty[8]", pwm)
        self.assertNotRegex(pwm, r"const\s+std::uint16_t\s+duty")
        self.assertIn("pwm->play(sequence, nullptr, 2U, false, false)", pwm)
        self.assertIn("PwmSequenceEventType::playback_complete", pwm)

    def test_conflict_does_not_preempt_current_owner(self):
        source = sketch("ResourceConflictDemo").read_text(encoding="utf-8")
        collision = source.index("conflict_result = spi->activate()")
        release = source.index("stop_result = uart->deactivate(100000U)", collision)
        retry = source.index("last_result = spi->activate()", release)
        self.assertLess(collision, release)
        self.assertLess(release, retry)
        self.assertIn("SerialFabricResult::ownership_conflict", source)
        self.assertIn("owner_preserved = uart->state() == SerialFabricState::active", source)
        self.assertNotIn("transferAsync", source)

    def test_readmes_separate_build_runtime_and_physical_prerequisites(self):
        for name in NAMES:
            with self.subTest(name=name):
                readme = (sketch(name).parent / "README.md").read_text(encoding="utf-8")
                for heading in ("목적", "준비물과 결선", "설정과 buffer 수명", "실행 순서",
                                "예상 결과", "종료·재시작과 오류", "다음 예제"):
                    self.assertIn("## " + heading, readme)
                self.assertIn("NOT_RUN", readme)
                self.assertIn("fabric", readme)
                self.assertIn("NCS v3.4.0", readme)
                self.assertNotRegex(readme, r"\bM\d{2}\w*")


if __name__ == "__main__":
    unittest.main(verbosity=2)
