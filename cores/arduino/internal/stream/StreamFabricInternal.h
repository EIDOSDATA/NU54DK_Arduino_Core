/** @file @brief Stream 내부 queue·자원 helper와 단일 잠금 경계입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <nucode/StreamFabric.h>
#include "../IoResourceManager.h"
#include "../FabricSynchronization.h"
#include "../dma_count.h"
#include "../dma_memory.h"
#include "../pin_description.h"
#include <variant.h>
#include <hal/nrf_gpio.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>
#include <cstddef>
#include <cstdint>
#include <errno.h>
namespace nucode::arduino::internal::stream
{
    /** @brief 기존 family mutex를 단일 소유하는 잠금 경계입니다. */
    void lockStream() noexcept;
    void unlockStream() noexcept;
    /** @brief 기존 SYS_INIT 순서에서 연결하는 peripheral IRQ trampoline입니다. */
    void pdm20Irq(const void *);
    void pdm21Irq(const void *);
    void i2s20Irq(const void *);
    void qdec20Irq(const void *);
    void qdec21Irq(const void *);
    /** @brief PDM/I2S callback의 짧은 metadata 접근만 보호하는 단일 spinlock입니다. */
    k_spinlock &dmaMetadataLock() noexcept;
    using internal::IoAcquirePolicy;
    using internal::IoOwnerKind;
    using internal::IoResourceId;
    using internal::IoResourceKind;
    using internal::IoResourceLease;
    using internal::IoResourceResult;
    using internal::IoResourceToken;
    using internal::PinCapability;
    using internal::PinPolicy;
    using internal::PinRoute;

    inline constexpr std::size_t event_queue_capacity = 12U;
    inline constexpr pin_size_t disconnected_pin = 0xFFU;
    template <typename Event> struct EventQueue
    {
        Event entries[event_queue_capacity]{};
        std::size_t read_index{0U};
        std::size_t write_index{0U};
        std::size_t count{0U};
        bool overflow{false};
        struct k_spinlock lock{};
    };

    template <typename Event> bool pushEvent(EventQueue<Event> &queue, const Event &event) noexcept
    {
        const k_spinlock_key_t key = k_spin_lock(&queue.lock);
        if (queue.count == event_queue_capacity)
        {
            queue.overflow = true;
            k_spin_unlock(&queue.lock, key);
            return false;
        }
        queue.entries[queue.write_index] = event;
        queue.write_index = (queue.write_index + 1U) % event_queue_capacity;
        ++queue.count;
        k_spin_unlock(&queue.lock, key);
        return true;
    }

    template <typename Event> bool popEvent(EventQueue<Event> &queue, Event &event) noexcept
    {
        const k_spinlock_key_t key = k_spin_lock(&queue.lock);
        /** @brief 가득 찬 queue 밖에 보존한 손실을 다음 thread 연산이 덮어쓰지 않습니다. */
        if (queue.overflow)
        {
            queue.overflow = false;
            event = {};
            event.driver_error = -ENOBUFS;
            k_spin_unlock(&queue.lock, key);
            return true;
        }
        if (queue.count == 0U)
        {
            k_spin_unlock(&queue.lock, key);
            return false;
        }
        event = queue.entries[queue.read_index];
        queue.read_index = (queue.read_index + 1U) % event_queue_capacity;
        --queue.count;
        k_spin_unlock(&queue.lock, key);
        return true;
    }

    template <typename Event> void clearEvents(EventQueue<Event> &queue) noexcept
    {
        const k_spinlock_key_t key = k_spin_lock(&queue.lock);
        queue.read_index = 0U;
        queue.write_index = 0U;
        queue.count = 0U;
        queue.overflow = false;
        k_spin_unlock(&queue.lock, key);
    }
    template <typename Context>
    void record(Context &context, StreamFabricResult result, int driver_error = 0) noexcept
    {
        context.diagnostics.record(result, driver_error);
    }
    [[nodiscard]] inline StreamFabricResult mapResourceResult(IoResourceResult result) noexcept
    {
        switch (result)
        {
        case IoResourceResult::success:
            return StreamFabricResult::success;
        case IoResourceResult::invalid_context:
            return StreamFabricResult::invalid_context;
        case IoResourceResult::invalid_argument:
            return StreamFabricResult::invalid_argument;
        case IoResourceResult::conflict:
            return StreamFabricResult::ownership_conflict;
        case IoResourceResult::capacity_exhausted:
            return StreamFabricResult::resource_exhausted;
        default:
            return StreamFabricResult::release_failed;
        }
    }
    struct DmaLeaseSlot
    {
        const void *address{nullptr};
        std::size_t bytes{0U};
        IoResourceToken token{};
        bool active{false};
    };

    template <std::size_t Capacity>
    [[nodiscard]] StreamFabricResult reserveDma(DmaLeaseSlot (&slots)[Capacity], IoOwnerKind owner,
                                                std::uint8_t instance, const void *address,
                                                std::size_t bytes, DmaLeaseSlot *&slot) noexcept
    {
        slot = nullptr;
        if (bytes > UINT32_MAX || !internal::dmaMemoryRangeValid(address, bytes))
        {
            return StreamFabricResult::invalid_argument;
        }
        for (auto &candidate : slots)
        {
            if (!candidate.active)
            {
                slot = &candidate;
                break;
            }
        }
        if (slot == nullptr)
        {
            return StreamFabricResult::resource_exhausted;
        }
        const IoResourceId resource =
            internal::dmaMemoryIoResource(address, static_cast<std::uint32_t>(bytes));
        slot->token = {};
        const auto result = internal::acquireIoResources({owner, instance}, &resource, 1U,
                                                         IoAcquirePolicy::exclusive, slot->token);
        if (result != IoResourceResult::success)
        {
            slot = nullptr;
            return mapResourceResult(result);
        }
        const auto key = k_spin_lock(&dmaMetadataLock());
        slot->address = address;
        slot->bytes = bytes;
        slot->active = true;
        k_spin_unlock(&dmaMetadataLock(), key);
        return StreamFabricResult::success;
    }

    inline void rollbackDma(DmaLeaseSlot &slot) noexcept
    {
        if (slot.active && internal::releaseIoResources(slot.token) != IoResourceResult::success)
        {
            return;
        }
        const auto key = k_spin_lock(&dmaMetadataLock());
        slot = {};
        k_spin_unlock(&dmaMetadataLock(), key);
    }

    [[nodiscard]] inline IoResourceResult commitDma(DmaLeaseSlot &slot) noexcept
    {
        return slot.active ? IoResourceResult::success : IoResourceResult::wrong_phase;
    }

    [[nodiscard]] inline IoResourceResult releaseDma(DmaLeaseSlot &slot) noexcept
    {
        if (!slot.active)
        {
            return IoResourceResult::success;
        }
        const auto result = internal::releaseIoResources(slot.token);
        if (result == IoResourceResult::success)
        {
            const auto key = k_spin_lock(&dmaMetadataLock());
            slot = {};
            k_spin_unlock(&dmaMetadataLock(), key);
        }
        return result;
    }

    template <std::size_t Capacity>
    [[nodiscard]] IoResourceResult releaseDmaFor(DmaLeaseSlot (&slots)[Capacity],
                                                 const void *address) noexcept
    {
        if (address == nullptr)
        {
            return IoResourceResult::success;
        }
        for (auto &slot : slots)
        {
            if (slot.active && slot.address == address)
            {
                return releaseDma(slot);
            }
        }
        return IoResourceResult::stale_lease;
    }

    template <std::size_t Capacity>
    [[nodiscard]] IoResourceResult releaseAllDma(DmaLeaseSlot (&slots)[Capacity]) noexcept
    {
        IoResourceResult result = IoResourceResult::success;
        for (auto &slot : slots)
        {
            const auto current = releaseDma(slot);
            if (current != IoResourceResult::success)
            {
                result = current;
            }
        }
        return result;
    }

    [[nodiscard]] inline std::uint32_t
    physicalPin(const internal::PinDescription &description) noexcept
    {
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio0))
        if (description.gpio.port == DEVICE_DT_GET(DT_NODELABEL(gpio0)))
        {
            return NRF_GPIO_PIN_MAP(0U, description.gpio.pin);
        }
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio1))
        if (description.gpio.port == DEVICE_DT_GET(DT_NODELABEL(gpio1)))
        {
            return NRF_GPIO_PIN_MAP(1U, description.gpio.pin);
        }
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio2))
        if (description.gpio.port == DEVICE_DT_GET(DT_NODELABEL(gpio2)))
        {
            return NRF_GPIO_PIN_MAP(2U, description.gpio.pin);
        }
