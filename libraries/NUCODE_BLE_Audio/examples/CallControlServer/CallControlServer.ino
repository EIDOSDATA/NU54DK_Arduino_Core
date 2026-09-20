/**
 * @file CallControlServer.ino
 * @brief 합성 통화를 Generic Telephone Bearer Service로 제공하는 예제입니다.
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
using nucode::ble::audio::CallControlServer;
using nucode::ble::audio::Error;

namespace
{
    CallControlServer callServer;
    bool restartAdvertising = false;
    std::uint32_t restartAt = 0U;

    /** @brief GTBS UUID와 전체 장치 이름을 광고합니다. */
    bool startAdvertising()
    {
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.addServiceUuid(BLEUuid(0x184CU)) &&
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

    /** @brief call controller 연결 해제 뒤 광고 재시작을 예약합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            Serial.println("Call controller connected");
        }
        else if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            restartAt = millis() + 100U;
            Serial.print("Call controller disconnected reason=");
            Serial.println(event.reason);
        }
    }

    /** @brief 현재 call index/state/result를 출력합니다. */
    void printState()
    {
        const auto state = callServer.snapshot();
        Serial.print("call index=");
        Serial.print(state.call_index);
        Serial.print(" state=");
        Serial.print(static_cast<unsigned int>(state.state));
        Serial.print(" result=");
        Serial.print(state.result_code);
        Serial.print(" updates=");
        Serial.println(state.updates);
    }

    /** @brief 공개 call server 요청 결과를 출력합니다. */
    void report(const char *operation, Error result)
    {
        Serial.print(operation);
        Serial.print(" result=");
        Serial.print(static_cast<unsigned int>(result));
        Serial.print(" native=");
        Serial.println(callServer.nativeCode());
    }
} // namespace

/** @brief security와 GTBS를 광고 전에 준비합니다. */
void setup()
{
    Serial.begin(115200);
    SecurityConfig security;
    security.minimum_level = SecurityLevel::encrypted;
    security.bonding = false;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-CALL-SERVER") ||
        (callServer.begin("NUCODE Voice", "tel") != Error::none) || !startAdvertising())
    {
        Serial.print("Call server start failed native=");
        Serial.println(callServer.nativeCode());
        return;
    }
    Serial.println("Commands: i=incoming a=remote answer h=remote hold r=remote retrieve x=remote "
                   "end s=state");
}

/** @brief BLE lifecycle과 합성 telephone network 상태 명령을 처리합니다. */
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
        }
        else
        {
            restartAt = millis() + 1000U;
        }
    }
    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        const std::uint8_t callIndex = callServer.snapshot().call_index;
        if (command == 'i')
        {
            report("CALL_INCOMING", callServer.incoming("tel:1000", "tel:2000", "Synthetic peer"));
        }
        else if (command == 'a')
        {
            report("CALL_REMOTE_ANSWER", callServer.remoteAnswer(callIndex));
        }
        else if (command == 'h')
        {
            report("CALL_REMOTE_HOLD", callServer.remoteHold(callIndex));
        }
        else if (command == 'r')
        {
            report("CALL_REMOTE_RETRIEVE", callServer.remoteRetrieve(callIndex));
        }
        else if (command == 'x')
        {
            report("CALL_REMOTE_TERMINATE", callServer.remoteTerminate(callIndex));
        }
        else if (command == 's')
        {
            printState();
        }
    }
    static std::uint32_t updates = 0U;
    if (updates != callServer.snapshot().updates)
    {
        updates = callServer.snapshot().updates;
        printState();
    }
    delay(1U);
}
