/**
 * @file p2_audio_broadcast_sink.ino
 * @brief 암호화 BIS 방송의 LC3 복호화와 P2 메모리를 계측합니다.
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <P2MemoryTelemetry.h>

using nucode::ble::audio::BroadcastCode;
using nucode::ble::audio::BroadcastSink;
using nucode::ble::audio::BroadcastStage;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;

namespace
{
    constexpr const char *broadcastName = "NU54-AUDIO-BROADCAST";
    constexpr BroadcastCode broadcastCode = {
        0x4e, 0x55, 0x35, 0x34, 0x2d, 0x41, 0x55, 0x44,
        0x49, 0x4f, 0x2d, 0x43, 0x4f, 0x44, 0x45, 0x31,
    };
    BroadcastSink audioSink;
    Lc3Codec codec;
    std::uint32_t decodedFrames = 0U;
    bool announcedStreaming = false;
    bool reportedFailure = false;
    bool finished = false;

    /** @brief PCM frame이 무음이 아닌지 검증할 절대값 합을 계산합니다. */
    std::uint32_t frameEnergy(const std::int16_t (&pcm)[160])
    {
        std::uint32_t energy = 0U;
        for (const std::int16_t sample : pcm)
        {
            const std::int32_t value = sample;
            energy += static_cast<std::uint32_t>((value < 0) ? -value : value);
        }
        return energy;
    }
}

/** @brief Bluetooth·codec·암호화 broadcast sink를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("P2_READY role=audio-broadcast-sink");
    if (!BLEDevice.begin("NU54-AUDIO-BROADCAST-SNK"))
    {
        Serial.println("P2_AUDIO_FAIL bt-begin");
        return;
    }
    if (codec.begin() != Error::none)
    {
        Serial.println("P2_AUDIO_FAIL codec-begin");
        return;
    }
    if (audioSink.begin(broadcastName, broadcastCode) != Error::none)
    {
        Serial.print("P2_AUDIO_FAIL sink-begin native=");
        Serial.println(audioSink.nativeCode());
        return;
    }
    nucode::test::reportMemory("ready");
}

/** @brief LC3 frame을 복호화하고 STOP 뒤 high-water를 기록합니다. */
void loop()
{
    if (finished)
    {
        delay(10);
        return;
    }
    BLEDevice.poll();
    audioSink.poll();
    if (Serial.available() > 0 && Serial.read() == 's')
    {
        const std::uint32_t dropped = audioSink.droppedFrames();
        const Error result = audioSink.end();
        if ((result != Error::none) && (result != Error::not_started))
        {
            Serial.println("P2_AUDIO_FAIL sink-end");
        }
        codec.end();
        BLEDevice.end();
        nucode::test::reportMemory("stopped");
        Serial.print("P2_STOP role=audio-broadcast-sink decoded=");
        Serial.print(decodedFrames);
        Serial.print(" dropped=");
        Serial.println(dropped);
        finished = true;
        return;
    }
    if ((audioSink.stage() == BroadcastStage::failed) && !reportedFailure)
    {
        reportedFailure = true;
        Serial.print("P2_AUDIO_FAIL sink-stage native=");
        Serial.print(audioSink.nativeCode());
        Serial.print(" step=");
        Serial.println(static_cast<unsigned int>(audioSink.lastStep()));
    }
    if (audioSink.streaming() && !announcedStreaming)
    {
        announcedStreaming = true;
        Serial.println("P2_AUDIO_STREAM role=broadcast-sink");
    }
    std::uint8_t frame[40] = {};
    while (audioSink.readFrame(frame))
    {
        std::int16_t pcm[160] = {};
        if (codec.decode(frame, sizeof(frame), pcm, 160U) != Error::none)
        {
            Serial.println("P2_AUDIO_FAIL decode");
            continue;
        }
        ++decodedFrames;
        if ((decodedFrames % 100U) == 0U)
        {
            Serial.print("P2_AUDIO_DECODED frames=");
            Serial.print(decodedFrames);
            Serial.print(" dropped=");
            Serial.print(audioSink.droppedFrames());
            Serial.print(" energy=");
            Serial.println(frameEnergy(pcm));
        }
    }
    delay(1);
}
