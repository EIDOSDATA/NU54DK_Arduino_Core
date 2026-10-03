/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) ANS alert server; 2) Kind::alert로 설정한 StandardCollector
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * collector가 email category와 CCC를 허용한 뒤에만 알림을 받습니다. ANCS/Apple 알림 연동과는 다른 표준 ANS입니다.
 * @par Metadata
 * identity `NUCODE_BLE_Profiles/AlertSensor`, sha256 `887eebbba6fc133ee6020d672a3159fad3150ad7ad25afcbd83abe4ac1906d3e`
 * @nucode_example_setup_end */

/**
 * @file AlertSensor.ino
 * @brief category별 사용자 알림을 ANS로 전송합니다.
 * @par 목적
 * 각 link의 control point 허용 category를 분리해 email 알림을 보냅니다.
 * @par 준비물
 * NU54DK 2대와 StandardCollector(Kind::alert).
 * @par 설정
 * Feature set BLE NUS, 115200 baud, 별도 장치 없음.
 * @par 실행 순서
 * server와 collector를 시작하고 60초 동안 synthetic email 알림을 관찰합니다.
 * @par 성공 출력
 * alert queued와 collector의 decoded measurement: example email.
 * @par 흔한 오류
 * CCC 구독과 category enable 둘 다 필요합니다. 아직 준비 안 된 link의 send는 false입니다.
 * @par 다음 예제
 * StandardSensor, StandardCollector의 ANS control point 흐름을 참고합니다.
 */
#include <NUCODE_BLE_Profiles.h>
using namespace nucode::ble;
using namespace nucode::ble::profiles;
AlertService alerts;
bool running = false;
uint32_t startedAt = 0U;
uint32_t previousAt = 0U;
void setup()
{
    Serial.begin(115200);
    running = alerts.begin() && BLEDevice.begin("NU54-ALERT") && BLEAdvertising.clear() &&
              BLEAdvertising.addServiceUuid(BLEUuid(0x1811U)) && BLEAdvertising.start();
    startedAt = millis();
    Serial.println(running ? "alert ready" : "alert start failed");
}
void loop()
{
    if (!running)
    {
        return;
    }
    BLEDevice.poll();
    alerts.poll();
    if (millis() - startedAt >= 60000U)
    {
        BLEDevice.end();
        running = false;
        return;
    }
    if (millis() - previousAt >= 2000U)
    {
        previousAt = millis();
        Alert message{1U, 1U, "example email"};
        const auto peer = BLEConnection.handle(BLELinkRole::peripheral);
        if (alerts.send(peer, message))
        {
            Serial.println("alert queued");
        }
    }
}
