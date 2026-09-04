// SPDX-License-Identifier: MIT
#pragma once
#include <cstddef>
#include <cstdint>

namespace v04 {
constexpr std::uint32_t magic = 0x344c4948U;
constexpr std::uint32_t version = 1U;
constexpr std::size_t words = 32U;
constexpr std::size_t max_values = 20U;
inline std::uint32_t checksum(const std::uint32_t *frame) {
    std::uint32_t result = 2166136261U;
    for (std::size_t index = 0; index < words - 1; ++index)
        for (unsigned byte = 0; byte < 4; ++byte)
            result = (result ^ ((frame[index] >> (byte * 8U)) & 255U)) * 16777619U;
    return result;
}
inline bool valid(const std::uint32_t *frame, std::uint32_t role) {
    if (frame[0] != magic || frame[1] != version || frame[2] == 0 ||
        frame[3] != role || frame[4] == 0 || frame[4] > 65535U ||
        (frame[5] | frame[6] | frame[7] | frame[8]) == 0 || frame[9] != 0 ||
        frame[10] > max_values || frame[31] != checksum(frame))
        return false;
    for (std::size_t index = 11U + frame[10]; index < 31U; ++index)
        if (frame[index] != 0) return false;
    return true;
}
} // namespace v04
