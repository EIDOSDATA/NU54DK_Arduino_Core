/** @file @brief 양방향 I2S 3-slot DMA의 모든 반환 word를 전역 위치로 대조합니다. */
#include "stream_types.h"
#include "i2s_stream_oracle.h"
#include <nucode/StreamFabric.h>
#include <variant.h>
#include <hal/nrf_gpio.h>

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
                stats.fail(6U, oracle.first_index);
            }
            stats.complete(256U, submitted[slot]);
            pending[slot] = false;
        }
        else if (event.type == I2sEventType::buffers_needed)
        {
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
