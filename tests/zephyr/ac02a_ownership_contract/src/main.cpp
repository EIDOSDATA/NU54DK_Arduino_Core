/**
 * @file main.cpp
 * @brief AC-02A 물리 I/O 자원 소유권과 GPIO 통합 계약을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/dt-bindings/pinctrl/nrf-pinctrl.h>
#include <zephyr/irq_offload.h>
#include <zephyr/kernel.h>
#include <zephyr/ztest.h>

#include <cstddef>
#include <cstdint>

#include "internal/IoResourceManager.h"
#include "internal/Nu54dkIoResources.h"
#include "internal/PinHandover.h"
#include "internal/pin_description.h"

namespace {
using nucode::arduino::internal::acquireIoResources;
using nucode::arduino::internal::beginGpioPinHandover;
using nucode::arduino::internal::canonicalPinId;
using nucode::arduino::internal::commitGpioPinHandover;
using nucode::arduino::internal::commitIoResources;
using nucode::arduino::internal::GpioError;
using nucode::arduino::internal::gpioIoResource;
using nucode::arduino::internal::GpioPinHandover;
using nucode::arduino::internal::initializeNu54dkIoResources;
using nucode::arduino::internal::IoAcquirePolicy;
using nucode::arduino::internal::IoOwnerKind;
using nucode::arduino::internal::IoResourceId;
using nucode::arduino::internal::IoResourceKind;
using nucode::arduino::internal::IoResourceLease;
using nucode::arduino::internal::IoResourceOwner;
using nucode::arduino::internal::IoResourceResult;
using nucode::arduino::internal::IoResourceSnapshot;
using nucode::arduino::internal::ioResourceSnapshot;
using nucode::arduino::internal::IoResourceState;
using nucode::arduino::internal::IoResourceToken;
using nucode::arduino::internal::lastGpioError;
using nucode::arduino::internal::peripheralIoResource;
using nucode::arduino::internal::pinDescription;
using nucode::arduino::internal::PinHandoverResult;
using nucode::arduino::internal::releaseIoResources;
using nucode::arduino::internal::releasePeripheralPinHandover;
using nucode::arduino::internal::reserveIoResources;
using nucode::arduino::internal::resetIoResourceManagerForTest;
using nucode::arduino::internal::restoreGpioAfterPeripheral;
using nucode::arduino::internal::rollbackGpioPinHandover;
using nucode::arduino::internal::rollbackIoResources;
using nucode::arduino::internal::transferIoResources;

std::uint8_t test_domain_a;
std::uint8_t test_domain_b;

/** @brief 시험 전용 물리 GPIO 자원 키를 생성합니다. */
[[nodiscard]] constexpr IoResourceId testPin(const void *domain,
                                             std::uint16_t pin) noexcept {
  return {IoResourceKind::gpio_pin, domain, pin};
}

/** @brief 하나의 자원을 reserve하고 commit합니다. */
[[nodiscard]] IoResourceResult claim(IoResourceOwner owner,
                                     const IoResourceId &resource,
                                     IoResourceLease &lease) noexcept {
  const IoResourceResult reserve_result = reserveIoResources(
      owner, &resource, 1U, IoAcquirePolicy::exclusive, lease);
  return reserve_result == IoResourceResult::success ? commitIoResources(lease)
                                                     : reserve_result;
}

/** @brief nRF PSEL 값을 실제 GPIO controller 자원으로 변환합니다. */
[[nodiscard]] IoResourceId pselResource(std::uint32_t psel) noexcept {
  const auto absolute_pin =
      static_cast<std::uint16_t>((psel >> NRF_PIN_POS) & NRF_PIN_MSK);
  const struct device *controller = nullptr;
  switch (absolute_pin / 32U) {
  case 0U:
    controller = DEVICE_DT_GET(DT_NODELABEL(gpio0));
    break;
  case 1U:
    controller = DEVICE_DT_GET(DT_NODELABEL(gpio1));
    break;
  case 2U:
    controller = DEVICE_DT_GET(DT_NODELABEL(gpio2));
    break;
  default:
    break;
  }
  return {IoResourceKind::gpio_pin, controller,
          static_cast<std::uint16_t>(absolute_pin % 32U)};
}

