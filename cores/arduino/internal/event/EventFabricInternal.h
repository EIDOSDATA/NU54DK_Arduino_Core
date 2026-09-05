/** @file @brief EventFabric registry context와 내부 accessor 계약입니다. */
#pragma once
#include <nucode/EventFabric.h>
#include <internal/IoResourceManager.h>
#include <internal/pin_description.h>
#include <hal/nrf_dppi.h>
#include <zephyr/kernel.h>
#include <cstddef>
#include <cstdint>

namespace nucode::arduino::internal::event
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

    /** @brief 기존 하나의 mutex 참조를 반환하며 caller가 같은 lock 순서를 유지합니다. */
    k_mutex &eventFabricMutex() noexcept;
    [[nodiscard]] TimerContext *timerContext(std::uint8_t instance) noexcept;
    [[nodiscard]] EguContext *eguContext(std::uint8_t instance) noexcept;
    [[nodiscard]] GpioteContext *gpioteContext(std::uint8_t instance) noexcept;
    [[nodiscard]] DppiContext *dppiContext(std::uint8_t instance) noexcept;
    [[nodiscard]] PpibContext *ppibContext(std::uint8_t instance) noexcept;
    [[nodiscard]] EventFabricResult mapResourceResult(IoResourceResult result) noexcept;
    [[nodiscard]] EventFabricResult claimResources(ChannelContext &context, IoResourceOwner owner,
                                                   const IoResourceId *resources,
                                                   std::size_t count) noexcept;
    [[nodiscard]] EventFabricResult releaseResources(ChannelContext &context) noexcept;
} // namespace nucode::arduino::internal::event
