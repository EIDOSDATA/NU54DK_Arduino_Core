/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 1대 — 1) ConnectedCteResponder (responder)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * app.overlay, nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 제품 SDC의 IQ RX·AoD는 지원하지 않으며 외부 compatible peer 조건을 확인합니다.
 * @par Metadata
 * identity `NUCODE_BLE_DirectionFinding/ConnectedCteResponder`, sha256 `f3037685d5072b1747fe557a3aad874fada0630a3005af36dfda3a7898e140ac`
 * @nucode_example_setup_end */

/**
 * @file ConnectedCteResponder.ino
 * @brief 연결된 peer의 AoA CTE 요청에 기본 안테나로 응답합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_DirectionFinding.h>

using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::df::ConnectedResponder;
using nucode::ble::df::Error;

namespace
{
    ConnectedResponder responder;
    BLEConnectionHandle peer;
    bool restartAdvertising = false;

    /** @brief 공개 오류와 원본 controller 코드를 함께 보여 줍니다. */
    void printError(const char *operation, Error error)
    {
        Serial.print("CTE responder ");
        Serial.print(operation);
        Serial.print(" failed: ");
        Serial.print(static_cast<unsigned int>(error));
        Serial.print(" native=");
        Serial.println(responder.nativeCode());
    }

    /** @brief 연결마다 응답기를 준비하고 끊어진 연결의 상태를 반환합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            peer = event.connection;
            const Error prepared = responder.begin(peer);
            if (prepared != Error::none)
            {
                printError("begin", prepared);
                return;
            }
            const Error started = responder.start();
            if (started != Error::none)
            {
                printError("start", started);
                responder.end();
                return;
            }
            Serial.println("CTE responses enabled on connected peer");
        }
        else if ((event.event == BLEEvent::disconnected) &&
                 (event.connection == peer))
        {
            responder.end();
            peer = BLEConnectionHandle();
            restartAdvertising = true;
            Serial.println("CTE peer disconnected");
        }
    }
}

/** @brief 연결 가능한 BLE 광고와 공개 연결 event를 준비합니다. */
void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-CTE-RSP") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.setInterval(0x00a0U, 0x00f0U) ||
        !BLEAdvertising.start())
    {
        Serial.println("CTE responder advertising failed");
    }
}

/** @brief 연결 event와 사용자가 요청한 응답 중단·재시작을 처리합니다. */
void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("CTE responder advertising restart failed");
        }
    }

    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if ((command == 's') && responder.active())
        {
            const Error stopped = responder.stop();
            if (stopped == Error::none)
            {
                Serial.println("CTE responses stopped");
            }
            else
            {
                printError("stop", stopped);
            }
        }
        else if ((command == 'r') && peer.valid() && !responder.active())
        {
            const Error started = responder.start();
            if (started == Error::none)
            {
                Serial.println("CTE responses restarted");
            }
            else
            {
                printError("restart", started);
            }
        }
    }
    delay(1);
}
