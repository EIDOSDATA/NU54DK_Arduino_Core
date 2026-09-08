/**
 * @file serial.cpp
 * @brief 활성 peripheral을 유지하며 두 DMA slot의 실제 반환과 전역 payload를 검사합니다.
 * @note UART 수신은 두 버퍼 단위로 재공급하며 frame 사이의 20ms 주기를 기록합니다.
 * SPDX-License-Identifier: MIT
 */
#include "engine.h"
#include "flow.h"
#include "uart_fault.h"
#include "measurement.h"
#include <nucode/SerialFabric.h>
#include <zephyr/kernel.h>
#include <hal/nrf_uarte.h>
#include <hal/nrf_spim.h>
#include <hal/nrf_twim.h>
#include <hal/nrf_spis.h>
#include <hal/nrf_twis.h>
#include <hal/nrf_gpio.h>

namespace
{
    using namespace nucode::arduino;
    using namespace t13;
    constexpr unsigned role = CONFIG_NUCODE_V04_HIL_ROLE;
    constexpr std::uint64_t frame_period_ms = 20U;

    struct Lane
    {
        Endpoint endpoint{};
        SerialFabricHandle *handle = nullptr;
        Buffer tx[2]{}, rx[2]{};
        SerialSignalPin pins[4]{};
        SerialDmaWorkspace workspaces[4]{};
        Direction sent{}, received{};
        Timing timing[3]{};
        std::uint32_t submitted_tx[2]{}, submitted_rx[2]{};
        std::uint32_t seed_tx = 0U, seed_rx = 0U;
        std::uint32_t queued_tx = 0U, queued_rx = 0U;
        std::uint32_t error = 0U, driver_error = 0U;
        std::uint32_t max_queue_us = 0U, requests = 0U;
        std::uint64_t next_frame = 0U;
        bool tx_pending[2]{}, rx_pending[2]{};
        bool active = false;
        std::uint32_t data_fault[20]{};
    };

    Lane lanes[max_lanes];
    unsigned lane_count = 0U;
    bool transmitting = false;
    bool receivers_armed = false;
    Buffer conflict_tx{}, conflict_rx{};
    SerialSignalPin conflict_pins[3]{};
    SerialDmaWorkspace conflict_workspaces[2]{};
    unsigned spi_boundary_policy = 0U;
    struct SpiBoundary
    {
        std::uint32_t raw[20]{}, before[20]{}, after[20]{}, baseline[20]{};
        bool prepared = false;
    } spi_boundary;
    unsigned rx_delay_policy = 0U;
    struct RxDelay
    {
        std::uint32_t raw[20]{};
        bool prepared = false;
    } rx_delay;

    /** @brief RX 공급 지연에서 두 slot의 실제 DMA 앞뒤 경계를 검사합니다. */
    bool rxDelayGuards(const Lane &lane)
    {
        return lane.tx[0].guards(lane.endpoint.length) && lane.tx[1].guards(lane.endpoint.length) &&
               lane.rx[0].guards(lane.endpoint.length) && lane.rx[1].guards(lane.endpoint.length);
    }

    /** @brief 실제 두 버퍼 반환·추가 요청 뒤 한 번만2ms 공급을 미룹니다. */
    bool rxDelayHold(const Lane &lane)
    {
        auto &raw = rx_delay.raw;
        if (!rx_delay.prepared || rx_delay_policy != 1U || raw[2] == 0U || raw[3] == 2U)
        {
            return false;
        }
        if (raw[3] == 0U)
        {
            if (lane.received.completed <= raw[7] || lane.requests <= raw[10])
            {
                return false;
            }
            raw[3] = 1U;
            raw[5] = k_cycle_get_32();
            raw[8] = lane.received.completed;
            raw[9] = lane.requests;
            raw[12] = (lane.rx_pending[0] ? 1U : 0U) | (lane.rx_pending[1] ? 2U : 0U);
            raw[13] = rxDelayGuards(lane) ? 1U : 0U;
        }
        return k_cyc_to_us_floor32(k_cycle_get_32() - raw[5]) < 2000U;
    }

    /** @brief 단독 serial의 의도적 첫 실패와 실제 반환 정보를 정상 통계와 분리합니다. */
    struct Fault
    {
        std::uint32_t mode = 0U, triggered = 0U, result = UINT32_MAX;
        std::uint32_t event = UINT32_MAX, tx_amount = 0U, rx_amount = 0U;
        std::uint32_t pointers = 0U, guards = 0U, error = 0U, address = 0U;
        std::uint32_t submitted_cycle = 0U, requested_cycle = 0U, event_cycle = 0U;
        std::uint32_t events = 0U;
        std::uint32_t hardware_tx = 0U, hardware_rx = 0U;
        std::uint32_t timing_reference = 0U, rx_ready = 0U, rx_completed_before = 0U;
        std::uint32_t rx_pending_before = 0U;
        std::uint32_t twi_proof[20]{};
    } fault;

    /** @brief SDK가 정의한 공유 serial block 주소만 조회합니다. */
    NRF_UARTE_Type *serialRegisters(unsigned instance)
    {
        switch (instance)
        {
        case 0U:
            return NRF_UARTE00;
        case 20U:
            return NRF_UARTE20;
        case 21U:
            return NRF_UARTE21;
        case 22U:
            return NRF_UARTE22;
        case 30U:
            return NRF_UARTE30;
        default:
            return nullptr;
        }
    }

    /** @brief 실제 SPI DMA·semaphore·CS 수준을 읽기만 하며 다음 전송 전에 보존합니다. */
    void spiBoundaryRegisters(std::uint32_t *out)
    {
        const auto &lane = lanes[0];
        const bool target = lane.endpoint.kind == Kind::spis;
        out[0] = spi_boundary_policy;
        out[1] = static_cast<std::uint32_t>(lane.endpoint.kind);
        out[2] = lane.endpoint.instance;
        const auto *common = serialRegisters(lane.endpoint.instance);
        out[3] = common->ENABLE;
        if (target)
        {
            const auto *reg = reinterpret_cast<const NRF_SPIS_Type *>(common);
            out[4] = reg->ORC;
            out[5] = reg->DEF;
            out[6] = reg->DMA.TX.MAXCNT;
            out[7] = reg->DMA.RX.MAXCNT;
            out[8] = reg->DMA.TX.PTR;
            out[9] = reg->DMA.RX.PTR;
            out[10] = nrf_spis_sck_pin_get(reg);
            out[11] = nrf_spis_mosi_pin_get(reg);
            out[12] = nrf_spis_miso_pin_get(reg);
            out[13] = nrf_spis_csn_pin_get(reg);
            out[14] = nrf_spis_status_get(reg);
            out[15] = nrf_spis_semaphore_status_get(reg);
            spi_boundary.raw[11] = nrf_spis_tx_amount_get(reg);
            spi_boundary.raw[12] = nrf_spis_rx_amount_get(reg);
        }
        else
        {
            const auto *reg = reinterpret_cast<const NRF_SPIM_Type *>(common);
            out[4] = reg->ORC;
            out[5] = UINT32_MAX;
            out[6] = nrf_spim_tx_maxcnt_get(reg);
            out[7] = nrf_spim_rx_maxcnt_get(reg);
            out[8] = reg->DMA.TX.PTR;
            out[9] = reg->DMA.RX.PTR;
            out[10] = nrf_spim_sck_pin_get(reg);
            out[11] = nrf_spim_mosi_pin_get(reg);
            out[12] = nrf_spim_miso_pin_get(reg);
            out[13] = nrf_spim_csn_pin_get(reg);
            out[14] = out[15] = UINT32_MAX;
            spi_boundary.raw[11] = nrf_spim_tx_amount_get(reg);
            spi_boundary.raw[12] = nrf_spim_rx_amount_get(reg);
        }
        out[16] = out[13] < 96U ? nrf_gpio_pin_read(out[13]) : UINT32_MAX;
        out[17] = 1U;
        for (unsigned slot = 0U; slot < 2U; ++slot)
        {
            out[17] &= lane.tx[slot].guards(1024U) && lane.rx[slot].guards(1024U) ? 1U : 0U;
        }
        out[18] = k_cycle_get_32();
        out[19] = CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC;
    }

