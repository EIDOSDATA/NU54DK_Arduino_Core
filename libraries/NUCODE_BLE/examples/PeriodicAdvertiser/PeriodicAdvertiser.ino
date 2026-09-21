/**
 * @file PeriodicAdvertiser.ino
 * @brief Extended set에 periodic manufacturer data를 결합해 송신합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSet;
uint8_t extendedPayload[] = {3U, 0x09U, 'P', 'A'};
uint8_t periodicPayload[] = {4U, 0xffU, 0x59U, 0x00U, 0U};

void setup()
{
    Serial.begin(115200);
    nucode::ble::BLEExtendedAdvertisingParameters extendedParameters{};
    extendedParameters.sid = 2U;
    if (!BLEDevice.begin("NU54-PER-ADV") ||
        !BLEExtendedAdvertising.create(extendedParameters, advertisingSet) ||
        !BLEExtendedAdvertising.setData(advertisingSet, extendedPayload,
                                        sizeof(extendedPayload)) ||
        !BLEPeriodicAdvertising.configure(advertisingSet) ||
        !BLEPeriodicAdvertising.setData(advertisingSet, periodicPayload,
                                        sizeof(periodicPayload)) ||
        !BLEPeriodicAdvertising.start(advertisingSet) ||
        !BLEExtendedAdvertising.start(advertisingSet))
    {
        Serial.println("periodic advertiser failed");
    }
}

void loop()
{
    static uint8_t sequence = 0U;
    BLEDevice.poll();
    periodicPayload[4] = sequence++;
    if (!BLEPeriodicAdvertising.setData(advertisingSet, periodicPayload,
                                        sizeof(periodicPayload)))
    {
        Serial.println("periodic payload update failed");
    }
    delay(1000);
}
