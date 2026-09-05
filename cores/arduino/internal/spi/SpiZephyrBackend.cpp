/**
 * @file SpiZephyrBackend.cpp
 * @brief SPI00 device·runtime route·주파수·driver configuration을 단일 소유합니다.
 * SPDX-License-Identifier: MIT
 */
#include "internal/spi/SpiBackendOperations.h"
#include "internal/RuntimePeripheralRoute.h"
#include <peripheral_routes.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/spi.h>
#if !DT_HAS_CHOSEN(nucode_arduino_spi)
#error "SPI에는 app overlay의 nucode,arduino-spi chosen controller가 필요합니다."
#endif

#define NUCODE_ARDUINO_SPI_NODE DT_CHOSEN(nucode_arduino_spi)

#if !DT_NODE_HAS_STATUS_OKAY(NUCODE_ARDUINO_SPI_NODE)
#error "nucode,arduino-spi chosen controller가 활성화되어 있지 않습니다."
#endif

#if !DT_NODE_EXISTS(DT_NODELABEL(spi00))
#error "NU54DK SPI 구현에는 spi00 Devicetree node가 필요합니다."
#elif !DT_SAME_NODE(NUCODE_ARDUINO_SPI_NODE, DT_NODELABEL(spi00)) &&                               \
    !defined(NUCODE_ARDUINO_SPI_TEST_ALLOW_NON_SPI00)
#error                                                                                             \
    "NUCODE_M7_SPI_CHOSEN_MUST_BE_SPI00: NU54DK nucode,arduino-spi chosen은 SPI00을 가리켜야 합니다."
#endif

#if DT_NODE_EXISTS(DT_NODELABEL(spi00)) && DT_NODE_EXISTS(DT_NODELABEL(uart00))
#if DT_SAME_NODE(NUCODE_ARDUINO_SPI_NODE, DT_NODELABEL(spi00)) &&                                  \
    DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(uart00))
#error                                                                                             \
    "NUCODE_M7_SPI_UART00_CONFLICT: NU54DK spi00과 uart00은 같은 하드웨어 자원을 공유하므로 동시에 활성화할 수 없습니다."
#endif
#endif

namespace nucode::arduino::internal::spi_backend
{
    namespace
    {
        /** @brief NU54DK chosen SPI controller가 선언한 최대 SCK 속도입니다. */
        constexpr std::uint32_t maximum_spi_frequency_hz =
            DT_PROP_OR(NUCODE_ARDUINO_SPI_NODE, max_frequency, 32000000U);

        /** @brief NU54DK SPI00의 고정 SPIM base clock입니다. */
        constexpr std::uint32_t spi_base_frequency_hz = 128000000U;

        /** @brief nRF54L15 SPI00이 허용하는 가장 작은 prescaler입니다. */
        constexpr std::uint32_t minimum_spi_prescaler = 4U;

        /** @brief nRF54L15 SPI00이 허용하는 가장 큰 prescaler입니다. */
        constexpr std::uint32_t maximum_spi_prescaler = 126U;

        /** @brief 보드 overlay가 선택한 SPI controller입니다. */
        const struct device *const spi_device = DEVICE_DT_GET(NUCODE_ARDUINO_SPI_NODE);
        const nucode::arduino::internal::PeripheralRouteBinding spi_binding =
            nucode::arduino::internal::spiRouteBinding();
        nucode::arduino::internal::RuntimePeripheralRoute
            spi_route(spi_binding.device, spi_binding.pinctrl_config, spi_binding.owner,
                      spi_binding.block_kind, spi_binding.block_index);
        bool spi_route_staged = false;