    /** @brief 비정상 frame을 정상 complete 경로로 보내지 않고 최초 event·DMA를 별도로 보존합니다. */
    bool spiBoundaryEvent(const SpiFabricEvent &event)
    {
        if (!spi_boundary.prepared || spi_boundary.raw[2] != 1U ||
            event.type == SpiFabricEventType::buffers_armed ||
            event.type == SpiFabricEventType::buffer_needed)
        {
            return false;
        }
        auto &raw = spi_boundary.raw;
        if (raw[4] == 0U)
        {
            raw[4] = 1U;
            raw[5] = static_cast<std::uint32_t>(event.type);
            raw[6] = event.tx_transferred;
            raw[7] = event.rx_transferred;
            raw[8] = (event.tx_buffer == lanes[0].tx[0].data() ? 1U : 0U) |
                     (event.rx_buffer == lanes[0].rx[0].data() ? 2U : 0U);
            raw[15] = k_cycle_get_32();
            spiBoundaryRegisters(spi_boundary.after);
            raw[9] = spi_boundary.after[17];
            raw[13] = spi_boundary.after[14];
            raw[14] = spi_boundary.after[15];
        }
        return true;
    }

    /** @brief 정상 frame 판정 전에 첫 오류·취소 event의 길이와 DMA 주소·가드를 보존합니다. */
    void recordFault(Lane &lane, std::uint32_t event, const void *tx, std::size_t tx_amount,
                     const void *rx, std::size_t rx_amount, std::uint32_t error,
                     std::uint32_t address = 0U)
    {
        if (fault.triggered == 0U || &lane != &lanes[0])
        {
            return;
        }
        ++fault.events;
        if (fault.event != UINT32_MAX)
        {
            return;
        }
        fault.event = event;
        fault.tx_amount = static_cast<std::uint32_t>(tx_amount);
        fault.rx_amount = static_cast<std::uint32_t>(rx_amount);
        fault.pointers = (tx == lane.tx[0].data() ? 1U : 0U) | (rx == lane.rx[0].data() ? 2U : 0U);
        fault.guards = 1U;
        for (unsigned slot = 0U; slot < 2U; ++slot)
        {
            fault.guards &= lane.tx[slot].guards(lane.endpoint.length) &&
                                    lane.rx[slot].guards(lane.endpoint.length)
                                ? 1U
                                : 0U;
        }
        fault.error = error;
        fault.address = address;
        fault.event_cycle = k_cycle_get_32();
        /** @brief 오류 event의 descriptor 길이를 실제 전송량으로 바꾸어 기록하지 않습니다. */
        if (lane.endpoint.kind == Kind::spim)
        {
            const auto *registers =
                reinterpret_cast<NRF_SPIM_Type *>(serialRegisters(lane.endpoint.instance));
            fault.hardware_tx = nrf_spim_tx_amount_get(registers);
            fault.hardware_rx = nrf_spim_rx_amount_get(registers);
        }
        else if (lane.endpoint.kind == Kind::twim)
        {
            const auto *registers =
                reinterpret_cast<NRF_TWIM_Type *>(serialRegisters(lane.endpoint.instance));
            fault.hardware_tx = nrf_twim_txd_amount_get(registers);
            fault.hardware_rx = nrf_twim_rxd_amount_get(registers);
            if (fault.mode == 4U)
            {
                auto &proof = fault.twi_proof;
                proof[8] = nrf_twim_event_check(registers, NRF_TWIM_EVENT_RXSTARTED) ? 1U : 0U;
                proof[9] = nrf_twim_event_check(registers, NRF_TWIM_EVENT_ENDRX) ? 1U : 0U;
                proof[10] = 1U;
                for (unsigned byte = 0U; byte < lane.endpoint.length; ++byte)
                {
                    proof[10] &= lane.rx[0].data()[byte] == 0xCCU ? 1U : 0U;
                }
                proof[12] = fault.submitted_cycle;
                proof[13] = fault.requested_cycle;
                proof[14] = fault.event_cycle;
                proof[15] = fault.hardware_tx;
                proof[16] = fault.hardware_rx;
                proof[19] = fault.events;
            }
        }
        else
        {
            fault.hardware_tx = fault.tx_amount;
            fault.hardware_rx = fault.rx_amount;
        }
    }

    /** @brief 첫 실패를 보존하며 후속 성공으로 덮지 않습니다. */
    bool failure(Lane &lane, std::uint32_t code, std::uint32_t detail = 0U)
    {
        if (lane.error == 0U)
        {
            lane.error = code;
            lane.driver_error = detail;
        }
        return false;
    }

    bool accepted(Lane &lane, SerialFabricResult result, std::uint32_t code)
    {
        return result == SerialFabricResult::success ||
               failure(lane, code, static_cast<std::uint32_t>(result));
    }

    /** @brief 소유권이 반환된 slot만 새로운 전역 위치의 데이터로 채웁니다. */
    bool fillTx(Lane &lane, unsigned slot, std::uint32_t frame)
    {
        if (lane.tx_pending[slot] || !lane.tx[slot].initialize(lane.endpoint.length))
        {
            return failure(lane, 1U);
        }
        for (unsigned byte = 0U; byte < lane.endpoint.length; ++byte)
        {
            if (byte % 64U == 0U)
            {
                captureService();
            }
            lane.tx[slot].data()[byte] = pattern(lane.seed_tx, frame * lane.endpoint.length + byte);
        }
        return true;
    }

    bool resetRx(Lane &lane, unsigned slot)
    {
        if (lane.rx_pending[slot] || !lane.rx[slot].initialize(lane.endpoint.length))
        {
            return failure(lane, 2U);
        }
        return true;
    }

