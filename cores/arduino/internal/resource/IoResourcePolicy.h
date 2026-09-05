/** @file @brief 상태나 Zephyr 잠금에 의존하지 않는 물리 자원 비교 정책입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include "internal/IoResourceManager.h"
namespace nucode::arduino::internal::io_resource_detail
{
    /** @brief 두 자원 키가 같은 물리 자원을 나타내는지 확인합니다. */
    [[nodiscard]] inline constexpr bool sameResource(const IoResourceId &lhs,
                                                     const IoResourceId &rhs) noexcept
    {
        return (lhs.kind == rhs.kind) && (lhs.domain == rhs.domain) && (lhs.index == rhs.index) &&
               (lhs.span == rhs.span);
    }

    /** @brief 두 DMA RAM range가 byte 단위로 겹치는지 검사합니다. */
    [[nodiscard]] inline bool overlappingDmaMemory(const IoResourceId &lhs,
                                                   const IoResourceId &rhs) noexcept
    {
        if ((lhs.kind != IoResourceKind::dma_memory) || (rhs.kind != IoResourceKind::dma_memory))
        {
            return false;
        }
        const auto lhs_begin = reinterpret_cast<std::uintptr_t>(lhs.domain);
        const auto rhs_begin = reinterpret_cast<std::uintptr_t>(rhs.domain);
        const auto lhs_end = lhs_begin + lhs.span;
        const auto rhs_end = rhs_begin + rhs.span;
        return (lhs_begin < rhs_end) && (rhs_begin < lhs_end);
    }

    /** @brief exact key 또는 겹치는 DMA range가 exclusive 충돌인지 검사합니다. */
    [[nodiscard]] inline bool resourcesConflict(const IoResourceId &lhs,
                                                const IoResourceId &rhs) noexcept
    {
        return sameResource(lhs, rhs) || overlappingDmaMemory(lhs, rhs);
    }

    /** @brief 두 소유자 식별자가 같은지 확인합니다. */
    [[nodiscard]] inline constexpr bool sameOwner(const IoResourceOwner &lhs,
                                                  const IoResourceOwner &rhs) noexcept
    {
        return (lhs.kind == rhs.kind) && (lhs.instance == rhs.instance);
    }

    /** @brief 자원 키가 관리자에 저장 가능한 형식인지 확인합니다. */
    [[nodiscard]] inline constexpr bool validResource(const IoResourceId &resource) noexcept
    {
        if (resource.kind == IoResourceKind::invalid)
        {
            return false;
        }

        if (resource.span == 0U)
        {
            return false;
        }
        if ((resource.kind == IoResourceKind::gpio_pin) && (resource.domain == nullptr))
        {
            return false;
        }
        if (resource.kind == IoResourceKind::dma_memory)
        {
            if ((resource.domain == nullptr) || (resource.index != 0U))
            {
                return false;
            }
            const auto begin = reinterpret_cast<std::uintptr_t>(resource.domain);
            return begin <= (UINTPTR_MAX - resource.span);
        }
        return resource.span == 1U;
    }

    /** @brief 호출자가 전달한 lease가 고정 배열 범위 안인지 확인합니다. */
    [[nodiscard]] inline constexpr bool validLeaseShape(const IoResourceLease &lease) noexcept
    {
        return (lease.owner.kind != IoOwnerKind::none) && (lease.count != 0U) &&
               (lease.count <= io_resource_lease_capacity);
    }
} // namespace nucode::arduino::internal::io_resource_detail
