/** @file @brief EventFabric의 private context 저장소·mutex·metadata 초기화입니다. */
#include "EventFabricInternal.h"
#include <hal/nrf_dppi.h>
#include <hal/nrf_egu.h>
#include <hal/nrf_ppib.h>

namespace nucode::arduino::internal::event
{
    namespace
    {
        K_MUTEX_DEFINE(event_fabric_mutex);

        TimerContext timer_contexts[] = {
            {0U, NRF_TIMER00, 0U, 6U},   {10U, NRF_TIMER10, 10U, 8U}, {20U, NRF_TIMER20, 20U, 6U},
            {21U, NRF_TIMER21, 20U, 6U}, {22U, NRF_TIMER22, 20U, 6U}, {23U, NRF_TIMER23, 20U, 6U},
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
            {0U, NRF_PPIB00, 0U, 8U},    {1U, NRF_PPIB01, 0U, 8U},   {10U, NRF_PPIB10, 10U, 8U},
            {11U, NRF_PPIB11, 10U, 16U}, {20U, NRF_PPIB20, 20U, 8U}, {21U, NRF_PPIB21, 20U, 16U},
            {22U, NRF_PPIB22, 20U, 4U},  {30U, NRF_PPIB30, 30U, 4U},
        };

        int initializeEventFabricMetadata()
        {
            for (auto &context : dppi_contexts)
            {
                context.channel_count = nrf_dppi_channel_number_get(context.reg);
                context.group_count = nrf_dppi_group_number_get(context.reg);
            }
            for (auto &context : ppib_contexts)
            {
                context.channel_count = nrf_ppib_channel_number_get(context.reg);
            }
            for (auto &context : egu_contexts)
            {
                context.channel_count =
                    static_cast<std::uint8_t>(nrf_egu_channel_count(context.reg));
            }
            return 0;
        }

        SYS_INIT(initializeEventFabricMetadata, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);

    } // namespace

    k_mutex &eventFabricMutex() noexcept
    {
        return event_fabric_mutex;
    }

    [[nodiscard]] TimerContext *timerContext(std::uint8_t instance) noexcept
    {
        for (auto &context : timer_contexts)
        {
            if (context.instance == instance)
            {
                return &context;
            }
        }
        return nullptr;
    }

    [[nodiscard]] EguContext *eguContext(std::uint8_t instance) noexcept
    {
        for (auto &context : egu_contexts)
        {
            if (context.instance == instance)
            {
                return &context;
            }
        }
        return nullptr;
    }

    [[nodiscard]] GpioteContext *gpioteContext(std::uint8_t instance) noexcept
    {
        for (auto &context : gpiote_contexts)
        {
            if (context.instance == instance)
            {
                return &context;
            }
        }
        return nullptr;
    }

    [[nodiscard]] DppiContext *dppiContext(std::uint8_t instance) noexcept
    {
        for (auto &context : dppi_contexts)
        {
            if (context.instance == instance)
            {
                return &context;
            }
        }
        return nullptr;
    }

    [[nodiscard]] PpibContext *ppibContext(std::uint8_t instance) noexcept
    {
        for (auto &context : ppib_contexts)
        {
            if (context.instance == instance)
            {
                return &context;
            }
        }
        return nullptr;
    }

    [[nodiscard]] EventFabricResult mapResourceResult(IoResourceResult result) noexcept
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

    [[nodiscard]] EventFabricResult claimResources(ChannelContext &context, IoResourceOwner owner,
                                                   const IoResourceId *resources,
                                                   std::size_t count) noexcept
    {
        if (context.active)
        {
            return EventFabricResult::wrong_state;
        }
        context.token = {};
        const IoResourceResult acquire_result = internal::acquireIoResources(
            owner, resources, count, IoAcquirePolicy::exclusive, context.token);
        if (acquire_result != IoResourceResult::success)
        {
            return mapResourceResult(acquire_result);
        }
        context.active = true;
        return EventFabricResult::success;
    }

    [[nodiscard]] EventFabricResult releaseResources(ChannelContext &context) noexcept
    {
        if (!context.active)
        {
            return EventFabricResult::wrong_state;
        }
        const IoResourceResult release_result = internal::releaseIoResources(context.token);
        context = {};
        return mapResourceResult(release_result);
    }

} // namespace nucode::arduino::internal::event
