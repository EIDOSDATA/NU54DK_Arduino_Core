/** @file @brief 50% mono SPIS 합성 신호와 PDM 4-slot DMA를 연속 검사합니다. */
#include "stream_types.h"
#include <nucode/StreamFabric.h>
#include <nucode/SerialFabric.h>
#include <internal/IoResourceManager.h>
#include <variant.h>
#include <hal/nrf_gpio.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>

namespace
{
    using namespace nucode::arduino;
    using namespace nucode::arduino::internal;
    using namespace t13;
    constexpr unsigned role = CONFIG_NUCODE_V04_HIL_ROLE;
    auto &stats = stream_stats[3];
    PdmFabric *pdm = nullptr;
    SpisHandle *source = nullptr;
    Block<std::int16_t, 1024U> buffers[4];
    Block<std::uint8_t, 1024U> source_buffer;
    bool pending[4]{};
    std::uint32_t submitted[4]{};
    IoResourceToken select_token{};
    constexpr std::uint32_t select_pin = NRF_GPIO_PIN_MAP(1, 5);

    bool guards()
    {
        if (!stats.enabled)
        {
            return true;
        }
        if (role == 2U)
        {
            return source_buffer.guards();
        }
        for (const auto &buffer : buffers)
        {
            if (!buffer.guards())
            {
                return false;
            }
        }
        return true;
    }
} // namespace

bool t13::pdmPrepare(const Case &test)
{
    stats.enabled = test.pdm_instance != 0U;
    source = nullptr;
    pdm = nullptr;
    if (!stats.enabled)
    {
        return true;
    }
    if (role == 1U)
    {
        for (unsigned slot = 0U; slot < 4U; ++slot)
        {
            buffers[slot].initialize(0x5A5A);
            pending[slot] = false;
        }
        pdm = streamFabric().pdm(test.pdm_instance);
        if (pdm == nullptr)
        {
            return stats.fail(17U);
        }
        const auto result = pdm->configure({PIN_P1_04, PIN_P1_06, 16000U, false, false,
                                            StreamElectricalProfile::dap_uart_disabled});
        if (result != StreamFabricResult::success)
        {
            return stats.fail(1U, static_cast<std::uint32_t>(result));
        }
        const gpio_dt_spec gpio{DEVICE_DT_GET(DT_NODELABEL(gpio1)), 5U, 0U};
        const auto resource = gpioIoResource(gpio);
        if (acquireIoResources({IoOwnerKind::application, 242U}, &resource, 1U,
                               IoAcquirePolicy::exclusive,
                               select_token) != IoResourceResult::success)
        {
            return stats.fail(2U);
        }
        nrf_gpio_pin_set(select_pin);
        nrf_gpio_cfg_output(select_pin);
        return true;
    }
    source_buffer.initialize(0x55U);
    const SerialSignalPin pins[]{{SerialSignal::sck, PIN_P1_05},
                                 {SerialSignal::mosi, PIN_P1_06},
                                 {SerialSignal::miso, PIN_P1_07},
                                 {SerialSignal::csn, PIN_P1_04}};
    const SerialDmaWorkspace workspace{source_buffer.values, 1024U};
    const SerialFabricConfiguration route{SerialRouteClass::p1_flexible,
                                          SerialElectricalProfile::dap_uart_disabled,
                                          pins,
                                          4U,
                                          &workspace,
                                          1U};
    source = serialFabric().spis(21U);
    if (source == nullptr)
    {
        return stats.fail(18U);
    }
    /** @brief 초기 DMA 이후에도 ORC 0x55가 같은 밀도를 유지하며 실제 DMA 완료로 세지 않습니다. */
    if (source->configure({1000000U, SpiFabricMode::mode0, SpiFabricBitOrder::msb_first, 0x55U}) !=
            SerialFabricResult::success ||
        source->stage(route) != SerialFabricResult::success ||
        source->activate() != SerialFabricResult::success)
    {
        return stats.fail(3U);
    }
    return true;
}

bool t13::pdmStart()
{
    if (!stats.enabled)
    {
        return true;
    }
    if (role == 2U)
    {
        const auto result = source->queueBuffers(source_buffer.values, 1024U, nullptr, 0U);
        stats.active = result == SerialFabricResult::success;
        stats.queued = stats.active ? 1U : 0U;
        return stats.active || stats.fail(4U, static_cast<std::uint32_t>(result));
    }
    submitted[0] = k_cycle_get_32();
    nrf_gpio_pin_clear(select_pin);
    const auto result = pdm->start(buffers[0].values, 1024U);
    if (result != StreamFabricResult::success)
    {
        return stats.fail(5U, static_cast<std::uint32_t>(result));
    }
    pending[0] = stats.active = true;
    stats.queued = 1U;
    return true;
}

