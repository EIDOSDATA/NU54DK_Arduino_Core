/**
 * @file common_qdec_hil.h
 * @brief 공통 P1.14/P1.10 QDEC 추가 기능 시험입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>
/** @brief 다른 외부 시험과 배타적인 소유 상태입니다. */
bool commonQdecClaimed();
/** @brief 유한 quadrature 생성·누산기 배출·lease 만료를 처리합니다. */
void serviceCommonQdec();
/** @brief 짧은 poll이 필요한 상태인지 반환합니다. */
bool commonQdecNeedsPolling();
/** @brief 임의 pin 없이 520 명령만 처리합니다. */
std::uint32_t commonQdecCommand(std::uint32_t opcode, const std::uint32_t *args,
                                std::uint32_t nargs, std::uint32_t *out, std::uint32_t &count);
