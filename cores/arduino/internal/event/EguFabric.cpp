/** @file @brief EventFabric의 기존 peripheral 책임을 유지하는 내부 구현입니다. */
#include <internal/event/EventFabricInternal.h>
#include <hal/nrf_egu.h>

namespace nucode::arduino
{
    using namespace internal::event;
    std::uint8_t EguFabric::instance() const noexcept
    {
        return instance_;
    }

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
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = eguContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        const IoResourceId resource =
            internal::peripheralIoResource(IoResourceKind::event_channel, channel, context->reg);
        const auto result = claimResources(context->channels[channel],
                                           {IoOwnerKind::application, instance_}, &resource, 1U);
        k_mutex_unlock(&eventFabricMutex());
        return result;
    }

    EventFabricResult EguFabric::release(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = eguContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        const auto result = releaseResources(context->channels[channel]);
        k_mutex_unlock(&eventFabricMutex());
        return result;
    }

    EventFabricResult EguFabric::trigger(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = eguContext(instance_);
        if (context == nullptr || channel >= context->channel_count ||
            !context->channels[channel].active)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_egu_task_trigger(context->reg, nrf_egu_trigger_task_get(channel));
        k_mutex_unlock(&eventFabricMutex());
        return EventFabricResult::success;
    }

    EventEndpoint EguFabric::task(std::uint8_t channel) const noexcept
    {
        const auto *const context = eguContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            return {};
        }
        return {nrf_egu_task_address_get(context->reg, nrf_egu_trigger_task_get(channel)),
                context->domain, EventEndpointRole::subscriber};
    }

    EventEndpoint EguFabric::event(std::uint8_t channel) const noexcept
    {
        const auto *const context = eguContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            return {};
        }
        return {nrf_egu_event_address_get(context->reg, nrf_egu_triggered_event_get(channel)),
                context->domain, EventEndpointRole::publisher};
    }

} // namespace nucode::arduino
