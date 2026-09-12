/**
 * @file PerLinkControl.ino
 * @brief generation handle마다 PHY·DLE·parameter·remote-info를 분리하는 예제입니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEConnectionHandle centralLink;
nucode::ble::BLEConnectionHandle peripheralLink;

/** @brief 새 link의 역할별 handle을 보존하고 독립적인 제어 요청을 제출합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        if (information.role == nucode::ble::BLELinkRole::central)
        {
            centralLink = information.connection;
        }
        else if (information.role == nucode::ble::BLELinkRole::peripheral)
        {
            peripheralLink = information.connection;
        }
        const bool phyRequested = BLEConnection.requestPhy(information.connection, true);
        const bool dataLengthRequested =
            BLEConnection.requestDataLength(information.connection);
        const bool parametersRequested =
            BLEConnection.requestParameters(information.connection, 24U, 40U, 0U, 400U);
        if (!phyRequested || !dataLengthRequested || !parametersRequested)
        {
            Serial.println("per-link control request failed");
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
    else if (information.event == nucode::ble::BLEEvent::remote_information_available)
    {
        nucode::ble::BLERemoteInformation remote{};
        if (BLEConnection.remoteInformation(information.connection, remote))
        {
            Serial.print("Remote LL version: ");
            Serial.println(remote.version);
        }
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-LINK-CTRL") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEAdvertising.start())
    {
        Serial.println("per-link control setup failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