        bool spi_started = false;
        struct spi_config spi_configurations[2] = {};
        std::size_t active_configuration_index = 0U;
        const struct spi_config *active_configuration = nullptr;
        /**
	 * @brief Arduino SPI mode를 Zephyr operation flag로 변환합니다.
	 *
	 * @param mode Arduino SPI mode입니다.
	 * @param flags 변환 결과를 받을 주소입니다.
	 * @return mode 0~3이면 true입니다.
	 */
        [[nodiscard]] bool modeFlags(::arduino::SPIMode mode, spi_operation_t &flags) noexcept
        {
            switch (mode)
            {
            case ::arduino::SPI_MODE0:
                flags = 0U;
                return true;
            case ::arduino::SPI_MODE1:
                flags = SPI_MODE_CPHA;
                return true;
            case ::arduino::SPI_MODE2:
                flags = SPI_MODE_CPOL;
                return true;
            case ::arduino::SPI_MODE3:
                flags = SPI_MODE_CPOL | SPI_MODE_CPHA;
                return true;
            default:
                return false;
            }
        }
    } // namespace
    /**
	 * @brief 요청한 SCK를 SPI00 prescaler 규칙으로 표현할 수 있는지 확인합니다.
	 *
	 * Core가 임의의 근사값을 선택하지 않도록 nRF54L15 nrfx driver와 같은
	 * predicate를 선제 적용합니다. SPI00은 128 MHz base clock과 4~126
	 * 범위의 짝수 prescaler를 사용합니다.
	 *
	 * @param frequency 요청한 SCK 속도입니다.
	 * @return 실제 hardware driver가 허용하는 값이면 true입니다.
	 */
    [[nodiscard]] bool frequencySupported(std::uint32_t frequency) noexcept
    {
        if ((frequency == 0U) || (frequency > maximum_spi_frequency_hz))
        {
            return false;
        }

        const std::uint32_t prescaler = spi_base_frequency_hz / frequency;
        return ((spi_base_frequency_hz % frequency) < prescaler) && ((prescaler % 2U) == 0U) &&
               (prescaler >= minimum_spi_prescaler) && (prescaler <= maximum_spi_prescaler);
    }
    bool setPins(pin_size_t sck_pin, pin_size_t miso_pin, pin_size_t mosi_pin) noexcept
    {
        const pin_size_t pins[]{sck_pin, miso_pin, mosi_pin};
        const nucode::arduino::internal::PeripheralSignal signals[]{
            nucode::arduino::internal::PeripheralSignal::spi_sck,
            nucode::arduino::internal::PeripheralSignal::spi_miso,
            nucode::arduino::internal::PeripheralSignal::spi_mosi,
        };
        nucode::arduino::internal::PeripheralRouteConfiguration configuration{};
        const auto result = nucode::arduino::internal::buildPeripheralRoute(
            nucode::arduino::internal::PinRoute::spi00, pins, signals, 3U, configuration);
        const bool staged =
            (result == nucode::arduino::internal::PeripheralRouteBuildError::none) &&
            spi_route.stage(configuration);
        if (staged)
        {
            spi_route_staged = true;
        }
        recordSpiError(staged ? SpiError::none : SpiError::invalid_pin_route,
                       staged ? 0 : static_cast<int>(result));
        return staged;
    }
    void begin() noexcept
    {
        if (!spi_binding.available)
        {
            recordSpiError(SpiError::route_error);
        }
        else
        {
            if (!spi_route_staged)
            {
                nucode::arduino::internal::PeripheralRouteConfiguration route{};
                spi_route_staged = nucode::arduino::internal::defaultSpiRoute(route) ==
                                       nucode::arduino::internal::PeripheralRouteBuildError::none &&
                                   spi_route.stage(route);
            }
            if (!spi_route_staged || !spi_route.activate())
            {
                recordSpiError(SpiError::route_error, spi_route.lastDriverError());
            }
            else if (!device_is_ready(spi_device))
            {
                static_cast<void>(spi_route.deactivate());
                recordSpiError(SpiError::device_not_ready);
            }
            else
            {
                spi_started = true;
                recordSpiSuccess();
            }
        }
    }
    bool end() noexcept
    {
        const bool route_present = spi_started || spi_route.active() || spi_route.faulted();
        const bool route_ok = !route_present || spi_route.deactivate();
        spi_started = !route_ok && spi_route.active();
        if (!route_ok)
        {
            recordSpiError(SpiError::route_error, spi_route.lastDriverError());
        }
        return route_ok;
    }

    void configureValidated(const ::arduino::SPISettings &settings) noexcept
    {
        auto &configuration = spi_configurations[active_configuration_index];
        spi_operation_t mode_flags = 0U;
        static_cast<void>(modeFlags(settings.getDataMode(), mode_flags));
        configuration = {};
        configuration.frequency = settings.getClockFreq();
        configuration.operation =
            SPI_OP_MODE_MASTER | SPI_WORD_SET(8) | mode_flags |
            ((settings.getBitOrder() == LSBFIRST) ? SPI_TRANSFER_LSB : SPI_TRANSFER_MSB);
        configuration.slave = 0U;
        configuration.cs = {};
        configuration.word_delay = 0U;
    }
    /**
	 * @brief 현재 transaction 설정으로 full-duplex byte block을 전송합니다.
	 *
	 * @param transmit 송신 buffer입니다.
	 * @param receive 수신 buffer입니다.
	 * @param length buffer 길이입니다.
	 * @return 성공하면 true입니다.
	 */
    [[nodiscard]] bool transferBlock(const std::uint8_t *transmit, std::uint8_t *receive,
                                     std::size_t length) noexcept
    {
        if (length == 0U)
        {
            recordSpiSuccess();
            return true;
        }

        struct spi_buf tx_buffer = {};
        tx_buffer.buf = const_cast<std::uint8_t *>(transmit);
        tx_buffer.len = length;
        struct spi_buf_set tx_set = {};
        tx_set.buffers = &tx_buffer;
        tx_set.count = 1U;
        struct spi_buf rx_buffer = {};
        rx_buffer.buf = receive;
        rx_buffer.len = length;
        struct spi_buf_set rx_set = {};
        rx_set.buffers = &rx_buffer;
        rx_set.count = 1U;

        const int result = spi_transceive(spi_device, active_configuration, &tx_set, &rx_set);
        if (result < 0)
        {
            recordSpiError(SpiError::driver_error, result);
            return false;
        }

        recordSpiSuccess();
        return true;
    }
    bool started() noexcept
    {
        return spi_started;
    }
    void advanceConfiguration() noexcept
    {
        active_configuration_index ^= 1U;
    }
    void commitConfiguration() noexcept
    {
        active_configuration = &spi_configurations[active_configuration_index];
    }
    void clearConfiguration() noexcept
    {
        active_configuration = nullptr;
    }
    bool configurationReady() noexcept
    {
        return active_configuration != nullptr;
    }
} // namespace nucode::arduino::internal::spi_backend
#undef NUCODE_ARDUINO_SPI_NODE
