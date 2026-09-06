#!/usr/bin/env python3
"""! @brief M14 공통 API의 실제 compile, link와 의미 계약을 검증합니다. """

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
import shutil
import subprocess
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class M14CoreContractTests(unittest.TestCase):
    def test_disabled_peripheral_stubs_compile_link_and_fail_closed(self) -> None:
        compiler = self._find_cxx_compiler()

        with self._host_build_directory() as temporary_root:
            harness = temporary_root / "disabled_peripheral_stubs.cpp"
            harness.write_text(
                r'''
#include <NUCODEPeripheral.h>

#include <cstdint>

extern "C" void analogReadResolution(std::uint8_t);
extern "C" void analogWriteResolution(std::uint8_t);
extern "C" bool analogWriteFrequency(pin_size_t, std::uint32_t);

namespace arduino
{
std::size_t Print::write(const std::uint8_t *buffer, std::size_t size)
{
    std::size_t written = 0U;
    while (written < size && write(buffer[written]) == 1U)
    {
        ++written;
    }
    return written;
}
}

extern "C" int disabled_stub_test_main()
{
    if (Wire.setPins(0U, 1U) ||
        Wire.capabilities() != nucode::arduino::PeripheralCapability::none)
    {
        return 1;
    }
    Wire.begin();
    Wire.beginTransmission(0x52U);
    if (Wire.write(static_cast<std::uint8_t>(0xA5U)) != 0U ||
        Wire.endTransmission() != 4U || Wire.requestFrom(0x52U, 1U) != 0U)
    {
        return 2;
    }

    if (SPI.setPins(0U, 1U, 2U) ||
        SPI.capabilities() != nucode::arduino::PeripheralCapability::none)
    {
        return 3;
    }
    SPI.begin();
    SPI.beginTransaction(arduino::SPISettings());
    if (SPI.transfer(static_cast<std::uint8_t>(0xA5U)) != 0U)
    {
        return 4;
    }
    SPI.endTransaction();
    SPI.end();

    analogReadResolution(12U);
    if (analogRead(0U) != -1)
    {
        return 5;
    }
    analogWriteResolution(8U);
    if (analogWriteFrequency(0U, 1000U))
    {
        return 6;
    }
    analogWrite(0U, 127);
    tone(0U, 1000U, 1UL);
    noTone(0U);
    return 0;
}
'''.strip()
                + "\n",
                encoding="utf-8",
            )
            executable = temporary_root / (
                "disabled_peripheral_stubs.exe"
                if os.name == "nt"
                else "disabled_peripheral_stubs"
            )
            launcher = temporary_root / "disabled_peripheral_launcher.cpp"
            launcher.write_text(
                'extern "C" int disabled_stub_test_main();\n'
                "int main() { return disabled_stub_test_main(); }\n",
                encoding="utf-8",
            )
            command = [
                compiler,
                "-std=c++1z",
                "-DHOST",
                f"-I{REPOSITORY_ROOT / 'cores' / 'arduino'}",
                f"-I{REPOSITORY_ROOT / 'third_party' / 'ArduinoCore-API'}",
                str(launcher),
                str(harness),
                str(REPOSITORY_ROOT / "cores" / "arduino" / "peripheral_stubs.cpp"),
                "-o",
                str(executable),
            ]
            compile_result = subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            self.assertEqual(
                compile_result.returncode,
                0,
                msg=(
                    "disabled peripheral C++ compile/link failed:\n"
                    f"{compile_result.stdout}\n{compile_result.stderr}"
                ),
            )
            try:
                run_result = subprocess.run(
                    [str(executable)], capture_output=True, text=True, check=False
                )
            except OSError as error:
                if os.name == "nt" and getattr(error, "winerror", None) == 4551:
                    self.skipTest(
                        "Windows Application Control이 생성 native executable 실행을 "
                        "차단했습니다. compile/link 계약은 PASS이며, 실제 Zephyr 의미 "
                        "시험은 tests/zephyr/m14_core_contract가 담당합니다."
                    )
                raise
            self.assertEqual(
                run_result.returncode,
                0,
                msg=(
                    "disabled peripheral semantic test failed:\n"
                    f"{run_result.stdout}\n{run_result.stderr}"
                ),
            )

    def test_core_utility_random_f_and_diagnostics_compile_link(self) -> None:
        compiler = self._find_cxx_compiler()

        with self._host_build_directory() as temporary_root:
            atomic_header = temporary_root / "zephyr" / "sys" / "atomic.h"
            atomic_header.parent.mkdir(parents=True, exist_ok=True)
            atomic_header.write_text(
                """
#ifndef ZEPHYR_SYS_ATOMIC_H_
#define ZEPHYR_SYS_ATOMIC_H_
#include <stdint.h>
typedef int32_t atomic_val_t;
typedef struct { volatile atomic_val_t value; } atomic_t;
#define ATOMIC_INIT(value) { (value) }
static inline atomic_val_t atomic_get(const atomic_t *target)
{
    return __atomic_load_n(&target->value, __ATOMIC_SEQ_CST);
}
static inline bool atomic_cas(atomic_t *target, atomic_val_t old_value, atomic_val_t new_value)
{
    return __atomic_compare_exchange_n(&target->value, &old_value, new_value, false,
                                       __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}
static inline atomic_val_t atomic_set(atomic_t *target, atomic_val_t value)
{
    return __atomic_exchange_n(&target->value, value, __ATOMIC_SEQ_CST);
}
#endif
""".strip()
                + "\n",
                encoding="utf-8",
            )

            gpio_header = temporary_root / "zephyr" / "drivers" / "gpio.h"
            gpio_header.parent.mkdir(parents=True, exist_ok=True)
            gpio_header.write_text(
                """
#ifndef ZEPHYR_DRIVERS_GPIO_H_
#define ZEPHYR_DRIVERS_GPIO_H_
#include <stdint.h>
struct gpio_dt_spec
{
    const void *port;
    uint32_t pin;
    uint32_t dt_flags;
};
#endif
""".strip()
                + "\n",
                encoding="utf-8",
            )

            variant_header = temporary_root / "variant.h"
            variant_header.write_text(
                "#ifndef NUCODE_M14_HOST_VARIANT_H_\n"
                "#define NUCODE_M14_HOST_VARIANT_H_\n"
                "#include <api/Common.h>\n"
                "#define NUM_DIGITAL_PINS 2U\n"
                "#endif\n",
                encoding="utf-8",
            )

            harness = temporary_root / "m14_core_contract.cpp"
            harness.write_text(
                r'''
#include <Arduino.h>
#include <nucode/Diagnostics.h>

#include "internal/AnalogBackend.h"
#include "internal/RandomMath.h"
#include "internal/SPIBackend.h"
#include "internal/SerialBackend.h"
#include "internal/WireBackend.h"
#include "internal/pin_description.h"

#include <cmath>
#include <cstdint>
#include <cstring>
#include <typeinfo>

static_assert(bitRead(0x08UL, 3U) == 1U);
static_assert(nucode::arduino::internal::nextLcg32(0x12345678U) == 0x75432777U);
static_assert(nucode::arduino::internal::nextLcg32(0U) ==
              nucode::arduino::internal::kRandomIncrement);
static_assert(nucode::arduino::internal::randomRejectionThreshold(125U) == 46U);

class BufferPrint final : public arduino::Print
{
public:
    using arduino::Print::write;

    size_t write(std::uint8_t value) override
    {
        if (length_ >= sizeof(buffer_) - 1U)
        {
            return 0U;
        }
        buffer_[length_++] = static_cast<char>(value);
        buffer_[length_] = '\0';
        return 1U;
    }

    const char *text() const noexcept
    {
        return buffer_;
    }

private:
    char buffer_[32]{};
    size_t length_{0U};
};

struct HostExceptionValue
{
    int value;
};

class HostUnwindObserver
{
public:
    explicit HostUnwindObserver(int &destruction_count) : destruction_count_(destruction_count)
    {
    }

    ~HostUnwindObserver()
    {
        ++destruction_count_;
    }

private:
    int &destruction_count_;
};

class HostRttiBase
{
public:
    virtual ~HostRttiBase() = default;
};

class HostRttiDerived final : public HostRttiBase
{
};

namespace nucode::arduino::internal
{
GpioError host_gpio_error = GpioError::none;
int host_gpio_driver_error = 0;
SerialError host_serial_error = SerialError::none;
int host_serial_driver_error = 0;
std::uint32_t host_serial_dropped_bytes = 0U;
SerialError host_serial1_error = SerialError::none;
int host_serial1_driver_error = 0;
std::uint32_t host_serial1_dropped_bytes = 0U;
WireError host_wire_error = WireError::none;
int host_wire_driver_error = 0;
SpiError host_spi_error = SpiError::none;
int host_spi_driver_error = 0;
AnalogError host_analog_error = AnalogError::none;
int host_analog_driver_error = 0;

 GpioError lastGpioError() noexcept { return host_gpio_error; }
 int lastGpioDriverError() noexcept { return host_gpio_driver_error; }
 SerialError lastSerialError() noexcept { return host_serial_error; }
 int lastSerialDriverError() noexcept { return host_serial_driver_error; }
 std::uint32_t serialDroppedRxBytes() noexcept { return host_serial_dropped_bytes; }
 SerialError lastSerial1Error() noexcept { return host_serial1_error; }
 int lastSerial1DriverError() noexcept { return host_serial1_driver_error; }
 std::uint32_t serial1DroppedRxBytes() noexcept { return host_serial1_dropped_bytes; }
 WireError lastWireError() noexcept { return host_wire_error; }
 int lastWireDriverError() noexcept { return host_wire_driver_error; }
 SpiError lastSpiError() noexcept { return host_spi_error; }
 int lastSpiDriverError() noexcept { return host_spi_driver_error; }
AnalogError lastAnalogError() noexcept { return host_analog_error; }
int lastAnalogDriverError() noexcept { return host_analog_driver_error; }
}

extern "C" int m14_test_main()
{
    int abs_argument = -7;
    if (abs(abs_argument++) != 7 || abs_argument != -6 || abs(-2.5) != 2.5 ||
        std::abs(-11) != 11 || min(2, 9L) != 2 || max(2, 9L) != 9L)
    {
        return 1;
    }

    if (constrain(12, 0, 10) != 10 || constrain(-3, 0, 10) != 0 ||
        constrain(7, 0, 10) != 7)
    {
        return 2;
    }

    unsigned long bits = 0UL;
    bitSet(bits, 3U);
    bitWrite(bits, 5U, true);
    if (bitRead(bits, 3U) != 1U || bitRead(bits, 5U) != 1U || bit(3U) != 8UL)
    {
        return 3;
    }
    bitToggle(bits, 3U);
    bitClear(bits, 5U);
    if (bits != 0UL || lowByte(0x1234U) != 0x34U || highByte(0x1234U) != 0x12U)
    {
        return 4;
    }

    if (map(-10L, -10L, 10L, 0L, 100L) != 0L ||
        map(0L, -10L, 10L, 0L, 100L) != 50L ||
        map(10L, -10L, 10L, 0L, 100L) != 100L)
    {
        return 5;
    }

    BufferPrint output;
    if (output.print(F("flash")) != 5U || std::strcmp(output.text(), "flash") != 0)
    {
        return 6;
    }

    long first_sequence[8]{};
    randomSeed(0x12345678UL);
    for (auto &value : first_sequence)
    {
        value = random(-50L, 75L);
        if (value < -50L || value >= 75L)
        {
            return 7;
        }
    }

    randomSeed(0x12345678UL);
    for (const auto expected : first_sequence)
    {
        if (random(-50L, 75L) != expected)
        {
            return 8;
        }
    }

    randomSeed(77UL);
    const long first = random(1000L);
    randomSeed(0UL);
    const long second = random(1000L);
    randomSeed(77UL);
    if (random(1000L) != first || random(1000L) != second)
    {
        return 9;
    }
    if (random(0L) != 0L || random(-1L) != 0L || random(4L, 4L) != 4L ||
        random(5L, 4L) != 5L)
    {
        return 10;
    }

    const nucode::arduino::Diagnostic diagnostic{
        nucode::arduino::DiagnosticSubsystem::wire,
        nucode::arduino::DiagnosticCode::driver_error,
        -5,
        17U,
    };
    constexpr const char expected_diagnostic[] =
        "NU54:wire:driver-error:driver=-5:detail=17";
    char diagnostic_buffer[80]{};
    const size_t required = nucode::arduino::formatDiagnostic(
        diagnostic, diagnostic_buffer, sizeof(diagnostic_buffer));
    if (required != std::strlen(expected_diagnostic) ||
        std::strcmp(diagnostic_buffer, expected_diagnostic) != 0 ||
        nucode::arduino::formatDiagnostic(diagnostic, nullptr, 0U) != required ||
        nucode::arduino::formatDiagnostic(diagnostic, nullptr, 80U) != required)
    {
        return 11;
    }

     char truncated[8]{};
    if (nucode::arduino::formatDiagnostic(diagnostic, truncated, sizeof(truncated)) != required ||
        truncated[sizeof(truncated) - 1U] != '\0' || std::strcmp(truncated, "NU54:wi") != 0)
    {
         return 12;
     }

     char zero_capacity = 'X';
     char one_byte[1] = {'X'};
     if (nucode::arduino::formatDiagnostic(diagnostic, &zero_capacity, 0U) != required ||
         zero_capacity != 'X' ||
         nucode::arduino::formatDiagnostic(diagnostic, one_byte, sizeof(one_byte)) != required ||
         one_byte[0] != '\0')
     {
         return 13;
     }

     if (std::strcmp(nucode::arduino::diagnosticSubsystemToken(
                        static_cast<nucode::arduino::DiagnosticSubsystem>(0xffU)),
                    "unknown") != 0 ||
        std::strcmp(nucode::arduino::diagnosticCodeToken(
                        static_cast<nucode::arduino::DiagnosticCode>(0xffU)),
                    "unknown") != 0)
     {
         return 14;
     }

     using namespace nucode::arduino;
     internal::host_gpio_error = internal::GpioError::driver_error;
     internal::host_gpio_driver_error = -22;
     const Diagnostic gpio_diagnostic = lastDiagnostic(DiagnosticSubsystem::gpio);
     if (gpio_diagnostic.code != DiagnosticCode::driver_error ||
         gpio_diagnostic.driver_error != -22 || gpio_diagnostic.detail != 0U)
     {
         return 15;
     }

     internal::host_serial_error = internal::SerialError::rx_overflow;
     internal::host_serial_driver_error = -5;
     internal::host_serial_dropped_bytes = 17U;
     const Diagnostic serial_diagnostic = lastDiagnostic(DiagnosticSubsystem::serial);
     if (serial_diagnostic.code != DiagnosticCode::overflow ||
         serial_diagnostic.driver_error != 0 || serial_diagnostic.detail != 17U)
     {
         return 16;
     }

     internal::host_serial1_error = internal::SerialError::invalid_pin_route;
     internal::host_serial1_driver_error = 3;
     const Diagnostic serial1_diagnostic = lastDiagnostic(DiagnosticSubsystem::serial1);
     if (serial1_diagnostic.subsystem != DiagnosticSubsystem::serial1 ||
         serial1_diagnostic.code != DiagnosticCode::invalid_pin ||
         serial1_diagnostic.driver_error != 0 || serial1_diagnostic.detail != 3U ||
         std::strcmp(diagnosticSubsystemToken(DiagnosticSubsystem::serial1), "serial1") != 0)
     {
         return 17;
     }

     internal::host_wire_error = internal::WireError::invalid_pin_route;
     internal::host_wire_driver_error = 5;
     const Diagnostic wire_diagnostic = lastDiagnostic(DiagnosticSubsystem::wire);
     if (wire_diagnostic.code != DiagnosticCode::invalid_pin ||
         wire_diagnostic.driver_error != 0 || wire_diagnostic.detail != 5U)
     {
         return 18;
     }

     internal::host_spi_error = internal::SpiError::interrupt_mask_error;
     internal::host_spi_driver_error = -5;
     const Diagnostic spi_diagnostic = lastDiagnostic(DiagnosticSubsystem::spi);
     if (spi_diagnostic.code != DiagnosticCode::driver_error ||
         spi_diagnostic.driver_error != -5 || spi_diagnostic.detail != 0U)
     {
         return 19;
     }

     internal::host_analog_error = internal::AnalogError::unsupported_reference;
     const Diagnostic analog_diagnostic = lastDiagnostic(DiagnosticSubsystem::analog);
     if (analog_diagnostic.code != DiagnosticCode::unsupported ||
         lastDiagnostic(DiagnosticSubsystem::core).code != DiagnosticCode::none ||
         lastDiagnostic(DiagnosticSubsystem::time).code != DiagnosticCode::unsupported)
     {
         return 20;
     }

    int destruction_count = 0;
    int caught_value = 0;
    try
    {
        HostUnwindObserver observer(destruction_count);
        static_cast<void>(observer);
        throw HostExceptionValue{54};
    }
    catch (const HostExceptionValue &exception)
    {
        caught_value = exception.value;
    }
     if (caught_value != 54 || destruction_count != 1)
     {
         return 21;
    }

    HostRttiDerived derived;
    HostRttiBase *base = &derived;
    if (dynamic_cast<HostRttiDerived *>(base) == nullptr ||
        typeid(*base) != typeid(HostRttiDerived))
     {
         return 22;
    }

    return 0;
}
'''.strip()
                + "\n",
                encoding="utf-8",
            )

            executable = temporary_root / (
                "m14_core_contract.exe" if os.name == "nt" else "m14_core_contract"
            )
            launcher = temporary_root / "launcher.cpp"
            launcher.write_text(
                'extern "C" int m14_test_main();\n'
                "int main() { return m14_test_main(); }\n",
                encoding="utf-8",
            )
            command = [
                compiler,
                 "-std=c++1z",
                 "-DHOST",
                 "-DCONFIG_NUCODE_ARDUINO_GPIO=1",
                 "-DCONFIG_NUCODE_ARDUINO_SERIAL=1",
                 "-DCONFIG_NUCODE_ARDUINO_SERIAL1=1",
                 "-DCONFIG_NUCODE_ARDUINO_WIRE=1",
                 "-DCONFIG_NUCODE_ARDUINO_SPI=1",
                 "-DCONFIG_NUCODE_ARDUINO_ADC=1",
                f"-I{temporary_root}",
                f"-I{REPOSITORY_ROOT / 'cores' / 'arduino'}",
                f"-I{REPOSITORY_ROOT / 'variants' / 'nu54dk'}",
                f"-I{REPOSITORY_ROOT / 'third_party' / 'ArduinoCore-API'}",
                str(launcher),
                str(harness),
                str(REPOSITORY_ROOT / "third_party" / "ArduinoCore-API" / "api" / "Common.cpp"),
                str(REPOSITORY_ROOT / "third_party" / "ArduinoCore-API" / "api" / "Print.cpp"),
                str(REPOSITORY_ROOT / "cores" / "arduino" / "wiring_random.cpp"),
                str(REPOSITORY_ROOT / "cores" / "arduino" / "diagnostics.cpp"),
                "-o",
                str(executable),
            ]
            compile_result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(
                compile_result.returncode,
                0,
                msg=f"C++ compile/link failed:\n{compile_result.stdout}\n{compile_result.stderr}",
            )

    def test_generated_native_runtime_semantics(self) -> None:
        executable = REPOSITORY_ROOT / "build" / "m14-host-contract" / (
            "m14_core_contract.exe" if os.name == "nt" else "m14_core_contract"
        )
        self.test_core_utility_random_f_and_diagnostics_compile_link()

        try:
            run_result = subprocess.run(
                [str(executable)], capture_output=True, text=True, check=False
            )
        except OSError as error:
            if os.name == "nt" and getattr(error, "winerror", None) == 4551:
                self.skipTest(
                    "Windows Application Control이 생성 native executable 실행을 "
                    "차단했습니다. compile/link와 constexpr 계약은 별도 PASS이며, 실제 "
                    "Zephyr 의미 시험은 tests/zephyr/m14_cpp_policy가 담당합니다."
                )
            raise
        self.assertEqual(
            run_result.returncode,
            0,
            msg=f"C++ semantic test failed:\n{run_result.stdout}\n{run_result.stderr}",
        )

    def test_production_sources_are_registered(self) -> None:
        cmake_source = (REPOSITORY_ROOT / "zephyr" / "cmake/source_selection.cmake").read_text(
            encoding="utf-8"
        )
        self.assertIn('cores/arduino/wiring_random.cpp"', cmake_source)
        self.assertIn('cores/arduino/diagnostics.cpp"', cmake_source)
        self.assertIn('cores/arduino/peripheral_stubs.cpp"', cmake_source)

    def test_peripheral_config_matrix_has_real_link_targets(self) -> None:
        symbols = (
            "CONFIG_NUCODE_ARDUINO_WIRE",
            "CONFIG_NUCODE_ARDUINO_SPI",
            "CONFIG_NUCODE_ARDUINO_ADC",
            "CONFIG_NUCODE_ARDUINO_PWM",
        )
        expected_matrix = {
            "m14_core_contract": (False, False, False, False),
            "ac02b_b2_contract": (True, True, False, False),
            "ac02b_analog_contract": (False, False, True, True),
            "ac02b_hil_dut": (True, True, True, True),
        }
        for application, expected in expected_matrix.items():
            configuration = (
                REPOSITORY_ROOT / "tests" / "zephyr" / application / "prj.conf"
            ).read_text(encoding="utf-8")
            observed = tuple(f"{symbol}=y" in configuration for symbol in symbols)
            self.assertEqual(
                observed,
                expected,
                msg=f"AC-02B config/link matrix drifted: {application}",
            )

    @staticmethod
    @contextmanager
    def _host_build_directory() -> Iterator[Path]:
        staging = REPOSITORY_ROOT / "build" / "m14-host-contract"
        staging.mkdir(parents=True, exist_ok=True)
        yield staging

    @staticmethod
    def _find_cxx_compiler() -> str:
        candidates = [os.environ.get("CXX"), "g++", "clang++", "c++"]
        for candidate in candidates:
            if candidate:
                compiler = shutil.which(candidate)
                if compiler:
                    return compiler
        raise AssertionError("M14 host 계약 시험에 사용할 C++17 compiler를 찾지 못했습니다.")


if __name__ == "__main__":
    unittest.main()
