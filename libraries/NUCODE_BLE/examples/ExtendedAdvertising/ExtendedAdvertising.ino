/**
 * @file ExtendedAdvertising.ino
 * @brief SID 3과 255-byte payload로 non-connectable extended advertising을 실행합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSet;
uint8_t advertisingPayload[255] = {};

/** @brief 한 개의 최대 길이 manufacturer AD structure를 구성합니다. */
void preparePayload()
{
    advertisingPayload[0] = 254U;
    advertisingPayload[1] = 0xffU;
    for (size_t index = 2U; index < sizeof(advertisingPayload); ++index)
    {
        advertisingPayload[index] = static_cast<uint8_t>(index);
    }
}

void setup()
{
    Serial.begin(115200);
    preparePayload();
    nucode::ble::BLEExtendedAdvertisingParameters parameters{};
    parameters.sid = 3U;
    parameters.include_tx_power = true;
    if (!BLEDevice.begin("NU54-EXT-ADV") ||
        !BLEExtendedAdvertising.create(parameters, advertisingSet) ||
        !BLEExtendedAdvertising.setData(advertisingSet, advertisingPayload,
                                        sizeof(advertisingPayload)) ||
        !BLEExtendedAdvertising.start(advertisingSet))
    {
        Serial.println("extended advertising failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
