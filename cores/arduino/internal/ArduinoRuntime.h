/**
 * @file ArduinoRuntime.h
 * @brief Core 내부 런타임 확장 지점의 비공개 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_ARDUINO_RUNTIME_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_ARDUINO_RUNTIME_H_

namespace nucode::arduino::internal
{

	/**
	 * @brief 한 번의 Sketch `loop()` 반환 뒤 선택한 Zephyr 공존 정책을 적용합니다.
	 *
	 * 기본 설정에서는 현재 main thread를 한 kernel tick 동안 재워 낮은 우선순위
	 * thread와 idle thread가 실행 가능한 구간을 만듭니다.
	 */
	void runtimePostLoop(void);

}

#endif
