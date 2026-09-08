/**
 * @file serial.cpp
 * @brief 활성 peripheral을 유지하며 두 DMA slot의 실제 반환과 전역 payload를 검사합니다.
 * @note UART 수신은 두 버퍼 단위로 재공급하며 frame 사이의 20ms 주기를 기록합니다.
 * SPDX-License-Identifier: MIT
 */
#include "engine.h"
#include "measurement.h"
#include <nucode/SerialFabric.h>
#include <zephyr/kernel.h>
#include <hal/nrf_uarte.h>

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
    };

    Lane lanes[max_lanes];
    unsigned lane_count = 0U;
    bool transmitting = false;
    bool receivers_armed = false;

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
        if (lane.rx_pending[0] || lane.rx_pending[1] ||
            (kind != Kind::uart && (lane.tx_pending[0] || lane.tx_pending[1])))
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
                    {endpoint.rate, UarteParity::none, endpoint.pin_count == 4U, true});
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
            result = static_cast<TwimHandle *>(lane.handle)
                         ->transferAsync(0x42U, lane.tx[slot].data(), length, lane.rx[slot].data(),
                                         length);
        }
        if (accepted(lane, result, 60U))
        {
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
        }
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
        if (!configure(lane))
        {
            return false;
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
    bool stopped = true;
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
    if (stopped)
    {
        lane_count = 0U;
    }
    return stopped;
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
    NRF_UARTE_Type *registers = nullptr;
    switch (instance)
    {
    case 0U:
        registers = NRF_UARTE00;
        break;
    case 20U:
        registers = NRF_UARTE20;
        break;
    case 21U:
        registers = NRF_UARTE21;
        break;
    case 22U:
        registers = NRF_UARTE22;
        break;
    case 30U:
        registers = NRF_UARTE30;
        break;
    default:
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
