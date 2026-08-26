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

/** @brief board SAADC channel 5/P1.12에 대응하는 analog 입력 역할입니다. */
#define PIN_A0 2U

#ifdef __cplusplus
/** @brief Nordic register field와 충돌하지 않는 C++ Arduino A0 상수입니다. */
inline constexpr pin_size_t A0 = static_cast<pin_size_t>(PIN_A0);
#else
/** @brief C source에서 사용하는 Arduino 호환 A0 이름입니다. */
enum { A0 = PIN_A0 };
#endif

/** @brief board pwm_led1/P1.10 chosen에 대응하는 analogWrite 역할입니다. */
#define PIN_PWM0 3U

/** @brief 회로상의 PWM LED 역할을 설명하는 PIN_PWM0 별칭입니다. */
#define PIN_PWM_LED PIN_PWM0

/** @brief NU54DK Variant가 제공하는 analog 입력 역할 개수입니다. */
#define NUM_ANALOG_INPUTS 1U

/** @brief NU54DK Variant가 제공하는 PWM 출력 역할 개수입니다. */
#define NUM_ANALOG_OUTPUTS 1U

/** @brief digital, analog 입력과 PWM 역할을 합친 논리 역할 개수입니다. */
#define NUM_PIN_ROLES 4U

/** @brief Core overlay의 ADC_GAIN_1_4/ADC_REF_INTERNAL 설정을 사용하는 기본 mode입니다. */
#define AR_DEFAULT 0U

/** @brief NU54DK의 고정 internal reference를 설명하는 AR_DEFAULT 별칭입니다. */
#define AR_INTERNAL AR_DEFAULT

#ifndef DEFAULT
/** @brief 일반 Arduino Sketch의 analogReference(DEFAULT) 호환 이름입니다. */
#define DEFAULT AR_DEFAULT
#endif

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
