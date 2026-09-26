/**
 * @file p2_df_beacon.ino
 * @brief 기본 안테나 AoA CTE beacon 20회 수명을 계측합니다.
 */

#include <NUCODE_BLE_DirectionFinding.h>
#include <P2MemoryTelemetry.h>

using nucode::ble::df::Beacon;
using nucode::ble::df::BeaconConfig;
using nucode::ble::df::Error;

namespace
{
    Beacon beacon;
    std::uint8_t cycles = 0U;
    std::uint32_t startedMs = 0U;
    std::uint32_t restartMs = 0U;
    bool running = false;
    bool finished = false;

    /** @brief 실제 controller 오류를 포함해 실패를 기록합니다. */
    void fail(const char *step)
    {
        Serial.print("P2_DF_FAIL step=");
        Serial.print(step);
        Serial.print(" native=");
        Serial.println(beacon.nativeCode());
        beacon.end();
        finished = true;
    }
}

/** @brief 잘못된 CTE 길이를 거부하고 올바른 beacon을 준비합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("P2_READY role=df-beacon");
    BeaconConfig invalid = {};
    invalid.cte_length_8us = 0U;
    if (beacon.begin(invalid) != Error::invalid_argument)
    {
        fail("invalid-not-rejected");
        return;
    }
    Serial.println("P2_DF_REJECTED cte-length");
    BeaconConfig config = {};
    config.cte_length_8us = 20U;
    config.cte_count = 5U;
    if (beacon.begin(config) != Error::none)
    {
        fail("begin");
        return;
    }
    nucode::test::reportMemory("ready");
    restartMs = millis() + 100U;
}

/** @brief 2초 송신·중단을 20회 반복하고 광고 set을 반환합니다. */
void loop()
{
    if (finished)
    {
        delay(10);
        return;
    }
    if (Serial.available() > 0 && Serial.read() == 's')
    {
        beacon.end();
        nucode::test::reportMemory("stopped");
        Serial.print("P2_STOP role=df-beacon canceled=1 cycles=");
        Serial.println(cycles);
        finished = true;
        return;
    }
    if (!running && static_cast<std::int32_t>(millis() - restartMs) >= 0)
    {
        if (beacon.start() != Error::none)
        {
            fail("start");
            return;
        }
        running = true;
        startedMs = millis();
    }
    /** @brief connectionless 동기화 진단 image에서만 광고를 연속 유지합니다. */
#if defined(NUCODE_P2_DF_CONTINUOUS)
    if (running)
    {
        delay(1);
        return;
    }
#endif
    if (running && millis() - startedMs >= 2000U)
    {
        if (beacon.stop() != Error::none)
        {
            fail("stop");
            return;
        }
        running = false;
        ++cycles;
        Serial.print("P2_DF_CYCLE count=");
        Serial.println(cycles);
        if (cycles == 20U)
        {
            beacon.end();
            nucode::test::reportMemory("stopped");
            Serial.println("P2_STOP role=df-beacon cycles=20");
            finished = true;
        }
        else
        {
            restartMs = millis() + 100U;
        }
    }
    delay(1);
}
