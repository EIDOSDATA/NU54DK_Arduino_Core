/**
 * @file peripheral_routes.cpp
 * @brief NU54DK peripheral route 검증과 nRF pinctrl 생성을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "peripheral_routes.h"

#include <variant.h>

#include <zephyr/devicetree.h>
#include <zephyr/dt-bindings/pinctrl/nrf-pinctrl.h>
#include <zephyr/sys/util.h>

#include <pinctrl_soc.h>

#include <cstddef>
#include <cstdint>

#if defined(CONFIG_PINCTRL_DYNAMIC)
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(uart30))
PINCTRL_DT_DEV_CONFIG_DECLARE(DT_NODELABEL(uart30));
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(i2c22))
PINCTRL_DT_DEV_CONFIG_DECLARE(DT_NODELABEL(i2c22));
#endif
#if defined(CONFIG_SPI) && DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(spi00))
PINCTRL_DT_DEV_CONFIG_DECLARE(DT_NODELABEL(spi00));
#endif
#endif

namespace nucode::arduino::internal
{
    namespace
    {
        /** @brief 논리 핀 탐색 실패를 나타내는 내부 sentinel입니다. */
        constexpr pin_size_t invalid_logical_pin = static_cast<pin_size_t>(-1);

        /** @brief GPIO controller 장치를 nRF port 번호로 변환합니다. */
        [[nodiscard]] int gpioPortNumber(const struct device *port) noexcept
        {
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio0))
            if (port == DEVICE_DT_GET(DT_NODELABEL(gpio0)))
            {
                return 0;
            }
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio1))
            if (port == DEVICE_DT_GET(DT_NODELABEL(gpio1)))
            {
                return 1;
            }
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio2))
            if (port == DEVICE_DT_GET(DT_NODELABEL(gpio2)))
            {
                return 2;
            }
