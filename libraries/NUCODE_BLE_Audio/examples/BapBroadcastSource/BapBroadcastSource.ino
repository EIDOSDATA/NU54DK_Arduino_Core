/**
 * @file BapBroadcastSource.ino
 * @brief 합성 PCM을 LC3로 encode해 BAP broadcast stream으로 보냅니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::audio::BroadcastSource;
using nucode::ble::audio::BroadcastCode;
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

    /** @brief 16 kHz의 bounded 삼각파 PCM frame 하나를 생성합니다. */
    void fillPcm(std::int16_t (&pcm)[160])
    {
        for (std::size_t index = 0U; index < 160U; index++)
        {
            const std::uint16_t phase =
                static_cast<std::uint16_t>((wavePosition + index) % 160U);
            const std::int32_t rising = (phase < 80U) ? phase : (160U - phase);
            pcm[index] = static_cast<std::int16_t>(rising * 300 - 12000);
        }
        wavePosition = static_cast<std::uint16_t>((wavePosition + 17U) % 160U);
    }

    /** @brief 공개 API로 방송을 시작하고 결과를 Serial에 기록합니다. */
    bool startBroadcast()
    {
        const Error result = audioSource.begin(broadcastName, broadcastCode);
        if (result != Error::none)
        {
            Serial.print("broadcast source start failed: ");
            Serial.println(audioSource.nativeCode());
            return false;
        }
        announcedStreaming = false;
        Serial.println("broadcast source preparing");
        return true;
    }
} // namespace

/** @brief Bluetooth, LC3 codec, BAP broadcast source를 순서대로 시작합니다. */
void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-AUDIO-SOURCE"))
    {
        Serial.println("Bluetooth start failed");
        return;
    }
    if (codec.begin() != Error::none)
    {
        Serial.println("LC3 codec start failed");
        return;
    }
    static_cast<void>(startBroadcast());
}

/** @brief 10 ms마다 합성 LC3 frame을 보내고 Serial 명령으로 수명을 시험합니다. */
void loop()
{
    BLEDevice.poll();

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            const Error result = audioSource.end();
            Serial.print("broadcast source stopped: ");
            Serial.println(static_cast<unsigned int>(result));
        }
        else if (command == 'r')
        {
            static_cast<void>(startBroadcast());
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
        Serial.println("broadcast source streaming");
    }

    const std::uint32_t now = millis();
    if ((now - lastFrameAt) < 10U)
    {
        delay(1);
        return;
    }
    lastFrameAt = now;

    std::int16_t pcm[160] = {};
    std::uint8_t frame[40] = {};
    fillPcm(pcm);
    if (codec.encode(pcm, 160U, frame, sizeof(frame)) != Error::none)
    {
        Serial.println("LC3 encode failed");
        return;
    }
    const Error sent = audioSource.sendFrame(frame);
    if ((sent != Error::none) && (sent != Error::busy))
    {
        Serial.print("broadcast send failed: ");
        Serial.println(audioSource.nativeCode());
        return;
    }
    const std::uint32_t count = audioSource.sentFrames();
    if ((sent == Error::none) && ((count % 100U) == 0U))
    {
        Serial.print("broadcast sent frames=");
        Serial.println(count);
    }
}
