/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) PastSender (sender); 2) PastReceiver (receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/PastReceiver`, sha256 `ad737557c5ac6ee8472e0feea6729df7ecde8ea565f419314fec44ccc6122778`
 * @nucode_example_setup_end */

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
