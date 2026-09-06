/**
 * @file signal_hil.h
 * @brief T10 결선 확인 뒤 실행하는 analog/stream 합성 신호 명령입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>

/** @brief 합성 신호 시험의 event와 lease 만료를 처리합니다. */
void serviceSignal();
/** @brief 짧은 I2S buffer 요청을 thread 문맥에서 지체 없이 처리해야 하는지 반환합니다. */
bool signalNeedsPolling();
/** @brief 합성 신호 시험이 보드 자원을 점유하는지 반환합니다. */
bool signalClaimed();
/** @brief 고정 fixture만 사용하는 합성 신호 명령을 처리합니다. */
std::uint32_t signalCommand(std::uint32_t opcode, const std::uint32_t *args, std::uint32_t nargs,
                            std::uint32_t *out, std::uint32_t &count);
