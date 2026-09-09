/**
 * @file
 * @brief production SPIS adapter의 다음 semaphore 선행 예약과 연속 refill을 검증합니다.
 */

#include "../../cores/arduino/SpisFabric.cpp"

#include <hal/nrf_gpio.h>

#include <cassert>
#include <cstddef>
#include <cstdint>

using namespace nucode::arduino;
using namespace nucode::arduino::internal;

NRF_GPIO_Type mock_gpio[3]{};

int nrfx_power_constlat_mode_request()
{
    return 0;
}

int nrfx_power_constlat_mode_free()
{
    return 0;
}

namespace nucode::arduino::internal
{
    SerialFabricResult
    validateNu54dkSerialFabricRoute(SerialPersonality, std::uint8_t,
                                    const SerialFabricConfiguration &configuration,
                                    ValidatedSerialRoute &route, IoResourceId *resources,
                                    std::size_t, std::size_t &count) noexcept
    {
        route.pin_count = configuration.pin_count;
        for (std::size_t index = 0U; index < configuration.pin_count; ++index)
        {
            route.pins[index] = configuration.pins[index];
        }
        route.dma_workspace_count = configuration.dma_workspace_count;
        for (std::size_t index = 0U; index < configuration.dma_workspace_count; ++index)
        {
            route.dma_workspaces[index] = configuration.dma_workspaces[index];
        }
        resources[0] = peripheralIoResource(IoResourceKind::serial_block, 20U);
        count = 1U;
        return SerialFabricResult::success;
    }

    SerialFabricResult nu54dkSerialFabricPsel(pin_size_t pin, std::uint32_t &psel) noexcept
    {
        psel = pin;
        return SerialFabricResult::success;
    }

    IoResourceResult reserveIoResources(IoResourceOwner owner, const IoResourceId *, std::size_t,
                                        IoAcquirePolicy, IoResourceLease &lease,
                                        IoResourceSnapshot *) noexcept
    {
        lease.owner = owner;
        lease.phase = IoLeasePhase::reserved;
        return IoResourceResult::success;
    }

    IoResourceResult commitIoResources(IoResourceLease &lease) noexcept
    {
        lease.phase = IoLeasePhase::committed;
        return IoResourceResult::success;
    }

    IoResourceResult rollbackIoResources(IoResourceLease &) noexcept
    {
        return IoResourceResult::success;
    }

    IoResourceResult releaseIoResources(IoResourceLease &) noexcept
    {
        return IoResourceResult::success;
    }
} // namespace nucode::arduino::internal

namespace
{
    alignas(4) std::uint8_t memory[128]{};

    void expectEvent(SpisHandle &handle, SpiFabricEventType type, const void *tx, const void *rx)
    {
        SpiFabricEvent event{};
        assert(handle.takeEvent(event));
        assert(event.type == type);
        assert(event.tx_buffer == tx);
        assert(event.rx_buffer == rx);
    }
} // namespace

int main()
{
    assert(nucode::arduino::registerAdapters() == 0);
    auto *const handle = serialFabric().spis(20U);
    assert(handle != nullptr);
    SerialSignalPin pins[] = {
        {SerialSignal::sck, 1U},
        {SerialSignal::mosi, 2U},
        {SerialSignal::miso, 3U},
        {SerialSignal::csn, 4U},
    };
    SerialDmaWorkspace workspace{memory, sizeof(memory)};
    const SerialFabricConfiguration configuration{
        SerialRouteClass::p1_flexible,
        SerialElectricalProfile::dap_uart_disabled,
        pins,
        4U,
        &workspace,
        1U,
    };
    assert(handle->stage(configuration) == SerialFabricResult::success);
    assert(handle->activate() == SerialFabricResult::success);

    auto &driver = nucode::arduino::contextFor(20U)->driver;
    assert(handle->queueBuffers(memory, 8U, memory + 16U, 8U, memory + 32U, 8U, memory + 48U, 8U) ==
           SerialFabricResult::success);
    assert(mock_spis_buffer_sets.size() == 1U);

    /** @brief 첫 pair의 armed 통지는 다음 pair로 첫 CS 전에 교체하지 않아야 합니다. */
    mock_spis_buffers_armed(driver);
    assert(mock_spis_buffer_sets.size() == 1U);
    expectEvent(*handle, SpiFabricEventType::buffers_armed, memory, memory + 16U);

    /** @brief RX/TX 양쪽 DMA READY가 모두 도착한 뒤에만 다음 pair를 예약합니다. */
    mock_spis_rx_started(driver);
    handleIrq(20U);
    assert(mock_spis_buffer_sets.size() == 1U);
    mock_spis_tx_started(driver);
    handleIrq(20U);
    assert(mock_spis_buffer_sets.size() == 2U);
    assert(mock_spis_buffer_sets[1].tx == memory + 32U);

    mock_spis_transfer_done(driver, 8U, 8U);
    assert(mock_spis_buffer_sets.size() == 2U);
    expectEvent(*handle, SpiFabricEventType::transfer_complete, memory, memory + 16U);
    expectEvent(*handle, SpiFabricEventType::buffer_needed, nullptr, nullptr);

    /** @brief promoted pair의 ACQUIRED 뒤 완료 pair를 다음 transaction으로 refill합니다. */
    mock_spis_buffers_armed(driver);
    expectEvent(*handle, SpiFabricEventType::buffers_armed, memory + 32U, memory + 48U);
    assert(handle->provideNextBuffers(memory, 8U, memory + 16U, 8U) == SerialFabricResult::success);
    assert(mock_spis_buffer_sets.size() == 2U);
    assert(handle->provideNextBuffers(memory + 64U, 8U, memory + 80U, 8U) ==
           SerialFabricResult::wrong_state);

    /** @brief 반대 순서로 도착해도 첫 READY만으로 다음 pair를 예약하지 않습니다. */
    mock_spis_tx_started(driver);
    handleIrq(20U);
    assert(mock_spis_buffer_sets.size() == 2U);
    mock_spis_rx_started(driver);
    handleIrq(20U);
    assert(mock_spis_buffer_sets.size() == 3U);

    mock_spis_transfer_done(driver, 8U, 8U);
    assert(mock_spis_buffer_sets.size() == 3U);
    expectEvent(*handle, SpiFabricEventType::transfer_complete, memory + 32U, memory + 48U);
    expectEvent(*handle, SpiFabricEventType::buffer_needed, nullptr, nullptr);
    mock_spis_buffers_armed(driver);
    expectEvent(*handle, SpiFabricEventType::buffers_armed, memory, memory + 16U);

    assert(handle->deactivate() == SerialFabricResult::success);
    return 0;
}