    /** @brief 기대 slot·길이·가드·모든 byte를 검증한 실제 완료만 누적합니다. */
    bool complete(Lane &lane, const void *address, std::size_t amount, bool receive)
    {
        const auto observed_cycle = k_cycle_get_32();
        auto &direction = receive ? lane.received : lane.sent;
        const unsigned slot = direction.completed % 2U;
        auto &buffer = receive ? lane.rx[slot] : lane.tx[slot];
        auto &pending = receive ? lane.rx_pending[slot] : lane.tx_pending[slot];
        if (!pending || address != buffer.data() || amount != lane.endpoint.length)
        {
            return failure(lane, receive ? 3U : 4U, static_cast<std::uint32_t>(amount));
        }
        if (!buffer.guards(lane.endpoint.length))
        {
            return failure(lane, 5U);
        }
        const auto seed = receive ? lane.seed_rx : lane.seed_tx;
        for (unsigned byte = 0U; byte < amount; ++byte)
        {
            if (byte % 64U == 0U)
            {
                captureService();
            }
            const auto expected = pattern(seed, static_cast<std::uint32_t>(direction.bytes) + byte);
            if (buffer.data()[byte] != expected)
            {
                if (lane.data_fault[0] == 0U)
                {
                    /** @brief 자동 STOP 전에 첫 불일치와 앞뒤 원본을 보존하고 덮어쓰지 않습니다. */
                    auto &raw = lane.data_fault;
                    raw[0] = 1U;
                    raw[1] = static_cast<std::uint32_t>(lane.endpoint.kind);
                    raw[2] = lane.endpoint.instance;
                    raw[3] = receive ? 1U : 0U;
                    raw[4] = slot;
                    raw[5] = byte;
                    raw[6] = buffer.data()[byte];
                    raw[7] = expected;
                    raw[8] = seed;
                    raw[9] = direction.completed;
                    raw[10] = static_cast<std::uint32_t>(direction.bytes);
                    raw[11] = static_cast<std::uint32_t>(direction.bytes >> 32U);
                    raw[12] = reinterpret_cast<std::uintptr_t>(address);
                    raw[13] = static_cast<std::uint32_t>(amount);
                    raw[14] = buffer.guards(lane.endpoint.length) ? 1U : 0U;
                    raw[15] = observed_cycle;
                    for (unsigned offset = 0U; offset < 4U; ++offset)
                    {
                        const auto before = byte >= 4U ? byte - 4U + offset : offset;
                        const auto after = byte + offset;
                        for (unsigned side = 0U; side < 2U; ++side)
                        {
                            const auto position = side == 0U ? before : after;
                            if (position < amount)
                            {
                                raw[16U + side] |= std::uint32_t(buffer.data()[position])
                                                   << (offset * 8U);
                                raw[18U + side] |=
                                    std::uint32_t(
                                        pattern(seed, static_cast<std::uint32_t>(direction.bytes) +
                                                          position))
                                    << (offset * 8U);
                            }
                        }
                    }
                }
                return failure(lane, receive ? 6U : 7U, byte);
            }
            direction.hash = hashByte(direction.hash, buffer.data()[byte]);
        }
        direction.first_word = 0U;
        direction.last_word = 0U;
        for (unsigned byte = 0U; byte < 4U; ++byte)
        {
            direction.first_word |= std::uint32_t(buffer.data()[byte]) << (8U * byte);
            direction.last_word |= std::uint32_t(buffer.data()[amount - 4U + byte]) << (8U * byte);
        }
        direction.bytes += amount;
        lane.timing[receive ? 1U : 0U].add(k_cyc_to_us_floor32(
            observed_cycle - (receive ? lane.submitted_rx[slot] : lane.submitted_tx[slot])));
        const auto now = static_cast<std::uint64_t>(k_uptime_get());
        if (direction.last_completion_ms != 0U &&
            now - direction.last_completion_ms > direction.max_completion_gap_ms)
        {
            direction.max_completion_gap_ms =
                static_cast<std::uint32_t>(now - direction.last_completion_ms);
        }
        direction.last_completion_ms = now;
        ++direction.completed;
        pending = false;
        return true;
    }

    /** @brief 정확히 두 버퍼가 모두 반환된 경우에만 다음 묶음을 등록합니다. */
    bool queuePair(Lane &lane)
    {
        const auto kind = lane.endpoint.kind;
        const auto length = lane.endpoint.length;
        if (spi_boundary.prepared && kind == Kind::spis)
        {
            if (spi_boundary.raw[3] != 0U)
            {
                return true;
            }
            if (!resetRx(lane, 0U) || !fillTx(lane, 0U, 0U))
            {
                return false;
            }
            if (spi_boundary_policy == 2U)
            {
                const auto result =
                    static_cast<SpisHandle *>(lane.handle)
                        ->queueBuffers(lane.tx[0].data(), 512U, lane.rx[0].data(), 512U);
                if (!accepted(lane, result, 83U))
                {
                    return false;
                }
                lane.tx_pending[0] = lane.rx_pending[0] = true;
            }
            spi_boundary.raw[3] = spi_boundary_policy == 2U ? 1U : 2U;
            return true;
        }
        if (lane.rx_pending[0] || lane.rx_pending[1] ||
            (kind != Kind::uart && (lane.tx_pending[0] || lane.tx_pending[1])))
        {
            return true;
        }
        if (kind == Kind::uart && rxDelayHold(lane))
        {
            return true;
        }
        const auto started = k_cycle_get_32();
        for (unsigned slot = 0U; slot < 2U; ++slot)
        {
            if (!resetRx(lane, slot) ||
                (kind != Kind::uart && !fillTx(lane, slot, lane.queued_tx + slot)))
            {
                return false;
            }
        }
        SerialFabricResult result = SerialFabricResult::wrong_state;
        if (kind == Kind::uart)
        {
            result = static_cast<UarteHandle *>(lane.handle)
                         ->receiveAsync(lane.rx[0].data(), length, lane.rx[1].data(), length);
            if (rx_delay.prepared && rx_delay_policy == 1U && rx_delay.raw[3] == 1U)
            {
                rx_delay.raw[6] = k_cycle_get_32();
                rx_delay.raw[11] = static_cast<std::uint32_t>(result);
                rx_delay.raw[14] = rxDelayGuards(lane) ? 1U : 0U;
                rx_delay.raw[3] = 2U;
            }
        }
        else if (kind == Kind::spis)
        {
            result = static_cast<SpisHandle *>(lane.handle)
                         ->queueBuffers(lane.tx[0].data(), length, lane.rx[0].data(), length,
                                        lane.tx[1].data(), length, lane.rx[1].data(), length);
        }
        else if (kind == Kind::twis)
        {
            result = static_cast<TwisHandle *>(lane.handle)
                         ->queueBuffers(lane.tx[0].data(), length, lane.rx[0].data(), length,
                                        lane.tx[1].data(), length, lane.rx[1].data(), length);
        }
        if (!accepted(lane, result, 8U))
        {
            return false;
        }
        lane.rx_pending[0] = lane.rx_pending[1] = true;
        lane.submitted_rx[0] = lane.submitted_rx[1] = started;
        lane.queued_rx += 2U;
        if (kind != Kind::uart)
        {
            lane.tx_pending[0] = lane.tx_pending[1] = true;
            lane.submitted_tx[0] = lane.submitted_tx[1] = started;
            lane.queued_tx += 2U;
        }
        const auto elapsed = k_cyc_to_us_floor32(k_cycle_get_32() - started);
        lane.timing[2].add(elapsed);
        captureService();
        if (elapsed > lane.max_queue_us)
        {
            lane.max_queue_us = elapsed;
        }
        return true;
    }

