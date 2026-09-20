/**
 * @file TelephonyMediaBroadcaster.ino
 * @brief TMAP broadcast sender가 합성 PCM을 LC3 방송으로 전송합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

namespace
{
    using nucode::ble::audio::BroadcastSource;
    using nucode::ble::audio::Error;
    using nucode::ble::audio::Lc3Codec;
    using nucode::ble::audio::TelephonyMediaRole;
    using nucode::ble::audio::TelephonyMediaRoles;

    constexpr const char *broadcastName = "NU54-TMAP-AUDIO";
    TelephonyMediaRoles profile;
    BroadcastSource audioSource;
    Lc3Codec codec;
    std::uint32_t lastFrameAt = 0U;
    std::uint16_t wavePosition = 0U;

    /** @brief 16 kHz의 bounded 삼각파 PCM frame 하나를 생성합니다. */
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

    /** @brief BAP broadcast source를 다시 시작합니다. */
    bool startBroadcast()
    {
        const Error result = audioSource.begin(broadcastName);
        if (result != Error::none)
        {
            Serial.print("TMAP broadcast start failed native=");
            Serial.println(audioSource.nativeCode());
            return false;
        }
        Serial.println("TMAP broadcast streaming");
        return true;
    }

    /** @brief 초기화 실패가 성공 출력으로 가려지지 않게 멈춥니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("TMAP broadcaster start failed: ");
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
    require(BLEDevice.begin("NU54-TMAP-BROADCASTER"), "device");
    require(profile.begin(TelephonyMediaRole::broadcast_media_sender) == Error::none, "roles");
    require(codec.begin() == Error::none, "codec");
    require(startBroadcast(), "broadcast");
}

void loop()
{
    BLEDevice.poll();
    profile.poll();

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            const Error result = audioSource.end();
            Serial.print("TMAP broadcast stop result=");
            Serial.println(static_cast<unsigned int>(result));
        }
        else if (command == 'r')
        {
            static_cast<void>(startBroadcast());
        }
        else if (command == 'x')
        {
            TelephonyMediaRoles unsupported;
            Serial.println(unsupported.begin(TelephonyMediaRole::broadcast_media_receiver) ==
                                   Error::unsupported
                               ? "Unsupported TMAP role rejected"
                               : "Unsupported TMAP role unexpectedly accepted");
        }
    }

    if (!audioSource.streaming())
    {
        delay(1U);
        return;
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
        Serial.println("TMAP LC3 encode failed");
        return;
    }
    const Error sent = audioSource.sendFrame(frame);
    if ((sent != Error::none) && (sent != Error::busy))
    {
        Serial.print("TMAP broadcast send failed native=");
        Serial.println(audioSource.nativeCode());
    }
}
