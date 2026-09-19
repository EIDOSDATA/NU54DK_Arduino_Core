/**
 * @file CapUnicastInitiator.ino
 * @brief CAP Acceptor를 확인하고 LC3 unicast의 시작·취소·중단을 반복합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::BLEAddress;
using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLELinkRole;
using nucode::ble::BLEScanResult;
using nucode::ble::BLEUuid;
using nucode::ble::audio::CapUnicastInitiator;
using nucode::ble::audio::CapUnicastStage;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;

namespace
{
    CapUnicastInitiator initiator;
    Lc3Codec codec;
    BLEAddress peerAddress;
    BLEConnectionHandle peer;
    bool peerFound = false;
    bool restartScan = false;
    bool startIssued = false;
    bool stopIssued = false;
    bool failureReported = false;
    bool cancellationReported = false;
    std::uint32_t completedSessions = 0U;
    std::uint32_t lastFrameAt = 0U;
    std::uint32_t lastStatusAt = 0U;
    std::uint16_t wavePosition = 0U;

    /** @brief CAS를 광고하는 첫 연결 가능한 Acceptor를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            static_cast<void>(BLEScan.stop());
            Serial.println("CAP Acceptor found");
        }
    }

    /** @brief 공개 BLE 연결을 CAP unicast Initiator에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) && (event.role == BLELinkRole::central))
        {
            peer = event.connection;
            startIssued = false;
            stopIssued = false;
            failureReported = false;
            cancellationReported = false;
            const Error result = initiator.begin(peer);
            if (result == Error::none)
            {
                Serial.println("CAP connected; discovering services");
            }
            else
            {
                Serial.print("CAP begin failed: ");
                Serial.println(initiator.nativeCode());
                static_cast<void>(BLEConnection.disconnect(peer));
            }
        }
        else if ((event.event == BLEEvent::disconnected) && (event.connection == peer))
        {
            const Error result = initiator.end();
            if ((result != Error::none) && (result != Error::not_started))
            {
                Serial.print("CAP cleanup failed: ");
                Serial.println(initiator.nativeCode());
            }
            peer = BLEConnectionHandle();
            peerFound = false;
            restartScan = true;
            startIssued = false;
            stopIssued = false;
            Serial.println("CAP peer disconnected");
        }
    }

    /** @brief 16 kHz bounded 삼각파 PCM frame 하나를 생성합니다. */
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
} // namespace

/** @brief codec와 CAS 기반 Acceptor 검색을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScanResult);
    BLEDevice.onEventInfo(onBleEvent);
    if ((codec.begin() != Error::none) || !BLEDevice.begin("NU54-CAP-UNICAST") ||
        !BLEScan.clearFilters() || !BLEScan.filterServiceUuid(BLEUuid(0x1853U)) ||
        !BLEScan.start(true))
    {
        Serial.println("CAP unicast setup failed");
        return;
    }
    Serial.println("CAP Acceptor scan started");
}

/** @brief CAP group을 시작하고 홀수 session에서는 진행 중 절차 취소를 확인합니다. */
void loop()
{
    BLEDevice.poll();
    initiator.poll();
    const std::uint32_t now = millis();
    if ((now - lastStatusAt) >= 2000U)
    {
        lastStatusAt = now;
        Serial.print("CAP Initiator status found=");
        Serial.print(peerFound ? 1 : 0);
        Serial.print(" connected=");
        Serial.print(BLEConnection.connected() ? 1 : 0);
        Serial.print(" connecting=");
        Serial.print(BLEConnection.connecting() ? 1 : 0);
        Serial.print(" stage=");
        Serial.println(static_cast<unsigned int>(initiator.stage()));
    }

    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress))
        {
            restartScan = true;
            Serial.println("CAP connect failed");
        }
    }
    if (restartScan && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        restartScan = false;
        if (!BLEScan.startExtended(true, false, false))
        {
            restartScan = true;
            Serial.println("CAP scan restart failed");
        }
    }

    if (initiator.ready() && !startIssued)
    {
        const Error result = initiator.start();
        startIssued = result == Error::none;
        Serial.print("CAP group start result=");
        Serial.println(static_cast<unsigned int>(result));
        if (startIssued && ((completedSessions % 2U) == 1U))
        {
            const Error cancelled = initiator.cancel();
            Serial.print("CAP in-flight cancel result=");
            Serial.println(static_cast<unsigned int>(cancelled));
        }
    }

    if (initiator.cancelled() && !cancellationReported)
    {
        cancellationReported = true;
        completedSessions++;
        Serial.print("CAP procedure cancelled native=");
        Serial.println(initiator.nativeCode());
        static_cast<void>(BLEConnection.disconnect(peer));
    }

    if ((initiator.stage() == CapUnicastStage::failed) && !failureReported)
    {
        failureReported = true;
        Serial.print("CAP procedure failed step=");
        Serial.print(static_cast<unsigned int>(initiator.lastStep()));
        Serial.print(" peer=");
        Serial.print(initiator.failedOnPeer() ? 1 : 0);
        Serial.print(" native=");
        Serial.println(initiator.nativeCode());
        static_cast<void>(BLEConnection.disconnect(peer));
    }

    if (!initiator.streaming())
    {
        if (startIssued && stopIssued && initiator.ready())
        {
            const Error result = initiator.end();
            if (result == Error::none)
            {
                completedSessions++;
                Serial.print("CAP completed sessions=");
                Serial.println(completedSessions);
                static_cast<void>(BLEConnection.disconnect(peer));
            }
        }
        delay(1U);
        return;
    }

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
        Serial.println("CAP encode failed");
        return;
    }
    const Error sent = initiator.sendFrame(frame);
    if ((sent != Error::none) && (sent != Error::busy))
    {
        Serial.print("CAP send failed: ");
        Serial.println(initiator.nativeCode());
    }
    const std::uint32_t count = initiator.sentFrames();
    if ((sent == Error::none) && ((count % 100U) == 0U))
    {
        Serial.print("CAP sent frames=");
        Serial.println(count);
    }
    if (!stopIssued && (count >= 120U))
    {
        const Error result = initiator.stop();
        stopIssued = result == Error::none;
        const Error duplicate = initiator.stop();
        Serial.print("CAP stop result=");
        Serial.print(static_cast<unsigned int>(result));
        Serial.print(" duplicate=");
        Serial.println(static_cast<unsigned int>(duplicate));
    }
}