/** @brief snapshot의 owner와 active 상태를 함께 검사합니다. */
void expectActiveOwner(const IoResourceId &resource, IoOwnerKind kind,
                       std::uint8_t instance) {
  IoResourceSnapshot snapshot{};
  zassert_equal(ioResourceSnapshot(resource, snapshot),
                IoResourceResult::success,
                "자원 snapshot 조회가 실패했습니다.");
  zassert_equal(snapshot.state, IoResourceState::active,
                "자원이 active 상태가 아닙니다.");
  zassert_equal(snapshot.owner.kind, kind, "자원 owner 종류가 다릅니다.");
  zassert_equal(snapshot.owner.instance, instance,
                "자원 owner instance가 다릅니다.");
}

K_SEM_DEFINE(race_start, 0, 2);
K_SEM_DEFINE(race_done, 0, 2);
K_THREAD_STACK_DEFINE(race_stack_a, 1024);
K_THREAD_STACK_DEFINE(race_stack_b, 1024);
k_thread race_thread_a;
k_thread race_thread_b;

/** @brief 동시 claim 시험 thread의 입력과 결과입니다. */
struct RaceContext {
  IoResourceOwner owner;
  IoResourceId resource;
  IoResourceLease lease;
  IoResourceResult result{IoResourceResult::invalid_argument};
};

/** @brief 같은 자원을 동시에 획득해 manager 직렬화를 검증합니다. */
void raceClaim(void *context_pointer, void *, void *) {
  auto &context = *static_cast<RaceContext *>(context_pointer);
  k_sem_take(&race_start, K_FOREVER);
  context.result = claim(context.owner, context.resource, context.lease);
  k_sem_give(&race_done);
}

IoResourceResult isr_result = IoResourceResult::success;
IoResourceLease isr_lease{};
IoResourceId isr_resource{};

/** @brief ISR 문맥에서 reserve가 거부되는지 확인하는 offload callback입니다. */
void reserveFromIsr(const void *) {
  isr_result = reserveIoResources({IoOwnerKind::gpio, 0U}, &isr_resource, 1U,
                                  IoAcquirePolicy::exclusive, isr_lease);
}
} // namespace

ZTEST(ac02a_ownership_contract,
      test_claim_commit_same_owner_and_release_lifecycle) {
  resetIoResourceManagerForTest();
  const IoResourceId resource = testPin(&test_domain_a, 3U);
  IoResourceLease original{};
  zassert_equal(claim({IoOwnerKind::gpio, 0U}, resource, original),
                IoResourceResult::success, "최초 GPIO claim이 실패했습니다.");
  expectActiveOwner(resource, IoOwnerKind::gpio, 0U);

  IoResourceLease repeated{};
  zassert_equal(reserveIoResources({IoOwnerKind::gpio, 0U}, &resource, 1U,
                                   IoAcquirePolicy::exclusive, repeated),
                IoResourceResult::success,
                "같은 owner의 반복 reserve가 실패했습니다.");
  zassert_false(repeated.entries[0].changed,
                "반복 claim을 새 획득으로 기록했습니다.");
  IoResourceLease stale_pending_copy = repeated;
  IoResourceLease concurrent_pending{};
  zassert_equal(reserveIoResources({IoOwnerKind::gpio, 0U}, &resource, 1U,
                                   IoAcquirePolicy::exclusive,
                                   concurrent_pending),
                IoResourceResult::conflict,
                "동일 owner의 동시 예약을 직렬화하지 않았습니다.");
  zassert_equal(
      releaseIoResources(original), IoResourceResult::conflict,
      "진행 중인 같은-owner transaction의 원래 lease를 반환했습니다.");
  zassert_equal(commitIoResources(repeated), IoResourceResult::success,
                "같은 owner의 반복 commit이 실패했습니다.");

  IoResourceLease next_pending{};
  zassert_equal(reserveIoResources({IoOwnerKind::gpio, 0U}, &resource, 1U,
                                   IoAcquirePolicy::exclusive, next_pending),
                IoResourceResult::success, "다음 반복 reserve가 실패했습니다.");
  zassert_equal(commitIoResources(stale_pending_copy),
                IoResourceResult::stale_lease,
                "복사된 이전 예약 lease가 새 예약 token을 소비했습니다.");
  zassert_equal(rollbackIoResources(next_pending), IoResourceResult::success,
                "다음 반복 reserve rollback이 실패했습니다.");
  zassert_equal(releaseIoResources(repeated), IoResourceResult::success,
                "반복 lease 반환이 실패했습니다.");
  expectActiveOwner(resource, IoOwnerKind::gpio, 0U);

  zassert_equal(releaseIoResources(original), IoResourceResult::success,
                "원래 lease 반환이 실패했습니다.");
  IoResourceSnapshot snapshot{};
  zassert_equal(ioResourceSnapshot(resource, snapshot),
                IoResourceResult::success,
                "반환 뒤 snapshot 조회가 실패했습니다.");
  zassert_equal(snapshot.state, IoResourceState::free,
                "반환한 자원이 free가 아닙니다.");
}

