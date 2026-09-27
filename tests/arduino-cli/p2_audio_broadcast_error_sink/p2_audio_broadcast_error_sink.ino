/**
 * @file p2_audio_broadcast_error_sink.ino
 * @brief 잘못된 Broadcast Code 오류와 올바른 code 복구의 P2 메모리를 계측합니다.
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
    constexpr BroadcastCode correctCode = {
        0x4e, 0x55, 0x35, 0x34, 0x2d, 0x41, 0x55, 0x44,
        0x49, 0x4f, 0x2d, 0x43, 0x4f, 0x44, 0x45, 0x31,
    };
    constexpr BroadcastCode wrongCode = {
        0x4e, 0x55, 0x35, 0x34, 0x2d, 0x41, 0x55, 0x44,
        0x49, 0x4f, 0x2d, 0x43, 0x4f, 0x44, 0x45, 0x30,
    };
    BroadcastSink audioSink;
    Lc3Codec codec;
    std::uint32_t decodedFrames = 0U;
    bool recoveryStarted = false;
    bool recoveryReported = false;
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

/** @brief 잘못된 Broadcast Code로 첫 BIS 동기화를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("P2_READY role=audio-broadcast-error-sink");
    if (!BLEDevice.begin("NU54-AUDIO-ERROR-SNK"))
    {
        Serial.println("P2_AUDIO_FAIL bt-begin");
        return;
    }
    if (codec.begin() != Error::none)
    {
        Serial.println("P2_AUDIO_FAIL codec-begin");
        return;
    }
    if (audioSink.begin(broadcastName, wrongCode) != Error::none)
    {
        Serial.print("P2_AUDIO_FAIL wrong-code-begin native=");
        Serial.println(audioSink.nativeCode());
        return;
    }
    nucode::test::reportMemory("ready");
}

/** @brief MIC 오류 뒤 자원을 반환하고 같은 역할·용량에서 올바른 code로 복구합니다. */
void loop()
{
    if (finished)
    {
        delay(10);
        return;
    }
    BLEDevice.poll();
    audioSink.poll();

    if (!recoveryStarted && (audioSink.stage() == BroadcastStage::failed))
    {
        const int native = audioSink.nativeCode();
        Serial.print("P2_AUDIO_ENCRYPTION_REJECTED native=");
        Serial.print(native);
        Serial.print(" decoded=");
        Serial.print(decodedFrames);
        Serial.print(" dropped=");
        Serial.println(audioSink.droppedFrames());
        nucode::test::reportMemory("wrong-code-rejected");
        const Error stopped = audioSink.end();
        if ((native != -61) ||
            ((stopped != Error::none) && (stopped != Error::not_started)))
        {
            Serial.println("P2_AUDIO_FAIL wrong-code-contract");
            return;
        }
        if (audioSink.begin(broadcastName, correctCode) != Error::none)
        {
            Serial.print("P2_AUDIO_FAIL recovery-begin native=");
            Serial.println(audioSink.nativeCode());
            return;
        }
        recoveryStarted = true;
        Serial.println("P2_AUDIO_ENCRYPTION_RECOVERY_STARTED");
    }

    std::uint8_t frame[40] = {};
    while (audioSink.readFrame(frame))
    {
        std::int16_t pcm[160] = {};
        if (codec.decode(frame, sizeof(frame), pcm, 160U) != Error::none)
        {
            Serial.println("P2_AUDIO_FAIL recovery-decode");
            continue;
        }
        ++decodedFrames;
        if ((decodedFrames >= 100U) && !recoveryReported)
        {
            recoveryReported = true;
            Serial.print("P2_AUDIO_ENCRYPTION_RECOVERED frames=");
            Serial.print(decodedFrames);
            Serial.print(" dropped=");
            Serial.print(audioSink.droppedFrames());
            Serial.print(" energy=");
            Serial.println(frameEnergy(pcm));
            nucode::test::reportMemory("encrypted-recovered");
        }
    }

    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if (command == 'm')
        {
            nucode::test::reportMemory("cycle");
        }
        else if (command == 's')
        {
            const std::uint32_t dropped = audioSink.droppedFrames();
            const Error stopped = audioSink.end();
            if ((stopped != Error::none) && (stopped != Error::not_started))
            {
                Serial.println("P2_AUDIO_FAIL sink-end");
            }
            codec.end();
            BLEDevice.end();
            nucode::test::reportMemory("stopped");
            Serial.print("P2_STOP role=audio-broadcast-error-sink decoded=");
            Serial.print(decodedFrames);
            Serial.print(" dropped=");
            Serial.println(dropped);
            finished = true;
        }
    }
    delay(1);
}
