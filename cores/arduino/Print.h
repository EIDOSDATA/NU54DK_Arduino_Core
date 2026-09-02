/**
 * @file Print.h
 * @brief 기존 Arduino library가 사용하는 전역 Print 호환 헤더입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_PRINT_H_
#define NUCODE_ARDUINO_CORE_PRINT_H_

#include <api/Print.h>

#ifdef __cplusplus
/** @brief ArduinoCore-API의 Print 형식을 기존 Arduino 전역 이름으로 노출합니다. */
using arduino::Print;
#endif

#endif
