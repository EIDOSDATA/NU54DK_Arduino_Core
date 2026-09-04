/**
 * @file peripheral_stubs.cpp
 * @brief 비활성 Arduino 주변장치 API의 링크 안전 fail-closed 구현입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODEPeripheral.h"

#include <cstddef>
#include <cstdint>

#if !defined(CONFIG_NUCODE_ARDUINO_WIRE)
namespace
{
    /** @brief Wire가 비활성인 build에서 버스 접근을 거부하는 고정 stub입니다. */
    class DisabledWire final : public nucode::arduino::Nu54TwoWire
    {
      public:
        /** @brief 비활성 backend는 pin route를 예약하지 않습니다. */
        bool setPins(pin_size_t, pin_size_t) noexcept override
        {
            return false;
        }

        /** @brief 비활성 backend에는 제공 가능한 capability가 없습니다. */
        [[nodiscard]] nucode::arduino::PeripheralCapability capabilities() const noexcept override
        {
            return nucode::arduino::PeripheralCapability::none;
        }

        /** @brief 비활성 backend에서는 controller를 시작하지 않습니다. */
        void begin() override
        {
        }

        /** @brief 비활성 backend에서는 target mode도 시작하지 않습니다. */
        void begin(std::uint8_t) override
        {
        }

        /** @brief 반복 호출할 수 있는 무동작 종료 함수입니다. */
        void end() override
        {
        }

        /** @brief 비활성 backend에서는 clock 설정을 적용하지 않습니다. */
        void setClock(std::uint32_t) override
        {
        }

        /** @brief 비활성 backend에서는 전송 상태를 열지 않습니다. */
        void beginTransmission(std::uint8_t) override
        {
        }

        /** @brief Arduino Wire의 기타 오류 상태를 반환합니다. */
        std::uint8_t endTransmission(bool) override
        {
            return 4U;
        }

        /** @brief Arduino Wire의 기타 오류 상태를 반환합니다. */
        std::uint8_t endTransmission() override
        {
            return 4U;
        }

        /** @brief 비활성 backend에서는 수신 byte가 없습니다. */
        std::size_t requestFrom(std::uint8_t, std::size_t, bool) override
        {
            return 0U;
        }

        /** @brief 비활성 backend에서는 수신 byte가 없습니다. */
        std::size_t requestFrom(std::uint8_t, std::size_t) override
        {
            return 0U;
        }

        /** @brief 비활성 backend에서는 callback을 등록하지 않습니다. */
        void onReceive(void (*)(int)) override
        {
        }

        /** @brief 비활성 backend에서는 callback을 등록하지 않습니다. */
        void onRequest(void (*)(void)) override
        {
        }

        /** @brief 비활성 backend의 TX는 즉시 실패합니다. */
        std::size_t write(std::uint8_t) override
        {
            setWriteError();
            return 0U;
        }

        /** @brief 비활성 backend에는 쓸 수 있는 공간이 없습니다. */
        int availableForWrite() override
        {
            return 0;
        }

        /** @brief 비활성 backend에는 읽을 byte가 없습니다. */
        int available() override
        {
            return 0;
        }

        /** @brief 비활성 backend의 peek는 EOF를 반환합니다. */
        int peek() override
        {
            return -1;
        }

        /** @brief 비활성 backend의 read는 EOF를 반환합니다. */
        int read() override
        {
            return -1;
        }

        /** @brief 대기 중인 전송이 없으므로 즉시 반환합니다. */
        void flush() override
        {
        }
    };

    DisabledWire disabled_wire;
} // namespace

nucode::arduino::Nu54TwoWire &Wire = disabled_wire;
#endif

#if !defined(CONFIG_NUCODE_ARDUINO_SPI)
namespace
{
    /** @brief SPI가 비활성인 build에서 버스 접근을 거부하는 고정 stub입니다. */
    class DisabledSPI final : public nucode::arduino::Nu54SPIClass
    {
      public:
        /** @brief 비활성 backend는 pin route를 예약하지 않습니다. */
        bool setPins(pin_size_t, pin_size_t, pin_size_t) noexcept override
        {
            return false;
        }

        /** @brief 비활성 backend에는 제공 가능한 capability가 없습니다. */
        [[nodiscard]] nucode::arduino::PeripheralCapability capabilities() const noexcept override
        {
            return nucode::arduino::PeripheralCapability::none;
        }

        /** @brief 비활성 backend에서는 controller를 시작하지 않습니다. */
        void begin() override
        {
        }

        /** @brief 반복 호출할 수 있는 무동작 종료 함수입니다. */
        void end() override
        {
        }

        /** @brief 비활성 backend에서는 transaction을 시작하지 않습니다. */
        void beginTransaction(arduino::SPISettings) override
        {
        }

        /** @brief 반복 호출할 수 있는 무동작 transaction 종료 함수입니다. */
        void endTransaction() override
        {
        }

        /** @brief 비활성 backend에서는 수신값 0을 반환합니다. */
        std::uint8_t transfer(std::uint8_t) override
        {
            return 0U;
        }

        /** @brief 비활성 backend에서는 수신값 0을 반환합니다. */
        std::uint16_t transfer16(std::uint16_t) override
        {
            return 0U;
        }

        /** @brief 비활성 backend에서는 사용자의 buffer를 변경하지 않습니다. */
        void transfer(void *, std::size_t) override
        {
        }

        /** @brief 비활성 backend에서는 interrupt mask를 등록하지 않습니다. */
        void usingInterrupt(int) override
        {
        }

        /** @brief 비활성 backend에는 해제할 interrupt mask가 없습니다. */
        void notUsingInterrupt(int) override
        {
        }

        /** @brief controller 전용 backend이므로 무동작입니다. */
        void attachInterrupt() override
        {
        }

        /** @brief controller 전용 backend이므로 무동작입니다. */
        void detachInterrupt() override
        {
        }
    };

    DisabledSPI disabled_spi;
} // namespace

nucode::arduino::Nu54SPIClass &SPI = disabled_spi;
#endif

#if !defined(CONFIG_NUCODE_ARDUINO_ADC)
/** @brief ADC 비활성 build에서는 reference 변경을 적용하지 않습니다. */
extern "C" void analogReference(std::uint8_t)
{
}

/** @brief ADC 비활성 build에서는 read resolution을 적용하지 않습니다. */
extern "C" void analogReadResolution(std::uint8_t)
{
}

/** @brief ADC 비활성 build에서는 명시적인 실패값을 반환합니다. */
extern "C" int analogRead(pin_size_t)
{
    return -1;
}
#endif

#if !defined(CONFIG_NUCODE_ARDUINO_PWM)
/** @brief PWM 비활성 build에서는 write resolution을 적용하지 않습니다. */
extern "C" void analogWriteResolution(std::uint8_t)
{
}

/** @brief PWM 비활성 build에서는 주파수 변경을 거부합니다. */
extern "C" bool analogWriteFrequency(pin_size_t, std::uint32_t)
{
    return false;
}

/** @brief PWM 비활성 build에서는 pin 출력을 변경하지 않습니다. */
extern "C" void analogWrite(pin_size_t, int)
{
}

/** @brief PWM 비활성 build에서는 tone 출력을 시작하지 않습니다. */
void tone(std::uint8_t, unsigned int, unsigned long)
{
}

/** @brief PWM 비활성 build에는 중지할 tone 출력이 없습니다. */
void noTone(std::uint8_t)
{
}
#endif