#endif
            return -1;
        }

        /** @brief signal에 필요한 기본 GPIO capability를 검사합니다. */
        [[nodiscard]] bool supportsSignal(const PinDescription &description,
                                          PeripheralSignal signal) noexcept
        {
            switch (signal)
            {
            case PeripheralSignal::uart_rx:
                return hasPinCapability(description.capabilities, PinCapability::digital_input) ||
                       (description.policy == PinPolicy::conditional_dap_uart);
            case PeripheralSignal::spi_miso:
                return hasPinCapability(description.capabilities, PinCapability::digital_input);
            case PeripheralSignal::uart_tx:
                return hasPinCapability(description.capabilities, PinCapability::digital_output) ||
                       (description.policy == PinPolicy::conditional_dap_uart);
            case PeripheralSignal::spi_sck:
            case PeripheralSignal::spi_mosi:
                return hasPinCapability(description.capabilities, PinCapability::digital_output);
            case PeripheralSignal::pwm_out0:
            case PeripheralSignal::pwm_out1:
            case PeripheralSignal::pwm_out2:
            case PeripheralSignal::pwm_out3:
                return hasPinCapability(description.capabilities, PinCapability::digital_output) &&
                       hasPinCapability(description.capabilities, PinCapability::pwm_output);
            case PeripheralSignal::i2c_sda:
            case PeripheralSignal::i2c_scl:
                return hasPinCapability(description.capabilities, PinCapability::digital_input) &&
                       hasPinCapability(description.capabilities, PinCapability::digital_output) &&
                       hasPinCapability(description.capabilities, PinCapability::open_drain);
            default:
                return false;
            }
        }

        /** @brief nRF54L15 instance별 고정 port·signal route matrix를 검사합니다. */
        [[nodiscard]] bool routeMatrixAllows(PinRoute route, PeripheralSignal signal, int port,
                                             std::uint32_t pin) noexcept
        {
            if (route == PinRoute::uart30)
            {
                return (port == 0) && ((signal == PeripheralSignal::uart_rx) ||
                                       (signal == PeripheralSignal::uart_tx));
            }
            if (route == PinRoute::i2c22)
            {
                return (port == 1) && ((signal == PeripheralSignal::i2c_sda) ||
                                       (signal == PeripheralSignal::i2c_scl));
            }
            if (route == PinRoute::spi00)
            {
                switch (signal)
                {
                case PeripheralSignal::spi_sck:
                    return (port == 2) && (pin == 1U);
                case PeripheralSignal::spi_mosi:
                    return (port == 2) && (pin == 2U);
                case PeripheralSignal::spi_miso:
                    return (port == 2) && (pin == 4U);
                default:
                    return false;
                }
            }
            if ((route == PinRoute::pwm20) || (route == PinRoute::pwm21) ||
                (route == PinRoute::pwm22))
            {
                return (port == 1) && (signal >= PeripheralSignal::pwm_out0) &&
                       (signal <= PeripheralSignal::pwm_out3);
            }
            return false;
        }

        /** @brief signal과 nRF port/pin으로 default PSEL 값을 만듭니다. */
        [[nodiscard]] pinctrl_soc_pin_t defaultPsel(PeripheralSignal signal, int port,
                                                    std::uint32_t pin) noexcept
        {
            switch (signal)
            {
            case PeripheralSignal::uart_rx:
                return NRF_PSEL(UART_RX, port, pin) | (NRF_PULL_UP << NRF_PULL_POS);
            case PeripheralSignal::uart_tx:
                return NRF_PSEL(UART_TX, port, pin);
            case PeripheralSignal::i2c_sda:
                return NRF_PSEL(TWIM_SDA, port, pin);
            case PeripheralSignal::i2c_scl:
                return NRF_PSEL(TWIM_SCL, port, pin);
            case PeripheralSignal::spi_sck:
                return NRF_PSEL(SPIM_SCK, port, pin);
            case PeripheralSignal::spi_miso:
                return NRF_PSEL(SPIM_MISO, port, pin);
            case PeripheralSignal::spi_mosi:
                return NRF_PSEL(SPIM_MOSI, port, pin);
            case PeripheralSignal::pwm_out0:
                return NRF_PSEL(PWM_OUT0, port, pin);
            case PeripheralSignal::pwm_out1:
                return NRF_PSEL(PWM_OUT1, port, pin);
            case PeripheralSignal::pwm_out2:
                return NRF_PSEL(PWM_OUT2, port, pin);
            case PeripheralSignal::pwm_out3:
                return NRF_PSEL(PWM_OUT3, port, pin);
            default:
                return 0U;
            }
        }

        /** @brief physical nRF port/pin에 대응하는 canonical 논리 핀을 찾습니다. */
        [[nodiscard]] pin_size_t logicalPinForPhysical(std::uint32_t port, std::uint32_t pin,
                                                       PinRoute required_route) noexcept
        {
            for (std::size_t logical = 0U; logical < static_cast<std::size_t>(NUM_PIN_ROLES);
                 ++logical)
            {
                const PinDescription *const description = pinDescription(logical);
                if ((description == nullptr) || !hasPinRoute(description->routes, required_route))
                {
                    continue;
                }
                const int description_port = gpioPortNumber(description->gpio.port);
                if ((description_port == static_cast<int>(port)) && (description->gpio.pin == pin))
                {
                    return static_cast<pin_size_t>(description->canonical_pin);
                }
            }
            return invalid_logical_pin;
        }

        /** @brief DTS PSEL 값 하나를 canonical 논리 핀으로 변환합니다. */
        [[nodiscard]] pin_size_t logicalPinForPsel(std::uint32_t psel,
                                                   PinRoute required_route) noexcept
        {
            return logicalPinForPhysical(NRF_GET_PORT(psel), NRF_GET_PORT_PIN(psel),
                                         required_route);
        }
    } // namespace

    PeripheralRouteBinding serial1RouteBinding() noexcept
    {
#if defined(CONFIG_PINCTRL_DYNAMIC) && DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(uart30))
        return {DEVICE_DT_GET(DT_NODELABEL(uart30)),
                PINCTRL_DT_DEV_CONFIG_GET(DT_NODELABEL(uart30)),
                {IoOwnerKind::serial, 30U},
                IoResourceKind::serial_block,
                30U,
                PinRoute::uart30,
                true};
#else
        return {};
#endif
    }

    PeripheralRouteBinding wireRouteBinding() noexcept
    {
#if defined(CONFIG_PINCTRL_DYNAMIC) && DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(i2c22))
        return {DEVICE_DT_GET(DT_NODELABEL(i2c22)),
                PINCTRL_DT_DEV_CONFIG_GET(DT_NODELABEL(i2c22)),
                {IoOwnerKind::wire, 22U},
                IoResourceKind::serial_block,
                22U,
                PinRoute::i2c22,
                true};
#else
        return {};
#endif
    }

    PeripheralRouteBinding spiRouteBinding() noexcept
    {
        /** @brief DTS 활성 상태와 함께 실제 SPI driver의 device 생성 여부를 확인합니다. */
#if defined(CONFIG_SPI) && defined(CONFIG_PINCTRL_DYNAMIC) &&                                      \
    DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(spi00))
        return {DEVICE_DT_GET(DT_NODELABEL(spi00)),
                PINCTRL_DT_DEV_CONFIG_GET(DT_NODELABEL(spi00)),
                {IoOwnerKind::spi, 0U},
                IoResourceKind::serial_block,
                0U,
                PinRoute::spi00,
                true};
