/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) MixedRoleLinks 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 동작에 필요한 compatible BLE peer 또는 mobile/host client를 별도로 준비합니다.
 * @par Metadata
 * identity `NUCODE_BLE/MixedRoleLinks`, sha256 `5b3d8641a5b0a7fdb94800e390b015d6378ec6e4afc9bb7644ade169fc0da542`
 * @nucode_example_setup_end */

/**
 * @file MixedRoleLinks.ino
 * @brief 한 NU54DK가 central 1-link와 peripheral 1-link를 동시에 유지하는 예제입니다.
 *
 * Central peer는 `NU54-GAP-P`로 광고해야 하며, 세 번째 peer는 `NU54-MIXED`에 연결합니다.
 * 도구 → Feature set → BLE NUS를 선택해야 합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAddress centralPeerAddress;
nucode::ble::BLEConnectionHandle centralLink;
nucode::ble::BLEConnectionHandle peripheralLink;
bool centralPeerFound = false;
bool startPeripheralAdvertising = false;

/** @brief exact-name scan 결과에서 central 역할로 연결할 주소를 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (!centralPeerFound)
    {
        centralPeerAddress = result.address;
        centralPeerFound = true;
    }
}

/** @brief link별 generation handle과 local 역할을 main thread에서 보존합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        if (information.role == nucode::ble::BLELinkRole::central)
        {
            centralLink = information.connection;
            startPeripheralAdvertising = true;
        }
        else if (information.role == nucode::ble::BLELinkRole::peripheral)
        {
            peripheralLink = information.connection;
        }
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected)
    {
        if (information.connection == centralLink)
        {
            centralLink = nucode::ble::BLEConnectionHandle{};
        }
        if (information.connection == peripheralLink)
        {
            peripheralLink = nucode::ble::BLEConnectionHandle{};
        }
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin("NU54-MIXED") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEScan.clearFilters() ||
        !BLEScan.filterName("NU54-GAP-P") || !BLEScan.start(true))
    {
        Serial.println("mixed-role setup failed");
    }
}

void loop()
{
    BLEDevice.poll();
    if (centralPeerFound && !centralLink.valid())
    {
        centralPeerFound = false;
        if (!BLEConnection.connect(centralPeerAddress, centralLink))
        {
            Serial.println("central connect failed");
        }
    }
    if (startPeripheralAdvertising && BLEConnection.connected(centralLink))
    {
        startPeripheralAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("peripheral advertising failed");
        }
    }
}