#endif
        return UINT32_MAX;
    }

    [[nodiscard]] inline const internal::PinDescription *
    streamPin(pin_size_t pin, PinCapability capability, StreamElectricalProfile profile) noexcept
    {
        if (pin == disconnected_pin)
        {
            return nullptr;
        }
        const auto *const description = internal::pinDescription(pin);
        if (description == nullptr || description->canonical_pin != pin ||
            !internal::hasPinRoute(description->routes, PinRoute::header) ||
            !internal::hasPinRoute(description->routes, PinRoute::port1) ||
            physicalPin(*description) == UINT32_MAX)
        {
            return nullptr;
        }
        if (profile == StreamElectricalProfile::dap_uart_disabled)
        {
            /** @brief 공개 GPIO 권한은 변경하지 않고 격리된 DAP pad만 빌립니다. */
            const auto physical = physicalPin(*description);
            const bool console_owns =
                IS_ENABLED(CONFIG_SERIAL) && DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(uart20));
            if (console_owns || physical < NRF_GPIO_PIN_MAP(1, 4) ||
                physical > NRF_GPIO_PIN_MAP(1, 7) ||
                (capability != PinCapability::digital_input &&
                 capability != PinCapability::digital_output))
            {
                return nullptr;
            }
            return description;
        }
        if (profile != StreamElectricalProfile::connector_fixture ||
            description->policy == PinPolicy::system_reserved ||
            !internal::hasPinCapability(description->capabilities, capability))
        {
            return nullptr;
        }
        return description;
    }

    [[nodiscard]] inline bool duplicatePins(const pin_size_t *pins, std::size_t count) noexcept
    {
        for (std::size_t index = 0U; index < count; ++index)
        {
            if (pins[index] == disconnected_pin)
            {
                continue;
            }
            for (std::size_t prior = 0U; prior < index; ++prior)
            {
                if (pins[prior] == pins[index])
                {
                    return true;
                }
            }
        }
        return false;
    }

    template <typename Context>
    [[nodiscard]] StreamFabricResult
    claimBase(Context &context, IoOwnerKind owner, std::uint8_t instance,
              const void *driver_register, const pin_size_t *pins, std::size_t pin_count) noexcept
    {
        IoResourceId resources[internal::io_resource_lease_capacity]{};
        std::size_t resource_count = 0U;
        resources[resource_count++] =
            internal::peripheralIoResource(IoResourceKind::stream_block, instance, driver_register);
        for (std::size_t index = 0U; index < pin_count; ++index)
        {
            if (pins[index] == disconnected_pin)
            {
                continue;
            }
            const auto *const description = internal::pinDescription(pins[index]);
            resources[resource_count++] = internal::gpioIoResource(description->gpio);
        }
        context.base_lease = {};
        return mapResourceResult(
            internal::reserveIoResources({owner, instance}, resources, resource_count,
                                         IoAcquirePolicy::exclusive, context.base_lease));
    }
} // namespace nucode::arduino::internal::stream
