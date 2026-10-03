/**
 * @file NUCODE_Radio_Coexistence.cpp
 * @brief MPSL 공존 관측과 외부 1-wire grant backend 구현입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_Radio_Coexistence.h"

#include <zephyr/irq.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#if defined(CONFIG_NUCODE_RADIO_COEX_ONEWIRE)
#include <hal/nrf_egu.h>
#include <hal/nrf_gpio.h>
#include <protocol/mpsl_dppi_protocol_api.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/util.h>
#endif

namespace
{
    /** @brief protocol enum을 고정 배열 index로 변환합니다. */
    std::size_t protocolIndex(nucode::coexistence::Protocol protocol) noexcept
    {
        return static_cast<std::size_t>(protocol);
    }

    /** @brief IRQ와 thread 양쪽에서 사용하는 saturating add입니다. */
    void saturatingAdd(std::uint32_t &value, std::uint32_t increment) noexcept
    {
        if (UINT32_MAX - value < increment)
        {
            value = UINT32_MAX;
        }
        else
        {
            value += increment;
        }
    }

#if defined(CONFIG_NUCODE_RADIO_COEX_ONEWIRE)
#define NUCODE_COEX_EGU_NODE DT_ALIAS(egu)
#define NUCODE_COEX_EGU ((NRF_EGU_Type *)DT_REG_ADDR(NUCODE_COEX_EGU_NODE))
#define NUCODE_COEX_EGU_EVENT_ID 4
#define NUCODE_COEX_EGU_TASK NRFX_CONCAT(NRF_EGU_, TASK_TRIGGER, NUCODE_COEX_EGU_EVENT_ID)
#define NUCODE_COEX_EGU_INTERRUPT NRFX_CONCAT(NRF_EGU_, INT_TRIGGERED, NUCODE_COEX_EGU_EVENT_ID)
#define NUCODE_COEX_EGU_EVENT NRFX_CONCAT(NRF_EGU_, EVENT_TRIGGERED, NUCODE_COEX_EGU_EVENT_ID)
#define NUCODE_COEX_NODE DT_PHANDLE(DT_NODELABEL(radio), coex)
#define NUCODE_COEX_USER_NODE DT_PATH(zephyr_user)
#define NUCODE_COEX_GRANT_OUTPUT \
    NRF_DT_GPIOS_TO_PSEL(NUCODE_COEX_USER_NODE, coex_pta_grant_gpios)

    atomic_t radio_event_count;

    /** @brief RADIO READY publish를 누적하고 EGU event를 정리합니다. */
    extern "C" void nucodeCoexistenceEguHandler(const void *context)
    {
        static_cast<void>(context);
        atomic_inc(&radio_event_count);
        nrf_egu_event_clear(NUCODE_COEX_EGU, NUCODE_COEX_EGU_EVENT);
    }
#endif
}

namespace nucode::coexistence
{
    bool CoexistenceMonitor::begin(std::uint32_t starvation_limit_ms) noexcept
    {
        if (starvation_limit_ms == 0U)
        {
            return false;
        }

        const unsigned int key = irq_lock();
        for (std::size_t index = 0U; index < protocol_count; ++index)
        {
            statistics_[index] = {};
            last_service_ms_[index] = 0U;
        }
        starvation_limit_ms_ = starvation_limit_ms;
        started_ = true;
        irq_unlock(key);
        return true;
    }

    void CoexistenceMonitor::recordRequested(Protocol protocol) noexcept
    {
        const std::size_t index = protocolIndex(protocol);
        if (!started_ || index >= protocol_count)
        {
            return;
        }

        const unsigned int key = irq_lock();
        saturatingAdd(statistics_[index].requested, 1U);
        irq_unlock(key);
    }

    void CoexistenceMonitor::recordDelivered(Protocol protocol, std::uint32_t sequence,
                                             std::uint32_t hash, bool hash_valid) noexcept
    {
        const std::size_t index = protocolIndex(protocol);
        if (!started_ || index >= protocol_count)
        {
            return;
        }

        const std::uint32_t now = k_uptime_get_32();
        const unsigned int key = irq_lock();
        ServiceStatistics &entry = statistics_[index];
        if (entry.delivered != 0U && sequence != entry.last_sequence + 1U)
        {
            saturatingAdd(entry.sequence_errors, 1U);
        }
        if (!hash_valid)
        {
            saturatingAdd(entry.hash_errors, 1U);
        }
        if (last_service_ms_[index] != 0U)
        {
            const std::uint32_t gap_ms = now - last_service_ms_[index];
            if (gap_ms > entry.maximum_service_gap_ms)
            {
                entry.maximum_service_gap_ms = gap_ms;
            }
            if (gap_ms > starvation_limit_ms_)
            {
                saturatingAdd(entry.starvation_events, 1U);
            }
        }
        last_service_ms_[index] = now;
        entry.last_sequence = sequence;
        entry.last_hash = hash;
        entry.active = true;
        saturatingAdd(entry.delivered, 1U);
        irq_unlock(key);
    }

    void CoexistenceMonitor::recordDropped(Protocol protocol, std::uint32_t count) noexcept
    {
        const std::size_t index = protocolIndex(protocol);
        if (!started_ || index >= protocol_count)
        {
            return;
        }

        const unsigned int key = irq_lock();
        saturatingAdd(statistics_[index].dropped, count);
        irq_unlock(key);
    }

