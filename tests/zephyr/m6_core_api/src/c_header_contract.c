/**
 * @file c_header_contract.c
 * @brief Arduino.h의 C 언어 공개 계약을 컴파일로 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

/**
 * @brief C 호출부에서 Common 함수와 interrupt 매핑을 사용합니다.
 *
 * @return 계약을 유지하면 1을 반환합니다.
 */
int nucode_m6_c_header_contract(void)
{
	pin_size_t pin = 0U;
	const pin_size_t interrupt_number = digitalPinToInterrupt(pin++);
	return (interrupt_number == 0U) && (pin == 1U) &&
		   (lowByte(0x1234U) == 0x34U) && (highByte(0x1234U) == 0x12U);
}