    bool configure(Lane &lane)
    {
        const auto &endpoint = lane.endpoint;
        SerialFabricResult result = SerialFabricResult::wrong_state;
        switch (endpoint.kind)
        {
        case Kind::uart:
        {
            auto *handle = serialFabric().uarte(endpoint.instance);
            lane.handle = handle;
            if (handle != nullptr)
            {
                result = handle->configure(
                    {endpoint.rate, uartFaultParity(), endpoint.pin_count == 4U, true});
            }
            break;
        }
        case Kind::spim:
        {
            auto *handle = serialFabric().spim(endpoint.instance);
            lane.handle = handle;
            if (handle != nullptr)
            {
                result = handle->configure({endpoint.rate});
            }
            break;
        }
        case Kind::spis:
        {
            auto *handle = serialFabric().spis(endpoint.instance);
            lane.handle = handle;
            if (handle != nullptr)
            {
                result = handle->configure({endpoint.rate});
            }
            break;
        }
        case Kind::twim:
        {
            auto *handle = serialFabric().twim(endpoint.instance);
            lane.handle = handle;
            if (handle != nullptr)
            {
                result = handle->configure({static_cast<TwiFabricFrequency>(endpoint.rate)});
            }
            break;
        }
        case Kind::twis:
        {
            auto *handle = serialFabric().twis(endpoint.instance);
            lane.handle = handle;
            if (handle != nullptr)
            {
                result = handle->configure({0x42U, 0U, true});
            }
            break;
        }
        default:
            return failure(lane, 9U);
        }
        if (!accepted(lane, result, 10U))
        {
            return false;
        }
        for (unsigned index = 0U; index < endpoint.pin_count; ++index)
        {
            lane.pins[index] = {static_cast<SerialSignal>(endpoint.signals[index]),
                                static_cast<pin_size_t>(pinId(endpoint.pins[index]))};
        }
        for (unsigned slot = 0U; slot < 2U; ++slot)
        {
            if (!lane.tx[slot].initialize(endpoint.length) ||
                !lane.rx[slot].initialize(endpoint.length))
            {
                return failure(lane, 11U);
            }
            lane.workspaces[slot * 2U] = {lane.tx[slot].data(), endpoint.length};
            lane.workspaces[slot * 2U + 1U] = {lane.rx[slot].data(), endpoint.length};
        }
        const SerialFabricConfiguration config{
            static_cast<SerialRouteClass>(endpoint.bank),
            static_cast<SerialElectricalProfile>(endpoint.profile),
            lane.pins,
            endpoint.pin_count,
            lane.workspaces,
            4U};
        if (!accepted(lane, lane.handle->stage(config), 12U) ||
            !accepted(lane, lane.handle->activate(), 13U))
        {
            return false;
        }
        lane.active = true;
        /** @brief 양쪽 TX idle 설정을 마친 뒤 START에서 RX를 켜야 준비 중 break를 받지 않습니다. */
        return true;
    }

    /** @brief API 완료 event를 모두 소진하며 예상하지 않은 취소·오류는 실패로 고정합니다. */
    void poll(Lane &lane)
    {
        const auto kind = lane.endpoint.kind;
        if (kind == Kind::uart)
        {
            UarteEvent event{};
            while (static_cast<UarteHandle *>(lane.handle)->takeEvent(event))
            {
                if (event.type == UarteEventType::error)
                {
                    const bool guards = lane.tx[0].guards(lane.endpoint.length) &&
                                        lane.tx[1].guards(lane.endpoint.length) &&
                                        lane.rx[0].guards(lane.endpoint.length) &&
                                        lane.rx[1].guards(lane.endpoint.length);
                    uartFaultEvent(event, guards);
                }
                if (event.type == UarteEventType::tx_cancelled ||
                    event.type == UarteEventType::rx_cancelled ||
                    event.type == UarteEventType::error)
                {
                    const bool receive = event.type != UarteEventType::tx_cancelled;
                    recordFault(lane, static_cast<std::uint32_t>(event.type),
                                receive ? nullptr : event.buffer, receive ? 0U : event.transferred,
                                receive ? event.buffer : nullptr, receive ? event.transferred : 0U,
                                event.error_mask);
                }
                if (event.type == UarteEventType::tx_complete)
                {
                    complete(lane, event.buffer, event.transferred, false);
                }
                else if (event.type == UarteEventType::rx_complete)
                {
                    complete(lane, event.buffer, event.transferred, true);
                }
                else if (event.type == UarteEventType::rx_buffer_needed)
                {
                    ++lane.requests;
                }
                else
                {
                    failure(lane, 20U + static_cast<std::uint32_t>(event.type), event.error_mask);
                }
            }
        }
        else if (kind == Kind::spim || kind == Kind::spis)
        {
            SpiFabricEvent event{};
            while (kind == Kind::spim ? static_cast<SpimHandle *>(lane.handle)->takeEvent(event)
                                      : static_cast<SpisHandle *>(lane.handle)->takeEvent(event))
            {
                if (spiBoundaryEvent(event))
                {
                    failure(lane, 82U, static_cast<std::uint32_t>(event.type));
                    continue;
                }
                if (event.type != SpiFabricEventType::buffers_armed &&
                    event.type != SpiFabricEventType::buffer_needed)
                {
                    recordFault(lane, static_cast<std::uint32_t>(event.type), event.tx_buffer,
                                event.tx_transferred, event.rx_buffer, event.rx_transferred,
                                event.error_code);
                }
                if (event.type == SpiFabricEventType::transfer_complete)
                {
                    complete(lane, event.tx_buffer, event.tx_transferred, false);
                    complete(lane, event.rx_buffer, event.rx_transferred, true);
                }
                else if (event.type == SpiFabricEventType::buffer_needed)
                {
                    ++lane.requests;
                }
                else if (event.type != SpiFabricEventType::buffers_armed)
                {
                    failure(lane, 30U + static_cast<std::uint32_t>(event.type), event.error_code);
                }
            }
        }
        else
        {
            TwiFabricEvent event{};
            while (kind == Kind::twim ? static_cast<TwimHandle *>(lane.handle)->takeEvent(event)
                                      : static_cast<TwisHandle *>(lane.handle)->takeEvent(event))
            {
                if (kind == Kind::twim)
                {
                    recordFault(lane, static_cast<std::uint32_t>(event.type), event.tx_buffer,
                                event.tx_transferred, event.rx_buffer, event.rx_transferred,
                                event.error_code, event.address);
                }
                if (event.type == TwiFabricEventType::transfer_complete ||
                    event.type == TwiFabricEventType::read_complete)
                {
                    complete(lane, event.tx_buffer, event.tx_transferred, false);
                }
                if (event.type == TwiFabricEventType::transfer_complete ||
                    event.type == TwiFabricEventType::write_complete)
                {
                    complete(lane, event.rx_buffer, event.rx_transferred, true);
                }
                if (event.type == TwiFabricEventType::buffer_needed)
                {
                    ++lane.requests;
                }
                if (event.type != TwiFabricEventType::transfer_complete &&
                    event.type != TwiFabricEventType::read_complete &&
                    event.type != TwiFabricEventType::write_complete &&
                    event.type != TwiFabricEventType::read_request &&
                    event.type != TwiFabricEventType::write_request &&
                    event.type != TwiFabricEventType::buffer_needed)
                {
                    failure(lane, 40U + static_cast<std::uint32_t>(event.type), event.error_code);
                }
            }
        }
    }

