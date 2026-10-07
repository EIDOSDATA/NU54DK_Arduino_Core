/** @file @brief 고정 NCS CGMS 제어 응답을 Host와 target에서 동일하게 판정합니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstddef>
#include <cstdint>

/** @brief NCS 3.4.0은 read interval 응답에 opcode + LE16 값을 사용합니다. */
inline bool expectedCgmsInterval(const std::uint8_t *data, std::size_t length) noexcept
{
    return data != nullptr && length == 3U && data[0] == 3U && data[1] == 1U && data[2] == 0U;
}
