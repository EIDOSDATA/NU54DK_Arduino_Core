/** @file @brief EventFabric의 기존 peripheral 책임을 유지하는 내부 구현입니다. */
#include <internal/event/EventFabricInternal.h>
#include <hal/nrf_dppi.h>

namespace nucode::arduino
{
    using namespace internal::event;
    namespace
    {
        [[nodiscard]] bool endpointValid(const EventEndpoint &endpoint, std::uint8_t domain,
                                         EventEndpointRole role) noexcept
        {
            return endpoint.address != 0U && (endpoint.address % 4U) == 0U &&
                   endpoint.domain == domain && endpoint.role == role;
        }

        [[nodiscard]] bool channelOwned(const DppiContext &context, std::uint8_t channel) noexcept
        {
            return channel < context.channel_count && context.channels[channel].active;
        }
    } // namespace

    std::uint8_t DppiFabric::instance() const noexcept
    {
        return instance_;
    }

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
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        const IoResourceId resource =
            internal::peripheralIoResource(IoResourceKind::dppi_channel, channel, context->reg);
        const auto result = claimResources(context->channels[channel],
                                           {IoOwnerKind::dppi, instance_}, &resource, 1U);
        k_mutex_unlock(&eventFabricMutex());
        return result;
    }

    EventFabricResult DppiFabric::releaseChannel(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        if (!context->channels[channel].active)
        {
            k_mutex_unlock(&eventFabricMutex());
            return EventFabricResult::wrong_state;
        }
        nrf_dppi_channels_disable(context->reg, 1UL << channel);
        auto &connection = context->connections[channel];
        if (connection.publisher != 0U)
        {
            NRF_DPPI_ENDPOINT_CLEAR(connection.publisher);
        }
        for (std::size_t index = 0U; index < connection.subscriber_count; ++index)
        {
            NRF_DPPI_ENDPOINT_CLEAR(connection.subscribers[index]);
        }
        connection = {};
        const auto result = releaseResources(context->channels[channel]);
        k_mutex_unlock(&eventFabricMutex());
        return result;
    }

    EventFabricResult DppiFabric::connect(const EventEndpoint &publisher,
                                          const EventEndpoint &subscriber,
                                          std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || !channelOwned(*context, channel))
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        if (!endpointValid(publisher, instance_, EventEndpointRole::publisher) ||
            !endpointValid(subscriber, instance_, EventEndpointRole::subscriber))
        {
            k_mutex_unlock(&eventFabricMutex());
            return EventFabricResult::unsupported_route;
        }
        auto &connection = context->connections[channel];
        if (connection.publisher != 0U && connection.publisher != publisher.address)
        {
            k_mutex_unlock(&eventFabricMutex());
            return EventFabricResult::ownership_conflict;
        }
        bool already_subscribed = false;
        for (std::size_t index = 0U; index < connection.subscriber_count; ++index)
        {
            already_subscribed |= connection.subscribers[index] == subscriber.address;
        }
        if (!already_subscribed && connection.subscriber_count == max_subscribers_per_channel)
        {
            k_mutex_unlock(&eventFabricMutex());
            return EventFabricResult::resource_exhausted;
        }
        connection.publisher = publisher.address;
        if (!already_subscribed)
        {
            connection.subscribers[connection.subscriber_count++] = subscriber.address;
        }
        NRF_DPPI_ENDPOINT_SETUP(publisher.address, channel);
        NRF_DPPI_ENDPOINT_SETUP(subscriber.address, channel);
        k_mutex_unlock(&eventFabricMutex());
        return EventFabricResult::success;
    }

    EventFabricResult DppiFabric::disconnect(const EventEndpoint &publisher,
                                             const EventEndpoint &subscriber,
                                             std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || !channelOwned(*context, channel))
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        auto &connection = context->connections[channel];
        if (connection.publisher != publisher.address)
        {
            k_mutex_unlock(&eventFabricMutex());
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
            k_mutex_unlock(&eventFabricMutex());
            return EventFabricResult::invalid_argument;
        }
        NRF_DPPI_ENDPOINT_CLEAR(subscriber.address);
        for (std::size_t index = found + 1U; index < connection.subscriber_count; ++index)
        {
            connection.subscribers[index - 1U] = connection.subscribers[index];
        }
        --connection.subscriber_count;
        if (connection.subscriber_count == 0U)
        {
            NRF_DPPI_ENDPOINT_CLEAR(publisher.address);
            connection.publisher = 0U;
        }
        k_mutex_unlock(&eventFabricMutex());
        return EventFabricResult::success;
    }

    EventFabricResult DppiFabric::enable(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || !channelOwned(*context, channel))
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_dppi_channels_enable(context->reg, 1UL << channel);
        k_mutex_unlock(&eventFabricMutex());
        return EventFabricResult::success;
    }

    EventFabricResult DppiFabric::disable(std::uint8_t channel) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || !channelOwned(*context, channel))
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_dppi_channels_disable(context->reg, 1UL << channel);
        k_mutex_unlock(&eventFabricMutex());
        return EventFabricResult::success;
    }

    EventFabricResult DppiFabric::acquireGroup(std::uint8_t group,
                                               std::uint32_t channel_mask) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = dppiContext(instance_);
        const std::uint32_t valid_mask = context != nullptr && context->channel_count < 32U
                                             ? (1UL << context->channel_count) - 1UL
                                             : UINT32_MAX;
        if (context == nullptr || group >= context->group_count || channel_mask == 0U ||
            (channel_mask & ~valid_mask) != 0U)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        for (std::uint8_t channel = 0U; channel < context->channel_count; ++channel)
        {
            if ((channel_mask & (1UL << channel)) != 0U && !context->channels[channel].active)
            {
                k_mutex_unlock(&eventFabricMutex());
                return EventFabricResult::ownership_conflict;
            }
        }
        const IoResourceId resource =
            internal::peripheralIoResource(IoResourceKind::dppi_group, group, context->reg);
        const auto result =
            claimResources(context->groups[group], {IoOwnerKind::dppi, instance_}, &resource, 1U);
        if (result == EventFabricResult::success)
        {
            nrf_dppi_channels_group_set(context->reg, channel_mask,
                                        static_cast<nrf_dppi_channel_group_t>(group));
        }
        k_mutex_unlock(&eventFabricMutex());
        return result;
    }

    EventFabricResult DppiFabric::releaseGroup(std::uint8_t group) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = dppiContext(instance_);
        if (context == nullptr || group >= context->group_count || !context->groups[group].active)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_dppi_group_disable(context->reg, static_cast<nrf_dppi_channel_group_t>(group));
        nrf_dppi_group_clear(context->reg, static_cast<nrf_dppi_channel_group_t>(group));
        const auto result = releaseResources(context->groups[group]);
        k_mutex_unlock(&eventFabricMutex());
        return result;
    }

} // namespace nucode::arduino
