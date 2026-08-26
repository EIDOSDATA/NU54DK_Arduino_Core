/**
 * @file variant.h
 * @brief NU54DK의 M3 Arduino 논리 핀 상수를 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_VARIANTS_NU54DK_VARIANT_H_
#define NUCODE_ARDUINO_VARIANTS_NU54DK_VARIANT_H_

/** @brief 보드 Devicetree의 led0 alias에 대응하는 Arduino 논리 핀입니다. */
#define LED_BUILTIN 0U

/** @brief 보드 Devicetree의 sw0 alias에 대응하는 NU54DK 시험용 논리 핀입니다. */
#define PIN_BUTTON0 1U

/** @brief M3 Variant가 현재 제공하는 digital 논리 핀 개수입니다. */
#define NUM_DIGITAL_PINS 2U

#endif
