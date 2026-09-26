/**
 * @file BLEPeriodicSyncLease.h
 * @brief Bluetooth periodic sync 고정 slot의 image-wide 소유권 경계입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#pragma once

#include <zephyr/sys/atomic.h>

namespace nucode::arduino::internal
{

    inline atomic_ptr_t ble_periodic_sync_owner = nullptr;

    /** @brief owner가 periodic sync 고정 slot의 수명 소유권을 획득합니다. */
    inline bool claimBLEPeriodicSyncLease(const void *owner) noexcept
    {
        if (owner == nullptr)
        {
            return false;
        }
        void *const mutable_owner = const_cast<void *>(owner);
        return atomic_ptr_cas(&ble_periodic_sync_owner, nullptr, mutable_owner);
    }

    /** @brief owner가 현재 periodic sync 고정 slot을 소유하는지 확인합니다. */
    inline bool ownsBLEPeriodicSyncLease(const void *owner) noexcept
    {
        return (owner != nullptr) &&
               (atomic_ptr_get(&ble_periodic_sync_owner) == const_cast<void *>(owner));
    }

    /** @brief 같은 owner만 periodic sync 고정 slot의 수명 소유권을 해제합니다. */
    inline void releaseBLEPeriodicSyncLease(const void *owner) noexcept
    {
        if (owner != nullptr)
        {
            (void)atomic_ptr_cas(&ble_periodic_sync_owner, const_cast<void *>(owner), nullptr);
        }
    }

} // namespace nucode::arduino::internal
