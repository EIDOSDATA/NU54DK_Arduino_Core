/**
 * @file SpisFabric.cpp
 * @brief M24 SPIS00/20/21/22/30 double-buffer EasyDMA adapter입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>

#include "internal/SerialFabricBackend.h"
#include "serial_fabric_routes.h"

#include <nrfx_spis.h>

#include <zephyr/irq.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>

namespace nucode::arduino {
namespace {
using internal::SerialFabricDriverAdapter;
using internal::ValidatedSerialRoute;

inline constexpr std::size_t instance_count = 5U;
inline constexpr std::size_t event_capacity = 8U;
inline constexpr std::uint32_t event_queue_overflow = 0x80000000UL;

struct BufferPair {
  const void *tx{nullptr};
  std::size_t tx_size{0U};
  void *rx{nullptr};
  std::size_t rx_size{0U};
  DmaBufferState state{DmaBufferState::application_owned};
};

struct SpisContext {
  nrfx_spis_t driver;
  SpiFabricConfiguration configuration{};
  nrfx_spis_config_t driver_configuration{};
  ValidatedSerialRoute route{};
  BufferPair current{};
  BufferPair next{};
  SpiFabricEvent events[event_capacity]{};
  std::uint8_t event_head{0U};
  std::uint8_t event_tail{0U};
  std::uint8_t event_count{0U};
  bool event_overflow{false};
  atomic_t active{0};
  atomic_t buffers_active{0};
  atomic_t initialized{0};
  k_spinlock lock{};
};

SpisContext contexts[instance_count] = {
    {NRFX_SPIS_INSTANCE(NRF_SPIS00)}, {NRFX_SPIS_INSTANCE(NRF_SPIS20)},
    {NRFX_SPIS_INSTANCE(NRF_SPIS21)}, {NRFX_SPIS_INSTANCE(NRF_SPIS22)},
    {NRFX_SPIS_INSTANCE(NRF_SPIS30)},
};

[[nodiscard]] constexpr int instanceIndex(std::uint8_t instance) noexcept {
  switch (instance) {
  case 0U:
    return 0;
  case 20U:
    return 1;
  case 21U:
    return 2;
  case 22U:
    return 3;
  case 30U:
    return 4;
  default:
    return -1;
  }
}

[[nodiscard]] SpisContext *contextFor(std::uint8_t instance) noexcept {
  const int index = instanceIndex(instance);
  return index < 0 ? nullptr : &contexts[index];
}

[[nodiscard]] SerialFabricResult mapResult(int result) noexcept {
  switch (result) {
  case 0:
    return SerialFabricResult::success;
  case -EINVAL:
  case -EACCES:
  case -E2BIG:
    return SerialFabricResult::invalid_argument;
  case -EBUSY:
  case -EALREADY:
  case -EINPROGRESS:
    return SerialFabricResult::wrong_state;
  case -ENOMEM:
    return SerialFabricResult::resource_exhausted;
  default:
    return SerialFabricResult::driver_error;
  }
}

[[nodiscard]] bool rangeInside(const SerialDmaWorkspace &workspace,
                               const void *address, std::size_t size) noexcept {
  if ((address == nullptr) || (size == 0U))
    return false;
  const auto base = reinterpret_cast<std::uintptr_t>(workspace.address);
  const auto start = reinterpret_cast<std::uintptr_t>(address);
  if ((start < base) || (workspace.size > UINTPTR_MAX - base) ||
      (size > UINTPTR_MAX - start)) {
    return false;
  }
  return (start + size) <= (base + workspace.size);
}

[[nodiscard]] bool leasedBuffer(const SpisContext &context, const void *address,
                                std::size_t size) noexcept {
  if ((address == nullptr) && (size == 0U))
    return true;
  for (std::size_t index = 0U; index < context.route.dma_workspace_count;
       ++index) {
    if (rangeInside(context.route.dma_workspaces[index], address, size))
      return true;
  }
  return false;
}

[[nodiscard]] const SerialSignalPin *
signalPin(const ValidatedSerialRoute &route, SerialSignal signal) noexcept {
  for (std::size_t index = 0U; index < route.pin_count; ++index) {
    if (route.pins[index].signal == signal)
      return &route.pins[index];
  }
  return nullptr;
}

[[nodiscard]] bool pselFor(const ValidatedSerialRoute &route,
                           SerialSignal signal, std::uint32_t &psel) noexcept {
  const auto *const entry = signalPin(route, signal);
  return entry != nullptr &&
         internal::nu54dkSerialFabricPsel(entry->pin, psel) ==
             SerialFabricResult::success;
}

[[nodiscard]] bool spiMode(SpiFabricMode mode,
                           nrf_spis_mode_t &value) noexcept {
  switch (mode) {
  case SpiFabricMode::mode0:
    value = NRF_SPIS_MODE_0;
    return true;
  case SpiFabricMode::mode1:
    value = NRF_SPIS_MODE_1;
    return true;
  case SpiFabricMode::mode2:
    value = NRF_SPIS_MODE_2;
    return true;
  case SpiFabricMode::mode3:
    value = NRF_SPIS_MODE_3;
    return true;
  default:
    return false;
  }
}

void pushEvent(SpisContext &context, const SpiFabricEvent &event) noexcept {
  const k_spinlock_key_t key = k_spin_lock(&context.lock);
  if (context.event_count == event_capacity) {
    context.event_overflow = true;
  } else {
    context.events[context.event_tail] = event;
    context.event_tail =
        static_cast<std::uint8_t>((context.event_tail + 1U) % event_capacity);
    ++context.event_count;
  }
  k_spin_unlock(&context.lock, key);
}

void spisEvent(const nrfx_spis_event_t *event, void *opaque) {
  auto &context = *static_cast<SpisContext *>(opaque);
  if (event->evt_type == NRFX_SPIS_BUFFERS_SET_DONE) {
    pushEvent(context, {SpiFabricEventType::buffers_armed, context.current.tx,
                        context.current.rx, 0U, 0U, 0U});
    return;
  }
  if (event->evt_type != NRFX_SPIS_XFER_DONE)
    return;

  BufferPair completed{};
  BufferPair next{};
  {
    const k_spinlock_key_t key = k_spin_lock(&context.lock);
    completed = context.current;
    completed.state = DmaBufferState::completed;
    context.current = completed;
    next = context.next;
    context.next = {};
    k_spin_unlock(&context.lock, key);
  }
  pushEvent(context, {SpiFabricEventType::transfer_complete, event->p_tx_buf,
                      event->p_rx_buf, event->tx_amount, event->rx_amount, 0U});

  if ((next.tx != nullptr) || (next.rx != nullptr)) {
    const int result = nrfx_spis_buffers_set(
        &context.driver, static_cast<const std::uint8_t *>(next.tx),
        next.tx_size, static_cast<std::uint8_t *>(next.rx), next.rx_size);
    if (result == 0) {
      next.state = DmaBufferState::dma_owned;
      const k_spinlock_key_t key = k_spin_lock(&context.lock);
      context.current = next;
      k_spin_unlock(&context.lock, key);
      return;
    }
    next.state = DmaBufferState::error;
    const k_spinlock_key_t key = k_spin_lock(&context.lock);
    context.current = next;
    k_spin_unlock(&context.lock, key);
    pushEvent(context, {SpiFabricEventType::error, next.tx, next.rx, 0U, 0U,
                        static_cast<std::uint32_t>(-result)});
  }
  atomic_clear(&context.buffers_active);
  pushEvent(context,
            {SpiFabricEventType::buffer_needed, nullptr, nullptr, 0U, 0U, 0U});
}

SerialFabricResult validateAdapter(std::uint8_t instance,
                                   const ValidatedSerialRoute &route,
                                   int &driver_error) noexcept {
  driver_error = 0;
  auto *const context = contextFor(instance);
  std::uint32_t ignored = 0U;
  nrf_spis_mode_t mode{};
  if ((context == nullptr) || !spiMode(context->configuration.mode, mode) ||
      !pselFor(route, SerialSignal::sck, ignored) ||
      !pselFor(route, SerialSignal::mosi, ignored) ||
      !pselFor(route, SerialSignal::miso, ignored) ||
      !pselFor(route, SerialSignal::csn, ignored)) {
    return SerialFabricResult::invalid_argument;
  }
  return SerialFabricResult::success;
}

SerialFabricResult activateAdapter(std::uint8_t instance,
                                   const ValidatedSerialRoute &route,
                                   int &driver_error) noexcept {
  auto *const context = contextFor(instance);
  if (context == nullptr)
    return SerialFabricResult::unsupported_instance;
  std::uint32_t sck = 0U;
  std::uint32_t mosi = 0U;
  std::uint32_t miso = 0U;
  std::uint32_t csn = 0U;
  nrf_spis_mode_t mode{};
  if (!pselFor(route, SerialSignal::sck, sck) ||
      !pselFor(route, SerialSignal::mosi, mosi) ||
      !pselFor(route, SerialSignal::miso, miso) ||
      !pselFor(route, SerialSignal::csn, csn) ||
      !spiMode(context->configuration.mode, mode)) {
    return SerialFabricResult::invalid_argument;
  }
  context->driver_configuration =
      NRFX_SPIS_DEFAULT_CONFIG(sck, mosi, miso, csn);
  context->driver_configuration.mode = mode;
  context->driver_configuration.bit_order =
      context->configuration.bit_order == SpiFabricBitOrder::lsb_first
          ? NRF_SPIS_BIT_ORDER_LSB_FIRST
          : NRF_SPIS_BIT_ORDER_MSB_FIRST;
  context->driver_configuration.orc = context->configuration.overrun_character;
  driver_error = nrfx_spis_init(
      &context->driver, &context->driver_configuration, spisEvent, context);
  if (driver_error != 0)
    return mapResult(driver_error);
  context->route = route;
  context->current = {};
  context->next = {};
  context->event_head = 0U;
  context->event_tail = 0U;
  context->event_count = 0U;
  context->event_overflow = false;
  atomic_set(&context->initialized, 1);
  atomic_set(&context->active, 1);
  irq_enable(NRFX_IRQ_NUMBER_GET(context->driver.p_reg));
  return SerialFabricResult::success;
}

SerialFabricResult requestStopAdapter(std::uint8_t instance,
                                      int &driver_error) noexcept {
  auto *const context = contextFor(instance);
  if (context == nullptr)
    return SerialFabricResult::unsupported_instance;
  irq_disable(NRFX_IRQ_NUMBER_GET(context->driver.p_reg));
  if (atomic_get(&context->initialized) != 0) {
    nrfx_spis_uninit(&context->driver);
    atomic_clear(&context->initialized);
  }
  if (atomic_get(&context->buffers_active) != 0) {
    context->current.state = DmaBufferState::cancelled;
    context->next.state = DmaBufferState::cancelled;
    atomic_clear(&context->buffers_active);
  }
  driver_error = 0;
  return SerialFabricResult::success;
}

bool stoppedAdapter(std::uint8_t instance) noexcept {
  const auto *const context = contextFor(instance);
  return context != nullptr && atomic_get(&context->buffers_active) == 0 &&
         atomic_get(&context->initialized) == 0;
}

SerialFabricResult deactivateAdapter(std::uint8_t instance,
                                     int &driver_error) noexcept {
  auto *const context = contextFor(instance);
  if (context == nullptr)
    return SerialFabricResult::unsupported_instance;
  if (atomic_get(&context->initialized) != 0) {
    nrfx_spis_uninit(&context->driver);
    atomic_clear(&context->initialized);
  }
  atomic_clear(&context->active);
  context->route = {};
  context->current = {};
  context->next = {};
  driver_error = 0;
  return SerialFabricResult::success;
}

void handleIrq(std::uint8_t instance) noexcept {
  if (auto *const context = contextFor(instance))
    nrfx_spis_irq_handler(&context->driver);
}

const SerialFabricDriverAdapter adapter{validateAdapter,    activateAdapter,
                                        requestStopAdapter, stoppedAdapter,
                                        deactivateAdapter,  handleIrq};

int registerAdapters() {
  const std::uint8_t instances[] = {0U, 20U, 21U, 22U, 30U};
  for (const std::uint8_t instance : instances) {
    if (internal::registerSerialFabricAdapter(SerialPersonality::spis, instance,
                                              adapter) !=
        SerialFabricResult::success) {
      return -EIO;
    }
  }
  return 0;
}

SYS_INIT(registerAdapters, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
} // namespace

SerialFabricResult
SpisHandle::configure(const SpiFabricConfiguration &configuration) noexcept {
  if (k_is_in_isr())
    return SerialFabricResult::invalid_context;
  const auto current = state();
  nrf_spis_mode_t ignored{};
  if (((current != SerialFabricState::inactive) &&
       (current != SerialFabricState::staged)) ||
      !spiMode(configuration.mode, ignored)) {
    return SerialFabricResult::invalid_argument;
  }
  auto *const context = contextFor(instance());
  if (context == nullptr)
    return SerialFabricResult::unsupported_instance;
  context->configuration = configuration;
  return SerialFabricResult::success;
}

SerialFabricResult SpisHandle::queueBuffers(
    const void *tx_buffer, std::size_t tx_size, void *rx_buffer,
    std::size_t rx_size, const void *next_tx_buffer, std::size_t next_tx_size,
    void *next_rx_buffer, std::size_t next_rx_size) noexcept {
  if (k_is_in_isr())
    return SerialFabricResult::invalid_context;
  auto *const context = contextFor(instance());
  if ((context == nullptr) || !internal::isSerialFabricHandleActive(
                                  SerialPersonality::spis, instance())) {
    return SerialFabricResult::wrong_state;
  }
  const bool next_valid =
      (next_tx_buffer != nullptr) || (next_rx_buffer != nullptr);
  if (((tx_buffer == nullptr) != (tx_size == 0U)) ||
      ((rx_buffer == nullptr) != (rx_size == 0U)) ||
      ((tx_size == 0U) && (rx_size == 0U)) ||
      ((next_tx_buffer == nullptr) != (next_tx_size == 0U)) ||
      ((next_rx_buffer == nullptr) != (next_rx_size == 0U)) ||
      (tx_size > UINT16_MAX) || (rx_size > UINT16_MAX) ||
      (next_tx_size > UINT16_MAX) || (next_rx_size > UINT16_MAX) ||
      !leasedBuffer(*context, tx_buffer, tx_size) ||
      !leasedBuffer(*context, rx_buffer, rx_size) ||
      !leasedBuffer(*context, next_tx_buffer, next_tx_size) ||
      !leasedBuffer(*context, next_rx_buffer, next_rx_size) ||
      (next_valid && (next_tx_size == 0U) && (next_rx_size == 0U)) ||
      atomic_get(&context->buffers_active) != 0 ||
      atomic_get(&context->initialized) == 0) {
    return SerialFabricResult::invalid_argument;
  }
  {
    const k_spinlock_key_t key = k_spin_lock(&context->lock);
    context->current = {tx_buffer, tx_size, rx_buffer, rx_size,
                        DmaBufferState::dma_owned};
    context->next =
        next_valid ? BufferPair{next_tx_buffer, next_tx_size, next_rx_buffer,
                                next_rx_size, DmaBufferState::queued}
                   : BufferPair{};
    k_spin_unlock(&context->lock, key);
  }
  atomic_set(&context->buffers_active, 1);
  const int result = nrfx_spis_buffers_set(
      &context->driver, static_cast<const std::uint8_t *>(tx_buffer), tx_size,
      static_cast<std::uint8_t *>(rx_buffer), rx_size);
  if (result != 0) {
    atomic_clear(&context->buffers_active);
    context->current.state = DmaBufferState::error;
    context->next.state = DmaBufferState::error;
    return mapResult(result);
  }
  return SerialFabricResult::success;
}

SerialFabricResult SpisHandle::cancelBuffers() noexcept {
  if (k_is_in_isr())
    return SerialFabricResult::invalid_context;
  auto *const context = contextFor(instance());
  if ((context == nullptr) || atomic_get(&context->active) == 0 ||
      atomic_get(&context->buffers_active) == 0 ||
      atomic_get(&context->initialized) == 0) {
    return SerialFabricResult::wrong_state;
  }
  irq_disable(NRFX_IRQ_NUMBER_GET(context->driver.p_reg));
  nrfx_spis_uninit(&context->driver);
  atomic_clear(&context->initialized);
  context->current.state = DmaBufferState::cancelled;
  context->next.state = DmaBufferState::cancelled;
  atomic_clear(&context->buffers_active);
  const int result = nrfx_spis_init(
      &context->driver, &context->driver_configuration, spisEvent, context);
  if (result != 0) {
    pushEvent(*context, {SpiFabricEventType::error, context->current.tx,
                         context->current.rx, 0U, 0U,
                         static_cast<std::uint32_t>(-result)});
    return mapResult(result);
  }
  atomic_set(&context->initialized, 1);
  irq_enable(NRFX_IRQ_NUMBER_GET(context->driver.p_reg));
  pushEvent(*context, {SpiFabricEventType::transfer_cancelled,
                       context->current.tx, context->current.rx, 0U, 0U, 0U});
  return SerialFabricResult::success;
}

bool SpisHandle::takeEvent(SpiFabricEvent &event) noexcept {
  auto *const context = contextFor(instance());
  if (context == nullptr)
    return false;
  const k_spinlock_key_t key = k_spin_lock(&context->lock);
  if (context->event_overflow) {
    context->event_overflow = false;
    event = {SpiFabricEventType::error, nullptr, nullptr, 0U, 0U,
             event_queue_overflow};
    k_spin_unlock(&context->lock, key);
    return true;
  }
  if (context->event_count == 0U) {
    k_spin_unlock(&context->lock, key);
    return false;
  }
  event = context->events[context->event_head];
  context->event_head =
      static_cast<std::uint8_t>((context->event_head + 1U) % event_capacity);
  --context->event_count;
  k_spin_unlock(&context->lock, key);
  return true;
}

DmaBufferState SpisHandle::bufferState(const void *buffer) const noexcept {
  auto *const context = contextFor(instance());
  if (context == nullptr)
    return DmaBufferState::error;
  const k_spinlock_key_t key = k_spin_lock(&context->lock);
  DmaBufferState state = DmaBufferState::application_owned;
  if ((context->current.tx == buffer) || (context->current.rx == buffer))
    state = context->current.state;
  if ((context->next.tx == buffer) || (context->next.rx == buffer))
    state = context->next.state;
  k_spin_unlock(&context->lock, key);
  return state;
}
} // namespace nucode::arduino
