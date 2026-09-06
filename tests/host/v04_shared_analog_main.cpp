/**
 * @file v04_shared_analog_main.cpp
 * @brief 공유 입력 신호원이 강한 HIGH를 출력하지 않고 해제되는지 검증합니다.
 * SPDX-License-Identifier: MIT
 */
#include "tests/zephyr/v04_pair_hil/src/shared_analog_source.h"
#include "tests/zephyr/v04_pair_hil/src/fixture_gate.h"
#include <cassert>
#include <vector>

namespace
{
    /** @brief 핀 상태 전이마다 강한 HIGH 및 미설정 출력 활성화를 검출합니다. */
    struct Pin
    {
        inline static bool output = false, od = false, high = false;
        inline static std::vector<int> actions;

        static void input()
        {
            output = od = false;
            actions.push_back(0);
        }

        static void write(bool value)
        {
            assert(!output || od || !value);
            high = value;
            actions.push_back(value ? 1 : 2);
        }

        static void openDrainPullup()
        {
            assert(!output && high);
            output = od = true;
            actions.push_back(3);
        }
    };
} // namespace

int main()
{
    using v04::FixtureGate;
    for (unsigned role : {1U, 2U})
    {
        FixtureGate gate;
        assert(!gate.arm(405, 1, FixtureGate::consent, 1, role, 0));
        assert(!gate.arm(406, 1, FixtureGate::consent, 2, role, 0));
        assert(!gate.arm(407, 1, FixtureGate::consent, 2, role, 0));
        assert(gate.arm(405, 1, FixtureGate::consent, 2, role, 0));
        assert(!gate.live(10000));
    }
    for (unsigned phase : {0U, 1U, 2U})
    {
        std::uint32_t args[8]{0, 32, phase, 0, 0, 1, 0, 0};
        v04::SharedAnalogSource<Pin> source;
        Pin::actions.clear();
        assert(!source.start());
        assert(!source.prepare(405, 1, args));
        assert(!source.prepare(404, 2, args));
        for (unsigned index : {0U, 1U, 2U, 3U, 4U, 5U, 6U, 7U})
        {
            auto saved = args[index];
            args[index] = UINT32_MAX;
            assert(!source.prepare(405, 2, args));
            args[index] = saved;
        }
        assert(Pin::actions.empty());
        assert(source.prepare(405, 2, args));
        assert(Pin::actions == std::vector<int>({0, 1, 3}));
        assert(!source.prepare(405, 2, args));
        assert(source.start() && Pin::high == (phase == 1U));
        assert(!source.start());
        source.release();
        assert(!source.owned() && !Pin::output && Pin::high);
        auto actions = Pin::actions;
        source.release();
        assert(Pin::actions == actions);
        assert(source.prepare(405, 2, args));
        source.release();
        assert(!Pin::output);
    }
}
