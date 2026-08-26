/**
 * @file Arduino.h
 * @brief NU54DK Arduino Sketch의 공개 API 진입점입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_ARDUINO_H_
#define NUCODE_ARDUINO_CORE_ARDUINO_H_

#include <api/ArduinoAPI.h>
#include <variant.h>

#ifdef __cplusplus

#include <api/HardwareI2C.h>
#include <api/HardwareSPI.h>
#include <api/HardwareSerial.h>

/** @brief ArduinoCore-API의 HardwareSerial 형식을 전역 호환 이름으로 노출합니다. */
using arduino::HardwareSerial;

/** @brief ArduinoCore-API의 HardwareI2C 형식을 전역 호환 이름으로 노출합니다. */
using arduino::HardwareI2C;

/** @brief Arduino Wire 관례에 맞춘 HardwareI2C 호환 이름입니다. */
using TwoWire = arduino::HardwareI2C;

/** @brief ArduinoCore-API의 HardwareSPI 형식을 전역 호환 이름으로 노출합니다. */
using arduino::HardwareSPI;

/** @brief ArduinoCore-API의 SPIClass 호환 이름을 전역으로 노출합니다. */
using arduino::SPIClass;

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

/**
 * @brief Zephyr console UART를 빌려 사용하는 기본 Arduino Serial입니다.
 *
 * 장치 초기화, pinctrl, baud와 전원 수명주기는 Zephyr가 소유합니다.
 */
extern HardwareSerial &Serial;

/** @brief app overlay가 선택한 NU54DK Qwiic I2C controller입니다. */
extern TwoWire &Wire;

/**
 * @brief app overlay가 선택한 CS 없는 NU54DK SPI controller입니다.
 *
 * 외부 target의 CS는 Sketch가 별도의 확정된 GPIO 역할로 직접 관리해야 합니다.
 */
extern SPIClass &SPI;

#endif

#endif
