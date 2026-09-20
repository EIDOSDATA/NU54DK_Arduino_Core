/**
 * @file GamingAudioTerminal.ino
 * @brief GMAP terminal이 gateway의 LC3 unicast를 수신하고 복호화합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_BLE_Security.h>

namespace
{
    using nucode::ble::audio::Error;
    using nucode::ble::audio::GamingAudioFeatures;
    using nucode::ble::audio::GamingAudioRole;
    using nucode::ble::audio::GamingAudioRoles;
    using nucode::ble::audio::GamingTerminalFeature;
    using nucode::ble::audio::Lc3Codec;
    using nucode::ble::audio::UnicastServer;

    GamingAudioRoles profile;
    UnicastServer audioSink;
    Lc3Codec codec;
    bool restartAdvertising = false;
    bool audioStopped = false;
    std::uint32_t decodedFrames = 0U;

    /** @brief encrypted GMAS 읽기를 위해 pairing을 승인합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            static_cast<void>(BLESecurity.acceptPairing(event.connection, true));
        }
    }

    /** @brief 연결 해제 뒤 GMAS와 ASCS 광고를 다시 시작합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == nucode::ble::BLEEvent::disconnected)
        {
            restartAdvertising = !audioStopped;
        }
    }

    /** @brief GMAS와 ASCS UUID를 connectable 광고에 넣습니다. */
    bool startAdvertising()
    {
        constexpr std::uint8_t announcement[] = {1U, 0x03U, 0x00U, 0x00U, 0x00U, 0U};
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x1858U)) &&
               BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x184EU)) &&
               BLEAdvertising.setServiceData(nucode::ble::BLEUuid(0x184EU), announcement,
                                             sizeof(announcement)) &&
               BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    }

    /** @brief 설정 오류를 성공 상태와 구분해 출력합니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("Gaming terminal start failed: ");
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

    nucode::ble::SecurityConfig security;
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = false;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);

    GamingAudioFeatures features;
    features.unicast_terminal = static_cast<std::uint8_t>(GamingTerminalFeature::sink);
    require(BLESecurity.begin(security), "security");
    require(BLEDevice.begin("NU54-GAME-TERMINAL"), "device");
    require(profile.begin(GamingAudioRole::unicast_game_terminal, features) == Error::none,
            "roles");
    Serial.println("GMAP local roles=0x2 service=GMAS features=ugg:0x0,ugt:0x4,bgs:0x0,bgr:0x0");
    require(audioSink.begin() == Error::none, "unicast server");
    require(codec.begin() == Error::none, "codec");
    require(startAdvertising(), "advertising");
    Serial.println("Gaming terminal ready for unicast audio");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    profile.poll();

    if (restartAdvertising && !BLEAdvertising.running())
    {
        restartAdvertising = !startAdvertising();
    }
    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 'r')
        {
            if (audioStopped)
            {
                audioStopped = audioSink.begin() != Error::none;
            }
            restartAdvertising = !audioStopped;
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
            Lc3Codec incompatibleCodec;
            nucode::ble::audio::Lc3Config incompatibleQuality;
            incompatibleQuality.frame_duration_us = 5000U;
            Serial.println(incompatibleCodec.begin(incompatibleQuality) == Error::invalid_argument
                               ? "Gaming quality mismatch rejected"
                               : "Gaming quality mismatch unexpectedly accepted");
        }
        else if (command == 'f')
        {
            GamingAudioRoles invalidProfile;
            GamingAudioFeatures invalidFeatures;
            invalidFeatures.unicast_terminal = 0x80U;
            Serial.println(invalidProfile.begin(GamingAudioRole::unicast_game_terminal,
                                                invalidFeatures) == Error::invalid_argument
                               ? "Invalid GMAP feature rejected"
                               : "Invalid GMAP feature unexpectedly accepted");
        }
        else if (command == 's')
        {
            static_cast<void>(BLEAdvertising.stop());
            const Error result = audioSink.end();
            audioStopped = result == Error::none;
            Serial.print("Gaming unicast server stop result=");
            Serial.println(static_cast<unsigned int>(result));
        }
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
        decodedFrames++;
        if ((decodedFrames % 100U) == 0U)
        {
            Serial.print("Gaming decoded frames=");
            Serial.print(decodedFrames);
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1U);
}
