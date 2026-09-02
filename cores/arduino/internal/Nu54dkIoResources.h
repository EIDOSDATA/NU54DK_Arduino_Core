/**
 * @file Nu54dkIoResources.h
 * @brief NU54DK 고정 pinctrl 자원의 소유권 registry 계약을 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_NU54DK_IO_RESOURCES_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_NU54DK_IO_RESOURCES_H_

#include "internal/IoResourceManager.h"

namespace nucode::arduino::internal
{
	/**
	 * @brief 활성 NU54DK Devicetree가 부팅 시 적용하는 고정 자원을 등록합니다.
	 *
	 * UART20, I2C22, PWM20과 활성화된 SPI00의 pinctrl pad 및 peripheral
	 * block을 active owner로 기록합니다. 실제 driver나 pinctrl 상태는 바꾸지
	 * 않습니다.
	 *
	 * @return 모든 고정 자원을 등록하면 success, 충돌하면 해당 오류입니다.
	 */
	[[nodiscard]] IoResourceResult initializeNu54dkIoResources() noexcept;

	/** @brief 부팅 registry가 마지막으로 반환한 결과입니다. */
	[[nodiscard]] IoResourceResult nu54dkIoResourceRegistryResult() noexcept;
}

#endif
