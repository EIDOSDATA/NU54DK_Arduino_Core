/** @file @brief 기존 EventFabric handle registry와 singleton facade입니다. */
#include <nucode/EventFabric.h>

namespace nucode::arduino
{
    TimerFabric *EventFabric::timer(std::uint8_t instance) noexcept
    {
        static TimerFabric handles[] = {TimerFabric(0U),  TimerFabric(10U), TimerFabric(20U),
                                        TimerFabric(21U), TimerFabric(22U), TimerFabric(23U),
                                        TimerFabric(24U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
            {
                return &handle;
            }
        }
        return nullptr;
    }

    EguFabric *EventFabric::egu(std::uint8_t instance) noexcept
    {
        static EguFabric handles[] = {EguFabric(10U), EguFabric(20U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
            {
                return &handle;
            }
        }
        return nullptr;
    }

    GpioteFabric *EventFabric::gpiote(std::uint8_t instance) noexcept
    {
        static GpioteFabric handles[] = {GpioteFabric(20U), GpioteFabric(30U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
            {
                return &handle;
            }
        }
        return nullptr;
    }

    DppiFabric *EventFabric::dppi(std::uint8_t instance) noexcept
    {
        static DppiFabric handles[] = {DppiFabric(0U), DppiFabric(10U), DppiFabric(20U),
                                       DppiFabric(30U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
            {
                return &handle;
            }
        }
        return nullptr;
    }

    PpibFabric *EventFabric::ppib(std::uint8_t instance) noexcept
    {
        static PpibFabric handles[] = {PpibFabric(0U),  PpibFabric(1U),  PpibFabric(10U),
                                       PpibFabric(11U), PpibFabric(20U), PpibFabric(21U),
                                       PpibFabric(22U), PpibFabric(30U)};
        for (auto &handle : handles)
        {
            if (handle.instance() == instance)
            {
                return &handle;
            }
        }
        return nullptr;
    }

    EventFabric &eventFabric() noexcept
    {
        static EventFabric fabric;
        return fabric;
    }

} // namespace nucode::arduino
