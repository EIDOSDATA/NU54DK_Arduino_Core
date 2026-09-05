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

#include <hal/nrf_gpio.h>
#include <nrfx_power.h>

#include <zephyr/irq.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>

namespace nucode::arduino
{
    namespace
    {
        using internal::IoAcquirePolicy;
        using internal::IoOwnerKind;
        using internal::IoResourceId;
        using internal::IoResourceLease;
        using internal::IoResourceResult;
        using internal::SerialFabricDriverAdapter;
        using internal::ValidatedSerialRoute;

        inline constexpr std::size_t handle_count = 23U;
        inline constexpr std::size_t block_count = 5U;

        struct SavedPin
        {
            std::uint32_t psel{0U};
            std::uint32_t configuration{0U};
            std::uint32_t output{0U};
        };

        struct HandleContext
        {
            ValidatedSerialRoute route{};
            IoResourceId resources[internal::io_resource_lease_capacity]{};
            std::size_t resource_count{0U};
            IoResourceLease lease{};
            const SerialFabricDriverAdapter *adapter{nullptr};
            SerialFabricState state{SerialFabricState::inactive};
            SerialFabricResult last_result{SerialFabricResult::success};
            int last_driver_error{0};
            SavedPin saved_pins[internal::serial_fabric_pin_capacity]{};
            std::size_t saved_pin_count{0U};
            bool constant_latency_owned{false};
        };

        struct BlockContext
        {
            bool faulted{false};
            bool wait_in_progress{false};
            std::uint32_t wait_generation{0U};
            atomic_ptr_t active_adapter{nullptr};
            std::uint8_t active_instance{0U};
        };

        K_MUTEX_DEFINE(fabric_mutex);
        HandleContext contexts[handle_count]{};
        SerialFabricDriverAdapter adapters[handle_count]{};
        bool adapter_registered[handle_count]{};
        BlockContext blocks[block_count]{};

#if defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_UARTE) ||                                          \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIM) ||                                           \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIS) ||                                           \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_TWIM) ||                                           \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_TWIS)
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_UARTE) ||                                          \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIM) ||                                           \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIS)
        void irq00(const void *)
        {
            internal::dispatchSerialFabricIrq(0U);
        }
