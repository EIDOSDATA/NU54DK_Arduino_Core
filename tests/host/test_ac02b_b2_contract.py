"""AC-02B Serial/Wire/SPI 공개·route·실패 폐쇄 계약을 검사합니다."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class Ac02bPeripheralContractTests(unittest.TestCase):
    """B2 backend가 합의한 공개 범위와 SoC route 경계를 유지하는지 검사합니다."""

    def test_public_concrete_types_and_capabilities_are_explicit(self) -> None:
        header = (ROOT / "cores" / "arduino" / "NUCODEPeripheral.h").read_text(
            encoding="utf-8"
        )
        for token in (
            "class Nu54HardwareSerial",
            "class Nu54TwoWire",
            "class Nu54SPIClass",
            "extern nucode::arduino::Nu54HardwareSerial &Serial1",
            "extern nucode::arduino::Nu54TwoWire &Wire",
            "extern nucode::arduino::Nu54SPIClass &SPI",
            "target = 1U << 2U",
            "no_stop_read = 1U << 3U",
        ):
            self.assertIn(token, header)

    def test_instance_route_matrix_and_zero_psel_boundary_are_fixed(self) -> None:
        route = (ROOT / "variants" / "nu54dk" / "peripheral_routes.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("route == PinRoute::uart30", route)
        self.assertIn("port == 0", route)
        self.assertIn("route == PinRoute::i2c22", route)
        self.assertIn("port == 1", route)
        for exact_pin in ("pin == 1U", "pin == 2U", "pin == 4U"):
            self.assertIn(exact_pin, route)
        self.assertIn("PinPolicy::conditional_dap_uart", route)
        self.assertNotIn("psel == 0U", route)

    def test_lifecycle_and_fail_closed_operations_are_present(self) -> None:
        serial = (ROOT / "cores" / "arduino" / "HardwareSerial.cpp").read_text(
            encoding="utf-8"
        )
        wire = (ROOT / "cores" / "arduino" / "Wire.cpp").read_text(encoding="utf-8")
        spi = (ROOT / "cores" / "arduino" / "SPI.cpp").read_text(encoding="utf-8") + (ROOT / "cores/arduino/internal/spi/SpiZephyrBackend.cpp").read_text(encoding="utf-8")
        runtime = (
            ROOT / "cores" / "arduino" / "internal" / "RuntimePeripheralRoute.cpp"
        ).read_text(encoding="utf-8") + (ROOT / "cores/arduino/internal/RuntimePeripheralRouteRecovery.cpp").read_text(encoding="utf-8")
        for token in ("serial1_route.activate", "uart_configure", "serial1_route.deactivate"):
            self.assertIn(token, serial)
        flush_helper = serial.index("void flush(SerialPortState &state)")
        serial1_guard = serial.rfind(
            "#if defined(CONFIG_NUCODE_ARDUINO_SERIAL1)", 0, flush_helper
        )
        self.assertGreaterEqual(serial1_guard, 0)
        self.assertGreater(serial.index("#endif", flush_helper), flush_helper)
        for token in ("wire_route.activate", "wire_route.deactivate", "unsupported_no_stop_read"):
            self.assertIn(token, wire)
        for token in (
            "spi_route.activate",
            "spi_route.deactivate",
            "suspendSpiInterrupts",
            "restoreSpiInterrupts",
            "void attachInterrupt()",
            "SpiError::unsupported_operation",
        ):
            self.assertIn(token, spi)
        for token in (
            "pm_device_runtime_enable",
            "pinctrl_update_states",
            "beginGpioPinHandover",
            "restoreGpioAfterPeripheral",
        ):
            self.assertIn(token, runtime)

        for token in (
            "spi_interrupt_mask_faulted",
            "hasActiveSpiInterruptToken",
            "rollback_error",
            "if (backend::started())",
        ):
            self.assertIn(token, spi)
        begin = spi.index("void begin() override")
        idempotent = spi.index("if (backend::started())", begin)
        activate = spi.index("spi_route.activate()", begin)
        self.assertLess(idempotent, activate)

        for source, active_token, faulted_token in (
            (serial, "serial1_route.active()", "serial1_route.faulted()"),
            (wire, "wire_route.active()", "wire_route.faulted()"),
            (spi, "spi_route.active()", "spi_route.faulted()"),
        ):
            self.assertIn(active_token, source)
            self.assertIn(faulted_token, source)
        self.assertIn("uart_irq_rx_enable(state.device)", serial)
        clear_started = serial.index("atomic_clear(&state.diagnostics->started)")
        remove_callback = serial.index(
            "uart_irq_callback_user_data_set(state.device, nullptr, nullptr)"
        )
        self.assertGreater(clear_started, remove_callback)

    def test_wire_target_and_extra_instances_are_not_faked(self) -> None:
        public = (ROOT / "cores" / "arduino" / "NUCODEPeripheral.h").read_text(
            encoding="utf-8"
        )
        arduino = (ROOT / "cores" / "arduino" / "Arduino.h").read_text(encoding="utf-8")
        self.assertNotIn("extern nucode::arduino::Nu54TwoWire &Wire1", public)
        self.assertNotIn("extern nucode::arduino::Nu54SPIClass &SPI1", public)
        self.assertNotIn("extern TwoWire &Wire1", arduino)
        self.assertNotIn("extern SPIClass &SPI1", arduino)

    def test_disabled_backends_and_library_discovery_fail_closed(self) -> None:
        stubs = (ROOT / "cores" / "arduino" / "peripheral_stubs.cpp").read_text(
            encoding="utf-8"
        )
        cmake = (ROOT / "zephyr" / "cmake/source_selection.cmake").read_text(encoding="utf-8")
        wire_example = (
            ROOT
            / "libraries"
            / "NUCODE_NU54DK"
            / "examples"
            / "WireRuntimePins"
            / "WireRuntimePins.ino"
        ).read_text(encoding="utf-8")
        spi_example = (
            ROOT
            / "libraries"
            / "NUCODE_NU54DK"
            / "examples"
            / "SPI00RuntimePins"
            / "SPI00RuntimePins.ino"
        ).read_text(encoding="utf-8")
        smoke = (ROOT / "tests" / "arduino-cli" / "run_smoke.py").read_text(
            encoding="utf-8"
        )

        for symbol in (
            "CONFIG_NUCODE_ARDUINO_WIRE",
            "CONFIG_NUCODE_ARDUINO_SPI",
            "CONFIG_NUCODE_ARDUINO_ADC",
            "CONFIG_NUCODE_ARDUINO_PWM",
        ):
            self.assertIn(f"!defined({symbol})", stubs)
        self.assertIn('cores/arduino/peripheral_stubs.cpp"', cmake)
        self.assertIn("#include <Wire.h>", wire_example)
        self.assertIn("#include <SPI.h>", spi_example)
        self.assertIn('"SPI00RuntimePins": "nucode.spi"', smoke)
        self.assertIn('"WireRuntimePins": "nucode.wire"', smoke)

    def test_public_diagnostics_distinguish_runtime_routes_and_serial1(self) -> None:
        header = (ROOT / "cores" / "arduino" / "nucode" / "Diagnostics.h").read_text(
            encoding="utf-8"
        )
        source = (ROOT / "cores" / "arduino" / "diagnostics.cpp").read_text(
            encoding="utf-8"
        )
        self.assertIn("serial1,", header)
        for token in (
            "DiagnosticSubsystem::serial1",
            "internal::lastSerial1Error()",
            "internal::WireError::invalid_pin_route",
            "internal::WireError::route_busy",
            "internal::WireError::route_error",
            "internal::SpiError::invalid_pin_route",
            "internal::SpiError::route_busy",
            "internal::SpiError::route_error",
            "internal::SpiError::interrupt_mask_error",
        ):
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()
