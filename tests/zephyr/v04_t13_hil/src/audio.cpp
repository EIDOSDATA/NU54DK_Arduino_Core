/** @file @brief 양방향 I2S 3-slot DMA의 모든 반환 word를 전역 위치로 대조합니다. */
#include "stream_types.h"
#include "i2s_stream_oracle.h"
#include <nucode/EventFabric.h>
#include <nucode/StreamFabric.h>
#include <variant.h>
#include <hal/nrf_dppi.h>
#include <hal/nrf_gpio.h>
#include <hal/nrf_gpiote.h>
#include <hal/nrf_i2s.h>
#include <hal/nrf_timer.h>

namespace
{
    using namespace nucode::arduino;
    using namespace t13;
    constexpr unsigned role = CONFIG_NUCODE_V04_HIL_ROLE;
    auto &stats = stream_stats[2];
    I2sFabric *audio = nullptr;
    Block<std::uint32_t, 256U> tx[3], rx[3];
    bool pending[3]{};
    std::uint32_t submitted[3]{}, seed_tx = 0U;
    v04::I2sStreamOracle oracle;
    unsigned failed_slot = UINT32_MAX;
    std::uint32_t stop_requests = 0U;
    std::uint32_t first_failure_registers[20]{};

    constexpr std::uint8_t edge_gpiote_channel = 7U;
    constexpr std::uint8_t edge_count_dppi_channel = 14U;
    constexpr std::uint8_t edge_boundary_dppi_channel = 15U;

    /** @brief 실제 SDIN 전이와 I2S DMA 경계를 CPU 지연 없이 대조하는 진단 상태입니다. */
    struct EdgeDiagnostic
    {
        unsigned policy = 0U;
        bool active = false, boundary_ready = false, raw_configured = false;
        bool timer_owned = false, count_owned = false, boundary_owned = false;
        bool count_connected = false, boundary_connected = false;
        TimerFabric *timer = nullptr;
        DppiFabric *dppi = nullptr;
        std::uint32_t buffers = 0U, comparisons = 0U;
        std::uint32_t expected_matches = 0U, actual_matches = 0U;
        std::uint32_t previous_boundary = 0U, last_boundary = 0U, last_delta = 0U;
        std::uint32_t last_expected = 0U, last_actual = 0U;
        std::uint32_t first_boundary = 0U, first_previous = 0U, first_delta = 0U;
        std::uint32_t first_expected = 0U, first_actual = 0U, first_cycle = 0U;
        std::uint32_t pin_cnf_before = 0U, pin_cnf_after = 0U;
        std::uint32_t cleanup_failures = 0U;
        std::uint32_t trace_entries = 0U;
        std::uint32_t trace_observed_total = 0U;
        std::uint32_t trace_expected_total = 0U, trace_actual_total = 0U;
        std::uint32_t trace_expected_last = 0U, trace_actual_last = 0U;
        std::uint32_t trace_boundary[4]{}, trace_delta[4]{};
        std::uint32_t trace_expected[4]{}, trace_actual[4]{};
        std::uint32_t first_registers[20]{};
        bool first_saved = false;
    } edge;

    /** @brief 진단 route에서 role1이 실제 수신하는 SDIN 핀을 반환합니다. */
    unsigned edgeInputPin()
    {
        return edge.policy == 2U ? 6U : 7U;
    }

    EventEndpoint edgeDataEvent()
    {
        return {nrf_gpiote_event_address_get(NRF_GPIOTE20,
                                             nrf_gpiote_in_event_get(edge_gpiote_channel)),
                20U, EventEndpointRole::publisher};
    }

    EventEndpoint edgeBoundaryEvent()
    {
        return {nrf_i2s_event_address_get(NRF_I2S20, NRF_I2S_EVENT_RXPTRUPD), 20U,
                EventEndpointRole::publisher};
    }

    std::uint32_t absoluteDifference(std::uint32_t left, std::uint32_t right)
    {
        return left >= right ? left - right : right - left;
    }

