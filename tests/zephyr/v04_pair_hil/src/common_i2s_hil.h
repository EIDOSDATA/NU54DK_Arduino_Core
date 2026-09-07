/**
 * @file common_i2s_hil.h
 * @brief 공통 4선의 연속·단방향 I2S 시험입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>
/** @brief 다른 외부 시험과의 배타 상태입니다. */
bool commonI2sClaimed();
/** @brief DMA 반환·공급·검증·lease 만료를 처리합니다. */
void serviceCommonI2s();
/** @brief 짧은 poll이 필요한지 반환합니다. */
bool commonI2sNeedsPolling();
/** @brief 고정 530 결선 명령만 허용합니다. */
std::uint32_t commonI2sCommand(std::uint32_t opcode, const std::uint32_t *args, std::uint32_t nargs,
                               std::uint32_t *out, std::uint32_t &count);
