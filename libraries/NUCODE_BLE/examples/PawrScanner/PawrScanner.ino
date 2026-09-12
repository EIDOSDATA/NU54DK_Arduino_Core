/**
 * @file PawrScanner.ino
 * @brief PAwR sync의 4개 subevent를 받고 slot 0에 bounded response를 보냅니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEPeriodicSyncHandle periodicSync;

/** @brief periodic interval이 있는 첫 extended report에 sync를 요청합니다. */
void onScan(const nucode::ble::BLEScanResult &result, void *)
{
    if (!periodicSync.valid() && result.extended && result.periodic_interval != 0U)
    {
        static_cast<void>(BLEScan.stop());
        static_cast<void>(BLEPeriodicAdvertising.createSync(result.address, result.sid,
                                                            periodicSync));
    }
}

/** @brief PAwR request metadata를 사용해 다음 response를 한 번 예약합니다. */
void onPeriodicReport(const nucode::ble::BLEPeriodicReport &report, void *)
{
    const uint8_t response[] = {report.subevent, 0x5aU};
    static_cast<void>(BLEPawr.sendResponse(report.sync, report.periodic_event_counter,
                                          report.subevent, report.subevent, 0U,
                                          response, sizeof(response)));
}

/** @brief sync 완료 뒤 0~3 subevent 수신을 설정합니다. */
void onEvent(const nucode::ble::BLEEventInfo &information, void *)
{
    if (information.event == nucode::ble::BLEEvent::periodic_sync_synchronized)
    {
        const uint8_t subevents[] = {0U, 1U, 2U, 3U};
        static_cast<void>(BLEPawr.configureScanner(information.periodic_sync, subevents,
                                                  sizeof(subevents)));
    }
}

void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NU54-PAWR-SCAN"))
    {
        return;
    }
    BLEDevice.onEventInfo(onEvent);
    BLEScan.onResult(onScan);
    BLEPeriodicAdvertising.onReport(onPeriodicReport);
    static_cast<void>(BLEScan.startExtended(false));
}

void loop()
{
    BLEDevice.poll();
}