ZTEST(ac02a_ownership_contract,
      test_compact_token_claims_two_resources_and_releases) {
  resetIoResourceManagerForTest();
  const IoResourceId resources[] = {
      testPin(&test_domain_a, 20U),
      peripheralIoResource(IoResourceKind::dppi_channel, 3U, &test_domain_b),
  };
  IoResourceToken token{};
  zassert_equal(acquireIoResources({IoOwnerKind::dppi, 20U}, resources, 2U,
                                   IoAcquirePolicy::exclusive, token),
                IoResourceResult::success,
                "compact token 획득이 실패했습니다.");
  zassert_true(token.active, "compact token이 active가 아닙니다.");
  expectActiveOwner(resources[0], IoOwnerKind::dppi, 20U);
  expectActiveOwner(resources[1], IoOwnerKind::dppi, 20U);
  zassert_equal(releaseIoResources(token), IoResourceResult::success,
                "compact token 반환이 실패했습니다.");
  zassert_false(token.active, "반환한 compact token이 active로 남았습니다.");
  IoResourceSnapshot snapshot{};
  zassert_equal(ioResourceSnapshot(resources[0], snapshot),
                IoResourceResult::success, "반환 뒤 snapshot 조회 실패");
  zassert_equal(snapshot.state, IoResourceState::free,
                "compact token 자원이 free가 아닙니다.");
}

ZTEST(ac02a_ownership_contract,
      test_invalid_duplicate_and_wrong_phase_requests_are_rejected) {
  resetIoResourceManagerForTest();
  IoResourceLease lease{};
  const IoResourceId resource = testPin(&test_domain_a, 4U);
  const IoResourceId duplicate[] = {resource, resource};
  zassert_equal(reserveIoResources({IoOwnerKind::gpio, 0U}, duplicate, 2U,
                                   IoAcquirePolicy::exclusive, lease),
                IoResourceResult::invalid_argument,
                "중복 자원 batch를 허용했습니다.");
  zassert_equal(reserveIoResources({IoOwnerKind::none, 0U}, &resource, 1U,
                                   IoAcquirePolicy::exclusive, lease),
                IoResourceResult::invalid_argument,
                "none owner를 허용했습니다.");
  zassert_equal(commitIoResources(lease), IoResourceResult::wrong_phase,
                "예약하지 않은 lease commit을 허용했습니다.");

  IoResourceLease malformed{};
  malformed.owner = {IoOwnerKind::gpio, 0U};
  malformed.phase = nucode::arduino::internal::IoLeasePhase::reserved;
  malformed.count = nucode::arduino::internal::io_resource_lease_capacity + 1U;
  zassert_equal(commitIoResources(malformed),
                IoResourceResult::invalid_argument,
                "고정 배열 범위를 넘는 lease commit을 허용했습니다.");
  malformed.phase = nucode::arduino::internal::IoLeasePhase::committed;
  zassert_equal(releaseIoResources(malformed),
                IoResourceResult::invalid_argument,
                "고정 배열 범위를 넘는 lease release를 허용했습니다.");

  zassert_equal(reserveIoResources({IoOwnerKind::gpio, 0U}, &resource, 1U,
                                   IoAcquirePolicy::exclusive, lease),
                IoResourceResult::success, "정상 reserve가 실패했습니다.");
  zassert_equal(releaseIoResources(lease), IoResourceResult::wrong_phase,
                "commit 전 release를 허용했습니다.");
  zassert_equal(rollbackIoResources(lease), IoResourceResult::success,
                "reserve rollback이 실패했습니다.");
}

