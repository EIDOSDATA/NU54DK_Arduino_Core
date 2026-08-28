/**
 * @file variant.cpp
 * @brief NU54DK Devicetree alias에서 Arduino 논리 핀 설명자를 생성합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <variant.h>

#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/util.h>

#include "internal/pin_description.h"

#define NUCODE_NU54DK_DIGITAL_PIN(logical_pin, alias_name, pin_class)                     \
	static_assert(DT_NODE_HAS_STATUS_OKAY(DT_ALIAS(alias_name)),                          \
				  "NU54DK Arduino Variant의 필수 GPIO alias가 활성화되어야 합니다."); \
	static_assert(DT_NODE_HAS_PROP(DT_ALIAS(alias_name), gpios),                          \
				  "NU54DK Arduino Variant의 필수 alias에는 gpios가 필요합니다.");
#include "digital_pins.inc"
#undef NUCODE_NU54DK_DIGITAL_PIN

namespace nucode::arduino::internal
{
	namespace
	{
		/** @brief 하나의 sparse 논리 ID와 실제 GPIO descriptor를 결합합니다. */
		struct LogicalPinDescription
		{
			pin_size_t logical_pin;
			PinDescription description;
		};

		/** @brief LED alias에 허용하는 Arduino GPIO capability입니다. */
		constexpr PinCapability led_capabilities =
			PinCapability::digital_input | PinCapability::digital_output |
			PinCapability::interrupt;

		/** @brief 버튼 alias에 허용하는 Arduino GPIO capability입니다. */
		constexpr PinCapability button_capabilities =
			PinCapability::digital_input | PinCapability::interrupt;

#define NUCODE_NU54DK_CAPABILITIES_led led_capabilities
#define NUCODE_NU54DK_CAPABILITIES_button button_capabilities
#define NUCODE_NU54DK_DESCRIPTOR_led(logical_pin, alias_name)    \
	{static_cast<pin_size_t>(logical_pin),                         \
	 {GPIO_DT_SPEC_GET(DT_ALIAS(alias_name), gpios),               \
	  NUCODE_NU54DK_CAPABILITIES_led}},
#define NUCODE_NU54DK_DESCRIPTOR_button(logical_pin, alias_name) \
	{static_cast<pin_size_t>(logical_pin),                         \
	 {GPIO_DT_SPEC_GET(DT_ALIAS(alias_name), gpios),               \
	  NUCODE_NU54DK_CAPABILITIES_button}},
#define NUCODE_NU54DK_DESCRIPTOR_pwm_owned(logical_pin, alias_name)
#define NUCODE_NU54DK_SELECT_DESCRIPTOR(logical_pin, alias_name, pin_class) \
	NUCODE_NU54DK_DESCRIPTOR_##pin_class(logical_pin, alias_name)

		/**
		 * @brief DTS alias와 sparse Arduino 논리 ID로 생성한 immutable 설명자입니다.
		 */
		const LogicalPinDescription pin_descriptions[] = {
#define NUCODE_NU54DK_DIGITAL_PIN(logical_pin, alias_name, pin_class) \
	NUCODE_NU54DK_SELECT_DESCRIPTOR(logical_pin, alias_name, pin_class)
#include "digital_pins.inc"
#undef NUCODE_NU54DK_DIGITAL_PIN
		};

		static_assert(ARRAY_SIZE(pin_descriptions) == NUM_DIGITAL_CAPABLE_PINS,
					  "공개 논리 핀 개수와 NU54DK 설명자 개수가 일치해야 합니다.");
		static_assert(PIN_A0 < NUM_PIN_ROLES && PIN_PWM0 < NUM_PIN_ROLES &&
					  PIN_BUTTON3 < NUM_PIN_ROLES,
					  "모든 공개 논리 ID가 NUM_PIN_ROLES 범위 안에 있어야 합니다.");

#undef NUCODE_NU54DK_SELECT_DESCRIPTOR
#undef NUCODE_NU54DK_DESCRIPTOR_pwm_owned
#undef NUCODE_NU54DK_DESCRIPTOR_button
#undef NUCODE_NU54DK_DESCRIPTOR_led
#undef NUCODE_NU54DK_CAPABILITIES_button
#undef NUCODE_NU54DK_CAPABILITIES_led

	}

	const PinDescription *pinDescription(std::size_t logical_pin) noexcept
	{
		if (logical_pin >= NUM_PIN_ROLES)
		{
			return nullptr;
		}

		for (const auto &entry : pin_descriptions)
		{
			if (logical_pin == static_cast<std::size_t>(entry.logical_pin))
			{
				return &entry.description;
			}
		}

		return nullptr;
	}
	std::size_t pinDescriptionCount() noexcept
	{
		return ARRAY_SIZE(pin_descriptions);
	}

}
