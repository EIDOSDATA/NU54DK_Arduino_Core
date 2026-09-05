/** @file @brief Serial Fabric의 lease·pin·전원 전환과 STOP 예약 수명주기입니다.
 * SPDX-License-Identifier: MIT
 */
#include "SerialFabricInternal.h"
#include "serial_fabric_routes.h"
#include <hal/nrf_gpio.h>
#include <nrfx_power.h>
#include <zephyr/kernel.h>
#include <errno.h>
namespace nucode::arduino::internal::serial
{
    namespace
    {
        [[nodiscard]] constexpr IoOwnerKind ownerKind(SerialPersonality personality) noexcept
        {
            switch (personality)
            {
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

        [[nodiscard]] SerialFabricResult mapResourceResult(IoResourceResult result) noexcept
        {
            switch (result)
            {
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
                    int driver_error = 0) noexcept
        {
            context.last_result = result;
            context.last_driver_error = driver_error;
        }

        void latchFault(HandleContext &context, int block, SerialFabricResult result,
                        int driver_error) noexcept
        {
            context.state = SerialFabricState::faulted;
            blockAt(block).faulted = true;
            blockAt(block).wait_in_progress = false;
            record(context, result, driver_error);
        }

        /**
         * @brief 전체 독점 lease가 예약된 뒤에만 핀 snapshot을 읽습니다.
         *
         * 검증·staging 중이거나 충돌한 획득 뒤에는 패드를 건드리지 않습니다.
         */
        bool saveRouteState(HandleContext &context, std::uint8_t instance,
                            int &driver_error) noexcept
        {
            context.saved_pin_count = 0U;
            for (std::size_t index = 0; index < context.route.pin_count; ++index)
            {
                auto &saved = context.saved_pins[index];
                if (internal::nu54dkSerialFabricPsel(context.route.pins[index].pin, saved.psel) !=
                    SerialFabricResult::success)
                {
                    return false;
                }
                auto pin = saved.psel;
                const auto *port = nrf_gpio_pin_port_decode(&pin);
                saved.configuration = port->PIN_CNF[pin];
                saved.output = nrf_gpio_pin_out_read(saved.psel);
                ++context.saved_pin_count;
            }
            if (instance == 20U && context.route.route == SerialRouteClass::p2_dedicated20)
            {
                driver_error = nrfx_power_constlat_mode_request();
                /** @brief EALREADY도 증가시킨 nrfx 공유 참조 횟수를 되돌립니다. */
                if (driver_error != 0 && driver_error != -EALREADY)
                {
                    return false;
                }
                context.constant_latency_owned = true;
                driver_error = 0;
            }
            return true;
        }

        bool waitStopped(const SerialFabricDriverAdapter &adapter, std::uint8_t instance,
                         std::uint32_t timeout_us) noexcept
        {
            while (!adapter.stopped(instance) && timeout_us != 0U)
            {
                const auto interval = timeout_us < 10U ? timeout_us : 10U;
                k_busy_wait(interval);
                /** @brief UINT32_MAX에서도 뺄셈 wraparound가 생기지 않습니다. */
                timeout_us -= interval;
            }
            return adapter.stopped(instance);
        }

        /**
         * @brief block과 adapter를 예약하고 긴 STOP 확인만 전역 mutex 밖에서 수행합니다.
         * @details 호출자는 fabric mutex를 한 번 보유하고 activating/cancelling 상태여야 합니다.
         * driver의 짧은 request_stop critical section과 lease 반환 순서는 바꾸지 않습니다.
         */
        bool waitStoppedWithoutFabricLock(HandleContext &context, std::uint8_t instance, int block,
                                          std::uint32_t timeout_us) noexcept
        {
            auto &reservation = blockAt(block);
            reservation.wait_in_progress = true;
            ++reservation.wait_generation;
            if (reservation.wait_generation == 0U)
            {
                ++reservation.wait_generation;
            }
            const auto generation = reservation.wait_generation;
            const auto *const adapter = context.adapter;
            unlockFabric();
            const bool stopped = waitStopped(*adapter, instance, timeout_us);
            lockFabric();
            if (!reservation.wait_in_progress || reservation.wait_generation != generation ||
                context.adapter != adapter ||
                (context.state != SerialFabricState::activating &&
                 context.state != SerialFabricState::cancelling))
            {
                return false;
            }
            reservation.wait_in_progress = false;
            return stopped;
        }
    } // namespace
    bool restoreRouteState(HandleContext &context, int &driver_error) noexcept
    {
        /**
             * @brief adapter가 PSEL 분리와 DMA STOP을 증명한 뒤 GPIO를 복원합니다.
             *
             * port 전체를 덮지 않고 각 소유 핀의 OUT latch를 PIN_CNF보다 먼저 복원합니다.
             */
        for (std::size_t index = 0; index < context.saved_pin_count; ++index)
        {
            const auto &saved = context.saved_pins[index];
            nrf_gpio_pin_write(saved.psel, saved.output);
            auto pin = saved.psel;
            auto *port = nrf_gpio_pin_port_decode(&pin);
            port->PIN_CNF[pin] = saved.configuration;
        }
        context.saved_pin_count = 0U;
        if (context.constant_latency_owned)
        {
            driver_error = nrfx_power_constlat_mode_free();
            /** @brief EBUSY는 현재 참조는 반환됐고 다른 소유자 참조가 남았음을 뜻합니다. */
            if (driver_error != 0 && driver_error != -EBUSY)
            {
                return false;
            }
            context.constant_latency_owned = false;
            driver_error = 0;
        }
        return true;
    }
} // namespace nucode::arduino::internal::serial
namespace nucode::arduino
{
    using namespace internal::serial;
    SerialFabricResult
    SerialFabricHandle::stage(const SerialFabricConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        lockFabric();
        auto &context = contextAt(handle_index_);
        const int block = blockIndex(instance_);
        if ((block < 0) || blockAt(block).faulted || (context.state == SerialFabricState::faulted))
        {
            record(context, SerialFabricResult::faulted);
            unlockFabric();
            return SerialFabricResult::faulted;
        }
        if (blockAt(block).wait_in_progress)
        {
            record(context, SerialFabricResult::wrong_state);
            unlockFabric();
            return SerialFabricResult::wrong_state;
        }
        if ((context.state != SerialFabricState::inactive) &&
            (context.state != SerialFabricState::staged))
        {
            record(context, SerialFabricResult::wrong_state);
            unlockFabric();
            return SerialFabricResult::wrong_state;
        }
        if (!adapterRegistered(handle_index_))
        {
            record(context, SerialFabricResult::driver_unavailable);
            unlockFabric();
            return SerialFabricResult::driver_unavailable;
        }

        ValidatedSerialRoute candidate{};
        IoResourceId resources[internal::io_resource_lease_capacity]{};
        std::size_t resource_count = 0U;
        SerialFabricResult result = internal::validateNu54dkSerialFabricRoute(
            personality_, instance_, configuration, candidate, resources,
            internal::io_resource_lease_capacity, resource_count);
        int driver_error = 0;
        if (result == SerialFabricResult::success)
        {
            result = adapterAt(handle_index_).validate(instance_, candidate, driver_error);
        }
        if (result != SerialFabricResult::success)
        {
            record(context, result, driver_error);
            unlockFabric();
            return result;
        }

        context.route = candidate;
        context.resource_count = resource_count;
        for (std::size_t index = 0U; index < resource_count; ++index)
        {
            context.resources[index] = resources[index];
        }
        context.adapter = &adapterAt(handle_index_);
        context.state = SerialFabricState::staged;
        record(context, SerialFabricResult::success);
        unlockFabric();
        return SerialFabricResult::success;
    }

    SerialFabricResult SerialFabricHandle::activate() noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        lockFabric();
        auto &context = contextAt(handle_index_);
        const int block = blockIndex(instance_);
        if ((block < 0) || blockAt(block).faulted || (context.state == SerialFabricState::faulted))
        {
            record(context, SerialFabricResult::faulted);
            unlockFabric();
            return SerialFabricResult::faulted;
        }
        if (blockAt(block).wait_in_progress)
        {
            record(context, SerialFabricResult::wrong_state);
            unlockFabric();
            return SerialFabricResult::wrong_state;
        }
        if ((context.state != SerialFabricState::staged) || (context.adapter == nullptr))
        {
            record(context, SerialFabricResult::wrong_state);
            unlockFabric();
            return SerialFabricResult::wrong_state;
        }

        context.lease = {};
        const IoResourceResult reserve_result = internal::reserveIoResources(
            {ownerKind(personality_), instance_}, context.resources, context.resource_count,
            IoAcquirePolicy::exclusive, context.lease);
        if (reserve_result != IoResourceResult::success)
        {
            const auto result = mapResourceResult(reserve_result);
            record(context, result);
            unlockFabric();
            return result;
        }

        context.state = SerialFabricState::activating;
        int driver_error = 0;
        if (!saveRouteState(context, instance_, driver_error))
        {
            int restore_error = 0;
            const bool restored = restoreRouteState(context, restore_error);
            if (!restored ||
                internal::rollbackIoResources(context.lease) != IoResourceResult::success)
            {
                latchFault(context, block, SerialFabricResult::release_failed, restore_error);
            }
            else
            {
                context.lease = {};
                context.state = SerialFabricState::staged;
                record(context, SerialFabricResult::driver_error, driver_error);
            }
            const auto observed = context.last_result;
            unlockFabric();
            return observed;
        }
        blockAt(block).active_instance = instance_;
        atomic_ptr_set(&blockAt(block).active_adapter,
                       const_cast<SerialFabricDriverAdapter *>(context.adapter));
        SerialFabricResult result =
            context.adapter->activate(instance_, context.route, driver_error);
        if (result != SerialFabricResult::success)
        {
            atomic_ptr_clear(&blockAt(block).active_adapter);
            /** @brief 실패한 activate는 자체 hardware를 정지 상태로 남겨야 합니다. */
            int restore_error = 0;
            if (!restoreRouteState(context, restore_error))
            {
                latchFault(context, block, SerialFabricResult::release_failed, restore_error);
                unlockFabric();
                return SerialFabricResult::release_failed;
            }
            const IoResourceResult rollback_result = internal::rollbackIoResources(context.lease);
            if (rollback_result != IoResourceResult::success)
            {
                latchFault(context, block, SerialFabricResult::release_failed, driver_error);
                result = SerialFabricResult::release_failed;
            }
            else
            {
                context.lease = {};
                context.state = SerialFabricState::staged;
                record(context, result, driver_error);
            }
            unlockFabric();
            return result;
        }

        const IoResourceResult commit_result = internal::commitIoResources(context.lease);
        if (commit_result != IoResourceResult::success)
        {
            int cleanup_error = 0;
            const auto stop_result = context.adapter->request_stop(instance_, cleanup_error);
            if (stop_result != SerialFabricResult::success ||
                !waitStoppedWithoutFabricLock(context, instance_, block, 100000U))
            {
                /** @brief reset 전까지 hardware·핀·DMA·전원 lease를 계속 소유합니다. */
                latchFault(context, block, SerialFabricResult::stop_timeout, cleanup_error);
                unlockFabric();
                return SerialFabricResult::stop_timeout;
            }
            const SerialFabricResult cleanup_result =
                context.adapter->deactivate(instance_, cleanup_error);
            if (cleanup_result != SerialFabricResult::success ||
                !restoreRouteState(context, cleanup_error))
            {
                latchFault(context, block, SerialFabricResult::release_failed, cleanup_error);
                unlockFabric();
                return SerialFabricResult::release_failed;
            }
            const IoResourceResult rollback_result = internal::rollbackIoResources(context.lease);
            atomic_ptr_clear(&blockAt(block).active_adapter);
            if ((cleanup_result != SerialFabricResult::success) ||
                (rollback_result != IoResourceResult::success))
            {
                latchFault(context, block, SerialFabricResult::release_failed, cleanup_error);
            }
            else
            {
                context.lease = {};
                context.state = SerialFabricState::staged;
                record(context, mapResourceResult(commit_result));
            }
            const auto observed = context.last_result;
            unlockFabric();
            return observed;
        }

        context.state = SerialFabricState::active;
        record(context, SerialFabricResult::success);
        unlockFabric();
        return SerialFabricResult::success;
    }

    SerialFabricResult SerialFabricHandle::deactivate(std::uint32_t timeout_us) noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        if (timeout_us == 0U)
        {
            return SerialFabricResult::invalid_argument;
        }
        lockFabric();
        auto &context = contextAt(handle_index_);
        const int block = blockIndex(instance_);
        if ((block < 0) || blockAt(block).faulted || (context.state == SerialFabricState::faulted))
        {
            record(context, SerialFabricResult::faulted);
            unlockFabric();
            return SerialFabricResult::faulted;
        }
        if (blockAt(block).wait_in_progress)
        {
            record(context, SerialFabricResult::wrong_state);
            unlockFabric();
            return SerialFabricResult::wrong_state;
        }
        if ((context.state != SerialFabricState::active) || (context.adapter == nullptr))
        {
            record(context, SerialFabricResult::wrong_state);
            unlockFabric();
            return SerialFabricResult::wrong_state;
        }

        context.state = SerialFabricState::cancelling;
        int driver_error = 0;
        SerialFabricResult result = context.adapter->request_stop(instance_, driver_error);
        if (result != SerialFabricResult::success)
        {
            latchFault(context, block, result, driver_error);
            unlockFabric();
            return result;
        }

        if (!waitStoppedWithoutFabricLock(context, instance_, block, timeout_us))
        {
            latchFault(context, block, SerialFabricResult::stop_timeout, driver_error);
            unlockFabric();
            return SerialFabricResult::stop_timeout;
        }

        result = context.adapter->deactivate(instance_, driver_error);
        if (result != SerialFabricResult::success)
        {
            latchFault(context, block, result, driver_error);
            unlockFabric();
            return result;
        }
        atomic_ptr_clear(&blockAt(block).active_adapter);
        if (!restoreRouteState(context, driver_error))
        {
            latchFault(context, block, SerialFabricResult::release_failed, driver_error);
            unlockFabric();
            return SerialFabricResult::release_failed;
        }
        const IoResourceResult release_result = internal::releaseIoResources(context.lease);
        if (release_result != IoResourceResult::success)
        {
            latchFault(context, block, SerialFabricResult::release_failed, driver_error);
            unlockFabric();
            return SerialFabricResult::release_failed;
        }

        context.lease = {};
        context.state = SerialFabricState::inactive;
        context.resource_count = 0U;
        record(context, SerialFabricResult::success);
        unlockFabric();
        return SerialFabricResult::success;
    }
} // namespace nucode::arduino
namespace nucode::arduino::internal
{
    using namespace serial;
    SerialFabricResult executeSerialFabricRecovery(SerialPersonality personality,
                                                   std::uint8_t instance,
                                                   SerialFabricRecovery recovery) noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        const int index = handleIndex(personality, instance);
        const int block = blockIndex(instance);
        if (index < 0 || block < 0 || recovery == nullptr)
        {
            return SerialFabricResult::invalid_argument;
        }
        lockFabric();
        auto &context = contextAt(index);
        if (blockAt(block).faulted || context.state == SerialFabricState::faulted)
        {
            record(context, SerialFabricResult::faulted);
            unlockFabric();
            return SerialFabricResult::faulted;
        }
        if (blockAt(block).wait_in_progress)
        {
            record(context, SerialFabricResult::wrong_state);
            unlockFabric();
            return SerialFabricResult::wrong_state;
        }
        if (context.state != SerialFabricState::staged)
        {
            record(context, SerialFabricResult::wrong_state);
            unlockFabric();
            return SerialFabricResult::wrong_state;
        }
        context.lease = {};
        const auto reserve_result = internal::reserveIoResources(
            {ownerKind(personality), instance}, context.resources, context.resource_count,
            IoAcquirePolicy::exclusive, context.lease);
        if (reserve_result != IoResourceResult::success)
        {
            const auto result = mapResourceResult(reserve_result);
            record(context, result);
            unlockFabric();
            return result;
        }
        int driver_error = 0;
        SerialFabricResult result = SerialFabricResult::success;
        if (!saveRouteState(context, instance, driver_error))
        {
            result = SerialFabricResult::driver_error;
        }
        else
        {
            result = recovery(instance, context.route, driver_error);
        }
        int restore_error = 0;
        const bool restored = restoreRouteState(context, restore_error);
        if (!restored)
        {
            latchFault(context, block, SerialFabricResult::release_failed, restore_error);
        }
        else
        {
            const auto rollback_result = internal::rollbackIoResources(context.lease);
            if (rollback_result != IoResourceResult::success)
            {
                latchFault(context, block, SerialFabricResult::release_failed, restore_error);
            }
            else
            {
                context.lease = {};
                context.state = SerialFabricState::staged;
                record(context, result, driver_error);
            }
        }
        const auto observed = context.last_result;
        unlockFabric();
        return observed;
    }
} // namespace nucode::arduino::internal
