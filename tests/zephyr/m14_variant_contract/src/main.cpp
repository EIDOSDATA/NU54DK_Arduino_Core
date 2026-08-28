/**
 * @file main.cpp
 * @brief NU54DK production DTS에서 생성한 sparse Variant descriptor를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/ztest.h>

#include <cstddef>

#include "internal/pin_description.h"

namespace
{
	using nucode::arduino::internal::hasPinCapability;
	using nucode::arduino::internal::PinCapability;
	using nucode::arduino::internal::PinDescription;
	using nucode::arduino::internal::pinDescription;

	/** @brief 하나의 공개 논리 pin과 DTS alias의 기대 관계입니다. */
	struct ExpectedPin
	{
		pin_size_t logical_pin;
		gpio_dt_spec gpio;
		PinCapability capabilities;
	};

	/** @brief LED pin의 공개 digital capability입니다. */
	constexpr PinCapability led_capabilities =
		PinCapability::digital_input | PinCapability::digital_output |
		PinCapability::interrupt;

	/** @brief 버튼 pin의 공개 digital capability입니다. */
	constexpr PinCapability button_capabilities =
		PinCapability::digital_input | PinCapability::interrupt;

	/** @brief 물리 GPIO 값은 DTS alias에서만 생성하는 기대 descriptor입니다. */
	const ExpectedPin expected_pins[] = {
		{LED_BUILTIN, GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios), led_capabilities},
		{PIN_BUTTON0, GPIO_DT_SPEC_GET(DT_ALIAS(sw0), gpios), button_capabilities},
		{PIN_LED2, GPIO_DT_SPEC_GET(DT_ALIAS(led2), gpios), led_capabilities},
		{PIN_LED3, GPIO_DT_SPEC_GET(DT_ALIAS(led3), gpios), led_capabilities},
		{PIN_BUTTON1, GPIO_DT_SPEC_GET(DT_ALIAS(sw1), gpios), button_capabilities},
		{PIN_BUTTON2, GPIO_DT_SPEC_GET(DT_ALIAS(sw2), gpios), button_capabilities},
		{PIN_BUTTON3, GPIO_DT_SPEC_GET(DT_ALIAS(sw3), gpios), button_capabilities},
	};

	static_assert(LED_BUILTIN == 0U && PIN_BUTTON0 == 1U && PIN_A0 == 2U &&
				  PIN_PWM0 == 3U,
				  "v0.1 공개 논리 pin 번호를 보존해야 합니다.");
	static_assert(NUM_DIGITAL_PINS == 10U && NUM_DIGITAL_CAPABLE_PINS == 7U &&
				  NUM_PIN_ROLES == 10U,
				  "digital descriptor 개수와 sparse 논리 ID 범위를 분리해야 합니다.");
	static_assert(D0 == LED_BUILTIN && D1 == PIN_BUTTON0,
				  "v0.1 digital 역할의 D0/D1 별칭이 달라졌습니다.");
	static_assert(digitalPinToInterrupt(PIN_A0) == NOT_AN_INTERRUPT &&
				  digitalPinToInterrupt(PIN_PWM0) == NOT_AN_INTERRUPT &&
				  digitalPinToInterrupt(PIN_LED1) == NOT_AN_INTERRUPT,
				  "A0, PWM과 PWM-owned LED를 digital interrupt로 노출하면 안 됩니다.");

	/**
	 * @brief 실제 descriptor와 DTS에서 생성한 기대 GPIO를 비교합니다.
	 *
	 * @param expected 비교할 기대 descriptor입니다.
	 */
	void verifyPin(const ExpectedPin &expected)
	{
		const PinDescription *const actual = pinDescription(expected.logical_pin);
		zassert_not_null(actual, "공개 digital 논리 pin의 descriptor가 없습니다.");
		zassert_equal(actual->gpio.port, expected.gpio.port,
					  "descriptor GPIO controller가 DTS alias와 다릅니다.");
		zassert_equal(actual->gpio.pin, expected.gpio.pin,
					  "descriptor GPIO pin이 DTS alias와 다릅니다.");
		zassert_equal(actual->gpio.dt_flags, expected.gpio.dt_flags,
					  "descriptor GPIO flag가 DTS alias와 다릅니다.");
		zassert_equal(static_cast<unsigned int>(actual->capabilities),
					  static_cast<unsigned int>(expected.capabilities),
					  "descriptor capability가 공개 pin class와 다릅니다.");
	}
}

ZTEST(m14_variant_contract, test_all_public_digital_pins_are_generated_from_dts_aliases)
{
	zassert_equal(nucode::arduino::internal::pinDescriptionCount(),
				  NUM_DIGITAL_CAPABLE_PINS,
				  "production descriptor 개수가 NUM_DIGITAL_CAPABLE_PINS와 다릅니다.");
	for (const auto &expected : expected_pins)
	{
		verifyPin(expected);
	}
}

ZTEST(m14_variant_contract, test_sparse_a0_and_pwm_slots_are_rejected_by_digital_backend)
{
	zassert_is_null(pinDescription(PIN_A0), "A0 sparse slot에 GPIO descriptor가 있습니다.");
	zassert_is_null(pinDescription(PIN_PWM0), "PWM sparse slot에 GPIO descriptor가 있습니다.");
	zassert_is_null(pinDescription(PIN_LED1),
				"PWM-owned LED1 slot에 GPIO descriptor가 있습니다.");
	zassert_is_null(pinDescription(NUM_PIN_ROLES), "범위 밖 descriptor가 nullptr가 아닙니다.");

	pinMode(PIN_A0, OUTPUT);
	zassert_equal(nucode::arduino::internal::lastGpioError(),
				  nucode::arduino::internal::GpioError::invalid_pin,
				  "A0를 digital output으로 요청했을 때 안전하게 거부하지 않았습니다.");
	pinMode(PIN_PWM0, INPUT);
	zassert_equal(nucode::arduino::internal::lastGpioError(),
				  nucode::arduino::internal::GpioError::invalid_pin,
				  "PWM 역할을 digital input으로 요청했을 때 안전하게 거부하지 않았습니다.");
}

ZTEST(m14_variant_contract, test_led_and_button_capability_classes_are_distinct)
{
	const PinDescription *const led = pinDescription(PIN_LED3);
	const PinDescription *const button = pinDescription(PIN_BUTTON3);
	zassert_not_null(led, "LED descriptor가 없습니다.");
	zassert_not_null(button, "버튼 descriptor가 없습니다.");
	zassert_true(hasPinCapability(led->capabilities, PinCapability::digital_output),
				 "LED에 output capability가 없습니다.");
	zassert_false(hasPinCapability(button->capabilities, PinCapability::digital_output),
				  "버튼에 output capability를 잘못 부여했습니다.");
	zassert_true(hasPinCapability(button->capabilities, PinCapability::interrupt),
				 "버튼에 interrupt capability가 없습니다.");
}

ZTEST_SUITE(m14_variant_contract, nullptr, nullptr, nullptr, nullptr, nullptr);
