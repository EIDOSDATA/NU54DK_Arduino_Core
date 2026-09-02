/**
 * @file variant.h
 * @brief M3 GPIO 회귀 시험용 논리 핀 상수를 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_TEST_M3_VARIANT_H_
#define NUCODE_ARDUINO_TEST_M3_VARIANT_H_

/** @brief 입출력을 모두 지원하는 정상 GPIO입니다. */
#define LED_BUILTIN 0U

/** @brief 입력만 지원하는 GPIO입니다. */
#define PIN_INPUT_ONLY 1U

/** @brief 출력만 지원하는 GPIO입니다. */
#define PIN_OUTPUT_ONLY 2U

/** @brief 미설정 입력 오류 시험 전용 GPIO입니다. */
#define PIN_UNCONFIGURED_INPUT 3U

/** @brief 지원하지 않는 Devicetree flag 시험 전용 GPIO입니다. */
#define PIN_UNSUPPORTED_FLAGS 4U

/** @brief 시험 Variant가 제공하는 논리 GPIO 개수입니다. */
#define NUM_DIGITAL_PINS 5U

#endif
