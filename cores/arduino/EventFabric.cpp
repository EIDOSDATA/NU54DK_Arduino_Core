/**
 * @file EventFabric.cpp
 * @brief M25 TIMER/GPIOTE/EGU/DPPI/PPIB 전 instance event fabric입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <nucode/EventFabric.h>

#include "internal/IoResourceManager.h"
#include "internal/pin_description.h"
#include "internal/timer_clock.h"

#include <hal/nrf_dppi.h>
#include <hal/nrf_egu.h>
#include <hal/nrf_gpio.h>
#include <hal/nrf_gpiote.h>
#include <hal/nrf_ppib.h>
#include <hal/nrf_timer.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/util.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino
{
    namespace
    {
        using internal::IoAcquirePolicy;
        using internal::IoOwnerKind;
        using internal::IoResourceId;
        using internal::IoResourceKind;
        using internal::IoResourceOwner;
        using internal::IoResourceResult;
        using internal::IoResourceToken;
        using internal::PinCapability;
        using internal::PinPolicy;
        using internal::PinRoute;

        inline constexpr std::size_t max_dppi_channels = 24U;
        inline constexpr std::size_t max_dppi_groups = 6U;
        inline constexpr std::size_t max_event_channels = 16U;
        inline constexpr std::size_t max_subscribers_per_channel = 4U;

        struct TimerContext
        {
            std::uint8_t instance{0U};
            NRF_TIMER_Type *reg{nullptr};
            std::uint8_t domain{0U};
            std::uint8_t channel_count{0U};
            IoResourceToken token{};
            bool active{false};
        };

        struct ChannelContext
        {
            IoResourceToken token{};
            pin_size_t pin{0xFFU};
            bool active{false};
            bool output{false};
        };

        struct EguContext
        {
            std::uint8_t instance{0U};
            NRF_EGU_Type *reg{nullptr};
            std::uint8_t domain{0U};
            std::uint8_t channel_count{0U};
            ChannelContext channels[max_event_channels]{};
        };

        struct GpioteContext
        {
            std::uint8_t instance{0U};
            NRF_GPIOTE_Type *reg{nullptr};
            std::uint8_t domain{0U};
            std::uint8_t channel_count{0U};
            ChannelContext channels[8]{};
        };

        struct DppiConnection
        {
            std::uintptr_t publisher{0U};
            std::uintptr_t subscribers[max_subscribers_per_channel]{};
            std::size_t subscriber_count{0U};
        };

        struct DppiContext
        {
            std::uint8_t instance{0U};
            NRF_DPPIC_Type *reg{nullptr};
            std::uint8_t channel_count{0U};
            std::uint8_t group_count{0U};
            ChannelContext channels[max_dppi_channels]{};
            ChannelContext groups[max_dppi_groups]{};
            DppiConnection connections[max_dppi_channels]{};
        };

        struct PpibContext
        {
            std::uint8_t instance{0U};
            NRF_PPIB_Type *reg{nullptr};
            std::uint8_t domain{0U};
            std::uint8_t channel_count{0U};
            ChannelContext channels[max_event_channels]{};
        };

        K_MUTEX_DEFINE(event_fabric_mutex);

        TimerContext timer_contexts[] = {
            {0U, NRF_TIMER00, 0U, 6U},
            {10U, NRF_TIMER10, 10U, 8U},
            {20U, NRF_TIMER20, 20U, 6U},
            {21U, NRF_TIMER21, 20U, 6U},
            {22U, NRF_TIMER22, 20U, 6U},
            {23U, NRF_TIMER23, 20U, 6U},
            {24U, NRF_TIMER24, 20U, 6U},
        };

        EguContext egu_contexts[] = {
            {10U, NRF_EGU10, 10U, 16U},
            {20U, NRF_EGU20, 20U, 6U},
        };

        GpioteContext gpiote_contexts[] = {
            {20U, NRF_GPIOTE20, 20U, 8U},
            {30U, NRF_GPIOTE30, 30U, 4U},
        };

        DppiContext dppi_contexts[] = {
            {0U, NRF_DPPIC00, 8U, 0U},
            {10U, NRF_DPPIC10, 24U, 0U},
            {20U, NRF_DPPIC20, 16U, 0U},
            {30U, NRF_DPPIC30, 4U, 0U},
        };

        PpibContext ppib_contexts[] = {
            {0U, NRF_PPIB00, 0U, 8U},
            {1U, NRF_PPIB01, 0U, 8U},
            {10U, NRF_PPIB10, 10U, 8U},
            {11U, NRF_PPIB11, 10U, 16U},
            {20U, NRF_PPIB20, 20U, 8U},
            {21U, NRF_PPIB21, 20U, 16U},
            {22U, NRF_PPIB22, 20U, 4U},
            {30U, NRF_PPIB30, 30U, 4U},
        };

        int initializeEventFabricMetadata()
        {
            for (auto &context : dppi_contexts)
            {
                context.channel_count = nrf_dppi_channel_number_get(context.reg);
                context.group_count = nrf_dppi_group_number_get(context.reg);
            }
            for (auto &context : ppib_contexts)
                context.channel_count = nrf_ppib_channel_number_get(context.reg);
            for (auto &context : egu_contexts)
                context.channel_count =
                    static_cast<std::uint8_t>(nrf_egu_channel_count(context.reg));
            return 0;
        }

        SYS_INIT(initializeEventFabricMetadata, APPLICATION,
                 CONFIG_APPLICATION_INIT_PRIORITY);

        [[nodiscard]] TimerContext *timerContext(std::uint8_t instance) noexcept
        {
            for (auto &context : timer_contexts)
            {
                if (context.instance == instance)
                    return &context;
            }
            return nullptr;
        }

        [[nodiscard]] EguContext *eguContext(std::uint8_t instance) noexcept
        {
            for (auto &context : egu_contexts)
            {
                if (context.instance == instance)
                    return &context;
            }
            return nullptr;
        }

        [[nodiscard]] GpioteContext *gpioteContext(std::uint8_t instance) noexcept
        {
            for (auto &context : gpiote_contexts)
            {
                if (context.instance == instance)
                    return &context;
            }
            return nullptr;
        }

        [[nodiscard]] DppiContext *dppiContext(std::uint8_t instance) noexcept
        {
            for (auto &context : dppi_contexts)
            {
                if (context.instance == instance)
                    return &context;
            }
            return nullptr;
        }

        [[nodiscard]] PpibContext *ppibContext(std::uint8_t instance) noexcept
        {
            for (auto &context : ppib_contexts)
            {
                if (context.instance == instance)
                    return &context;
            }
            return nullptr;
        }

        [[nodiscard]] EventFabricResult
        mapResourceResult(IoResourceResult result) noexcept
        {
            switch (result)
            {
            case IoResourceResult::success:
                return EventFabricResult::success;
            case IoResourceResult::invalid_context:
                return EventFabricResult::invalid_context;
            case IoResourceResult::invalid_argument:
                return EventFabricResult::invalid_argument;
            case IoResourceResult::conflict:
                return EventFabricResult::ownership_conflict;
            case IoResourceResult::capacity_exhausted:
                return EventFabricResult::resource_exhausted;
            default:
                return EventFabricResult::release_failed;
            }
        }

        [[nodiscard]] EventFabricResult claimResources(ChannelContext &context,
                                                       IoResourceOwner owner,
                                                       const IoResourceId *resources,
                                                       std::size_t count) noexcept
        {
            if (context.active)
                return EventFabricResult::wrong_state;
            context.token = {};
            const IoResourceResult acquire_result = internal::acquireIoResources(
                owner, resources, count, IoAcquirePolicy::exclusive, context.token);
            if (acquire_result != IoResourceResult::success)
                return mapResourceResult(acquire_result);
            context.active = true;
            return EventFabricResult::success;
        }

        [[nodiscard]] EventFabricResult
        releaseResources(ChannelContext &context) noexcept
        {
            if (!context.active)
                return EventFabricResult::wrong_state;
            const IoResourceResult release_result =
                internal::releaseIoResources(context.token);
            context = {};
            return mapResourceResult(release_result);
        }

        [[nodiscard]] nrf_timer_task_t timerTask(TimerTask task,
                                                 std::uint8_t channel) noexcept
        {
            switch (task)
            {
            case TimerTask::start:
                return NRF_TIMER_TASK_START;
            case TimerTask::stop:
                return NRF_TIMER_TASK_STOP;
            case TimerTask::clear:
                return NRF_TIMER_TASK_CLEAR;
            case TimerTask::count:
                return NRF_TIMER_TASK_COUNT;
            case TimerTask::capture:
                return nrf_timer_capture_task_get(channel);
            default:
                return NRF_TIMER_TASK_START;
            }
        }

        [[nodiscard]] nrf_gpiote_polarity_t
        gpiotePolarity(GpiotePolarity polarity) noexcept
        {
            switch (polarity)
            {
            case GpiotePolarity::low_to_high:
                return NRF_GPIOTE_POLARITY_LOTOHI;
            case GpiotePolarity::high_to_low:
                return NRF_GPIOTE_POLARITY_HITOLO;
            case GpiotePolarity::toggle:
            default:
                return NRF_GPIOTE_POLARITY_TOGGLE;
            }
        }

        [[nodiscard]] std::uint32_t
        physicalPin(const internal::PinDescription &description) noexcept
        {
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio0))
            if (description.gpio.port == DEVICE_DT_GET(DT_NODELABEL(gpio0)))
                return NRF_GPIO_PIN_MAP(0U, description.gpio.pin);
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio1))
            if (description.gpio.port == DEVICE_DT_GET(DT_NODELABEL(gpio1)))
                return NRF_GPIO_PIN_MAP(1U, description.gpio.pin);
#endif
            return UINT32_MAX;
        }

        [[nodiscard]] bool
        gpioteRoute(const GpioteContext &context,
                    const internal::PinDescription &description) noexcept
        {
            const PinRoute port =
                context.instance == 20U ? PinRoute::port1 : PinRoute::port0;
            return internal::hasPinRoute(description.routes, PinRoute::gpiote) &&
                   internal::hasPinRoute(description.routes, port);
        }

        [[nodiscard]] bool endpointValid(const EventEndpoint &endpoint,
                                         std::uint8_t domain,
                                         EventEndpointRole role) noexcept
        {
            return endpoint.address != 0U && (endpoint.address % 4U) == 0U &&
                   endpoint.domain == domain && endpoint.role == role;
        }

        [[nodiscard]] bool channelOwned(const DppiContext &context,
                                        std::uint8_t channel) noexcept
        {
            return channel < context.channel_count && context.channels[channel].active;
        }
    } // namespace

    std::uint8_t TimerFabric::instance() const noexcept { return instance_; }

    std::uint8_t TimerFabric::domain() const noexcept
    {
        const auto *const context = timerContext(instance_);
        return context != nullptr ? context->domain : 0xFFU;
    }

    std::uint8_t TimerFabric::channelCount() const noexcept
    {
        const auto *const context = timerContext(instance_);
        return context != nullptr ? context->channel_count : 0U;
    }

    bool TimerFabric::active() const noexcept
    {
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        const auto *const context = timerContext(instance_);
        const bool value = context != nullptr && context->active;
        k_mutex_unlock(&event_fabric_mutex);
        return value;
    }

    EventFabricResult TimerFabric::acquire(std::uint32_t frequency_hz) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        std::uint32_t prescaler = 0U;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return EventFabricResult::unsupported_instance;
        }
        if (!internal::timerPrescalerFor(NRF_TIMER_BASE_FREQUENCY_GET(context->reg),
                                         frequency_hz, NRF_TIMER_PRESCALER_MAX, prescaler))
        {
            k_mutex_unlock(&event_fabric_mutex);
            return EventFabricResult::invalid_argument;
        }
        if (context->active)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return EventFabricResult::wrong_state;
        }
        const IoResourceId resource = internal::peripheralIoResource(
            IoResourceKind::timer_block, instance_, context->reg);
        context->token = {};
        const IoResourceResult acquire_result = internal::acquireIoResources(
            {IoOwnerKind::timer, instance_}, &resource, 1U,
            IoAcquirePolicy::exclusive, context->token);
        if (acquire_result != IoResourceResult::success)
        {
            const auto result = mapResourceResult(acquire_result);
            k_mutex_unlock(&event_fabric_mutex);
            return result;
        }
        nrf_timer_task_trigger(context->reg, NRF_TIMER_TASK_STOP);
        nrf_timer_task_trigger(context->reg, NRF_TIMER_TASK_CLEAR);
        nrf_timer_mode_set(context->reg, NRF_TIMER_MODE_TIMER);
        nrf_timer_bit_width_set(context->reg, NRF_TIMER_BIT_WIDTH_32);
        nrf_timer_prescaler_set(context->reg, prescaler);
        nrf_timer_shorts_set(context->reg, static_cast<nrf_timer_short_mask_t>(0U));
        context->active = true;
        k_mutex_unlock(&event_fabric_mutex);
        return EventFabricResult::success;
    }

    EventFabricResult TimerFabric::setCompare(std::uint8_t channel,
                                              std::uint32_t ticks,
                                              bool clear_on_match,
                                              bool stop_on_match) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr || !context->active ||
            channel >= context->channel_count || ticks == 0U)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        const auto cc = static_cast<nrf_timer_cc_channel_t>(channel);
        nrf_timer_cc_set(context->reg, cc, ticks);
        const auto clear_mask = nrf_timer_short_compare_clear_get(channel);
        const auto stop_mask = nrf_timer_short_compare_stop_get(channel);
        nrf_timer_shorts_disable(context->reg, static_cast<nrf_timer_short_mask_t>(
                                                   clear_mask | stop_mask));
        nrf_timer_short_mask_t enable_mask = static_cast<nrf_timer_short_mask_t>(0U);
        if (clear_on_match)
            enable_mask = static_cast<nrf_timer_short_mask_t>(enable_mask | clear_mask);
        if (stop_on_match)
            enable_mask = static_cast<nrf_timer_short_mask_t>(enable_mask | stop_mask);
        if (enable_mask != 0U)
            nrf_timer_shorts_enable(context->reg, enable_mask);
        k_mutex_unlock(&event_fabric_mutex);
        return EventFabricResult::success;
    }

    std::uint32_t TimerFabric::capture(std::uint8_t channel) noexcept
    {
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr || !context->active ||
            channel >= context->channel_count)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return 0U;
        }
        nrf_timer_task_trigger(context->reg, nrf_timer_capture_task_get(channel));
        const auto value = nrf_timer_cc_get(
            context->reg, static_cast<nrf_timer_cc_channel_t>(channel));
        k_mutex_unlock(&event_fabric_mutex);
        return value;
    }

    EventEndpoint TimerFabric::task(TimerTask task_kind,
                                    std::uint8_t channel) const noexcept
    {
        const auto *const context = timerContext(instance_);
        if (context == nullptr ||
            (task_kind == TimerTask::capture && channel >= context->channel_count))
            return {};
        return {
            nrf_timer_task_address_get(context->reg, timerTask(task_kind, channel)),
            context->domain, EventEndpointRole::subscriber};
    }

    EventEndpoint TimerFabric::compareEvent(std::uint8_t channel) const noexcept
    {
        const auto *const context = timerContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
            return {};
        return {nrf_timer_event_address_get(context->reg,
                                            nrf_timer_compare_event_get(channel)),
                context->domain, EventEndpointRole::publisher};
    }

    EventFabricResult TimerFabric::start() noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr || !context->active)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_timer_task_trigger(context->reg, NRF_TIMER_TASK_START);
        k_mutex_unlock(&event_fabric_mutex);
        return EventFabricResult::success;
    }

    EventFabricResult TimerFabric::stop() noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr || !context->active)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_timer_task_trigger(context->reg, NRF_TIMER_TASK_STOP);
        k_mutex_unlock(&event_fabric_mutex);
        return EventFabricResult::success;
    }

    EventFabricResult TimerFabric::clear() noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr || !context->active)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_timer_task_trigger(context->reg, NRF_TIMER_TASK_CLEAR);
        k_mutex_unlock(&event_fabric_mutex);
        return EventFabricResult::success;
    }

    EventFabricResult TimerFabric::release() noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr || !context->active)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_timer_task_trigger(context->reg, NRF_TIMER_TASK_STOP);
        nrf_timer_shorts_set(context->reg, static_cast<nrf_timer_short_mask_t>(0U));
        const IoResourceResult release_result =
            internal::releaseIoResources(context->token);
        context->token = {};
        context->active = false;
        k_mutex_unlock(&event_fabric_mutex);
        return mapResourceResult(release_result);
    }

    std::uint8_t EguFabric::instance() const noexcept { return instance_; }

    std::uint8_t EguFabric::domain() const noexcept
    {
        const auto *const context = eguContext(instance_);
        return context != nullptr ? context->domain : 0xFFU;
    }

    std::uint8_t EguFabric::channelCount() const noexcept
    {
        const auto *const context = eguContext(instance_);
        return context != nullptr ? context->channel_count : 0U;
    }

    EventFabricResult EguFabric::acquire(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = eguContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        const IoResourceId resource = internal::peripheralIoResource(
            IoResourceKind::event_channel, channel, context->reg);
        const auto result =
            claimResources(context->channels[channel],
                           {IoOwnerKind::application, instance_}, &resource, 1U);
        k_mutex_unlock(&event_fabric_mutex);
        return result;
    }

    EventFabricResult EguFabric::release(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = eguContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        const auto result = releaseResources(context->channels[channel]);
        k_mutex_unlock(&event_fabric_mutex);
        return result;
    }

    EventFabricResult EguFabric::trigger(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = eguContext(instance_);
        if (context == nullptr || channel >= context->channel_count ||
            !context->channels[channel].active)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_egu_task_trigger(context->reg, nrf_egu_trigger_task_get(channel));
        k_mutex_unlock(&event_fabric_mutex);
        return EventFabricResult::success;
    }

    EventEndpoint EguFabric::task(std::uint8_t channel) const noexcept
    {
        const auto *const context = eguContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
            return {};
        return {
            nrf_egu_task_address_get(context->reg, nrf_egu_trigger_task_get(channel)),
            context->domain, EventEndpointRole::subscriber};
    }

    EventEndpoint EguFabric::event(std::uint8_t channel) const noexcept
    {
        const auto *const context = eguContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
            return {};
        return {nrf_egu_event_address_get(context->reg,
                                          nrf_egu_triggered_event_get(channel)),
                context->domain, EventEndpointRole::publisher};
    }

    std::uint8_t GpioteFabric::instance() const noexcept { return instance_; }

    std::uint8_t GpioteFabric::domain() const noexcept
    {
        const auto *const context = gpioteContext(instance_);
        return context != nullptr ? context->domain : 0xFFU;
    }

    std::uint8_t GpioteFabric::channelCount() const noexcept
    {
        const auto *const context = gpioteContext(instance_);
        return context != nullptr ? context->channel_count : 0U;
    }

    EventFabricResult GpioteFabric::acquireInput(std::uint8_t channel,
                                                 pin_size_t pin,
                                                 GpiotePolarity polarity) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = gpioteContext(instance_);
        const auto *const description = internal::pinDescription(pin);
        if (context == nullptr || channel >= context->channel_count ||
            description == nullptr || description->canonical_pin != pin ||
            description->policy == PinPolicy::system_reserved ||
            !gpioteRoute(*context, *description) ||
            !internal::hasPinCapability(description->capabilities,
                                        PinCapability::digital_input))
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::unsupported_route;
        }
        IoResourceId resources[] = {
            internal::peripheralIoResource(IoResourceKind::gpiote_channel, channel,
                                           context->reg),
            internal::gpioIoResource(description->gpio),
        };
        auto &channel_context = context->channels[channel];
        EventFabricResult result =
            claimResources(channel_context, {IoOwnerKind::gpiote, instance_},
                           resources, ARRAY_SIZE(resources));
        if (result == EventFabricResult::success)
        {
            const int error = gpio_pin_configure_dt(&description->gpio, GPIO_INPUT);
            if (error != 0)
            {
                (void)releaseResources(channel_context);
                result = EventFabricResult::driver_error;
            }
            else
            {
                nrf_gpiote_event_configure(context->reg, channel,
                                           physicalPin(*description),
                                           gpiotePolarity(polarity));
                nrf_gpiote_event_enable(context->reg, channel);
                channel_context.pin = pin;
                channel_context.output = false;
            }
        }
        k_mutex_unlock(&event_fabric_mutex);
        return result;
    }

    EventFabricResult GpioteFabric::acquireOutput(std::uint8_t channel,
                                                  pin_size_t pin,
                                                  GpiotePolarity polarity,
                                                  bool initial_high) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = gpioteContext(instance_);
        const auto *const description = internal::pinDescription(pin);
        if (context == nullptr || channel >= context->channel_count ||
            description == nullptr || description->canonical_pin != pin ||
            description->policy == PinPolicy::system_reserved ||
            !gpioteRoute(*context, *description) ||
            !internal::hasPinCapability(description->capabilities,
                                        PinCapability::digital_output))
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::unsupported_route;
        }
        IoResourceId resources[] = {
            internal::peripheralIoResource(IoResourceKind::gpiote_channel, channel,
                                           context->reg),
            internal::gpioIoResource(description->gpio),
        };
        auto &channel_context = context->channels[channel];
        EventFabricResult result =
            claimResources(channel_context, {IoOwnerKind::gpiote, instance_},
                           resources, ARRAY_SIZE(resources));
        if (result == EventFabricResult::success)
        {
            const int error = gpio_pin_configure_dt(
                &description->gpio,
                initial_high ? GPIO_OUTPUT_ACTIVE : GPIO_OUTPUT_INACTIVE);
            if (error != 0)
            {
                (void)releaseResources(channel_context);
                result = EventFabricResult::driver_error;
            }
            else
            {
                nrf_gpiote_task_configure(context->reg, channel,
                                          physicalPin(*description),
                                          gpiotePolarity(polarity),
                                          initial_high ? NRF_GPIOTE_INITIAL_VALUE_HIGH
                                                       : NRF_GPIOTE_INITIAL_VALUE_LOW);
                nrf_gpiote_task_enable(context->reg, channel);
                channel_context.pin = pin;
                channel_context.output = true;
            }
        }
        k_mutex_unlock(&event_fabric_mutex);
        return result;
    }

    EventFabricResult GpioteFabric::release(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = gpioteContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        auto &channel_context = context->channels[channel];
        if (!channel_context.active)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return EventFabricResult::wrong_state;
        }
        nrf_gpiote_te_default(context->reg, channel);
        const auto *const description = internal::pinDescription(channel_context.pin);
        if (description != nullptr)
            (void)gpio_pin_configure_dt(&description->gpio, GPIO_INPUT);
        const auto result = releaseResources(channel_context);
        k_mutex_unlock(&event_fabric_mutex);
        return result;
    }

    EventEndpoint GpioteFabric::inEvent(std::uint8_t channel) const noexcept
    {
        const auto *const context = gpioteContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
            return {};
        return {nrf_gpiote_event_address_get(context->reg,
                                             nrf_gpiote_in_event_get(channel)),
                context->domain, EventEndpointRole::publisher};
    }

    EventEndpoint GpioteFabric::outTask(std::uint8_t channel) const noexcept
    {
        const auto *const context = gpioteContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
            return {};
        return {nrf_gpiote_task_address_get(context->reg,
                                            nrf_gpiote_out_task_get(channel)),
                context->domain, EventEndpointRole::subscriber};
    }

    EventEndpoint GpioteFabric::setTask(std::uint8_t channel) const noexcept
    {
        const auto *const context = gpioteContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
            return {};
        return {nrf_gpiote_task_address_get(context->reg,
                                            nrf_gpiote_set_task_get(channel)),
                context->domain, EventEndpointRole::subscriber};
    }

    EventEndpoint GpioteFabric::clearTask(std::uint8_t channel) const noexcept
    {
        const auto *const context = gpioteContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
            return {};
        return {nrf_gpiote_task_address_get(context->reg,
                                            nrf_gpiote_clr_task_get(channel)),
                context->domain, EventEndpointRole::subscriber};
    }

    std::uint8_t DppiFabric::instance() const noexcept { return instance_; }

    std::uint8_t DppiFabric::channelCount() const noexcept
    {
        const auto *const context = dppiContext(instance_);
        return context != nullptr ? context->channel_count : 0U;
    }

    std::uint8_t DppiFabric::groupCount() const noexcept
    {
        const auto *const context = dppiContext(instance_);
        return context != nullptr ? context->group_count : 0U;
    }

    EventFabricResult DppiFabric::acquireChannel(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        const IoResourceId resource = internal::peripheralIoResource(
            IoResourceKind::dppi_channel, channel, context->reg);
        const auto result =
            claimResources(context->channels[channel], {IoOwnerKind::dppi, instance_},
                           &resource, 1U);
        k_mutex_unlock(&event_fabric_mutex);
        return result;
    }

    EventFabricResult DppiFabric::releaseChannel(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        if (!context->channels[channel].active)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return EventFabricResult::wrong_state;
        }
        nrf_dppi_channels_disable(context->reg, 1UL << channel);
        auto &connection = context->connections[channel];
        if (connection.publisher != 0U)
            NRF_DPPI_ENDPOINT_CLEAR(connection.publisher);
        for (std::size_t index = 0U; index < connection.subscriber_count; ++index)
            NRF_DPPI_ENDPOINT_CLEAR(connection.subscribers[index]);
        connection = {};
        const auto result = releaseResources(context->channels[channel]);
        k_mutex_unlock(&event_fabric_mutex);
        return result;
    }

    EventFabricResult DppiFabric::connect(const EventEndpoint &publisher,
                                          const EventEndpoint &subscriber,
                                          std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || !channelOwned(*context, channel))
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        if (!endpointValid(publisher, instance_, EventEndpointRole::publisher) ||
            !endpointValid(subscriber, instance_, EventEndpointRole::subscriber))
        {
            k_mutex_unlock(&event_fabric_mutex);
            return EventFabricResult::unsupported_route;
        }
        auto &connection = context->connections[channel];
        if (connection.publisher != 0U && connection.publisher != publisher.address)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return EventFabricResult::ownership_conflict;
        }
        bool already_subscribed = false;
        for (std::size_t index = 0U; index < connection.subscriber_count; ++index)
            already_subscribed |= connection.subscribers[index] == subscriber.address;
        if (!already_subscribed &&
            connection.subscriber_count == max_subscribers_per_channel)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return EventFabricResult::resource_exhausted;
        }
        connection.publisher = publisher.address;
        if (!already_subscribed)
            connection.subscribers[connection.subscriber_count++] = subscriber.address;
        NRF_DPPI_ENDPOINT_SETUP(publisher.address, channel);
        NRF_DPPI_ENDPOINT_SETUP(subscriber.address, channel);
        k_mutex_unlock(&event_fabric_mutex);
        return EventFabricResult::success;
    }

    EventFabricResult DppiFabric::disconnect(const EventEndpoint &publisher,
                                             const EventEndpoint &subscriber,
                                             std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || !channelOwned(*context, channel))
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        auto &connection = context->connections[channel];
        if (connection.publisher != publisher.address)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return EventFabricResult::invalid_argument;
        }
        std::size_t found = connection.subscriber_count;
        for (std::size_t index = 0U; index < connection.subscriber_count; ++index)
        {
            if (connection.subscribers[index] == subscriber.address)
            {
                found = index;
                break;
            }
        }
        if (found == connection.subscriber_count)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return EventFabricResult::invalid_argument;
        }
        NRF_DPPI_ENDPOINT_CLEAR(subscriber.address);
        for (std::size_t index = found + 1U; index < connection.subscriber_count;
             ++index)
            connection.subscribers[index - 1U] = connection.subscribers[index];
        --connection.subscriber_count;
        if (connection.subscriber_count == 0U)
        {
            NRF_DPPI_ENDPOINT_CLEAR(publisher.address);
            connection.publisher = 0U;
        }
        k_mutex_unlock(&event_fabric_mutex);
        return EventFabricResult::success;
    }

    EventFabricResult DppiFabric::enable(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || !channelOwned(*context, channel))
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_dppi_channels_enable(context->reg, 1UL << channel);
        k_mutex_unlock(&event_fabric_mutex);
        return EventFabricResult::success;
    }

    EventFabricResult DppiFabric::disable(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || !channelOwned(*context, channel))
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_dppi_channels_disable(context->reg, 1UL << channel);
        k_mutex_unlock(&event_fabric_mutex);
        return EventFabricResult::success;
    }

    EventFabricResult
    DppiFabric::acquireGroup(std::uint8_t group,
                             std::uint32_t channel_mask) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = dppiContext(instance_);
        const std::uint32_t valid_mask =
            context != nullptr && context->channel_count < 32U
                ? (1UL << context->channel_count) - 1UL
                : UINT32_MAX;
        if (context == nullptr || group >= context->group_count ||
            channel_mask == 0U || (channel_mask & ~valid_mask) != 0U)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        for (std::uint8_t channel = 0U; channel < context->channel_count; ++channel)
        {
            if ((channel_mask & (1UL << channel)) != 0U &&
                !context->channels[channel].active)
            {
                k_mutex_unlock(&event_fabric_mutex);
                return EventFabricResult::ownership_conflict;
            }
        }
        const IoResourceId resource = internal::peripheralIoResource(
            IoResourceKind::dppi_group, group, context->reg);
        const auto result = claimResources(
            context->groups[group], {IoOwnerKind::dppi, instance_}, &resource, 1U);
        if (result == EventFabricResult::success)
            nrf_dppi_channels_group_set(context->reg, channel_mask,
                                        static_cast<nrf_dppi_channel_group_t>(group));
        k_mutex_unlock(&event_fabric_mutex);
        return result;
    }

    EventFabricResult DppiFabric::releaseGroup(std::uint8_t group) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || group >= context->group_count ||
            !context->groups[group].active)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_dppi_group_disable(context->reg,
                               static_cast<nrf_dppi_channel_group_t>(group));
        nrf_dppi_group_clear(context->reg,
                             static_cast<nrf_dppi_channel_group_t>(group));
        const auto result = releaseResources(context->groups[group]);
        k_mutex_unlock(&event_fabric_mutex);
        return result;
    }

    std::uint8_t PpibFabric::instance() const noexcept { return instance_; }

    std::uint8_t PpibFabric::domain() const noexcept
    {
        const auto *const context = ppibContext(instance_);
        return context != nullptr ? context->domain : 0xFFU;
    }

    std::uint8_t PpibFabric::channelCount() const noexcept
    {
        const auto *const context = ppibContext(instance_);
        return context != nullptr ? context->channel_count : 0U;
    }

    EventFabricResult PpibFabric::acquire(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = ppibContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        const IoResourceId resource = internal::peripheralIoResource(
            IoResourceKind::ppib_channel, channel, context->reg);
        const auto result =
            claimResources(context->channels[channel], {IoOwnerKind::dppi, instance_},
                           &resource, 1U);
        k_mutex_unlock(&event_fabric_mutex);
        return result;
    }

    EventFabricResult PpibFabric::release(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
            return EventFabricResult::invalid_context;
        k_mutex_lock(&event_fabric_mutex, K_FOREVER);
        auto *const context = ppibContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&event_fabric_mutex);
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        const auto result = releaseResources(context->channels[channel]);
        k_mutex_unlock(&event_fabric_mutex);
        return result;
    }

    EventEndpoint PpibFabric::sendTask(std::uint8_t channel) const noexcept
    {
        const auto *const context = ppibContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
            return {};
        return {
            nrf_ppib_task_address_get(context->reg, nrf_ppib_send_task_get(channel)),
            context->domain, EventEndpointRole::subscriber};
    }

    EventEndpoint PpibFabric::receiveEvent(std::uint8_t channel) const noexcept
    {
        const auto *const context = ppibContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
            return {};
        return {nrf_ppib_event_address_get(context->reg,
                                           nrf_ppib_receive_event_get(channel)),
                context->domain, EventEndpointRole::publisher};
    }

    TimerFabric *EventFabric::timer(std::uint8_t instance) noexcept
    {
        static TimerFabric handles[] = {
            TimerFabric(0U), TimerFabric(10U), TimerFabric(20U), TimerFabric(21U),
            TimerFabric(22U), TimerFabric(23U), TimerFabric(24U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
                return &handle;
        }
        return nullptr;
    }

    EguFabric *EventFabric::egu(std::uint8_t instance) noexcept
    {
        static EguFabric handles[] = {EguFabric(10U), EguFabric(20U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
                return &handle;
        }
        return nullptr;
    }

    GpioteFabric *EventFabric::gpiote(std::uint8_t instance) noexcept
    {
        static GpioteFabric handles[] = {GpioteFabric(20U), GpioteFabric(30U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
                return &handle;
        }
        return nullptr;
    }

    DppiFabric *EventFabric::dppi(std::uint8_t instance) noexcept
    {
        static DppiFabric handles[] = {DppiFabric(0U), DppiFabric(10U),
                                       DppiFabric(20U), DppiFabric(30U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
                return &handle;
        }
        return nullptr;
    }

    PpibFabric *EventFabric::ppib(std::uint8_t instance) noexcept
    {
        static PpibFabric handles[] = {
            PpibFabric(0U), PpibFabric(1U), PpibFabric(10U), PpibFabric(11U),
            PpibFabric(20U), PpibFabric(21U), PpibFabric(22U), PpibFabric(30U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
                return &handle;
        }
        return nullptr;
    }

    EventFabric &eventFabric() noexcept
    {
        static EventFabric fabric;
        return fabric;
    }

} // namespace nucode::arduino
