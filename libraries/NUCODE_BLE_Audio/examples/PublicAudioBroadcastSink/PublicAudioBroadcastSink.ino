/**
 * @file PublicAudioBroadcastSink.ino
 * @brief Standard Quality 공개 오디오 방송을 찾아 LC3 frame을 복호화합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::audio::BroadcastCode;
using nucode::ble::audio::BroadcastStage;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::PublicAudioBroadcastSink;
using nucode::ble::audio::PublicBroadcastFilter;
using nucode::ble::audio::PublicBroadcastInfo;
using nucode::ble::audio::PublicBroadcastQuality;

namespace
{
    constexpr BroadcastCode broadcastCode = {
        0x4e, 0x55, 0x43, 0x4f, 0x44, 0x45, 0x2d, 0x50,
        0x55, 0x42, 0x4c, 0x49, 0x43, 0x2d, 0x30, 0x31,
    };
    constexpr BroadcastCode alternateBroadcastCode = {
        0x4f, 0x55, 0x43, 0x4f, 0x44, 0x45, 0x2d, 0x50,
        0x55, 0x42, 0x4c, 0x49, 0x43, 0x2d, 0x30, 0x31,
    };
    PublicBroadcastFilter broadcastFilter = {
        .broadcast_name = "NUCODE-PUBLIC-AUDIO",
        .required_quality = PublicBroadcastQuality::standard,
    };
    PublicAudioBroadcastSink audioSink;
    Lc3Codec codec;
    bool listening = false;
    bool announcedSelection = false;
    bool announcedStreaming = false;
    bool recoveryPending = false;
    bool automaticRecovery = true;
    std::uint32_t recoveryAt = 0U;

    /** @brief 다음 정리·재시작 시도를 1초 뒤로 제한합니다. */
    void scheduleRecovery()
    {
        recoveryPending = true;
        recoveryAt = millis() + 1000U;
    }

    /** @brief 공개 API로 조건에 맞는 방송 검색을 시작합니다. */
    bool startListening(const BroadcastCode &code)
    {
        broadcastFilter.required_quality = PublicBroadcastQuality::standard;
        const Error result = audioSink.begin(broadcastFilter, code);
        if (result != Error::none)
        {
            Serial.print("public audio sink start failed: ");
            Serial.println(audioSink.nativeCode());
            listening = audioSink.stage() == BroadcastStage::failed;
            return false;
        }
        listening = true;
        announcedSelection = false;
        announcedStreaming = false;
        recoveryPending = false;
        Serial.println("public audio sink scanning");
        return true;
    }

    /** @brief 실행 중인 검색을 끝내고 객체 상태를 갱신합니다. */
    bool stopListening()
    {
        if (listening)
        {
            const Error result = audioSink.end();
            if (result != Error::none)
            {
                Serial.print("public audio sink stop failed: ");
                Serial.println(audioSink.nativeCode());
                return false;
            }
            listening = false;
        }
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

/** @brief Bluetooth, LC3 codec과 공개 오디오 sink를 순서대로 시작합니다. */
void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NUCODE-PUBLIC-SINK"))
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

/** @brief 검색·동기화를 진행하고 공개 LC3 frame을 PCM으로 decode합니다. */
void loop()
{
    BLEDevice.poll();
    audioSink.poll();

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            automaticRecovery = false;
            recoveryPending = false;
            if (stopListening())
            {
                Serial.println("public audio sink stopped");
            }
        }
        else if (command == 'r')
        {
            automaticRecovery = true;
            if (stopListening() && !startListening(broadcastCode))
            {
                scheduleRecovery();
            }
        }
        else if (command == 'w')
        {
            automaticRecovery = true;
            if (stopListening() && !startListening(alternateBroadcastCode))
            {
                scheduleRecovery();
            }
        }
        else if (command == 'h')
        {
            automaticRecovery = true;
            if (stopListening())
            {
                broadcastFilter.required_quality = PublicBroadcastQuality::high;
                const Error result = audioSink.begin(broadcastFilter, broadcastCode);
                Serial.print("high quality rejected: ");
                Serial.println(static_cast<unsigned int>(result));
                broadcastFilter.required_quality = PublicBroadcastQuality::standard;
                scheduleRecovery();
            }
        }
    }

    PublicBroadcastInfo selectedInfo = {};
    if (!announcedSelection && audioSink.selected(selectedInfo))
    {
        announcedSelection = true;
        Serial.print("selected public audio name=");
        Serial.print(selectedInfo.broadcast_name);
        Serial.print(" program=");
        Serial.print(selectedInfo.program_info);
        Serial.print(" encrypted=");
        Serial.println(selectedInfo.encrypted ? "yes" : "no");
    }

    if (listening && automaticRecovery && !recoveryPending &&
        (audioSink.stage() == BroadcastStage::failed))
    {
        Serial.print("public audio sync failed: ");
        Serial.print(audioSink.nativeCode());
        Serial.print(" step=");
        Serial.println(static_cast<unsigned int>(audioSink.lastStep()));
        scheduleRecovery();
    }
    if (recoveryPending &&
        (static_cast<std::int32_t>(millis() - recoveryAt) >= 0))
    {
        recoveryPending = false;
        if (listening && !stopListening())
        {
            scheduleRecovery();
        }
        else if (!startListening(broadcastCode))
        {
            scheduleRecovery();
        }
    }
    if (audioSink.streaming() && !announcedStreaming)
    {
        announcedStreaming = true;
        Serial.println("public audio sink streaming");
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
            Serial.print("public audio received=");
            Serial.print(count);
            Serial.print(" energy=");
            Serial.print(frameEnergy(pcm));
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1U);
}
