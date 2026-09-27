/**
 * @file MixedGattCocPayload.h
 * @brief mixed-role 예제의 고정 길이 검증 payload를 제공합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_MIXED_GATT_COC_PAYLOAD_H_
#define NUCODE_MIXED_GATT_COC_PAYLOAD_H_

#include <cstddef>
#include <cstdint>
#include <string.h>

namespace mixed_gatt_coc
{

    /** @brief GATT와 CoC에서 함께 사용하는 검증 가능한 payload입니다. */
    class Payload final
    {
      public:
        static constexpr std::size_t length = 32U;

        /** @brief 송신 role·transport·sequence를 포함한 payload를 만듭니다. */
        static void build(std::uint8_t output[length], std::uint8_t role,
                          std::uint8_t transport, std::uint32_t sequence) noexcept
        {
            output[0] = 0x4dU;
            output[1] = 0x32U;
            output[2] = 0x39U;
            output[3] = role;
            output[4] = transport;
            output[5] = static_cast<std::uint8_t>(sequence);
            output[6] = static_cast<std::uint8_t>(sequence >> 8U);
            output[7] = static_cast<std::uint8_t>(sequence >> 16U);
            output[8] = static_cast<std::uint8_t>(sequence >> 24U);
            for (std::size_t index = 9U; index < length; ++index)
            {
                output[index] = static_cast<std::uint8_t>(role + transport + sequence +
                                                          index * 17U);
            }
        }

        /** @brief 수신 payload가 현재 송신본과 byte 단위로 같은지 반환합니다. */
        static bool matches(const void *data, std::size_t size,
                            const std::uint8_t expected[length]) noexcept
        {
            return data != nullptr && size == length &&
                   ::memcmp(data, expected, length) == 0;
        }
    };

} // namespace mixed_gatt_coc

#endif
