/** @file @brief EGU·DPPI와 PPIB 왕복 경로를 외부 GPIO 없이 검증합니다. */
#pragma once
#include <hal/nrf_dppi.h>
#include <hal/nrf_egu.h>
#include <hal/nrf_ppib.h>

namespace
{
    NRF_DPPIC_Type *dppiRegisters(std::uint32_t instance)
    {
        switch (instance)
        {
        case 0U:
            return NRF_DPPIC00;
        case 10U:
            return NRF_DPPIC10;
        case 20U:
            return NRF_DPPIC20;
        case 30U:
            return NRF_DPPIC30;
        default:
            return nullptr;
        }
    }

    /** @brief CPU는 발생 EGU만 trigger하며 수신 EGU event를 독립 관측합니다. */
    bool observeEvent(EguFabric &egu, std::uint8_t source, std::uint8_t sink, bool expected)
    {
        auto *const event = reinterpret_cast<volatile std::uint32_t *>(egu.event(sink).address);
        *reinterpret_cast<volatile std::uint32_t *>(egu.event(source).address) = 0U;
        *event = 0U;
        nrf_barrier_rw();
        if (egu.trigger(source) != EventFabricResult::success)
        {
            return false;
        }
        k_busy_wait(100U);
        if (expected)
        {
            const auto deadline = k_uptime_get() + 2;
            while (*event == 0U && k_uptime_get() < deadline)
            {
                k_busy_wait(10U);
            }
        }
        return (*event != 0U) == expected;
    }

    /** @brief 한 channel의 enable/disable/disconnect와 모든 group의 해제를 반복합니다. */
    void exerciseEvent(const std::uint32_t *request, std::uint32_t *result)
    {
        const auto domain = request[3];
        const auto channel = request[4];
        const auto source = request[5];
        const auto events = request[6];
        const auto repetitions = request[7];
        auto *const dppi = eventFabric().dppi(static_cast<std::uint8_t>(domain));
        auto *const egu = eventFabric().egu(static_cast<std::uint8_t>(domain));
        auto *const registers = dppiRegisters(domain);
        if ((domain != 10U && domain != 20U) || dppi == nullptr || egu == nullptr ||
            channel >= dppi->channelCount() || source >= egu->channelCount() || events != 1000U ||
            repetitions == 0U || repetitions > 10U)
        {
            result[2] = 1U;
            return;
        }
        auto *const egu_registers = domain == 10U ? NRF_EGU10 : NRF_EGU20;
        const auto ch = static_cast<std::uint8_t>(channel);
        const auto src = static_cast<std::uint8_t>(source);
        const auto sink = static_cast<std::uint8_t>((source + 1U) % egu->channelCount());
        const auto publisher = egu->event(src);
        const auto subscriber = egu->task(sink);
        result[23] = dppi->groupCount();
        for (std::uint32_t run = 0U; run < repetitions; ++run)
        {
            if (!refusesReservation(
                    peripheralIoResource(IoResourceKind::dppi_channel, ch, registers),
                    [&]
                    {
                        return dppi->acquireChannel(ch);
                    }) ||
                !refusesReservation(
                    peripheralIoResource(IoResourceKind::event_channel, src, egu_registers),
                    [&]
                    {
                        return egu->acquire(src);
                    }))
            {
                result[2] = 6U;
                return;
            }
            ++result[24];
            ++result[25];
            bool valid = egu->acquire(src) == EventFabricResult::success;
            valid &= egu->acquire(sink) == EventFabricResult::success;
            valid &= dppi->acquireChannel(ch) == EventFabricResult::success;
            if (!valid)
            {
                result[2] = 2U;
                return;
            }
            valid &= dppi->connect(publisher, subscriber, ch) == EventFabricResult::success;
            valid &= dppi->enable(ch) == EventFabricResult::success;
            for (std::uint32_t index = 0U; valid && index < events; ++index)
            {
                valid = observeEvent(*egu, src, sink, true);
                if (valid)
                {
                    ++result[12];
                }
            }
            valid &= dppi->disable(ch) == EventFabricResult::success;
            valid &= observeEvent(*egu, src, sink, false);
            if (valid)
            {
                ++result[13];
            }
            for (std::uint8_t group = 0U; valid && group < dppi->groupCount(); ++group)
            {
                valid &= refusesReservation(
                    peripheralIoResource(IoResourceKind::dppi_group, group, registers),
                    [&]
                    {
                        return dppi->acquireGroup(group, 1UL << ch);
                    });
                if (valid)
                {
                    ++result[26];
                }
                valid &= dppi->acquireGroup(group, 1UL << ch) == EventFabricResult::success;
                valid &= registers->CHG[group] == (1UL << ch);
                nrf_dppi_group_enable(registers, static_cast<nrf_dppi_channel_group_t>(group));
                valid &= (registers->CHEN & (1UL << ch)) != 0U;
                valid &= observeEvent(*egu, src, sink, true);
                valid &= dppi->releaseGroup(group) == EventFabricResult::success;
                valid &= registers->CHG[group] == 0U && (registers->CHEN & (1UL << ch)) == 0U;
                valid &= observeEvent(*egu, src, sink, false);
                valid &= resourceFree(
                    peripheralIoResource(IoResourceKind::dppi_group, group, registers));
                if (valid)
                {
                    ++result[22];
                }
            }
            valid &= dppi->disconnect(publisher, subscriber, ch) == EventFabricResult::success;
            valid &= dppi->enable(ch) == EventFabricResult::success;
            valid &= observeEvent(*egu, src, sink, false);
            if (valid)
            {
                ++result[14];
            }
            result[10] = static_cast<std::uint32_t>(dppi->releaseChannel(ch));
            valid &= egu->release(src) == EventFabricResult::success;
            valid &= egu->release(sink) == EventFabricResult::success;
            result[17] = registers->CHEN & (1UL << ch);
            result[18] = *reinterpret_cast<volatile std::uint32_t *>(publisher.address + 0x80U);
            result[19] = *reinterpret_cast<volatile std::uint32_t *>(subscriber.address + 0x80U);
            result[20] =
                resourceFree(peripheralIoResource(IoResourceKind::dppi_channel, ch, registers)) &&
                resourceFree(
                    peripheralIoResource(IoResourceKind::event_channel, src, egu_registers)) &&
                resourceFree(
                    peripheralIoResource(IoResourceKind::event_channel, sink, egu_registers));
            if (!valid || result[10] != 0U || result[17] != 0U || result[18] != 0U ||
                result[19] != 0U || result[20] != 1U)
            {
                result[2] = 4U;
                return;
            }
            ++result[21];
        }
    }

