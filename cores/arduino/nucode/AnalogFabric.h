/**
 * @file AnalogFabric.h
 * @brief SAADC scan과 PWM sequence를 노출하는 v0.4 후보 API입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_ARDUINO_CORE_NUCODE_ANALOG_FABRIC_H_
#define NUCODE_ARDUINO_CORE_NUCODE_ANALOG_FABRIC_H_

#include <api/Common.h>

#include <cstddef>
#include <cstdint>

namespace nucode::arduino
{

    /** @brief M25 analog fabric의 lifecycle 상태입니다. */
    enum class AnalogFabricState : std::uint8_t
    {
        inactive = 0U,
        configured,
        active,
        stopping,
        faulted,
    };

    /** @brief M25 analog fabric 연산 결과입니다. */
    enum class AnalogFabricResult : std::uint8_t
    {
        success = 0U,
        invalid_context,
        invalid_argument,
        unsupported_instance,
        unsupported_route,
        driver_unavailable,
        wrong_state,
        ownership_conflict,
        resource_exhausted,
        driver_error,
        stop_timeout,
        release_failed,
        faulted,
    };

    /** @brief SAADC 입력 선택입니다. 0~7은 AIN0~AIN7, 0x80부터는 내부 입력입니다.
     */
    enum class SaadcInput : std::uint8_t
    {
        ain0 = 0U,
        ain1,
        ain2,
        ain3,
        ain4,
        ain5,
        ain6,
        ain7,
        vdd = 0x80U,
        vdd_div2,
        avdd,
        dvdd,
        vddh_div5,
        vddl,
        decb,
        vss,
        disabled = 0xFFU,
    };

    /** @brief nRF54L15의 8개 SAADC gain. 내부 reference는 0.9 V입니다. */
    enum class SaadcGain : std::uint8_t
    {
        two = 0U, one, two_thirds, one_half, two_fifths,
        one_third, two_sevenths, one_quarter,
    };

    /** @brief 한 logical SAADC channel의 입력·gain입니다.
     * gain=1 기본값을 보존합니다. 0.9 V보다 높은 입력은 적절한 감쇠 gain을
     * 선택해야 하며, gain 선택이 pad 허용 전압을 높이지는 않습니다.
     */
    struct SaadcChannelConfiguration
    {
        SaadcInput positive{SaadcInput::ain0};
        SaadcInput negative{SaadcInput::disabled};
        SaadcGain gain{SaadcGain::one};
    };

    /** @brief SAADC 8채널 scan과 연속 double-buffer 설정입니다. */
    struct SaadcConfiguration
    {
        const SaadcChannelConfiguration *channels{nullptr};
        std::size_t channel_count{0U};
        std::uint8_t resolution_bits{12U};
        std::uint16_t oversample{1U};
        std::uint16_t interval_us{0U};
    };

    /** @brief SAADC 비동기 event 종류입니다. */
    enum class SaadcEventType : std::uint8_t
    {
        ready = 0U,
        buffer_complete,
        buffer_needed,
        calibration_complete,
        finished,
        error,
    };

    /** @brief SAADC 완료 queue에서 읽는 event입니다. */
    struct SaadcEvent
    {
        SaadcEventType type{SaadcEventType::error};
        std::int16_t *buffer{nullptr};
        std::size_t samples{0U};
        int driver_error{0};
    };

    /** @brief SAADC 전 instance scan/continuous DMA handle입니다. */
    class SaadcFabric
    {
    public:
        [[nodiscard]] AnalogFabricState state() const noexcept;
        [[nodiscard]] AnalogFabricResult lastResult() const noexcept;
        [[nodiscard]] int lastDriverError() const noexcept;

        [[nodiscard]] AnalogFabricResult
        configure(const SaadcConfiguration &configuration) noexcept;
        [[nodiscard]] AnalogFabricResult start(std::int16_t *first_buffer,
                                               std::size_t first_samples,
                                               std::int16_t *next_buffer,
                                               std::size_t next_samples) noexcept;
        [[nodiscard]] AnalogFabricResult queueBuffer(std::int16_t *buffer,
                                                     std::size_t samples) noexcept;
        /** @brief interval_us=0의 ready event 이후 SAMPLE 한 번을 요청합니다.
         * start()는 DMA를 준비하며 수동 모드의 변환을 자동 시작하지 않습니다.
         */
        [[nodiscard]] AnalogFabricResult sample() noexcept;
        [[nodiscard]] AnalogFabricResult calibrate() noexcept;
        [[nodiscard]] std::uintptr_t sampleTaskAddress() const noexcept;
        [[nodiscard]] std::uintptr_t readyEventAddress() const noexcept;
        /** @brief stop_timeout이면 DMA lease를 유지하며 stop() 재시도가 가능합니다. */
        [[nodiscard]] AnalogFabricResult
        stop(std::uint32_t timeout_us = 100000U) noexcept;
        [[nodiscard]] bool takeEvent(SaadcEvent &event) noexcept;

    private:
        friend class AnalogFabric;
        constexpr SaadcFabric() noexcept = default;
    };

    /** @brief PWM decoder load 방식입니다. */
    enum class PwmSequenceLoad : std::uint8_t
    {
        common = 0U,
        grouped,
        individual,
        wave_form,
    };

    /** @brief PWM sequence 재생 설정입니다. */
    struct PwmSequenceConfiguration
    {
        pin_size_t output_pins[4]{0xFFU, 0xFFU, 0xFFU, 0xFFU};
        bool inverted[4]{false, false, false, false};
        std::uint16_t top_value{1000U};
        PwmSequenceLoad load{PwmSequenceLoad::individual};
        bool triggered_step{false};
    };

    /** @brief application RAM에 있는 한 PWM EasyDMA sequence입니다. */
    struct PwmSequenceBuffer
    {
        const std::uint16_t *values{nullptr};
        std::size_t value_count{0U};
        std::uint32_t repeats{0U};
        std::uint32_t end_delay{0U};
    };

    /** @brief PWM sequence event 종류입니다. */
    enum class PwmSequenceEventType : std::uint8_t
    {
        sequence0_complete = 0U,
        sequence1_complete,
        playback_complete,
        stopped,
        error,
    };

    /** @brief PWM sequence 완료 queue에서 읽는 event입니다. */
    struct PwmSequenceEvent
    {
        PwmSequenceEventType type{PwmSequenceEventType::error};
        std::uint8_t instance{0U};
        int driver_error{0};
    };

    /** @brief PWM20/21/22 한 block의 4채널 sequence handle입니다. */
    class PwmSequenceFabric
    {
    public:
        [[nodiscard]] std::uint8_t instance() const noexcept;
        [[nodiscard]] AnalogFabricState state() const noexcept;
        [[nodiscard]] AnalogFabricResult lastResult() const noexcept;
        [[nodiscard]] int lastDriverError() const noexcept;

        [[nodiscard]] AnalogFabricResult
        configure(const PwmSequenceConfiguration &configuration) noexcept;
        [[nodiscard]] AnalogFabricResult
        play(const PwmSequenceBuffer &sequence0,
             const PwmSequenceBuffer *sequence1 = nullptr,
             std::uint16_t playback_count = 1U, bool loop = false,
             bool start_via_task = false) noexcept;
        [[nodiscard]] std::uintptr_t startTaskAddress() const noexcept;
        [[nodiscard]] AnalogFabricResult step() noexcept;
        [[nodiscard]] AnalogFabricResult
        stop(std::uint32_t timeout_us = 100000U) noexcept;
        [[nodiscard]] bool takeEvent(PwmSequenceEvent &event) noexcept;

    private:
        friend class AnalogFabric;
        constexpr explicit PwmSequenceFabric(std::uint8_t instance) noexcept
            : instance_(instance) {}

        std::uint8_t instance_;
    };

    /** @brief M25 analog/timing candidate handle factory입니다. */
    class AnalogFabric
    {
    public:
        [[nodiscard]] SaadcFabric &saadc() noexcept;
        [[nodiscard]] PwmSequenceFabric *pwm(std::uint8_t instance) noexcept;

    private:
        friend AnalogFabric &analogFabric() noexcept;
        constexpr AnalogFabric() noexcept = default;
    };

    /** @brief process-wide M25 analog fabric factory를 반환합니다. */
    [[nodiscard]] AnalogFabric &analogFabric() noexcept;

} // namespace nucode::arduino

#endif
