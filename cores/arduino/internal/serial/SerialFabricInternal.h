/** @file @brief Serial Fabric의 고정 context와 비공개 registry 경계입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include "internal/IoResourceManager.h"
#include "internal/SerialFabricBackend.h"
#include <zephyr/sys/atomic.h>
#include <cstddef>
#include <cstdint>
namespace nucode::arduino::internal::serial
{
    using internal::IoAcquirePolicy;
    using internal::IoOwnerKind;
    using internal::IoResourceId;
    using internal::IoResourceLease;
    using internal::IoResourceResult;
    using internal::SerialFabricDriverAdapter;
    using internal::ValidatedSerialRoute;

    inline constexpr std::size_t handle_count = 23U;
    inline constexpr std::size_t block_count = 5U;

    struct SavedPin
    {
        std::uint32_t psel{0U};
        std::uint32_t configuration{0U};
        std::uint32_t output{0U};
    };

    struct HandleContext
    {
        ValidatedSerialRoute route{};
        IoResourceId resources[internal::io_resource_lease_capacity]{};
        std::size_t resource_count{0U};
        IoResourceLease lease{};
        const SerialFabricDriverAdapter *adapter{nullptr};
        SerialFabricState state{SerialFabricState::inactive};
        SerialFabricResult last_result{SerialFabricResult::success};
        int last_driver_error{0};
        SavedPin saved_pins[internal::serial_fabric_pin_capacity]{};
        std::size_t saved_pin_count{0U};
        bool constant_latency_owned{false};
    };

    struct BlockContext
    {
        bool faulted{false};
        bool wait_in_progress{false};
        std::uint32_t wait_generation{0U};
        atomic_ptr_t active_adapter{nullptr};
        std::uint8_t active_instance{0U};
    };

    [[nodiscard]] inline constexpr int blockIndex(std::uint8_t instance) noexcept
    {
        switch (instance)
        {
        case 0U:
            return 0;
        case 20U:
            return 1;
        case 21U:
            return 2;
        case 22U:
            return 3;
        case 30U:
            return 4;
        default:
            return -1;
        }
    }

    [[nodiscard]] inline constexpr int handleIndex(SerialPersonality personality,
                                                   std::uint8_t instance) noexcept
    {
        const int block = blockIndex(instance);
        if (block < 0)
        {
            return -1;
        }
        switch (personality)
        {
        case SerialPersonality::uarte:
            return block;
        case SerialPersonality::spim:
            return 5 + block;
        case SerialPersonality::spis:
            return 10 + block;
        case SerialPersonality::twim:
            return instance == 0U ? -1 : 14 + block;
        case SerialPersonality::twis:
            return instance == 0U ? -1 : 18 + block;
        default:
            return -1;
        }
    }
    /** @brief 기존 단일 fabric mutex의 잠금 경계입니다. */
    void lockFabric() noexcept;
    void unlockFabric() noexcept;
    /** @brief mutex 보유 중에만 수정하는 고정 context를 반환합니다. */
    [[nodiscard]] HandleContext &contextAt(std::uint8_t index) noexcept;
    [[nodiscard]] BlockContext &blockAt(std::size_t index) noexcept;
    /** @brief 등록 이후 불변인 adapter와 등록 여부를 조회합니다. */
    [[nodiscard]] const SerialFabricDriverAdapter &adapterAt(std::uint8_t index) noexcept;
    [[nodiscard]] bool adapterRegistered(std::uint8_t index) noexcept;
    /** @brief STOP 증명 뒤 또는 fake adapter test reset에서 저장한 핀·전원을 복원합니다. */
    bool restoreRouteState(HandleContext &context, int &driver_error) noexcept;
} // namespace nucode::arduino::internal::serial
