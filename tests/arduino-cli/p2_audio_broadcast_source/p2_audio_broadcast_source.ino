/**
 * @file p2_audio_broadcast_source.ino
 * @brief 합성 PCM→LC3→BIS 방송과 P2 메모리를 계측합니다.
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <P2MemoryTelemetry.h>

using nucode::ble::audio::BroadcastCode;
using nucode::ble::audio::BroadcastSource;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;

namespace
{
    constexpr const char *broadcastName = "NU54-AUDIO-BROADCAST";
    constexpr BroadcastCode broadcastCode = {
        0x4e, 0x55, 0x35, 0x34, 0x2d, 0x41, 0x55, 0x44,
        0x49, 0x4f, 0x2d, 0x43, 0x4f, 0x44, 0x45, 0x31,
    };
    BroadcastSource audioSource;
    Lc3Codec codec;
    std::uint32_t lastFrameAt = 0U;
    std::uint16_t wavePosition = 0U;
    bool announcedStreaming = false;
    bool finished = false;

    /** @brief 공개 예제와 같은 16 kHz bounded 삼각파를 만듭니다. */
    void fillPcm(std::int16_t (&pcm)[160])
    {
        for (std::size_t index = 0U; index < 160U; index++)
        {
            const std::uint16_t phase = static_cast<std::uint16_t>((wavePosition + index) % 160U);
            const std::int32_t rising = (phase < 80U) ? phase : (160U - phase);
            pcm[index] = static_cast<std::int16_t>(rising * 300 - 12000);
        }
        wavePosition = static_cast<std::uint16_t>((wavePosition + 17U) % 160U);
    }
}

/** @brief Bluetooth와 codec을 준비하고 암호화 방송을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("P2_READY role=audio-broadcast-source");
    if (!BLEDevice.begin("NU54-AUDIO-BROADCAST-SRC"))
    {
        Serial.println("P2_AUDIO_FAIL bt-begin");
        return;
    }
    if (codec.begin() != Error::none)
    {
        Serial.println("P2_AUDIO_FAIL codec-begin");
        return;
    }
    if (audioSource.begin(broadcastName, broadcastCode) != Error::none)
    {
        Serial.print("P2_AUDIO_FAIL source-begin native=");
        Serial.println(audioSource.nativeCode());
        return;
    }
    nucode::test::reportMemory("ready");
}

/** @brief LC3 frame을 10 ms 간격으로 전송하고 요청 시 자원을 반환합니다. */
void loop()
{
    if (finished)
    {
        delay(10);
        return;
    }
    BLEDevice.poll();
    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if (command == 'm')
        {
            nucode::test::reportMemory("cycle");
            Serial.print("P2_AUDIO_CYCLE_MEMORY sent=");
            Serial.println(audioSource.sentFrames());
        }
        else if (command == 's')
        {
            const std::uint32_t sent = audioSource.sentFrames();
            if (audioSource.end() != Error::none)
            {
                Serial.println("P2_AUDIO_FAIL source-end");
            }
            codec.end();
            BLEDevice.end();
            nucode::test::reportMemory("stopped");
            Serial.print("P2_STOP role=audio-broadcast-source sent=");
            Serial.println(sent);
            finished = true;
            return;
        }
    }
    if (!audioSource.streaming())
    {
        delay(1);
        return;
    }
    if (!announcedStreaming)
    {
        announcedStreaming = true;
        lastFrameAt = millis();
        Serial.println("P2_AUDIO_STREAM role=broadcast-source");
    }
    if (millis() - lastFrameAt < 10U)
    {
        delay(1);
        return;
    }
    lastFrameAt = millis();
    std::int16_t pcm[160] = {};
    std::uint8_t frame[40] = {};
    fillPcm(pcm);
    if (codec.encode(pcm, 160U, frame, sizeof(frame)) != Error::none)
    {
        Serial.println("P2_AUDIO_FAIL encode");
        return;
    }
    const Error sent = audioSource.sendFrame(frame);
    if ((sent != Error::none) && (sent != Error::busy))
    {
        Serial.print("P2_AUDIO_FAIL send native=");
        Serial.println(audioSource.nativeCode());
        return;
    }
    const std::uint32_t count = audioSource.sentFrames();
    if ((sent == Error::none) && ((count % 100U) == 0U))
    {
        Serial.print("P2_AUDIO_SENT frames=");
        Serial.println(count);
    }
}
