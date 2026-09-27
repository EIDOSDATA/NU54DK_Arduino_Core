/**
 * @file M29MultiPayload.h
 * @brief M29 3보드 통합 시험의 link 식별 payload를 생성하고 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include <cstddef>
#include <cstdint>
#include <string.h>

namespace nucode::test::m29
{

    /** @brief GATT와 CoC가 공통으로 사용하는 고정 payload codec입니다. */
    class MultiPayload final
    {
      public:
        static constexpr std::size_t nonce_text_length = 32U;
        static constexpr std::size_t nonce_binary_length = 16U;
        static constexpr std::size_t payload_length = 20U;
        static constexpr std::uint8_t gatt_kind = 0x47U;
        static constexpr std::uint8_t coc_kind = 0x4cU;

        /** @brief 128-bit lowercase hex nonce를 고정 binary buffer로 변환합니다. */
        [[nodiscard]] static bool decodeNonce(const char *text,
                                              std::uint8_t output[nonce_binary_length]) noexcept
        {
            if (text == nullptr || output == nullptr || ::strlen(text) != nonce_text_length)
            {
                return false;
            }
            for (std::size_t index = 0U; index < nonce_binary_length; ++index)
            {
                const int high = nibble(text[index * 2U]);
                const int low = nibble(text[index * 2U + 1U]);
                if (high < 0 || low < 0)
                {
                    return false;
                }
                output[index] = static_cast<std::uint8_t>((high << 4U) | low);
            }
            return true;
        }

        /** @brief link marker·종류·sequence·nonce로 검증 가능한 payload를 만듭니다. */
        static void build(std::uint8_t output[payload_length], std::uint8_t marker,
                          std::uint8_t kind, std::uint32_t sequence,
                          const std::uint8_t nonce[nonce_binary_length]) noexcept
        {
            output[0] = marker;
            output[1] = kind;
            putLe32(output + 2U, sequence);
            for (std::size_t index = 6U; index < payload_length; ++index)
            {
                output[index] = static_cast<std::uint8_t>(
                    nonce[(index + sequence) % nonce_binary_length] ^
                    static_cast<std::uint8_t>(marker + kind + index * 13U + sequence * 7U));
            }
        }

        /** @brief 수신 payload가 기대 link·종류·sequence·nonce와 byte 단위로 일치하는지 확인합니다. */
        [[nodiscard]] static bool valid(const std::uint8_t *data, std::size_t length,
                                        std::uint8_t marker, std::uint8_t kind,
                                        std::uint32_t sequence,
                                        const std::uint8_t nonce[nonce_binary_length]) noexcept
        {
            if (data == nullptr || length != payload_length || data[0] != marker ||
                data[1] != kind || getLe32(data + 2U) != sequence)
            {
                return false;
            }
            std::uint8_t expected[payload_length] = {};
            build(expected, marker, kind, sequence, nonce);
            return ::memcmp(data, expected, payload_length) == 0;
        }

      private:
        /** @brief lowercase hex 한 글자를 0..15로 변환합니다. */
        [[nodiscard]] static int nibble(char value) noexcept
        {
            if (value >= '0' && value <= '9')
            {
                return value - '0';
            }
            if (value >= 'a' && value <= 'f')
            {
                return value - 'a' + 10;
            }
            return -1;
        }

        /** @brief 32-bit sequence를 little-endian으로 기록합니다. */
        static void putLe32(std::uint8_t *output, std::uint32_t value) noexcept
        {
            output[0] = static_cast<std::uint8_t>(value & 0xffU);
            output[1] = static_cast<std::uint8_t>((value >> 8U) & 0xffU);
            output[2] = static_cast<std::uint8_t>((value >> 16U) & 0xffU);
            output[3] = static_cast<std::uint8_t>((value >> 24U) & 0xffU);
        }

        /** @brief little-endian 32-bit sequence를 읽습니다. */
        [[nodiscard]] static std::uint32_t getLe32(const std::uint8_t *input) noexcept
        {
            return static_cast<std::uint32_t>(input[0]) |
                   (static_cast<std::uint32_t>(input[1]) << 8U) |
                   (static_cast<std::uint32_t>(input[2]) << 16U) |
                   (static_cast<std::uint32_t>(input[3]) << 24U);
        }
    };

} // namespace nucode::test::m29
