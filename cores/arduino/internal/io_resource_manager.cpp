/**
 * @file io_resource_manager.cpp
 * @brief 고정 메모리 기반 물리 I/O 자원 소유권 관리자를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "internal/IoResourceManager.h"

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{
    namespace
    {
        /** @brief 관리자 table의 한 항목입니다. */
        struct ResourceSlot
        {
            IoResourceId resource{};
            IoResourceOwner owner{};
            IoResourceState state{IoResourceState::free};
            std::uint64_t generation{0U};
            std::uint64_t reservation_token{0U};
            bool occupied{false};
        };

        K_MUTEX_DEFINE(io_resource_mutex);
        ResourceSlot resource_slots[CONFIG_NUCODE_ARDUINO_IO_RESOURCE_SLOTS]{};
        std::uint64_t manager_epoch = 1U;
        std::uint64_t next_generation = 1U;

        /** @brief 두 자원 키가 같은 물리 자원을 나타내는지 확인합니다. */
        [[nodiscard]] constexpr bool sameResource(const IoResourceId &lhs,
                                                  const IoResourceId &rhs) noexcept
        {
            return (lhs.kind == rhs.kind) && (lhs.domain == rhs.domain) &&
                   (lhs.index == rhs.index) && (lhs.span == rhs.span);
        }

        /** @brief 두 DMA RAM range가 byte 단위로 겹치는지 검사합니다. */
        [[nodiscard]] bool overlappingDmaMemory(const IoResourceId &lhs,
                                                const IoResourceId &rhs) noexcept
        {
            if ((lhs.kind != IoResourceKind::dma_memory) ||
                (rhs.kind != IoResourceKind::dma_memory))
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
        [[nodiscard]] bool resourcesConflict(const IoResourceId &lhs,
                                             const IoResourceId &rhs) noexcept
        {
            return sameResource(lhs, rhs) || overlappingDmaMemory(lhs, rhs);
        }

        /** @brief 두 소유자 식별자가 같은지 확인합니다. */
        [[nodiscard]] constexpr bool sameOwner(const IoResourceOwner &lhs,
                                               const IoResourceOwner &rhs) noexcept
        {
            return (lhs.kind == rhs.kind) && (lhs.instance == rhs.instance);
        }

        /** @brief 자원 키가 관리자에 저장 가능한 형식인지 확인합니다. */
        [[nodiscard]] constexpr bool validResource(const IoResourceId &resource) noexcept
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

        /** @brief 0을 예약값으로 남기면서 다음 변경 세대를 생성합니다. */
        [[nodiscard]] std::uint64_t allocateGeneration() noexcept
        {
            const std::uint64_t generation = next_generation++;
            if (next_generation == 0U)
            {
                next_generation = 1U;
            }
            return generation == 0U ? 1U : generation;
        }

        /** @brief table에서 같은 물리 자원의 slot을 찾습니다. */
        [[nodiscard]] ResourceSlot *findSlot(const IoResourceId &resource) noexcept
        {
            for (auto &slot : resource_slots)
            {
                if (slot.occupied && sameResource(slot.resource, resource))
                {
                    return &slot;
                }
            }
            return nullptr;
        }

        /** @brief table에서 요청과 겹치지만 exact key는 아닌 slot을 찾습니다. */
        [[nodiscard]] ResourceSlot *findConflictingSlot(const IoResourceId &resource) noexcept
        {
            for (auto &slot : resource_slots)
            {
                if (slot.occupied && resourcesConflict(slot.resource, resource))
                {
                    return &slot;
                }
            }
            return nullptr;
        }

        /** @brief table에서 같은 물리 자원의 const slot을 찾습니다. */
        [[nodiscard]] const ResourceSlot *findSlot(const IoResourceId &resource, int) noexcept
        {
            return findSlot(resource);
        }

        /** @brief 이번 batch가 아직 선택하지 않은 빈 slot을 찾습니다. */
        [[nodiscard]] ResourceSlot *findEmptySlot(ResourceSlot *const *selected,
                                                  std::size_t selected_count) noexcept
        {
            for (auto &slot : resource_slots)
            {
                if (slot.occupied)
                {
                    continue;
                }

                bool already_selected = false;
                for (std::size_t index = 0U; index < selected_count; ++index)
                {
                    already_selected = already_selected || (selected[index] == &slot);
                }
                if (!already_selected)
                {
                    return &slot;
                }
            }
            return nullptr;
        }

        /** @brief mutation API를 thread 문맥으로 제한합니다. */
        [[nodiscard]] bool isThreadContext() noexcept
        {
            return !k_is_in_isr();
        }

        /** @brief lease가 현재 manager epoch의 요청 단계인지 확인합니다. */
        [[nodiscard]] bool validLeaseEpoch(const IoResourceLease &lease) noexcept
        {
            return lease.manager_epoch == manager_epoch;
        }

        /** @brief 호출자가 전달한 lease가 고정 배열 범위 안인지 확인합니다. */
        [[nodiscard]] constexpr bool validLeaseShape(const IoResourceLease &lease) noexcept
        {
            return (lease.owner.kind != IoOwnerKind::none) && (lease.count != 0U) &&
                   (lease.count <= io_resource_lease_capacity);
        }

        /** @brief reserve 단계의 변경·차용 entry가 모두 유효한지 검사합니다. */
        [[nodiscard]] bool validateReservedEntries(const IoResourceLease &lease) noexcept
        {
            for (std::size_t index = 0U; index < lease.count; ++index)
            {
                const auto &entry = lease.entries[index];
                const ResourceSlot *const slot = findSlot(entry.resource, 0);
                const IoResourceState expected_state =
                    entry.changed ? IoResourceState::reserved : IoResourceState::active;
                if ((slot == nullptr) || (slot->state != expected_state) ||
                    !sameOwner(slot->owner, lease.owner))
                {
                    return false;
                }
                if (entry.changed)
                {
                    if (slot->generation != entry.generation)
                    {
                        return false;
                    }
                }
                else if ((slot->reservation_token == 0U) ||
                         (slot->reservation_token != entry.generation))
                {
                    return false;
                }
            }
            return true;
        }

        /** @brief commit된 lease의 변경 entry가 반환 가능한지 검사합니다. */
        [[nodiscard]] IoResourceResult validateReleaseEntries(const IoResourceLease &lease) noexcept
        {
            for (std::size_t index = 0U; index < lease.count; ++index)
            {
                const auto &entry = lease.entries[index];
                if (!entry.changed)
                {
                    continue;
                }

                const ResourceSlot *const slot = findSlot(entry.resource, 0);
                if ((slot == nullptr) || (slot->state != IoResourceState::active) ||
                    !sameOwner(slot->owner, lease.owner) || (slot->generation != entry.generation))
                {
                    return IoResourceResult::stale_lease;
                }
                if (slot->reservation_token != 0U)
                {
                    return IoResourceResult::conflict;
                }
            }
            return IoResourceResult::success;
        }

        /** @brief 조회 결과를 slot 또는 free 상태로 채웁니다. */
        void fillSnapshot(const ResourceSlot *slot, IoResourceSnapshot &snapshot) noexcept
        {
            if (slot == nullptr)
            {
                snapshot = {};
                return;
            }
            snapshot.owner = slot->owner;
            snapshot.state = slot->state;
            snapshot.generation = slot->generation;
        }
    } // namespace

    IoResourceResult reserveIoResources(IoResourceOwner owner, const IoResourceId *resources,
                                        std::size_t count, IoAcquirePolicy policy,
                                        IoResourceLease &lease,
                                        IoResourceSnapshot *conflict) noexcept
    {
        if (!isThreadContext())
        {
            return IoResourceResult::invalid_context;
        }
        if ((resources == nullptr) || (count == 0U) || (count > io_resource_lease_capacity) ||
            (owner.kind == IoOwnerKind::none) || (policy != IoAcquirePolicy::exclusive))
        {
            return IoResourceResult::invalid_argument;
        }
        if ((lease.phase == IoLeasePhase::reserved) || (lease.phase == IoLeasePhase::committed))
        {
            return IoResourceResult::wrong_phase;
        }

        for (std::size_t index = 0U; index < count; ++index)
        {
            if (!validResource(resources[index]))
            {
                return IoResourceResult::invalid_argument;
            }
            for (std::size_t prior = 0U; prior < index; ++prior)
            {
                if (resourcesConflict(resources[index], resources[prior]))
                {
                    return IoResourceResult::invalid_argument;
                }
            }
        }

        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        ResourceSlot *selected[io_resource_lease_capacity]{};
        bool selected_new[io_resource_lease_capacity]{};

        for (std::size_t index = 0U; index < count; ++index)
        {
            ResourceSlot *slot = findSlot(resources[index]);
            if (slot == nullptr)
            {
                ResourceSlot *const conflicting = findConflictingSlot(resources[index]);
                if (conflicting != nullptr)
                {
                    if (conflict != nullptr)
                    {
                        fillSnapshot(conflicting, *conflict);
                    }
                    k_mutex_unlock(&io_resource_mutex);
                    return IoResourceResult::conflict;
                }
                slot = findEmptySlot(selected, index);
                if (slot == nullptr)
                {
                    k_mutex_unlock(&io_resource_mutex);
                    return IoResourceResult::capacity_exhausted;
                }
                selected_new[index] = true;
            }
            else if ((slot->state == IoResourceState::reserved) || !sameOwner(slot->owner, owner))
            {
                if (conflict != nullptr)
                {
                    fillSnapshot(slot, *conflict);
                }
                k_mutex_unlock(&io_resource_mutex);
                return IoResourceResult::conflict;
            }
            else if (slot->reservation_token != 0U)
            {
                if (conflict != nullptr)
                {
                    fillSnapshot(slot, *conflict);
                }
                k_mutex_unlock(&io_resource_mutex);
                return IoResourceResult::conflict;
            }
            selected[index] = slot;
        }

        lease = {};
        lease.owner = owner;
        lease.phase = IoLeasePhase::reserved;
        lease.manager_epoch = manager_epoch;
        lease.count = count;

        for (std::size_t index = 0U; index < count; ++index)
        {
            ResourceSlot &slot = *selected[index];
            auto &entry = lease.entries[index];
            entry.resource = resources[index];
            entry.previous_owner = selected_new[index] ? IoResourceOwner{} : slot.owner;
            entry.previous_state = selected_new[index] ? IoResourceState::free : slot.state;
            entry.previous_generation = selected_new[index] ? 0U : slot.generation;
            entry.changed = selected_new[index] || !sameOwner(slot.owner, owner) ||
                            (slot.state != IoResourceState::active);

            if (!entry.changed)
            {
                slot.reservation_token = allocateGeneration();
                entry.generation = slot.reservation_token;
                continue;
            }

            slot.resource = resources[index];
            slot.owner = owner;
            slot.state = IoResourceState::reserved;
            slot.generation = allocateGeneration();
            slot.occupied = true;
            entry.generation = slot.generation;
        }

        k_mutex_unlock(&io_resource_mutex);
        return IoResourceResult::success;
    }

    IoResourceResult transferIoResources(IoResourceOwner expected_owner, IoResourceOwner new_owner,
                                         const IoResourceId *resources, std::size_t count,
                                         IoResourceLease &lease,
                                         IoResourceSnapshot *conflict) noexcept
    {
        if (!isThreadContext())
        {
            return IoResourceResult::invalid_context;
        }
        if ((resources == nullptr) || (count == 0U) || (count > io_resource_lease_capacity) ||
            (expected_owner.kind == IoOwnerKind::none) || (new_owner.kind == IoOwnerKind::none) ||
            sameOwner(expected_owner, new_owner))
        {
            return IoResourceResult::invalid_argument;
        }
        if ((lease.phase == IoLeasePhase::reserved) || (lease.phase == IoLeasePhase::committed))
        {
            return IoResourceResult::wrong_phase;
        }

        for (std::size_t index = 0U; index < count; ++index)
        {
            if (!validResource(resources[index]))
            {
                return IoResourceResult::invalid_argument;
            }
            for (std::size_t prior = 0U; prior < index; ++prior)
            {
                if (resourcesConflict(resources[index], resources[prior]))
                {
                    return IoResourceResult::invalid_argument;
                }
            }
        }

        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        ResourceSlot *selected[io_resource_lease_capacity]{};
        for (std::size_t index = 0U; index < count; ++index)
        {
            ResourceSlot *const slot = findSlot(resources[index]);
            if ((slot == nullptr) || (slot->state != IoResourceState::active) ||
                !sameOwner(slot->owner, expected_owner) || (slot->reservation_token != 0U))
            {
                if (conflict != nullptr)
                {
                    fillSnapshot(slot, *conflict);
                }
                k_mutex_unlock(&io_resource_mutex);
                return IoResourceResult::conflict;
            }
            selected[index] = slot;
        }

        lease = {};
        lease.owner = new_owner;
        lease.phase = IoLeasePhase::reserved;
        lease.manager_epoch = manager_epoch;
        lease.count = count;
        for (std::size_t index = 0U; index < count; ++index)
        {
            ResourceSlot &slot = *selected[index];
            auto &entry = lease.entries[index];
            entry.resource = resources[index];
            entry.previous_owner = slot.owner;
            entry.previous_state = slot.state;
            entry.previous_generation = slot.generation;
            entry.changed = true;
            slot.owner = new_owner;
            slot.state = IoResourceState::reserved;
            slot.generation = allocateGeneration();
            entry.generation = slot.generation;
        }
        k_mutex_unlock(&io_resource_mutex);
        return IoResourceResult::success;
    }

    IoResourceResult commitIoResources(IoResourceLease &lease) noexcept
    {
        if (!isThreadContext())
        {
            return IoResourceResult::invalid_context;
        }
        if (lease.phase != IoLeasePhase::reserved)
        {
            return IoResourceResult::wrong_phase;
        }
        if (!validLeaseShape(lease))
        {
            return IoResourceResult::invalid_argument;
        }

        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        if (!validLeaseEpoch(lease) || !validateReservedEntries(lease))
        {
            k_mutex_unlock(&io_resource_mutex);
            return IoResourceResult::stale_lease;
        }

        for (std::size_t index = 0U; index < lease.count; ++index)
        {
            auto &entry = lease.entries[index];
            if (!entry.changed)
            {
                ResourceSlot *const slot = findSlot(entry.resource);
                slot->reservation_token = 0U;
                continue;
            }
            ResourceSlot *const slot = findSlot(entry.resource);
            slot->state = IoResourceState::active;
            slot->generation = allocateGeneration();
            entry.generation = slot->generation;
        }
        lease.phase = IoLeasePhase::committed;
        k_mutex_unlock(&io_resource_mutex);
        return IoResourceResult::success;
    }

    IoResourceResult rollbackIoResources(IoResourceLease &lease) noexcept
    {
        if (!isThreadContext())
        {
            return IoResourceResult::invalid_context;
        }
        if (lease.phase != IoLeasePhase::reserved)
        {
            return IoResourceResult::wrong_phase;
        }
        if (!validLeaseShape(lease))
        {
            return IoResourceResult::invalid_argument;
        }

        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        if (!validLeaseEpoch(lease) || !validateReservedEntries(lease))
        {
            k_mutex_unlock(&io_resource_mutex);
            return IoResourceResult::stale_lease;
        }

        for (std::size_t index = 0U; index < lease.count; ++index)
        {
            const auto &entry = lease.entries[index];
            if (!entry.changed)
            {
                ResourceSlot *const slot = findSlot(entry.resource);
                slot->reservation_token = 0U;
                continue;
            }
            ResourceSlot *const slot = findSlot(entry.resource);
            if (entry.previous_state == IoResourceState::free)
            {
                *slot = {};
            }
            else
            {
                slot->owner = entry.previous_owner;
                slot->state = entry.previous_state;
                slot->generation = entry.previous_generation != 0U ? entry.previous_generation
                                                                   : allocateGeneration();
            }
        }
        lease.phase = IoLeasePhase::rolled_back;
        k_mutex_unlock(&io_resource_mutex);
        return IoResourceResult::success;
    }

    IoResourceResult releaseIoResources(IoResourceLease &lease) noexcept
    {
        if (!isThreadContext())
        {
            return IoResourceResult::invalid_context;
        }
        if (lease.phase != IoLeasePhase::committed)
        {
            return IoResourceResult::wrong_phase;
        }
        if (!validLeaseShape(lease))
        {
            return IoResourceResult::invalid_argument;
        }

        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        if (!validLeaseEpoch(lease))
        {
            k_mutex_unlock(&io_resource_mutex);
            return IoResourceResult::stale_lease;
        }
        const IoResourceResult validation_result = validateReleaseEntries(lease);
        if (validation_result != IoResourceResult::success)
        {
            k_mutex_unlock(&io_resource_mutex);
            return validation_result;
        }

        for (std::size_t index = 0U; index < lease.count; ++index)
        {
            const auto &entry = lease.entries[index];
            if (entry.changed)
            {
                ResourceSlot *const slot = findSlot(entry.resource);
                *slot = {};
            }
        }
        lease.phase = IoLeasePhase::released;
        k_mutex_unlock(&io_resource_mutex);
        return IoResourceResult::success;
    }

    IoResourceResult acquireIoResources(IoResourceOwner owner, const IoResourceId *resources,
                                        std::size_t count, IoAcquirePolicy policy,
                                        IoResourceToken &token,
                                        IoResourceSnapshot *conflict) noexcept
    {
        if (count == 0U || count > io_resource_token_capacity || token.active)
        {
            return IoResourceResult::invalid_argument;
        }
        IoResourceLease lease{};
        IoResourceResult result =
            reserveIoResources(owner, resources, count, policy, lease, conflict);
        if (result != IoResourceResult::success)
        {
            return result;
        }
        result = commitIoResources(lease);
        if (result != IoResourceResult::success)
        {
            (void)rollbackIoResources(lease);
            return result;
        }
        token = {};
        token.owner = lease.owner;
        token.manager_epoch = lease.manager_epoch;
        token.count = lease.count;
        for (std::size_t index = 0U; index < lease.count; ++index)
        {
            token.entries[index] = {lease.entries[index].resource, lease.entries[index].generation,
                                    lease.entries[index].changed};
        }
        token.active = true;
        return IoResourceResult::success;
    }

    IoResourceResult releaseIoResources(IoResourceToken &token) noexcept
    {
        if (!token.active || token.count == 0U || token.count > io_resource_token_capacity)
        {
            return IoResourceResult::wrong_phase;
        }
        IoResourceLease lease{};
        lease.owner = token.owner;
        lease.phase = IoLeasePhase::committed;
        lease.manager_epoch = token.manager_epoch;
        lease.count = token.count;
        for (std::size_t index = 0U; index < token.count; ++index)
        {
            lease.entries[index].resource = token.entries[index].resource;
            lease.entries[index].generation = token.entries[index].generation;
            lease.entries[index].changed = token.entries[index].changed;
        }
        const IoResourceResult result = releaseIoResources(lease);
        if (result == IoResourceResult::success)
        {
            token = {};
        }
        return result;
    }

    IoResourceResult ioResourceSnapshot(const IoResourceId &resource,
                                        IoResourceSnapshot &snapshot) noexcept
    {
        if (!isThreadContext())
        {
            return IoResourceResult::invalid_context;
        }
        if (!validResource(resource))
        {
            return IoResourceResult::invalid_argument;
        }

        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        ResourceSlot *slot = findSlot(resource);
        if (slot == nullptr)
        {
            slot = findConflictingSlot(resource);
        }
        fillSnapshot(slot, snapshot);
        k_mutex_unlock(&io_resource_mutex);
        return IoResourceResult::success;
    }

#if defined(CONFIG_ZTEST)
    void resetIoResourceManagerForTest() noexcept
    {
        if (!isThreadContext())
        {
            return;
        }
        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        for (auto &slot : resource_slots)
        {
            slot = {};
        }
        ++manager_epoch;
        if (manager_epoch == 0U)
        {
            manager_epoch = 1U;
        }
        next_generation = 1U;
        k_mutex_unlock(&io_resource_mutex);
    }
#endif

} // namespace nucode::arduino::internal
