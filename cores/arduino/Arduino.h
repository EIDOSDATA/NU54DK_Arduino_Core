/**
 * @file Arduino.h
 * @brief NU54DK Arduino Sketch의 공개 API 진입점입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_ARDUINO_H_
#define NUCODE_ARDUINO_CORE_ARDUINO_H_

#include <variant.h>
#include <api/ArduinoAPI.h>

#include "internal/ArduinoUtility.h"

#ifdef __cplusplus
extern "C"
{
#endif

    /**
     * @brief Arduino가 소유한 GPIO callback 전달을 중첩 안전하게 일시 중지합니다.
     *
     * Zephyr kernel, BLE, system timer와 다른 driver IRQ는 중지하지 않습니다. 첫 호출
     * thread만 같은 thread에서 중첩 호출과 복원을 수행할 수 있습니다.
     */
    void noInterrupts(void);

    /**
     * @brief 같은 thread의 마지막 noInterrupts()와 짝을 이루어 GPIO callback을 복원합니다.
     */
    void interrupts(void);

    /** @brief SAADC가 반환할 해상도를 8/10/12/14 bit 중 하나로 선택합니다. */
    void analogReadResolution(uint8_t bits);

    /** @brief analogWrite() 입력값의 해상도를 1~16 bit로 선택합니다. */
    void analogWriteResolution(uint8_t bits);

#ifdef __cplusplus
    /**
     * @brief 지정 PWM 핀의 주파수를 변경합니다.
     *
     * @return 핀과 주파수가 유효하고 기존 PWM 출력과 충돌하지 않으면 true입니다.
     */
    bool analogWriteFrequency(pin_size_t pin, uint32_t frequency_hz);
#endif

#ifdef __cplusplus
}
#endif

#ifdef __cplusplus

#include <api/HardwareI2C.h>
#include <api/HardwareSPI.h>
#include <api/HardwareSerial.h>

#include "NUCODEPeripheral.h"

/** @brief ArduinoCore-API의 HardwareSerial 형식을 전역 호환 이름으로 노출합니다. */
using arduino::HardwareSerial;

/** @brief ArduinoCore-API의 HardwareI2C 형식을 전역 호환 이름으로 노출합니다. */
using arduino::HardwareI2C;

/** @brief 기존 Wire API와 NU54DK runtime 핀 선택을 함께 제공하는 형식입니다. */
using TwoWire = nucode::arduino::Nu54TwoWire;

/** @brief ArduinoCore-API의 HardwareSPI 형식을 전역 호환 이름으로 노출합니다. */
using arduino::HardwareSPI;

/** @brief 기존 SPI API와 NU54DK runtime 핀 선택을 함께 제공하는 형식입니다. */
using SPIClass = nucode::arduino::Nu54SPIClass;

/** @brief ArduinoCore-API의 SPISettings 형식을 전역으로 노출합니다. */
using arduino::SPISettings;

/** @brief ArduinoCore-API의 SPIMode 형식을 전역으로 노출합니다. */
using arduino::SPIMode;

/** @brief ArduinoCore-API의 SPIBusMode 형식을 전역으로 노출합니다. */
using arduino::SPIBusMode;

using arduino::SPI_CONTROLLER;
using arduino::SPI_MODE0;
using arduino::SPI_MODE1;
using arduino::SPI_MODE2;
using arduino::SPI_MODE3;
using arduino::SPI_PERIPHERAL;

/** @brief ArduinoCore-API의 String 형식을 전역 호환 이름으로 노출합니다. */
using arduino::String;

/** @brief ArduinoCore-API의 Print 형식을 전역 호환 이름으로 노출합니다. */
using arduino::Print;

/** @brief ArduinoCore-API의 Stream 형식을 전역 호환 이름으로 노출합니다. */
using arduino::Stream;

/** @brief ArduinoCore-API의 Printable 형식을 전역 호환 이름으로 노출합니다. */
using arduino::Printable;

/** @brief 정수 상태 값을 허용하는 기존 Arduino digitalWrite 호환 overload입니다. */
using arduino::digitalWrite;

/** @brief 정수 mode 값을 허용하는 기존 Arduino pinMode 호환 overload입니다. */
using arduino::pinMode;

/**
 * @brief Zephyr console UART를 빌려 사용하는 기본 Arduino Serial입니다.
 *
 * 장치 초기화, pinctrl, baud와 전원 수명주기는 Zephyr가 소유합니다.
 */
extern HardwareSerial &Serial;

/** @brief Wire, SPI와 Serial1의 concrete extern은 NUCODEPeripheral.h가 단일 소유합니다. */

#endif

#endif
