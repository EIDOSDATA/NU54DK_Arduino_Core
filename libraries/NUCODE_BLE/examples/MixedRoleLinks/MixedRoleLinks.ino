/**
 * @file MixedRoleLinks.ino
 * @brief 한 NU54DK가 central 1-link와 peripheral 1-link를 동시에 유지하는 예제입니다.
 *
 * Central peer는 `NU54-GAP-P`로 광고해야 하며, 세 번째 peer는 `NU54-MIXED`에 연결합니다.
 * 도구 → Feature set → BLE NUS를 선택해야 합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAddress centralPeerAddress;
nucode::ble::BLEConnectionHandle centralLink;
nucode::ble::BLEConnectionHandle peripheralLink;
bool centralPeerFound = false;
bool startPeripheralAdvertising = false;

/** @brief exact-name scan 결과에서 central 역할로 연결할 주소를 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (!centralPeerFound)
    {
        centralPeerAddress = result.address;
        centralPeerFound = true;
    }
}

/** @brief link별 generation handle과 local 역할을 main thread에서 보존합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        if (information.role == nucode::ble::BLELinkRole::central)
        {
            centralLink = information.connection;
            startPeripheralAdvertising = true;
        }
        else if (information.role == nucode::ble::BLELinkRole::peripheral)
        {
            peripheralLink = information.connection;
        }
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected)
    {
        if (information.connection == centralLink)
        {
            centralLink = nucode::ble::BLEConnectionHandle{};
        }
        if (information.connection == peripheralLink)
        {
            peripheralLink = nucode::ble::BLEConnectionHandle{};
        }
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-MIXED") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEScan.clearFilters() ||
        !BLEScan.filterName("NU54-GAP-P") || !BLEScan.start(true))
    {
        Serial.println("mixed-role setup failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (centralPeerFound && !centralLink.valid())
    {
        centralPeerFound = false;
        if (!BLEConnection.connect(centralPeerAddress, centralLink))
        {
            Serial.println("central connect failed");
        }
    }
    if (startPeripheralAdvertising && BLEConnection.connected(centralLink))
    {
        startPeripheralAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("peripheral advertising failed");
        }
    }
}