ZTEST(ac02a_ownership_contract,
      test_batch_conflict_is_atomic_and_rollback_restores_free) {
  resetIoResourceManagerForTest();
  const IoResourceId first = testPin(&test_domain_a, 5U);
  const IoResourceId occupied = testPin(&test_domain_b, 6U);
  IoResourceLease occupied_lease{};
  zassert_equal(claim({IoOwnerKind::wire, 22U}, occupied, occupied_lease),
                IoResourceResult::success, "선행 owner claim이 실패했습니다.");

  const IoResourceId batch[] = {first, occupied};
  IoResourceLease rejected{};
  IoResourceSnapshot conflict{};
  zassert_equal(reserveIoResources({IoOwnerKind::spi, 0U}, batch, 2U,
                                   IoAcquirePolicy::exclusive, rejected,
                                   &conflict),
                IoResourceResult::conflict, "충돌 batch를 허용했습니다.");
  zassert_equal(conflict.owner.kind, IoOwnerKind::wire,
                "충돌 owner 진단이 다릅니다.");
  IoResourceSnapshot first_snapshot{};
  zassert_equal(ioResourceSnapshot(first, first_snapshot),
                IoResourceResult::success,
                "부분 획득 여부 조회가 실패했습니다.");
  zassert_equal(first_snapshot.state, IoResourceState::free,
                "충돌 batch가 앞 자원을 부분 획득했습니다.");

  IoResourceLease rollback_lease{};
  zassert_equal(reserveIoResources({IoOwnerKind::gpio, 0U}, &first, 1U,
                                   IoAcquirePolicy::exclusive, rollback_lease),
                IoResourceResult::success,
                "rollback 대상 reserve가 실패했습니다.");
  zassert_equal(rollbackIoResources(rollback_lease), IoResourceResult::success,
                "rollback이 실패했습니다.");
  zassert_equal(ioResourceSnapshot(first, first_snapshot),
                IoResourceResult::success, "rollback 뒤 조회가 실패했습니다.");
  zassert_equal(first_snapshot.state, IoResourceState::free,
                "rollback 뒤 자원이 free가 아닙니다.");
}

ZTEST(ac02a_ownership_contract,
      test_copied_or_stale_lease_cannot_release_new_owner) {
  resetIoResourceManagerForTest();
  const IoResourceId resource = testPin(&test_domain_a, 7U);
  IoResourceLease first{};
  zassert_equal(claim({IoOwnerKind::gpio, 0U}, resource, first),
                IoResourceResult::success, "첫 claim이 실패했습니다.");
  IoResourceLease stale_copy = first;
  zassert_equal(releaseIoResources(first), IoResourceResult::success,
                "첫 lease 반환이 실패했습니다.");

  IoResourceLease second{};
  zassert_equal(claim({IoOwnerKind::spi, 0U}, resource, second),
                IoResourceResult::success,
                "두 번째 owner claim이 실패했습니다.");
  zassert_equal(releaseIoResources(stale_copy), IoResourceResult::stale_lease,
                "복사된 stale lease가 새 owner를 해제했습니다.");
  expectActiveOwner(resource, IoOwnerKind::spi, 0U);
}

ZTEST(ac02a_ownership_contract,
      test_two_threads_racing_for_one_resource_have_one_winner) {
  resetIoResourceManagerForTest();
  k_sem_reset(&race_start);
  k_sem_reset(&race_done);
  const IoResourceId resource = testPin(&test_domain_a, 8U);
  RaceContext first{{IoOwnerKind::wire, 22U},
                    resource,
                    {},
                    IoResourceResult::invalid_argument};
  RaceContext second{
      {IoOwnerKind::spi, 0U}, resource, {}, IoResourceResult::invalid_argument};

  k_thread_create(&race_thread_a, race_stack_a,
                  K_THREAD_STACK_SIZEOF(race_stack_a), raceClaim, &first,
                  nullptr, nullptr, 5, 0, K_NO_WAIT);
  k_thread_create(&race_thread_b, race_stack_b,
                  K_THREAD_STACK_SIZEOF(race_stack_b), raceClaim, &second,
                  nullptr, nullptr, 5, 0, K_NO_WAIT);
  k_sem_give(&race_start);
  k_sem_give(&race_start);
  zassert_equal(k_sem_take(&race_done, K_SECONDS(1)), 0,
                "첫 race thread가 끝나지 않았습니다.");
  zassert_equal(k_sem_take(&race_done, K_SECONDS(1)), 0,
                "둘째 race thread가 끝나지 않았습니다.");

  const unsigned int success_count =
      (first.result == IoResourceResult::success ? 1U : 0U) +
      (second.result == IoResourceResult::success ? 1U : 0U);
  zassert_equal(success_count, 1U,
                "동시 claim의 승자가 정확히 하나가 아닙니다.");
  zassert_true((first.result == IoResourceResult::conflict) ||
                   (second.result == IoResourceResult::conflict),
               "패배 thread가 conflict를 받지 않았습니다.");
}

