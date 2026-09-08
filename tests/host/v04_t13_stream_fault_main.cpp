/** @file @brief 단일 공급 생략과 최초 오류 원본 보존을 실제 target helper로 검사합니다. */
#include "stream_fault.h"
#include <cassert>

int main()
{
    for (unsigned mode = 1U; mode <= 2U; ++mode)
    {
        t13::StreamFault fault{};
        const unsigned stream = mode == 1U ? 2U : 3U;
        assert(!fault.skip(stream, 4U, 5U, 100U));
        assert(!fault.arm(0U, 20U, 1U, 1000000U));
        assert(fault.arm(mode, 20U, 1U, 1000000U));
        assert(!fault.arm(mode, 20U, 1U, 1000000U));
        assert(!fault.skip(5U - stream, 4U, 5U, 100U));
        for (unsigned complete = 0U; complete < 4U; ++complete)
        {
            assert(!fault.skip(stream, complete, complete + 1U, 100U));
        }
        fault.observe(stream, 4U, 9, 50U, 3U, 4U, false, 4U, 12U, 13U);
        assert(fault.words[7] == UINT32_MAX);
        assert(fault.skip(stream, 4U, 5U, 100U));
        for (unsigned request = 0U; request < 100U; ++request)
        {
            assert(!fault.skip(stream, 5U + request, 6U + request, 200U + request));
        }
        fault.event(5U - stream);
        assert(fault.words[14] == 0U);
        fault.event(stream);
        fault.observe(stream, 3U, -139, 300U, 5U, 5U, false, 2U, 12U, 13U);
        fault.observe(stream, 4U, 0, 400U, 6U, 6U, true, 4U, 0U, 0U);
        assert(fault.words[3] == 1U && fault.words[6] == 100U);
        assert(fault.words[7] == 3U && fault.words[8] == static_cast<std::uint32_t>(-139));
        assert(fault.words[9] == 300U && fault.words[12] == 0U && fault.words[13] == 2U);
        assert(fault.words[14] == 1U && fault.words[16] == 12U && fault.words[17] == 13U);
    }
    return 0;
}