    /** @brief 전송 중 재시도 없이 고정 간격의 다음 frame을 제출합니다. */
    void submit(Lane &lane, std::uint64_t now)
    {
        const auto kind = lane.endpoint.kind;
        if (!transmitting || now < lane.next_frame || lane.tx_pending[0] || lane.tx_pending[1] ||
            (kind == Kind::uart && !uartFaultTransmitAllowed()) ||
            (kind != Kind::uart && kind != Kind::spim && kind != Kind::twim))
        {
            return;
        }
        const auto slot = lane.queued_tx % 2U;
        const auto length = lane.endpoint.length;
        if (!fillTx(lane, slot, lane.queued_tx) || (kind != Kind::uart && !resetRx(lane, slot)))
        {
            return;
        }
        const auto submitted = k_cycle_get_32();
        SerialFabricResult result = SerialFabricResult::wrong_state;
        if (kind == Kind::uart)
        {
            result = static_cast<UarteHandle *>(lane.handle)
                         ->transmitAsync(lane.tx[slot].data(), length);
        }
        else if (kind == Kind::spim)
        {
            result =
                static_cast<SpimHandle *>(lane.handle)
                    ->transferAsync(lane.tx[slot].data(), length, lane.rx[slot].data(), length);
        }
        else
        {
            if (fault.mode == 4U && fault.triggered == 0U && &lane == &lanes[0])
            {
                /** @brief 비활성 DMA의 이전 AMOUNT와 새 RX 시작 근거를 전송 전에 분리합니다. */
                auto *registers =
                    reinterpret_cast<NRF_TWIM_Type *>(serialRegisters(lane.endpoint.instance));
                auto &proof = fault.twi_proof;
                proof[0] = fault.mode;
                proof[1] = 1U;
                proof[2] = nrf_twim_txd_amount_get(registers);
                proof[3] = nrf_twim_rxd_amount_get(registers);
                nrf_twim_event_clear(registers, NRF_TWIM_EVENT_RXSTARTED);
                nrf_twim_event_clear(registers, NRF_TWIM_EVENT_ENDRX);
                proof[4] = nrf_twim_event_check(registers, NRF_TWIM_EVENT_RXSTARTED) ? 1U : 0U;
                proof[5] = nrf_twim_event_check(registers, NRF_TWIM_EVENT_ENDRX) ? 1U : 0U;
                proof[11] = slot;
                proof[17] = length;
                proof[18] = registers->ENABLE;
            }
            result = static_cast<TwimHandle *>(lane.handle)
                         ->transferAsync(fault.mode == 5U ? 0x44U : 0x42U, lane.tx[slot].data(),
                                         length, fault.mode == 5U ? nullptr : lane.rx[slot].data(),
                                         fault.mode == 5U ? 0U : length);
        }
        if (accepted(lane, result, 60U))
        {
            if (spi_boundary.prepared && kind == Kind::spim)
            {
                spi_boundary.raw[3] = 1U;
                spi_boundary.raw[17] = submitted;
                transmitting = false;
            }
            if (kind == Kind::uart)
            {
                uartFaultSubmitted(submitted);
            }
            const auto elapsed = k_cyc_to_us_floor32(k_cycle_get_32() - submitted);
            lane.timing[2].add(elapsed);
            lane.max_queue_us = elapsed > lane.max_queue_us ? elapsed : lane.max_queue_us;
            captureService();
            lane.tx_pending[slot] = true;
            lane.submitted_tx[slot] = submitted;
            ++lane.queued_tx;
            if (kind != Kind::uart)
            {
                lane.rx_pending[slot] = true;
                lane.submitted_rx[slot] = submitted;
                ++lane.queued_rx;
            }
            lane.next_frame = now + frame_period_ms;
            if (fault.mode != 0U && fault.mode != 2U && fault.triggered == 0U && &lane == &lanes[0])
            {
                fault.triggered = 1U;
                fault.submitted_cycle = submitted;
                transmitting = false;
                if (fault.mode != 5U)
                {
                    /** @brief 완료 전에 취소를 요청하되 실제 부분 길이는 event로 별도 증명합니다. */
                    k_busy_wait(50U);
                }
                fault.requested_cycle = k_cycle_get_32();
                SerialFabricResult cancelled = SerialFabricResult::success;
                switch (fault.mode)
                {
                case 1U:
                    cancelled = static_cast<UarteHandle *>(lane.handle)->cancelTransmit();
                    break;
                case 3U:
                    cancelled = static_cast<SpimHandle *>(lane.handle)->cancelTransfer();
                    break;
                case 4U:
                {
                    /** @brief 취소 직전과 terminal event의 RX 시작 상태를 각각 보존합니다. */
                    const auto *registers =
                        reinterpret_cast<NRF_TWIM_Type *>(serialRegisters(lane.endpoint.instance));
                    fault.twi_proof[6] =
                        nrf_twim_event_check(registers, NRF_TWIM_EVENT_RXSTARTED) ? 1U : 0U;
                    fault.twi_proof[7] =
                        nrf_twim_event_check(registers, NRF_TWIM_EVENT_ENDRX) ? 1U : 0U;
                    cancelled = static_cast<TwimHandle *>(lane.handle)->cancelTransfer();
                    break;
                }
                default:
                    break;
                }
                fault.result = static_cast<std::uint32_t>(cancelled);
                accepted(lane, cancelled, 72U);
            }
        }
    }

    /** @brief 첫 RX 바이트가 실제 도착한 뒤 취소하여 자기 TX와 상대 RX의 시작 편차를 배제합니다. */
    void cancelAfterReceive(Lane &lane)
    {
        if (fault.mode != 2U || fault.triggered != 0U || &lane != &lanes[0] || !receivers_armed ||
            lane.endpoint.kind != Kind::uart)
        {
            return;
        }
        const auto *registers = serialRegisters(lane.endpoint.instance);
        if (!nrf_uarte_event_check(registers, NRF_UARTE_EVENT_RXDRDY))
        {
            return;
        }
        fault.submitted_cycle = k_cycle_get_32();
        fault.timing_reference = 1U;
        fault.rx_ready = 1U;
        fault.rx_completed_before = lane.received.completed;
        fault.rx_pending_before = lane.rx_pending[0] ? 1U : 0U;
        fault.triggered = 1U;
        transmitting = false;
        /** @brief RXDRDY는 RAM 저장 완료가 아니므로 실제 부분량은 취소 terminal event로 판정합니다. */
        k_busy_wait(50U);
        fault.requested_cycle = k_cycle_get_32();
        const auto cancelled = static_cast<UarteHandle *>(lane.handle)->cancelReceive();
        fault.result = static_cast<std::uint32_t>(cancelled);
        accepted(lane, cancelled, 72U);
    }
} // namespace

bool t13::serialPrepare(const Case &test, std::uint32_t seed)
{
    if (lane_count != 0U || test.serial_count > max_lanes)
    {
        return false;
    }
    transmitting = false;
    receivers_armed = false;
    fault = {};
    spi_boundary = {};
    rx_delay = {};
    lane_count = test.serial_count;
    for (auto &lane : lanes)
    {
        lane = {};
    }
    for (unsigned index = 0U; index < lane_count; ++index)
    {
        auto &lane = lanes[index];
        lane.endpoint = test.serial[role - 1U][index];
        lane.seed_tx = laneSeed(seed, index, role);
        lane.seed_rx = laneSeed(seed, index, 3U - role);
        if (rx_delay_policy != 0U)
        {
            if (test.id < 2U || test.id > 5U || test.serial_count != 1U || test.harness != 2U ||
                lane.endpoint.kind != Kind::uart || lane.endpoint.pin_count != 4U ||
                lane.endpoint.rate != 1000000U || lane.endpoint.length != 1024U)
            {
                return false;
            }
            unsigned count = 0U;
            for (unsigned pin = 0U; pin < 4U; ++pin)
            {
                const auto signal = static_cast<SerialSignal>(lane.endpoint.signals[pin]);
                if (signal == SerialSignal::txd || signal == SerialSignal::rxd)
                {
                    lane.endpoint.pins[count] = lane.endpoint.pins[pin];
                    lane.endpoint.signals[count++] = lane.endpoint.signals[pin];
                }
            }
            lane.endpoint.pin_count = count;
            if (count != 2U)
            {
                return false;
            }
            rx_delay.prepared = true;
            rx_delay.raw[0] = rx_delay_policy;
            rx_delay.raw[1] = lane.endpoint.instance;
            rx_delay.raw[11] = UINT32_MAX;
            rx_delay.raw[18] = CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC;
        }
        if (!flowPrepare(test, lane.endpoint) || !uartFaultPrepare(test, lane.endpoint) ||
            !configure(lane))
        {
            return false;
        }
        if (spi_boundary_policy != 0U)
        {
            const bool controller = spi_boundary_policy == 1U || spi_boundary_policy == 3U;
            if (test.serial_count != 1U || test.harness != 2U || test.adc_channels ||
                test.pwm_instance || test.pdm_instance || test.i2s ||
                lane.endpoint.length != 1024U || lane.endpoint.rate != 8000000U ||
                lane.endpoint.kind != (controller ? Kind::spim : Kind::spis))
            {
                return false;
            }
            spi_boundary.prepared = true;
            spi_boundary.raw[0] = spi_boundary_policy;
            spi_boundary.raw[1] = lane.endpoint.instance;
            spi_boundary.raw[5] = UINT32_MAX;
            spi_boundary.raw[18] = CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC;
        }
    }
    return true;
}

