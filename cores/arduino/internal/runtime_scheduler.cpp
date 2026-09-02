/**
 * @file runtime_scheduler.cpp
 * @brief Arduino loop와 Zephyr scheduler의 공존 정책을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "ArduinoRuntime.h"

#include <zephyr/kernel.h>

namespace nucode::arduino::internal
{

	void runtimePostLoop(void)
	{
#if defined(CONFIG_NUCODE_ARDUINO_LOOP_SLEEP_ONE_TICK)
		static_cast<void>(k_sleep(K_TICKS(1)));
#elif defined(CONFIG_NUCODE_ARDUINO_LOOP_YIELD)
		k_yield();
#endif
	}

}
