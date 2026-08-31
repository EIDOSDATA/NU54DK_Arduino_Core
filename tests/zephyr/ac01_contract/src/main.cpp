/**
 * @file main.cpp
 * @brief AC-01 공개 API와 negative 의미를 production DTS에서 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/devicetree.h>
#include <zephyr/ztest.h>

#include "internal/pin_description.h"

namespace
{
	using nucode::arduino::internal::GpioError;
	using nucode::arduino::internal::hasPinCapability;
	using nucode::arduino::internal::lastGpioError;
	using nucode::arduino::internal::PinCapability;
	using nucode::arduino::internal::PinOwnership;
	using nucode::arduino::internal::pinDescription;

	static_assert(NUCODE_NU54DK_HAS_CONNECTOR_GPIO == 1,
				  "AC-01 target에는 connector alias 두 개가 필요합니다.");
	static_assert(PIN_GPIO0 == 10U && PIN_GPIO1 == 11U,
				  "기존 v0.2.0 논리 ID 뒤에 connector GPIO를 추가해야 합니다.");
	static_assert(NUM_DIGITAL_PINS == 12U && NUM_DIGITAL_CAPABLE_PINS == 9U &&
				  NUM_PIN_ROLES == 12U,
				  "AC-01 profile의 공개 pin 범위와 descriptor 수가 다릅니다.");
	static_assert(D10 == PIN_GPIO0 && D11 == PIN_GPIO1,
				  "connector GPIO의 Arduino digital 별칭이 다릅니다.");
	static_assert(digitalPinToInterrupt(PIN_GPIO0) == NOT_AN_INTERRUPT &&
				  digitalPinToInterrupt(PIN_GPIO1) == NOT_AN_INTERRUPT &&
				  digitalPinToInterrupt(PIN_BUTTON0) == PIN_BUTTON0,
				  "P2 connector는 IRQ에서 제외하고 GPIOTE button은 유지해야 합니다.");
}

ZTEST(ac01_contract, test_connector_descriptors_are_alias_owned_and_open_drain_capable)
{
	const auto *const gpio0 = pinDescription(PIN_GPIO0);
	const auto *const gpio1 = pinDescription(PIN_GPIO1);
	zassert_not_null(gpio0, "PIN_GPIO0 descriptor가 없습니다.");
	zassert_not_null(gpio1, "PIN_GPIO1 descriptor가 없습니다.");
	zassert_equal(gpio0->gpio.port, DEVICE_DT_GET(DT_NODELABEL(gpio2)),
				  "PIN_GPIO0 controller가 profile alias와 다릅니다.");
	zassert_equal(gpio0->gpio.pin, 5U, "PIN_GPIO0 physical pin이 다릅니다.");
	zassert_equal(gpio1->gpio.pin, 6U, "PIN_GPIO1 physical pin이 다릅니다.");
	zassert_equal(gpio0->ownership, PinOwnership::connector_gpio,
				  "PIN_GPIO0 ownership이 connector_gpio가 아닙니다.");
	zassert_true(hasPinCapability(gpio0->capabilities, PinCapability::digital_input),
				 "connector input capability가 없습니다.");
	zassert_true(hasPinCapability(gpio0->capabilities, PinCapability::digital_output),
				 "connector output capability가 없습니다.");
	zassert_false(hasPinCapability(gpio0->capabilities, PinCapability::interrupt),
				  "GPIOTE가 없는 P2 connector에 interrupt capability를 노출했습니다.");
	zassert_true(hasPinCapability(gpio0->capabilities, PinCapability::open_drain),
				 "connector open-drain capability가 없습니다.");
}

ZTEST(ac01_contract, test_open_drain_is_limited_to_connector_gpio)
{
	pinMode(PIN_GPIO0, OUTPUT_OPENDRAIN);
	zassert_equal(lastGpioError(), GpioError::none,
				  "connector open-drain 구성이 실패했습니다.");

	pinMode(LED_BUILTIN, OUTPUT_OPENDRAIN);
	zassert_equal(lastGpioError(), GpioError::unsupported_capability,
				  "board LED의 open-drain 요청을 거부하지 않았습니다.");
}

ZTEST(ac01_contract, test_pulse_and_shift_negative_contract)
{
	pinMode(PIN_GPIO0, OUTPUT);
	zassert_equal(pulseIn(PIN_GPIO0, HIGH, 100U), 0UL,
				  "output pin pulse 측정을 허용했습니다.");
	zassert_equal(lastGpioError(), GpioError::wrong_mode,
				  "output pin pulse 오류가 wrong_mode가 아닙니다.");

	pinMode(PIN_GPIO1, INPUT_PULLUP);
	zassert_equal(pulseIn(PIN_GPIO1, 2U, 100U), 0UL,
				  "잘못된 pulse state를 허용했습니다.");
	zassert_equal(lastGpioError(), GpioError::invalid_value,
				  "잘못된 pulse state 진단이 다릅니다.");

	shiftOut(PIN_GPIO0, PIN_GPIO0, MSBFIRST, 0x5aU);
	zassert_equal(lastGpioError(), GpioError::ownership_conflict,
				  "data/clock 중복 pin을 거부하지 않았습니다.");
}

ZTEST(ac01_contract, test_interrupt_mask_is_nested_and_unbalanced_restore_is_rejected)
{
	noInterrupts();
	zassert_equal(lastGpioError(), GpioError::none, "첫 callback mask가 실패했습니다.");
	noInterrupts();
	zassert_equal(lastGpioError(), GpioError::none, "중첩 callback mask가 실패했습니다.");
	interrupts();
	zassert_equal(lastGpioError(), GpioError::none, "첫 중첩 복원이 실패했습니다.");
	interrupts();
	zassert_equal(lastGpioError(), GpioError::none, "마지막 중첩 복원이 실패했습니다.");
	interrupts();
	zassert_equal(lastGpioError(), GpioError::interrupt_restore_without_disable,
				  "짝이 없는 interrupts()를 안전하게 거부하지 않았습니다.");
}

ZTEST_SUITE(ac01_contract, nullptr, nullptr, nullptr, nullptr, nullptr);
