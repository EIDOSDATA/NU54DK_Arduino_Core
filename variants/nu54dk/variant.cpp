/**
 * @file variant.cpp
 * @brief Core-owned Devicetree에서 NU54DK canonical 핀 설명자를 생성합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <variant.h>

#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/util.h>

#include <nucode/nu54dk-arduino-pin-metadata.h>

#include <cstddef>
#include <cstdint>

#include "internal/pin_description.h"

static_assert(DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(nucode_arduino_pin_map)),
			  "NU54DK Arduino Core-owned 31핀 DTS map이 필요합니다.");

#define NUCODE_NU54DK_PHYSICAL_PIN(logical_pin, node_label)                      \
	static_assert(DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(node_label)),             \
				  "NU54DK Arduino pin map child가 활성화되어야 합니다.");        \
	static_assert(DT_NODE_HAS_PROP(DT_NODELABEL(node_label), gpios),             \
				  "NU54DK Arduino pin map child에는 gpios가 필요합니다.");       \
	static_assert(!((DT_PROP(DT_NODELABEL(node_label), nucode_route_mask) &      \
					 NUCODE_PIN_ROUTE_PORT2) != 0 &&                             \
					(DT_PROP(DT_NODELABEL(node_label), nucode_capability_mask) & \
					 NUCODE_PIN_CAP_INTERRUPT) != 0),                            \
				  "GPIO2에는 GPIOTE interrupt capability를 부여할 수 없습니다.");
#include "digital_pins.inc"
#undef NUCODE_NU54DK_PHYSICAL_PIN

namespace nucode::arduino::internal
{
	namespace
	{
		/** @brief canonical ID와 실제 설명자를 결합합니다. */
		struct LogicalPinDescription
		{
			std::size_t logical_pin;
			PinDescription description;
		};

		/** @brief 조건부 조립 핀의 digital capability를 profile 승인 전 제거합니다. */
		[[nodiscard]] constexpr PinCapability enabledCapabilities(
			std::uint32_t raw_capabilities, PinPolicy policy) noexcept
		{
			if ((policy == PinPolicy::conditional_lfxo) &&
				(NUCODE_NU54DK_HAS_LFXO_GPIO_PINS == 0))
			{
				return PinCapability::none;
			}
			if ((policy == PinPolicy::conditional_dap_uart) &&
				(NUCODE_NU54DK_HAS_DAP_UART_GPIO_PINS == 0))
			{
				return PinCapability::none;
			}
			return static_cast<PinCapability>(raw_capabilities);
		}

		static_assert(static_cast<std::uint8_t>(PinPolicy::normal) ==
					  NUCODE_PIN_POLICY_NORMAL);
		static_assert(static_cast<std::uint8_t>(PinPolicy::system_reserved) ==
					  NUCODE_PIN_POLICY_SYSTEM_RESERVED);
		static_assert(static_cast<std::uint8_t>(PinOwnership::conditional) ==
					  NUCODE_PIN_OWNER_CONDITIONAL);
		static_assert(static_cast<std::uint32_t>(PinRoute::port2) ==
					  NUCODE_PIN_ROUTE_PORT2);

		const LogicalPinDescription pin_descriptions[] = {
#define NUCODE_NU54DK_PHYSICAL_PIN(logical_pin, node_label)                           \
	{static_cast<std::size_t>(logical_pin),                                           \
	 {static_cast<std::size_t>(logical_pin),                                          \
	  GPIO_DT_SPEC_GET(DT_NODELABEL(node_label), gpios),                              \
	  enabledCapabilities(                                                            \
		  DT_PROP(DT_NODELABEL(node_label), nucode_capability_mask),                  \
		  static_cast<PinPolicy>(DT_PROP(DT_NODELABEL(node_label), nucode_policy))),  \
	  static_cast<PinOwnership>(DT_PROP(DT_NODELABEL(node_label), nucode_ownership)), \
	  static_cast<PinPolicy>(DT_PROP(DT_NODELABEL(node_label), nucode_policy)),       \
	  static_cast<PinRoute>(DT_PROP(DT_NODELABEL(node_label), nucode_route_mask)),    \
	  static_cast<std::int8_t>(DT_PROP_OR(DT_NODELABEL(node_label),                   \
										  nucode_analog_channel, -1))}},
#include "digital_pins.inc"
#undef NUCODE_NU54DK_PHYSICAL_PIN
		};

		static_assert(ARRAY_SIZE(pin_descriptions) == NUM_PHYSICAL_PINS,
					  "NU54DK 실제 pad 수와 canonical descriptor 수가 다릅니다.");
		static_assert(PIN_LED1 < NUM_PIN_ROLES && PIN_P2_10 < NUM_PIN_ROLES,
					  "공개 logical ID가 NUM_PIN_ROLES 범위 안에 있어야 합니다.");
	}

	std::size_t canonicalPinId(std::size_t logical_pin) noexcept
	{
		if (logical_pin >= NUM_PIN_ROLES)
		{
			return static_cast<std::size_t>(-1);
		}
		return logical_pin == static_cast<std::size_t>(PIN_LED1)
				   ? static_cast<std::size_t>(PIN_PWM0)
				   : logical_pin;
	}

	const PinDescription *pinDescription(std::size_t logical_pin) noexcept
	{
		const std::size_t canonical = canonicalPinId(logical_pin);
		if (canonical == static_cast<std::size_t>(-1))
		{
			return nullptr;
		}
		for (const auto &entry : pin_descriptions)
		{
			if (entry.logical_pin == canonical)
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
