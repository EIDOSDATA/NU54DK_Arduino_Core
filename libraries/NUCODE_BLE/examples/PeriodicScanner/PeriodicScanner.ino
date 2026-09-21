/**
 * @file PeriodicScanner.ino
 * @brief Periodic advertiser를 발견해 한 개 sync를 만들고 bounded report를 읽습니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEPeriodicSyncHandle periodicSync;

/** @brief periodic interval이 있는 첫 extended report에 sync를 요청합니다. */
void onScan(const nucode::ble::BLEScanResult &result, void *)
{
    if (!periodicSync.valid() && result.extended && result.periodic_interval != 0U)
    {
        if (!BLEScan.stop() ||
            !BLEPeriodicAdvertising.createSync(result.address, result.sid, periodicSync))
        {
            Serial.println("periodic sync request failed");
            static_cast<void>(BLEScan.startExtended(false));
        }
    }
}

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-PER-SCAN"))
    {
        return;
    }
    BLEScan.onResult(onScan);
    if (!BLEScan.startExtended(false))
    {
        Serial.println("extended scan failed");
    }
}

void loop()
{
    BLEDevice.poll();
    nucode::ble::BLEPeriodicReport report{};
    while (BLEPeriodicAdvertising.read(report))
    {
        Serial.print("periodic bytes=");
        Serial.println(report.payload_length);
    }
}
