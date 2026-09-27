/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) TelephonyMediaGateway (gateway); 2) TelephonyMediaTerminal (terminal)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE_Audio/TelephonyMediaTerminal`, sha256 `f4b2c3c02dd15bcfed8c0de19ea57c46ab495e86b656bcf6a809e442f79d6065`
 * @nucode_example_setup_end */

/**
 * @file TelephonyMediaTerminal.ino
 * @brief TMAP terminal이 gateway의 LC3 unicast를 수신하고 복호화합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_BLE_Security.h>

namespace
{
    using nucode::ble::audio::Error;
    using nucode::ble::audio::Lc3Codec;
    using nucode::ble::audio::TelephonyMediaRole;
    using nucode::ble::audio::TelephonyMediaRoles;
    using nucode::ble::audio::UnicastServer;

    TelephonyMediaRoles profile;
    UnicastServer audioSink;
    Lc3Codec codec;
    bool restartAdvertising = false;
    bool audioStopped = false;
    std::uint32_t decodedFrames = 0U;

    constexpr TelephonyMediaRole localRoles =
        TelephonyMediaRole::call_terminal | TelephonyMediaRole::unicast_media_receiver;

    /** @brief TMAS와 ASCS UUID를 connectable 광고에 넣습니다. */
    bool startAdvertising()
    {
        constexpr std::uint8_t announcement[] = {1U, 0x03U, 0x00U, 0x00U, 0x00U, 0U};
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x1855U)) &&
               BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x184EU)) &&
               BLEAdvertising.setServiceData(nucode::ble::BLEUuid(0x184EU), announcement,
                                             sizeof(announcement)) &&
               BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    }

    /** @brief Just Works pairing을 승인합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            static_cast<void>(BLESecurity.acceptPairing(event.connection, true));
        }
    }

    /** @brief peer 소실 뒤 같은 역할 광고를 재시작합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == nucode::ble::BLEEvent::disconnected)
        {
            restartAdvertising = !audioStopped;
        }
    }

    /** @brief 역할 등록 또는 광고 실패를 명확히 출력합니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("TMAP terminal start failed: ");
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

    require(BLESecurity.begin(security), "security");
    require(BLEDevice.begin("NU54-TMAP-TERMINAL"), "device");
    require(profile.begin(localRoles) == Error::none, "roles");
    Serial.println("TMAP local roles=0xA service=TMAS");
    require(audioSink.begin() == Error::none, "unicast server");
    require(codec.begin() == Error::none, "codec");
    require(startAdvertising(), "advertising");
    Serial.println("TMAP terminal ready for unicast audio");
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
        else if (command == 's')
        {
            static_cast<void>(BLEAdvertising.stop());
            const Error result = audioSink.end();
            audioStopped = result == Error::none;
            Serial.print("TMAP unicast server stop result=");
            Serial.println(static_cast<unsigned int>(result));
        }
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
        decodedFrames++;
        if ((decodedFrames % 100U) == 0U)
        {
            Serial.print("TMAP decoded frames=");
            Serial.print(decodedFrames);
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1U);
}