    /** @brief 서로 다른 두 bridge channel을 사용해 되먹임 없는 왕복 경로를 구성합니다. */
    void exerciseBridge(const std::uint32_t *request, std::uint32_t *result)
    {
        const auto pair = request[3];
        const auto channel = request[4];
        const auto remote_channel = request[5];
        const auto events = request[6];
        const auto repetitions = request[7];
        constexpr std::uint8_t starts[] = {10U, 20U, 21U, 22U};
        constexpr std::uint8_t ends[] = {0U, 1U, 11U, 30U};
        NRF_PPIB_Type *const start_regs[] = {NRF_PPIB10, NRF_PPIB20, NRF_PPIB21, NRF_PPIB22};
        NRF_PPIB_Type *const end_regs[] = {NRF_PPIB00, NRF_PPIB01, NRF_PPIB11, NRF_PPIB30};
        if (pair > 3U || events != 1000U || repetitions == 0U || repetitions > 10U)
        {
            result[2] = 1U;
            return;
        }
        auto &start = *eventFabric().ppib(starts[pair]);
        auto &end = *eventFabric().ppib(ends[pair]);
        auto &local = *eventFabric().dppi(start.domain());
        auto &remote = *eventFabric().dppi(end.domain());
        auto &egu = *eventFabric().egu(start.domain());
        auto *const local_reg = dppiRegisters(start.domain());
        auto *const remote_reg = dppiRegisters(end.domain());
        const auto outgoing = static_cast<std::uint8_t>(channel);
        const auto incoming = static_cast<std::uint8_t>(channel ^ 1U);
        const auto middle = static_cast<std::uint8_t>(remote_channel);
        if (channel >= start.channelCount() || channel >= end.channelCount() ||
            incoming >= start.channelCount() || incoming >= end.channelCount() ||
            remote_channel >= remote.channelCount())
        {
            result[2] = 1U;
            return;
        }
        result[23] = remote.groupCount();
        for (std::uint32_t run = 0U; run < repetitions; ++run)
        {
            if (!refusesReservation(
                    peripheralIoResource(IoResourceKind::ppib_channel, outgoing, start_regs[pair]),
                    [&]
                    {
                        return start.acquire(outgoing);
                    }))
            {
                result[2] = 6U;
                return;
            }
            ++result[24];
            bool valid = start.acquire(outgoing) == EventFabricResult::success;
            valid &= start.acquire(incoming) == EventFabricResult::success;
            valid &= end.acquire(outgoing) == EventFabricResult::success;
            valid &= end.acquire(incoming) == EventFabricResult::success;
            valid &= local.acquireChannel(0U) == EventFabricResult::success;
            valid &= local.acquireChannel(1U) == EventFabricResult::success;
            valid &= remote.acquireChannel(middle) == EventFabricResult::success;
            valid &= egu.acquire(0U) == EventFabricResult::success;
            valid &= egu.acquire(1U) == EventFabricResult::success;
            if (!valid)
            {
                result[2] = 2U;
                return;
            }
            start_regs[pair]->OVERFLOW.SEND = 0U;
            end_regs[pair]->OVERFLOW.SEND = 0U;
            valid &= local.connect(egu.event(0U), start.sendTask(outgoing), 0U) ==
                     EventFabricResult::success;
            valid &= remote.connect(end.receiveEvent(outgoing), end.sendTask(incoming), middle) ==
                     EventFabricResult::success;
            valid &= local.connect(start.receiveEvent(incoming), egu.task(1U), 1U) ==
                     EventFabricResult::success;
            valid &= remote.enable(middle) == EventFabricResult::success;
            valid &= local.enable(1U) == EventFabricResult::success;
            valid &= local.enable(0U) == EventFabricResult::success;
            for (std::uint32_t index = 0U; valid && index < events; ++index)
            {
                valid = observeEvent(egu, 0U, 1U, true);
                if (valid)
                {
                    ++result[12];
                }
            }
            valid &= remote.disable(middle) == EventFabricResult::success;
            valid &= observeEvent(egu, 0U, 1U, false);
            if (valid)
            {
                ++result[13];
            }
            for (std::uint8_t group = 0U; valid && group < remote.groupCount(); ++group)
            {
                valid &= refusesReservation(
                    peripheralIoResource(IoResourceKind::dppi_group, group, remote_reg),
                    [&]
                    {
                        return remote.acquireGroup(group, 1UL << middle);
                    });
                if (valid)
                {
                    ++result[26];
                }
                valid &= remote.acquireGroup(group, 1UL << middle) == EventFabricResult::success;
                valid &= remote_reg->CHG[group] == (1UL << middle);
                nrf_dppi_group_enable(remote_reg, static_cast<nrf_dppi_channel_group_t>(group));
                valid &= observeEvent(egu, 0U, 1U, true);
                valid &= remote.releaseGroup(group) == EventFabricResult::success;
                valid &= remote_reg->CHG[group] == 0U && (remote_reg->CHEN & (1UL << middle)) == 0U;
                valid &= observeEvent(egu, 0U, 1U, false);
                valid &= resourceFree(
                    peripheralIoResource(IoResourceKind::dppi_group, group, remote_reg));
                if (valid)
                {
                    ++result[22];
                }
            }
            valid &= local.releaseChannel(0U) == EventFabricResult::success;
            valid &= local.releaseChannel(1U) == EventFabricResult::success;
            valid &= remote.releaseChannel(middle) == EventFabricResult::success;
            valid &= start.release(outgoing) == EventFabricResult::success;
            valid &= start.release(incoming) == EventFabricResult::success;
            valid &= end.release(outgoing) == EventFabricResult::success;
            valid &= end.release(incoming) == EventFabricResult::success;
            valid &= egu.release(0U) == EventFabricResult::success;
            valid &= egu.release(1U) == EventFabricResult::success;
            result[17] = (local_reg->CHEN & 3U) | (remote_reg->CHEN & (1UL << middle));
            result[18] = start_regs[pair]->OVERFLOW.SEND;
            result[19] = end_regs[pair]->OVERFLOW.SEND;
            result[20] =
                resourceFree(peripheralIoResource(IoResourceKind::dppi_channel, 0U, local_reg)) &&
                resourceFree(peripheralIoResource(IoResourceKind::dppi_channel, 1U, local_reg)) &&
                resourceFree(
                    peripheralIoResource(IoResourceKind::dppi_channel, middle, remote_reg));
            auto *const egu_registers = start.domain() == 10U ? NRF_EGU10 : NRF_EGU20;
            result[20] &= resourceFree(peripheralIoResource(IoResourceKind::event_channel, 0U,
                                                            egu_registers)) &&
                          resourceFree(peripheralIoResource(IoResourceKind::event_channel, 1U,
                                                            egu_registers));
            valid &=
                *reinterpret_cast<volatile std::uint32_t *>(egu.event(0U).address + 0x80U) == 0U &&
                *reinterpret_cast<volatile std::uint32_t *>(egu.task(1U).address + 0x80U) == 0U;
            const std::uint8_t bridge_channels[] = {outgoing, incoming};
            for (auto bridge_channel : bridge_channels)
            {
                result[20] &=
                    resourceFree(peripheralIoResource(IoResourceKind::ppib_channel, bridge_channel,
                                                      start_regs[pair])) &&
                    resourceFree(peripheralIoResource(IoResourceKind::ppib_channel, bridge_channel,
                                                      end_regs[pair]));
                valid &= start_regs[pair]->SUBSCRIBE_SEND[bridge_channel] == 0U &&
                         start_regs[pair]->PUBLISH_RECEIVE[bridge_channel] == 0U &&
                         end_regs[pair]->SUBSCRIBE_SEND[bridge_channel] == 0U &&
                         end_regs[pair]->PUBLISH_RECEIVE[bridge_channel] == 0U;
            }
            if (!valid || result[17] != 0U || result[18] != 0U || result[19] != 0U ||
                result[20] != 1U)
            {
                result[2] = 4U;
                return;
            }
            ++result[21];
        }
    }
} // namespace
