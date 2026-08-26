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

#include <api/HardwareSerial.h>

/** @brief ArduinoCore-API의 HardwareSerial 형식을 전역 호환 이름으로 노출합니다. */
using arduino::HardwareSerial;

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

#endif

#endif