    /** @brief MSB 우선 직렬화한 한 DMA 내부의 논리 전이 수를 계산합니다. */
    std::uint32_t transitionCount(const std::uint32_t *values)
    {
        std::uint32_t count = 0U, previous = 0U;
        bool begun = false;
        for (unsigned index = 0U; index < 256U; ++index)
        {
            for (unsigned bit = 0U; bit < 32U; ++bit)
            {
                const auto value = (values[index] >> (31U - bit)) & 1U;
                if (begun && value != previous)
                {
                    ++count;
                }
                previous = value;
                begun = true;
            }
        }
        return count;
    }

    /** @brief 현재 수신 위치의 시작 padding과 peer 기대 word를 한 규칙으로 반환합니다. */
    std::uint32_t expectedWord(std::uint32_t position)
    {
        return position < oracle.padding
                   ? 0U
                   : v04::i2sStreamPattern(oracle.seed, position - oracle.padding);
    }

    /** @brief 현재 전역 수신 위치에 해당하는 peer의 기대 전이 수를 계산합니다. */
    std::uint32_t expectedTransitionCount()
    {
        std::uint32_t count = 0U, previous = 0U;
        bool begun = false;
        const auto first_position = stats.completed * 256U;
        for (unsigned index = 0U; index < 256U; ++index)
        {
            const auto position = first_position + index;
            const auto word = expectedWord(position);
            for (unsigned bit = 0U; bit < 32U; ++bit)
            {
                const auto value = (word >> (31U - bit)) & 1U;
                if (begun && value != previous)
                {
                    ++count;
                }
                previous = value;
                begun = true;
            }
        }
        return count;
    }

    /** @brief 최초 데이터 불일치 순간의 계수기와 연결 레지스터를 RAM에 보존합니다. */
    void saveEdgeFailure()
    {
        if (!edge.active || edge.first_saved)
        {
            return;
        }
        edge.first_saved = true;
        edge.first_boundary = edge.last_boundary;
        edge.first_previous = edge.previous_boundary - edge.last_delta;
        edge.first_delta = edge.last_delta;
        edge.first_expected = edge.last_expected;
        edge.first_actual = edge.last_actual;
        edge.first_cycle = k_cycle_get_32();
        const std::uint32_t values[]{0x49324552U,
                                     role,
                                     NRF_GPIOTE20->CONFIG[edge_gpiote_channel],
                                     NRF_GPIOTE20->PUBLISH_IN[edge_gpiote_channel],
                                     NRF_GPIOTE20->EVENTS_IN[edge_gpiote_channel],
                                     NRF_TIMER22->MODE,
                                     NRF_TIMER22->BITMODE,
                                     NRF_TIMER22->SUBSCRIBE_COUNT,
                                     NRF_TIMER22->SUBSCRIBE_CAPTURE[0],
                                     NRF_TIMER22->CC[0],
                                     NRF_DPPIC20->CHEN,
                                     NRF_I2S20->PUBLISH_RXPTRUPD,
                                     NRF_I2S20->EVENTS_RXPTRUPD,
                                     NRF_I2S20->RXD.PTR,
                                     NRF_I2S20->RXTXD.MAXCNT,
                                     NRF_P1->PIN_CNF[edgeInputPin()],
                                     NRF_P1->IN,
                                     edge.first_cycle,
                                     edge.active,
                                     edge.boundary_ready};
        for (unsigned index = 0U; index < 20U; ++index)
        {
            edge.first_registers[index] = values[index];
        }
    }

    /** @brief 반환 DMA 경계의 실제 핀 누적 전이 수를 먼저 고정합니다. */
    void observeEdgeBoundary()
    {
        if (!edge.active || !edge.boundary_ready)
        {
            return;
        }
        const auto boundary = nrf_timer_cc_get(NRF_TIMER22, NRF_TIMER_CC_CHANNEL0);
        const auto previous = edge.previous_boundary;
        edge.last_boundary = boundary;
        edge.last_delta = boundary - previous;
        edge.previous_boundary = boundary;
        ++edge.buffers;
    }

