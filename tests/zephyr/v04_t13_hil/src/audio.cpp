/** @file @brief 양방향 I2S 3-slot DMA의 모든 반환 word를 전역 위치로 대조합니다. */
#include "stream_types.h"
#include "i2s_stream_oracle.h"
#include <nucode/StreamFabric.h>
#include <variant.h>
#include <hal/nrf_gpio.h>
#include <hal/nrf_i2s.h>

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
        return true;
    }
    seed_tx = laneSeed(seed, 0U, role);
    oracle.reset(laneSeed(seed, 0U, 3U - role), 32U, 0U);
    for (unsigned slot = 0U; slot < 3U; ++slot)
    {
        pending[slot] = false;
        tx[slot].initialize(0U);
        rx[slot].initialize(0xCCCCCCCCU);
    }
    audio = streamFabric().i2s(20U);
    if (audio == nullptr)
    {
        return stats.fail(12U);
    }
    const I2sConfiguration configuration{
        static_cast<pin_size_t>(role == 1U ? PIN_P1_04 : PIN_P1_05),
        static_cast<pin_size_t>(role == 1U ? PIN_P1_05 : PIN_P1_04),
        0xFFU,
        PIN_P1_06,
        PIN_P1_07,
        48000U,
        I2sSampleWidth::bits32,
        I2sChannels::stereo,
        role == 1U,
        StreamElectricalProfile::dap_uart_disabled};
    const auto result = audio->configure(configuration);
    return result == StreamFabricResult::success ||
           stats.fail(2U, static_cast<std::uint32_t>(result));
}

bool t13::audioStart()
{
    if (!stats.enabled)
    {
        return true;
    }
    if (!fill(0U))
    {
        return false;
    }
    submitted[0] = k_cycle_get_32();
    const auto result = audio->start(buffers(0U));
    if (result != StreamFabricResult::success)
    {
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
            if (oracle.mismatches != 0U)
            {
                if (failed_slot == UINT32_MAX)
                {
                    registers(first_failure_registers);
                    failed_slot = slot;
                }
                stats.fail(6U, oracle.first_index);
            }
            stats.complete(256U, submitted[slot]);
            pending[slot] = false;
        }
        else if (event.type == I2sEventType::buffers_needed)
        {
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
    if (audio != nullptr && audio->state() == StreamFabricState::faulted)
    {
        return stats.fail(9U);
    }
    if (audio != nullptr && (audio->state() == StreamFabricState::active ||
                             audio->state() == StreamFabricState::stopping))
    {
        const auto result = audio->stop(100000U);
        if (result != StreamFabricResult::success)
        {
            return stats.fail(10U, static_cast<std::uint32_t>(result));
        }
        for (unsigned pin = 4U; pin <= 7U; ++pin)
        {
            nrf_gpio_cfg_input(NRF_GPIO_PIN_MAP(1, pin), NRF_GPIO_PIN_NOPULL);
        }
    }
    stats.active = false;
    return guards() || stats.fail(11U);
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
