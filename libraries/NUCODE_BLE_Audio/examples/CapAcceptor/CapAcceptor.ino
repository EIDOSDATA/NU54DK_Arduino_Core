/**
 * @file CapAcceptor.ino
 * @brief CAP Acceptor와 Scan Delegator로 암호화 LC3 broadcast를 수신합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_BLE_Security.h>

using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::SecurityConfig;
using nucode::ble::SecurityEvent;
using nucode::ble::SecurityEventRecord;
using nucode::ble::SecurityIoCapability;
using nucode::ble::SecurityLevel;
using nucode::ble::audio::BroadcastSink;
using nucode::ble::audio::BroadcastStage;
using nucode::ble::audio::CapAcceptor;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;

namespace
{
    CapAcceptor acceptor;
    BroadcastSink audioSink;
    Lc3Codec codec;
    bool restartProfile = false;
    bool restartAdvertising = false;
    std::uint32_t restartAdvertisingAt = 0U;
    bool announcedStreaming = false;
    std::uint32_t reportedAdds = 0U;
    std::uint32_t reportedModifications = 0U;
    std::uint32_t reportedRemovals = 0U;

    /** @brief CAS와 BASS UUID를 포함한 연결 광고를 시작합니다. */
    bool startAdvertising()
    {
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.addServiceUuid(BLEUuid(0x1853U)) &&
               BLEAdvertising.addServiceUuid(BLEUuid(0x184FU)) &&
               BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    }

    /** @brief Just Works pairing 요청을 공개 security API로 승인합니다. */
    void onSecurityEvent(const SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(event.connection, true))
            {
                Serial.println("CAP pairing approval failed");
            }
        }
    }

    /** @brief Commander 연결 해제 뒤 profile과 광고 재시작을 예약합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            Serial.println("CAP commander connected");
        }
        else if (event.event == BLEEvent::disconnected)
        {
            restartProfile = true;
            restartAdvertising = true;
            restartAdvertisingAt = millis() + 100U;
            Serial.print("CAP commander disconnected reason=");
            Serial.println(event.reason);
        }
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

/** @brief security, CAP Acceptor, broadcast sink와 광고를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    SecurityConfig security;
    security.minimum_level = SecurityLevel::encrypted;
    security.bonding = false;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-CAP-ACCEPTOR") ||
        (codec.begin() != Error::none) || (acceptor.begin() != Error::none) ||
        (audioSink.beginDelegated() != Error::none) || !startAdvertising())
    {
        Serial.print("CAP acceptor start failed: ");
        Serial.println(audioSink.nativeCode());
        return;
    }
    Serial.println("CAP acceptor ready");
}

/** @brief CAP Commander 요청을 진행하고 수신한 LC3 frame을 decode합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    audioSink.poll();

    if (restartProfile)
    {
        restartProfile = false;
        Error result = audioSink.end();
        if (result == Error::none)
        {
            result = audioSink.beginDelegated();
        }
        if (result != Error::none)
        {
            Serial.print("CAP acceptor restart failed: ");
            Serial.println(audioSink.nativeCode());
        }
        else
        {
            reportedAdds = 0U;
            reportedModifications = 0U;
            reportedRemovals = 0U;
            announcedStreaming = false;
            restartAdvertisingAt = millis() + 100U;
            Serial.println("CAP acceptor profile restarted");
        }
    }

    if (restartAdvertising && !BLEAdvertising.running() &&
        (static_cast<std::int32_t>(millis() - restartAdvertisingAt) >= 0))
    {
        if (startAdvertising())
        {
            restartAdvertising = false;
            Serial.println("CAP acceptor advertising restarted");
        }
        else
        {
            restartAdvertisingAt = millis() + 1000U;
            Serial.println("CAP acceptor advertising restart failed");
        }
    }

    if (audioSink.delegatedAdds() != reportedAdds)
    {
        reportedAdds = audioSink.delegatedAdds();
        Serial.print("CAP source added: ");
        Serial.println(reportedAdds);
    }
    if (audioSink.delegatedModifications() != reportedModifications)
    {
        reportedModifications = audioSink.delegatedModifications();
        Serial.print("CAP source modified: ");
        Serial.println(reportedModifications);
    }
    if (audioSink.delegatedRemovals() != reportedRemovals)
    {
        reportedRemovals = audioSink.delegatedRemovals();
        Serial.print("CAP source removed: ");
        Serial.println(reportedRemovals);
    }
    if (audioSink.streaming() && !announcedStreaming)
    {
        announcedStreaming = true;
        Serial.println("CAP acceptor streaming");
    }
    else if (!audioSink.streaming() && (audioSink.stage() == BroadcastStage::idle))
    {
        announcedStreaming = false;
    }

    std::uint8_t frame[40] = {};
    while (audioSink.readFrame(frame))
    {
        std::int16_t pcm[160] = {};
        if (codec.decode(frame, sizeof(frame), pcm, 160U) != Error::none)
        {
            Serial.println("CAP LC3 decode failed");
            continue;
        }
        const std::uint32_t count = audioSink.receivedFrames();
        if ((count % 100U) == 0U)
        {
            Serial.print("CAP received=");
            Serial.print(count);
            Serial.print(" energy=");
            Serial.print(frameEnergy(pcm));
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }

    if (audioSink.stage() == BroadcastStage::failed)
    {
        Serial.print("CAP broadcast failed: ");
        Serial.println(audioSink.nativeCode());
        delay(1000U);
    }
    delay(1U);
}