ZTEST(ac02a_ownership_contract, test_reserve_is_rejected_from_isr) {
  resetIoResourceManagerForTest();
  isr_resource = testPin(&test_domain_a, 9U);
  isr_lease = {};
  isr_result = IoResourceResult::success;
  irq_offload(reserveFromIsr, nullptr);
  zassert_equal(isr_result, IoResourceResult::invalid_context,
                "ISR에서 ownership reserve를 허용했습니다.");
}

ZTEST(ac02a_ownership_contract,
      test_expected_owner_transfer_rolls_back_generation_exactly) {
  resetIoResourceManagerForTest();
  const IoResourceId resource = testPin(&test_domain_a, 10U);
  IoResourceLease gpio_lease{};
  zassert_equal(claim({IoOwnerKind::gpio, 0U}, resource, gpio_lease),
                IoResourceResult::success, "GPIO 선행 claim이 실패했습니다.");

  IoResourceLease transfer{};
  zassert_equal(transferIoResources({IoOwnerKind::gpio, 0U},
                                    {IoOwnerKind::pwm, 20U}, &resource, 1U,
                                    transfer),
                IoResourceResult::success,
                "expected-owner transfer 예약이 실패했습니다.");
  zassert_equal(rollbackIoResources(transfer), IoResourceResult::success,
                "expected-owner transfer rollback이 실패했습니다.");
  expectActiveOwner(resource, IoOwnerKind::gpio, 0U);
  zassert_equal(releaseIoResources(gpio_lease), IoResourceResult::success,
                "rollback 뒤 원래 GPIO lease 세대가 복구되지 않았습니다.");
}

ZTEST(ac02a_ownership_contract,
      test_expected_owner_transfer_commit_invalidates_old_lease) {
  resetIoResourceManagerForTest();
  const IoResourceId resource = testPin(&test_domain_a, 11U);
  IoResourceLease gpio_lease{};
  zassert_equal(claim({IoOwnerKind::gpio, 0U}, resource, gpio_lease),
                IoResourceResult::success, "GPIO 선행 claim이 실패했습니다.");

  IoResourceLease transfer{};
  zassert_equal(
      transferIoResources({IoOwnerKind::gpio, 0U}, {IoOwnerKind::spi, 0U},
                          &resource, 1U, transfer),
      IoResourceResult::success, "GPIO에서 SPI로 transfer가 실패했습니다.");
  zassert_equal(commitIoResources(transfer), IoResourceResult::success,
                "GPIO에서 SPI로 transfer commit이 실패했습니다.");
  expectActiveOwner(resource, IoOwnerKind::spi, 0U);
  zassert_equal(releaseIoResources(gpio_lease), IoResourceResult::stale_lease,
                "이전 owner lease가 새 owner를 해제했습니다.");
  zassert_equal(releaseIoResources(transfer), IoResourceResult::success,
                "새 owner lease 반환이 실패했습니다.");
}

ZTEST(ac02a_ownership_contract,
      test_expected_owner_transfer_rejects_mismatch_atomically) {
  resetIoResourceManagerForTest();
  const IoResourceId first = testPin(&test_domain_a, 12U);
  const IoResourceId second = testPin(&test_domain_b, 13U);
  IoResourceLease first_lease{};
  IoResourceLease second_lease{};
  zassert_equal(claim({IoOwnerKind::gpio, 0U}, first, first_lease),
                IoResourceResult::success, "첫 GPIO claim이 실패했습니다.");
  zassert_equal(claim({IoOwnerKind::wire, 22U}, second, second_lease),
                IoResourceResult::success, "둘째 Wire claim이 실패했습니다.");
  const IoResourceId resources[] = {first, second};
  IoResourceLease rejected{};
  IoResourceSnapshot conflict{};
  zassert_equal(transferIoResources({IoOwnerKind::gpio, 0U},
                                    {IoOwnerKind::pwm, 20U}, resources, 2U,
                                    rejected, &conflict),
                IoResourceResult::conflict,
                "expected owner가 다른 batch를 허용했습니다.");
  zassert_equal(conflict.owner.kind, IoOwnerKind::wire,
                "transfer 충돌 owner 진단이 다릅니다.");
  expectActiveOwner(first, IoOwnerKind::gpio, 0U);
  expectActiveOwner(second, IoOwnerKind::wire, 22U);
}

