/** @file @brief 실제 SPI facade의 설정·순서·부분 실패를 검증합니다. */
/** @brief Arduino의 weak main() 선언과 Host 명령행 entrypoint를 구분합니다. */
#define main arduino_core_entry
#include <Arduino.h>
#undef main
#include "internal/SPIBackend.h"
#include "internal/SpiInterruptMask.h"
#include <peripheral_routes.h>
#include <zephyr/kernel.h>
#include <zephyr/drivers/spi.h>
#include <cassert>
#include <cerrno>
#include <string>
#include <thread>
#include <vector>

extern const device mock_spi_device{};
using namespace nucode::arduino::internal;
namespace
{
    std::string scenario;
    bool route_active = false;
    bool begin_fails = false;
    bool end_fails = false;
    int activates = 0;
    int deactivates = 0;
    int transfer_calls = 0;
    int fail_transfer = 0;
    int fail_suspend = -1;
    bool fail_restore = false;
    pinctrl_dev_config mock_pinctrl{};
    spi_config observed{};
    const spi_config *observed_pointer = nullptr;
    std::vector<std::uint8_t> transmitted;
    std::vector<int> masks;
    std::vector<int> restores;
    void expect(SpiError error)
    {
        assert(lastSpiError() == error);
    }
    bool valid(int value) noexcept
    {
        return value >= 0 && value < 8;
    }
    int suspend(int value, SpiInterruptMaskToken &token) noexcept
    {
        masks.push_back(value);
        if (value == fail_suspend)
        {
            return -EIO;
        }
        token.words[0] = static_cast<std::uintptr_t>(value);
        token.active = true;
        return 0;
    }
    int restore(SpiInterruptMaskToken &token) noexcept
    {
        assert(token.active);
        restores.push_back(static_cast<int>(token.words[0]));
        if (fail_restore)
        {
            return -EIO;
        }
        token.active = false;
        return 0;
    }
} // namespace
namespace nucode::arduino::internal
{
    PeripheralRouteBinding spiRouteBinding() noexcept
    {
        return {
            &mock_spi_device, &mock_pinctrl, {IoOwnerKind::spi, 0}, IoResourceKind::serial_block, 0,
            PinRoute::spi00,  true};
    }
    PeripheralRouteBuildError buildPeripheralRoute(PinRoute required, const pin_size_t *pins,
                                                   const PeripheralSignal *signals,
                                                   std::size_t count,
                                                   PeripheralRouteConfiguration &config) noexcept
    {
        assert(required == PinRoute::spi00 && count == 3);
        if (pins[0] == 99)
        {
            return PeripheralRouteBuildError::invalid_pin;
        }
        config.pin_count = count;
        for (std::size_t index = 0; index < count; ++index)
        {
            config.logical_pins[index] = pins[index];
            config.signals[index] = signals[index];
        }
        return PeripheralRouteBuildError::none;
    }
    PeripheralRouteBuildError defaultSpiRoute(PeripheralRouteConfiguration &config) noexcept
    {
        config.pin_count = 3;
        return PeripheralRouteBuildError::none;
    }
    RuntimePeripheralRoute::RuntimePeripheralRoute(const device *dev, pinctrl_dev_config *config,
                                                   IoResourceOwner owner, IoResourceKind kind,
                                                   std::uint16_t index) noexcept
        : device_(dev), pinctrl_config_(config), owner_(owner), block_kind_(kind),
          block_index_(index)
    {
    }
    bool RuntimePeripheralRoute::stage(const PeripheralRouteConfiguration &config) noexcept
    {
        assert(!route_active);
        staged_configuration_ = config;
        return true;
    }
    bool RuntimePeripheralRoute::activate() noexcept
    {
        ++activates;
        if (begin_fails)
        {
            return false;
        }
        assert(!route_active);
        route_active = true;
        return true;
    }
    bool RuntimePeripheralRoute::deactivate() noexcept
    {
        ++deactivates;
        if (end_fails)
        {
            return false;
        }
        route_active = false;
        return true;
    }
    bool RuntimePeripheralRoute::active() const noexcept
    {
        return route_active;
    }
    bool RuntimePeripheralRoute::faulted() const noexcept
    {
        return false;
    }
    int RuntimePeripheralRoute::lastDriverError() const noexcept
    {
        return -123;
    }
} // namespace nucode::arduino::internal
int spi_transceive(const device *dev, const spi_config *config, const spi_buf_set *tx,
                   const spi_buf_set *rx)
{
    assert(dev == &mock_spi_device && route_active && config != nullptr);
    assert(config->cs == 0 && config->slave == 0 && config->word_delay == 0);
    assert(tx->count == 1 && rx->count == 1 && tx->buffers->len == rx->buffers->len);
    observed = *config;
    observed_pointer = config;
    ++transfer_calls;
    if (transfer_calls == fail_transfer)
    {
        return -EIO;
    }
    auto *source = static_cast<std::uint8_t *>(tx->buffers->buf);
    auto *destination = static_cast<std::uint8_t *>(rx->buffers->buf);
    transmitted.assign(source, source + tx->buffers->len);
    for (std::size_t index = 0; index < tx->buffers->len; ++index)
    {
        destination[index] = source[index] ^ 0x5A;
    }
    return 0;
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    scenario = argv[1];
    assert(SPI.transfer(1) == 0);
    expect(SpiError::not_started);
    assert(!SPI.setPins(99, 1, 2));
    expect(SpiError::invalid_pin_route);
    assert(SPI.setPins(0, 1, 2));
    if (scenario == "route_fail")
    {
        begin_fails = true;
        SPI.begin();
        expect(SpiError::route_error);
        assert(lastSpiDriverError() == -123 && !route_active);
        begin_fails = false;
    }
    SPI.begin();
    expect(SpiError::none);
    const int begin_count = activates;
    SPI.begin();
    assert(activates == begin_count);
    assert(!SPI.setPins(0, 1, 2));
    expect(SpiError::route_busy);
    if (scenario == "settings")
    {
        for (std::uint32_t frequency : {0U, 1000000U, 3000000U, 33000000U})
        {
            SPI.beginTransaction(SPISettings(frequency, MSBFIRST, arduino::SPI_MODE0));
            expect(SpiError::invalid_frequency);
            assert(!spiTransactionActive());
        }
        SPI.beginTransaction(SPISettings(0, MSBFIRST, arduino::SPI_MODE0, arduino::SPI_PERIPHERAL));
        expect(SpiError::unsupported_bus_mode);
        SPI.beginTransaction(SPISettings(4000000, static_cast<BitOrder>(7), arduino::SPI_MODE0));
        expect(SpiError::invalid_bit_order);
        SPI.beginTransaction(SPISettings(4000000, MSBFIRST, 4));
        expect(SpiError::invalid_data_mode);
        for (std::uint32_t frequency : {2000000U, 4000000U, 8000000U, 16000000U, 32000000U})
        {
            SPI.beginTransaction(SPISettings(frequency, MSBFIRST, 0));
            expect(SpiError::none);
            assert(spiTransactionFrequency() == frequency);
            assert(SPI.transfer(1) == (1 ^ 0x5A));
            assert(observed.frequency == frequency);
            SPI.endTransaction();
        }
    }
    else if (scenario == "modes")
    {
        const spi_config *previous = nullptr;
        for (int mode = 0; mode < 4; ++mode)
        {
            for (BitOrder order : {LSBFIRST, MSBFIRST})
            {
                SPI.beginTransaction(SPISettings(4000000, order, mode));
                assert(SPI.transfer16(0x1234) == 0x486E);
                const std::uint16_t flags = 256 | ((mode & 1) ? 4 : 0) | ((mode & 2) ? 2 : 0) |
                                            ((order == LSBFIRST) ? 16 : 0);
                assert(observed.operation == flags);
                assert(transmitted[0] == (order == LSBFIRST ? 0x34 : 0x12));
                assert(previous != observed_pointer);
                previous = observed_pointer;
                SPI.endTransaction();
            }
        }
    }
    else if (scenario == "mask" || scenario == "mask_begin_fail" || scenario == "mask_end_retry")
    {
        SpiInterruptMaskAdapter adapter{valid, suspend, restore};
        assert(registerSpiInterruptMaskAdapter(adapter));
        assert(!registerSpiInterruptMaskAdapter(adapter));
        SPI.usingInterrupt(1);
        SPI.usingInterrupt(2);
        SPI.usingInterrupt(1);
        if (scenario == "mask_begin_fail")
        {
            fail_suspend = 2;
            SPI.beginTransaction(SPISettings());
            expect(SpiError::interrupt_mask_error);
            assert(!spiTransactionActive() && restores == std::vector<int>{1});
            fail_suspend = -1;
            masks.clear();
            restores.clear();
        }
        SPI.beginTransaction(SPISettings());
        expect(SpiError::none);
        assert((masks == std::vector<int>{1, 2}));
        SPI.notUsingInterrupt(1);
        expect(SpiError::transaction_already_active);
        if (scenario == "mask_end_retry")
        {
            fail_restore = true;
            SPI.endTransaction();
            expect(SpiError::interrupt_mask_error);
            assert(spiTransactionActive());
            fail_restore = false;
            restores.clear();
        }
        SPI.endTransaction();
        assert((restores == std::vector<int>{2, 1}) && !spiTransactionActive());
        SPI.notUsingInterrupt(1);
        SPI.notUsingInterrupt(2);
    }
    else
    {
        SPI.beginTransaction(SPISettings());
        assert(spiTransactionActive());
        SPI.beginTransaction(SPISettings());
        expect(SpiError::transaction_already_active);
        if (scenario == "thread")
        {
            std::thread other(
                []()
                {
                    assert(SPI.transfer(1) == 0);
                    expect(SpiError::transaction_owner_mismatch);
                    SPI.endTransaction();
                    expect(SpiError::transaction_owner_mismatch);
                    SPI.end();
                    expect(SpiError::transaction_owner_mismatch);
                });
            other.join();
            assert(spiTransactionActive() && SPI.transfer(1) == (1 ^ 0x5A));
        }
        else if (scenario == "buffer")
        {
            SPI.transfer(nullptr, 1);
            expect(SpiError::invalid_buffer);
            std::uint8_t buffer[70]{};
            fail_transfer = 2;
            SPI.transfer(buffer, sizeof(buffer));
            expect(SpiError::driver_error);
            assert(transfer_calls == 2);
            for (unsigned index = 0; index < 70; ++index)
            {
                assert(buffer[index] == (index < 32 ? 0x5A : 0));
            }
            fail_transfer = 0;
        }
        else if (scenario == "driver")
        {
            fail_transfer = 1;
            assert(SPI.transfer16(0x1234) == 0);
            expect(SpiError::driver_error);
            assert(lastSpiDriverError() == -EIO);
            fail_transfer = 0;
            assert(SPI.transfer16(0x1234) == 0x486E);
            expect(SpiError::none);
        }
        else if (scenario == "isr")
        {
            mock_in_isr = true;
            SPI.begin();
            expect(SpiError::invalid_context);
            assert(SPI.transfer(1) == 0 && SPI.transfer16(1) == 0);
            SPI.endTransaction();
            SPI.end();
            expect(SpiError::invalid_context);
            mock_in_isr = false;
            assert(spiTransactionActive() && route_active && transfer_calls == 0);
        }
        SPI.endTransaction();
    }
    assert(!spiTransactionActive());
    if (scenario == "end_retry")
    {
        end_fails = true;
        SPI.end();
        expect(SpiError::route_error);
        assert(route_active);
        end_fails = false;
    }
    SPI.end();
    assert(!route_active);
    const int ended = deactivates;
    SPI.end();
    assert(deactivates == ended);
    SPI.begin();
    assert(route_active && activates == begin_count + 1);
    SPI.end();
}
