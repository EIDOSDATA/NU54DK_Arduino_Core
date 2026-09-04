/**
 * @file wire_pmic_id.cpp
 * @brief 온보드 BQ25186 Device ID repeated-start HIL firmware입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include "internal/WireBackend.h"

#include <cstddef>
#include <cstdint>
#include <string.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>

namespace
{
    /** @brief NU54DK 온보드 BQ25186의 고정 7-bit 주소입니다. */
    constexpr std::uint8_t pmic_address = 0x6AU;

    /** @brief BQ25186 MASK_ID register입니다. */
    constexpr std::uint8_t mask_id_register = 0x0CU;

    /** @brief MASK_ID 하위 nibble에 있는 Device ID mask입니다. */
    constexpr std::uint8_t device_id_mask = 0x0FU;

    /** @brief BQ25186이 반환해야 하는 Device ID입니다. */
    constexpr std::uint8_t device_id_expected = 0x01U;

    /** @brief HIL host가 보낼 수 있는 유일한 고정 요청입니다. */
    constexpr char request_token[] = "NUCODE_M7_I2C_PMIC_ID_RS:6A:0C";

    /** @brief UART protocol에서 byte를 두 자리 대문자 16진수로 출력할 표입니다. */
    constexpr char hexadecimal_digits[] = "0123456789ABCDEF";

    /** @brief I2C22 SDA가 연결된 GPIO1 pin 번호입니다. */
    constexpr gpio_pin_t sda_pin = 2U;

    /** @brief I2C22 SCL이 연결된 GPIO1 pin 번호입니다. */
    constexpr gpio_pin_t scl_pin = 3U;

    /** @brief I2C22 line level을 읽을 GPIO1 controller입니다. */
    const struct device *const gpio1 = DEVICE_DT_GET(DT_NODELABEL(gpio1));

    char request_buffer[sizeof(request_token)] = {};
    std::size_t request_length = 0U;
    bool request_overflow = false;
    int gpio_before = -1;
    int sda_before = -1;
    int scl_before = -1;

    /**
	 * @brief I2C22 SDA와 SCL의 현재 논리값을 읽습니다.
	 *
	 * @param sda SDA 논리값을 받을 위치입니다.
	 * @param scl SCL 논리값을 받을 위치입니다.
	 * @return GPIO port read 결과입니다.
	 */
    int readBusLevels(int &sda, int &scl)
    {
        gpio_port_value_t value = 0U;
        if (!device_is_ready(gpio1))
        {
            return -ENODEV;
        }

        const int result = gpio_port_get_raw(gpio1, &value);
        if (result == 0)
        {
            sda = ((value & (1UL << sda_pin)) != 0U) ? 1 : 0;
            scl = ((value & (1UL << scl_pin)) != 0U) ? 1 : 0;
        }
        return result;
    }

    /**
	 * @brief Wire Core 상태와 원래 Zephyr driver 오류를 UART로 보고합니다.
	 *
	 * @param stage 실패한 고정 transaction 단계입니다.
	 */
    void reportWireFailure(const char *stage)
    {
        int sda = -1;
        int scl = -1;
        const int gpio_result = readBusLevels(sda, scl);

        Serial.print("NUCODE_M7_I2C_ERROR:");
        Serial.print(stage);
        Serial.print(":BACKEND=");
        Serial.print(static_cast<int>(nucode::arduino::internal::lastWireError()));
        Serial.print(":ERRNO=");
        Serial.print(nucode::arduino::internal::lastWireDriverError());
        Serial.print(":GPIO_BEFORE=");
        Serial.print(gpio_before);
        Serial.print(":SDA_BEFORE=");
        Serial.print(sda_before);
        Serial.print(":SCL_BEFORE=");
        Serial.print(scl_before);
        Serial.print(":GPIO_AFTER=");
        Serial.print(gpio_result);
        Serial.print(":SDA_AFTER=");
        Serial.print(sda);
        Serial.print(":SCL_AFTER=");
        Serial.println(scl);
    }

    /**
	 * @brief BQ25186 MASK_ID를 no-STOP pointer write와 repeated-start read로 읽습니다.
	 *
	 * 첫 I2C transaction은 PMIC의 기본 160초 watchdog을 시작합니다. 이 함수는
	 * register 값을 쓰지 않으며 Device ID가 있는 하위 nibble만 판정합니다.
	 */
    void readPmicId(void)
    {
        gpio_before = readBusLevels(sda_before, scl_before);
        Wire.beginTransmission(pmic_address);
        if ((Wire.write(mask_id_register) != 1U) || (Wire.endTransmission(false) != 0U))
        {
            reportWireFailure("TX");
            return;
        }

        if ((Wire.requestFrom(pmic_address, 1U, true) != 1U) || (Wire.available() != 1))
        {
            reportWireFailure("RX");
            return;
        }

        const int value = Wire.read();
        if ((value < 0) ||
            ((static_cast<std::uint8_t>(value) & device_id_mask) != device_id_expected))
        {
            Serial.println("NUCODE_M7_I2C_ERROR:PMIC_ID");
            return;
        }

        const std::uint8_t register_value = static_cast<std::uint8_t>(value);
        Serial.print("NUCODE_M7_I2C_RESULT:6A:0C:");
        Serial.print(hexadecimal_digits[(register_value >> 4U) & 0x0FU]);
        Serial.print(hexadecimal_digits[register_value & 0x0FU]);
        Serial.println(":RS");
    }

    /** @brief 완성된 UART 줄이 고정 HIL 요청과 같은 경우에만 I2C를 실행합니다. */
    void finishRequest(void)
    {
        request_buffer[request_length] = '\0';
        if (!request_overflow && (request_length == (sizeof(request_token) - 1U)) &&
            (strcmp(request_buffer, request_token) == 0))
        {
            readPmicId();
        }

        request_length = 0U;
        request_overflow = false;
    }

    /**
	 * @brief 한 UART byte를 고정 요청 parser에 반영합니다.
	 *
	 * @param value 수신한 byte입니다.
	 */
    void consumeRequestByte(char value)
    {
        if (value == '\r')
        {
            return;
        }
        if (value == '\n')
        {
            finishRequest();
            return;
        }

        if (request_length < (sizeof(request_buffer) - 1U))
        {
            request_buffer[request_length++] = value;
        }
        else
        {
            request_overflow = true;
        }
    }
} // namespace

/** @brief Serial과 400 kHz Wire controller를 시작하고 준비 token을 출력합니다. */
void setup(void)
{
    Serial.begin(115200U);
    Wire.begin();
    Wire.setClock(400000U);
    Serial.println("NUCODE_M7_I2C_READY");
}

/** @brief 고정 UART 요청만 수신하며 I2C 주소 탐색은 수행하지 않습니다. */
void loop(void)
{
    while (Serial.available() > 0)
    {
        const int value = Serial.read();
        if (value < 0)
        {
            break;
        }
        consumeRequestByte(static_cast<char>(value));
    }
    delay(1U);
}
