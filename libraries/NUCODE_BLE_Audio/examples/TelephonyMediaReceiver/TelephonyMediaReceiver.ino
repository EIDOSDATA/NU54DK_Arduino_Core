/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) TelephonyMediaBroadcaster (broadcaster); 2) TelephonyMediaReceiver (receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE_Audio/TelephonyMediaReceiver`, sha256 `06a086e5e723758512e955bc411f02bdd832d3e0945e73ca3eb4493aef8161f2`
 * @nucode_example_setup_end */

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
    Serial.println("TMAP local roles=0x20 service=TMAS");
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
        else if (command == 'q')
        {
            Lc3Codec incompatibleCodec;
            nucode::ble::audio::Lc3Config incompatibleQuality;
            incompatibleQuality.frame_duration_us = 5000U;
            Serial.println(incompatibleCodec.begin(incompatibleQuality) == Error::invalid_argument
                               ? "TMAP quality mismatch rejected"
                               : "TMAP quality mismatch unexpectedly accepted");
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
