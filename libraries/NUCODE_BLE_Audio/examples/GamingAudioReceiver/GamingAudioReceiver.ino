/**
 * @file GamingAudioReceiver.ino
 * @brief GMAP broadcast receiver가 LC3 방송을 찾아 PCM으로 복호화합니다.
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
    using nucode::ble::audio::GamingAudioFeatures;
    using nucode::ble::audio::GamingAudioRole;
    using nucode::ble::audio::GamingAudioRoles;
    using nucode::ble::audio::Lc3Codec;

    constexpr const char *broadcastName = "NU54-GAME-AUDIO";
    GamingAudioRoles profile;
    BroadcastSink audioSink;
    Lc3Codec codec;
    bool reportedFailure = false;

    /** @brief 방송 검색을 시작하고 오류를 원본 코드와 함께 출력합니다. */
    bool startListening()
    {
        const Error result = audioSink.begin(broadcastName);
        if (result != Error::none)
        {
            Serial.print("Gaming broadcast sink start failed native=");
            Serial.println(audioSink.nativeCode());
            return false;
        }
        reportedFailure = false;
        Serial.println("Gaming broadcast receiver scanning");
        return true;
    }

    /** @brief 초기화 실패를 성공 출력과 구분합니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("Gaming receiver start failed: ");
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
    GamingAudioFeatures features;

    require(BLEDevice.begin("NU54-GAME-RECEIVER"), "device");
    require(profile.begin(GamingAudioRole::broadcast_game_receiver, features) == Error::none,
            "roles");
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
            Serial.print("Gaming broadcast sink stop result=");
            Serial.println(static_cast<unsigned int>(result));
        }
        else if (command == 'r')
        {
            static_cast<void>(startListening());
        }
        else if (command == 'x')
        {
            GamingAudioRoles unsupported;
            const GamingAudioFeatures noFeatures;
            Serial.println(unsupported.begin(GamingAudioRole::broadcast_game_sender, noFeatures) ==
                                   Error::unsupported
                               ? "Unsupported GMAP role rejected"
                               : "Unsupported GMAP role unexpectedly accepted");
        }
        else if (command == 'q')
        {
            GamingAudioRoles invalidProfile;
            GamingAudioFeatures invalidFeatures;
            invalidFeatures.broadcast_receiver = 0x80U;
            Serial.println(invalidProfile.begin(GamingAudioRole::broadcast_game_receiver,
                                                invalidFeatures) == Error::invalid_argument
                               ? "Invalid GMAP feature rejected"
                               : "Invalid GMAP feature unexpectedly accepted");
        }
    }

    if ((audioSink.stage() == BroadcastStage::failed) && !reportedFailure)
    {
        reportedFailure = true;
        Serial.print("Gaming broadcast sync failed native=");
        Serial.println(audioSink.nativeCode());
    }
    std::uint8_t frame[40] = {};
    std::int16_t pcm[160] = {};
    while (audioSink.readFrame(frame))
    {
        if (codec.decode(frame, sizeof(frame), pcm, 160U) != Error::none)
        {
            Serial.println("Gaming LC3 decode failed");
            continue;
        }
        const std::uint32_t count = audioSink.receivedFrames();
        if ((count % 100U) == 0U)
        {
            Serial.print("Gaming broadcast received=");
            Serial.print(count);
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1U);
}
