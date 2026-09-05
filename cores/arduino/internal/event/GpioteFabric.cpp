/** @file @brief EventFabric의 기존 peripheral 책임을 유지하는 내부 구현입니다. */
#include <internal/event/EventFabricInternal.h>
#include <hal/nrf_gpio.h>
#include <hal/nrf_gpiote.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/util.h>

namespace nucode::arduino
{
    using namespace internal::event;
    namespace
    {
        [[nodiscard]] nrf_gpiote_polarity_t gpiotePolarity(GpiotePolarity polarity) noexcept
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
            {
                return NRF_GPIO_PIN_MAP(0U, description.gpio.pin);
            }
#endif
#if DT_NODE_HAS_STATUS_OKAY(DT_NODELABEL(gpio1))
            if (description.gpio.port == DEVICE_DT_GET(DT_NODELABEL(gpio1)))
            {
                return NRF_GPIO_PIN_MAP(1U, description.gpio.pin);
            }
#endif
            return UINT32_MAX;
        }

        [[nodiscard]] bool gpioteRoute(const GpioteContext &context,
                                       const internal::PinDescription &description) noexcept
        {
            const PinRoute port = context.instance == 20U ? PinRoute::port1 : PinRoute::port0;
            return internal::hasPinRoute(description.routes, PinRoute::gpiote) &&
                   internal::hasPinRoute(description.routes, port);
        }

    } // namespace

    std::uint8_t GpioteFabric::instance() const noexcept
    {
        return instance_;
    }

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

    EventFabricResult GpioteFabric::acquireInput(std::uint8_t channel, pin_size_t pin,
                                                 GpiotePolarity polarity) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = gpioteContext(instance_);
        const auto *const description = internal::pinDescription(pin);
        if (context == nullptr || channel >= context->channel_count || description == nullptr ||
            description->canonical_pin != pin ||
            description->policy == PinPolicy::system_reserved ||
            !gpioteRoute(*context, *description) ||
            !internal::hasPinCapability(description->capabilities, PinCapability::digital_input))
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::unsupported_route;
        }
        IoResourceId resources[] = {
            internal::peripheralIoResource(IoResourceKind::gpiote_channel, channel, context->reg),
            internal::gpioIoResource(description->gpio),
        };
        auto &channel_context = context->channels[channel];
        EventFabricResult result = claimResources(channel_context, {IoOwnerKind::gpiote, instance_},
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
                nrf_gpiote_event_configure(context->reg, channel, physicalPin(*description),
                                           gpiotePolarity(polarity));
                nrf_gpiote_event_enable(context->reg, channel);
                channel_context.pin = pin;
                channel_context.output = false;
            }
        }
        k_mutex_unlock(&eventFabricMutex());
        return result;
    }

    EventFabricResult GpioteFabric::acquireOutput(std::uint8_t channel, pin_size_t pin,
                                                  GpiotePolarity polarity,
                                                  bool initial_high) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = gpioteContext(instance_);
        const auto *const description = internal::pinDescription(pin);
        if (context == nullptr || channel >= context->channel_count || description == nullptr ||
            description->canonical_pin != pin ||
            description->policy == PinPolicy::system_reserved ||
            !gpioteRoute(*context, *description) ||
            !internal::hasPinCapability(description->capabilities, PinCapability::digital_output))
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::unsupported_route;
        }
        IoResourceId resources[] = {
            internal::peripheralIoResource(IoResourceKind::gpiote_channel, channel, context->reg),
            internal::gpioIoResource(description->gpio),
        };
        auto &channel_context = context->channels[channel];
        EventFabricResult result = claimResources(channel_context, {IoOwnerKind::gpiote, instance_},
                                                  resources, ARRAY_SIZE(resources));
        if (result == EventFabricResult::success)
        {
            const int error = gpio_pin_configure_dt(
                &description->gpio, initial_high ? GPIO_OUTPUT_ACTIVE : GPIO_OUTPUT_INACTIVE);
            if (error != 0)
            {
                (void)releaseResources(channel_context);
                result = EventFabricResult::driver_error;
            }
            else
            {
                nrf_gpiote_task_configure(
                    context->reg, channel, physicalPin(*description), gpiotePolarity(polarity),
                    initial_high ? NRF_GPIOTE_INITIAL_VALUE_HIGH : NRF_GPIOTE_INITIAL_VALUE_LOW);
                nrf_gpiote_task_enable(context->reg, channel);
                channel_context.pin = pin;
                channel_context.output = true;
            }
        }
        k_mutex_unlock(&eventFabricMutex());
        return result;
    }

    EventFabricResult GpioteFabric::release(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = gpioteContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        auto &channel_context = context->channels[channel];
        if (!channel_context.active)
        {
            k_mutex_unlock(&eventFabricMutex());
            return EventFabricResult::wrong_state;
        }
        nrf_gpiote_te_default(context->reg, channel);
        const auto *const description = internal::pinDescription(channel_context.pin);
        if (description != nullptr)
        {
            (void)gpio_pin_configure_dt(&description->gpio, GPIO_INPUT);
        }
        const auto result = releaseResources(channel_context);
        k_mutex_unlock(&eventFabricMutex());
        return result;
    }

    EventEndpoint GpioteFabric::inEvent(std::uint8_t channel) const noexcept
    {
        const auto *const context = gpioteContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            return {};
        }
        return {nrf_gpiote_event_address_get(context->reg, nrf_gpiote_in_event_get(channel)),
                context->domain, EventEndpointRole::publisher};
    }

    EventEndpoint GpioteFabric::outTask(std::uint8_t channel) const noexcept
    {
        const auto *const context = gpioteContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            return {};
        }
        return {nrf_gpiote_task_address_get(context->reg, nrf_gpiote_out_task_get(channel)),
                context->domain, EventEndpointRole::subscriber};
    }

    EventEndpoint GpioteFabric::setTask(std::uint8_t channel) const noexcept
    {
        const auto *const context = gpioteContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            return {};
        }
        return {nrf_gpiote_task_address_get(context->reg, nrf_gpiote_set_task_get(channel)),
                context->domain, EventEndpointRole::subscriber};
    }

    EventEndpoint GpioteFabric::clearTask(std::uint8_t channel) const noexcept
    {
        const auto *const context = gpioteContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            return {};
        }
        return {nrf_gpiote_task_address_get(context->reg, nrf_gpiote_clr_task_get(channel)),
                context->domain, EventEndpointRole::subscriber};
    }

} // namespace nucode::arduino
