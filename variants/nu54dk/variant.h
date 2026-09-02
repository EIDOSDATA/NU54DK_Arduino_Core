/**
 * @file variant.h
 * @brief NU54DK의 Arduino 논리 핀과 canonical 물리 핀 상수를 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_VARIANTS_NU54DK_VARIANT_H_
#define NUCODE_ARDUINO_VARIANTS_NU54DK_VARIANT_H_

#if defined(__ZEPHYR__)
#include <zephyr/devicetree.h>
#endif

#include <api/Common.h>

#if defined(__ZEPHYR__) && defined(CONFIG_NUCODE_ARDUINO_CONNECTOR_GPIO)
#if DT_NODE_HAS_STATUS_OKAY(DT_ALIAS(nucode_gpio0)) && \
	DT_NODE_HAS_STATUS_OKAY(DT_ALIAS(nucode_gpio1))
#define NUCODE_NU54DK_HAS_CONNECTOR_GPIO 1
#else
#define NUCODE_NU54DK_HAS_CONNECTOR_GPIO 0
#endif
#else
#define NUCODE_NU54DK_HAS_CONNECTOR_GPIO 0
#endif

#if defined(CONFIG_NUCODE_ARDUINO_DAP_UART_GPIO_PINS)
#define NUCODE_NU54DK_HAS_DAP_UART_GPIO_PINS 1
#else
#define NUCODE_NU54DK_HAS_DAP_UART_GPIO_PINS 0
#endif

#if defined(CONFIG_NUCODE_ARDUINO_LFXO_GPIO_PINS)
#define NUCODE_NU54DK_HAS_LFXO_GPIO_PINS 1
#else
#define NUCODE_NU54DK_HAS_LFXO_GPIO_PINS 0
#endif

/** @brief v0.1~v0.2 공개 ID는 값을 변경하지 않습니다. */
#define LED_BUILTIN 0U
#define D0 LED_BUILTIN
#define PIN_LED0 LED_BUILTIN
#define PIN_BUTTON0 1U
#define D1 PIN_BUTTON0
#define PIN_A0 2U
#define PIN_PWM0 3U
#define PIN_PWM_LED PIN_PWM0
/** @brief legacy ID 4이며 내부에서 P1.10의 canonical ID 3으로 정규화됩니다. */
#define PIN_LED1 4U
#define PIN_LED2 5U
#define PIN_LED3 6U
#define PIN_BUTTON1 7U
#define PIN_BUTTON2 8U
#define PIN_BUTTON3 9U
#define PIN_GPIO0 10U
#define D10 PIN_GPIO0
#define PIN_GPIO1 11U
#define D11 PIN_GPIO1

/** @brief 나머지 실제 module/header pad에는 기존 ID 뒤의 안정된 canonical ID를 부여합니다. */
#define PIN_P0_00 12U
#define PIN_P0_01 13U
#define PIN_P0_02 14U
#define PIN_P0_03 15U
#define PIN_P1_00 16U
#define PIN_P1_01 17U
#define PIN_P1_02 18U
#define PIN_P1_03 19U
#define PIN_P1_04 20U
#define PIN_P1_05 21U
#define PIN_P1_06 22U
#define PIN_P1_07 23U
#define PIN_P1_11 24U
#define PIN_P2_00 25U
#define PIN_P2_01 26U
#define PIN_P2_02 27U
#define PIN_P2_03 28U
#define PIN_P2_04 29U
#define PIN_P2_08 30U
#define PIN_P2_10 31U

/** @brief nRF54L15 SAADC AIN0~AIN7의 실제 pad 별칭입니다. */
#define PIN_AIN0 PIN_P1_04
#define PIN_AIN1 PIN_P1_05
#define PIN_AIN2 PIN_P1_06
#define PIN_AIN3 PIN_P1_07
#define PIN_AIN4 PIN_P1_11
#define PIN_AIN5 PIN_A0
#define PIN_AIN6 PIN_BUTTON0
#define PIN_AIN7 PIN_LED3

