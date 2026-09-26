/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) GamingAudioBroadcaster (broadcaster); 2) GamingAudioReceiver (receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE_Audio/GamingAudioBroadcaster`, sha256 `b34ecb1d66b3def44a3f6fe72133f3c454d27a4da24a590bf923b15f1ef5dc28`
 * @nucode_example_setup_end */

/**
 * @file GamingAudioBroadcaster.ino
 * @brief GMAP broadcast sender가 합성 PCM을 LC3 방송으로 전송합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

namespace
{
    using nucode::ble::audio::BroadcastSource;
    using nucode::ble::audio::Error;
    using nucode::ble::audio::GamingAudioFeatures;
    using nucode::ble::audio::GamingAudioRole;
    using nucode::ble::audio::GamingAudioRoles;
    using nucode::ble::audio::Lc3Codec;

    constexpr const char *broadcastName = "NU54-GAME-AUDIO";
    GamingAudioRoles profile;
    BroadcastSource audioSource;
    Lc3Codec codec;
    std::uint32_t lastFrameAt = 0U;
    std::uint32_t sentFrames = 0U;
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
        wavePosition = static_cast<std::uint16_t>((wavePosition + 23U) % 160U);
    }

    /** @brief BAP broadcast source를 다시 시작합니다. */
    bool startBroadcast()
    {
        const Error result = audioSource.begin(broadcastName);
        if (result != Error::none)
        {
            Serial.print("Gaming broadcast start failed native=");
            Serial.println(audioSource.nativeCode());
            return false;
        }
        Serial.println("Gaming broadcast streaming");
        return true;
    }

    /** @brief 초기화 실패를 단계별로 표시합니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("Gaming broadcaster start failed: ");
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

    require(BLEDevice.begin("NU54-GAME-BROADCASTER"), "device");
    require(profile.begin(GamingAudioRole::broadcast_game_sender, features) == Error::none,
            "roles");
    Serial.println("GMAP local roles=0x4 service=GMAS features=ugg:0x0,ugt:0x0,bgs:0x0,bgr:0x0");
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
            Serial.print("Gaming broadcast stop result=");
            Serial.println(static_cast<unsigned int>(result));
        }
        else if (command == 'r')
        {
            static_cast<void>(startBroadcast());
        }
        else if (command == 'x')
        {
            GamingAudioRoles unsupported;
            const GamingAudioFeatures noFeatures;
            Serial.println(unsupported.begin(GamingAudioRole::broadcast_game_receiver,
                                             noFeatures) == Error::unsupported
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
            invalidFeatures.broadcast_sender = 0x80U;
            Serial.println(invalidProfile.begin(GamingAudioRole::broadcast_game_sender,
                                                invalidFeatures) == Error::invalid_argument
                               ? "Invalid GMAP feature rejected"
                               : "Invalid GMAP feature unexpectedly accepted");
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
        Serial.println("Gaming LC3 encode failed");
        return;
    }
    const Error sent = audioSource.sendFrame(frame);
    if (sent == Error::none)
    {
        sentFrames++;
        if ((sentFrames % 100U) == 0U)
        {
            Serial.print("Gaming broadcast sent=");
            Serial.println(sentFrames);
        }
    }
    else if (sent != Error::busy)
    {
        Serial.print("Gaming broadcast send failed native=");
        Serial.println(audioSource.nativeCode());
    }
}
