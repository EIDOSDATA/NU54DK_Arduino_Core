#include "tests/zephyr/v04_pair_hil/src/fixture_gate.h"
#include <cstdint>
#include <iostream>

namespace
{
    bool check(bool value, const char *message)
    {
        if (!value)
        {
            std::cerr << message << '\n';
        }
        return value;
    }
} // namespace

int main()
{
    using v04::Bank;
    using v04::FixtureGate;
    bool ok = true;
    ok &= check(v04::fixtureFamily(101) == v04::FixtureFamily::uarte &&
                    v04::fixtureFamily(203) == v04::FixtureFamily::spi &&
                    v04::fixtureFamily(301) == v04::FixtureFamily::twi &&
                    v04::fixtureFamily(401) == v04::FixtureFamily::analog &&
                    v04::fixtureFamily(404) == v04::FixtureFamily::analog &&
                    v04::fixtureFamily(408) == v04::FixtureFamily::analog &&
                    v04::fixtureFamily(405) == v04::FixtureFamily::analog &&
                    v04::fixtureFamily(406) == v04::FixtureFamily::invalid &&
                    v04::fixtureFamily(407) == v04::FixtureFamily::invalid &&
                    v04::fixtureFamily(420) == v04::FixtureFamily::qdec &&
                    v04::fixtureFamily(430) == v04::FixtureFamily::i2s &&
                    v04::fixtureFamily(440) == v04::FixtureFamily::pdm &&
                    v04::fixtureFamily(999) == v04::FixtureFamily::invalid,
                "fixture 계열 판정이 잘못되었습니다.");
    ok &= check(v04::fixtureBank(101, 1) == Bank::p2 && v04::fixtureBank(102, 1) == Bank::p0 &&
                    v04::fixtureBank(103, 2) == Bank::p1,
                "UART 역할별 고정 bank가 잘못되었습니다.");
    ok &= check(v04::fixtureBank(201, 1) == Bank::p2 && v04::fixtureBank(201, 2) == Bank::p1,
                "201의 역할별 고정 bank가 잘못되었습니다.");
    ok &= check(v04::fixtureBank(202, 1) == Bank::p0 && v04::fixtureBank(202, 2) == Bank::p1,
                "202의 역할별 고정 bank가 잘못되었습니다.");
    ok &= check(v04::fixtureBank(203, 1) == Bank::p1 && v04::fixtureBank(301, 2) == Bank::p0,
                "203/301의 고정 bank가 잘못되었습니다.");
    ok &= check(v04::fixtureBank(999, 1) == Bank::invalid &&
                    v04::fixtureBank(201, 3) == Bank::invalid,
                "알 수 없는 fixture/role을 허용했습니다.");
    ok &= check(v04::fixtureInstance(Bank::p2, 0) && v04::fixtureInstance(Bank::p2, 20) &&
                    !v04::fixtureInstance(Bank::p2, 21) && v04::fixtureInstance(Bank::p0, 30) &&
                    v04::fixtureInstance(Bank::p1, 22),
                "bank별 인스턴스 allowlist가 잘못되었습니다.");
    ok &= check(!v04::shouldQueueSerialPeripheralBuffers(true, false, false, false) &&
                    !v04::shouldQueueSerialPeripheralBuffers(false, true, false, false) &&
                    !v04::shouldQueueSerialPeripheralBuffers(false, false, true, false) &&
                    !v04::shouldQueueSerialPeripheralBuffers(false, false, false, true) &&
                    v04::shouldQueueSerialPeripheralBuffers(false, false, false, false),
                "UART 또는 지연·controller 경로를 peripheral buffer 분기에 허용했습니다.");

    FixtureGate gate;
    ok &= check(!gate.arm(201, 0, FixtureGate::consent, 1, 1, 100),
                "다른 결선표 개정을 허용했습니다.");
    ok &= check(!gate.arm(201, FixtureGate::revision, 0, 1, 1, 100),
                "사용자 확인 없는 arm을 허용했습니다.");
    ok &= check(gate.arm(201, FixtureGate::revision, FixtureGate::consent, 1, 1, 100),
                "정상 fixture arm을 거부했습니다.");
    ok &= check(gate.live(100) && gate.live(10099) && !gate.live(10100),
                "lease 만료 경계가 잘못되었습니다.");
    ok &= check(!gate.renew(10100), "만료된 lease를 되살렸습니다.");
    gate.close(true);
    ok &= check(!gate.claimed(), "증명된 STOP 뒤 gate를 해제하지 않았습니다.");
    ok &= check(gate.arm(301, FixtureGate::revision, FixtureGate::consent, 2, 2, 200),
                "해제 후 정상 arm을 거부했습니다.");
    ok &= check(gate.renew(201) && gate.live(10200), "활성 lease 갱신에 실패했습니다.");
    gate.close(false);
    ok &= check(gate.claimed() && !gate.live(202) &&
                    !gate.arm(301, FixtureGate::revision, FixtureGate::consent, 2, 2, 202),
                "STOP 미증명 fault latch 뒤 재사용을 허용했습니다.");
    return ok ? 0 : 1;
}
