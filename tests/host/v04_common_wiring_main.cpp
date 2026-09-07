/** @file @brief 실제 HIL 핀 대응·LOW 제한·허가 만료의 constexpr 경계 회귀입니다. */
#include "common_wiring.h"
#include "fixture_gate.h"

namespace
{
    /** @brief 입력 준비를 제외한 임의 핀·중복 LOW·시간 overflow를 거부해야 합니다. */
    constexpr bool pulseBounds()
    {
        v04::WiringPulse pulse;
        if (pulse.start(17U, 0U) || pulse.start(0U, UINT64_MAX) || !pulse.start(16U, 123U) ||
            pulse.start(0U, 124U) || pulse.expired(622U) || !pulse.expired(623U) ||
            pulse.net() != 16U)
        {
            return false;
        }
        pulse.clear();
        return pulse.net() == UINT32_MAX && !pulse.expired(UINT64_MAX) && pulse.start(0U, 0U);
    }

    /** @brief 커넥터 회로 대조에서 확정한 물리 GPIO 상수로 독립 비교합니다. */
    constexpr bool routes()
    {
        constexpr unsigned a[]{46, 42, 36, 37, 38, 39, 0, 1, 2, 3, 64, 65, 66, 67, 68, 69, 70};
        constexpr unsigned b[]{46, 42, 36, 37, 39, 38, 0, 1, 2, 3, 64, 65, 66, 67, 68, 69, 70};
        for (unsigned index = 0U; index < 17U; ++index)
        {
            if (v04::wiringPin(1U, index) != a[index] || v04::wiringPin(2U, index) != b[index])
            {
                return false;
            }
        }
        return v04::wiringPin(0U, 0U) == UINT32_MAX && v04::wiringPin(1U, 17U) == UINT32_MAX &&
               v04::fixtureFamily(501U) == v04::FixtureFamily::wiring &&
               v04::fixtureBank(501U, 2U) == v04::Bank::mixed &&
               v04::fixtureBank(501U, 0U) == v04::Bank::invalid;
    }
    static_assert(pulseBounds());
    static_assert(routes());
} // namespace
