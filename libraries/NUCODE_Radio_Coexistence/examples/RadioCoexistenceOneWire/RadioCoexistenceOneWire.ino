/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE external 1-wire coexistence (`external_coexistence`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) 1-wire grant simulator와 BLE advertiser
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 전원을 끈 상태에서 P1.10(P4-8) output을 P1.14(P4-12) grant input에 연결하고 g/d 명령으로 허용/거부를 확인합니다.
 * @par Metadata
 * identity `NUCODE_Radio_Coexistence/RadioCoexistenceOneWire`, sha256 `0bf142727ef89a8b9537bb535dd858d4e99563aee3a84e1ef2f15649e4a6a833`
 * @nucode_example_setup_end */

/**
 * @file RadioCoexistenceOneWire.ino
 * @brief P1.10 output과 P1.14 grant input을 연결해 1-wire arbitration을 관측합니다.
 */

#include <NUCODE_BLE.h>
#include <NUCODE_Radio_Coexistence.h>

using nucode::coexistence::Protocol;

uint32_t lastRadioEvents = 0U;
uint32_t lastReportMs = 0U;

void setup()
{
    Serial.begin(115200);
    static_cast<void>(NUCODECoexistence.begin(500U));
    if (!NUCODECoexistence.beginOneWire())
    {
        Serial.println("1-wire coexistence start failed");
    }
    if (!BLESerial.beginPeripheral("NU54-COEX-1W") || !BLESerial.startAdvertising())
    {
        Serial.println("BLE start failed");
    }
    else
    {
        NUCODECoexistence.setActive(Protocol::ble, true);
    }
    NUCODECoexistence.setActive(Protocol::external_radio, true);
    Serial.println("P1.10을 P1.14에 연결했습니다. g=grant, d=deny");
}

void loop()
{
    BLESerial.poll();
    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if (command == 'g')
        {
            static_cast<void>(NUCODECoexistence.setExternalGrant(true));
        }
        else if (command == 'd')
        {
            static_cast<void>(NUCODECoexistence.setExternalGrant(false));
        }
    }

    const uint32_t now = millis();
    if (now - lastReportMs >= 1000U)
    {
        lastReportMs = now;
        const uint32_t radioEvents = NUCODECoexistence.radioEventCount();
        NUCODECoexistence.recordRequested(Protocol::external_radio);
        NUCODECoexistence.recordDelivered(Protocol::external_radio, radioEvents,
                                          radioEvents ^ 0xC0E1U);
        Serial.print("radio_ready_events=");
        Serial.print(radioEvents);
        Serial.print(" delta=");
        Serial.println(radioEvents - lastRadioEvents);
        lastRadioEvents = radioEvents;
    }
}
