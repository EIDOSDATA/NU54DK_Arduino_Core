/** @file @brief 실제 target 모델의 DMA 양끝 가드와 전역 byte 위치를 Host에서 대조합니다. */
#include "model.h"
#include <cstdio>

int main()
{
    t13::Buffer buffer{};
    constexpr unsigned lengths[]{4U, 32U, 256U, 1024U};
    for (const auto length : lengths)
    {
        if (!buffer.initialize(length) || !buffer.guards(length))
        {
            return 1;
        }
        buffer.data()[length - 1U] ^= 1U;
        if (!buffer.guards(length))
        {
            return 2;
        }
        buffer.data()[length] ^= 1U;
        if (buffer.guards(length))
        {
            return 3;
        }
        buffer.initialize(length);
        buffer.storage[3] ^= 1U;
        if (buffer.guards(length))
        {
            return 4;
        }
    }
    constexpr unsigned invalid[]{0U, 3U, 1028U, UINT32_MAX};
    for (const auto length : invalid)
    {
        if (buffer.initialize(length) || buffer.guards(length))
        {
            return 5;
        }
    }
    constexpr std::uint32_t positions[]{0U, 1U, 1023U, 1024U, 1000000U, UINT32_MAX};
    for (unsigned lane = 0U; lane < 5U; ++lane)
    {
        for (unsigned role = 1U; role <= 2U; ++role)
        {
            const auto seed = t13::laneSeed(0xA7130924U, lane, role);
            for (const auto position : positions)
            {
                std::printf("%u\n", static_cast<unsigned>(t13::pattern(seed, position)));
            }
        }
    }
    return 0;
}