/** @brief 기존 역할과 같은 pad의 물리 이름은 같은 canonical ID를 사용합니다. */
#define PIN_P0_04 PIN_BUTTON3
#define PIN_P1_08 PIN_BUTTON2
#define PIN_P1_09 PIN_BUTTON1
#define PIN_P1_10 PIN_PWM0
#define PIN_P1_12 PIN_A0
#define PIN_P1_13 PIN_BUTTON0
#define PIN_P1_14 PIN_LED3
#define PIN_P2_05 PIN_GPIO0
#define PIN_P2_06 PIN_GPIO1
#define PIN_P2_07 PIN_LED2
#define PIN_P2_09 LED_BUILTIN

#ifdef __cplusplus
/** @brief Arduino 호환 A0 상수입니다. */
inline constexpr pin_size_t A0 = static_cast<pin_size_t>(PIN_A0);
inline constexpr pin_size_t A1 = static_cast<pin_size_t>(PIN_AIN0);
inline constexpr pin_size_t A2 = static_cast<pin_size_t>(PIN_AIN1);
inline constexpr pin_size_t A3 = static_cast<pin_size_t>(PIN_AIN2);
inline constexpr pin_size_t A4 = static_cast<pin_size_t>(PIN_AIN3);
inline constexpr pin_size_t A5 = static_cast<pin_size_t>(PIN_AIN4);
inline constexpr pin_size_t A6 = static_cast<pin_size_t>(PIN_AIN6);
inline constexpr pin_size_t A7 = static_cast<pin_size_t>(PIN_AIN7);
#else
enum
{
	A0 = PIN_A0,
	A1 = PIN_AIN0,
	A2 = PIN_AIN1,
	A3 = PIN_AIN2,
	A4 = PIN_AIN3,
	A5 = PIN_AIN4,
	A6 = PIN_AIN6,
	A7 = PIN_AIN7
};
#endif

#define NUM_PIN_ROLES 32U
#define NUM_DIGITAL_PINS NUM_PIN_ROLES
#define NUM_PHYSICAL_PINS 31U
#define NUM_DIGITAL_CAPABLE_PINS                         \
	(20U + (4U * NUCODE_NU54DK_HAS_DAP_UART_GPIO_PINS) + \
	 (2U * NUCODE_NU54DK_HAS_LFXO_GPIO_PINS))
#define NUM_ANALOG_INPUTS 8U
#define NUM_ANALOG_OUTPUTS 1U

#define AR_DEFAULT 0U
#define AR_INTERNAL AR_DEFAULT
#ifndef DEFAULT
#define DEFAULT AR_DEFAULT
#endif

#define NOT_AN_INTERRUPT 0xFFU

#ifdef __cplusplus

/** @brief legacy logical ID를 canonical 물리 ID로 정규화합니다. */
[[nodiscard]] constexpr pin_size_t canonicalDigitalPin(pin_size_t pin) noexcept
{
	return pin == static_cast<pin_size_t>(PIN_LED1)
			   ? static_cast<pin_size_t>(PIN_PWM0)
			   : pin;
}

/** @brief 논리 ID가 현재 profile에서 digital GPIO 기능을 제공하는지 확인합니다. */
[[nodiscard]] constexpr bool digitalPinIsValid(pin_size_t pin) noexcept
{
	const pin_size_t canonical = canonicalDigitalPin(pin);
	const bool always_available =
		(canonical <= static_cast<pin_size_t>(PIN_GPIO1)) ||
		((canonical >= static_cast<pin_size_t>(PIN_P1_02)) &&
		 (canonical <= static_cast<pin_size_t>(PIN_P1_03))) ||
		(canonical == static_cast<pin_size_t>(PIN_P1_11)) ||
		((canonical >= static_cast<pin_size_t>(PIN_P2_00)) &&
		 (canonical <= static_cast<pin_size_t>(PIN_P2_08)));
	const bool dap_uart_available = NUCODE_NU54DK_HAS_DAP_UART_GPIO_PINS &&
									(canonical >= static_cast<pin_size_t>(PIN_P0_00)) &&
									(canonical <= static_cast<pin_size_t>(PIN_P0_03));
	const bool lfxo_available = NUCODE_NU54DK_HAS_LFXO_GPIO_PINS &&
								(canonical >= static_cast<pin_size_t>(PIN_P1_00)) &&
								(canonical <= static_cast<pin_size_t>(PIN_P1_01));
	return always_available || dap_uart_available || lfxo_available;
}

