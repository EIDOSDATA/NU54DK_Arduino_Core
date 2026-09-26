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
 * Initiator와 함께 사용하며 거리 결과는 Initiator Serial에서 확인합니다.
 * @par Metadata
 * identity `NUCODE_BLE_ChannelSounding/RasReflector`, sha256 `705e67eea52bd009febb87f2ac9232fbf84107f77c03d304482bb2bcddaab85b`
 * @nucode_example_setup_end */

/**
 * @file RasReflector.ino
 * @brief 보안 BLE 연결에서 Ranging Service와 CS reflector를 실행합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_ChannelSounding.h>

using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::cs::Error;
using nucode::ble::cs::RasReflector;

namespace
{
    RasReflector reflector;
    BLEConnectionHandle peer;
    bool restartAdvertising = false;
    bool wasSecure = false;
    bool wasReady = false;
    bool wasActive = false;

    /** @brief 연결 상태 변화를 공개 API로 reflector에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            peer = event.connection;
            const Error result = reflector.begin(peer);
            if (result == Error::none)
            {
                Serial.println("CS reflector connected");
            }
            else
            {
                Serial.print("CS reflector begin failed: ");
                Serial.println(reflector.nativeCode());
            }
        }
        else if ((event.event == BLEEvent::disconnected) &&
                 (event.connection == peer))
        {
            reflector.end();
            peer = BLEConnectionHandle();
            restartAdvertising = true;
            wasSecure = false;
            wasReady = false;
            wasActive = false;
            Serial.println("CS reflector disconnected");
        }
    }
}

/** @brief Ranging Service UUID와 연결 가능한 광고를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-CS-RSP") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x185BU)) ||
        !BLEAdvertising.start())
    {
        Serial.println("CS reflector advertising failed");
        return;
    }
    Serial.println("CS reflector advertising");
}

/** @brief CS 설정 완료와 보안·절차 상태를 Arduino 문맥에서 관찰합니다. */
void loop()
{
    BLEDevice.poll();
    reflector.poll();

    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("CS reflector advertising restart failed");
        }
    }

    if (peer.valid())
    {
        const bool secure = reflector.secure();
        const bool ready = reflector.ready();
        const bool active = reflector.active();
        if (secure && !wasSecure)
        {
            Serial.println("CS reflector secure L2");
        }
        if (ready && !wasReady)
        {
            Serial.println("CS reflector config ready");
        }
        if (active != wasActive)
        {
            Serial.println(active ? "CS procedures enabled" :
                                   "CS procedures disabled");
        }
        wasSecure = secure;
        wasReady = ready;
        wasActive = active;
    }

    if (reflector.lastError() == Error::controller_error)
    {
        Serial.print("CS reflector controller error: ");
        Serial.println(reflector.nativeCode());
        reflector.end();
    }
    delay(1);
}