ZTEST(ac02a_ownership_contract,
      test_only_uart20_is_boot_fixed_and_dynamic_routes_start_free) {
  resetIoResourceManagerForTest();
  const IoResourceId uart_tx = pselResource(
      DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(uart20_default), group1), psels, 0));
  const IoResourceId wire_sda = pselResource(
      DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(i2c22_default), group1), psels, 0));
  const IoResourceId pwm_output = pselResource(
      DT_PROP_BY_IDX(DT_CHILD(DT_NODELABEL(pwm20_default), group1), psels, 0));

  IoResourceLease blocker{};
  zassert_equal(claim({IoOwnerKind::gpio, 0U}, uart_tx, blocker),
                IoResourceResult::success,
                "registry 충돌 준비가 실패했습니다.");
  zassert_equal(initializeNu54dkIoResources(), IoResourceResult::conflict,
                "UART20 고정 registry 충돌을 보고하지 않았습니다.");
  IoResourceSnapshot uart_after_failure{};
  zassert_equal(ioResourceSnapshot(uart_tx, uart_after_failure),
                IoResourceResult::success,
                "registry 실패 뒤 UART 조회가 실패했습니다.");
  zassert_equal(uart_after_failure.state, IoResourceState::active,
                "registry 실패가 선행 충돌 owner 상태를 훼손했습니다.");
  zassert_equal(uart_after_failure.owner.kind, IoOwnerKind::gpio,
                "registry 실패가 선행 충돌 owner를 바꿨습니다.");
  zassert_equal(releaseIoResources(blocker), IoResourceResult::success,
                "registry 충돌 준비 자원 반환이 실패했습니다.");

  zassert_equal(initializeNu54dkIoResources(), IoResourceResult::success,
                "NU54DK 고정 자원 registry 초기화가 실패했습니다.");

  expectActiveOwner(uart_tx, IoOwnerKind::serial, 20U);
  expectActiveOwner(peripheralIoResource(IoResourceKind::serial_block, 20U),
                    IoOwnerKind::serial, 20U);
  IoResourceSnapshot wire_snapshot{};
  IoResourceSnapshot pwm_snapshot{};
  zassert_equal(ioResourceSnapshot(wire_sda, wire_snapshot),
                IoResourceResult::success, "Wire22 pad 조회가 실패했습니다.");
  zassert_equal(ioResourceSnapshot(pwm_output, pwm_snapshot),
                IoResourceResult::success, "PWM20 pad 조회가 실패했습니다.");
  zassert_equal(wire_snapshot.state, IoResourceState::free,
                "Wire22 동적 route를 부팅 시 고정했습니다.");
  zassert_equal(pwm_snapshot.state, IoResourceState::free,
                "PWM20 동적 route를 부팅 시 고정했습니다.");

  IoResourceLease gpio_attempt{};
  zassert_equal(reserveIoResources({IoOwnerKind::gpio, 0U}, &uart_tx, 1U,
                                   IoAcquirePolicy::exclusive, gpio_attempt),
                IoResourceResult::conflict,
                "console TX를 GPIO가 선점했습니다.");
}

ZTEST(ac02a_ownership_contract,
      test_legacy_alias_is_canonicalized_for_gpio_and_handover) {
  resetIoResourceManagerForTest();
  zassert_equal(canonicalPinId(PIN_LED1), static_cast<std::size_t>(PIN_PWM0),
                "legacy ID 4가 canonical ID 3으로 정규화되지 않았습니다.");
  zassert_equal(pinDescription(PIN_LED1), pinDescription(PIN_PWM0),
                "legacy와 canonical descriptor 주소가 다릅니다.");

  pinMode(PIN_LED1, OUTPUT);
  zassert_equal(lastGpioError(), GpioError::none,
                "legacy alias를 통한 GPIO 설정이 실패했습니다.");
  const auto *const description = pinDescription(PIN_PWM0);
  zassert_not_null(description, "P1.10 descriptor가 없습니다.");
  expectActiveOwner(gpioIoResource(description->gpio), IoOwnerKind::gpio, 0U);

  GpioPinHandover handover{};
  zassert_equal(
      beginGpioPinHandover(PIN_LED1, {IoOwnerKind::pwm, 20U}, handover),
      PinHandoverResult::success,
      "legacy alias handover begin이 실패했습니다.");
  zassert_equal(handover.canonical_pin, static_cast<std::size_t>(PIN_PWM0),
                "handover가 legacy slot을 별도 물리 핀으로 취급했습니다.");
  zassert_equal(rollbackGpioPinHandover(handover), PinHandoverResult::success,
                "legacy alias handover rollback이 실패했습니다.");
  expectActiveOwner(gpioIoResource(description->gpio), IoOwnerKind::gpio, 0U);
}

