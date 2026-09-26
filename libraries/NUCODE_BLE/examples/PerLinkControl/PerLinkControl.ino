/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) PerLinkControl 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 동작에 필요한 compatible BLE peer 또는 mobile/host client를 별도로 준비합니다.
 * @par Metadata
 * identity `NUCODE_BLE/PerLinkControl`, sha256 `d52fd9b5175784453b826fcb0811de6afbb7591824b5017954863d77e5b334b2`
 * @nucode_example_setup_end */

/**
 * @file PerLinkControl.ino
 * @brief generation handle마다 PHY·DLE·parameter·remote-info를 분리하는 예제입니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEConnectionHandle centralLink;
nucode::ble::BLEConnectionHandle peripheralLink;

/** @brief 새 link의 역할별 handle을 보존하고 독립적인 제어 요청을 제출합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        if (information.role == nucode::ble::BLELinkRole::central)
        {
            centralLink = information.connection;
        }
        else if (information.role == nucode::ble::BLELinkRole::peripheral)
        {
            peripheralLink = information.connection;
        }
        const bool phyRequested = BLEConnection.requestPhy(information.connection, true);
        const bool dataLengthRequested =
            BLEConnection.requestDataLength(information.connection);
        const bool parametersRequested =
            BLEConnection.requestParameters(information.connection, 24U, 40U, 0U, 400U);
        if (!phyRequested || !dataLengthRequested || !parametersRequested)
        {
            Serial.println("per-link control request failed");
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
    else if (information.event == nucode::ble::BLEEvent::remote_information_available)
    {
        nucode::ble::BLERemoteInformation remote{};
        if (BLEConnection.remoteInformation(information.connection, remote))
        {
            Serial.print("Remote LL version: ");
            Serial.println(remote.version);
        }
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-LINK-CTRL") || !BLEAdvertising.clear() ||
        !BLEAdvertising.setConnectable(true) || !BLEAdvertising.start())
    {
        Serial.println("per-link control setup failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
