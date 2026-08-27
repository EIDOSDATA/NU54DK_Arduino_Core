/**
 * @file tab_math.ino
 * @brief Arduino CLI가 주 스케치 뒤에 결합할 보조 INO 탭입니다.
 *
 * SPDX-License-Identifier: MIT
 */

/** @brief 보조 탭 내부에서 사용하는 고정 기준값을 반환합니다. */
unsigned int tabBaseValue(void)
{
	return 22U;
}

/** @brief 주 탭에서 전달한 값과 보조 탭 기준값을 결합합니다. */
unsigned int combineTabValues(unsigned int value)
{
	return value + tabBaseValue();
}