/** @brief P0/P1 GPIOTE 가능 핀만 canonical interrupt 번호로 변환합니다. */
[[nodiscard]] constexpr pin_size_t digitalPinToInterrupt(pin_size_t pin) noexcept
{
	const pin_size_t canonical = canonicalDigitalPin(pin);
	const bool port0 =
		(canonical == static_cast<pin_size_t>(PIN_P0_04)) ||
		(NUCODE_NU54DK_HAS_DAP_UART_GPIO_PINS &&
		 (canonical >= static_cast<pin_size_t>(PIN_P0_00)) &&
		 (canonical <= static_cast<pin_size_t>(PIN_P0_03)));
	const bool port1 =
		(canonical == static_cast<pin_size_t>(PIN_P1_08)) ||
		(canonical == static_cast<pin_size_t>(PIN_P1_09)) ||
		(canonical == static_cast<pin_size_t>(PIN_P1_10)) ||
		(canonical == static_cast<pin_size_t>(PIN_P1_12)) ||
		(canonical == static_cast<pin_size_t>(PIN_P1_13)) ||
		(canonical == static_cast<pin_size_t>(PIN_P1_14)) ||
		((canonical >= static_cast<pin_size_t>(PIN_P1_02)) &&
		 (canonical <= static_cast<pin_size_t>(PIN_P1_11))) ||
		(NUCODE_NU54DK_HAS_LFXO_GPIO_PINS &&
		 (canonical >= static_cast<pin_size_t>(PIN_P1_00)) &&
		 (canonical <= static_cast<pin_size_t>(PIN_P1_01)));
	return digitalPinIsValid(canonical) && (port0 || port1)
			   ? canonical
			   : static_cast<pin_size_t>(NOT_AN_INTERRUPT);
}

#else

static inline pin_size_t canonicalDigitalPin(pin_size_t pin)
{
	return pin == (pin_size_t)PIN_LED1 ? (pin_size_t)PIN_PWM0 : pin;
}

static inline int digitalPinIsValid(pin_size_t pin)
{
	const pin_size_t canonical = canonicalDigitalPin(pin);
	return (canonical <= (pin_size_t)PIN_GPIO1) ||
		   ((canonical >= (pin_size_t)PIN_P1_02) &&
			(canonical <= (pin_size_t)PIN_P1_03)) ||
		   (canonical == (pin_size_t)PIN_P1_11) ||
		   ((canonical >= (pin_size_t)PIN_P2_00) &&
			(canonical <= (pin_size_t)PIN_P2_08)) ||
		   (NUCODE_NU54DK_HAS_DAP_UART_GPIO_PINS &&
			(canonical >= (pin_size_t)PIN_P0_00) &&
			(canonical <= (pin_size_t)PIN_P0_03)) ||
		   (NUCODE_NU54DK_HAS_LFXO_GPIO_PINS &&
			(canonical >= (pin_size_t)PIN_P1_00) &&
			(canonical <= (pin_size_t)PIN_P1_01));
}

static inline pin_size_t digitalPinToInterrupt(pin_size_t pin)
{
	const pin_size_t canonical = canonicalDigitalPin(pin);
	const int port0 = (canonical == (pin_size_t)PIN_P0_04) ||
					  (NUCODE_NU54DK_HAS_DAP_UART_GPIO_PINS &&
					   (canonical >= (pin_size_t)PIN_P0_00) &&
					   (canonical <= (pin_size_t)PIN_P0_03));
	const int port1 =
		(canonical == (pin_size_t)PIN_P1_08) ||
		(canonical == (pin_size_t)PIN_P1_09) ||
		(canonical == (pin_size_t)PIN_P1_10) ||
		(canonical == (pin_size_t)PIN_P1_12) ||
		(canonical == (pin_size_t)PIN_P1_13) ||
		(canonical == (pin_size_t)PIN_P1_14) ||
		((canonical >= (pin_size_t)PIN_P1_02) &&
		 (canonical <= (pin_size_t)PIN_P1_11)) ||
		(NUCODE_NU54DK_HAS_LFXO_GPIO_PINS &&
		 (canonical >= (pin_size_t)PIN_P1_00) &&
		 (canonical <= (pin_size_t)PIN_P1_01));
	return digitalPinIsValid(canonical) && (port0 || port1)
			   ? canonical
			   : (pin_size_t)NOT_AN_INTERRUPT;
}

#endif

#endif
