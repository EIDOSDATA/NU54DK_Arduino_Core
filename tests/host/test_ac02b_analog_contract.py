"""AC-02B analog/PWM/tone/Servo 공개·구조 계약을 검사합니다."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class Ac02bAnalogContractTests(unittest.TestCase):
    """B3 구현이 합의한 API와 고정 자원 경계를 유지하는지 검사합니다."""

    def test_math_contract_compiles(self) -> None:
        compiler = shutil.which("c++") or shutil.which("g++")
        if compiler is None:
            self.skipTest("host C++ compiler가 없습니다.")
        with tempfile.TemporaryDirectory(prefix="nu54-ac02b-") as temporary:
            object_file = Path(temporary) / "ac02b_analog_math.o"
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-Wno-error=attributes",
                    "-I",
                    str(ROOT / "cores" / "arduino"),
                    str(ROOT / "tests" / "host" / "ac02b_analog_math.cpp"),
                    "-c",
                    "-o",
                    str(object_file),
                ],
                cwd=ROOT,
                check=True,
            )
            self.assertTrue(object_file.is_file())

    def test_public_implementation_contains_fixed_policy(self) -> None:
        wiring = (ROOT / "cores" / "arduino" / "wiring_analog.cpp").read_text(
            encoding="utf-8"
        )
        runtime = (ROOT / "cores" / "arduino" / "internal" / "PwmRuntime.cpp").read_text(
            encoding="utf-8"
        )
        header = (ROOT / "cores" / "arduino" / "internal" / "PwmRuntime.h").read_text(
            encoding="utf-8"
        )
        for token in (
            "analogReadResolution",
            "analogWriteResolution",
            "analogWriteFrequency",
            "toneStopWorkHandler",
            "k_work_cancel_delayable_sync",
            "DT_FOREACH_PROP_ELEM",
            "beginGpioPinHandover",
            "rollbackGpioPinHandover",
        ):
            self.assertIn(token, wiring)
        for block in ("20U", "21U", "22U"):
            self.assertIn(block, runtime)
        self.assertIn("period_conflict", header)
        self.assertIn("pwm_runtime_channel_capacity = 4U", header)

    def test_servo_is_fixed_memory_pwm22_backend(self) -> None:
        servo = (ROOT / "libraries" / "Servo" / "src" / "Servo.cpp").read_text(
            encoding="utf-8"
        )
        servo_header = (ROOT / "libraries" / "Servo" / "src" / "Servo.h").read_text(
            encoding="utf-8"
        )
        public_include = servo.index("#include <Servo.h>")
        discovery_guard = servo.index(
            "#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)"
        )
        zephyr_include = servo.index("#include <zephyr/kernel.h>")
        internal_include = servo.index('#include "internal/PwmRuntime.h"')
        self.assertLess(public_include, discovery_guard)
        self.assertLess(discovery_guard, zephyr_include)
        self.assertLess(discovery_guard, internal_include)
        self.assertTrue(servo.rstrip().endswith("#endif"))
        self.assertIn("PwmRuntimeClient::servo", servo)
        self.assertIn("ServoSlot servo_slots[MAX_SERVOS]", servo)
        self.assertNotIn("new ", servo)
        self.assertNotIn("delete ", servo)
        for method in (
            "attach(int pin)",
            "attach(int pin, int minimum, int maximum)",
            "writeMicroseconds(int value)",
            "readMicroseconds()",
            "attached()",
        ):
            self.assertIn(method, servo_header)

    def test_production_pwm_route_backend_is_transactional(self) -> None:
        """Production adapter가 B2 route 수명주기와 실패 복구를 사용합니다."""
        adapter = (
            ROOT / "variants" / "nu54dk" / "pwm_runtime_routes.cpp"
        ).read_text(encoding="utf-8")
        header = (
            ROOT / "variants" / "nu54dk" / "pwm_runtime_routes.h"
        ).read_text(encoding="utf-8")

        for instance in (20, 21, 22):
            self.assertIn(f"IoOwnerKind::pwm, {instance}U", adapter)
            self.assertIn(f"IoResourceKind::pwm_block, {instance}U", adapter)
            self.assertIn(f"DT_NODELABEL(pwm{instance})", adapter)
        for token in (
            "buildPeripheralRoute",
            "state->runtime_route->deactivate()",
            "state->runtime_route->stage(next_configuration)",
            "state->runtime_route->activate()",
            "restorePreviousRoute",
            "previous_configuration",
            "previous_routes",
            "SYS_INIT",
        ):
            self.assertIn(token, adapter)
        self.assertIn("installNu54dkPwmRuntimeRouteBackend", header)

        deactivate = adapter.index("state->runtime_route->deactivate()")
        stage = adapter.index("state->runtime_route->stage(next_configuration)")
        activate = adapter.index("state->runtime_route->activate()", stage)
        self.assertLess(deactivate, stage)
        self.assertLess(stage, activate)

    def test_recovery_failure_is_fail_closed_and_gpio_transition_is_rollbackable(self) -> None:
        """복구 실패가 조용히 상태를 버리거나 route를 재사용하지 않습니다."""
        runtime = (
            ROOT / "cores" / "arduino" / "internal" / "RuntimePeripheralRoute.cpp"
        ).read_text(encoding="utf-8") + (ROOT / "cores/arduino/internal/RuntimePeripheralRouteRecovery.cpp").read_text(encoding="utf-8")
        adapter = (
            ROOT / "variants" / "nu54dk" / "pwm_runtime_routes.cpp"
        ).read_text(encoding="utf-8")
        digital = (ROOT / "cores" / "arduino" / "wiring_digital.cpp").read_text(
            encoding="utf-8"
        )
        pwm_header = (
            ROOT / "cores" / "arduino" / "internal" / "PwmRuntime.h"
        ).read_text(encoding="utf-8")
        pwm_runtime = (
            ROOT / "cores" / "arduino" / "internal" / "PwmRuntime.cpp"
        ).read_text(encoding="utf-8")
        interrupt = (
            ROOT / "cores" / "arduino" / "wiring_interrupt.cpp"
        ).read_text(encoding="utf-8")
        spi = (ROOT / "cores" / "arduino" / "SPI.cpp").read_text(encoding="utf-8") + (ROOT / "cores/arduino/internal/spi/SpiZephyrBackend.cpp").read_text(encoding="utf-8")
        digital_compact = " ".join(digital.split())

        for token in (
            "unwindActivation",
            "abandonPreparedPinsFailClosed",
            "abandonGpioPinHandoverFailClosed",
            "pinctrl_route_installed_",
            "pm_reference_held_",
            "refreshCommittedPinCount",
            "phase_ = Phase::faulted",
        ):
            self.assertIn(token, runtime)
        for token in ("bool fatal", "latchFatal", "state->fatal"):
            self.assertIn(token, adapter)
        for token in (
            "preflightPinMode",
            "pwmRuntimeSuspend",
            "pwmRuntimeResume",
            "resumeAnalogWriteAfterGpioFailure",
            "suspendInterruptForPinHandover",
            "commitInterruptForPinHandover",
            "recoverPendingPinInterrupt",
            "interrupt_recovery_pending",
            "isGpioPinHandoverFaulted",
            "atomic_get(&state->handover_faulted)",
            "rollbackIoResources(ownership_lease)",
        ):
            self.assertIn(token, digital)
        self.assertIn(
            "handover.phase = cleanup_failed ? PinHandoverPhase::faulted",
            digital_compact,
        )

        self.assertIn("unwindActivation(prepared_count + 1U)", runtime)
        self.assertIn("PwmRuntimeSuspendedOutput", pwm_header)
        for token in ("bool fatal", "latchBlockFault", "restore_result < 0"):
            self.assertIn(token, pwm_runtime)
        for token in (
            "const bool was_registered",
            "return disable_result",
            "isGpioPinHandoverFaulted(logical_pin)",
            "isGpioPinHandoverFaulted(canonical_pin)",
            "token.active = true",
            "rollback_result < 0 ? rollback_result : result",
        ):
            self.assertIn(token, interrupt)
        self.assertGreaterEqual(spi.count("spi_interrupt_mask_faulted || hasActiveSpiInterruptToken()"), 3)

    def test_examples_exist(self) -> None:
        expected = (
            ROOT / "libraries" / "NUCODE_NU54DK" / "examples" / "AnalogChannels" / "AnalogChannels.ino",
            ROOT / "libraries" / "NUCODE_NU54DK" / "examples" / "AnalogResolution" / "AnalogResolution.ino",
            ROOT / "libraries" / "NUCODE_NU54DK" / "examples" / "DynamicPWM" / "DynamicPWM.ino",
            ROOT / "libraries" / "NUCODE_NU54DK" / "examples" / "ToneOutput" / "ToneOutput.ino",
            ROOT / "libraries" / "Servo" / "examples" / "Sweep" / "Sweep.ino",
        )
        for path in expected:
            self.assertTrue(path.is_file(), path)

    def test_target_contract_covers_adc_pwm_tone_servo_and_pm(self) -> None:
        target = ROOT / "tests" / "zephyr" / "ac02b_analog_contract"
        source = (target / "src" / "main.cpp").read_text(encoding="utf-8")
        configuration = (target / "prj.conf").read_text(encoding="utf-8")
        overlay = (
            target
            / "boards"
            / "nrf54l15dk_nrf54l15_cpuapp_nu54dk.overlay"
        ).read_text(encoding="utf-8")
        for token in (
            "test_adc_alias_resolution_and_ownership_policy",
            "test_analog_write_resolution_period_and_capacity",
            "test_allocator_route_failure_is_transactional",
            "test_output_restore_failure_latches_pwm_block",
            "test_pin_mode_reclaims_analog_write_route",
            "test_pin_mode_preflight_and_pwm_resume_are_transactional",
            "test_tone_duration_generation_and_single_channel",
            "test_servo_four_channel_fixed_capacity",
        ):
            self.assertIn(token, source)
        for symbol in (
            "CONFIG_PINCTRL_DYNAMIC=y",
            "CONFIG_PINCTRL_KEEP_SLEEP_STATE=y",
            "CONFIG_PM_DEVICE=y",
            "CONFIG_PM_DEVICE_RUNTIME=y",
        ):
            self.assertIn(symbol, configuration)
        for channel in range(8):
            self.assertIn(f"channel@{channel}", overlay)
        for block in (20, 21, 22):
            self.assertIn(f"ac02b_pwm{block}", overlay)


if __name__ == "__main__":
    unittest.main()
