/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) RasInitiator (initiator); 2) RasReflector (reflector)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * Reflector를 먼저 켜고 두 보드의 보안 peer 상태를 맞춥니다.
 * @par Metadata
 * identity `NUCODE_BLE_ChannelSounding/RasInitiator`, sha256 `01776401708fbed8ef04098be6b913abe607770692f900287e7b09e633ad4e88`
 * @nucode_example_setup_end */

/**
 * @file RasInitiator.ino
 * @brief 보안 연결의 Ranging Service를 찾아 CS raw step을 수집합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_ChannelSounding.h>

using nucode::ble::BLEAddress;
using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEScanResult;
using nucode::ble::BLEUuid;
using nucode::ble::cs::Error;
using nucode::ble::cs::InitiatorStage;
using nucode::ble::cs::RasInitiator;
using nucode::ble::cs::RasReading;

namespace
{
    RasInitiator initiator;
    BLEAddress peerAddress;
    BLEConnectionHandle peer;
    bool peerFound = false;
    bool restartScan = false;
    bool started = false;
    bool reportedFailure = false;

    /** @brief Ranging Service를 광고하는 연결 가능한 reflector를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            if (!BLEScan.stop())
            {
                Serial.println("CS scan stop failed");
            }
        }
    }

    /** @brief BLE 연결 수명을 Ranging Requestor에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) &&
            (event.role == nucode::ble::BLELinkRole::central))
        {
            peer = event.connection;
            const Error result = initiator.begin(peer);
            if (result == Error::none)
            {
                Serial.println("CS initiator connected; securing");
            }
            else
            {
                Serial.print("CS initiator begin failed: ");
                Serial.println(initiator.nativeCode());
            }
        }
        else if ((event.event == BLEEvent::disconnected) &&
                 (event.connection == peer))
        {
            initiator.end();
            peer = BLEConnectionHandle();
            peerFound = false;
            restartScan = true;
            started = false;
            reportedFailure = false;
            Serial.println("CS initiator disconnected");
        }
    }
}

/** @brief 공개 BLE scan과 연결 event를 설정합니다. */
void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScanResult);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-CS-INIT") || !BLEScan.clearFilters() ||
        !BLEScan.filterServiceUuid(BLEUuid(0x185BU)) || !BLEScan.start(true))
    {
        Serial.println("CS initiator scan failed");
    }
}

/** @brief CS 보안·GATT·controller 단계를 진행하고 raw 결과를 출력합니다. */
void loop()
{
    BLEDevice.poll();
    initiator.poll();

    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress))
        {
            restartScan = true;
            Serial.println("CS initiator connect failed");
        }
    }
    if (restartScan && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        restartScan = false;
        if (!BLEScan.start(true))
        {
            Serial.println("CS initiator scan restart failed");
        }
    }

    if ((initiator.stage() == InitiatorStage::ready) && !started)
    {
        if (initiator.start() == Error::none)
        {
            started = true;
            Serial.println("CS procedures requested");
        }
    }
    if ((initiator.stage() == InitiatorStage::failed) && !reportedFailure)
    {
        reportedFailure = true;
        Serial.print("CS initiator failed: ");
        Serial.println(initiator.nativeCode());
    }

    RasReading reading;
    while (initiator.read(reading))
    {
        Serial.print("CS_RAW counter=");
        Serial.print(reading.ranging_counter);
        Serial.print(" local=");
        Serial.print(reading.local_steps);
        Serial.print(" peer=");
        Serial.print(reading.peer_steps);
        Serial.print(" rtt=");
        Serial.print(reading.mode_1_steps);
        Serial.print(" tone=");
        Serial.print(reading.mode_2_steps);
        Serial.print(" valid_rtt=");
        Serial.print(reading.valid_rtt_samples);
        if (reading.valid_rtt_samples > 0U)
        {
            Serial.print(" distance_m=");
            Serial.print(reading.rtt_distance_meters, 3);
        }
        Serial.println();
    }

    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if ((command == 's') && (initiator.stage() == InitiatorStage::ranging))
        {
            if (initiator.stop() == Error::none)
            {
                Serial.println("CS procedures stop requested");
            }
        }
        else if ((command == 'r') && (initiator.stage() == InitiatorStage::ready))
        {
            if (initiator.start() == Error::none)
            {
                Serial.println("CS procedures restart requested");
            }
        }
        else if ((command == 'd') && peer.valid())
        {
            if (BLEConnection.disconnect(peer))
            {
                Serial.println("CS disconnect requested");
            }
            else
            {
                Serial.println("CS disconnect failed");
            }
        }
    }
    delay(1);
}