    /** @brief 초기 네 DMA와 실제 실패 DMA만 계산해 실시간 공급 시점을 교란하지 않습니다. */
    void compareEdgeBuffer(unsigned slot, bool failure)
    {
        if (!edge.active || !edge.boundary_ready || (!failure && edge.buffers > 4U))
        {
            return;
        }
        edge.last_expected = expectedTransitionCount();
        edge.last_actual = transitionCount(rx[slot].values);
        if (edge.trace_entries < 4U)
        {
            const auto trace = edge.trace_entries;
            const auto first_position = stats.completed * 256U;
            const auto expected_first = expectedWord(first_position) >> 31U;
            const auto actual_first = rx[slot].values[0] >> 31U;
            edge.trace_observed_total += edge.last_delta;
            edge.trace_expected_total += edge.last_expected;
            edge.trace_actual_total += edge.last_actual;
            if (trace != 0U)
            {
                edge.trace_expected_total += edge.trace_expected_last != expected_first ? 1U : 0U;
                edge.trace_actual_total += edge.trace_actual_last != actual_first ? 1U : 0U;
            }
            edge.trace_expected_last = expectedWord(first_position + 255U) & 1U;
            edge.trace_actual_last = rx[slot].values[255] & 1U;
            edge.trace_boundary[trace] = edge.last_boundary;
            edge.trace_delta[trace] = edge.last_delta;
            edge.trace_expected[trace] = edge.last_expected;
            edge.trace_actual[trace] = edge.last_actual;
            ++edge.trace_entries;
        }
        ++edge.comparisons;
        if (absoluteDifference(edge.last_delta, edge.last_expected) <= 1U)
        {
            ++edge.expected_matches;
        }
        if (absoluteDifference(edge.last_delta, edge.last_actual) <= 1U)
        {
            ++edge.actual_matches;
        }
    }

    /** @brief 부분 준비 상태도 역순으로 해제하고 모든 진단 endpoint가 0인지 확인합니다. */
    bool cleanupEdgeDiagnostic()
    {
        if (role != 1U || (!edge.active && !edge.raw_configured && !edge.timer_owned &&
                           !edge.count_owned && !edge.boundary_owned))
        {
            edge.active = false;
            edge.boundary_ready = false;
            return true;
        }
        std::uint32_t failures = 0U;
        if (edge.count_owned &&
            edge.dppi->disable(edge_count_dppi_channel) != EventFabricResult::success)
        {
            failures |= 1U << 0U;
        }
        if (edge.boundary_owned &&
            edge.dppi->disable(edge_boundary_dppi_channel) != EventFabricResult::success)
        {
            failures |= 1U << 1U;
        }
        if (edge.boundary_connected &&
            edge.dppi->disconnect(edgeBoundaryEvent(), edge.timer->task(TimerTask::capture, 0U),
                                  edge_boundary_dppi_channel) != EventFabricResult::success)
        {
            failures |= 1U << 2U;
        }
        edge.boundary_connected = false;
        if (edge.count_connected &&
            edge.dppi->disconnect(edgeDataEvent(), edge.timer->task(TimerTask::count),
                                  edge_count_dppi_channel) != EventFabricResult::success)
        {
            failures |= 1U << 3U;
        }
        edge.count_connected = false;
        if (edge.raw_configured)
        {
            nrf_gpiote_te_default(NRF_GPIOTE20, edge_gpiote_channel);
            nrf_gpiote_event_clear(NRF_GPIOTE20, nrf_gpiote_in_event_get(edge_gpiote_channel));
            edge.raw_configured = false;
        }
        if (edge.timer_owned)
        {
            if (edge.timer->stop() != EventFabricResult::success ||
                edge.timer->clear() != EventFabricResult::success)
            {
                failures |= 1U << 4U;
            }
            nrf_timer_mode_set(NRF_TIMER22, NRF_TIMER_MODE_TIMER);
            if (edge.timer->release() != EventFabricResult::success)
            {
                failures |= 1U << 5U;
            }
        }
        edge.timer_owned = false;
        if (edge.boundary_owned &&
            edge.dppi->releaseChannel(edge_boundary_dppi_channel) != EventFabricResult::success)
        {
            failures |= 1U << 6U;
        }
        edge.boundary_owned = false;
        if (edge.count_owned &&
            edge.dppi->releaseChannel(edge_count_dppi_channel) != EventFabricResult::success)
        {
            failures |= 1U << 7U;
        }
        edge.count_owned = false;
        edge.active = false;
        edge.boundary_ready = false;
        const auto mask = (1UL << edge_count_dppi_channel) | (1UL << edge_boundary_dppi_channel);
        if (NRF_GPIOTE20->CONFIG[edge_gpiote_channel] != 0U ||
            NRF_GPIOTE20->PUBLISH_IN[edge_gpiote_channel] != 0U ||
            NRF_TIMER22->SUBSCRIBE_COUNT != 0U || NRF_TIMER22->SUBSCRIBE_CAPTURE[0] != 0U ||
            NRF_I2S20->PUBLISH_RXPTRUPD != 0U || (NRF_DPPIC20->CHEN & mask) != 0U)
        {
            failures |= 1U << 8U;
        }
        edge.cleanup_failures |= failures;
        return failures == 0U;
    }

