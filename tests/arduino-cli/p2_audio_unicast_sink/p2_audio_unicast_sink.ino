/**
 * @file p2_audio_unicast_sink.ino
 * @brief LC3/CIS unicast 수신·복호화 경로의 P2 메모리를 계측합니다.
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <P2MemoryTelemetry.h>

using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::UnicastServer;

namespace
{
    UnicastServer audioSink;
    Lc3Codec codec;
    bool restartAdvertising = false;
    bool stopRequested = false;
    bool finished = false;
    std::uint32_t decodedFrames = 0U;
    std::uint32_t droppedAtStop = 0U;

    /** @brief 연결 해제 뒤 광고를 재개하거나 STOP 완료를 허용합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = !stopRequested;
        }
    }
}

/** @brief PACS/ASCS sink·LC3 codec과 계측기를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("P2_READY role=audio-sink");
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-AUDIO-SNK"))
    {
        Serial.println("P2_AUDIO_FAIL bt-begin");
        return;
    }
    if (audioSink.begin() != Error::none || codec.begin() != Error::none)
    {
        Serial.println("P2_AUDIO_FAIL codec-or-server-begin");
        return;
    }
    constexpr std::uint8_t announcement[] = {1U, 0x03U, 0x00U, 0x00U, 0x00U, 0U};
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x184EU)) ||
        !BLEAdvertising.setServiceData(BLEUuid(0x184EU), announcement,
                                       sizeof(announcement)) ||
        !BLEAdvertising.start())
    {
        Serial.println("P2_AUDIO_FAIL advertising");
        return;
    }
    nucode::test::reportMemory("ready");
    Serial.println("P2_AUDIO_ADVERTISING role=sink");
}

/** @brief LC3 frame을 복호화하고 명시적 STOP 뒤 high-water를 출력합니다. */
void loop()
{
    if (finished)
    {
        delay(10);
        return;
    }
    BLEDevice.poll();
    if (Serial.available() > 0 && Serial.read() == 's')
    {
        stopRequested = true;
    }
    if (restartAdvertising && !stopRequested && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("P2_AUDIO_FAIL advertising-restart");
        }
    }

    std::uint8_t frame[40] = {};
    std::int16_t pcm[160] = {};
    while (audioSink.readFrame(frame))
    {
        if (codec.decode(frame, sizeof(frame), pcm, 160U) != Error::none)
        {
            Serial.println("P2_AUDIO_FAIL decode");
            continue;
        }
        ++decodedFrames;
        if ((decodedFrames % 100U) == 0U)
        {
            std::uint32_t energy = 0U;
            for (const std::int16_t sample : pcm)
            {
                const std::int32_t value = sample;
                energy += static_cast<std::uint32_t>((value < 0) ? -value : value);
            }
            Serial.print("P2_AUDIO_DECODED frames=");
            Serial.print(decodedFrames);
            Serial.print(" dropped=");
            Serial.print(audioSink.droppedFrames());
            Serial.print(" energy=");
            Serial.println(energy);
        }
    }
    if (stopRequested && !BLEConnection.connected())
    {
        droppedAtStop = audioSink.droppedFrames();
        static_cast<void>(BLEAdvertising.stop());
        const Error result = audioSink.end();
        if ((result != Error::none) && (result != Error::not_started))
        {
            Serial.println("P2_AUDIO_FAIL server-end");
        }
        codec.end();
        BLEDevice.end();
        nucode::test::reportMemory("stopped");
        Serial.print("P2_STOP role=audio-sink decoded=");
        Serial.print(decodedFrames);
        Serial.print(" dropped=");
        Serial.println(droppedAtStop);
        finished = true;
    }
    delay(1);
}
