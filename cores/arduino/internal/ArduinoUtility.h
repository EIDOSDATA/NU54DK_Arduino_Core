/**
 * @file ArduinoUtility.h
 * @brief Arduino 공통 산술 utility 호환 정의입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_ARDUINO_UTILITY_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_ARDUINO_UTILITY_H_

#ifdef __cplusplus

/**
 * @brief Arduino C++ 스케치에서 사용하는 산술 절댓값 호환 함수입니다.
 *
 * 인수를 한 번만 평가하며, 뒤에 포함한 `<cmath>`와 `std::abs()`를 가리지
 * 않습니다. signed 정수형의 최솟값은 같은 형식의 양수로 표현할 수 없으므로
 * 지원 입력 범위에 포함하지 않습니다.
 *
 * @tparam Value 산술 값 형식입니다.
 * @param value 절댓값을 구할 값입니다.
 * @return value가 음수이면 부호를 반전한 값, 아니면 원래 값입니다.
 */
template <typename Value>
[[nodiscard]] constexpr Value abs(Value value) noexcept
{
	return value < static_cast<Value>(0) ? static_cast<Value>(-value) : value;
}

#else

/**
 * @brief C 호출부에서 사용하는 Arduino 절댓값 호환 매크로입니다.
 *
 * 인수를 반복 평가할 수 있으므로 C 호출부는 부수 효과가 있는 표현식을 전달하지
 * 않아야 합니다.
 */
#ifndef abs
#define abs(value) ((value) > 0 ? (value) : -(value))
#endif

#endif

#endif