void t13::pdmService()
{
    if (!stats.active || stats.error != 0U)
    {
        return;
    }
    if (role == 2U)
    {
        SpiFabricEvent event{};
        while (source->takeEvent(event))
        {
            if (event.type == SpiFabricEventType::buffers_armed)
            {
                ++stats.extra[0];
            }
            else if (event.type == SpiFabricEventType::transfer_complete && streams_quiesced)
            {
                ++stats.completed;
            }
            else if (event.type != SpiFabricEventType::buffer_needed)
            {
                stats.fail(6U, static_cast<std::uint32_t>(event.type));
            }
        }
        return;
    }
    PdmEvent event{};
    while (pdm->takeEvent(event))
    {
        if (event.type == PdmEventType::buffer_needed)
        {
            const auto slot = stats.queued % 4U;
            if (pending[slot])
            {
                stats.fail(7U, slot);
                break;
            }
            const auto began = k_cycle_get_32();
            buffers[slot].initialize(0x5A5A);
            const auto result = pdm->queueBuffer(buffers[slot].values, 1024U);
            stats.queue_time.add(k_cyc_to_us_floor32(k_cycle_get_32() - began));
            if (result != StreamFabricResult::success)
            {
                stats.fail(8U, static_cast<std::uint32_t>(result));
                break;
            }
            submitted[slot] = began;
            pending[slot] = true;
            ++stats.queued;
        }
        else if (event.type == PdmEventType::buffer_complete)
        {
            const auto slot = stats.completed % 4U;
            if (!pending[slot] || event.buffer != buffers[slot].values || event.samples != 1024U ||
                !guards())
            {
                stats.fail(9U, event.samples);
                break;
            }
            std::int32_t sum = 0;
            for (unsigned index = 0U; index < 1024U; ++index)
            {
                if (index % 64U == 0U)
                {
                    captureService();
                }
                const auto value = event.buffer[index];
                if (value == 0x5A5A || (stats.completed >= 4U && (value < -4096 || value > 4096)))
                {
                    stats.fail(10U, static_cast<std::uint32_t>(value));
                }
                sum += value;
                stats.minimum = value < stats.minimum ? value : stats.minimum;
                stats.maximum = value > stats.maximum ? value : stats.maximum;
                const auto bits = static_cast<std::uint16_t>(value);
                stats.hash = hashByte(hashByte(stats.hash, bits & 255U), bits >> 8U);
            }
            stats.first = static_cast<std::uint32_t>(static_cast<std::int32_t>(event.buffer[0]));
            stats.last = static_cast<std::uint32_t>(static_cast<std::int32_t>(event.buffer[1023]));
            stats.extra[0] = static_cast<std::uint32_t>(sum);
            stats.extra[1] = 16000U;
            stats.complete(1024U, submitted[slot]);
            pending[slot] = false;
        }
        else
        {
            stats.fail(11U, static_cast<std::uint32_t>(event.type));
        }
        if (stats.error != 0U)
        {
            break;
        }
    }
}

bool t13::pdmStop()
{
    if (pdm != nullptr && pdm->state() == StreamFabricState::faulted)
    {
        return stats.fail(12U);
    }
    if (pdm != nullptr &&
        (pdm->state() == StreamFabricState::active || pdm->state() == StreamFabricState::stopping))
    {
        const auto result = pdm->stop(100000U);
        if (result != StreamFabricResult::success)
        {
            return stats.fail(13U, static_cast<std::uint32_t>(result));
        }
        nrf_gpio_cfg_input(NRF_GPIO_PIN_MAP(1, 4), NRF_GPIO_PIN_NOPULL);
        nrf_gpio_cfg_input(NRF_GPIO_PIN_MAP(1, 6), NRF_GPIO_PIN_NOPULL);
    }
    if (select_token.active)
    {
        nrf_gpio_pin_set(select_pin);
        nrf_gpio_cfg_input(select_pin, NRF_GPIO_PIN_NOPULL);
        if (releaseIoResources(select_token) != IoResourceResult::success)
        {
            return stats.fail(14U);
        }
    }
    if (source != nullptr && source->deactivate(100000U) != SerialFabricResult::success)
    {
        return stats.fail(15U);
    }
    stats.active = false;
    return guards() || stats.fail(16U);
}

bool t13::pdmHealthy()
{
    return stats.error == 0U;
}

void t13::pdmSnapshot(std::uint32_t *out)
{
    stats.snapshot(3U, guards(), out);
}
