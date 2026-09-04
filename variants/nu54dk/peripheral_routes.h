/**
 * @file peripheral_routes.h
 * @brief NU54DK 논리 핀을 runtime 주변장치 pinctrl route로 변환합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_VARIANTS_NU54DK_PERIPHERAL_ROUTES_H_
#define NUCODE_ARDUINO_VARIANTS_NU54DK_PERIPHERAL_ROUTES_H_

#include "internal/RuntimePeripheralRoute.h"
#include "internal/pin_description.h"

#include <api/Common.h>

#include <zephyr/device.h>
#include <zephyr/drivers/pinctrl.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{
    /** @brief 하나의 보드 peripheral instance와 Zephyr 장치 설정을 연결합니다. */
    struct PeripheralRouteBinding
    {
        const struct device *device{nullptr};
        struct pinctrl_dev_config *pinctrl_config{nullptr};
        IoResourceOwner owner{};
        IoResourceKind block_kind{IoResourceKind::invalid};
        std::uint16_t block_index{0U};
        PinRoute required_route{PinRoute::none};
        bool available{false};
    };

    /** @brief NU54DK route 생성 오류입니다. */
    enum class PeripheralRouteBuildError : std::uint8_t
    {
        none = 0U,
        invalid_argument,
        invalid_pin,
        duplicate_pin,
        unsupported_route,
        unsupported_capability,
        reserved_pin,
        device_not_ready,
        unsupported_gpio_port,
    };

    /** @brief uart30 Serial1의 장치·ownership binding을 반환합니다. */
    [[nodiscard]] PeripheralRouteBinding serial1RouteBinding() noexcept;

    /** @brief i2c22 Wire의 장치·ownership binding을 반환합니다. */
    [[nodiscard]] PeripheralRouteBinding wireRouteBinding() noexcept;

    /** @brief spi00 SPI의 장치·ownership binding을 반환합니다. */
    [[nodiscard]] PeripheralRouteBinding spiRouteBinding() noexcept;

    /**
	 * @brief 논리 핀과 signal 배열을 검증해 default/sleep pinctrl을 생성합니다.
	 */
    [[nodiscard]] PeripheralRouteBuildError
    buildPeripheralRoute(PinRoute required_route, const pin_size_t *logical_pins,
                         const PeripheralSignal *signals, std::size_t pin_count,
                         PeripheralRouteConfiguration &configuration) noexcept;

    /** @brief 보드 DTS uart30_default의 RX/TX route를 생성합니다. */
    [[nodiscard]] PeripheralRouteBuildError
    defaultSerial1Route(PeripheralRouteConfiguration &configuration) noexcept;

    /** @brief 보드 DTS i2c22_default의 SDA/SCL route를 생성합니다. */
    [[nodiscard]] PeripheralRouteBuildError
    defaultWireRoute(PeripheralRouteConfiguration &configuration) noexcept;

    /** @brief 보드 DTS spi00_default의 SCK/MISO/MOSI route를 생성합니다. */
    [[nodiscard]] PeripheralRouteBuildError
    defaultSpiRoute(PeripheralRouteConfiguration &configuration) noexcept;

} // namespace nucode::arduino::internal

#endif