    /** @brief role1의 선택된 SDIN을 GPIO 재설정 없이 감시하고 TIMER/DPPI를 구성합니다. */
    bool prepareEdgeDiagnostic()
    {
        if (!edge.policy || role != 1U)
        {
            return true;
        }
        edge.timer = eventFabric().timer(22U);
        edge.dppi = eventFabric().dppi(20U);
        const auto mask = (1UL << edge_count_dppi_channel) | (1UL << edge_boundary_dppi_channel);
        if (edge.timer == nullptr || edge.dppi == nullptr ||
            NRF_GPIOTE20->CONFIG[edge_gpiote_channel] != 0U ||
            NRF_GPIOTE20->PUBLISH_IN[edge_gpiote_channel] != 0U ||
            NRF_I2S20->PUBLISH_RXPTRUPD != 0U || (NRF_DPPIC20->CHEN & mask) != 0U)
        {
            return false;
        }
        edge.timer_owned = edge.timer->acquire(1000000U) == EventFabricResult::success;
        edge.count_owned = edge.timer_owned && edge.dppi->acquireChannel(edge_count_dppi_channel) ==
                                                   EventFabricResult::success;
        edge.boundary_owned =
            edge.count_owned &&
            edge.dppi->acquireChannel(edge_boundary_dppi_channel) == EventFabricResult::success;
        if (!edge.boundary_owned)
        {
            cleanupEdgeDiagnostic();
            return false;
        }
        nrf_timer_mode_set(NRF_TIMER22, NRF_TIMER_MODE_COUNTER);
        const auto input_pin = edgeInputPin();
        edge.pin_cnf_before = NRF_P1->PIN_CNF[input_pin];
        nrf_gpiote_event_configure(NRF_GPIOTE20, edge_gpiote_channel,
                                   NRF_GPIO_PIN_MAP(1U, input_pin), NRF_GPIOTE_POLARITY_TOGGLE);
        nrf_gpiote_event_enable(NRF_GPIOTE20, edge_gpiote_channel);
        edge.raw_configured = true;
        edge.pin_cnf_after = NRF_P1->PIN_CNF[input_pin];
        edge.count_connected =
            edge.dppi->connect(edgeDataEvent(), edge.timer->task(TimerTask::count),
                               edge_count_dppi_channel) == EventFabricResult::success;
        edge.boundary_connected =
            edge.count_connected &&
            edge.dppi->connect(edgeBoundaryEvent(), edge.timer->task(TimerTask::capture, 0U),
                               edge_boundary_dppi_channel) == EventFabricResult::success;
        if (!edge.boundary_connected || edge.pin_cnf_before != edge.pin_cnf_after)
        {
            cleanupEdgeDiagnostic();
            return false;
        }
        return true;
    }

