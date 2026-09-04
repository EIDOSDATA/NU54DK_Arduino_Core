// SPDX-License-Identifier: MIT
#ifndef NUCODE_INTERNAL_DMA_COUNT_H_
#define NUCODE_INTERNAL_DMA_COUNT_H_
#include <cstddef>
namespace nucode::arduino::internal
{
    /**
     * @brief 주변장치별 MAXCNT 단위에 맞춰 overflow 없이 길이를 검증합니다.
     *
     * MAXCNT는 주변장치에 따라 byte, sample 또는 word를 세므로 악의적인 size_t에서도 곱셈
     * overflow가 생기지 않도록 먼저 나눠 비교합니다.
     */
    [[nodiscard]] constexpr bool dmaCountFits(std::size_t count, std::size_t register_max,
                                              std::size_t register_units_per_element) noexcept
    {
        return count != 0 && register_units_per_element != 0 &&
               count <= register_max / register_units_per_element;
    }
} // namespace nucode::arduino::internal
#endif
