/**
 * @file serial_fabric_routes.cpp
 * @brief M24의 block·pin bank·전기 정책을 실행 가능한 validator로 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "serial_fabric_routes.h"

#include "internal/pin_description.h"

#include <variant.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal {
namespace {
[[nodiscard]] bool validInstance(SerialPersonality personality,
                                 std::uint8_t instance) noexcept {
  if ((personality == SerialPersonality::uarte) ||
      (personality == SerialPersonality::spim) ||
      (personality == SerialPersonality::spis)) {
    return (instance == 0U) || (instance == 20U) || (instance == 21U) ||
           (instance == 22U) || (instance == 30U);
  }
  return (instance == 20U) || (instance == 21U) || (instance == 22U) ||
         (instance == 30U);
}

[[nodiscard]] bool routeAllowsInstance(SerialRouteClass route,
                                       std::uint8_t instance) noexcept {
  switch (route) {
  case SerialRouteClass::p2_dedicated20:
    return (instance == 0U) || (instance == 20U);
  case SerialRouteClass::p1_flexible:
    return (instance == 20U) || (instance == 21U) || (instance == 22U);
  case SerialRouteClass::p0_flexible:
    return instance == 30U;
  default:
    return false;
  }
}

[[nodiscard]] int gpioPort(const struct device *device) noexcept {
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio0))
  if (device == DEVICE_DT_GET(DT_NODELABEL(gpio0)))
    return 0;
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio1))
  if (device == DEVICE_DT_GET(DT_NODELABEL(gpio1)))
    return 1;
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio2))
  if (device == DEVICE_DT_GET(DT_NODELABEL(gpio2)))
    return 2;
#endif
  return -1;
}

[[nodiscard]] bool isInputSignal(SerialSignal signal) noexcept {
  return (signal == SerialSignal::rxd) || (signal == SerialSignal::cts) ||
         (signal == SerialSignal::miso);
}

[[nodiscard]] bool isOutputSignal(SerialSignal signal) noexcept {
  return (signal == SerialSignal::txd) || (signal == SerialSignal::rts) ||
         (signal == SerialSignal::sck) || (signal == SerialSignal::mosi) ||
         (signal == SerialSignal::csn) || (signal == SerialSignal::dcx);
}

[[nodiscard]] bool isBidirectionalSignal(SerialSignal signal) noexcept {
  return (signal == SerialSignal::sda) || (signal == SerialSignal::scl);
}

[[nodiscard]] bool personalityAllowsSignal(SerialPersonality personality,
                                           SerialSignal signal) noexcept {
  switch (personality) {
  case SerialPersonality::uarte:
    return (signal == SerialSignal::txd) || (signal == SerialSignal::rxd) ||
           (signal == SerialSignal::rts) || (signal == SerialSignal::cts);
  case SerialPersonality::spim:
    return (signal == SerialSignal::sck) || (signal == SerialSignal::mosi) ||
           (signal == SerialSignal::miso) || (signal == SerialSignal::csn) ||
           (signal == SerialSignal::dcx);
  case SerialPersonality::spis:
    return (signal == SerialSignal::sck) || (signal == SerialSignal::mosi) ||
           (signal == SerialSignal::miso) || (signal == SerialSignal::csn);
  case SerialPersonality::twim:
  case SerialPersonality::twis:
    return isBidirectionalSignal(signal);
  default:
    return false;
  }
}

[[nodiscard]] bool hasRequiredSignals(SerialPersonality personality,
                                      std::uint16_t mask) noexcept {
  const auto signalBit = [](SerialSignal signal) {
    return static_cast<std::uint16_t>(1U << static_cast<std::uint8_t>(signal));
  };
  switch (personality) {
  case SerialPersonality::uarte:
    return (mask &
            (signalBit(SerialSignal::txd) | signalBit(SerialSignal::rxd))) ==
           (signalBit(SerialSignal::txd) | signalBit(SerialSignal::rxd));
  case SerialPersonality::spim:
    return (mask &
            (signalBit(SerialSignal::sck) | signalBit(SerialSignal::mosi) |
             signalBit(SerialSignal::miso))) ==
           (signalBit(SerialSignal::sck) | signalBit(SerialSignal::mosi) |
            signalBit(SerialSignal::miso));
  case SerialPersonality::spis:
    return (mask &
            (signalBit(SerialSignal::sck) | signalBit(SerialSignal::mosi) |
             signalBit(SerialSignal::miso) | signalBit(SerialSignal::csn))) ==
           (signalBit(SerialSignal::sck) | signalBit(SerialSignal::mosi) |
            signalBit(SerialSignal::miso) | signalBit(SerialSignal::csn));
  case SerialPersonality::twim:
  case SerialPersonality::twis:
    return (mask &
            (signalBit(SerialSignal::sda) | signalBit(SerialSignal::scl))) ==
           (signalBit(SerialSignal::sda) | signalBit(SerialSignal::scl));
  default:
    return false;
  }
}

[[nodiscard]] bool
electricalProfileAllowed(SerialPersonality personality, SerialRouteClass route,
                         SerialElectricalProfile profile) noexcept {
  if (route == SerialRouteClass::p2_dedicated20) {
    return profile == SerialElectricalProfile::connector_fixture;
  }
  if (route == SerialRouteClass::p0_flexible) {
    return personality == SerialPersonality::uarte
               ? profile == SerialElectricalProfile::dap_uart_bridge
               : profile == SerialElectricalProfile::dap_uart_disabled;
  }
  if ((personality == SerialPersonality::twim) ||
      (personality == SerialPersonality::twis)) {
    return (profile == SerialElectricalProfile::pmic_read_only) ||
           (profile == SerialElectricalProfile::connector_fixture);
  }
  return (profile == SerialElectricalProfile::dap_uart_bridge) ||
         (profile == SerialElectricalProfile::dap_uart_disabled) ||
         (profile == SerialElectricalProfile::connector_fixture);
}

[[nodiscard]] bool dedicatedPinMatches(SerialPersonality personality,
                                       SerialSignal signal,
                                       std::uint32_t pin) noexcept {
  if (personality == SerialPersonality::uarte) {
    switch (signal) {
    case SerialSignal::rxd:
      return pin == 0U;
    case SerialSignal::txd:
      return pin == 2U;
    case SerialSignal::cts:
      return pin == 4U;
    case SerialSignal::rts:
      return pin == 5U;
    default:
      return false;
    }
  }
  if (personality == SerialPersonality::spim) {
    switch (signal) {
    case SerialSignal::dcx:
      return pin == 0U;
    case SerialSignal::sck:
      return pin == 1U;
    case SerialSignal::mosi:
      return pin == 2U;
    case SerialSignal::miso:
      return pin == 4U;
    case SerialSignal::csn:
      return pin == 5U;
    default:
      return false;
    }
  }
  if (personality == SerialPersonality::spis) {
    switch (signal) {
    case SerialSignal::sck:
      return pin == 1U;
    case SerialSignal::miso:
      return pin == 2U;
    case SerialSignal::mosi:
      return pin == 4U;
    case SerialSignal::csn:
      return pin == 5U;
    default:
      return false;
    }
  }
  return false;
}

[[nodiscard]] bool
specialBoardRouteAllowed(SerialPersonality personality,
                         const PinDescription &description, SerialSignal signal,
                         SerialElectricalProfile profile) noexcept {
  const int port = gpioPort(description.gpio.port);
  const std::uint32_t pin = description.gpio.pin;
  if ((port == 1) && (pin >= 4U) && (pin <= 7U)) {
    return personality == SerialPersonality::uarte
               ? profile == SerialElectricalProfile::dap_uart_bridge
               : profile == SerialElectricalProfile::dap_uart_disabled;
  }
  if ((port == 1) && ((pin == 2U) || (pin == 3U))) {
    return ((personality == SerialPersonality::twim) ||
            (personality == SerialPersonality::twis)) &&
           isBidirectionalSignal(signal);
  }
  if ((description.policy == PinPolicy::input_only) ||
      (description.policy == PinPolicy::system_reserved) ||
      (description.policy == PinPolicy::conditional_lfxo)) {
    return false;
  }
  return true;
}
} // namespace

SerialFabricResult validateNu54dkSerialFabricRoute(
    SerialPersonality personality, std::uint8_t instance,
    const SerialFabricConfiguration &configuration, ValidatedSerialRoute &route,
    IoResourceId *resources, std::size_t resource_capacity,
    std::size_t &resource_count) noexcept {
  route = {};
  resource_count = 0U;
  if (!validInstance(personality, instance)) {
    return SerialFabricResult::unsupported_instance;
  }
  if (!routeAllowsInstance(configuration.route, instance) ||
      (configuration.pins == nullptr) || (configuration.pin_count == 0U) ||
      (configuration.pin_count > serial_fabric_pin_capacity) ||
      (configuration.dma_workspace_count >
       serial_fabric_dma_workspace_capacity) ||
      ((configuration.dma_workspace_count != 0U) &&
       (configuration.dma_workspaces == nullptr))) {
    return SerialFabricResult::invalid_argument;
  }
  if (!electricalProfileAllowed(personality, configuration.route,
                                configuration.electrical_profile)) {
    return SerialFabricResult::unsafe_electrical_profile;
  }

  const std::size_t fixed_resources =
      2U + ((configuration.route == SerialRouteClass::p2_dedicated20 &&
             instance == 20U)
                ? 1U
                : 0U);
  const std::size_t total_resources = fixed_resources +
                                      configuration.pin_count +
                                      configuration.dma_workspace_count;
  if ((resources == nullptr) || (resource_capacity < total_resources)) {
    return SerialFabricResult::resource_exhausted;
  }

  resources[resource_count++] =
      peripheralIoResource(IoResourceKind::serial_block, instance);
  resources[resource_count++] =
      peripheralIoResource(IoResourceKind::interrupt_line, instance);
  if (fixed_resources == 3U) {
    resources[resource_count++] =
        peripheralIoResource(IoResourceKind::power_domain, 20U);
  }

  std::uint16_t signal_mask = 0U;
  for (std::size_t index = 0U; index < configuration.pin_count; ++index) {
    const auto entry = configuration.pins[index];
    const std::uint8_t signal_value = static_cast<std::uint8_t>(entry.signal);
    if ((entry.signal == SerialSignal::invalid) || (signal_value >= 16U) ||
        !personalityAllowsSignal(personality, entry.signal) ||
        ((signal_mask & (1U << signal_value)) != 0U)) {
      return SerialFabricResult::invalid_argument;
    }
    const PinDescription *const description = pinDescription(entry.pin);
    if ((description == nullptr) || !device_is_ready(description->gpio.port)) {
      return SerialFabricResult::unsupported_route;
    }
    const int expected_port =
        configuration.route == SerialRouteClass::p0_flexible   ? 0
        : configuration.route == SerialRouteClass::p1_flexible ? 1
                                                               : 2;
    if (gpioPort(description->gpio.port) != expected_port) {
      return SerialFabricResult::unsupported_route;
    }
    if ((configuration.route == SerialRouteClass::p2_dedicated20) &&
        !dedicatedPinMatches(personality, entry.signal,
                             description->gpio.pin)) {
      return SerialFabricResult::unsupported_route;
    }
    if ((configuration.route != SerialRouteClass::p2_dedicated20) &&
        !specialBoardRouteAllowed(personality, *description, entry.signal,
                                  configuration.electrical_profile)) {
      return SerialFabricResult::unsafe_electrical_profile;
    }
    if ((isInputSignal(entry.signal) &&
         !hasPinCapability(description->capabilities,
                           PinCapability::digital_input) &&
         description->policy != PinPolicy::conditional_dap_uart) ||
        (isOutputSignal(entry.signal) &&
         !hasPinCapability(description->capabilities,
                           PinCapability::digital_output) &&
         description->policy != PinPolicy::conditional_dap_uart) ||
        (isBidirectionalSignal(entry.signal) &&
         (!hasPinCapability(description->capabilities,
                            PinCapability::digital_input) ||
          !hasPinCapability(description->capabilities,
                            PinCapability::digital_output) ||
          !hasPinCapability(description->capabilities,
                            PinCapability::open_drain)))) {
      return SerialFabricResult::unsupported_route;
    }
    for (std::size_t prior = 0U; prior < index; ++prior) {
      if (canonicalPinId(configuration.pins[prior].pin) ==
          description->canonical_pin) {
        return SerialFabricResult::invalid_argument;
      }
    }
    signal_mask =
        static_cast<std::uint16_t>(signal_mask | (1U << signal_value));
    route.pins[index] = {entry.signal,
                         static_cast<pin_size_t>(description->canonical_pin)};
    resources[resource_count++] = gpioIoResource(description->gpio);
  }
  if (!hasRequiredSignals(personality, signal_mask)) {
    return SerialFabricResult::invalid_argument;
  }

  for (std::size_t index = 0U; index < configuration.dma_workspace_count;
       ++index) {
    const auto workspace = configuration.dma_workspaces[index];
    if ((workspace.address == nullptr) || (workspace.size == 0U) ||
        (workspace.size > UINT32_MAX)) {
      return SerialFabricResult::invalid_argument;
    }
    route.dma_workspaces[index] = workspace;
    resources[resource_count++] = dmaMemoryIoResource(
        workspace.address, static_cast<std::uint32_t>(workspace.size));
  }

  route.pin_count = configuration.pin_count;
  route.dma_workspace_count = configuration.dma_workspace_count;
  route.route = configuration.route;
  route.electrical_profile = configuration.electrical_profile;
  return SerialFabricResult::success;
}
} // namespace nucode::arduino::internal
