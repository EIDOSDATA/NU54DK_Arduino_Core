/**
 * @file TelephonyMediaReceiver.ino
 * @brief TMAP broadcast receiver가 LC3 방송을 찾아 PCM으로 복호화합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

namespace
{
    using nucode::ble::audio::BroadcastSink;
    using nucode::ble::audio::BroadcastStage;
    using nucode::ble::audio::Error;
    using nucode::ble::audio::Lc3Codec;
    using nucode::ble::audio::TelephonyMediaRole;
    using nucode::ble::audio::TelephonyMediaRoles;

    constexpr const char *broadcastName = "NU54-TMAP-AUDIO";
    TelephonyMediaRoles profile;
    BroadcastSink audioSink;
    Lc3Codec codec;
    bool reportedFailure = false;

    /** @brief 방송 검색을 시작하고 오류를 원본 코드와 함께 출력합니다. */
    bool startListening()
    {
        const Error result = audioSink.begin(broadcastName);
        if (result != Error::none)
        {
            Serial.print("TMAP broadcast sink start failed native=");
            Serial.println(audioSink.nativeCode());
            return false;
        }
        reportedFailure = false;
        Serial.println("TMAP broadcast receiver scanning");
        return true;
    }

    /** @brief 초기화 실패 시 실패 단계를 출력합니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("TMAP receiver start failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000U);
        }
    }
} // namespace

void setup()
{
    Serial.begin(115200);
    require(BLEDevice.begin("NU54-TMAP-RECEIVER"), "device");
    require(profile.begin(TelephonyMediaRole::broadcast_media_receiver) == Error::none, "roles");
    require(codec.begin() == Error::none, "codec");
    require(startListening(), "broadcast");
}

void loop()
{
    BLEDevice.poll();
    profile.poll();
    audioSink.poll();

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            const Error result = audioSink.end();
            Serial.print("TMAP broadcast sink stop result=");
            Serial.println(static_cast<unsigned int>(result));
        }
        else if (command == 'r')
        {
            static_cast<void>(startListening());
        }
        else if (command == 'x')
        {
            TelephonyMediaRoles unsupported;
            Serial.println(unsupported.begin(TelephonyMediaRole::broadcast_media_sender) ==
                                   Error::unsupported
                               ? "Unsupported TMAP role rejected"
                               : "Unsupported TMAP role unexpectedly accepted");
        }
    }

    if ((audioSink.stage() == BroadcastStage::failed) && !reportedFailure)
    {
        reportedFailure = true;
        Serial.print("TMAP broadcast sync failed native=");
        Serial.println(audioSink.nativeCode());
    }
    std::uint8_t frame[40] = {};
    std::int16_t pcm[160] = {};
    while (audioSink.readFrame(frame))
    {
        if (codec.decode(frame, sizeof(frame), pcm, 160U) != Error::none)
        {
            Serial.println("TMAP LC3 decode failed");
            continue;
        }
        const std::uint32_t count = audioSink.receivedFrames();
        if ((count % 100U) == 0U)
        {
            Serial.print("TMAP broadcast received=");
            Serial.print(count);
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1U);
}
