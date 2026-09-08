/** @file @brief 기존 S net의 SPI/TWI 역할을 핀 추가 없이 양쪽 함께 전환합니다. */
#pragma once
#include "model.h"

namespace t13
{
    /** @brief 생성된 단독 pair만 전환하며 유효하지 않은 입력은 변경하지 않습니다. */
    inline bool reverseSerialCase(Case &test)
    {
        if (test.serial_count != 1U || test.adc_channels != 0U || test.pwm_instance != 0U ||
            test.pdm_instance != 0U || test.i2s)
        {
            return false;
        }
        const auto first = test.serial[0][0].kind;
        const auto second = test.serial[1][0].kind;
        const bool spi = (first == Kind::spim && second == Kind::spis) ||
                         (first == Kind::spis && second == Kind::spim);
        const bool twi = (first == Kind::twim && second == Kind::twis) ||
                         (first == Kind::twis && second == Kind::twim);
        if (!spi && !twi)
        {
            return false;
        }
        for (unsigned role = 0U; role < 2U; ++role)
        {
            const auto &endpoint = test.serial[role][0];
            if (endpoint.pin_count != (spi ? 4U : 2U))
            {
                return false;
            }
            unsigned mosi = 0U, miso = 0U;
            for (unsigned pin = 0U; pin < endpoint.pin_count; ++pin)
            {
                mosi += endpoint.signals[pin] == 6U ? 1U : 0U;
                miso += endpoint.signals[pin] == 7U ? 1U : 0U;
            }
            if (spi && (mosi != 1U || miso != 1U))
            {
                return false;
            }
        }
        for (unsigned role = 0U; role < 2U; ++role)
        {
            auto &endpoint = test.serial[role][0];
            endpoint.kind = spi ? (endpoint.kind == Kind::spim ? Kind::spis : Kind::spim)
                                : (endpoint.kind == Kind::twim ? Kind::twis : Kind::twim);
            if (spi)
            {
                for (unsigned pin = 0U; pin < endpoint.pin_count; ++pin)
                {
                    /** @brief case 생성기의 SerialSignal::mosi(6)·miso(7)만 서로 바꿉니다. */
                    if (endpoint.signals[pin] == 6U || endpoint.signals[pin] == 7U)
                    {
                        endpoint.signals[pin] = 13U - endpoint.signals[pin];
                    }
                }
            }
        }
        return true;
    }
} // namespace t13
