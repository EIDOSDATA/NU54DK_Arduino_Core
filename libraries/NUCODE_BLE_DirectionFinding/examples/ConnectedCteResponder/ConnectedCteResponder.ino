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
