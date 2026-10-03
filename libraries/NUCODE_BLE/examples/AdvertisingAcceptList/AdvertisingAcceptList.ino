/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) AdvertisingAcceptList (peripheral); 2) 허용 주소로 설정한 central
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 예제의 allowedPeer를 central identity 주소로 바꿉니다.
 * @par Metadata
 * identity `NUCODE_BLE/AdvertisingAcceptList`, sha256 `823bfbb516b3ded6c5e8848205312d676230e4502ad250fe2fe680c3d1fd4956`
 * @nucode_example_setup_end */

/**
 * @file AdvertisingAcceptList.ino
 * @brief 허용한 peer만 연결할 수 있는 advertising set을 실행합니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSet;
const nucode::ble::BLEAddress allowedPeer(
    "C0:DE:00:00:00:01", nucode::ble::BLEAddress::Type::random_address);

void setup()
{
    Serial.begin(115200);
    nucode::ble::BLEExtendedAdvertisingParameters parameters;
    parameters.connectable = true;
    parameters.filter_connections = true;
    if (!BLEDevice.begin("NU54-ACCEPT") ||
        !BLEAdvertisingLists.clearFilterAccept() ||
        !BLEAdvertisingLists.addFilterAccept(allowedPeer) ||
        !BLEExtendedAdvertising.create(parameters, advertisingSet) ||
        !BLEExtendedAdvertising.start(advertisingSet))
    {
        Serial.println("accept list advertising failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
