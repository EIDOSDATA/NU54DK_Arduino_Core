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

#define NUCODE_NU54DK_LED0_NODE DT_ALIAS(led0)
#define NUCODE_NU54DK_SW0_NODE DT_ALIAS(sw0)

#if !DT_NODE_HAS_STATUS_OKAY(NUCODE_NU54DK_LED0_NODE)
#error "NU54DK Arduino Variant에는 활성화된 led0 alias가 필요합니다."
#elif !DT_NODE_HAS_PROP(NUCODE_NU54DK_LED0_NODE, gpios)
#error "NU54DK led0 alias 대상에는 gpios 속성이 필요합니다."
#endif

#if !DT_NODE_HAS_STATUS_OKAY(NUCODE_NU54DK_SW0_NODE)
#error "NU54DK Arduino Variant에는 활성화된 sw0 alias가 필요합니다."
#elif !DT_NODE_HAS_PROP(NUCODE_NU54DK_SW0_NODE, gpios)
#error "NU54DK sw0 alias 대상에는 gpios 속성이 필요합니다."
#endif

#if DT_NODE_HAS_STATUS_OKAY(NUCODE_NU54DK_LED0_NODE) && \
	DT_NODE_HAS_PROP(NUCODE_NU54DK_LED0_NODE, gpios) && \
	DT_NODE_HAS_STATUS_OKAY(NUCODE_NU54DK_SW0_NODE) &&  \
	DT_NODE_HAS_PROP(NUCODE_NU54DK_SW0_NODE, gpios)

namespace nucode::arduino::internal
{
	namespace
	{

		/**
		 * @brief Arduino 논리 순서에 맞춘 NU54DK immutable 핀 설명자입니다.
		 */
		const PinDescription pin_descriptions[] = {
			{
				GPIO_DT_SPEC_GET(NUCODE_NU54DK_LED0_NODE, gpios),
				PinCapability::digital_input | PinCapability::digital_output |
					PinCapability::interrupt,
			},
			{
				GPIO_DT_SPEC_GET(NUCODE_NU54DK_SW0_NODE, gpios),
				PinCapability::digital_input | PinCapability::interrupt,
			},
		};

		static_assert(ARRAY_SIZE(pin_descriptions) == NUM_DIGITAL_PINS,
					  "공개 논리 핀 개수와 NU54DK 설명자 개수가 일치해야 합니다.");

	}

	const PinDescription *pinDescription(std::size_t logical_pin) noexcept
	{
		if (logical_pin >= ARRAY_SIZE(pin_descriptions))
		{
			return nullptr;
		}

		return &pin_descriptions[logical_pin];
	}
	std::size_t pinDescriptionCount() noexcept
	{
		return ARRAY_SIZE(pin_descriptions);
	}

}

#endif
