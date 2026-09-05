/** @file @brief EventFabric의 기존 peripheral 책임을 유지하는 내부 구현입니다. */
#include <internal/event/EventFabricInternal.h>
#include <hal/nrf_timer.h>
#include <internal/timer_clock.h>

namespace nucode::arduino
{
    using namespace internal::event;
    namespace
    {
        [[nodiscard]] nrf_timer_task_t timerTask(TimerTask task, std::uint8_t channel) noexcept
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

    } // namespace

    std::uint8_t TimerFabric::instance() const noexcept
    {
        return instance_;
    }

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
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        const auto *const context = timerContext(instance_);
        const bool value = context != nullptr && context->active;
        k_mutex_unlock(&eventFabricMutex());
        return value;
    }

    EventFabricResult TimerFabric::acquire(std::uint32_t frequency_hz) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        std::uint32_t prescaler = 0U;
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr)
        {
            k_mutex_unlock(&eventFabricMutex());
            return EventFabricResult::unsupported_instance;
        }
        if (!internal::timerPrescalerFor(NRF_TIMER_BASE_FREQUENCY_GET(context->reg), frequency_hz,
                                         NRF_TIMER_PRESCALER_MAX, prescaler))
        {
            k_mutex_unlock(&eventFabricMutex());
            return EventFabricResult::invalid_argument;
        }
        if (context->active)
        {
            k_mutex_unlock(&eventFabricMutex());
            return EventFabricResult::wrong_state;
        }
        const IoResourceId resource =
            internal::peripheralIoResource(IoResourceKind::timer_block, instance_, context->reg);
        context->token = {};
        const IoResourceResult acquire_result =
            internal::acquireIoResources({IoOwnerKind::timer, instance_}, &resource, 1U,
                                         IoAcquirePolicy::exclusive, context->token);
        if (acquire_result != IoResourceResult::success)
        {
            const auto result = mapResourceResult(acquire_result);
            k_mutex_unlock(&eventFabricMutex());
            return result;
        }
        nrf_timer_task_trigger(context->reg, NRF_TIMER_TASK_STOP);
        nrf_timer_task_trigger(context->reg, NRF_TIMER_TASK_CLEAR);
        nrf_timer_mode_set(context->reg, NRF_TIMER_MODE_TIMER);
        nrf_timer_bit_width_set(context->reg, NRF_TIMER_BIT_WIDTH_32);
        nrf_timer_prescaler_set(context->reg, prescaler);
        nrf_timer_shorts_set(context->reg, static_cast<nrf_timer_short_mask_t>(0U));
        context->active = true;
        k_mutex_unlock(&eventFabricMutex());
        return EventFabricResult::success;
    }

    EventFabricResult TimerFabric::setCompare(std::uint8_t channel, std::uint32_t ticks,
                                              bool clear_on_match, bool stop_on_match) noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr || !context->active || channel >= context->channel_count ||
            ticks == 0U)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::invalid_argument;
        }
        const auto cc = static_cast<nrf_timer_cc_channel_t>(channel);
        nrf_timer_cc_set(context->reg, cc, ticks);
        const auto clear_mask = nrf_timer_short_compare_clear_get(channel);
        const auto stop_mask = nrf_timer_short_compare_stop_get(channel);
        nrf_timer_shorts_disable(context->reg,
                                 static_cast<nrf_timer_short_mask_t>(clear_mask | stop_mask));
        nrf_timer_short_mask_t enable_mask = static_cast<nrf_timer_short_mask_t>(0U);
        if (clear_on_match)
        {
            enable_mask = static_cast<nrf_timer_short_mask_t>(enable_mask | clear_mask);
        }
        if (stop_on_match)
        {
            enable_mask = static_cast<nrf_timer_short_mask_t>(enable_mask | stop_mask);
        }
        if (enable_mask != 0U)
        {
            nrf_timer_shorts_enable(context->reg, enable_mask);
        }
        k_mutex_unlock(&eventFabricMutex());
        return EventFabricResult::success;
    }

    std::uint32_t TimerFabric::capture(std::uint8_t channel) noexcept
    {
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr || !context->active || channel >= context->channel_count)
        {
            k_mutex_unlock(&eventFabricMutex());
            return 0U;
        }
        nrf_timer_task_trigger(context->reg, nrf_timer_capture_task_get(channel));
        const auto value =
            nrf_timer_cc_get(context->reg, static_cast<nrf_timer_cc_channel_t>(channel));
        k_mutex_unlock(&eventFabricMutex());
        return value;
    }

    EventEndpoint TimerFabric::task(TimerTask task_kind, std::uint8_t channel) const noexcept
    {
        const auto *const context = timerContext(instance_);
        if (context == nullptr ||
            (task_kind == TimerTask::capture && channel >= context->channel_count))
        {
            return {};
        }
        return {nrf_timer_task_address_get(context->reg, timerTask(task_kind, channel)),
                context->domain, EventEndpointRole::subscriber};
    }

    EventEndpoint TimerFabric::compareEvent(std::uint8_t channel) const noexcept
    {
        const auto *const context = timerContext(instance_);
        if (context == nullptr || channel >= context->channel_count)
        {
            return {};
        }
        return {nrf_timer_event_address_get(context->reg, nrf_timer_compare_event_get(channel)),
                context->domain, EventEndpointRole::publisher};
    }

    EventFabricResult TimerFabric::start() noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr || !context->active)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_timer_task_trigger(context->reg, NRF_TIMER_TASK_START);
        k_mutex_unlock(&eventFabricMutex());
        return EventFabricResult::success;
    }

    EventFabricResult TimerFabric::stop() noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr || !context->active)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_timer_task_trigger(context->reg, NRF_TIMER_TASK_STOP);
        k_mutex_unlock(&eventFabricMutex());
        return EventFabricResult::success;
    }

    EventFabricResult TimerFabric::clear() noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr || !context->active)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_timer_task_trigger(context->reg, NRF_TIMER_TASK_CLEAR);
        k_mutex_unlock(&eventFabricMutex());
        return EventFabricResult::success;
    }

    EventFabricResult TimerFabric::release() noexcept
    {
        if (k_is_in_isr())
        {
            return EventFabricResult::invalid_context;
        }
        k_mutex_lock(&eventFabricMutex(), K_FOREVER);
        auto *const context = timerContext(instance_);
        if (context == nullptr || !context->active)
        {
            k_mutex_unlock(&eventFabricMutex());
            return context == nullptr ? EventFabricResult::unsupported_instance
                                      : EventFabricResult::wrong_state;
        }
        nrf_timer_task_trigger(context->reg, NRF_TIMER_TASK_STOP);
        nrf_timer_shorts_set(context->reg, static_cast<nrf_timer_short_mask_t>(0U));
        const IoResourceResult release_result = internal::releaseIoResources(context->token);
        context->token = {};
        context->active = false;
        k_mutex_unlock(&eventFabricMutex());
        return mapResourceResult(release_result);
    }

} // namespace nucode::arduino