bool t13::serialStart()
{
    if (!serialHealthy())
    {
        return false;
    }
    for (unsigned index = 0U; index < lane_count; ++index)
    {
        auto &lane = lanes[index];
        if ((lane.endpoint.kind == Kind::uart || lane.endpoint.kind == Kind::spis ||
             lane.endpoint.kind == Kind::twis) &&
            !queuePair(lane))
        {
            return false;
        }
        lanes[index].next_frame = static_cast<std::uint64_t>(k_uptime_get()) + 100U;
    }
    receivers_armed = true;
    transmitting = true;
    return true;
}

void t13::serialService()
{
    for (unsigned index = 0U; index < lane_count; ++index)
    {
        auto &lane = lanes[index];
        if (!lane.active || lane.error != 0U)
        {
            continue;
        }
        poll(lane);
        flowService(lane.endpoint, lane.sent.completed, lane.tx_pending[0] || lane.tx_pending[1]);
        flowBackground(index, lane.endpoint, lane.sent.completed, lane.received.completed);
        captureService();
        if (lane.error != 0U)
        {
            continue;
        }
        if (receivers_armed &&
            (lane.endpoint.kind == Kind::uart || lane.endpoint.kind == Kind::spis ||
             lane.endpoint.kind == Kind::twis))
        {
            queuePair(lane);
        }
        if (lane.error == 0U)
        {
            cancelAfterReceive(lane);
            submit(lane, k_uptime_get());
        }
    }
}

void t13::serialQuiesce()
{
    transmitting = false;
}

bool t13::serialHealthy()
{
    for (unsigned index = 0U; index < lane_count; ++index)
    {
        if (lanes[index].error != 0U)
        {
            return false;
        }
    }
    return true;
}

bool t13::serialDrained()
{
    if (transmitting)
    {
        return false;
    }
    for (unsigned index = 0U; index < lane_count; ++index)
    {
        const auto &lane = lanes[index];
        if ((lane.endpoint.kind == Kind::uart || lane.endpoint.kind == Kind::spim ||
             lane.endpoint.kind == Kind::twim) &&
            (lane.tx_pending[0] || lane.tx_pending[1]))
        {
            return false;
        }
    }
    return true;
}

bool t13::serialStop()
{
    transmitting = false;
    receivers_armed = false;
    if (rx_delay.prepared && lane_count == 1U)
    {
        rx_delay.raw[15] = lanes[0].received.completed;
        rx_delay.raw[16] = lanes[0].sent.completed;
        rx_delay.raw[17] = lanes[0].requests;
    }
    if (spi_boundary.prepared && spi_boundary.raw[19] == 0U)
    {
        if (spi_boundary.raw[4] == 0U)
        {
            spiBoundaryRegisters(spi_boundary.after);
            spi_boundary.raw[9] = spi_boundary.after[17];
            spi_boundary.raw[13] = spi_boundary.after[14];
            spi_boundary.raw[14] = spi_boundary.after[15];
        }
        spi_boundary.raw[10] = 1U;
        const unsigned first = spi_boundary_policy == 2U ? 512U : 0U;
        if (spi_boundary_policy == 2U || spi_boundary_policy == 4U)
        {
            for (unsigned byte = first; byte < 1024U; ++byte)
            {
                spi_boundary.raw[10] &= lanes[0].rx[0].data()[byte] == 0xCCU ? 1U : 0U;
            }
        }
    }
    bool stopped = flowStop();
    for (unsigned index = 0U; index < lane_count; ++index)
    {
        auto &lane = lanes[index];
        if (lane.handle != nullptr &&
            lane.handle->deactivate(100000U) != SerialFabricResult::success)
        {
            failure(lane, 70U);
            stopped = false;
            continue;
        }
        lane.active = false;
        for (unsigned slot = 0U; slot < 2U; ++slot)
        {
            if (!lane.tx[slot].guards(lane.endpoint.length) ||
                !lane.rx[slot].guards(lane.endpoint.length))
            {
                failure(lane, 71U);
                stopped = false;
            }
        }
    }
    stopped = uartFaultStop(stopped) && stopped;
    if (stopped)
    {
        if (rx_delay.prepared)
        {
            rx_delay.raw[19] = 1U;
        }
        if (spi_boundary.prepared)
        {
            spi_boundary.raw[19] = 1U;
        }
        lane_count = 0U;
    }
    return stopped;
}

bool t13::serialSpiBoundaryPolicy(unsigned mode)
{
    if (lane_count != 0U || mode > 4U)
    {
        return false;
    }
    spi_boundary_policy = mode;
    return true;
}

bool t13::serialRxDelayPolicy(unsigned mode)
{
    if (lane_count != 0U || mode > 2U)
    {
        return false;
    }
    rx_delay_policy = mode;
    return true;
}

bool t13::serialRxDelayArm()
{
    if (!rx_delay.prepared || lane_count != 1U || rx_delay.raw[2] != 0U || !receivers_armed)
    {
        return false;
    }
    rx_delay.raw[2] = 1U;
    rx_delay.raw[4] = k_cycle_get_32();
    rx_delay.raw[7] = lanes[0].received.completed;
    rx_delay.raw[10] = lanes[0].requests;
    return true;
}

void t13::serialRxDelaySnapshot(std::uint32_t *out, std::uint32_t &count)
{
    if (rx_delay.prepared && lane_count == 1U)
    {
        rx_delay.raw[15] = lanes[0].received.completed;
        rx_delay.raw[16] = lanes[0].sent.completed;
        rx_delay.raw[17] = lanes[0].requests;
    }
    for (unsigned index = 0U; index < 20U; ++index)
    {
        out[index] = rx_delay.raw[index];
    }
    count = 20U;
}

bool t13::serialSpiBoundaryArm()
{
    if (!spi_boundary.prepared || lane_count != 1U || spi_boundary.raw[2] != 0U || receivers_armed)
    {
        return false;
    }
    spi_boundary.raw[2] = 1U;
    spi_boundary.raw[16] = k_cycle_get_32();
    spiBoundaryRegisters(spi_boundary.before);
    spi_boundary.baseline[0] = spi_boundary.raw[11];
    spi_boundary.baseline[1] = spi_boundary.raw[12];
    spi_boundary.baseline[2] = reinterpret_cast<std::uintptr_t>(lanes[0].tx[0].data());
    spi_boundary.baseline[3] = reinterpret_cast<std::uintptr_t>(lanes[0].rx[0].data());
    spi_boundary.baseline[4] = 1024U;
    return true;
}

