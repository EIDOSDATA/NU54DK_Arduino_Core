/**
 * @file BapBroadcastAssistant.ino
 * @brief BASS Scan Delegator에 broadcast source를 추가하고 상태를 확인합니다.
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
using nucode::ble::audio::BroadcastAssistant;
using nucode::ble::audio::BroadcastAssistantStage;
using nucode::ble::audio::BroadcastAssistantStep;
using nucode::ble::audio::BroadcastCode;
using nucode::ble::audio::Error;

namespace
{
    enum class ScanTarget : std::uint8_t
    {
        delegator,
        source,
        none,
    };

    constexpr BroadcastCode broadcastCode = {
        0x4e, 0x55, 0x35, 0x34, 0x2d, 0x41, 0x55, 0x44,
        0x49, 0x4f, 0x2d, 0x43, 0x4f, 0x44, 0x45, 0x31,
    };
    BroadcastAssistant assistant;
    BLEAddress delegatorAddress;
    BLEConnectionHandle delegatorConnection;
    ScanTarget scanTarget = ScanTarget::delegator;
    BroadcastAssistantStage previousStage = BroadcastAssistantStage::idle;
    bool delegatorFound = false;
    bool sourceSelected = false;
    bool sourceScanStarted = false;
    bool addPending = false;
    bool codePending = false;
    bool assistantStarted = false;
    bool delegatorScanPending = false;
    std::uint32_t delegatorScanAt = 0U;

    /** @brief BASS service를 광고하는 Scan Delegator 검색을 시작합니다. */
    bool startDelegatorScan()
    {
        scanTarget = ScanTarget::delegator;
        return BLEScan.clearFilters() &&
               BLEScan.filterServiceUuid(BLEUuid(0x184FU)) &&
               BLEScan.start(true);
    }

    /** @brief 현재 검색 단계에 맞는 Delegator 또는 Broadcast Source를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if ((scanTarget == ScanTarget::delegator) && result.connectable)
        {
            delegatorAddress = result.address;
            delegatorFound = true;
            scanTarget = ScanTarget::none;
            static_cast<void>(BLEScan.stop());
            Serial.println("broadcast delegator found");
        }
        else if ((scanTarget == ScanTarget::source) && !result.connectable &&
                 (assistant.selectSource(result) == Error::none))
        {
            sourceSelected = true;
            addPending = true;
            scanTarget = ScanTarget::none;
            static_cast<void>(BLEScan.stop());
            Serial.println("broadcast source selected");
        }
    }

    /** @brief encrypted 연결이 준비되면 BASS 검색을 시작합니다. */
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
                 (event.connection == delegatorConnection) && !assistantStarted)
        {
            const Error result = assistant.begin(delegatorConnection);
            if (result == Error::none)
            {
                assistantStarted = true;
                Serial.println("BASS discovery started");
            }
            else
            {
                Serial.print("BASS discovery start failed: ");
                Serial.println(assistant.nativeCode());
            }
        }
    }

    /** @brief BLE link 수명에 security와 Assistant 수명을 결합합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) &&
            (event.role == BLELinkRole::central))
        {
            delegatorConnection = event.connection;
            if (!BLESecurity.requestSecurity(delegatorConnection))
            {
                Serial.println("delegator security request failed");
            }
        }
        else if ((event.event == BLEEvent::disconnected) &&
                 (event.connection == delegatorConnection))
        {
            if (assistantStarted)
            {
                static_cast<void>(assistant.end());
            }
            assistantStarted = false;
            delegatorConnection = BLEConnectionHandle();
            delegatorFound = false;
            sourceSelected = false;
            sourceScanStarted = false;
            addPending = false;
            codePending = false;
            delegatorScanPending = true;
            delegatorScanAt = millis() + 100U;
            Serial.print("broadcast delegator disconnected reason=");
            Serial.println(event.reason);
        }
    }

    /** @brief operation 시작 결과와 원본 오류를 한 형식으로 출력합니다. */
    void reportRequest(const char *name, Error result)
    {
        Serial.print(name);
        Serial.print(": ");
        Serial.print(static_cast<unsigned int>(result));
        Serial.print(" native=");
        Serial.println(assistant.nativeCode());
    }
} // namespace