    void CoexistenceMonitor::recordTimeslotFailure(Protocol protocol) noexcept
    {
        const std::size_t index = protocolIndex(protocol);
        if (!started_ || index >= protocol_count)
        {
            return;
        }

        const unsigned int key = irq_lock();
        saturatingAdd(statistics_[index].timeslot_failures, 1U);
        irq_unlock(key);
    }

    void CoexistenceMonitor::recordRestart(Protocol protocol) noexcept
    {
        const std::size_t index = protocolIndex(protocol);
        if (!started_ || index >= protocol_count)
        {
            return;
        }

        const unsigned int key = irq_lock();
        saturatingAdd(statistics_[index].restart_count, 1U);
        statistics_[index].active = true;
        last_service_ms_[index] = 0U;
        irq_unlock(key);
    }

    void CoexistenceMonitor::setActive(Protocol protocol, bool active) noexcept
    {
        const std::size_t index = protocolIndex(protocol);
        if (!started_ || index >= protocol_count)
        {
            return;
        }

        const unsigned int key = irq_lock();
        statistics_[index].active = active;
        irq_unlock(key);
    }

    ServiceStatistics CoexistenceMonitor::statistics(Protocol protocol) const noexcept
    {
        const std::size_t index = protocolIndex(protocol);
        if (index >= protocol_count)
        {
            return {};
        }

        const unsigned int key = irq_lock();
        const ServiceStatistics snapshot = statistics_[index];
        irq_unlock(key);
        return snapshot;
    }

    bool CoexistenceMonitor::healthy() const noexcept
    {
        const unsigned int key = irq_lock();
        bool result = started_;
        for (std::size_t index = 0U; index < protocol_count; ++index)
        {
            const ServiceStatistics &entry = statistics_[index];
            if (entry.sequence_errors != 0U || entry.hash_errors != 0U ||
                entry.starvation_events != 0U)
            {
                result = false;
            }
        }
        irq_unlock(key);
        return result;
    }

    bool CoexistenceMonitor::beginOneWire() noexcept
    {
#if defined(CONFIG_NUCODE_RADIO_COEX_ONEWIRE)
        if (!started_)
        {
            return false;
        }

        nrf_gpio_cfg_output(NUCODE_COEX_GRANT_OUTPUT);
        atomic_set(&radio_event_count, 0);
        nrf_egu_event_clear(NUCODE_COEX_EGU, NUCODE_COEX_EGU_EVENT);
        nrf_egu_subscribe_set(NUCODE_COEX_EGU, NUCODE_COEX_EGU_TASK,
                              MPSL_DPPI_RADIO_PUBLISH_READY_CHANNEL_IDX);
        IRQ_DIRECT_CONNECT(DT_IRQN(NUCODE_COEX_EGU_NODE), 5,
                           nucodeCoexistenceEguHandler, 0);
        nrf_egu_int_enable(NUCODE_COEX_EGU, NUCODE_COEX_EGU_INTERRUPT);
        NVIC_EnableIRQ(static_cast<IRQn_Type>(DT_IRQN(NUCODE_COEX_EGU_NODE)));
        one_wire_started_ = true;
        return setExternalGrant(true);
#else
        return false;
#endif
    }

    bool CoexistenceMonitor::setExternalGrant(bool granted) noexcept
    {
#if defined(CONFIG_NUCODE_RADIO_COEX_ONEWIRE)
        if (!one_wire_started_)
        {
            return false;
        }

        constexpr bool active_low =
            (DT_GPIO_FLAGS(NUCODE_COEX_NODE, grant_gpios) & GPIO_ACTIVE_LOW) != 0U;
        if (granted != active_low)
        {
            nrf_gpio_pin_set(NUCODE_COEX_GRANT_OUTPUT);
        }
        else
        {
            nrf_gpio_pin_clear(NUCODE_COEX_GRANT_OUTPUT);
        }
        return true;
#else
        static_cast<void>(granted);
        return false;
#endif
    }

    bool CoexistenceMonitor::oneWireSupported() const noexcept
    {
#if defined(CONFIG_NUCODE_RADIO_COEX_ONEWIRE)
        return true;
#else
        return false;
#endif
    }

    std::uint32_t CoexistenceMonitor::radioEventCount() const noexcept
    {
#if defined(CONFIG_NUCODE_RADIO_COEX_ONEWIRE)
        return static_cast<std::uint32_t>(atomic_get(&radio_event_count));
#else
        return 0U;
#endif
    }

    void CoexistenceMonitor::stop() noexcept
    {
#if defined(CONFIG_NUCODE_RADIO_COEX_ONEWIRE)
        if (one_wire_started_)
        {
            static_cast<void>(setExternalGrant(false));
            nrf_egu_int_disable(NUCODE_COEX_EGU, NUCODE_COEX_EGU_INTERRUPT);
            nrf_egu_subscribe_clear(NUCODE_COEX_EGU, NUCODE_COEX_EGU_TASK);
            NVIC_DisableIRQ(static_cast<IRQn_Type>(DT_IRQN(NUCODE_COEX_EGU_NODE)));
        }
#endif
        const unsigned int key = irq_lock();
        for (std::size_t index = 0U; index < protocol_count; ++index)
        {
            statistics_[index].active = false;
        }
        one_wire_started_ = false;
        started_ = false;
        irq_unlock(key);
    }
}

nucode::coexistence::CoexistenceMonitor NUCODECoexistence;
