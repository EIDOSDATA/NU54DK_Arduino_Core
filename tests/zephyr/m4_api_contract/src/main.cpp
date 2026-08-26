/**
 * @file main.cpp
 * @brief ArduinoCore-API 1.5.2의 NU54DK target compile 계약을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <api/ArduinoAPI.h>
#include <api/HardwareSerial.h>

namespace
{

	template <typename Left, typename Right>
	inline constexpr bool same_type = false;

	template <typename Value>
	inline constexpr bool same_type<Value, Value> = true;

}

static_assert(ARDUINO_API_VERSION == 10502,
		      "고정한 ArduinoCore-API 버전이 변경되었습니다.");
static_assert(same_type<pin_size_t, uint8_t>,
		      "M4의 기본 Arduino 논리 핀 ABI는 8-bit여야 합니다.");
static_assert(__is_abstract(arduino::HardwareSerial),
		      "HardwareSerial은 M6 backend가 구현할 추상 계약이어야 합니다.");
static_assert(__is_base_of(arduino::Stream, arduino::HardwareSerial),
		      "HardwareSerial은 Arduino Stream 계약을 따라야 합니다.");
static_assert(same_type<decltype(arduino::String{}), arduino::String>,
		      "Arduino String 공개 생성자 계약을 찾을 수 없습니다.");

using AttachInterruptSignature =
	void (*)(pin_size_t, voidFuncPtr, PinStatus);

static_assert(
	same_type<decltype(static_cast<AttachInterruptSignature>(&attachInterrupt)),
		  AttachInterruptSignature>,
	"기본 attachInterrupt 함수 계약이 변경되었습니다.");
