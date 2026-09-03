/**
 * @file SerialFabric.h
 * @brief nRF54L15 공유 serial block을 안전하게 선택하는 v0.4 후보 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_NUCODE_SERIAL_FABRIC_H_
#define NUCODE_ARDUINO_CORE_NUCODE_SERIAL_FABRIC_H_

#include <api/Common.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino {
/** @brief 한 serial block에서 선택할 hardware personality입니다. */
enum class SerialPersonality : std::uint8_t {
  uarte = 0U,
  spim,
  spis,
  twim,
  twis,
};

/** @brief NU54DK가 승인한 serial pin bank입니다. */
enum class SerialRouteClass : std::uint8_t {
  p2_dedicated20 = 0U,
  p1_flexible,
  p0_flexible,
};

/** @brief 회로 경로의 전기적 전제조건을 명시합니다. */
enum class SerialElectricalProfile : std::uint8_t {
  connector_fixture = 0U,
  dap_uart_bridge,
  dap_uart_disabled,
  pmic_read_only,
};

/** @brief personality route의 신호 이름입니다. */
enum class SerialSignal : std::uint8_t {
  invalid = 0U,
  txd,
  rxd,
  rts,
  cts,
  sck,
  mosi,
  miso,
  csn,
  dcx,
  sda,
  scl,
};

/** @brief public lifecycle 상태입니다. */
enum class SerialFabricState : std::uint8_t {
  inactive = 0U,
  staged,
  activating,
  active,
  cancelling,
  faulted,
};

/** @brief EasyDMA buffer의 소유권 상태입니다. */
enum class DmaBufferState : std::uint8_t {
  application_owned = 0U,
  queued,
  dma_owned,
  completed,
  cancelled,
  error,
};

/** @brief serial-fabric 연산의 안정된 결과입니다. */
enum class SerialFabricResult : std::uint8_t {
  success = 0U,
  invalid_context,
  invalid_argument,
  unsupported_instance,
  unsupported_route,
  unsafe_electrical_profile,
  driver_unavailable,
  wrong_state,
  ownership_conflict,
  resource_exhausted,
  driver_error,
  stop_timeout,
  release_failed,
  faulted,
};

/** @brief 한 signal과 Arduino canonical pin을 연결합니다. */
struct SerialSignalPin {
  SerialSignal signal{SerialSignal::invalid};
  pin_size_t pin{0U};
};

/** @brief activate와 함께 lease할 application RAM 범위입니다. */
struct SerialDmaWorkspace {
  void *address{nullptr};
  std::size_t size{0U};
};

/** @brief allocation 없이 stage되는 완전한 route·DMA 설정입니다. */
struct SerialFabricConfiguration {
  SerialRouteClass route{SerialRouteClass::p1_flexible};
  SerialElectricalProfile electrical_profile{
      SerialElectricalProfile::connector_fixture};
  const SerialSignalPin *pins{nullptr};
  std::size_t pin_count{0U};
  const SerialDmaWorkspace *dma_workspaces{nullptr};
  std::size_t dma_workspace_count{0U};
};

class SerialFabric;

/** @brief 모든 typed handle이 공유하는 lifecycle 조회·제어 표면입니다. */
class SerialFabricHandle {
public:
  [[nodiscard]] SerialPersonality personality() const noexcept;
  [[nodiscard]] std::uint8_t instance() const noexcept;
  [[nodiscard]] SerialFabricState state() const noexcept;
  [[nodiscard]] SerialFabricResult lastResult() const noexcept;
  [[nodiscard]] int lastDriverError() const noexcept;

  [[nodiscard]] SerialFabricResult
  stage(const SerialFabricConfiguration &configuration) noexcept;
  [[nodiscard]] SerialFabricResult activate() noexcept;
  [[nodiscard]] SerialFabricResult
  deactivate(std::uint32_t timeout_us = 100000U) noexcept;

protected:
  constexpr SerialFabricHandle(SerialPersonality personality,
                               std::uint8_t instance,
                               std::uint8_t handle_index) noexcept
      : personality_(personality), instance_(instance),
        handle_index_(handle_index) {}

private:
  SerialPersonality personality_;
  std::uint8_t instance_;
  std::uint8_t handle_index_;
};

class UarteHandle final : public SerialFabricHandle {
  friend class SerialFabric;
  constexpr UarteHandle(std::uint8_t instance, std::uint8_t index) noexcept
      : SerialFabricHandle(SerialPersonality::uarte, instance, index) {}
};

class SpimHandle final : public SerialFabricHandle {
  friend class SerialFabric;
  constexpr SpimHandle(std::uint8_t instance, std::uint8_t index) noexcept
      : SerialFabricHandle(SerialPersonality::spim, instance, index) {}
};

class SpisHandle final : public SerialFabricHandle {
  friend class SerialFabric;
  constexpr SpisHandle(std::uint8_t instance, std::uint8_t index) noexcept
      : SerialFabricHandle(SerialPersonality::spis, instance, index) {}
};

class TwimHandle final : public SerialFabricHandle {
  friend class SerialFabric;
  constexpr TwimHandle(std::uint8_t instance, std::uint8_t index) noexcept
      : SerialFabricHandle(SerialPersonality::twim, instance, index) {}
};

class TwisHandle final : public SerialFabricHandle {
  friend class SerialFabric;
  constexpr TwisHandle(std::uint8_t instance, std::uint8_t index) noexcept
      : SerialFabricHandle(SerialPersonality::twis, instance, index) {}
};

/** @brief kind+instance selector만 허용하는 allocation-free factory입니다. */
class SerialFabric final {
public:
  [[nodiscard]] UarteHandle *uarte(std::uint8_t instance) noexcept;
  [[nodiscard]] SpimHandle *spim(std::uint8_t instance) noexcept;
  [[nodiscard]] SpisHandle *spis(std::uint8_t instance) noexcept;
  [[nodiscard]] TwimHandle *twim(std::uint8_t instance) noexcept;
  [[nodiscard]] TwisHandle *twis(std::uint8_t instance) noexcept;

private:
  friend SerialFabric &serialFabric() noexcept;
  SerialFabric() = default;
};

/** @brief process-wide static factory를 반환하며 hardware를 활성화하지
 * 않습니다. */
[[nodiscard]] SerialFabric &serialFabric() noexcept;
} // namespace nucode::arduino

#endif
