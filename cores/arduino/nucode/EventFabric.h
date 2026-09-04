/**
 * @file EventFabric.h
 * @brief TIMER/GPIOTE/EGU/DPPI/PPIB 전 instance의 v0.4 후보 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_NUCODE_EVENT_FABRIC_H_
#define NUCODE_ARDUINO_CORE_NUCODE_EVENT_FABRIC_H_

#include <api/Common.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino
{

    enum class EventFabricResult : std::uint8_t
    {
        success = 0U,
        invalid_context,
        invalid_argument,
        unsupported_instance,
        unsupported_route,
        wrong_state,
        ownership_conflict,
        resource_exhausted,
        driver_error,
        release_failed,
    };

    enum class EventEndpointRole : std::uint8_t
    {
        publisher = 0U,
        subscriber,
    };

    /** @brief 동일 DPPI domain 안에서만 연결할 수 있는 task/event endpoint입니다.
     */
    struct EventEndpoint
    {
        std::uintptr_t address{0U};
        std::uint8_t domain{0xFFU};
        EventEndpointRole role{EventEndpointRole::publisher};
    };

    enum class TimerTask : std::uint8_t
    {
        start = 0U,
        stop,
        clear,
        count,
        capture,
    };

    /** @brief TIMER00/10/20~24의 block-exclusive handle입니다. */
    class TimerFabric
    {
    public:
        [[nodiscard]] std::uint8_t instance() const noexcept;
        [[nodiscard]] std::uint8_t domain() const noexcept;
        [[nodiscard]] std::uint8_t channelCount() const noexcept;
        [[nodiscard]] bool active() const noexcept;
        [[nodiscard]] EventFabricResult
        acquire(std::uint32_t frequency_hz = 1000000U) noexcept;
        [[nodiscard]] EventFabricResult
        setCompare(std::uint8_t channel, std::uint32_t ticks,
                   bool clear_on_match = false, bool stop_on_match = false) noexcept;
        [[nodiscard]] std::uint32_t capture(std::uint8_t channel) noexcept;
        [[nodiscard]] EventEndpoint task(TimerTask task,
                                         std::uint8_t channel = 0U) const noexcept;
        [[nodiscard]] EventEndpoint compareEvent(std::uint8_t channel) const noexcept;
        [[nodiscard]] EventFabricResult start() noexcept;
        [[nodiscard]] EventFabricResult stop() noexcept;
        [[nodiscard]] EventFabricResult clear() noexcept;
        [[nodiscard]] EventFabricResult release() noexcept;

    private:
        friend class EventFabric;
        constexpr explicit TimerFabric(std::uint8_t instance) noexcept
            : instance_(instance) {}
        std::uint8_t instance_;
    };

    /** @brief EGU10/20 channel의 software event handle입니다. */
    class EguFabric
    {
    public:
        [[nodiscard]] std::uint8_t instance() const noexcept;
        [[nodiscard]] std::uint8_t domain() const noexcept;
        [[nodiscard]] std::uint8_t channelCount() const noexcept;
        [[nodiscard]] EventFabricResult acquire(std::uint8_t channel) noexcept;
        [[nodiscard]] EventFabricResult release(std::uint8_t channel) noexcept;
        [[nodiscard]] EventFabricResult trigger(std::uint8_t channel) noexcept;
        [[nodiscard]] EventEndpoint task(std::uint8_t channel) const noexcept;
        [[nodiscard]] EventEndpoint event(std::uint8_t channel) const noexcept;

    private:
        friend class EventFabric;
        constexpr explicit EguFabric(std::uint8_t instance) noexcept
            : instance_(instance) {}
        std::uint8_t instance_;
    };

    enum class GpiotePolarity : std::uint8_t
    {
        low_to_high = 0U,
        high_to_low,
        toggle,
    };

    /** @brief GPIOTE20/30 channel의 task/event handle입니다. */
    class GpioteFabric
    {
    public:
        [[nodiscard]] std::uint8_t instance() const noexcept;
        [[nodiscard]] std::uint8_t domain() const noexcept;
        [[nodiscard]] std::uint8_t channelCount() const noexcept;
        [[nodiscard]] EventFabricResult
        acquireInput(std::uint8_t channel, pin_size_t pin,
                     GpiotePolarity polarity) noexcept;
        [[nodiscard]] EventFabricResult
        acquireOutput(std::uint8_t channel, pin_size_t pin, GpiotePolarity polarity,
                      bool initial_high = false) noexcept;
        [[nodiscard]] EventFabricResult release(std::uint8_t channel) noexcept;
        [[nodiscard]] EventEndpoint inEvent(std::uint8_t channel) const noexcept;
        [[nodiscard]] EventEndpoint outTask(std::uint8_t channel) const noexcept;
        [[nodiscard]] EventEndpoint setTask(std::uint8_t channel) const noexcept;
        [[nodiscard]] EventEndpoint clearTask(std::uint8_t channel) const noexcept;

    private:
        friend class EventFabric;
        constexpr explicit GpioteFabric(std::uint8_t instance) noexcept
            : instance_(instance) {}
        std::uint8_t instance_;
    };

    /** @brief DPPIC00/10/20/30의 channel/group ownership과 endpoint 연결입니다. */
    class DppiFabric
    {
    public:
        [[nodiscard]] std::uint8_t instance() const noexcept;
        [[nodiscard]] std::uint8_t channelCount() const noexcept;
        [[nodiscard]] std::uint8_t groupCount() const noexcept;
        [[nodiscard]] EventFabricResult acquireChannel(std::uint8_t channel) noexcept;
        [[nodiscard]] EventFabricResult releaseChannel(std::uint8_t channel) noexcept;
        [[nodiscard]] EventFabricResult connect(const EventEndpoint &publisher,
                                                const EventEndpoint &subscriber,
                                                std::uint8_t channel) noexcept;
        [[nodiscard]] EventFabricResult disconnect(const EventEndpoint &publisher,
                                                   const EventEndpoint &subscriber,
                                                   std::uint8_t channel) noexcept;
        [[nodiscard]] EventFabricResult enable(std::uint8_t channel) noexcept;
        [[nodiscard]] EventFabricResult disable(std::uint8_t channel) noexcept;
        [[nodiscard]] EventFabricResult
        acquireGroup(std::uint8_t group, std::uint32_t channel_mask) noexcept;
        [[nodiscard]] EventFabricResult releaseGroup(std::uint8_t group) noexcept;

    private:
        friend class EventFabric;
        constexpr explicit DppiFabric(std::uint8_t instance) noexcept
            : instance_(instance) {}
        std::uint8_t instance_;
    };

    /** @brief PPIB00/01/10/11/20/21/22/30의 bridge endpoint입니다. */
    class PpibFabric
    {
    public:
        [[nodiscard]] std::uint8_t instance() const noexcept;
        [[nodiscard]] std::uint8_t domain() const noexcept;
        [[nodiscard]] std::uint8_t channelCount() const noexcept;
        [[nodiscard]] EventFabricResult acquire(std::uint8_t channel) noexcept;
        [[nodiscard]] EventFabricResult release(std::uint8_t channel) noexcept;
        [[nodiscard]] EventEndpoint sendTask(std::uint8_t channel) const noexcept;
        [[nodiscard]] EventEndpoint receiveEvent(std::uint8_t channel) const noexcept;

    private:
        friend class EventFabric;
        constexpr explicit PpibFabric(std::uint8_t instance) noexcept
            : instance_(instance) {}
        std::uint8_t instance_;
    };

    /** @brief M25 event fabric 전 instance factory입니다. */
    class EventFabric
    {
    public:
        [[nodiscard]] TimerFabric *timer(std::uint8_t instance) noexcept;
        [[nodiscard]] EguFabric *egu(std::uint8_t instance) noexcept;
        [[nodiscard]] GpioteFabric *gpiote(std::uint8_t instance) noexcept;
        [[nodiscard]] DppiFabric *dppi(std::uint8_t instance) noexcept;
        [[nodiscard]] PpibFabric *ppib(std::uint8_t instance) noexcept;

    private:
        friend EventFabric &eventFabric() noexcept;
        constexpr EventFabric() noexcept = default;
    };

    [[nodiscard]] EventFabric &eventFabric() noexcept;

} // namespace nucode::arduino

#endif