#else
        return {};
#endif
    }

    PeripheralRouteBuildError
    buildPeripheralRoute(PinRoute required_route, const pin_size_t *logical_pins,
                         const PeripheralSignal *signals, std::size_t pin_count,
                         PeripheralRouteConfiguration &configuration) noexcept
    {
        configuration = {};
        if ((required_route == PinRoute::none) || (logical_pins == nullptr) ||
            (signals == nullptr) || (pin_count == 0U) ||
            (pin_count > runtime_peripheral_route_pin_capacity))
        {
            return PeripheralRouteBuildError::invalid_argument;
        }

        for (std::size_t index = 0U; index < pin_count; ++index)
        {
            const std::size_t canonical = canonicalPinId(logical_pins[index]);
            if (canonical == SIZE_MAX)
            {
                return PeripheralRouteBuildError::invalid_pin;
            }
            for (std::size_t previous = 0U; previous < index; ++previous)
            {
                if (configuration.logical_pins[previous] == static_cast<pin_size_t>(canonical))
                {
                    return PeripheralRouteBuildError::duplicate_pin;
                }
            }

            const PinDescription *const description = pinDescription(canonical);
            if (description == nullptr)
            {
                return PeripheralRouteBuildError::invalid_pin;
            }
            if (!hasPinRoute(description->routes, required_route))
            {
                return PeripheralRouteBuildError::unsupported_route;
            }
            if (description->policy == PinPolicy::system_reserved)
            {
                return PeripheralRouteBuildError::reserved_pin;
            }
            if (!supportsSignal(*description, signals[index]))
            {
                return PeripheralRouteBuildError::unsupported_capability;
            }
            if (!device_is_ready(description->gpio.port))
            {
                return PeripheralRouteBuildError::device_not_ready;
            }

            const int port = gpioPortNumber(description->gpio.port);
            if (port < 0)
            {
                return PeripheralRouteBuildError::unsupported_gpio_port;
            }
            if (!routeMatrixAllows(required_route, signals[index], port, description->gpio.pin))
            {
                return PeripheralRouteBuildError::unsupported_route;
            }
            if ((required_route == PinRoute::i2c22) && (index > 0U))
            {
                const PinDescription *const first = pinDescription(configuration.logical_pins[0]);
                if ((first == nullptr) || (gpioPortNumber(first->gpio.port) != port))
                {
                    return PeripheralRouteBuildError::unsupported_route;
                }
            }
            const pinctrl_soc_pin_t psel = defaultPsel(signals[index], port, description->gpio.pin);

            configuration.logical_pins[index] = static_cast<pin_size_t>(canonical);
            configuration.signals[index] = signals[index];
            configuration.default_pins[index] = psel;
            configuration.sleep_pins[index] = psel | (NRF_LP_ENABLE << NRF_LP_POS);
        }
        configuration.pin_count = pin_count;
        return PeripheralRouteBuildError::none;
    }

    PeripheralRouteBuildError
    defaultSerial1Route(PeripheralRouteConfiguration &configuration) noexcept
    {
#if DT_NODE_EXISTS(DT_NODELABEL(uart30_default))
        constexpr std::uint32_t tx_psel =
            DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(uart30_default), group1), psels, 0);
        constexpr std::uint32_t rx_psel =
            DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(uart30_default), group2), psels, 0);
        const pin_size_t pins[] = {
            logicalPinForPsel(rx_psel, PinRoute::uart30),
            logicalPinForPsel(tx_psel, PinRoute::uart30),
        };
        if ((pins[0] == invalid_logical_pin) || (pins[1] == invalid_logical_pin))
        {
            return PeripheralRouteBuildError::invalid_pin;
        }
        const PeripheralSignal signals[] = {
            PeripheralSignal::uart_rx,
            PeripheralSignal::uart_tx,
        };
        return buildPeripheralRoute(PinRoute::uart30, pins, signals, ARRAY_SIZE(pins),
                                    configuration);
