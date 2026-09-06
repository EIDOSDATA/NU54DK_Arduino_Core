/** @file @brief 기존 단일 I/O 관리자의 Zephyr 동기화와 token 진입점을 제공합니다.
 * SPDX-License-Identifier: MIT
 */
#include "internal/IoResourceManager.h"
#include "internal/resource/IoResourceTable.h"
#include <zephyr/kernel.h>
namespace nucode::arduino::internal
{
    namespace
    {
        K_MUTEX_DEFINE(io_resource_mutex);
        io_resource_detail::IoResourceTable table;
    } // namespace
    IoResourceResult reserveIoResources(IoResourceOwner owner, const IoResourceId *resources,
                                        std::size_t count, IoAcquirePolicy policy,
                                        IoResourceLease &lease,
                                        IoResourceSnapshot *conflict) noexcept
    {
        if (k_is_in_isr())
        {
            return IoResourceResult::invalid_context;
        }
        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        const auto result =
            table.reserveIoResources(owner, resources, count, policy, lease, conflict);
        k_mutex_unlock(&io_resource_mutex);
        return result;
    }

    IoResourceResult transferIoResources(IoResourceOwner expected_owner, IoResourceOwner new_owner,
                                         const IoResourceId *resources, std::size_t count,
                                         IoResourceLease &lease,
                                         IoResourceSnapshot *conflict) noexcept
    {
        if (k_is_in_isr())
        {
            return IoResourceResult::invalid_context;
        }
        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        const auto result =
            table.transferIoResources(expected_owner, new_owner, resources, count, lease, conflict);
        k_mutex_unlock(&io_resource_mutex);
        return result;
    }

    IoResourceResult commitIoResources(IoResourceLease &lease) noexcept
    {
        if (k_is_in_isr())
        {
            return IoResourceResult::invalid_context;
        }
        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        const auto result = table.commitIoResources(lease);
        k_mutex_unlock(&io_resource_mutex);
        return result;
    }

    IoResourceResult rollbackIoResources(IoResourceLease &lease) noexcept
    {
        if (k_is_in_isr())
        {
            return IoResourceResult::invalid_context;
        }
        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        const auto result = table.rollbackIoResources(lease);
        k_mutex_unlock(&io_resource_mutex);
        return result;
    }

    IoResourceResult releaseIoResources(IoResourceLease &lease) noexcept
    {
        if (k_is_in_isr())
        {
            return IoResourceResult::invalid_context;
        }
        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        const auto result = table.releaseIoResources(lease);
        k_mutex_unlock(&io_resource_mutex);
        return result;
    }

    IoResourceResult ioResourceSnapshot(const IoResourceId &resource,
                                        IoResourceSnapshot &snapshot) noexcept
    {
        if (k_is_in_isr())
        {
            return IoResourceResult::invalid_context;
        }
        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        const auto result = table.ioResourceSnapshot(resource, snapshot);
        k_mutex_unlock(&io_resource_mutex);
        return result;
    }

#if defined(CONFIG_ZTEST)
    void resetIoResourceManagerForTest() noexcept
    {
        if (k_is_in_isr())
        {
            return;
        }
        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        table.resetIoResourceManagerForTest();
        k_mutex_unlock(&io_resource_mutex);
    }
#endif

    IoResourceResult acquireIoResources(IoResourceOwner owner, const IoResourceId *resources,
                                        std::size_t count, IoAcquirePolicy policy,
                                        IoResourceToken &token,
                                        IoResourceSnapshot *conflict) noexcept
    {
        if (count == 0U || count > io_resource_token_capacity || token.active)
        {
            return IoResourceResult::invalid_argument;
        }
        if (k_is_in_isr())
        {
            return IoResourceResult::invalid_context;
        }
        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        const auto result =
            table.acquireIoResources(owner, resources, count, policy, token, conflict);
        k_mutex_unlock(&io_resource_mutex);
        return result;
    }

    IoResourceResult releaseIoResources(IoResourceToken &token) noexcept
    {
        if (!token.active || token.count == 0U || token.count > io_resource_token_capacity)
        {
            return IoResourceResult::wrong_phase;
        }
        if (k_is_in_isr())
        {
            return IoResourceResult::invalid_context;
        }
        k_mutex_lock(&io_resource_mutex, K_FOREVER);
        const auto result = table.releaseIoResources(token);
        k_mutex_unlock(&io_resource_mutex);
        return result;
    }

} // namespace nucode::arduino::internal
