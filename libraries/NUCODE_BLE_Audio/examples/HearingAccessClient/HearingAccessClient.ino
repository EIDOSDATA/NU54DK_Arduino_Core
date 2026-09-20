/**
 * @file HearingAccessClient.ino
 * @brief 원격 Hearing Access preset을 읽고 선택하는 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_BLE_Security.h>

using nucode::ble::BLEAddress;
using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLELinkRole;
using nucode::ble::BLEScanResult;
using nucode::ble::BLEUuid;
using nucode::ble::SecurityConfig;
using nucode::ble::SecurityEvent;
using nucode::ble::SecurityEventRecord;
using nucode::ble::SecurityIoCapability;
using nucode::ble::SecurityLevel;
using nucode::ble::audio::Error;
using nucode::ble::audio::HearingAccessClient;
using nucode::ble::audio::HearingAccessStage;
using nucode::ble::audio::HearingPreset;

namespace
{
    HearingAccessClient hearingAccess;
    BLEAddress peerAddress;
    BLEConnectionHandle peerConnection;
    bool peerFound = false;
    bool profileStarted = false;
    bool presetsRequested = false;
    bool scanPending = false;
    std::uint32_t scanAt = 0U;
    std::uint32_t profileDeadline = 0U;
    constexpr std::uint32_t profileTimeoutMs = 10000U;

    /** @brief Hearing Access Service UUID를 광고하는 장치를 검색합니다. */
    bool startScan()
    {
        return BLEScan.clearFilters() && BLEScan.filterServiceUuid(BLEUuid(0x1854U)) &&
               BLEScan.start(true);
    }

    /** @brief 처음 발견한 connectable Hearing Access server를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            static_cast<void>(BLEScan.stop());
            Serial.println("Hearing Access server found");
        }
    }

    /** @brief 암호화 완료 뒤 HAS discovery를 시작합니다. */
    void onSecurityEvent(const SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == SecurityEvent::pairing_requested)
        {
            static_cast<void>(BLESecurity.acceptPairing(event.connection, true));
        }
        else if (((event.event == SecurityEvent::paired) ||
                  (event.event == SecurityEvent::bond_verified) ||
                  (event.event == SecurityEvent::security_changed)) &&
                 (event.connection == peerConnection) && !profileStarted)
        {
            const Error result = hearingAccess.begin(peerConnection);
            if (result == Error::none)
            {
                profileStarted = true;
                profileDeadline = millis() + profileTimeoutMs;
                Serial.println("Hearing Access discovery started");
            }
            else
            {
                Serial.print("Hearing Access discovery failed native=");
                Serial.println(hearingAccess.nativeCode());
            }
        }
    }

    /** @brief 연결과 profile 수명을 결합하고 해제 뒤 재검색합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) && (event.role == BLELinkRole::central))
        {
            peerConnection = event.connection;
            if (!BLESecurity.requestSecurity(peerConnection))
            {
                Serial.println("Hearing Access security request failed");
            }
        }
        else if ((event.event == BLEEvent::disconnected) && (event.connection == peerConnection))
        {
            if (profileStarted)
            {
                static_cast<void>(hearingAccess.end());
            }
            peerConnection = BLEConnectionHandle();
            peerFound = false;
            profileStarted = false;
            presetsRequested = false;
            scanPending = true;
            scanAt = millis() + 100U;
            Serial.print("Hearing Access server disconnected reason=");
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

    /** @brief 원격 preset cache와 active index를 출력합니다. */
    void printPresets()
    {
        Serial.print("active=");
        Serial.print(hearingAccess.activePreset());
        Serial.print(" presets=");
        Serial.println(hearingAccess.presetCount());
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

/** @brief central, security와 Hearing Access 검색을 시작합니다. */
void setup()
{
    Serial.begin(115200);

    SecurityConfig security;
    security.minimum_level = SecurityLevel::encrypted;
    security.bonding = false;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-HEARING-REMOTE") || !startScan())
    {
        Serial.println("Hearing Access client start failed");
    }
    Serial.println("Commands: 1/5/8=select n=next p=previous r=read x=invalid y=sync s=state");
}

/** @brief discovery와 사용자가 선택한 원격 preset 절차를 진행합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    hearingAccess.poll();

    if (scanPending && !BLEConnection.connected() && !BLEConnection.connecting() &&
        (static_cast<std::int32_t>(millis() - scanAt) >= 0))
    {
        if (startScan())
        {
            scanPending = false;
        }
        else
        {
            scanAt = millis() + 1000U;
        }
    }
    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress, peerConnection))
        {
            scanPending = true;
            scanAt = millis() + 1000U;
            Serial.println("Hearing Access connect failed");
        }
    }

    if (profileStarted && hearingAccess.ready() && !presetsRequested)
    {
        const Error result = hearingAccess.readPresets();
        report("Read presets", result);
        presetsRequested = result == Error::none;
    }
    if (profileStarted && !hearingAccess.ready() &&
        (static_cast<std::int32_t>(millis() - profileDeadline) >= 0) &&
        (hearingAccess.stage() != HearingAccessStage::operating))
    {
        Serial.print("Hearing Access profile timeout stage=");
        Serial.print(static_cast<unsigned int>(hearingAccess.stage()));
        Serial.print(" native=");
        Serial.println(hearingAccess.nativeCode());
        profileDeadline = millis() + profileTimeoutMs;
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
            report("Next preset", hearingAccess.nextPreset());
        }
        else if (command == 'p')
        {
            report("Previous preset", hearingAccess.previousPreset());
        }
        else if (command == 'r')
        {
            report("Read presets", hearingAccess.readPresets());
        }
        else if (command == 'x')
        {
            report("Invalid preset", hearingAccess.setActivePreset(0U));
        }
        else if (command == 'y')
        {
            report("Synchronized preset", hearingAccess.setActivePreset(5U, true));
        }
        else if (command == 's')
        {
            printPresets();
        }
    }

    static HearingAccessStage previousStage = HearingAccessStage::idle;
    const HearingAccessStage currentStage = hearingAccess.stage();
    if ((currentStage == HearingAccessStage::failed) && (currentStage != previousStage))
    {
        Serial.print("Hearing Access operation rejected step=");
        Serial.print(static_cast<unsigned int>(hearingAccess.lastStep()));
        Serial.print(" error=");
        Serial.print(static_cast<unsigned int>(hearingAccess.lastError()));
        Serial.print(" native=");
        Serial.println(hearingAccess.nativeCode());
    }
    previousStage = currentStage;

    static std::uint32_t updates = 0U;
    if (updates != hearingAccess.stateUpdates())
    {
        updates = hearingAccess.stateUpdates();
        printPresets();
    }
    delay(1U);
}
