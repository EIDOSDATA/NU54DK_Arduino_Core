/** @file @brief Serial Fabric의 단일 table·adapter 등록·IRQ 소유권입니다.
 * SPDX-License-Identifier: MIT
 */
#include "SerialFabricInternal.h"
#include <hal/nrf_gpio.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>
namespace nucode::arduino::internal::serial
{
    namespace
    {
        K_MUTEX_DEFINE(fabric_mutex);
        HandleContext contexts[handle_count]{};
        SerialFabricDriverAdapter adapters[handle_count]{};
        bool adapter_registered[handle_count]{};
        BlockContext blocks[block_count]{};

#if defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_UARTE) ||                                          \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIM) ||                                           \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIS) ||                                           \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_TWIM) ||                                           \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_TWIS)
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_UARTE) ||                                          \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIM) ||                                           \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIS)
        void irq00(const void *)
        {
            internal::dispatchSerialFabricIrq(0U);
        }
#endif
        void irq20(const void *)
        {
            internal::dispatchSerialFabricIrq(20U);
        }
        void irq21(const void *)
        {
            internal::dispatchSerialFabricIrq(21U);
        }
        void irq22(const void *)
        {
            internal::dispatchSerialFabricIrq(22U);
        }
        void irq30(const void *)
        {
            internal::dispatchSerialFabricIrq(30U);
        }

        int connectFabricIrqs()
        {
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_UARTE) ||                                          \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIM) ||                                           \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIS)
            IRQ_CONNECT(SERIAL00_IRQn, IRQ_PRIO_LOWEST, irq00, nullptr, 0);
#endif
            IRQ_CONNECT(SERIAL20_IRQn, IRQ_PRIO_LOWEST, irq20, nullptr, 0);
            IRQ_CONNECT(SERIAL21_IRQn, IRQ_PRIO_LOWEST, irq21, nullptr, 0);
            IRQ_CONNECT(SERIAL22_IRQn, IRQ_PRIO_LOWEST, irq22, nullptr, 0);
            IRQ_CONNECT(SERIAL30_IRQn, IRQ_PRIO_LOWEST, irq30, nullptr, 0);
            return 0;
        }

        SYS_INIT(connectFabricIrqs, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
#endif

    } // namespace
    void lockFabric() noexcept
    {
        k_mutex_lock(&fabric_mutex, K_FOREVER);
    }
    void unlockFabric() noexcept
    {
        k_mutex_unlock(&fabric_mutex);
    }
    [[nodiscard]] HandleContext &contextAt(std::uint8_t index) noexcept
    {
        return contexts[index];
    }
    BlockContext &blockAt(std::size_t index) noexcept
    {
        return blocks[index];
    }
    const SerialFabricDriverAdapter &adapterAt(std::uint8_t index) noexcept
    {
        return adapters[index];
    }
    bool adapterRegistered(std::uint8_t index) noexcept
    {
        return adapter_registered[index];
    }
} // namespace nucode::arduino::internal::serial
namespace nucode::arduino::internal
{
    using namespace serial;
    SerialFabricResult
    registerSerialFabricAdapter(SerialPersonality personality, std::uint8_t instance,
                                const SerialFabricDriverAdapter &adapter) noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        const int index = handleIndex(personality, instance);
        if ((index < 0) || (adapter.validate == nullptr) || (adapter.activate == nullptr) ||
            (adapter.request_stop == nullptr) || (adapter.stopped == nullptr) ||
            (adapter.deactivate == nullptr) || (adapter.handle_irq == nullptr))
        {
            return index < 0 ? SerialFabricResult::unsupported_instance
                             : SerialFabricResult::invalid_argument;
        }
        lockFabric();
        if (adapter_registered[index] || (contexts[index].state != SerialFabricState::inactive))
        {
            unlockFabric();
            return SerialFabricResult::wrong_state;
        }
        adapters[index] = adapter;
        adapter_registered[index] = true;
        contexts[index].adapter = &adapters[index];
        unlockFabric();
        return SerialFabricResult::success;
    }

    bool isSerialFabricHandleActive(SerialPersonality personality, std::uint8_t instance) noexcept
    {
        const int index = handleIndex(personality, instance);
        if (index < 0)
        {
            return false;
        }
        lockFabric();
        const bool active = contexts[index].state == SerialFabricState::active &&
                            !blocks[blockIndex(instance)].wait_in_progress;
        unlockFabric();
        return active;
    }

    SerialFabricOperationGuard::SerialFabricOperationGuard() noexcept
    {
        lockFabric();
    }

    SerialFabricOperationGuard::~SerialFabricOperationGuard()
    {
        unlockFabric();
    }

    void dispatchSerialFabricIrq(std::uint8_t instance) noexcept
    {
        const int block = blockIndex(instance);
        if (block < 0)
        {
            return;
        }
        auto *const adapter =
            static_cast<SerialFabricDriverAdapter *>(atomic_ptr_get(&blocks[block].active_adapter));
        if (adapter != nullptr)
        {
            adapter->handle_irq(blocks[block].active_instance);
        }
    }
#if defined(CONFIG_ZTEST)
    void resetSerialFabricForTest() noexcept
    {
        if (k_is_in_isr())
        {
            return;
        }
        lockFabric();
        for (const auto &block : blocks)
        {
            /** @brief fake adapter 시험에서도 대기 중인 context를 교체하지 않습니다. */
            if (block.wait_in_progress)
            {
                unlockFabric();
                return;
            }
        }
        for (auto &context : contexts)
        {
            /** @brief fake adapter ztest 격리 전용이며 실제 hardware 복구 API가 아닙니다. */
            int ignored = 0;
            (void)restoreRouteState(context, ignored);
            context = {};
        }
        for (auto &adapter : adapters)
        {
            adapter = {};
        }
        for (bool &registered : adapter_registered)
        {
            registered = false;
        }
        for (auto &block : blocks)
        {
            block = {};
        }
        unlockFabric();
    }
#endif
} // namespace nucode::arduino::internal
