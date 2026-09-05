/** @file @brief 고정 table의 예약·확정·복구를 구현합니다.
 * SPDX-License-Identifier: MIT
 */
#include "internal/resource/IoResourceTable.h"
#include "internal/resource/IoResourcePolicy.h"
namespace nucode::arduino::internal::io_resource_detail
{
    /** @brief 0을 예약값으로 남기면서 다음 변경 세대를 생성합니다. */
    std::uint64_t IoResourceTable::allocateGeneration() noexcept
    {
        const std::uint64_t generation = next_generation++;
        if (next_generation == 0U)
        {
            next_generation = 1U;
        }
        return generation == 0U ? 1U : generation;
    }

    /** @brief table에서 같은 물리 자원의 slot을 찾습니다. */
    /** @brief table에서 같은 물리 자원의 const slot을 찾습니다. */
    IoResourceTable::ResourceSlot *IoResourceTable::findSlot(const IoResourceId &resource) noexcept
    {
        for (auto &slot : resource_slots)
        {
            /** @brief 두 자원 키가 같은 물리 자원을 나타내는지 확인합니다. */
            if (slot.occupied && sameResource(slot.resource, resource))
            {
                return &slot;
            }
        }
        return nullptr;
    }

    /** @brief table에서 요청과 겹치지만 exact key는 아닌 slot을 찾습니다. */
    IoResourceTable::ResourceSlot *
    IoResourceTable::findConflictingSlot(const IoResourceId &resource) noexcept
    {
        for (auto &slot : resource_slots)
        {
            /** @brief exact key 또는 겹치는 DMA range가 exclusive 충돌인지 검사합니다. */
            if (slot.occupied && resourcesConflict(slot.resource, resource))
            {
                return &slot;
            }
        }
        return nullptr;
    }

    /** @brief 이번 batch가 아직 선택하지 않은 빈 slot을 찾습니다. */
    IoResourceTable::ResourceSlot *
    IoResourceTable::findEmptySlot(ResourceSlot *const *selected,
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

    /** @brief lease가 현재 manager epoch의 요청 단계인지 확인합니다. */
    bool IoResourceTable::validLeaseEpoch(const IoResourceLease &lease) noexcept
    {
        return lease.manager_epoch == manager_epoch;
    }

    /** @brief reserve 단계의 변경·차용 entry가 모두 유효한지 검사합니다. */
    bool IoResourceTable::validateReservedEntries(const IoResourceLease &lease) noexcept
    {
        for (std::size_t index = 0U; index < lease.count; ++index)
        {
            const auto &entry = lease.entries[index];
            const ResourceSlot *const slot = findSlot(entry.resource, 0);
            const IoResourceState expected_state =
                entry.changed ? IoResourceState::reserved : IoResourceState::active;
            if ((slot == nullptr) || (slot->state != expected_state) ||
                /** @brief 두 소유자 식별자가 같은지 확인합니다. */
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
    IoResourceResult IoResourceTable::validateReleaseEntries(const IoResourceLease &lease) noexcept
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

    void IoResourceTable::fillSnapshot(const ResourceSlot *slot,
                                       IoResourceSnapshot &snapshot) noexcept
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

    const IoResourceTable::ResourceSlot *IoResourceTable::findSlot(const IoResourceId &resource,
                                                                   int) noexcept
    {
        return findSlot(resource);
    }

    IoResourceResult IoResourceTable::reserveIoResources(IoResourceOwner owner,
                                                         const IoResourceId *resources,
                                                         std::size_t count, IoAcquirePolicy policy,
                                                         IoResourceLease &lease,
                                                         IoResourceSnapshot *conflict) noexcept
    {
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
            /** @brief 자원 키가 관리자에 저장 가능한 형식인지 확인합니다. */
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

                    return IoResourceResult::conflict;
                }
                slot = findEmptySlot(selected, index);
                if (slot == nullptr)
                {

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

                return IoResourceResult::conflict;
            }
            else if (slot->reservation_token != 0U)
            {
                if (conflict != nullptr)
                {
                    fillSnapshot(slot, *conflict);
                }

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

        return IoResourceResult::success;
    }

    IoResourceResult IoResourceTable::transferIoResources(IoResourceOwner expected_owner,
                                                          IoResourceOwner new_owner,
                                                          const IoResourceId *resources,
                                                          std::size_t count, IoResourceLease &lease,
                                                          IoResourceSnapshot *conflict) noexcept
    {
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

        return IoResourceResult::success;
    }

    IoResourceResult IoResourceTable::commitIoResources(IoResourceLease &lease) noexcept
    {
        if (lease.phase != IoLeasePhase::reserved)
        {
            return IoResourceResult::wrong_phase;
        }
        /** @brief 호출자가 전달한 lease가 고정 배열 범위 안인지 확인합니다. */
        if (!validLeaseShape(lease))
        {
            return IoResourceResult::invalid_argument;
        }

        if (!validLeaseEpoch(lease) || !validateReservedEntries(lease))
        {

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

        return IoResourceResult::success;
    }

    IoResourceResult IoResourceTable::rollbackIoResources(IoResourceLease &lease) noexcept
    {
        if (lease.phase != IoLeasePhase::reserved)
        {
            return IoResourceResult::wrong_phase;
        }
        if (!validLeaseShape(lease))
        {
            return IoResourceResult::invalid_argument;
        }

        if (!validLeaseEpoch(lease) || !validateReservedEntries(lease))
        {

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

        return IoResourceResult::success;
    }

    IoResourceResult IoResourceTable::releaseIoResources(IoResourceLease &lease) noexcept
    {
        if (lease.phase != IoLeasePhase::committed)
        {
            return IoResourceResult::wrong_phase;
        }
        if (!validLeaseShape(lease))
        {
            return IoResourceResult::invalid_argument;
        }

        if (!validLeaseEpoch(lease))
        {

            return IoResourceResult::stale_lease;
        }
        const IoResourceResult validation_result = validateReleaseEntries(lease);
        if (validation_result != IoResourceResult::success)
        {

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

        return IoResourceResult::success;
    }

    IoResourceResult IoResourceTable::ioResourceSnapshot(const IoResourceId &resource,
                                                         IoResourceSnapshot &snapshot) noexcept
    {
        if (!validResource(resource))
        {
            return IoResourceResult::invalid_argument;
        }

        ResourceSlot *slot = findSlot(resource);
        if (slot == nullptr)
        {
            slot = findConflictingSlot(resource);
        }
        fillSnapshot(slot, snapshot);

        return IoResourceResult::success;
    }

#if defined(CONFIG_ZTEST)
    void IoResourceTable::resetIoResourceManagerForTest() noexcept
    {
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
    }
#endif
} // namespace nucode::arduino::internal::io_resource_detail
