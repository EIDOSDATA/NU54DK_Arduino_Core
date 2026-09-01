/**
 * @file pwm_runtime_routes.h
 * @brief NU54DK PWM20·PWM21·PWM22 runtime route backend을 연결합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_VARIANTS_NU54DK_PWM_RUNTIME_ROUTES_H_
#define NUCODE_ARDUINO_VARIANTS_NU54DK_PWM_RUNTIME_ROUTES_H_

namespace nucode::arduino::internal
{
	/**
	 * @brief NU54DK production PWM route backend를 allocator에 설치합니다.
	 *
	 * @details 필요한 PWM20·PWM21·PWM22 장치와 dynamic pinctrl이
	 * 유효한 구성에서만 설치합니다. 부팅 init이 자동으로 호출하며,
	 * 전용 시험에서 backend를 재설치할 때도 직접 호출할 수 있습니다.
	 *
	 * @return backend가 설치되었으면 true, 장치나 구성이 빠졌거나
	 *         활성 출력 때문에 교체할 수 없으면 false입니다.
	 */
	[[nodiscard]] bool installNu54dkPwmRuntimeRouteBackend() noexcept;
}

#endif