ZTEST(ac02a_ownership_contract,
      test_committed_handover_restores_previous_gpio_state) {
  resetIoResourceManagerForTest();
  pinMode(PIN_GPIO0, OUTPUT);
  digitalWrite(PIN_GPIO0, HIGH);
  zassert_equal(lastGpioError(), GpioError::none,
                "GPIO 사전 상태 설정이 실패했습니다.");

  GpioPinHandover handover{};
  zassert_equal(
      beginGpioPinHandover(PIN_GPIO0, {IoOwnerKind::spi, 0U}, handover),
      PinHandoverResult::success, "GPIO→SPI handover begin이 실패했습니다.");
  zassert_equal(commitGpioPinHandover(handover), PinHandoverResult::success,
                "GPIO→SPI handover commit이 실패했습니다.");
  expectActiveOwner(gpioIoResource(pinDescription(PIN_GPIO0)->gpio),
                    IoOwnerKind::spi, 0U);
  digitalWrite(PIN_GPIO0, LOW);
  zassert_equal(lastGpioError(), GpioError::ownership_conflict,
                "주변장치 소유 중 digitalWrite를 허용했습니다.");
  zassert_equal(restoreGpioAfterPeripheral(handover),
                PinHandoverResult::success,
                "주변장치 종료 뒤 GPIO 상태 복원이 실패했습니다.");
  expectActiveOwner(gpioIoResource(pinDescription(PIN_GPIO0)->gpio),
                    IoOwnerKind::gpio, 0U);
  digitalWrite(PIN_GPIO0, LOW);
  zassert_equal(lastGpioError(), GpioError::none,
                "복원된 GPIO output 상태를 사용하지 못했습니다.");
}

ZTEST(ac02a_ownership_contract,
      test_nested_two_pin_handover_is_recursive_and_exact_once) {
  resetIoResourceManagerForTest();
  pinMode(PIN_GPIO0, OUTPUT);
  pinMode(PIN_GPIO1, INPUT_PULLUP);
  GpioPinHandover first{};
  GpioPinHandover second{};
  zassert_equal(
      beginGpioPinHandover(PIN_GPIO0, {IoOwnerKind::wire, 22U}, first),
      PinHandoverResult::success, "첫 중첩 handover begin이 실패했습니다.");
  zassert_equal(
      beginGpioPinHandover(PIN_GPIO1, {IoOwnerKind::wire, 22U}, second),
      PinHandoverResult::success,
      "같은 thread의 재귀 handover mutex 획득이 실패했습니다.");
  zassert_equal(rollbackGpioPinHandover(second), PinHandoverResult::success,
                "둘째 handover rollback이 실패했습니다.");
  zassert_equal(rollbackGpioPinHandover(first), PinHandoverResult::success,
                "첫 handover rollback이 실패했습니다.");
  zassert_equal(rollbackGpioPinHandover(first), PinHandoverResult::wrong_phase,
                "동일 handover의 이중 rollback을 허용했습니다.");
  zassert_true(nucode::arduino::internal::isPinConfiguredForOutput(PIN_GPIO0),
               "첫 GPIO output 상태가 복원되지 않았습니다.");
  zassert_true(nucode::arduino::internal::isPinConfiguredForInput(PIN_GPIO1),
               "둘째 GPIO input 상태가 복원되지 않았습니다.");
}

