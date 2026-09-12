/**
 * @file ExtendedScanner.ino
 * @brief 1M·coded PHY의 extended advertising metadata와 최대 255-byte payload를 수신합니다.
 */

#include <NUCODE_BLE.h>

/** @brief copied extended scan result의 식별 필드를 main thread에서 출력합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (result.extended)
    {
        Serial.print("SID=");
        Serial.print(result.sid);
        Serial.print(" PHY=");
        Serial.print(static_cast<unsigned int>(result.secondary_phy));
        Serial.print(" LEN=");
        Serial.println(result.payload_length);
    }
}

void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-EXT-SCAN") || !BLEScan.clearFilters() ||
        !BLEScan.startExtended(true, true))
    {
        Serial.println("extended scan failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
