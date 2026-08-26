/**
 * @file variant.h
 * @brief NU54DK의 Arduino 논리 핀 상수를 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_VARIANTS_NU54DK_VARIANT_H_
#define NUCODE_ARDUINO_VARIANTS_NU54DK_VARIANT_H_

#include <api/Common.h>

/** @brief 보드 Devicetree의 led0 alias에 대응하는 Arduino 논리 핀입니다. */
#define LED_BUILTIN 0U

/** @brief 보드 Devicetree의 sw0 alias에 대응하는 NU54DK 시험용 논리 핀입니다. */
#define PIN_BUTTON0 1U

/** @brief NU54DK Variant가 현재 제공하는 digital 논리 핀 개수입니다. */
#define NUM_DIGITAL_PINS 2U

/** @brief 유효하지 않은 Arduino interrupt 번호입니다. */
#define NOT_AN_INTERRUPT 0xFFU

#ifdef __cplusplus

/**
 * @brief Arduino 논리 핀을 interrupt 번호로 안전하게 변환합니다.
 *
 * @param pin 변환할 Arduino 논리 핀입니다.
 * @return 유효하면 같은 번호, 범위를 벗어나면 NOT_AN_INTERRUPT입니다.
 */
[[nodiscard]] constexpr pin_size_t digitalPinToInterrupt(pin_size_t pin) noexcept
{
	return (pin < static_cast<pin_size_t>(NUM_DIGITAL_PINS))
		       ? pin
		       : static_cast<pin_size_t>(NOT_AN_INTERRUPT);
}

#else

/**
 * @brief C 호출부에서 Arduino 논리 핀을 interrupt 번호로 안전하게 변환합니다.
 *
 * @param pin 변환할 Arduino 논리 핀입니다.
 * @return 유효하면 같은 번호, 범위를 벗어나면 NOT_AN_INTERRUPT입니다.
 */
static inline pin_size_t digitalPinToInterrupt(pin_size_t pin)
{
	return (pin < (pin_size_t)NUM_DIGITAL_PINS) ? pin : (pin_size_t)NOT_AN_INTERRUPT;
}

#endif

#endif