    /** @brief I2S START 직전에 계수 경로를 열어 최초 RXPTRUPD를 기준점으로 사용합니다. */
    bool startEdgeDiagnostic()
    {
        if (!edge.policy || role != 1U)
        {
            return true;
        }
        nrf_gpiote_event_clear(NRF_GPIOTE20, nrf_gpiote_in_event_get(edge_gpiote_channel));
        nrf_i2s_event_clear(NRF_I2S20, NRF_I2S_EVENT_RXPTRUPD);
        if (edge.timer->clear() != EventFabricResult::success ||
            edge.timer->start() != EventFabricResult::success ||
            edge.dppi->enable(edge_count_dppi_channel) != EventFabricResult::success ||
            edge.dppi->enable(edge_boundary_dppi_channel) != EventFabricResult::success)
        {
            cleanupEdgeDiagnostic();
            return false;
        }
        edge.active = true;
        edge.boundary_ready = false;
        return true;
    }

    /** @brief 읽기만으로 DMA·핀 설정·IRQ 상태를 수집하며 event를 지우지 않습니다. */
    void registers(std::uint32_t *out)
    {
        const std::uint32_t values[]{0x49325331U,
                                     role,
                                     k_cycle_get_32(),
                                     NRF_I2S20->ENABLE,
                                     NRF_I2S20->CONFIG.MODE,
                                     NRF_I2S20->CONFIG.RXEN,
                                     NRF_I2S20->CONFIG.TXEN,
                                     NRF_I2S20->TXD.PTR,
                                     NRF_I2S20->RXD.PTR,
                                     NRF_I2S20->RXTXD.MAXCNT,
                                     NRF_I2S20->PSEL.SCK,
                                     NRF_I2S20->PSEL.LRCK,
                                     NRF_I2S20->PSEL.SDOUT,
                                     NRF_I2S20->PSEL.SDIN,
                                     NRF_P1->PIN_CNF[6],
                                     NRF_P1->PIN_CNF[7],
                                     NRF_P1->IN,
                                     NVIC_GetPriority(I2S20_IRQn),
                                     NVIC_GetEnableIRQ(I2S20_IRQn),
                                     NVIC_GetPendingIRQ(I2S20_IRQn)};
        for (unsigned index = 0U; index < 20U; ++index)
        {
            out[index] = values[index];
        }
    }

    bool guards()
    {
        if (!stats.enabled)
        {
            return true;
        }
        for (unsigned slot = 0U; slot < 3U; ++slot)
        {
            if (!tx[slot].guards() || !rx[slot].guards())
            {
                return false;
            }
        }
        return true;
    }

    bool fill(unsigned slot)
    {
        if (pending[slot])
        {
            return stats.fail(1U, slot);
        }
        tx[slot].initialize(0U);
        rx[slot].initialize(0xCCCCCCCCU);
        for (unsigned index = 0U; index < 256U; ++index)
        {
            if (index % 32U == 0U)
            {
                captureService();
            }
            tx[slot].values[index] = v04::i2sStreamPattern(seed_tx, stats.queued * 256U + index);
        }
        return true;
    }

    I2sBuffers buffers(unsigned slot)
    {
        return {rx[slot].values, tx[slot].values, 256U};
    }
} // namespace

bool t13::audioPrepare(const Case &test, std::uint32_t seed)
{
    const unsigned edge_policy = edge.policy;
    edge = {};
    edge.policy = edge_policy;
    stats.enabled = test.i2s;
    audio = nullptr;
    failed_slot = UINT32_MAX;
    stop_requests = 0U;
    for (auto &value : first_failure_registers)
    {
        value = 0U;
    }
    if (!stats.enabled)
    {
        return !edge.policy;
    }
    seed_tx = laneSeed(seed, 0U, role);
    oracle.reset(laneSeed(seed, 0U, 3U - role), 32U, 0U);
    for (unsigned slot = 0U; slot < 3U; ++slot)
    {
        pending[slot] = false;
        tx[slot].initialize(0U);
        rx[slot].initialize(0xCCCCCCCCU);
    }
    if (!prepareEdgeDiagnostic())
    {
        return stats.fail(13U);
    }
    audio = streamFabric().i2s(20U);
    if (audio == nullptr)
    {
        cleanupEdgeDiagnostic();
        return stats.fail(12U);
    }
    const bool swapped_data_route = edge.policy == 2U;
    const I2sConfiguration configuration{
        static_cast<pin_size_t>(role == 1U ? PIN_P1_04 : PIN_P1_05),
        static_cast<pin_size_t>(role == 1U ? PIN_P1_05 : PIN_P1_04),
        0xFFU,
        static_cast<pin_size_t>(swapped_data_route ? PIN_P1_07 : PIN_P1_06),
        static_cast<pin_size_t>(swapped_data_route ? PIN_P1_06 : PIN_P1_07),
        48000U,
        I2sSampleWidth::bits32,
        I2sChannels::stereo,
        role == 1U,
        StreamElectricalProfile::dap_uart_disabled};
    const auto result = audio->configure(configuration);
    if (result != StreamFabricResult::success)
    {
        cleanupEdgeDiagnostic();
        return stats.fail(2U, static_cast<std::uint32_t>(result));
    }
    return true;
}

