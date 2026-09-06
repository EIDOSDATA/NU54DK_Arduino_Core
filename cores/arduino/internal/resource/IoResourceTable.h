/** @file @brief 기존 단일 관리자의 고정 table과 transaction을 캡슐화합니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include "internal/IoResourceManager.h"
namespace nucode::arduino::internal::io_resource_detail
{
    /** @brief 호출자가 manager mutex를 보유하는 동안만 접근하는 저장소입니다. */
    class IoResourceTable final
    {
      public:
        IoResourceTable() = default;
        IoResourceTable(const IoResourceTable &) = delete;
        IoResourceTable &operator=(const IoResourceTable &) = delete;
        IoResourceResult reserveIoResources(IoResourceOwner owner, const IoResourceId *resources,
                                            std::size_t count, IoAcquirePolicy policy,
                                            IoResourceLease &lease,
                                            IoResourceSnapshot *conflict) noexcept;
        IoResourceResult transferIoResources(IoResourceOwner expected_owner,
                                             IoResourceOwner new_owner,
                                             const IoResourceId *resources, std::size_t count,
                                             IoResourceLease &lease,
                                             IoResourceSnapshot *conflict) noexcept;
        IoResourceResult commitIoResources(IoResourceLease &lease) noexcept;
        IoResourceResult rollbackIoResources(IoResourceLease &lease) noexcept;
        IoResourceResult releaseIoResources(IoResourceLease &lease) noexcept;
        /** @brief 최대 두 자원의 즉시 획득을 큰 임시 lease 없이 원자적으로 처리합니다. */
        IoResourceResult acquireIoResources(IoResourceOwner owner, const IoResourceId *resources,
                                            std::size_t count, IoAcquirePolicy policy,
                                            IoResourceToken &token,
                                            IoResourceSnapshot *conflict) noexcept;
        /** @brief compact token의 전체 세대를 먼저 검사한 뒤 자원을 반환합니다. */
        IoResourceResult releaseIoResources(IoResourceToken &token) noexcept;
        IoResourceResult ioResourceSnapshot(const IoResourceId &resource,
                                            IoResourceSnapshot &snapshot) noexcept;
#if defined(CONFIG_ZTEST)
        void resetIoResourceManagerForTest() noexcept;
#endif
      private:
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

        [[nodiscard]] std::uint64_t allocateGeneration() noexcept;
        [[nodiscard]] ResourceSlot *findSlot(const IoResourceId &resource) noexcept;
        [[nodiscard]] ResourceSlot *findConflictingSlot(const IoResourceId &resource) noexcept;
        [[nodiscard]] ResourceSlot *findEmptySlot(ResourceSlot *const *selected,
                                                  std::size_t selected_count) noexcept;
        [[nodiscard]] bool validLeaseEpoch(const IoResourceLease &lease) noexcept;
        [[nodiscard]] bool validateReservedEntries(const IoResourceLease &lease) noexcept;
        [[nodiscard]] IoResourceResult
        validateReleaseEntries(const IoResourceLease &lease) noexcept;
        void fillSnapshot(const ResourceSlot *slot, IoResourceSnapshot &snapshot) noexcept;
        [[nodiscard]] const ResourceSlot *findSlot(const IoResourceId &resource, int) noexcept;
        ResourceSlot resource_slots[CONFIG_NUCODE_ARDUINO_IO_RESOURCE_SLOTS]{};
        std::uint64_t manager_epoch{1U};
        std::uint64_t next_generation{1U};
    };
} // namespace nucode::arduino::internal::io_resource_detail
