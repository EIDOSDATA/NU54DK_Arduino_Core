/**
 * @file PwmRuntime.cpp
 * @brief AC-02B PWM20·PWM21·PWM22의 채널과 공유 주기를 관리합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "internal/PwmRuntime.h"

#include "internal/AnalogRuntimeMath.h"

#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <errno.h>
#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal
{
    namespace
    {
        /** @brief NU54DK가 AC-02B에 할당한 PWM block 수입니다. */
        constexpr std::size_t block_count = 3U;

        /** @brief 한 PWM channel의 마지막 성공 상태입니다. */
        struct PwmSlot
        {
            pin_size_t pin{};
            std::uint32_t period_ns{0U};
            std::uint32_t pulse_ns{0U};
            std::uint8_t channel{0U};
            bool active{false};
        };

        /** @brief 한 PWM block의 고정 네 channel 상태입니다. */
        struct PwmBlockState
        {
            std::uint8_t instance{0U};
            PwmRuntimeClient client{PwmRuntimeClient::analog_write};
            PwmSlot slots[pwm_runtime_channel_capacity]{};
            bool fatal{false};
        };

        K_MUTEX_DEFINE(pwm_runtime_mutex);

        PwmRuntimeRouteBackend route_backend{};
        bool route_backend_installed = false;
        PwmBlockState blocks[block_count] = {
            {20U, PwmRuntimeClient::analog_write, {}, false},
            {21U, PwmRuntimeClient::tone, {}, false},
            {22U, PwmRuntimeClient::servo, {}, false},
        };
        atomic_t last_driver_error = ATOMIC_INIT(0);

        /** @brief client 전용 block 상태를 반환합니다. */
        [[nodiscard]] PwmBlockState *stateForClient(PwmRuntimeClient client) noexcept
        {
            for (auto &block : blocks)
            {
                if (block.client == client)
                {
                    return &block;
                }
            }
            return nullptr;
        }

        /** @brief block의 활성 channel 수를 반환합니다. */
        [[nodiscard]] std::size_t activeCount(const PwmBlockState &block) noexcept
        {
            std::size_t count = 0U;
            for (const auto &slot : block.slots)
            {
                count += slot.active ? 1U : 0U;
            }
            return count;
        }

        /** @brief client 정책이 허용하는 최대 channel 수를 반환합니다. */
        [[nodiscard]] constexpr std::size_t clientCapacity(PwmRuntimeClient client) noexcept
        {
            return client == PwmRuntimeClient::tone ? 1U : pwm_runtime_channel_capacity;
        }

        /** @brief block에서 지정 핀을 소유한 slot을 찾습니다. */
        [[nodiscard]] PwmSlot *findSlot(PwmBlockState &block, pin_size_t pin) noexcept
        {
            for (auto &slot : block.slots)
            {
                if (slot.active && slot.pin == pin)
                {
                    return &slot;
                }
            }
            return nullptr;
        }

        /** @brief block에서 비어 있는 channel slot을 반환합니다. */
        [[nodiscard]] PwmSlot *freeSlot(PwmBlockState &block) noexcept
        {
            for (auto &slot : block.slots)
            {
                if (!slot.active)
                {
                    return &slot;
                }
            }
            return nullptr;
        }

        /** @brief 현재 slot 집합으로 block route 요청을 생성합니다. */
        [[nodiscard]] PwmRuntimeRouteSet routeSet(const PwmBlockState &block,
                                                  const PwmSlot *additional = nullptr,
                                                  const PwmSlot *excluded = nullptr) noexcept
        {
            PwmRuntimeRouteSet routes{};
            for (const auto &slot : block.slots)
            {
                if (!slot.active || &slot == excluded)
                {
                    continue;
                }
                routes.pins[routes.count] = slot.pin;
                routes.channels[routes.count] = slot.channel;
                ++routes.count;
            }
            if (additional != nullptr)
            {
                routes.pins[routes.count] = additional->pin;
                routes.channels[routes.count] = additional->channel;
                ++routes.count;
            }
            return routes;
        }

        /** @brief route backend의 원래 오류 번호를 보존합니다. */
        void recordRouteDriverError(std::uint8_t instance) noexcept
        {
            const int error = route_backend.last_driver_error != nullptr
                                  ? route_backend.last_driver_error(instance)
                                  : 0;
            atomic_set(&last_driver_error, static_cast<atomic_val_t>(error));
        }

        /** @brief 실제 출력 복구가 실패한 block을 재사용 불가 상태로 고정합니다. */
        void latchBlockFault(PwmBlockState &state, int driver_error) noexcept
        {
            state.fatal = true;
            atomic_set(&last_driver_error,
                       static_cast<atomic_val_t>(driver_error != 0 ? driver_error : -EIO));
        }

        /** @brief 하나의 slot 값을 Zephyr PWM driver에 전달합니다. */
        [[nodiscard]] int driveSlot(const PwmRuntimeBlock &runtime_block,
                                    const PwmSlot &slot) noexcept
        {
            return pwm_set(runtime_block.device, slot.channel, slot.period_ns, slot.pulse_ns,
                           runtime_block.flags);
        }

        /** @brief 활성 slot 전체를 마지막 성공값으로 다시 출력합니다. */
        [[nodiscard]] int restoreOutputs(const PwmRuntimeBlock &runtime_block,
                                         const PwmBlockState &block,
                                         const PwmSlot *excluded = nullptr) noexcept
        {
            int first_error = 0;
            for (const auto &slot : block.slots)
            {
                if (!slot.active || &slot == excluded)
                {
                    continue;
                }
                const int result = driveSlot(runtime_block, slot);
                if (first_error == 0 && result < 0)
                {
                    first_error = result;
                }
            }
            return first_error;
        }

        /** @brief 활성 slot 전체의 pulse를 0으로 만든 뒤 route를 바꿀 준비를 합니다. */
        [[nodiscard]] int stopOutputs(const PwmRuntimeBlock &runtime_block,
                                      const PwmBlockState &block) noexcept
        {
            int first_error = 0;
            for (const auto &slot : block.slots)
            {
                if (!slot.active)
                {
                    continue;
                }
                const int result = pwm_set(runtime_block.device, slot.channel, slot.period_ns, 0U,
                                           runtime_block.flags);
                if (first_error == 0 && result < 0)
                {
                    first_error = result;
                }
            }
            return first_error;
        }

        /** @brief backend과 block device의 기본 유효성을 검사합니다. */
        [[nodiscard]] PwmRuntimeResult resolveBlock(PwmBlockState &state,
                                                    PwmRuntimeBlock &block) noexcept
        {
            if (state.fatal)
            {
                return PwmRuntimeResult::route_error;
            }
            if (!route_backend_installed)
            {
                return PwmRuntimeResult::unsupported_route;
            }
            const PwmRuntimeResult result = route_backend.block(state.instance, block);
            if (result != PwmRuntimeResult::success)
            {
                recordRouteDriverError(state.instance);
                return result;
            }
            if (block.device == nullptr || !device_is_ready(block.device))
            {
                return PwmRuntimeResult::device_not_ready;
            }
            return PwmRuntimeResult::success;
        }

        /** @brief 새 channel route와 출력을 적용하고 실패 시 기존 상태를 복구합니다. */
        [[nodiscard]] PwmRuntimeResult addSlot(PwmBlockState &state, PwmSlot &slot,
                                               const PwmSlot &desired) noexcept
        {
            PwmRuntimeBlock runtime_block{};
            PwmRuntimeResult result = resolveBlock(state, runtime_block);
            if (result != PwmRuntimeResult::success)
            {
                return result;
            }

            const PwmRuntimeRouteSet old_routes = routeSet(state);
            const PwmRuntimeRouteSet new_routes = routeSet(state, &desired);
            const int stop_result = stopOutputs(runtime_block, state);
            if (stop_result < 0)
            {
                const int restore_result = restoreOutputs(runtime_block, state);
                if (restore_result < 0)
                {
                    latchBlockFault(state, restore_result);
                    return PwmRuntimeResult::route_error;
                }
                atomic_set(&last_driver_error, static_cast<atomic_val_t>(stop_result));
                return PwmRuntimeResult::driver_error;
            }

            result = route_backend.apply(state.instance, new_routes);
            if (result != PwmRuntimeResult::success)
            {
                recordRouteDriverError(state.instance);
                const int restore_result = restoreOutputs(runtime_block, state);
                if (restore_result < 0)
                {
                    latchBlockFault(state, restore_result);
                    return PwmRuntimeResult::route_error;
                }
                return result;
            }

            int driver_result = restoreOutputs(runtime_block, state);
            if (driver_result == 0)
            {
                driver_result = driveSlot(runtime_block, desired);
            }
            if (driver_result < 0)
            {
                const int desired_stop_result = pwm_set(runtime_block.device, desired.channel,
                                                        desired.period_ns, 0U, runtime_block.flags);
                const int old_stop_result = stopOutputs(runtime_block, state);
                const PwmRuntimeResult rollback_result =
                    old_routes.count == 0U ? route_backend.clear(state.instance)
                                           : route_backend.apply(state.instance, old_routes);
                const int restore_result = restoreOutputs(runtime_block, state);
                atomic_set(&last_driver_error, static_cast<atomic_val_t>(driver_result));
                if (desired_stop_result < 0 || old_stop_result < 0 ||
                    rollback_result != PwmRuntimeResult::success || restore_result < 0)
                {
                    const int fault_error =
                        restore_result < 0
                            ? restore_result
                            : (old_stop_result < 0 ? old_stop_result
                                                   : (desired_stop_result < 0 ? desired_stop_result
                                                                              : driver_result));
                    latchBlockFault(state, fault_error);
                    return PwmRuntimeResult::route_error;
                }
                return rollback_result == PwmRuntimeResult::success ? PwmRuntimeResult::driver_error
                                                                    : PwmRuntimeResult::route_error;
            }

            slot = desired;
            slot.active = true;
            atomic_set(&last_driver_error, 0);
            return PwmRuntimeResult::success;
        }

        /** @brief route에서 channel을 제거하고 실패 시 기존 출력을 복원합니다. */
        [[nodiscard]] PwmRuntimeResult removeSlot(PwmBlockState &state, PwmSlot &removed) noexcept
        {
            PwmRuntimeBlock runtime_block{};
            PwmRuntimeResult result = resolveBlock(state, runtime_block);
            if (result != PwmRuntimeResult::success)
            {
                return result;
            }

            const PwmRuntimeRouteSet old_routes = routeSet(state);
            const PwmRuntimeRouteSet new_routes = routeSet(state, nullptr, &removed);
            const int stop_result = stopOutputs(runtime_block, state);
            if (stop_result < 0)
            {
                const int restore_result = restoreOutputs(runtime_block, state);
                if (restore_result < 0)
                {
                    latchBlockFault(state, restore_result);
                    return PwmRuntimeResult::route_error;
                }
                atomic_set(&last_driver_error, static_cast<atomic_val_t>(stop_result));
                return PwmRuntimeResult::driver_error;
            }

            result = new_routes.count == 0U ? route_backend.clear(state.instance)
                                            : route_backend.apply(state.instance, new_routes);
            if (result != PwmRuntimeResult::success)
            {
                recordRouteDriverError(state.instance);
                const int restore_result = restoreOutputs(runtime_block, state);
                if (restore_result < 0)
                {
                    latchBlockFault(state, restore_result);
                    return PwmRuntimeResult::route_error;
                }
                return result;
            }

            const int restore_result = restoreOutputs(runtime_block, state, &removed);
            if (restore_result < 0)
            {
                const int stop_rollback_result = stopOutputs(runtime_block, state);
                const PwmRuntimeResult rollback_result =
                    route_backend.apply(state.instance, old_routes);
                const int output_rollback_result = restoreOutputs(runtime_block, state);
                atomic_set(&last_driver_error, static_cast<atomic_val_t>(restore_result));
                if (stop_rollback_result < 0 || rollback_result != PwmRuntimeResult::success ||
                    output_rollback_result < 0)
                {
                    const int fault_error =
                        output_rollback_result < 0
                            ? output_rollback_result
                            : (stop_rollback_result < 0 ? stop_rollback_result : restore_result);
                    latchBlockFault(state, fault_error);
                    return PwmRuntimeResult::route_error;
                }
                return rollback_result == PwmRuntimeResult::success ? PwmRuntimeResult::driver_error
                                                                    : PwmRuntimeResult::route_error;
            }

            removed = {};
            atomic_set(&last_driver_error, 0);
            return PwmRuntimeResult::success;
        }
    } // namespace

    bool installPwmRuntimeRouteBackend(const PwmRuntimeRouteBackend &backend) noexcept
    {
        if (k_is_in_isr() || backend.supports == nullptr || backend.block == nullptr ||
            backend.apply == nullptr || backend.clear == nullptr)
        {
            return false;
        }

        static_cast<void>(k_mutex_lock(&pwm_runtime_mutex, K_FOREVER));
        for (const auto &block : blocks)
        {
            if (activeCount(block) != 0U)
            {
                static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
                return false;
            }
        }
        route_backend = backend;
        route_backend_installed = true;
        atomic_set(&last_driver_error, 0);
        static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
        return true;
    }

    bool pwmRuntimePinSupported(PwmRuntimeClient client, pin_size_t pin) noexcept
    {
        if (k_is_in_isr())
        {
            return false;
        }
        static_cast<void>(k_mutex_lock(&pwm_runtime_mutex, K_FOREVER));
        PwmBlockState *const state = stateForClient(client);
        const bool supported = route_backend_installed && state != nullptr && !state->fatal &&
                               route_backend.supports(pin, state->instance);
        static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
        return supported;
    }

    PwmRuntimeResult pwmRuntimeWrite(PwmRuntimeClient client, pin_size_t pin,
                                     std::uint32_t period_ns, std::uint32_t pulse_ns) noexcept
    {
        if (k_is_in_isr())
        {
            return PwmRuntimeResult::invalid_context;
        }
        if (period_ns == 0U || pulse_ns > period_ns)
        {
            return PwmRuntimeResult::invalid_argument;
        }

        static_cast<void>(k_mutex_lock(&pwm_runtime_mutex, K_FOREVER));
        PwmBlockState *const state = stateForClient(client);
        if (state == nullptr || !route_backend_installed || state->fatal ||
            !route_backend.supports(pin, state->instance))
        {
            static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
            return state == nullptr ? PwmRuntimeResult::invalid_argument
                                    : (state->fatal ? PwmRuntimeResult::route_error
                                                    : PwmRuntimeResult::unsupported_route);
        }

        PwmSlot *slot = findSlot(*state, pin);
        if (slot != nullptr)
        {
            if (slot->period_ns != period_ns && activeCount(*state) > 1U)
            {
                static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
                return PwmRuntimeResult::period_conflict;
            }

            PwmRuntimeBlock runtime_block{};
            const PwmRuntimeResult resolve_result = resolveBlock(*state, runtime_block);
            if (resolve_result != PwmRuntimeResult::success)
            {
                static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
                return resolve_result;
            }
            const int result = pwm_set(runtime_block.device, slot->channel, period_ns, pulse_ns,
                                       runtime_block.flags);
            if (result < 0)
            {
                atomic_set(&last_driver_error, static_cast<atomic_val_t>(result));
                static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
                return PwmRuntimeResult::driver_error;
            }
            slot->period_ns = period_ns;
            slot->pulse_ns = pulse_ns;
            atomic_set(&last_driver_error, 0);
            static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
            return PwmRuntimeResult::success;
        }

        if (activeCount(*state) >= clientCapacity(client))
        {
            static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
            return PwmRuntimeResult::channel_exhausted;
        }
        for (const auto &existing : state->slots)
        {
            if (existing.active && existing.period_ns != period_ns)
            {
                static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
                return PwmRuntimeResult::period_conflict;
            }
        }

        slot = freeSlot(*state);
        if (slot == nullptr)
        {
            static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
            return PwmRuntimeResult::channel_exhausted;
        }
        const std::size_t slot_index = static_cast<std::size_t>(slot - state->slots);
        PwmSlot desired{pin, period_ns, pulse_ns, static_cast<std::uint8_t>(slot_index), true};
        const PwmRuntimeResult result = addSlot(*state, *slot, desired);
        static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
        return result;
    }

    PwmRuntimeResult pwmRuntimeRetune(PwmRuntimeClient client, pin_size_t pin,
                                      std::uint32_t period_ns) noexcept
    {
        if (k_is_in_isr())
        {
            return PwmRuntimeResult::invalid_context;
        }
        if (period_ns == 0U)
        {
            return PwmRuntimeResult::invalid_argument;
        }

        static_cast<void>(k_mutex_lock(&pwm_runtime_mutex, K_FOREVER));
        PwmBlockState *const state = stateForClient(client);
        PwmSlot *const slot = state != nullptr ? findSlot(*state, pin) : nullptr;
        if (slot == nullptr)
        {
            static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
            return PwmRuntimeResult::not_active;
        }
        if (slot->period_ns != period_ns && activeCount(*state) > 1U)
        {
            static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
            return PwmRuntimeResult::period_conflict;
        }

        PwmRuntimeBlock runtime_block{};
        const PwmRuntimeResult resolve_result = resolveBlock(*state, runtime_block);
        if (resolve_result != PwmRuntimeResult::success)
        {
            static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
            return resolve_result;
        }
        const std::uint32_t pulse_ns =
            rescalePulseForPeriod(slot->period_ns, slot->pulse_ns, period_ns);
        const int driver_result =
            pwm_set(runtime_block.device, slot->channel, period_ns, pulse_ns, runtime_block.flags);
        if (driver_result < 0)
        {
            atomic_set(&last_driver_error, static_cast<atomic_val_t>(driver_result));
            static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
            return PwmRuntimeResult::driver_error;
        }
        slot->period_ns = period_ns;
        slot->pulse_ns = pulse_ns;
        atomic_set(&last_driver_error, 0);
        static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
        return PwmRuntimeResult::success;
    }

    PwmRuntimeResult pwmRuntimeStop(PwmRuntimeClient client, pin_size_t pin) noexcept
    {
        if (k_is_in_isr())
        {
            return PwmRuntimeResult::invalid_context;
        }
        static_cast<void>(k_mutex_lock(&pwm_runtime_mutex, K_FOREVER));
        PwmBlockState *const state = stateForClient(client);
        PwmSlot *const slot = state != nullptr ? findSlot(*state, pin) : nullptr;
        if (slot == nullptr)
        {
            static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
            return PwmRuntimeResult::not_active;
        }
        const PwmRuntimeResult result = removeSlot(*state, *slot);
        static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
        return result;
    }

    PwmRuntimeResult pwmRuntimeSuspend(PwmRuntimeClient client, pin_size_t pin,
                                       PwmRuntimeSuspendedOutput &snapshot) noexcept
    {
        snapshot = {};
        if (k_is_in_isr())
        {
            return PwmRuntimeResult::invalid_context;
        }
        static_cast<void>(k_mutex_lock(&pwm_runtime_mutex, K_FOREVER));
        PwmBlockState *const state = stateForClient(client);
        PwmSlot *const slot = state != nullptr ? findSlot(*state, pin) : nullptr;
        if (slot == nullptr)
        {
            static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
            return PwmRuntimeResult::not_active;
        }

        const PwmRuntimeSuspendedOutput saved{client, slot->pin, slot->period_ns, slot->pulse_ns,
                                              true};
        const PwmRuntimeResult result = removeSlot(*state, *slot);
        if (result == PwmRuntimeResult::success)
        {
            snapshot = saved;
        }
        static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
        return result;
    }

    PwmRuntimeResult pwmRuntimeResume(PwmRuntimeSuspendedOutput &snapshot) noexcept
    {
        if (!snapshot.valid)
        {
            return PwmRuntimeResult::not_active;
        }
        const PwmRuntimeResult result =
            pwmRuntimeWrite(snapshot.client, snapshot.pin, snapshot.period_ns, snapshot.pulse_ns);
        if (result == PwmRuntimeResult::success)
        {
            snapshot.valid = false;
        }
        return result;
    }

    bool pwmRuntimeActive(PwmRuntimeClient client, pin_size_t pin) noexcept
    {
        if (k_is_in_isr())
        {
            return false;
        }
        static_cast<void>(k_mutex_lock(&pwm_runtime_mutex, K_FOREVER));
        PwmBlockState *const state = stateForClient(client);
        const bool active = state != nullptr && findSlot(*state, pin) != nullptr;
        static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
        return active;
    }

    int lastPwmRuntimeDriverError() noexcept
    {
        return static_cast<int>(atomic_get(&last_driver_error));
    }

#if defined(CONFIG_ZTEST)
    void resetPwmRuntimeForTest() noexcept
    {
        static_cast<void>(k_mutex_lock(&pwm_runtime_mutex, K_FOREVER));
        for (auto &block : blocks)
        {
            for (auto &slot : block.slots)
            {
                slot = {};
            }
            block.fatal = false;
        }
        route_backend = {};
        route_backend_installed = false;
        atomic_set(&last_driver_error, 0);
        static_cast<void>(k_mutex_unlock(&pwm_runtime_mutex));
    }
#endif
} // namespace nucode::arduino::internal