bool t13::audioStart()
{
    if (!stats.enabled)
    {
        return true;
    }
    if (!fill(0U))
    {
        cleanupEdgeDiagnostic();
        return false;
    }
    submitted[0] = k_cycle_get_32();
    if (!startEdgeDiagnostic())
    {
        return stats.fail(14U);
    }
    const auto result = audio->start(buffers(0U));
    if (result != StreamFabricResult::success)
    {
        cleanupEdgeDiagnostic();
        return stats.fail(3U, static_cast<std::uint32_t>(result));
    }
    pending[0] = stats.active = true;
    stats.queued = 1U;
    return true;
}

void t13::audioService()
{
    if (!stats.active || stats.error != 0U)
    {
        return;
    }
    I2sEvent event{};
    while (audio->takeEvent(event))
    {
        stream_fault.event(2U);
        if (event.type == I2sEventType::buffers_complete)
        {
            const auto slot = stats.completed % 3U;
            if (!pending[slot] || event.released.receive != rx[slot].values ||
                event.released.transmit != tx[slot].values || event.released.words != 256U ||
                !guards())
            {
                stats.fail(4U, slot);
                break;
            }
            observeEdgeBoundary();
            const auto mismatches_before = oracle.mismatches;
            for (unsigned index = 0U; index < 256U; ++index)
            {
                if (index % 32U == 0U)
                {
                    captureService();
                }
                const auto value = rx[slot].values[index];
                oracle.consume(value);
                if (tx[slot].values[index] !=
                    v04::i2sStreamPattern(seed_tx, stats.completed * 256U + index))
                {
                    stats.fail(5U, index);
                }
                for (unsigned byte = 0U; byte < 4U; ++byte)
                {
                    stats.hash = hashByte(stats.hash, (value >> (byte * 8U)) & 255U);
                }
            }
            stats.first = rx[slot].values[0];
            stats.last = rx[slot].values[255];
            stats.padding = oracle.padding;
            stats.extra[0] = oracle.samples;
            stats.extra[1] = oracle.mismatches;
            compareEdgeBuffer(slot, oracle.mismatches != mismatches_before);
            if (oracle.mismatches != 0U)
            {
                if (failed_slot == UINT32_MAX)
                {
                    registers(first_failure_registers);
                    failed_slot = slot;
                    saveEdgeFailure();
                }
                stats.fail(6U, oracle.first_index);
            }
            stats.complete(256U, submitted[slot]);
            pending[slot] = false;
        }
        else if (event.type == I2sEventType::buffers_needed)
        {
            if (edge.active && stats.completed == 0U && !edge.boundary_ready)
            {
                edge.previous_boundary = nrf_timer_cc_get(NRF_TIMER22, NRF_TIMER_CC_CHANNEL0);
                edge.last_boundary = edge.previous_boundary;
                edge.boundary_ready = true;
            }
            if (stream_fault.skip(2U, stats.completed, stats.queued, k_cycle_get_32()))
            {
                continue;
            }
            const auto slot = stats.queued % 3U;
            const auto began = k_cycle_get_32();
            if (!fill(slot))
            {
                break;
            }
            const auto result = audio->queueBuffers(buffers(slot));
            stats.queue_time.add(k_cyc_to_us_floor32(k_cycle_get_32() - began));
            if (result != StreamFabricResult::success)
            {
                stats.fail(7U, static_cast<std::uint32_t>(result));
                break;
            }
            pending[slot] = true;
            submitted[slot] = began;
            ++stats.queued;
        }
        else
        {
            stream_fault.observe(2U, static_cast<unsigned>(event.type), event.driver_error,
                                 k_cycle_get_32(), stats.completed, stats.queued, guards(),
                                 static_cast<unsigned>(audio->state()), stats.error, stats.detail);
            stats.fail(8U, static_cast<std::uint32_t>(event.type));
        }
        if (stats.error != 0U)
        {
            break;
        }
    }
}

