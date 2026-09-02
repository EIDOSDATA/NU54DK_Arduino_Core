/**
 * @file test_variant.cpp
 * @brief GPIO emulator를 사용하는 M3 자동 회귀용 Variant를 제공합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <variant.h>

#include <zephyr/devicetree.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/util.h>

#include <cstddef>

#include "internal/pin_description.h"

namespace nucode::arduino::internal
{
	namespace
	{

		/** @brief 시험용 GPIO emulator 장치입니다. */
		const struct device *const test_gpio = DEVICE_DT_GET(DT_NODELABEL(test_gpio));

		/** @brief 각 오류 경로를 독립적으로 확인하는 논리 핀 설명자입니다. */
		const PinDescription pin_descriptions[] = {
			{0U, {test_gpio, 0U, 0U}, PinCapability::digital_input | PinCapability::digital_output, PinOwnership::connector_gpio, PinPolicy::normal, PinRoute::gpio, -1},
			{1U, {test_gpio, 1U, 0U}, PinCapability::digital_input, PinOwnership::connector_gpio, PinPolicy::input_only, PinRoute::gpio, -1},
			{2U, {test_gpio, 2U, 0U}, PinCapability::digital_output, PinOwnership::connector_gpio, PinPolicy::normal, PinRoute::gpio, -1},
			{3U, {test_gpio, 3U, 0U}, PinCapability::digital_input, PinOwnership::connector_gpio, PinPolicy::normal, PinRoute::gpio, -1},
			{4U, {test_gpio, 4U, GPIO_OPEN_DRAIN}, PinCapability::digital_input | PinCapability::digital_output, PinOwnership::connector_gpio, PinPolicy::normal, PinRoute::gpio, -1},
		};

		static_assert(ARRAY_SIZE(pin_descriptions) == NUM_DIGITAL_PINS,
					  "시험 Variant의 논리 핀 개수가 일치해야 합니다.");

	}

	const PinDescription *pinDescription(std::size_t logical_pin) noexcept
	{
		if (logical_pin >= ARRAY_SIZE(pin_descriptions))
		{
			return nullptr;
		}

		return &pin_descriptions[logical_pin];
	}

	std::size_t canonicalPinId(std::size_t logical_pin) noexcept
	{
		return logical_pin < ARRAY_SIZE(pin_descriptions) ? logical_pin : SIZE_MAX;
	}

	std::size_t pinDescriptionCount() noexcept
	{
		return ARRAY_SIZE(pin_descriptions);
	}

}
