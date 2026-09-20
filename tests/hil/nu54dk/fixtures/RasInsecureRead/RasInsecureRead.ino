/**
 * @file RasInsecureRead.ino
 * @brief 암호화되지 않은 연결에서 Ranging Features 읽기 거부를 확인합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>

using nucode::ble::BLEAddress;
using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEGattClientEvent;
using nucode::ble::BLEGattClientEventInfo;
using nucode::ble::BLEScanResult;
using nucode::ble::BLEUuid;

namespace
{
    BLEAddress peerAddress;
    BLEConnectionHandle peer;
    bool peerFound = false;
    bool discoveryPending = false;
    bool readPending = false;
    bool readInFlight = false;
    bool done = false;
    unsigned int rejected = 0U;

    /** @brief 광고된 Ranging UUID를 기준으로 peer를 고릅니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            (void)BLEScan.stop();
        }
    }

    /** @brief 암호화를 요청하지 않고 GATT 탐색만 예약합니다. */
    void onBleEvent(const BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if ((information.event == BLEEvent::connected) &&
            (information.role == nucode::ble::BLELinkRole::central))
        {
            peer = information.connection;
            discoveryPending = true;
            Serial.println("CS insecure peer connected");
        }
        else if ((information.event == BLEEvent::disconnected) &&
                 (information.connection == peer))
        {
            done = true;
            Serial.println("CS insecure peer disconnected");
        }
    }

    /** @brief 실제 ATT 오류와 읽기 성공 여부를 별도로 출력합니다. */
    void onClientEvent(const BLEGattClientEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.connection != peer)
        {
            return;
        }
        if (information.event == BLEGattClientEvent::discovery_complete)
        {
            readPending = true;
            Serial.println("CS insecure RAS discovered");
        }
        else if (information.event == BLEGattClientEvent::read_complete)
        {
            readInFlight = false;
            done = true;
            Serial.println("CS insecure read ACCEPTED");
        }
        else if (information.event == BLEGattClientEvent::operation_failed)
        {
            if (!readInFlight)
            {
                done = true;
                Serial.print("CS insecure discovery failed att=");
                Serial.println(information.att_error);
                return;
            }
            readInFlight = false;
            if (information.att_error != 15U)
            {
                done = true;
                Serial.print("CS insecure unexpected att=");
                Serial.println(information.att_error);
                return;
            }
            ++rejected;
            Serial.print("CS insecure read rejected att=15 count=");
            Serial.println(rejected);
            done = true;
        }
    }
}

/** @brief SMP 없이 연결 가능한 Ranging Service 광고만 찾습니다. */
void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScanResult);
    BLEDevice.onEventInfo(onBleEvent);
    BLEClient.onDetailedEvent(onClientEvent);
    if (!BLEDevice.begin("NU54-CS-UNAUTH") || !BLEScan.clearFilters() ||
        !BLEScan.filterServiceUuid(BLEUuid(0x185BU)) || !BLEScan.start(true))
    {
        Serial.println("CS insecure scan failed");
    }
}

/** @brief 공개 GATT API로 Ranging Features를 한 번 읽어 봅니다. */
void loop()
{
    BLEDevice.poll();
    if (done)
    {
        delay(1);
        return;
    }
    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress))
        {
            done = true;
            Serial.println("CS insecure connect failed");
        }
    }
    if (discoveryPending && peer.valid())
    {
        discoveryPending = false;
        if (!BLEClient.discover(peer, BLEUuid(0x185BU), BLEUuid(0x2C14U)))
        {
            done = true;
            Serial.println("CS insecure discovery start failed");
        }
    }
    if (readPending && !BLEClient.busy(peer))
    {
        readPending = false;
        if (BLEClient.read(peer))
        {
            readInFlight = true;
        }
        else
        {
            done = true;
            Serial.println("CS insecure read start failed");
        }
    }
    delay(1);
}
