/**
 * @file GAPCentral.ino
 * @brief exact local-name scan 결과에 한 번 연결하는 GAP central 예제입니다.
 */

#include <NUCODE_BLE.h>

bool peerFound = false;
nucode::ble::BLEAddress peerAddress;

/** @brief bounded scan 결과를 main thread에서 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    /** @note exact name은 scan response에서 올 수 있어 같은 peer 주소를 사용합니다. */
    if (!peerFound)
    {
        peerAddress = result.address;
        peerFound = true;
    }
}

void setup()
{
    Serial.begin(115200);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-GAP-C") || !BLEScan.clearFilters() ||
        !BLEScan.filterName("NU54-GAP-P") || !BLEScan.start(true))
    {
        Serial.println("BLE GAP scan failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        static_cast<void>(BLEConnection.connect(peerAddress));
    }
}
