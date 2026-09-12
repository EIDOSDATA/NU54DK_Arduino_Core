/**
 * @file PrivacyPeripheral.ino
 * @brief 60초 RPA 회전을 사용하는 extended advertising 예제입니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSet;

/** @brief RPA 만료 event가 실제 set과 결합되었는지 출력합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::rpa_expired &&
        information.advertising_set == advertisingSet)
    {
        Serial.print("RPA expiration count: ");
        Serial.println(BLEPrivacy.expirationCount());
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    nucode::ble::BLEExtendedAdvertisingParameters parameters{};
    parameters.connectable = true;
    parameters.sid = 6U;
    if (!BLEDevice.begin("NU54-PRIVATE") ||
        !BLEPrivacy.setRotationTimeout(60U) ||
        !BLEExtendedAdvertising.create(parameters, advertisingSet) ||
        !BLEExtendedAdvertising.start(advertisingSet))
    {
        Serial.println("privacy advertising failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