void t13::serialSpiBoundarySnapshot(unsigned page, std::uint32_t *out, std::uint32_t &count)
{
    if (page > 3U)
    {
        count = 0U;
        return;
    }
    const auto *values = page == 0U   ? spi_boundary.raw
                         : page == 1U ? spi_boundary.before
                         : page == 2U ? spi_boundary.after
                                      : spi_boundary.baseline;
    for (unsigned index = 0U; index < 20U; ++index)
    {
        out[index] = values[index];
    }
    count = 20U;
}

/** @brief 양쪽 STOP 이후에만 첫 DMA slot 전체를 반환하며 재구성 전 원본을 보존합니다. */
void t13::serialSpiBoundaryBuffer(unsigned direction, unsigned page, std::uint32_t *out,
                                  std::uint32_t &count)
{
    if (!spi_boundary.prepared || spi_boundary.raw[19] != 1U || lane_count != 0U ||
        direction > 1U || page >= 16U)
    {
        count = 0U;
        return;
    }
    auto *bytes = direction == 0U ? lanes[0].tx[0].data() : lanes[0].rx[0].data();
    for (unsigned index = 0U; index < 16U; ++index)
    {
        out[index] = 0U;
        for (unsigned byte = 0U; byte < 4U; ++byte)
        {
            out[index] |= std::uint32_t(bytes[page * 64U + index * 4U + byte]) << (byte * 8U);
        }
    }
    count = 16U;
}

bool t13::serialBreakPrepare()
{
    return uartFaultBreakReady() && serialStop() && uartFaultBreakPrepare();
}

void t13::serialSnapshot(unsigned index, std::uint32_t *out, std::uint32_t &count)
{
    if (index >= max_lanes)
    {
        count = 0U;
        return;
    }
    const auto &lane = lanes[index];
    out[0] = lane.error;
    out[1] = lane.driver_error;
    out[2] = lane.active ? 1U : 0U;
    out[3] = lane.max_queue_us;
    out[4] = lane.requests;
    for (unsigned receive = 0U; receive < 2U; ++receive)
    {
        const auto &direction = receive == 0U ? lane.sent : lane.received;
        auto *values = out + 5U + receive * 6U;
        values[0] = direction.completed;
        values[1] = static_cast<std::uint32_t>(direction.bytes);
        values[2] = static_cast<std::uint32_t>(direction.bytes >> 32U);
        values[3] = direction.hash;
        values[4] = direction.first_word;
        values[5] = direction.last_word;
    }
    out[17] = lane.sent.max_completion_gap_ms;
    out[18] = lane.received.max_completion_gap_ms;
    out[19] = static_cast<std::uint32_t>(frame_period_ms);
    count = 20U;
}

void t13::serialTiming(unsigned lane, unsigned metric, std::uint32_t *out, std::uint32_t &count)
{
    if (lane >= max_lanes || metric >= 3U)
    {
        count = 0U;
        return;
    }
    lanes[lane].timing[metric].snapshot(out);
    count = 20U;
}

/** @brief 전송 전 사용·미사용 UART PSEL을 읽어 이전 personality의 핀 선택 잔류를 검출합니다. */
void t13::serialPinSnapshot(unsigned lane, std::uint32_t *out, std::uint32_t &count)
{
    if (lane >= max_lanes || lanes[lane].endpoint.kind != Kind::uart)
    {
        count = 0U;
        return;
    }
    const auto instance = lanes[lane].endpoint.instance;
    const auto *registers = serialRegisters(instance);
    if (registers == nullptr)
    {
        count = 0U;
        return;
    }
    out[0] = instance;
    out[1] = (registers->CONFIG & UARTE_CONFIG_HWFC_Msk) != 0U ? 1U : 0U;
    out[2] = registers->PSEL.TXD;
    out[3] = registers->PSEL.RXD;
    out[4] = registers->PSEL.RTS;
    out[5] = registers->PSEL.CTS;
    out[6] = registers->ENABLE;
    count = 7U;
}

/** @brief 준비된 단독 UART/SPI/TWI에서만 고정 취소 또는 peer 미할당 주소 NACK를 허용합니다. */
bool t13::serialArmFault(std::uint32_t mode)
{
    if (lane_count != 1U || receivers_armed || fault.mode != 0U || !lanes[0].active)
    {
        return false;
    }
    const auto kind = lanes[0].endpoint.kind;
    if (!((mode >= 1U && mode <= 2U && kind == Kind::uart) || (mode == 3U && kind == Kind::spim) ||
          (mode >= 4U && mode <= 5U && kind == Kind::twim)))
    {
        return false;
    }
    fault.mode = mode;
    if (mode == 2U)
    {
        /** @brief 이전 personality·frame의 RXDRDY를 이번 수신 시작으로 재사용하지 않습니다. */
        nrf_uarte_event_clear(serialRegisters(lanes[0].endpoint.instance), NRF_UARTE_EVENT_RXDRDY);
    }
    return true;
}

/** @brief 의도적 오류 raw를 STOP 뒤에도 유지하며 새 PREPARE만 초기화합니다. */
void t13::serialFaultSnapshot(std::uint32_t *out, std::uint32_t &count)
{
    const auto &lane = lanes[0];
    const std::uint32_t values[]{fault.mode,
                                 fault.triggered,
                                 fault.result,
                                 static_cast<std::uint32_t>(lane.endpoint.kind),
                                 lane.endpoint.instance,
                                 fault.event,
                                 fault.tx_amount,
                                 fault.rx_amount,
                                 fault.pointers,
                                 fault.guards,
                                 fault.error,
                                 fault.address,
                                 fault.submitted_cycle,
                                 fault.requested_cycle,
                                 fault.event_cycle,
                                 fault.events,
                                 fault.hardware_tx,
                                 fault.hardware_rx,
                                 lane.error,
                                 CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC};
    for (unsigned index = 0U; index < 20U; ++index)
    {
        out[index] = values[index];
    }
    count = 20U;
}

/** @brief 원래20word 응답을 확장하지 않고 RX 취소 시점의 별도 근거를8word로 보존합니다. */
void t13::serialRxFaultSnapshot(std::uint32_t *out, std::uint32_t &count)
{
    const std::uint32_t values[]{fault.mode,
                                 fault.timing_reference,
                                 fault.rx_ready,
                                 fault.rx_completed_before,
                                 fault.rx_pending_before,
                                 fault.submitted_cycle,
                                 fault.requested_cycle,
                                 fault.event_cycle};
    for (unsigned index = 0U; index < 8U; ++index)
    {
        out[index] = values[index];
    }
    count = 8U;
}

/** @brief 취소한 TWIM의 이전 AMOUNT·새 RX 이벤트·수신 RAM을 해석 없이 반환합니다. */
void t13::serialTwiFaultSnapshot(std::uint32_t *out, std::uint32_t &count)
{
    for (unsigned index = 0U; index < 20U; ++index)
    {
        out[index] = fault.twi_proof[index];
    }
    count = 20U;
}

/** @brief 첫 payload 오류 원본은 STOP 뒤에도 유지하며 PREPARE에서만 초기화합니다. */
void t13::serialDataFaultSnapshot(unsigned lane, std::uint32_t *out, std::uint32_t &count)
{
    count = 0U;
    if (lane >= max_lanes)
    {
        return;
    }
    for (unsigned index = 0U; index < 20U; ++index)
    {
        out[index] = lanes[lane].data_fault[index];
    }
    count = 20U;
}

