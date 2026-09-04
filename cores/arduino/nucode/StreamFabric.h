/**
 * @file StreamFabric.h
 * @brief PDM, I2S와 QDEC 전 instance를 노출하는 v0.4 후보 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_NUCODE_STREAM_FABRIC_H_
#define NUCODE_ARDUINO_CORE_NUCODE_STREAM_FABRIC_H_

#include <api/Common.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino {

/** @brief M25 stream fabric handle의 수명주기 상태입니다. */
enum class StreamFabricState : std::uint8_t {
  inactive = 0U,
  configured,
  active,
  stopping,
  faulted,
};

/** @brief M25 stream fabric 연산 결과입니다. */
enum class StreamFabricResult : std::uint8_t {
  success = 0U,
  invalid_context,
  invalid_argument,
  unsupported_instance,
  unsupported_route,
  wrong_state,
  ownership_conflict,
  resource_exhausted,
  driver_error,
  stop_timeout,
  release_failed,
  faulted,
};

/** @brief PDM20/21 입력 설정입니다. */
struct PdmConfiguration {
  pin_size_t clock_pin{0xFFU};
  pin_size_t data_pin{0xFFU};
  std::uint32_t sample_rate_hz{16000U};
  bool stereo{false};
  bool left_on_rising_edge{false};
};

/** @brief PDM 비동기 event 종류입니다. */
enum class PdmEventType : std::uint8_t {
  buffer_needed = 0U,
  buffer_complete,
  stopped,
  overflow,
  error,
};

/** @brief PDM 완료 queue에서 읽는 event입니다. */
struct PdmEvent {
  PdmEventType type{PdmEventType::error};
  std::int16_t *buffer{nullptr};
  std::size_t samples{0U};
  int driver_error{0};
};

/** @brief PDM20 또는 PDM21 연속 EasyDMA capture handle입니다. */
class PdmFabric {
public:
  [[nodiscard]] std::uint8_t instance() const noexcept;
  [[nodiscard]] StreamFabricState state() const noexcept;
  [[nodiscard]] StreamFabricResult lastResult() const noexcept;
  [[nodiscard]] int lastDriverError() const noexcept;

  [[nodiscard]] StreamFabricResult
  configure(const PdmConfiguration &configuration) noexcept;
  [[nodiscard]] StreamFabricResult start(std::int16_t *first_buffer,
                                         std::size_t samples) noexcept;
  [[nodiscard]] StreamFabricResult queueBuffer(std::int16_t *buffer,
                                               std::size_t samples) noexcept;
  [[nodiscard]] std::uintptr_t startTaskAddress() const noexcept;
  [[nodiscard]] StreamFabricResult
  stop(std::uint32_t timeout_us = 100000U) noexcept;
  [[nodiscard]] bool takeEvent(PdmEvent &event) noexcept;

private:
  friend class StreamFabric;
  constexpr explicit PdmFabric(std::uint8_t instance) noexcept
      : instance_(instance) {}

  std::uint8_t instance_;
};

/** @brief I2S20 sample 폭입니다. */
enum class I2sSampleWidth : std::uint8_t {
  bits8 = 8U,
  bits16 = 16U,
  bits24 = 24U,
  bits32 = 32U,
};

/** @brief I2S20 활성 channel입니다. */
enum class I2sChannels : std::uint8_t {
  stereo = 0U,
  left,
  right,
};

/** @brief I2S20 pin·clock 설정입니다. 0xFF pin은 연결하지 않습니다. */
struct I2sConfiguration {
  pin_size_t sck_pin{0xFFU};
  pin_size_t lrck_pin{0xFFU};
  pin_size_t mck_pin{0xFFU};
  pin_size_t data_out_pin{0xFFU};
  pin_size_t data_in_pin{0xFFU};
  std::uint32_t sample_rate_hz{48000U};
  I2sSampleWidth sample_width{I2sSampleWidth::bits16};
  I2sChannels channels{I2sChannels::stereo};
  bool master{true};
};

