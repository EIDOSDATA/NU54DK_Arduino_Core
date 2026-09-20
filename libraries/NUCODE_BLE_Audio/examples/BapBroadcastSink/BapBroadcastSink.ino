/**
 * @file BapBroadcastSink.ino
 * @brief BAP broadcast source를 찾아 LC3 frame을 수신하고 decode합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::audio::BroadcastSink;
using nucode::ble::audio::BroadcastCode;
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
    constexpr BroadcastCode alternateBroadcastCode = {
        0x4f, 0x55, 0x35, 0x34, 0x2d, 0x41, 0x55, 0x44,
        0x49, 0x4f, 0x2d, 0x43, 0x4f, 0x44, 0x45, 0x31,
    };
    BroadcastSink audioSink;
    Lc3Codec codec;
    bool announcedStreaming = false;
    bool reportedFailure = false;

    /** @brief 공개 API로 방송 검색을 시작하고 결과를 Serial에 기록합니다. */
    bool startListening(const BroadcastCode &code)
    {
        const Error result = audioSink.begin(broadcastName, code);
        if (result != Error::none)
        {
            Serial.print("broadcast sink start failed: ");
            Serial.print(audioSink.nativeCode());
            Serial.print(" step=");
            Serial.println(static_cast<unsigned int>(audioSink.lastStep()));
            return false;
        }
        announcedStreaming = false;
        reportedFailure = false;
        Serial.println("broadcast sink scanning");
        return true;
    }

    /** @brief PCM frame의 절대값 합으로 실제 decode 결과를 확인합니다. */
    std::uint32_t frameEnergy(const std::int16_t (&pcm)[160])
    {
        std::uint32_t energy = 0U;
        for (const std::int16_t sample : pcm)
        {
            const std::int32_t value = sample;
            energy += static_cast<std::uint32_t>(value < 0 ? -value : value);
        }
        return energy;
    }
} // namespace

/** @brief Bluetooth, LC3 codec, BAP broadcast sink를 순서대로 시작합니다. */
void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-AUDIO-SINK"))
    {
        Serial.println("Bluetooth start failed");
        return;
    }
    if (codec.begin() != Error::none)
    {
        Serial.println("LC3 codec start failed");
        return;
    }
    static_cast<void>(startListening(broadcastCode));
}

/** @brief 동기화 단계를 진행하고 수신 LC3 frame을 PCM으로 decode합니다. */
void loop()
{
    BLEDevice.poll();
    audioSink.poll();

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            const Error result = audioSink.end();
            Serial.print("broadcast sink stopped: ");
            Serial.print(static_cast<unsigned int>(result));
            Serial.print(" native=");
            Serial.print(audioSink.nativeCode());
            Serial.print(" step=");
            Serial.println(static_cast<unsigned int>(audioSink.lastStep()));
        }
        else if (command == 'r')
        {
            static_cast<void>(startListening(broadcastCode));
        }
        else if (command == 'w')
        {
            const Error stopped = audioSink.end();
            if (stopped == Error::none)
            {
                static_cast<void>(startListening(alternateBroadcastCode));
            }
        }
    }

    if ((audioSink.stage() == BroadcastStage::failed) && !reportedFailure)
    {
        reportedFailure = true;
        Serial.print("broadcast sync failed: ");
        Serial.print(audioSink.nativeCode());
        Serial.print(" step=");
        Serial.println(static_cast<unsigned int>(audioSink.lastStep()));
    }
    if (audioSink.streaming() && !announcedStreaming)
    {
        announcedStreaming = true;
        Serial.println("broadcast sink streaming");
    }

    std::uint8_t frame[40] = {};
    while (audioSink.readFrame(frame))
    {
        std::int16_t pcm[160] = {};
        if (codec.decode(frame, sizeof(frame), pcm, 160U) != Error::none)
        {
            Serial.println("LC3 decode failed");
            continue;
        }
        const std::uint32_t count = audioSink.receivedFrames();
        if ((count % 100U) == 0U)
        {
            Serial.print("broadcast received=");
            Serial.print(count);
            Serial.print(" energy=");
            Serial.print(frameEnergy(pcm));
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1);
}
