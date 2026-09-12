/**
 * @file PastReceiver.ino
 * @brief 연결된 peer가 전달하는 PAST sync를 받고 periodic report를 출력합니다.
 *
 * `PeriodicAdvertiser`와 `PastSender`를 각각 다른 보드에서 실행합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEConnectionHandle senderLink;
nucode::ble::BLEPeriodicSyncHandle transferredSync;
bool restartAdvertising = false;

/** @brief PAST 구독과 전달된 sync handle을 link별 event에서 처리합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected &&
        information.role == nucode::ble::BLELinkRole::peripheral)
    {
        senderLink = information.connection;
        if (!BLEPeriodicAdvertising.subscribeTransfers(senderLink))
        {
            Serial.println("PAST subscription failed");
        }
    }
    else if (information.event == nucode::ble::BLEEvent::periodic_sync_synchronized)
    {
        transferredSync = information.periodic_sync;
        Serial.println("PAST sync received");
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected &&
             information.connection == senderLink)
    {
        senderLink = nucode::ble::BLEConnectionHandle{};
        restartAdvertising = true;
    }
}

/** @brief 전달받은 sync의 bounded periodic report 길이를 출력합니다. */
void onPeriodicReport(const nucode::ble::BLEPeriodicReport &report, void *context)
{
    static_cast<void>(context);
    if (report.sync == transferredSync)
    {
        Serial.print("PAST periodic bytes=");
        Serial.println(report.payload_length);
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEPeriodicAdvertising.onReport(onPeriodicReport);
    if (!BLEDevice.begin("NU54-PAST-RX") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEAdvertising.start())
    {
        Serial.println("PAST receiver setup failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected(senderLink))
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("PAST receiver advertising restart failed");
        }
    }
}
