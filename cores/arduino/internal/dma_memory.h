/**
 * @file dma_memory.h
 * @brief nRF54L15 application EasyDMA가 접근할 수 있는 RAM 전체 범위를 검사합니다.
 * SPDX-License-Identifier: MIT
 */
#ifndef NUCODE_INTERNAL_DMA_MEMORY_H_
#define NUCODE_INTERNAL_DMA_MEMORY_H_

#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{
    inline constexpr std::uintptr_t nrf54l15_application_ram_begin = 0x20000000U;
    inline constexpr std::uintptr_t nrf54l15_application_ram_end = 0x20040000U;

    /**
     * @brief 시작 주소뿐 아니라 마지막 바이트까지 application RAM 안에 있는지 검사합니다.
     * @param address DMA buffer의 첫 바이트입니다.
     * @param bytes DMA가 접근할 전체 바이트 수입니다.
     * @param alignment 주변장치가 요구하는 정렬이며 0은 허용하지 않습니다.
     */
    [[nodiscard]] inline bool dmaMemoryRangeValid(const void *address, std::size_t bytes,
                                                  std::size_t alignment = 1U) noexcept
    {
        if (address == nullptr || bytes == 0U || alignment == 0U)
        {
            return false;
        }
        const auto start = reinterpret_cast<std::uintptr_t>(address);
        if (start < nrf54l15_application_ram_begin || start >= nrf54l15_application_ram_end ||
            start % alignment != 0U || bytes > nrf54l15_application_ram_end - start)
        {
            return false;
        }
        return true;
    }
} // namespace nucode::arduino::internal

#endif