#endif
        void irq20(const void *)
        {
            internal::dispatchSerialFabricIrq(20U);
        }
        void irq21(const void *)
        {
            internal::dispatchSerialFabricIrq(21U);
        }
        void irq22(const void *)
        {
            internal::dispatchSerialFabricIrq(22U);
        }
        void irq30(const void *)
        {
            internal::dispatchSerialFabricIrq(30U);
        }

        int connectFabricIrqs()
        {
#if defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_UARTE) ||                                          \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIM) ||                                           \
    defined(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_SPIS)
            IRQ_CONNECT(SERIAL00_IRQn, IRQ_PRIO_LOWEST, irq00, nullptr, 0);
#endif
            IRQ_CONNECT(SERIAL20_IRQn, IRQ_PRIO_LOWEST, irq20, nullptr, 0);
            IRQ_CONNECT(SERIAL21_IRQn, IRQ_PRIO_LOWEST, irq21, nullptr, 0);
            IRQ_CONNECT(SERIAL22_IRQn, IRQ_PRIO_LOWEST, irq22, nullptr, 0);
            IRQ_CONNECT(SERIAL30_IRQn, IRQ_PRIO_LOWEST, irq30, nullptr, 0);
            return 0;
        }

        SYS_INIT(connectFabricIrqs, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
#endif

        [[nodiscard]] constexpr int blockIndex(std::uint8_t instance) noexcept
        {
            switch (instance)
            {
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
                                                std::uint8_t instance) noexcept
        {
            const int block = blockIndex(instance);
            if (block < 0)
            {
                return -1;
            }
            switch (personality)
            {
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
            blocks[block].faulted = true;
            blocks[block].wait_in_progress = false;
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
            auto &reservation = blocks[block];
            reservation.wait_in_progress = true;
            ++reservation.wait_generation;
            if (reservation.wait_generation == 0U)
            {
                ++reservation.wait_generation;
            }
            const auto generation = reservation.wait_generation;
            const auto *const adapter = context.adapter;
            k_mutex_unlock(&fabric_mutex);
            const bool stopped = waitStopped(*adapter, instance, timeout_us);
            k_mutex_lock(&fabric_mutex, K_FOREVER);
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

        [[nodiscard]] HandleContext &contextAt(std::uint8_t index) noexcept
        {
            return contexts[index];
        }
    } // namespace

    SerialPersonality SerialFabricHandle::personality() const noexcept
    {
        return personality_;
    }

    std::uint8_t SerialFabricHandle::instance() const noexcept
    {
        return instance_;
    }

    SerialFabricState SerialFabricHandle::state() const noexcept
    {
        k_mutex_lock(&fabric_mutex, K_FOREVER);
        const auto value = contextAt(handle_index_).state;
        k_mutex_unlock(&fabric_mutex);
        return value;
    }

    SerialFabricResult SerialFabricHandle::lastResult() const noexcept
    {
        k_mutex_lock(&fabric_mutex, K_FOREVER);
        const auto value = contextAt(handle_index_).last_result;
        k_mutex_unlock(&fabric_mutex);
        return value;
    }

    int SerialFabricHandle::lastDriverError() const noexcept
    {
        k_mutex_lock(&fabric_mutex, K_FOREVER);
        const int value = contextAt(handle_index_).last_driver_error;
        k_mutex_unlock(&fabric_mutex);
        return value;
    }

    SerialFabricResult
    SerialFabricHandle::stage(const SerialFabricConfiguration &configuration) noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        k_mutex_lock(&fabric_mutex, K_FOREVER);
        auto &context = contextAt(handle_index_);
        const int block = blockIndex(instance_);
        if ((block < 0) || blocks[block].faulted || (context.state == SerialFabricState::faulted))
        {
            record(context, SerialFabricResult::faulted);
            k_mutex_unlock(&fabric_mutex);
            return SerialFabricResult::faulted;
        }
        if (blocks[block].wait_in_progress)
        {
            record(context, SerialFabricResult::wrong_state);
            k_mutex_unlock(&fabric_mutex);
            return SerialFabricResult::wrong_state;
        }
        if ((context.state != SerialFabricState::inactive) &&
            (context.state != SerialFabricState::staged))
        {
            record(context, SerialFabricResult::wrong_state);
            k_mutex_unlock(&fabric_mutex);
            return SerialFabricResult::wrong_state;
        }
        if (!adapter_registered[handle_index_])
        {
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
        if (result == SerialFabricResult::success)
        {
            result = adapters[handle_index_].validate(instance_, candidate, driver_error);
        }
        if (result != SerialFabricResult::success)
        {
            record(context, result, driver_error);
            k_mutex_unlock(&fabric_mutex);
            return result;
        }

        context.route = candidate;
        context.resource_count = resource_count;
        for (std::size_t index = 0U; index < resource_count; ++index)
        {
            context.resources[index] = resources[index];
        }
        context.adapter = &adapters[handle_index_];
        context.state = SerialFabricState::staged;
        record(context, SerialFabricResult::success);
        k_mutex_unlock(&fabric_mutex);
        return SerialFabricResult::success;
    }

    SerialFabricResult SerialFabricHandle::activate() noexcept
    {
        if (k_is_in_isr())
        {
            return SerialFabricResult::invalid_context;
        }
        k_mutex_lock(&fabric_mutex, K_FOREVER);
        auto &context = contextAt(handle_index_);
        const int block = blockIndex(instance_);
        if ((block < 0) || blocks[block].faulted || (context.state == SerialFabricState::faulted))
        {
            record(context, SerialFabricResult::faulted);
            k_mutex_unlock(&fabric_mutex);
            return SerialFabricResult::faulted;
        }
        if (blocks[block].wait_in_progress)
        {
            record(context, SerialFabricResult::wrong_state);
            k_mutex_unlock(&fabric_mutex);
            return SerialFabricResult::wrong_state;
        }
        if ((context.state != SerialFabricState::staged) || (context.adapter == nullptr))
        {
            record(context, SerialFabricResult::wrong_state);
            k_mutex_unlock(&fabric_mutex);
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
            k_mutex_unlock(&fabric_mutex);
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
            k_mutex_unlock(&fabric_mutex);
            return observed;
        }
        blocks[block].active_instance = instance_;
        atomic_ptr_set(&blocks[block].active_adapter,
                       const_cast<SerialFabricDriverAdapter *>(context.adapter));
        SerialFabricResult result =
            context.adapter->activate(instance_, context.route, driver_error);
        if (result != SerialFabricResult::success)
        {
            atomic_ptr_clear(&blocks[block].active_adapter);
            /** @brief 실패한 activate는 자체 hardware를 정지 상태로 남겨야 합니다. */
            int restore_error = 0;
            if (!restoreRouteState(context, restore_error))
            {
                latchFault(context, block, SerialFabricResult::release_failed, restore_error);
                k_mutex_unlock(&fabric_mutex);
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
            k_mutex_unlock(&fabric_mutex);
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
                k_mutex_unlock(&fabric_mutex);
                return SerialFabricResult::stop_timeout;
            }
            const SerialFabricResult cleanup_result =
                context.adapter->deactivate(instance_, cleanup_error);
            if (cleanup_result != SerialFabricResult::success ||
                !restoreRouteState(context, cleanup_error))
            {
                latchFault(context, block, SerialFabricResult::release_failed, cleanup_error);
                k_mutex_unlock(&fabric_mutex);
                return SerialFabricResult::release_failed;
            }
            const IoResourceResult rollback_result = internal::rollbackIoResources(context.lease);
            atomic_ptr_clear(&blocks[block].active_adapter);
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
            k_mutex_unlock(&fabric_mutex);
            return observed;
        }

        context.state = SerialFabricState::active;
        record(context, SerialFabricResult::success);
        k_mutex_unlock(&fabric_mutex);
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
        k_mutex_lock(&fabric_mutex, K_FOREVER);
        auto &context = contextAt(handle_index_);
        const int block = blockIndex(instance_);
        if ((block < 0) || blocks[block].faulted || (context.state == SerialFabricState::faulted))
        {
            record(context, SerialFabricResult::faulted);
            k_mutex_unlock(&fabric_mutex);
            return SerialFabricResult::faulted;
        }
        if (blocks[block].wait_in_progress)
        {
            record(context, SerialFabricResult::wrong_state);
            k_mutex_unlock(&fabric_mutex);
            return SerialFabricResult::wrong_state;
        }
        if ((context.state != SerialFabricState::active) || (context.adapter == nullptr))
        {
            record(context, SerialFabricResult::wrong_state);
            k_mutex_unlock(&fabric_mutex);
            return SerialFabricResult::wrong_state;
        }

        context.state = SerialFabricState::cancelling;
        int driver_error = 0;
        SerialFabricResult result = context.adapter->request_stop(instance_, driver_error);
        if (result != SerialFabricResult::success)
        {
            latchFault(context, block, result, driver_error);
            k_mutex_unlock(&fabric_mutex);
            return result;
        }

        if (!waitStoppedWithoutFabricLock(context, instance_, block, timeout_us))
        {
            latchFault(context, block, SerialFabricResult::stop_timeout, driver_error);
            k_mutex_unlock(&fabric_mutex);
            return SerialFabricResult::stop_timeout;
        }

        result = context.adapter->deactivate(instance_, driver_error);
        if (result != SerialFabricResult::success)
        {
            latchFault(context, block, result, driver_error);
            k_mutex_unlock(&fabric_mutex);
            return result;
        }
        atomic_ptr_clear(&blocks[block].active_adapter);
        if (!restoreRouteState(context, driver_error))
        {
            latchFault(context, block, SerialFabricResult::release_failed, driver_error);
            k_mutex_unlock(&fabric_mutex);
            return SerialFabricResult::release_failed;
        }
        const IoResourceResult release_result = internal::releaseIoResources(context.lease);
        if (release_result != IoResourceResult::success)
        {
            latchFault(context, block, SerialFabricResult::release_failed, driver_error);
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

    UarteHandle *SerialFabric::uarte(std::uint8_t instance) noexcept
    {
        static UarteHandle handles[] = {{0U, 0U}, {20U, 1U}, {21U, 2U}, {22U, 3U}, {30U, 4U}};
        const int block = blockIndex(instance);
        return block < 0 ? nullptr : &handles[block];
    }

    SpimHandle *SerialFabric::spim(std::uint8_t instance) noexcept
    {
        static SpimHandle handles[] = {{0U, 5U}, {20U, 6U}, {21U, 7U}, {22U, 8U}, {30U, 9U}};
        const int block = blockIndex(instance);
        return block < 0 ? nullptr : &handles[block];
    }

    SpisHandle *SerialFabric::spis(std::uint8_t instance) noexcept
    {
        static SpisHandle handles[] = {{0U, 10U}, {20U, 11U}, {21U, 12U}, {22U, 13U}, {30U, 14U}};
        const int block = blockIndex(instance);
        return block < 0 ? nullptr : &handles[block];
    }

    TwimHandle *SerialFabric::twim(std::uint8_t instance) noexcept
    {
        static TwimHandle handles[] = {{20U, 15U}, {21U, 16U}, {22U, 17U}, {30U, 18U}};
        const int block = blockIndex(instance);
        return block <= 0 ? nullptr : &handles[block - 1];
    }

    TwisHandle *SerialFabric::twis(std::uint8_t instance) noexcept
    {
        static TwisHandle handles[] = {{20U, 19U}, {21U, 20U}, {22U, 21U}, {30U, 22U}};
        const int block = blockIndex(instance);
        return block <= 0 ? nullptr : &handles[block - 1];
    }

    SerialFabric &serialFabric() noexcept
    {
        static SerialFabric fabric;
        return fabric;
    }

    namespace internal
    {
        SerialFabricResult
        registerSerialFabricAdapter(SerialPersonality personality, std::uint8_t instance,
                                    const SerialFabricDriverAdapter &adapter) noexcept
        {
            if (k_is_in_isr())
            {
                return SerialFabricResult::invalid_context;
            }
            const int index = handleIndex(personality, instance);
            if ((index < 0) || (adapter.validate == nullptr) || (adapter.activate == nullptr) ||
                (adapter.request_stop == nullptr) || (adapter.stopped == nullptr) ||
                (adapter.deactivate == nullptr) || (adapter.handle_irq == nullptr))
            {
                return index < 0 ? SerialFabricResult::unsupported_instance
                                 : SerialFabricResult::invalid_argument;
            }
            k_mutex_lock(&fabric_mutex, K_FOREVER);
            if (adapter_registered[index] || (contexts[index].state != SerialFabricState::inactive))
            {
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
                                        std::uint8_t instance) noexcept
        {
            const int index = handleIndex(personality, instance);
            if (index < 0)
            {
                return false;
            }
            k_mutex_lock(&fabric_mutex, K_FOREVER);
            const bool active = contexts[index].state == SerialFabricState::active &&
                                !blocks[blockIndex(instance)].wait_in_progress;
            k_mutex_unlock(&fabric_mutex);
            return active;
        }

        SerialFabricOperationGuard::SerialFabricOperationGuard() noexcept
        {
            k_mutex_lock(&fabric_mutex, K_FOREVER);
        }

        SerialFabricOperationGuard::~SerialFabricOperationGuard()
        {
            k_mutex_unlock(&fabric_mutex);
        }

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
            k_mutex_lock(&fabric_mutex, K_FOREVER);
            auto &context = contexts[index];
            if (blocks[block].faulted || context.state == SerialFabricState::faulted)
            {
                record(context, SerialFabricResult::faulted);
                k_mutex_unlock(&fabric_mutex);
                return SerialFabricResult::faulted;
            }
            if (blocks[block].wait_in_progress)
            {
                record(context, SerialFabricResult::wrong_state);
                k_mutex_unlock(&fabric_mutex);
                return SerialFabricResult::wrong_state;
            }
            if (context.state != SerialFabricState::staged)
            {
                record(context, SerialFabricResult::wrong_state);
                k_mutex_unlock(&fabric_mutex);
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
                k_mutex_unlock(&fabric_mutex);
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
            k_mutex_unlock(&fabric_mutex);
            return observed;
        }

        void dispatchSerialFabricIrq(std::uint8_t instance) noexcept
        {
            const int block = blockIndex(instance);
            if (block < 0)
            {
                return;
            }
            auto *const adapter = static_cast<SerialFabricDriverAdapter *>(
                atomic_ptr_get(&blocks[block].active_adapter));
            if (adapter != nullptr)
            {
                adapter->handle_irq(blocks[block].active_instance);
            }
        }

#if defined(CONFIG_ZTEST)
        void resetSerialFabricForTest() noexcept
        {
            if (k_is_in_isr())
            {
                return;
            }
            k_mutex_lock(&fabric_mutex, K_FOREVER);
            for (const auto &block : blocks)
            {
                /** @brief fake adapter 시험에서도 대기 중인 context를 교체하지 않습니다. */
                if (block.wait_in_progress)
                {
                    k_mutex_unlock(&fabric_mutex);
                    return;
                }
            }
            for (auto &context : contexts)
            {
                /** @brief fake adapter ztest 격리 전용이며 실제 hardware 복구 API가 아닙니다. */
                int ignored = 0;
                (void)restoreRouteState(context, ignored);
                context = {};
            }
            for (auto &adapter : adapters)
            {
                adapter = {};
            }
            for (bool &registered : adapter_registered)
            {
                registered = false;
            }
            for (auto &block : blocks)
            {
                block = {};
            }
            k_mutex_unlock(&fabric_mutex);
        }
#endif
    } // namespace internal
} // namespace nucode::arduino
