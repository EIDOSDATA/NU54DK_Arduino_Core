/** @file @brief Analog 내부 queue·자원 helper와 단일 잠금 경계입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <nucode/AnalogFabric.h>
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
namespace nucode::arduino::internal::analog
{
    /** @brief 기존 family mutex를 단일 소유하는 잠금 경계입니다. */
    void lockAnalog() noexcept;
    void unlockAnalog() noexcept;
    /** @brief 기존 SYS_INIT 순서에서 연결하는 peripheral IRQ trampoline입니다. */
    void saadcIrq(const void *);
    void pwm20Irq(const void *);
    void pwm21Irq(const void *);
    void pwm22Irq(const void *);
    using internal::IoAcquirePolicy;
    using internal::IoOwnerKind;
    using internal::IoResourceId;
    using internal::IoResourceKind;
    using internal::IoResourceLease;
    using internal::IoResourceResult;
    using internal::PinCapability;
    using internal::PinPolicy;
    using internal::PinRoute;

    inline constexpr std::size_t event_queue_capacity = 8U;
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
    void record(Context &context, AnalogFabricResult result, int driver_error = 0) noexcept
    {
        context.diagnostics.record(result, driver_error);
    }
    [[nodiscard]] inline AnalogFabricResult mapResourceResult(IoResourceResult result) noexcept
    {
        switch (result)
        {
        case IoResourceResult::success:
            return AnalogFabricResult::success;
        case IoResourceResult::invalid_context:
            return AnalogFabricResult::invalid_context;
        case IoResourceResult::invalid_argument:
            return AnalogFabricResult::invalid_argument;
        case IoResourceResult::conflict:
            return AnalogFabricResult::ownership_conflict;
        case IoResourceResult::capacity_exhausted:
            return AnalogFabricResult::resource_exhausted;
        default:
            return AnalogFabricResult::release_failed;
        }
    }

} // namespace nucode::arduino::internal::analog