bool t13::audioStop()
{
    if (stats.enabled)
    {
        ++stop_requests;
    }
    bool stopped = true;
    if (audio != nullptr && audio->state() == StreamFabricState::faulted)
    {
        stopped = stats.fail(9U);
    }
    else if (audio != nullptr && (audio->state() == StreamFabricState::active ||
                                  audio->state() == StreamFabricState::stopping))
    {
        const auto result = audio->stop(100000U);
        if (result != StreamFabricResult::success)
        {
            stopped = stats.fail(10U, static_cast<std::uint32_t>(result));
        }
        else
        {
            for (unsigned pin = 4U; pin <= 7U; ++pin)
            {
                nrf_gpio_cfg_input(NRF_GPIO_PIN_MAP(1, pin), NRF_GPIO_PIN_NOPULL);
            }
        }
    }
    const bool edge_clean = cleanupEdgeDiagnostic();
    if (!edge_clean)
    {
        stats.fail(15U, edge.cleanup_failures);
    }
    stats.active = false;
    const bool guarded = guards();
    if (!guarded)
    {
        stats.fail(11U);
    }
    return stopped && edge_clean && guarded;
}

bool t13::audioHealthy()
{
    return stats.error == 0U;
}

void t13::audioSnapshot(std::uint32_t *out)
{
    stats.snapshot(2U, guards(), out);
}

/** @brief 최초 불일치의 예상/실제 word와 반환된 DMA 전체를 STOP 뒤에도 읽습니다. */
void t13::audioDiagnosticSnapshot(unsigned page, std::uint32_t *out, std::uint32_t &count)
{
    if (!stats.enabled || page > 19U)
    {
        count = 0U;
        return;
    }
    if (page >= 17U)
    {
        if (page == 17U)
        {
            registers(out);
        }
        else if (page == 18U)
        {
            const std::uint32_t values[]{0x49325332U,
                                         role,
                                         stats.active,
                                         stats.error,
                                         stats.detail,
                                         stats.completed,
                                         stats.queued,
                                         stop_requests,
                                         failed_slot,
                                         audio == nullptr ? UINT32_MAX
                                                          : static_cast<unsigned>(audio->state()),
                                         NRF_I2S20->EVENTS_STOPPED,
                                         NRF_I2S20->EVENTS_RXPTRUPD,
                                         NRF_I2S20->EVENTS_TXPTRUPD,
                                         NRF_P1->PIN_CNF[4],
                                         NRF_P1->PIN_CNF[5],
                                         NRF_I2S20->CONFIG.SWIDTH,
                                         NRF_I2S20->CONFIG.CHANNELS,
                                         NRF_I2S20->CONFIG.RATIO,
                                         k_cycle_get_32(),
                                         guards()};
            for (unsigned index = 0U; index < 20U; ++index)
            {
                out[index] = values[index];
            }
        }
        else
        {
            for (unsigned index = 0U; index < 20U; ++index)
            {
                out[index] = first_failure_registers[index];
            }
        }
        count = 20U;
        return;
    }
    if (page == 0U)
    {
        const std::uint32_t values[]{20U,
                                     role,
                                     seed_tx,
                                     oracle.seed,
                                     oracle.padding,
                                     oracle.samples,
                                     oracle.mismatches,
                                     oracle.first_index,
                                     oracle.first_expected,
                                     oracle.first_actual,
                                     failed_slot,
                                     stats.completed,
                                     stats.queued,
                                     stats.error,
                                     stats.detail,
                                     guards(),
                                     audio == nullptr ? UINT32_MAX
                                                      : static_cast<unsigned>(audio->state()),
                                     CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC,
                                     k_cycle_get_32(),
                                     256U};
        for (unsigned index = 0U; index < 20U; ++index)
        {
            out[index] = values[index];
        }
        count = 20U;
        return;
    }
    if (failed_slot >= 3U || stats.error == 0U || stats.active)
    {
        count = 0U;
        return;
    }
    for (unsigned index = 0U; index < 16U; ++index)
    {
        out[index] = rx[failed_slot].values[(page - 1U) * 16U + index];
    }
    count = 16U;
}

