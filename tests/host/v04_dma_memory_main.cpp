/**
 * @file v04_dma_memory_main.cpp
 * @brief EasyDMA RAM 전체 범위와 정렬 경계를 Host에서 검사합니다.
 * SPDX-License-Identifier: MIT
 */
#include "internal/dma_memory.h"

#include <cstdint>
#include <limits>

int main()
{
    using nucode::arduino::internal::dmaMemoryRangeValid;
    const auto address = [](std::uintptr_t value)
    {
        return reinterpret_cast<const void *>(value);
    };
    if (!dmaMemoryRangeValid(address(0x20000000U), 1U) ||
        !dmaMemoryRangeValid(address(0x2003FFFFU), 1U) ||
        !dmaMemoryRangeValid(address(0x20000004U), 4U, 4U))
    {
        return 1;
    }
    if (dmaMemoryRangeValid(nullptr, 1U) || dmaMemoryRangeValid(address(0x20000000U), 0U) ||
        dmaMemoryRangeValid(address(0x1FFFFFFFU), 1U) ||
        dmaMemoryRangeValid(address(0x20040000U), 1U) ||
        dmaMemoryRangeValid(address(0x2003FFFFU), 2U) ||
        dmaMemoryRangeValid(address(0x20000001U), 2U, 2U) ||
        dmaMemoryRangeValid(address(0x20000000U), std::numeric_limits<std::size_t>::max()))
    {
        return 2;
    }
    return 0;
}