/** @brief 한 I2S20 transfer 구간의 TX/RX EasyDMA buffer입니다. */
struct I2sBuffers {
  std::uint32_t *receive{nullptr};
  const std::uint32_t *transmit{nullptr};
  std::size_t words{0U};
};

/** @brief I2S20 비동기 event 종류입니다. */
enum class I2sEventType : std::uint8_t {
  buffers_needed = 0U,
  buffers_complete,
  stopped,
  underrun,
  error,
};

/** @brief I2S20 완료 queue에서 읽는 event입니다. */
struct I2sEvent {
  I2sEventType type{I2sEventType::error};
  I2sBuffers released{};
  int driver_error{0};
};

/** @brief I2S20 full-duplex 연속 EasyDMA handle입니다. */
class I2sFabric {
public:
  [[nodiscard]] std::uint8_t instance() const noexcept;
  [[nodiscard]] StreamFabricState state() const noexcept;
  [[nodiscard]] StreamFabricResult lastResult() const noexcept;
  [[nodiscard]] int lastDriverError() const noexcept;

  [[nodiscard]] StreamFabricResult
  configure(const I2sConfiguration &configuration) noexcept;
  [[nodiscard]] StreamFabricResult start(const I2sBuffers &buffers) noexcept;
  [[nodiscard]] StreamFabricResult
  queueBuffers(const I2sBuffers &buffers) noexcept;
  [[nodiscard]] StreamFabricResult
  stop(std::uint32_t timeout_us = 100000U) noexcept;
  [[nodiscard]] bool takeEvent(I2sEvent &event) noexcept;

private:
  friend class StreamFabric;
  constexpr I2sFabric() noexcept = default;
};

/** @brief QDEC20/21 pin과 sampling 설정입니다. */
struct QdecConfiguration {
  pin_size_t phase_a_pin{0xFFU};
  pin_size_t phase_b_pin{0xFFU};
  pin_size_t led_pin{0xFFU};
  bool debounce{false};
  bool sample_events{false};
};

/** @brief QDEC 비동기 event 종류입니다. */
enum class QdecEventType : std::uint8_t {
  sample = 0U,
  report,
  error,
};

/** @brief QDEC event 또는 명시적 accumulator read 결과입니다. */
struct QdecEvent {
  QdecEventType type{QdecEventType::error};
  std::int32_t accumulated{0};
  std::uint32_t double_transitions{0U};
  int driver_error{0};
};

/** @brief QDEC20 또는 QDEC21 quadrature capture handle입니다. */
class QdecFabric {
public:
  [[nodiscard]] std::uint8_t instance() const noexcept;
  [[nodiscard]] StreamFabricState state() const noexcept;
  [[nodiscard]] StreamFabricResult lastResult() const noexcept;
  [[nodiscard]] int lastDriverError() const noexcept;

  [[nodiscard]] StreamFabricResult
  configure(const QdecConfiguration &configuration) noexcept;
  [[nodiscard]] StreamFabricResult start() noexcept;
  [[nodiscard]] StreamFabricResult read(QdecEvent &event) noexcept;
  [[nodiscard]] StreamFabricResult stop() noexcept;
  [[nodiscard]] bool takeEvent(QdecEvent &event) noexcept;

private:
  friend class StreamFabric;
  constexpr explicit QdecFabric(std::uint8_t instance) noexcept
      : instance_(instance) {}

  std::uint8_t instance_;
};

/** @brief M25 audio/encoder candidate handle factory입니다. */
class StreamFabric {
public:
  [[nodiscard]] PdmFabric *pdm(std::uint8_t instance) noexcept;
  [[nodiscard]] I2sFabric *i2s(std::uint8_t instance) noexcept;
  [[nodiscard]] QdecFabric *qdec(std::uint8_t instance) noexcept;

private:
  friend StreamFabric &streamFabric() noexcept;
  constexpr StreamFabric() noexcept = default;
};

/** @brief process-wide M25 stream fabric factory를 반환합니다. */
[[nodiscard]] StreamFabric &streamFabric() noexcept;

} // namespace nucode::arduino

#endif