bool t13::audioEdgeDiagnosticPolicy(unsigned mode)
{
    if (mode > 2U || edge.active || edge.timer_owned || edge.count_owned || edge.boundary_owned)
    {
        return false;
    }
    edge.policy = mode;
    return true;
}

/** @brief SDIN 전이 판정, 최초 네 DMA 추적값, 최초 오류 레지스터를 반환합니다. */
void t13::audioEdgeDiagnosticSnapshot(unsigned page, std::uint32_t *out, std::uint32_t &count)
{
    if (page > 2U)
    {
        count = 0U;
        return;
    }
    if (page == 0U)
    {
        const std::uint32_t values[]{
            0x49324530U,
            role,
            edge.policy,
            edge.active,
            edge.boundary_ready,
            edge.buffers,
            edge.comparisons,
            edge.expected_matches,
            edge.actual_matches,
            edge.last_boundary,
            edge.last_delta,
            edge.last_expected,
            edge.last_actual,
            edge.first_saved,
            edge.first_saved ? edge.first_delta : edge.trace_observed_total,
            edge.first_saved ? edge.first_expected : edge.trace_expected_total,
            edge.first_saved ? edge.first_actual : edge.trace_actual_total,
            edge.cleanup_failures,
            edge.pin_cnf_before,
            edge.pin_cnf_after};
        for (unsigned index = 0U; index < 20U; ++index)
        {
            out[index] = values[index];
        }
    }
    else if (page == 1U)
    {
        const std::uint32_t values[]{0x49324531U,
                                     role,
                                     edge.first_saved,
                                     edge.first_previous,
                                     edge.first_boundary,
                                     edge.first_delta,
                                     edge.first_expected,
                                     edge.first_actual,
                                     absoluteDifference(edge.first_delta, edge.first_expected),
                                     absoluteDifference(edge.first_delta, edge.first_actual),
                                     edge.buffers,
                                     stats.completed,
                                     stats.error,
                                     stats.detail,
                                     edge.first_cycle,
                                     NRF_P1->PIN_CNF[edgeInputPin()],
                                     NRF_P1->IN,
                                     NRF_TIMER22->CC[0],
                                     edge.cleanup_failures,
                                     guards()};
        for (unsigned index = 0U; index < 20U; ++index)
        {
            out[index] = values[index];
        }
    }
    else
    {
        if (edge.first_saved)
        {
            for (unsigned index = 0U; index < 20U; ++index)
            {
                out[index] = edge.first_registers[index];
            }
        }
        else if (role == 1U)
        {
            out[0] = 0x49324554U;
            out[1] = role;
            out[2] = edge.trace_entries;
            out[3] = edge.buffers;
            for (unsigned index = 0U; index < 4U; ++index)
            {
                const auto base = 4U + index * 4U;
                out[base] = edge.trace_boundary[index];
                out[base + 1U] = edge.trace_delta[index];
                out[base + 2U] = edge.trace_expected[index];
                out[base + 3U] = edge.trace_actual[index];
            }
        }
        else
        {
            for (unsigned index = 0U; index < 20U; ++index)
            {
                out[index] = 0U;
            }
        }
    }
    count = 20U;
}
