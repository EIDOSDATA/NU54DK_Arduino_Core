/**
 * @file TimeBackend.h
 * @brief Arduino 시간 API와 Zephyr 시간원을 연결하는 비공개 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_INTERNAL_TIME_BACKEND_H_
#define NUCODE_ARDUINO_CORE_INTERNAL_TIME_BACKEND_H_

#include <stdint.h>

namespace nucode::arduino::internal
{

    /**
     * @brief Zephyr kernel uptime의 하위 32비트를 밀리초로 반환합니다.
     *
     * @return 약 49.7일마다 자연스럽게 순환하는 밀리초 값입니다.
     */
    uint32_t timeMillis(void);

    /**
     * @brief Zephyr 시간원 시작 이후 경과 시간의 하위 32비트를 마이크로초로 반환합니다.
     *
     * @return 약 71.6분마다 자연스럽게 순환하는 마이크로초 값입니다.
     */
    uint32_t timeMicros(void);

    /**
     * @brief 현재 thread를 지정한 밀리초 이상 재웁니다.
     *
     * 0을 전달하면 현재 thread가 실행 기회를 양보합니다. 커널이 block 또는 yield를
     * 허용하지 않는 문맥에서는 아무 동작도 하지 않습니다.
     *
     * @param milliseconds 대기할 밀리초입니다.
     */
    void sleepMilliseconds(uint32_t milliseconds);

    /**
     * @brief 현재 thread에서 지정한 시간만큼 busy wait를 수행합니다.
     *
     * ISR 문맥은 공개 계약에서 허용하지 않으므로 아무 동작도 하지 않습니다.
     *
     * @param microseconds 대기할 마이크로초입니다.
     */
    void busyWaitMicroseconds(uint32_t microseconds);

    /**
     * @brief 실행 가능한 같은 우선순위 thread에 CPU 실행 기회를 양보합니다.
     *
     * 커널이 yield를 허용하지 않는 문맥에서는 아무 동작도 하지 않습니다.
     */
    void yieldCurrentThread(void);

}

#endif
