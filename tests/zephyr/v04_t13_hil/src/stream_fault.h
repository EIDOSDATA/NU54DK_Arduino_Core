/** @file @brief 정상 버퍼 네 개 뒤 한 번의 공급 생략과 최초 오류 원본을 보존합니다. */
#pragma once
#include <cstdint>

namespace t13
{
    struct StreamFault
    {
        std::uint32_t words[20]{};

        bool arm(unsigned mode, unsigned instance, unsigned role, std::uint32_t frequency)
        {
            if (words[0] != 0U || (mode != 1U && mode != 2U))
            {
                return false;
            }
            words[0] = mode;
            words[1] = mode == 1U ? 2U : 3U;
            words[2] = instance;
            words[7] = UINT32_MAX;
            words[18] = role;
            words[19] = frequency;
            return true;
        }

        bool skip(unsigned stream, std::uint32_t completed, std::uint32_t queued,
                  std::uint32_t cycle)
        {
            if (words[0] == 0U || words[1] != stream || words[3] != 0U || completed < 4U)
            {
                return false;
            }
            words[3] = 1U;
            words[4] = completed;
            words[5] = queued;
            words[6] = cycle;
            return true;
        }

        /** @brief 공급 생략 뒤 첫 비정상 event만 저장하며 후속 event로 덮어쓰지 않습니다. */
        void observe(unsigned stream, unsigned event, int driver_error, std::uint32_t cycle,
                     std::uint32_t completed, std::uint32_t queued, bool guards, unsigned state,
                     std::uint32_t prior_error, std::uint32_t prior_detail)
        {
            if (words[3] == 0U || words[1] != stream || words[7] != UINT32_MAX)
            {
                return;
            }
            words[7] = event;
            words[8] = static_cast<std::uint32_t>(driver_error);
            words[9] = cycle;
            words[10] = completed;
            words[11] = queued;
            words[12] = guards ? 1U : 0U;
            words[13] = state;
            words[16] = prior_error;
            words[17] = prior_detail;
        }

        void event(unsigned stream)
        {
            if (words[3] != 0U && words[1] == stream)
            {
                ++words[14];
            }
        }
    };

    extern StreamFault stream_fault;
} // namespace t13
