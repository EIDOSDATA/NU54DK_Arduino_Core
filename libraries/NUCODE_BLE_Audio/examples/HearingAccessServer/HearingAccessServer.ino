/**
 * @file HearingAccessServer.ino
 * @brief preset을 게시하고 local·remote 선택을 처리하는 Hearing Access 예제입니다.
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
using nucode::ble::audio::Error;
using nucode::ble::audio::HearingAccessServer;
using nucode::ble::audio::HearingAccessServerConfig;
using nucode::ble::audio::HearingAidType;
using nucode::ble::audio::HearingPreset;

namespace
{
    HearingAccessServer hearingAccess;
    bool restartAdvertising = false;
    std::uint32_t restartAt = 0U;

    /** @brief Hearing Access Service UUID와 장치 이름을 광고합니다. */
    bool startAdvertising()
    {
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.addServiceUuid(BLEUuid(0x1854U)) &&
               BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    }

    /** @brief Just Works pairing 요청을 승인합니다. */
    void onSecurityEvent(const SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == SecurityEvent::pairing_requested)
        {
            static_cast<void>(BLESecurity.acceptPairing(event.connection, true));
        }
    }

    /** @brief client 연결 해제 뒤 광고 재시작을 예약합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            Serial.println("Hearing client connected");
            if (!BLESecurity.requestSecurity(event.connection))
            {
                Serial.println("Hearing Access security request failed");
            }
        }
        else if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            restartAt = millis() + 100U;
            Serial.print("Hearing client disconnected reason=");
            Serial.println(event.reason);
        }
    }

    /** @brief 공개 API 결과와 HAS 원본 오류를 출력합니다. */
    void report(const char *operation, Error result)
    {
        Serial.print(operation);
        Serial.print(" result=");
        Serial.print(static_cast<unsigned int>(result));
        Serial.print(" native=");
        Serial.println(hearingAccess.nativeCode());
    }

    /** @brief 현재 preset 목록과 active index를 출력합니다. */
    void printPresets()
    {
        Serial.print("active=");
        Serial.print(hearingAccess.activePreset());
        Serial.print(" selections=");
        Serial.println(hearingAccess.selectionChanges());
        for (std::size_t position = 0U; position < hearingAccess.presetCount(); ++position)
        {
            HearingPreset preset;
            if (hearingAccess.preset(position, preset) == Error::none)
            {
                Serial.print("preset index=");
                Serial.print(preset.index);
                Serial.print(" available=");
                Serial.print(preset.available ? 1 : 0);
                Serial.print(" writable=");
                Serial.print(preset.writable ? 1 : 0);
                Serial.print(" name=");
                Serial.println(preset.name);
            }
        }
    }
} // namespace

/** @brief 보안, HAS preset database와 광고를 준비합니다. */
void setup()
{
    Serial.begin(115200);

    SecurityConfig security;
    security.minimum_level = SecurityLevel::encrypted;
    security.bonding = false;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);

    HearingAccessServerConfig config;
    config.type = HearingAidType::monaural;
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-HEARING-AID") ||
        (hearingAccess.begin(config) != Error::none) ||
        (hearingAccess.addPreset(1U, "Universal") != Error::none) ||
        (hearingAccess.addPreset(5U, "Outdoor") != Error::none) ||
        (hearingAccess.addPreset(8U, "Noisy room") != Error::none) ||
        (hearingAccess.setActivePreset(1U) != Error::none) || !startAdvertising())
    {
        Serial.print("Hearing Access server start failed native=");
        Serial.println(hearingAccess.nativeCode());
        return;
    }
    Serial.println("Commands: 1/5/8=select n=rename 8 a=toggle 5 s=state");
    printPresets();
}

/** @brief BLE event와 사용자가 선택한 preset 변경을 처리합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();

    if (restartAdvertising && !BLEAdvertising.running() &&
        (static_cast<std::int32_t>(millis() - restartAt) >= 0))
    {
        if (startAdvertising())
        {
            restartAdvertising = false;
            Serial.println("Hearing Access advertising restarted");
        }
        else
        {
            restartAt = millis() + 1000U;
        }
    }

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if ((command == '1') || (command == '5') || (command == '8'))
        {
            report("Select preset",
                   hearingAccess.setActivePreset(static_cast<std::uint8_t>(command - '0')));
        }
        else if (command == 'n')
        {
            report("Rename preset", hearingAccess.renamePreset(8U, "Conversation"));
        }
        else if (command == 'a')
        {
            HearingPreset preset;
            bool available = false;
            for (std::size_t position = 0U; position < hearingAccess.presetCount(); ++position)
            {
                if ((hearingAccess.preset(position, preset) == Error::none) && (preset.index == 5U))
                {
                    available = preset.available;
                    break;
                }
            }
            report("Toggle preset availability", hearingAccess.setPresetAvailable(5U, !available));
        }
        else if (command == 's')
        {
            printPresets();
        }
    }

    static std::uint32_t changes = 0U;
    if (changes != hearingAccess.selectionChanges())
    {
        changes = hearingAccess.selectionChanges();
        printPresets();
    }
    delay(1U);
}
