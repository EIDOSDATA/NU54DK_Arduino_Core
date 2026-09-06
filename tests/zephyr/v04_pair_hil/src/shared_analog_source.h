/**
 * @file shared_analog_source.h
 * @brief Fixture 405의 고정 오픈드레인 신호원 수명과 입력 계약입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>

namespace v04
{
    /** @brief PWM 인자와 구별되는 405 전용 LOW/해제/LOW vector만 허용합니다. */
    constexpr bool sharedAnalogArguments(const std::uint32_t *args)
    {
        return args[0] == 0U && (args[1] == 32U || args[1] == 256U) && args[2] <= 2U &&
               args[3] == 0U && args[4] == 0U && (args[5] == 1U || args[5] == 2U) &&
               args[6] == 0U && args[7] == 0U;
    }

    /**
     * @brief LOW만 구동하고 HIGH는 풀업에 맡기며 해제 시 입력으로 돌아갑니다.
     * @note Backend는 고정 B P1.14만 사용합니다. 기존 출력 설정은 복원하지 않습니다.
     */
    template <typename Backend> class SharedAnalogSource
    {
      public:
        bool prepare(std::uint32_t fixture, std::uint32_t role, const std::uint32_t *args)
        {
            if (owned_ || fixture != 405U || role != 2U || !sharedAnalogArguments(args))
            {
                return false;
            }
            Backend::input();
            Backend::write(true);
            Backend::openDrainPullup();
            phase_ = args[2];
            owned_ = true;
            return true;
        }

        bool start()
        {
            if (!owned_ || started_)
            {
                return false;
            }
            Backend::write(phase_ == 1U);
            started_ = true;
            return true;
        }

        void release()
        {
            if (owned_)
            {
                Backend::input();
                Backend::write(true);
                owned_ = started_ = false;
                phase_ = UINT32_MAX;
            }
        }

        bool owned() const
        {
            return owned_;
        }

        std::uint32_t phase() const
        {
            return phase_;
        }

      private:
        bool owned_ = false, started_ = false;
        std::uint32_t phase_ = UINT32_MAX;
    };
} // namespace v04
