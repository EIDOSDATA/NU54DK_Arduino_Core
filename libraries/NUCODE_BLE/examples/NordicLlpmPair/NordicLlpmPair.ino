/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) NordicLlpmPair (central); 2) NordicLlpmPair (peripheral)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * centralRole을 한 보드는 true, 다른 보드는 false로 빌드하고 Nordic LLPM peer끼리 사용합니다.
 * @par Metadata
 * identity `NUCODE_BLE/NordicLlpmPair`, sha256 `1378be5d303e0e3f94657ef8fdce01ab926a2969525dc0f30a4aee349330c544`
 * @nucode_example_setup_end */

/**
 * @file NordicLlpmPair.ino
 * @brief 두 Nordic peer에서 2M PHY 뒤 1 ms LLPM과 표준 interval fallback을 비교합니다.
 */

#include <NUCODE_BLE.h>

/** @brief 한 보드는 true, 다른 보드는 false로 빌드합니다. */
constexpr bool centralRole = true;
bool peerFound = false;
nucode::ble::BLEAddress peerAddress;

/** @brief peripheral 이름을 찾은 central이 주소를 main loop에 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (!peerFound)
    {
        peerAddress = result.address;
        peerFound = true;
    }
}

/** @brief 연결 뒤 2M PHY를 요청하고 성공한 link만 Nordic 1 ms interval로 전환합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected)
    {
        static_cast<void>(BLEConnection.requestPhy(information.connection, true));
    }
    else if (information.event == nucode::ble::BLEEvent::phy_changed && centralRole)
    {
        if (!BLENordic.requestLlpmInterval(information.connection, 1000U))
        {
            static_cast<void>(BLEConnection.requestParameters(
                information.connection, 6U, 6U, 0U, 300U));
            Serial.println("LLPM rejected; requested standard 7.5 ms fallback");
        }
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    if (!BLEDevice.begin(centralRole ? "NU54-LLPM-C" : "NU54-LLPM-P") ||
        !BLENordic.setLlpmMode(true))
    {
        Serial.println("LLPM mode start failed");
        return;
    }
    if (centralRole)
    {
        static_cast<void>(BLEScan.filterName("NU54-LLPM-P"));
        static_cast<void>(BLEScan.start(true));
    }
    else
    {
        static_cast<void>(BLEAdvertising.setScanResponseName(true));
        static_cast<void>(BLEAdvertising.start());
    }
}

void loop()
{
    BLEDevice.poll();
    if (centralRole && peerFound && !BLEConnection.connected() &&
        !BLEConnection.connecting())
    {
        peerFound = false;
        static_cast<void>(BLEConnection.connect(peerAddress));
    }
}