/** @brief 현재 peer 출력과 충돌하지 않는 후보만 사용하여 API의 원자적 점유 거부를 검사합니다. */
void t13::serialConflict(unsigned mode, std::uint32_t *out, std::uint32_t &count)
{
    count = 0U;
    auto &lane = lanes[0];
    const auto instance = lane.endpoint.instance;
    if (mode < 1U || mode > 3U || lane_count != 1U || !receivers_armed || !transmitting ||
        !lane.active || lane.endpoint.kind != Kind::uart ||
        (instance != 21U && instance != 22U && instance != 30U) ||
        (instance == 30U && mode != 1U) || !serialHealthy())
    {
        return;
    }
    auto pin = [&lane](SerialSignal signal)
    {
        for (unsigned index = 0U; index < lane.endpoint.pin_count; ++index)
        {
            if (lane.pins[index].signal == signal)
            {
                return lane.pins[index].pin;
            }
        }
        return static_cast<pin_size_t>(UINT32_MAX);
    };
    for (unsigned index = 0U; index < 20U; ++index)
    {
        out[index] = UINT32_MAX;
    }
    const auto alternative = mode == 1U ? instance : instance == 21U ? 22U : 21U;
    out[0] = mode;
    out[1] = instance;
    out[2] = alternative;
    out[7] = static_cast<std::uint32_t>(lane.handle->state());
    const auto *registers = serialRegisters(instance);
    out[9] = registers->PSEL.TXD;
    out[11] = registers->PSEL.RXD;
    out[13] = registers->PSEL.RTS;
    out[15] = registers->PSEL.CTS;
    out[17] = registers->ENABLE;
    out[19] = 1U;
    for (unsigned slot = 0U; slot < 2U; ++slot)
    {
        out[19] &=
            lane.tx[slot].guards(lane.endpoint.length) && lane.rx[slot].guards(lane.endpoint.length)
                ? 1U
                : 0U;
    }
    static_cast<void>(conflict_tx.initialize(128U));
    static_cast<void>(conflict_rx.initialize(128U));
    conflict_workspaces[0] = {conflict_tx.data(), 128U};
    conflict_workspaces[1] = mode == 2U ? SerialDmaWorkspace{conflict_tx.data() + 4U, 124U}
                                        : SerialDmaWorkspace{conflict_rx.data(), 128U};
    SerialFabricHandle *candidate = nullptr;
    if (mode == 1U)
    {
        auto *spi = serialFabric().spim(alternative);
        candidate = spi;
        out[3] =
            spi == nullptr ? UINT32_MAX : static_cast<std::uint32_t>(spi->configure({1000000U}));
        conflict_pins[0] = {SerialSignal::sck, pin(SerialSignal::txd)};
        conflict_pins[1] = {SerialSignal::mosi, pin(SerialSignal::rts)};
        conflict_pins[2] = {SerialSignal::miso, pin(SerialSignal::rxd)};
    }
    else
    {
        auto *uart = serialFabric().uarte(alternative);
        candidate = uart;
        out[3] =
            uart == nullptr ? UINT32_MAX : static_cast<std::uint32_t>(uart->configure({1000000U}));
        conflict_pins[0] = {SerialSignal::txd, pin(SerialSignal::txd)};
        conflict_pins[1] = {SerialSignal::rxd, pin(SerialSignal::rxd)};
    }
    const SerialFabricConfiguration config{
        static_cast<SerialRouteClass>(lane.endpoint.bank),
        static_cast<SerialElectricalProfile>(lane.endpoint.profile),
        conflict_pins,
        mode == 1U ? 3U : 2U,
        conflict_workspaces,
        2U};
    if (candidate != nullptr && out[3] == 0U)
    {
        out[4] = static_cast<std::uint32_t>(candidate->stage(config));
        if (out[4] == 0U)
        {
            out[5] = static_cast<std::uint32_t>(candidate->activate());
            if (out[5] == 0U)
            {
                /** @brief 잘못 허용된 후보는 즉시 정지하며 이 동작은 성공으로 인정하지 않습니다. */
                out[6] = static_cast<std::uint32_t>(candidate->deactivate());
            }
        }
    }
    out[8] = static_cast<std::uint32_t>(lane.handle->state());
    out[10] = registers->PSEL.TXD;
    out[12] = registers->PSEL.RXD;
    out[14] = registers->PSEL.RTS;
    out[16] = registers->PSEL.CTS;
    out[18] = registers->ENABLE;
    for (unsigned slot = 0U; slot < 2U; ++slot)
    {
        out[19] &=
            lane.tx[slot].guards(lane.endpoint.length) && lane.rx[slot].guards(lane.endpoint.length)
                ? 1U
                : 0U;
    }
    bool intact = out[3] == 0U && out[4] == 0U && out[5] == (mode == 2U ? 2U : 8U) &&
                  out[6] == UINT32_MAX && out[7] == 3U && out[8] == 3U && out[19] == 1U;
    for (unsigned index = 9U; index < 19U; index += 2U)
    {
        intact &= out[index] == out[index + 1U];
    }
    if (!intact)
    {
        failure(lane, 75U, mode);
    }
    count = 20U;
}

/** @brief SPI/TWI START 전에 실제 PSEL을 읽으며 없는 signal slot은 disconnected로 표시합니다. */
void t13::serialBusPins(unsigned index, std::uint32_t *out, std::uint32_t &count)
{
    count = 0U;
    if (index >= max_lanes)
    {
        return;
    }
    const auto &endpoint = lanes[index].endpoint;
    const auto *address = serialRegisters(endpoint.instance);
    if (address == nullptr)
    {
        return;
    }
    out[0] = static_cast<std::uint32_t>(endpoint.kind);
    out[1] = endpoint.instance;
    out[2] = address->ENABLE;
    for (unsigned slot = 3U; slot < 8U; ++slot)
    {
        out[slot] = UINT32_MAX;
    }
    if (endpoint.kind == Kind::spim)
    {
        const auto *registers = reinterpret_cast<const NRF_SPIM_Type *>(address);
        out[3] = nrf_spim_sck_pin_get(registers);
        out[4] = nrf_spim_mosi_pin_get(registers);
        out[5] = nrf_spim_miso_pin_get(registers);
        out[6] = nrf_spim_csn_pin_get(registers);
        out[7] = nrf_spim_dcx_pin_get(registers);
    }
    else if (endpoint.kind == Kind::spis)
    {
        const auto *registers = reinterpret_cast<const NRF_SPIS_Type *>(address);
        out[3] = nrf_spis_sck_pin_get(registers);
        out[4] = nrf_spis_mosi_pin_get(registers);
        out[5] = nrf_spis_miso_pin_get(registers);
        out[6] = nrf_spis_csn_pin_get(registers);
    }
    else if (endpoint.kind == Kind::twim)
    {
        const auto *registers = reinterpret_cast<const NRF_TWIM_Type *>(address);
        out[3] = nrf_twim_sda_pin_get(registers);
        out[4] = nrf_twim_scl_pin_get(registers);
    }
    else if (endpoint.kind == Kind::twis)
    {
        const auto *registers = reinterpret_cast<const NRF_TWIS_Type *>(address);
        out[3] = nrf_twis_sda_pin_get(registers);
        out[4] = nrf_twis_scl_pin_get(registers);
    }
    else
    {
        return;
    }
    count = 8U;
}