ZTEST(ac02a_ownership_contract,
      test_free_pin_handover_release_and_reserved_policy_fail_closed) {
  resetIoResourceManagerForTest();
  GpioPinHandover free_handover{};
  zassert_equal(
      beginGpioPinHandover(PIN_P2_00, {IoOwnerKind::spi, 0U}, free_handover),
      PinHandoverResult::success, "free pad handover begin이 실패했습니다.");
  zassert_equal(commitGpioPinHandover(free_handover),
                PinHandoverResult::success,
                "free pad handover commit이 실패했습니다.");
  zassert_equal(releasePeripheralPinHandover(free_handover),
                PinHandoverResult::success,
                "free pad 주변장치 release가 실패했습니다.");
  IoResourceSnapshot snapshot{};
  zassert_equal(ioResourceSnapshot(
                    gpioIoResource(pinDescription(PIN_P2_00)->gpio), snapshot),
                IoResourceResult::success,
                "free pad 반환 조회가 실패했습니다.");
  zassert_equal(snapshot.state, IoResourceState::free,
                "주변장치 종료 뒤 원래 free pad가 해제되지 않았습니다.");

  GpioPinHandover reserved{};
  zassert_equal(
      beginGpioPinHandover(PIN_P1_04, {IoOwnerKind::adc, 0U}, reserved),
      PinHandoverResult::unsupported,
      "UART20 system-reserved AIN0를 동적 handover했습니다.");
  pinMode(PIN_BUTTON1, OUTPUT);
  zassert_equal(lastGpioError(), GpioError::unsupported_capability,
                "input-only 버튼을 output으로 구성했습니다.");
}

ZTEST(ac02a_ownership_contract,
      test_pin_mode_claims_pad_and_reports_conflicting_owner) {
  resetIoResourceManagerForTest();
  const auto *const led = pinDescription(PIN_LED3);
  zassert_not_null(led, "LED3 descriptor가 없습니다.");
  const IoResourceId led_resource = gpioIoResource(led->gpio);

  pinMode(PIN_LED3, OUTPUT);
  zassert_equal(lastGpioError(), GpioError::none,
                "pinMode GPIO claim이 실패했습니다.");
  expectActiveOwner(led_resource, IoOwnerKind::gpio, 0U);

  resetIoResourceManagerForTest();
  IoResourceLease peripheral_lease{};
  zassert_equal(claim({IoOwnerKind::spi, 0U}, led_resource, peripheral_lease),
                IoResourceResult::success, "충돌 owner 준비가 실패했습니다.");
  pinMode(PIN_LED3, OUTPUT);
  zassert_equal(lastGpioError(), GpioError::ownership_conflict,
                "pinMode가 물리 pad 소유권 충돌을 보고하지 않았습니다.");
}

ZTEST_SUITE(ac02a_ownership_contract, nullptr, nullptr, nullptr, nullptr,
            nullptr);

/** @brief UART 없이 debugger가 회수할 수 있는 AC-02A ztest 결과입니다. */
struct Ac02aEvidence {
  std::uint32_t magic;
  std::uint32_t test_count;
  std::uint32_t run_count;
  std::uint32_t pass_count;
  std::uint32_t fail_count;
  std::uint32_t skip_count;
  std::uint32_t complete;
};

extern "C" {
/** @brief pyOCD memory read용 고정 결과 block입니다. */
volatile Ac02aEvidence nucode_ac02a_evidence{};
}

/** @brief 전체 ztest 통계를 RAM evidence에 기록하는 강한 test_main입니다. */
void test_main(void) {
  nucode_ac02a_evidence.magic = 0xAC02A001U;
  nucode_ac02a_evidence.test_count = 0U;
  nucode_ac02a_evidence.run_count = 0U;
  nucode_ac02a_evidence.pass_count = 0U;
  nucode_ac02a_evidence.fail_count = 0U;
  nucode_ac02a_evidence.skip_count = 0U;
  nucode_ac02a_evidence.complete = 0U;

  ztest_run_all(nullptr, false, 1, 1);
  ztest_verify_all_test_suites_ran();

  for (const auto *test = _ztest_unit_test_list_start;
       test < _ztest_unit_test_list_end; ++test) {
    ++nucode_ac02a_evidence.test_count;
    nucode_ac02a_evidence.run_count += test->stats->run_count;
    nucode_ac02a_evidence.pass_count += test->stats->pass_count;
    nucode_ac02a_evidence.fail_count += test->stats->fail_count;
    nucode_ac02a_evidence.skip_count += test->stats->skip_count;
  }
  nucode_ac02a_evidence.complete = 0xC002A11EU;

  /** debugger가 완료된 RAM evidence를 회수할 때까지 CPU를 실행 상태로
   * 유지합니다. */
  while (true) {
    k_busy_wait(1000U);
  }
}
