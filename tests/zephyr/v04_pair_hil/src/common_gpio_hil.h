/**
 * @file common_gpio_hil.h
 * @brief 공통 결선의 Arduino GPIO와 GPIOTE 기능 명령을 선언합니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>

/** @brief 다른 fixture와 배타적으로 사용하는 실행 상태입니다. */
bool commonGpioClaimed();
/** @brief 유한 에지 생성·관측과 10초 lease 만료를 처리합니다. */
void serviceCommonGpio();
/** @brief 에지를 놓치지 않도록 짧은 main poll이 필요한지 반환합니다. */
bool commonGpioNeedsPolling();
/** @brief 고정 net만 허용하는 GPIO/GPIOTE 명령입니다. */
std::uint32_t commonGpioCommand(std::uint32_t opcode, const std::uint32_t *args,
                                std::uint32_t nargs, std::uint32_t *out, std::uint32_t &count);
