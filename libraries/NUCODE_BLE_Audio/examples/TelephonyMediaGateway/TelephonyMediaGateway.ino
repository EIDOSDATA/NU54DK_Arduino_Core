/**
 * @file TelephonyMediaGateway.ino
 * @brief TMAP gateway가 terminal 역할을 확인한 뒤 LC3 unicast를 송신합니다.
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
    using nucode::ble::audio::TelephonyMediaStage;
    using nucode::ble::audio::UnicastClient;
    using nucode::ble::audio::UnicastClientStage;

    TelephonyMediaRoles profile;
    UnicastClient audioSource;
    Lc3Codec codec;
    nucode::ble::BLEAddress candidate;
    nucode::ble::BLEConnectionHandle peer;
    bool candidateReady = false;
    bool restartScan = false;
    bool audioStarted = false;
    bool reportedStreaming = false;
    bool reportedFailure = false;
    std::uint32_t lastFrameAt = 0U;
    std::uint32_t sentFrames = 0U;
    std::uint16_t wavePosition = 0U;

    constexpr TelephonyMediaRole localRoles =
        TelephonyMediaRole::call_gateway | TelephonyMediaRole::unicast_media_sender;
    constexpr TelephonyMediaRole expectedPeerRoles =
        TelephonyMediaRole::call_terminal | TelephonyMediaRole::unicast_media_receiver;

    /** @brief TMAS 광고 하나를 선택합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!candidateReady && result.connectable && !result.scan_response)
        {
            candidate = result.address;
            candidateReady = true;
            static_cast<void>(BLEScan.stop());
        }
    }

    /** @brief 연결 완료 뒤 보안을 요청하고 연결 소실 뒤 재검색합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == nucode::ble::BLEEvent::connected) &&
            (event.role == nucode::ble::BLELinkRole::central))
        {
            peer = event.connection;
            if (!BLESecurity.requestSecurity(peer))
            {
                Serial.println("TMAP security request failed");
            }
        }
        else if ((event.event == nucode::ble::BLEEvent::disconnected) && (event.connection == peer))
        {
            static_cast<void>(audioSource.end());
            peer = {};
            candidateReady = false;
            restartScan = true;
            audioStarted = false;
            reportedStreaming = false;
            reportedFailure = false;
        }
    }

    /** @brief encrypted link에서 TMAP 역할 검색을 시작합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        if ((event.connection == peer) &&
            ((event.event == nucode::ble::SecurityEvent::paired) ||
             (event.event == nucode::ble::SecurityEvent::security_changed)))
        {
            const Error result = profile.discover(peer);
            if ((result != Error::none) && (result != Error::busy))
            {
                Serial.print("TMAP discovery start failed native=");
                Serial.println(profile.nativeCode());
            }
        }
    }

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

    /** @brief 실패하면 사람이 읽을 수 있는 단계와 함께 예제를 멈춥니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("TMAP gateway start failed: ");
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
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLESecurity.onEvent(onSecurityEvent);

    require(BLESecurity.begin(security), "security");
    require(BLEDevice.begin("NU54-TMAP-GATEWAY"), "device");
    require(codec.begin() == Error::none, "codec");
    require(profile.begin(localRoles) == Error::none, "roles");
    Serial.println("TMAP local roles=0x5 service=TMAS");
    require(BLEScan.clearFilters(), "scan clear");
    require(BLEScan.filterServiceUuid(nucode::ble::BLEUuid(0x1855U)), "TMAS filter");
    require(BLEScan.start(true), "scan");
    Serial.println("TMAP gateway searching for a terminal");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    profile.poll();
    audioSource.poll();

    if (candidateReady && !peer.valid())
    {
        candidateReady = false;
        if (!BLEConnection.connect(candidate))
        {
            restartScan = true;
        }
    }
    if (restartScan && !BLEScan.running())
    {
        restartScan = !BLEScan.start(true);
    }
    if (!audioStarted && (profile.stage() == TelephonyMediaStage::discovered))
    {
        Serial.print("TMAP peer roles=0x");
        Serial.println(profile.peerRoles(), HEX);
        if (!profile.peerSupports(expectedPeerRoles))
        {
            Serial.println("TMAP terminal role combination rejected");
            static_cast<void>(BLEConnection.disconnect(peer));
        }
        else
        {
            const Error result = audioSource.begin(peer);
            audioStarted = result == Error::none;
            if (!audioStarted)
            {
                Serial.print("TMAP unicast start failed native=");
                Serial.println(audioSource.nativeCode());
                static_cast<void>(BLEConnection.disconnect(peer));
            }
        }
    }

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if ((command == 'r') && peer.valid())
        {
            static_cast<void>(BLEConnection.disconnect(peer));
        }
        else if (command == 'x')
        {
            const nucode::ble::BLEConnectionHandle invalid;
            Serial.println(profile.discover(invalid) == Error::not_connected
                               ? "Invalid TMAP peer rejected"
                               : "Invalid TMAP peer unexpectedly accepted");
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
            const Error result = audioSource.stop();
            Serial.print("TMAP stream stop result=");
            Serial.println(static_cast<unsigned int>(result));
        }
    }

    if ((audioSource.stage() == UnicastClientStage::failed) && !reportedFailure)
    {
        reportedFailure = true;
        Serial.print("TMAP unicast failed native=");
        Serial.println(audioSource.nativeCode());
    }
    if (audioSource.stage() != UnicastClientStage::streaming)
    {
        delay(1U);
        return;
    }
    if (!reportedStreaming)
    {
        reportedStreaming = true;
        Serial.println("TMAP unicast streaming");
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
    if (sent == Error::none)
    {
        sentFrames++;
        if ((sentFrames % 100U) == 0U)
        {
            Serial.print("TMAP sent frames=");
            Serial.println(sentFrames);
        }
    }
    else if (sent != Error::busy)
    {
        Serial.print("TMAP send failed native=");
        Serial.println(audioSource.nativeCode());
    }
}
