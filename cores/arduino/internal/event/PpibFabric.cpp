/** @file @brief EventFabric의 기존 peripheral 책임을 유지하는 내부 구현입니다. */
#include <internal/event/EventFabricInternal.h>
#include <hal/nrf_ppib.h>

namespace nucode::arduino
{
    using namespace internal::event;
    std::uint8_t PpibFabric::instance() const noexcept
    {
        return instance_;
    }

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
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = ppibContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        const IoResourceId resource =
            internal::peripheralIoResource(IoResourceKind::ppib_channel, channel, context->reg);
        const auto result = claimResources(context->channels[channel],
                                           {IoOwnerKind::dppi, instance_}, &resource, 1U);
        k_mutex_unlock(&eventFabricMutex());
        return result;
    }

    EventFabricResult PpibFabric::release(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = ppibContext(instance_);
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

    EventEndpoint PpibFabric::sendTask(std::uint8_t channel) const noexcept
    {
        const auto *const context = ppibContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            return {};
        }
        return {nrf_ppib_task_address_get(context->reg, nrf_ppib_send_task_get(channel)),
                context->domain, EventEndpointRole::subscriber};
    }

    EventEndpoint PpibFabric::receiveEvent(std::uint8_t channel) const noexcept
    {
        const auto *const context = ppibContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            return {};
        }
        return {nrf_ppib_event_address_get(context->reg, nrf_ppib_receive_event_get(channel)),
                context->domain, EventEndpointRole::publisher};
    }

} // namespace nucode::arduino
