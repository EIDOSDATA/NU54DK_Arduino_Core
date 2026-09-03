/**
 * @file SerialFabric.cpp
 * @brief M24 Serial Fabric의 allocation-free factory와 공통 handover
 * 상태기계입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/SerialFabric.h>

#include "internal/IoResourceManager.h"
#include "internal/SerialFabricBackend.h"
#include "serial_fabric_routes.h"

#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino {
namespace {
using internal::IoAcquirePolicy;
using internal::IoOwnerKind;
using internal::IoResourceId;
using internal::IoResourceLease;
using internal::IoResourceResult;
using internal::SerialFabricDriverAdapter;
using internal::ValidatedSerialRoute;

inline constexpr std::size_t handle_count = 23U;
inline constexpr std::size_t block_count = 5U;

struct HandleContext {
  ValidatedSerialRoute route{};
  IoResourceId resources[internal::io_resource_lease_capacity]{};
  std::size_t resource_count{0U};
  IoResourceLease lease{};
  const SerialFabricDriverAdapter *adapter{nullptr};
  SerialFabricState state{SerialFabricState::inactive};
  SerialFabricResult last_result{SerialFabricResult::success};
  int last_driver_error{0};
};

struct BlockContext {
  bool faulted{false};
  atomic_ptr_t active_adapter{nullptr};
  std::uint8_t active_instance{0U};
};

K_MUTEX_DEFINE(fabric_mutex);
HandleContext contexts[handle_count]{};
SerialFabricDriverAdapter adapters[handle_count]{};
bool adapter_registered[handle_count]{};
BlockContext blocks[block_count]{};

[[nodiscard]] constexpr int blockIndex(std::uint8_t instance) noexcept {
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

[[nodiscard]] constexpr int handleIndex(SerialPersonality personality,
                                        std::uint8_t instance) noexcept {
  const int block = blockIndex(instance);
  if (block < 0)
    return -1;
  switch (personality) {
  case SerialPersonality::uarte:
    return block;
  case SerialPersonality::spim:
    return 5 + block;
  case SerialPersonality::spis:
    return 10 + block;
  case SerialPersonality::twim:
    return instance == 0U ? -1 : 14 + block;
  case SerialPersonality::twis:
    return instance == 0U ? -1 : 18 + block;
  default:
    return -1;
  }
}

[[nodiscard]] constexpr IoOwnerKind
ownerKind(SerialPersonality personality) noexcept {
  switch (personality) {
  case SerialPersonality::uarte:
    return IoOwnerKind::serial;
  case SerialPersonality::spim:
  case SerialPersonality::spis:
    return IoOwnerKind::spi;
  case SerialPersonality::twim:
  case SerialPersonality::twis:
    return IoOwnerKind::wire;
  default:
    return IoOwnerKind::none;
  }
}

[[nodiscard]] SerialFabricResult
mapResourceResult(IoResourceResult result) noexcept {
  switch (result) {
  case IoResourceResult::success:
    return SerialFabricResult::success;
  case IoResourceResult::invalid_context:
    return SerialFabricResult::invalid_context;
  case IoResourceResult::invalid_argument:
    return SerialFabricResult::invalid_argument;
  case IoResourceResult::conflict:
    return SerialFabricResult::ownership_conflict;
  case IoResourceResult::capacity_exhausted:
    return SerialFabricResult::resource_exhausted;
  default:
    return SerialFabricResult::release_failed;
  }
}

void record(HandleContext &context, SerialFabricResult result,
            int driver_error = 0) noexcept {
  context.last_result = result;
  context.last_driver_error = driver_error;
}

void latchFault(HandleContext &context, int block, SerialFabricResult result,
                int driver_error) noexcept {
  context.state = SerialFabricState::faulted;
  blocks[block].faulted = true;
  record(context, result, driver_error);
}

[[nodiscard]] HandleContext &contextAt(std::uint8_t index) noexcept {
  return contexts[index];
}
} // namespace

SerialPersonality SerialFabricHandle::personality() const noexcept {
  return personality_;
}

std::uint8_t SerialFabricHandle::instance() const noexcept { return instance_; }

SerialFabricState SerialFabricHandle::state() const noexcept {
  k_mutex_lock(&fabric_mutex, K_FOREVER);
  const auto value = contextAt(handle_index_).state;
  k_mutex_unlock(&fabric_mutex);
  return value;
}

SerialFabricResult SerialFabricHandle::lastResult() const noexcept {
  k_mutex_lock(&fabric_mutex, K_FOREVER);
  const auto value = contextAt(handle_index_).last_result;
  k_mutex_unlock(&fabric_mutex);
  return value;
}

int SerialFabricHandle::lastDriverError() const noexcept {
  k_mutex_lock(&fabric_mutex, K_FOREVER);
  const int value = contextAt(handle_index_).last_driver_error;
  k_mutex_unlock(&fabric_mutex);
  return value;
}

SerialFabricResult SerialFabricHandle::stage(
    const SerialFabricConfiguration &configuration) noexcept {
  if (k_is_in_isr())
    return SerialFabricResult::invalid_context;
  k_mutex_lock(&fabric_mutex, K_FOREVER);
  auto &context = contextAt(handle_index_);
  const int block = blockIndex(instance_);
  if ((block < 0) || blocks[block].faulted ||
      (context.state == SerialFabricState::faulted)) {
    record(context, SerialFabricResult::faulted);
    k_mutex_unlock(&fabric_mutex);
    return SerialFabricResult::faulted;
  }
  if ((context.state != SerialFabricState::inactive) &&
      (context.state != SerialFabricState::staged)) {
    record(context, SerialFabricResult::wrong_state);
    k_mutex_unlock(&fabric_mutex);
    return SerialFabricResult::wrong_state;
  }
  if (!adapter_registered[handle_index_]) {
    record(context, SerialFabricResult::driver_unavailable);
    k_mutex_unlock(&fabric_mutex);
    return SerialFabricResult::driver_unavailable;
  }

  ValidatedSerialRoute candidate{};
  IoResourceId resources[internal::io_resource_lease_capacity]{};
  std::size_t resource_count = 0U;
  SerialFabricResult result = internal::validateNu54dkSerialFabricRoute(
      personality_, instance_, configuration, candidate, resources,
      internal::io_resource_lease_capacity, resource_count);
  int driver_error = 0;
  if (result == SerialFabricResult::success) {
    result =
        adapters[handle_index_].validate(instance_, candidate, driver_error);
  }
  if (result != SerialFabricResult::success) {
    record(context, result, driver_error);
    k_mutex_unlock(&fabric_mutex);
    return result;
  }

  context.route = candidate;
  context.resource_count = resource_count;
  for (std::size_t index = 0U; index < resource_count; ++index) {
    context.resources[index] = resources[index];
  }
  context.adapter = &adapters[handle_index_];
  context.state = SerialFabricState::staged;
  record(context, SerialFabricResult::success);
  k_mutex_unlock(&fabric_mutex);
  return SerialFabricResult::success;
}

SerialFabricResult SerialFabricHandle::activate() noexcept {
  if (k_is_in_isr())
    return SerialFabricResult::invalid_context;
  k_mutex_lock(&fabric_mutex, K_FOREVER);
  auto &context = contextAt(handle_index_);
  const int block = blockIndex(instance_);
  if ((block < 0) || blocks[block].faulted ||
      (context.state == SerialFabricState::faulted)) {
    record(context, SerialFabricResult::faulted);
    k_mutex_unlock(&fabric_mutex);
    return SerialFabricResult::faulted;
  }
  if ((context.state != SerialFabricState::staged) ||
      (context.adapter == nullptr)) {
    record(context, SerialFabricResult::wrong_state);
    k_mutex_unlock(&fabric_mutex);
    return SerialFabricResult::wrong_state;
  }

  context.lease = {};
  const IoResourceResult reserve_result = internal::reserveIoResources(
      {ownerKind(personality_), instance_}, context.resources,
      context.resource_count, IoAcquirePolicy::exclusive, context.lease);
  if (reserve_result != IoResourceResult::success) {
    const auto result = mapResourceResult(reserve_result);
    record(context, result);
    k_mutex_unlock(&fabric_mutex);
    return result;
  }

  context.state = SerialFabricState::activating;
  blocks[block].active_instance = instance_;
  atomic_ptr_set(&blocks[block].active_adapter,
                 const_cast<SerialFabricDriverAdapter *>(context.adapter));
  int driver_error = 0;
  SerialFabricResult result =
      context.adapter->activate(instance_, context.route, driver_error);
  if (result != SerialFabricResult::success) {
    atomic_ptr_clear(&blocks[block].active_adapter);
    const IoResourceResult rollback_result =
        internal::rollbackIoResources(context.lease);
    context.lease = {};
    context.state = SerialFabricState::staged;
    if (rollback_result != IoResourceResult::success) {
      latchFault(context, block, SerialFabricResult::release_failed,
                 driver_error);
      result = SerialFabricResult::release_failed;
    } else {
      record(context, result, driver_error);
    }
    k_mutex_unlock(&fabric_mutex);
    return result;
  }

  const IoResourceResult commit_result =
      internal::commitIoResources(context.lease);
  if (commit_result != IoResourceResult::success) {
    int cleanup_error = 0;
    (void)context.adapter->request_stop(instance_, cleanup_error);
    const SerialFabricResult cleanup_result =
        context.adapter->deactivate(instance_, cleanup_error);
    const IoResourceResult rollback_result =
        internal::rollbackIoResources(context.lease);
    atomic_ptr_clear(&blocks[block].active_adapter);
    if ((cleanup_result != SerialFabricResult::success) ||
        (rollback_result != IoResourceResult::success)) {
      latchFault(context, block, SerialFabricResult::release_failed,
                 cleanup_error);
    } else {
      context.lease = {};
      context.state = SerialFabricState::staged;
      record(context, mapResourceResult(commit_result));
    }
    const auto observed = context.last_result;
    k_mutex_unlock(&fabric_mutex);
    return observed;
  }

  context.state = SerialFabricState::active;
  record(context, SerialFabricResult::success);
  k_mutex_unlock(&fabric_mutex);
  return SerialFabricResult::success;
}

SerialFabricResult
SerialFabricHandle::deactivate(std::uint32_t timeout_us) noexcept {
  if (k_is_in_isr())
    return SerialFabricResult::invalid_context;
  if (timeout_us == 0U)
    return SerialFabricResult::invalid_argument;
  k_mutex_lock(&fabric_mutex, K_FOREVER);
  auto &context = contextAt(handle_index_);
  const int block = blockIndex(instance_);
  if ((block < 0) || blocks[block].faulted ||
      (context.state == SerialFabricState::faulted)) {
    record(context, SerialFabricResult::faulted);
    k_mutex_unlock(&fabric_mutex);
    return SerialFabricResult::faulted;
  }
  if ((context.state != SerialFabricState::active) ||
      (context.adapter == nullptr)) {
    record(context, SerialFabricResult::wrong_state);
    k_mutex_unlock(&fabric_mutex);
    return SerialFabricResult::wrong_state;
  }

  context.state = SerialFabricState::cancelling;
  int driver_error = 0;
  SerialFabricResult result =
      context.adapter->request_stop(instance_, driver_error);
  if (result != SerialFabricResult::success) {
    latchFault(context, block, result, driver_error);
    k_mutex_unlock(&fabric_mutex);
    return result;
  }

  std::uint32_t elapsed = 0U;
  while (!context.adapter->stopped(instance_) && (elapsed < timeout_us)) {
    constexpr std::uint32_t poll_us = 10U;
    k_busy_wait(poll_us);
    elapsed += poll_us;
  }
  if (!context.adapter->stopped(instance_)) {
    latchFault(context, block, SerialFabricResult::stop_timeout, driver_error);
    k_mutex_unlock(&fabric_mutex);
    return SerialFabricResult::stop_timeout;
  }

  result = context.adapter->deactivate(instance_, driver_error);
  if (result != SerialFabricResult::success) {
    latchFault(context, block, result, driver_error);
    k_mutex_unlock(&fabric_mutex);
    return result;
  }
  atomic_ptr_clear(&blocks[block].active_adapter);
  const IoResourceResult release_result =
      internal::releaseIoResources(context.lease);
  if (release_result != IoResourceResult::success) {
    latchFault(context, block, SerialFabricResult::release_failed,
               driver_error);
    k_mutex_unlock(&fabric_mutex);
    return SerialFabricResult::release_failed;
  }

  context.lease = {};
  context.state = SerialFabricState::inactive;
  context.resource_count = 0U;
  record(context, SerialFabricResult::success);
  k_mutex_unlock(&fabric_mutex);
  return SerialFabricResult::success;
}

UarteHandle *SerialFabric::uarte(std::uint8_t instance) noexcept {
  static UarteHandle handles[] = {
      {0U, 0U}, {20U, 1U}, {21U, 2U}, {22U, 3U}, {30U, 4U}};
  const int block = blockIndex(instance);
  return block < 0 ? nullptr : &handles[block];
}

SpimHandle *SerialFabric::spim(std::uint8_t instance) noexcept {
  static SpimHandle handles[] = {
      {0U, 5U}, {20U, 6U}, {21U, 7U}, {22U, 8U}, {30U, 9U}};
  const int block = blockIndex(instance);
  return block < 0 ? nullptr : &handles[block];
}

SpisHandle *SerialFabric::spis(std::uint8_t instance) noexcept {
  static SpisHandle handles[] = {
      {0U, 10U}, {20U, 11U}, {21U, 12U}, {22U, 13U}, {30U, 14U}};
  const int block = blockIndex(instance);
  return block < 0 ? nullptr : &handles[block];
}

TwimHandle *SerialFabric::twim(std::uint8_t instance) noexcept {
  static TwimHandle handles[] = {
      {20U, 15U}, {21U, 16U}, {22U, 17U}, {30U, 18U}};
  const int block = blockIndex(instance);
  return block <= 0 ? nullptr : &handles[block - 1];
}

TwisHandle *SerialFabric::twis(std::uint8_t instance) noexcept {
  static TwisHandle handles[] = {
      {20U, 19U}, {21U, 20U}, {22U, 21U}, {30U, 22U}};
  const int block = blockIndex(instance);
  return block <= 0 ? nullptr : &handles[block - 1];
}

SerialFabric &serialFabric() noexcept {
  static SerialFabric fabric;
  return fabric;
}

namespace internal {
SerialFabricResult
registerSerialFabricAdapter(SerialPersonality personality,
                            std::uint8_t instance,
                            const SerialFabricDriverAdapter &adapter) noexcept {
  if (k_is_in_isr())
    return SerialFabricResult::invalid_context;
  const int index = handleIndex(personality, instance);
  if ((index < 0) || (adapter.validate == nullptr) ||
      (adapter.activate == nullptr) || (adapter.request_stop == nullptr) ||
      (adapter.stopped == nullptr) || (adapter.deactivate == nullptr) ||
      (adapter.handle_irq == nullptr)) {
    return index < 0 ? SerialFabricResult::unsupported_instance
                     : SerialFabricResult::invalid_argument;
  }
  k_mutex_lock(&fabric_mutex, K_FOREVER);
  if (adapter_registered[index] ||
      (contexts[index].state != SerialFabricState::inactive)) {
    k_mutex_unlock(&fabric_mutex);
    return SerialFabricResult::wrong_state;
  }
  adapters[index] = adapter;
  adapter_registered[index] = true;
  contexts[index].adapter = &adapters[index];
  k_mutex_unlock(&fabric_mutex);
  return SerialFabricResult::success;
}

bool isSerialFabricHandleActive(SerialPersonality personality,
                                std::uint8_t instance) noexcept {
  const int index = handleIndex(personality, instance);
  if (index < 0)
    return false;
  k_mutex_lock(&fabric_mutex, K_FOREVER);
  const bool active = contexts[index].state == SerialFabricState::active;
  k_mutex_unlock(&fabric_mutex);
  return active;
}

void dispatchSerialFabricIrq(std::uint8_t instance) noexcept {
  const int block = blockIndex(instance);
  if (block < 0)
    return;
  auto *const adapter = static_cast<SerialFabricDriverAdapter *>(
      atomic_ptr_get(&blocks[block].active_adapter));
  if (adapter != nullptr)
    adapter->handle_irq(blocks[block].active_instance);
}

#if defined(CONFIG_ZTEST)
void resetSerialFabricForTest() noexcept {
  if (k_is_in_isr())
    return;
  k_mutex_lock(&fabric_mutex, K_FOREVER);
  for (auto &context : contexts)
    context = {};
  for (auto &adapter : adapters)
    adapter = {};
  for (bool &registered : adapter_registered)
    registered = false;
  for (auto &block : blocks)
    block = {};
  k_mutex_unlock(&fabric_mutex);
}
#endif
} // namespace internal
} // namespace nucode::arduino