#else
        ARG_UNUSED(configuration);
        return PeripheralRouteBuildError::unsupported_route;
#endif
    }

    PeripheralRouteBuildError defaultWireRoute(PeripheralRouteConfiguration &configuration) noexcept
    {
#if DT_NODE_EXISTS(DT_NODELABEL(i2c22_default))
        constexpr std::uint32_t sda_psel =
            DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(i2c22_default), group1), psels, 0);
        constexpr std::uint32_t scl_psel =
            DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(i2c22_default), group1), psels, 1);
        const pin_size_t pins[] = {
            logicalPinForPsel(sda_psel, PinRoute::i2c22),
            logicalPinForPsel(scl_psel, PinRoute::i2c22),
        };
        if ((pins[0] == invalid_logical_pin) || (pins[1] == invalid_logical_pin))
        {
            return PeripheralRouteBuildError::invalid_pin;
        }
        const PeripheralSignal signals[] = {
            PeripheralSignal::i2c_sda,
            PeripheralSignal::i2c_scl,
        };
        return buildPeripheralRoute(PinRoute::i2c22, pins, signals, ARRAY_SIZE(pins),
                                    configuration);
#else
        ARG_UNUSED(configuration);
        return PeripheralRouteBuildError::unsupported_route;
#endif
    }

    PeripheralRouteBuildError defaultSpiRoute(PeripheralRouteConfiguration &configuration) noexcept
    {
#if DT_NODE_EXISTS(DT_NODELABEL(spi00_default))
        constexpr std::uint32_t sck_psel =
            DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(spi00_default), group1), psels, 0);
        constexpr std::uint32_t mosi_psel =
            DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(spi00_default), group1), psels, 1);
        constexpr std::uint32_t miso_psel =
            DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(spi00_default), group1), psels, 2);
        const pin_size_t pins[] = {
            logicalPinForPsel(sck_psel, PinRoute::spi00),
            logicalPinForPsel(miso_psel, PinRoute::spi00),
            logicalPinForPsel(mosi_psel, PinRoute::spi00),
        };
        if ((pins[0] == invalid_logical_pin) || (pins[1] == invalid_logical_pin) ||
            (pins[2] == invalid_logical_pin))
        {
            return PeripheralRouteBuildError::invalid_pin;
        }
        const PeripheralSignal signals[] = {
            PeripheralSignal::spi_sck,
            PeripheralSignal::spi_miso,
            PeripheralSignal::spi_mosi,
        };
        return buildPeripheralRoute(PinRoute::spi00, pins, signals, ARRAY_SIZE(pins),
                                    configuration);
#else
        ARG_UNUSED(configuration);
        return PeripheralRouteBuildError::unsupported_route;
#endif
    }

} // namespace nucode::arduino::internal
