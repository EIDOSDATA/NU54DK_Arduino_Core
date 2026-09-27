/**
 * @file p2_audio_duplex_client.ino
 * @brief 공개 양방향 LE Audio 예제를 그대로 실행하며 메모리 수명을 계측합니다.
 */

#include <P2MemoryTelemetry.h>

#define setup publicDuplexSetup
#define loop publicDuplexLoop
#include "PublicDuplex.h"
#undef loop
#undef setup

namespace
{
    bool p2Stopped = false;
    std::uint32_t p2LastReport = 0U;
}

/** @brief 공개 예제를 시작한 뒤 계측 시작점을 표시합니다. */
void setup()
{
    publicDuplexSetup();
    Serial.println("P2_READY role=audio-duplex-client");
    nucode::test::reportMemory("ready");
    p2LastReport = millis();
}

/** @brief 원본 loop를 보존하고 종료 명령 때 자원과 최고 사용량을 기록합니다. */
void loop()
{
    if (p2Stopped)
    {
        return;
    }
    if ((Serial.available() > 0) && (Serial.read() == 'x'))
    {
        p2Stopped = true;
        (void)audioClient.end();
        codec.end();
        BLEDevice.end();
        nucode::test::reportMemory("stopped");
        Serial.print("P2_STOP role=audio-duplex-client decoded=");
        Serial.println(decodedFrames);
        return;
    }
    publicDuplexLoop();
    if ((millis() - p2LastReport) >= 10000U)
    {
        nucode::test::reportMemory("traffic");
        p2LastReport = millis();
    }
}