/** @brief security와 공개 BLE 검색을 시작합니다. */
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
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-AUDIO-ASSISTANT") ||
        !startDelegatorScan())
    {
        Serial.println("broadcast assistant start failed");
    }
}

/** @brief BASS add/code/modify/remove 명령과 receive state 변화를 진행합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();

    if (delegatorScanPending && !BLEConnection.connected() &&
        !BLEConnection.connecting() &&
        (static_cast<std::int32_t>(millis() - delegatorScanAt) >= 0))
    {
        if (startDelegatorScan())
        {
            delegatorScanPending = false;
            Serial.println("broadcast delegator scan restarted");
        }
        else
        {
            delegatorScanAt = millis() + 1000U;
            Serial.println("broadcast delegator scan restart failed");
        }
    }

    if (delegatorFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        delegatorFound = false;
        if (!BLEConnection.connect(delegatorAddress, delegatorConnection))
        {
            Serial.println("broadcast delegator connect failed");
        }
    }

    const BroadcastAssistantStage stage = assistant.stage();
    if (stage != previousStage)
    {
        previousStage = stage;
        Serial.print("assistant stage=");
        Serial.print(static_cast<unsigned int>(stage));
        Serial.print(" step=");
        Serial.print(static_cast<unsigned int>(assistant.lastStep()));
        Serial.print(" native=");
        Serial.println(assistant.nativeCode());
    }
    if (assistantStarted && (stage == BroadcastAssistantStage::ready) &&
        !sourceScanStarted && !sourceSelected)
    {
        sourceScanStarted = true;
        scanTarget = ScanTarget::source;
        if (!BLEScan.clearFilters() || !BLEScan.startExtended(false, false, false))
        {
            Serial.println("broadcast source scan failed");
        }
        else
        {
            Serial.println("broadcast source scan started");
        }
    }
    if (addPending && (stage == BroadcastAssistantStage::ready))
    {
        addPending = false;
        reportRequest("BASS add source", assistant.addSource());
    }
    if (assistant.hasSource() && !codePending &&
        (stage == BroadcastAssistantStage::ready))
    {
        codePending = true;
        reportRequest("BASS broadcast code", assistant.setBroadcastCode(broadcastCode));
    }

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 'a')
        {
            reportRequest("BASS duplicate add", assistant.addSource());
        }
        else if (command == 'm')
        {
            reportRequest("BASS stop source", assistant.modifySource(false));
        }
        else if (command == 'r')
        {
            if (assistant.hasSource())
            {
                reportRequest("BASS resume source", assistant.modifySource(true));
            }
            else
            {
                reportRequest("BASS re-add source", assistant.addSource());
                codePending = false;
            }
        }
        else if (command == 'd')
        {
            reportRequest("BASS remove source", assistant.removeSource());
            codePending = false;
        }
        else if (command == 'x')
        {
            BLEScanResult invalidSource;
            reportRequest("BASS invalid source", assistant.selectSource(invalidSource));
        }
    }

    static std::uint32_t reportedUpdates = 0U;
    if (assistant.stateUpdates() != reportedUpdates)
    {
        reportedUpdates = assistant.stateUpdates();
        Serial.print("receive state update=");
        Serial.print(reportedUpdates);
        Serial.print(" source=");
        Serial.print(assistant.hasSource() ? assistant.sourceId() : 255U);
        Serial.print(" pa=");
        Serial.print(assistant.periodicSynchronized() ? 1 : 0);
        Serial.print(" bis=");
        Serial.println(assistant.bisSynchronized() ? 1 : 0);
    }
    delay(1U);
}
