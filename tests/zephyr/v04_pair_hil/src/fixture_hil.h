/**
 * @file fixture_hil.h
 * @brief 결선 확인 뒤에만 실행하는 외부 통신 시험 명령입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>

/** @brief 외부 시험의 이벤트와 실행 허가 만료를 처리합니다. */
void serviceFixture();
/** @brief 외부 시험이 온보드 핀 사용을 막고 있는지 반환합니다. */
bool fixtureClaimed();
/** @brief 고정 결선 명령을 처리하며 임의 핀 주소를 받지 않습니다. */
std::uint32_t fixtureCommand(std::uint32_t opcode, const std::uint32_t *args, std::uint32_t nargs,
                             std::uint32_t *out, std::uint32_t &count);
