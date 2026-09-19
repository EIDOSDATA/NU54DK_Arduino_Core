/**
 * @file PublicAudioBroadcastSource.ino
 * @brief Standard Quality 공개 오디오 방송으로 합성 LC3 frame을 보냅니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::audio::BroadcastCode;
using nucode::ble::audio::CapStage;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::PublicAudioBroadcastSource;
using nucode::ble::audio::PublicBroadcastQuality;
using nucode::ble::audio::PublicBroadcastSourceConfig;

namespace
{
    constexpr BroadcastCode broadcastCode = {
        0x4e, 0x55, 0x43, 0x4f, 0x44, 0x45, 0x2d, 0x50,
        0x55, 0x42, 0x4c, 0x49, 0x43, 0x2d, 0x30, 0x31,
    };
    PublicBroadcastSourceConfig broadcastConfig = {
        .broadcast_name = "NUCODE-PUBLIC-AUDIO",
        .program_info = "Synthetic 16 kHz audio",
        .quality = PublicBroadcastQuality::standard,
    };
    PublicAudioBroadcastSource audioSource;
    Lc3Codec codec;
    std::uint32_t lastFrameAt = 0U;
    std::uint16_t wavePosition = 0U;
    bool announcedStreaming = false;
    bool broadcasting = false;
    bool recoveryPending = false;
    bool automaticRecovery = true;
    std::uint32_t recoveryAt = 0U;

    /** @brief 다음 정리·재시작 시도를 1초 뒤로 제한합니다. */
    void scheduleRecovery()
    {
        recoveryPending = true;
        recoveryAt = millis() + 1000U;
    }

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

    /** @brief 공개 C++ API로 암호화된 Standard Quality 방송을 시작합니다. */
    bool startBroadcast()
    {
        broadcastConfig.quality = PublicBroadcastQuality::standard;
        const Error result = audioSource.begin(broadcastConfig, broadcastCode);
        if (result != Error::none)
        {
            Serial.print("public audio source start failed: ");
            Serial.println(audioSource.nativeCode());
            broadcasting = audioSource.stage() == CapStage::failed;
            return false;
        }
        broadcasting = true;
        announcedStreaming = false;
        recoveryPending = false;
        Serial.println("public audio source preparing");
        return true;
    }

    /** @brief source teardown이 끝난 경우에만 공개 상태를 stopped로 바꿉니다. */
    bool stopBroadcast()
    {
        if (!broadcasting)
        {
            return true;
        }
        const Error result = audioSource.end();
        if (result != Error::none)
        {
            Serial.print("public audio source stop failed: ");
            Serial.println(audioSource.nativeCode());
            return false;
        }
        broadcasting = false;
        return true;
    }
} // namespace

/** @brief Bluetooth, LC3 codec과 공개 오디오 source를 순서대로 시작합니다. */
void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NUCODE-PUBLIC-SOURCE"))
    {
        Serial.println("Bluetooth start failed");
        return;
    }
    if (codec.begin() != Error::none)
    {
        Serial.println("LC3 codec start failed");
        return;
    }
    if (!startBroadcast())
    {
        scheduleRecovery();
    }
}

/** @brief LC3 송신과 중단·재시작·미지원 품질 확인 명령을 처리합니다. */
void loop()
{
    BLEDevice.poll();

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            automaticRecovery = false;
            recoveryPending = false;
            if (stopBroadcast())
            {
                Serial.println("public audio source stopped");
            }
        }
        else if (command == 'r')
        {
            automaticRecovery = true;
            if (stopBroadcast() && !startBroadcast())
            {
                scheduleRecovery();
            }
        }
        else if (command == 'h')
        {
            automaticRecovery = true;
            if (stopBroadcast())
            {
                broadcastConfig.quality = PublicBroadcastQuality::high;
                const Error result = audioSource.begin(broadcastConfig, broadcastCode);
                Serial.print("high quality rejected: ");
                Serial.println(static_cast<unsigned int>(result));
                broadcastConfig.quality = PublicBroadcastQuality::standard;
                scheduleRecovery();
            }
        }
    }

    if (broadcasting && automaticRecovery && !recoveryPending &&
        (audioSource.stage() == CapStage::failed))
    {
        Serial.print("public audio source failed: ");
        Serial.println(audioSource.nativeCode());
        scheduleRecovery();
    }
    if (recoveryPending &&
        (static_cast<std::int32_t>(millis() - recoveryAt) >= 0))
    {
        recoveryPending = false;
        if (broadcasting && !stopBroadcast())
        {
            scheduleRecovery();
        }
        else if (!startBroadcast())
        {
            scheduleRecovery();
        }
    }

    if (!audioSource.streaming())
    {
        delay(1U);
        return;
    }
    if (!announcedStreaming)
    {
        announcedStreaming = true;
        lastFrameAt = millis();
        Serial.println("public audio source streaming");
    }

    const std::uint32_t now = millis();
    if ((now - lastFrameAt) < 10U)
    {
        delay(1U);
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
        Serial.print("public audio send failed: ");
        Serial.println(audioSource.nativeCode());
        return;
    }
    const std::uint32_t count = audioSource.sentFrames();
    if ((sent == Error::none) && ((count % 100U) == 0U))
    {
        Serial.print("public audio sent frames=");
        Serial.println(count);
    }
}
