/**
 * @file PastSender.ino
 * @brief Periodic source를 동기화한 뒤 연결된 receiver에 PAST로 전달합니다.
 *
 * `PeriodicAdvertiser`와 `PastReceiver`를 각각 다른 보드에서 먼저 실행합니다.
 */

#include <NUCODE_BLE.h>

enum class SenderPhase : uint8_t
{
    findSource,
    createSync,
    waitSync,
    findReceiver,
    connectReceiver,
    waitConnection,
    transfer,
    complete,
};

SenderPhase phase = SenderPhase::findSource;
nucode::ble::BLEAddress sourceAddress;
nucode::ble::BLEAddress receiverAddress;
nucode::ble::BLEPeriodicSyncHandle periodicSync;
nucode::ble::BLEConnectionHandle receiverLink;
uint8_t sourceSid = 0U;

/** @brief 현재 단계에 맞는 source 또는 receiver 주소만 보존합니다. */
void onScan(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (phase == SenderPhase::findSource && result.extended &&
        result.periodic_interval != 0U)
    {
        sourceAddress = result.address;
        sourceSid = result.sid;
        phase = SenderPhase::createSync;
    }
    else if (phase == SenderPhase::findReceiver)
    {
        receiverAddress = result.address;
        phase = SenderPhase::connectReceiver;
    }
}

/** @brief receiver link의 generation handle을 연결 수명에 맞춰 보존합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected &&
        information.role == nucode::ble::BLELinkRole::central)
    {
        receiverLink = information.connection;
        phase = SenderPhase::transfer;
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected &&
             information.connection == receiverLink)
    {
        receiverLink = nucode::ble::BLEConnectionHandle{};
        phase = SenderPhase::complete;
        Serial.println("PAST receiver disconnected");
    }
}

void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScan);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-PAST-TX") || !BLEScan.startExtended(false))
    {
        Serial.println("PAST sender setup failed");
        phase = SenderPhase::complete;
    }
}

void loop()
{
    BLEDevice.poll();
    if (phase == SenderPhase::createSync)
    {
        static_cast<void>(BLEScan.stop());
        if (BLEPeriodicAdvertising.createSync(sourceAddress, sourceSid,
                                              periodicSync))
        {
            phase = SenderPhase::waitSync;
        }
        else
        {
            Serial.println("periodic sync creation failed");
            phase = SenderPhase::complete;
        }
    }
    else if (phase == SenderPhase::waitSync &&
             BLEPeriodicAdvertising.synchronized(periodicSync))
    {
        if (!BLEScan.clearFilters() || !BLEScan.filterName("NU54-PAST-RX") ||
            !BLEScan.start(true))
        {
            Serial.println("PAST receiver scan failed");
            phase = SenderPhase::complete;
        }
        else
        {
            phase = SenderPhase::findReceiver;
        }
    }
    else if (phase == SenderPhase::connectReceiver)
    {
        static_cast<void>(BLEScan.stop());
        phase = SenderPhase::waitConnection;
        if (!BLEConnection.connect(receiverAddress, receiverLink))
        {
            Serial.println("PAST receiver connection failed");
            phase = SenderPhase::complete;
        }
    }
    else if (phase == SenderPhase::transfer &&
             BLEConnection.connected(receiverLink))
    {
        if (BLEPeriodicAdvertising.transferSync(periodicSync, receiverLink,
                                                0x054dU))
        {
            Serial.println("PAST transfer submitted");
        }
        else
        {
            Serial.println("PAST transfer failed");
        }
        phase = SenderPhase::complete;
    }
}
