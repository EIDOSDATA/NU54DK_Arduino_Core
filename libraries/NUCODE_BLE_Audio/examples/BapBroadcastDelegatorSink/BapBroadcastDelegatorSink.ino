/**
 * @file BapBroadcastDelegatorSink.ino
 * @brief BASS Scan Delegator로 선택된 broadcast LC3 stream을 수신합니다.
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
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;

namespace
{
    BroadcastSink audioSink;
    Lc3Codec codec;
    bool restartDelegatedState = false;
    bool restartAdvertising = false;
    std::uint32_t restartAdvertisingAt = 0U;
    bool announcedStreaming = false;
    std::uint32_t reportedAdds = 0U;
    std::uint32_t reportedModifications = 0U;
    std::uint32_t reportedRemovals = 0U;

    /** @brief BASS와 PACS UUID를 포함한 연결 광고를 시작합니다. */
    bool startAdvertising()
    {
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.addServiceUuid(BLEUuid(0x184FU)) &&
               BLEAdvertising.addServiceUuid(BLEUuid(0x1850U)) &&
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
                Serial.println("delegator pairing approval failed");
            }
        }
    }

    /** @brief Assistant 연결 해제 뒤 connectable 광고를 다시 예약합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            Serial.println("broadcast assistant connected");
        }
        else if (event.event == BLEEvent::disconnected)
        {
            restartDelegatedState = true;
            restartAdvertising = true;
            restartAdvertisingAt = millis() + 100U;
            Serial.print("broadcast assistant disconnected reason=");
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

/** @brief security, BLE, codec, Scan Delegator와 connectable 광고를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    SecurityConfig security;
    security.minimum_level = SecurityLevel::encrypted;
    security.bonding = false;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-AUDIO-DELEGATOR") ||
        (codec.begin() != Error::none) || (audioSink.beginDelegated() != Error::none) ||
        !startAdvertising())
    {
        Serial.print("broadcast delegator start failed: ");
        Serial.println(audioSink.nativeCode());
        return;
    }
    Serial.println("broadcast delegator ready");
}

/** @brief Assistant 요청과 broadcast 동기화를 진행하고 LC3 frame을 decode합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    audioSink.poll();

    if (restartDelegatedState)
    {
        restartDelegatedState = false;
        Error result = audioSink.end();
        if (result == Error::none)
        {
            result = audioSink.beginDelegated();
        }
        if (result != Error::none)
        {
            Serial.print("delegator state restart failed: ");
            Serial.println(audioSink.nativeCode());
        }
        else
        {
            reportedAdds = 0U;
            reportedModifications = 0U;
            reportedRemovals = 0U;
            announcedStreaming = false;
            restartAdvertisingAt = millis() + 100U;
            Serial.println("delegator state restarted");
        }
    }

    if (restartAdvertising && !BLEAdvertising.running() &&
        (static_cast<std::int32_t>(millis() - restartAdvertisingAt) >= 0))
    {
        if (startAdvertising())
        {
            restartAdvertising = false;
            Serial.println("delegator advertising restarted");
        }
        else
        {
            restartAdvertisingAt = millis() + 1000U;
            Serial.print("delegator advertising restart failed error=");
            Serial.print(static_cast<unsigned int>(BLEDevice.lastError()));
            Serial.print(" driver=");
            Serial.println(BLEDevice.lastDriverError());
        }
    }

    if (audioSink.delegatedAdds() != reportedAdds)
    {
        reportedAdds = audioSink.delegatedAdds();
        Serial.print("delegated source added: ");
        Serial.println(reportedAdds);
    }
    if (audioSink.delegatedModifications() != reportedModifications)
    {
        reportedModifications = audioSink.delegatedModifications();
        Serial.print("delegated source modified: ");
        Serial.println(reportedModifications);
    }
    if (audioSink.delegatedRemovals() != reportedRemovals)
    {
        reportedRemovals = audioSink.delegatedRemovals();
        Serial.print("delegated source removed: ");
        Serial.println(reportedRemovals);
    }
    if (audioSink.streaming() && !announcedStreaming)
    {
        announcedStreaming = true;
        Serial.println("delegated broadcast streaming");
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
            Serial.println("delegated LC3 decode failed");
            continue;
        }
        const std::uint32_t count = audioSink.receivedFrames();
        if ((count % 100U) == 0U)
        {
            Serial.print("delegated received=");
            Serial.print(count);
            Serial.print(" energy=");
            Serial.print(frameEnergy(pcm));
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }

    if (audioSink.stage() == BroadcastStage::failed)
    {
        Serial.print("delegated broadcast failed: ");
        Serial.print(audioSink.nativeCode());
        Serial.print(" step=");
        Serial.println(static_cast<unsigned int>(audioSink.lastStep()));
        delay(1000U);
    }
    delay(1U);
}
