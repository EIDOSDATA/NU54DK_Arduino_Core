/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) synthetic CGMS server; 2) Kind::glucose로 설정한 StandardCollector
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 단일 연결과 L3 인증을 요구합니다. 양쪽 숫자가 실제로 같을 때 각각 y를 입력합니다. 1분 주기·16 record이며 의료 측정기나 SOCP start/stop 지원이 아닙니다.
 * @par Metadata
 * identity `NUCODE_BLE_Profiles/GlucoseSensor`, sha256 `35081720cbecf641af79b00474b04451dde016c2e7e686fa0def01610158543f`
 * @nucode_example_setup_end */

/**
 * @file GlucoseSensor.ino
 * @brief NCS CGMS의 record·session·RACP를 synthetic 농도로 사용합니다.
 * @par 목적
 * 사용자 SFLOAT 값을 실제 CGMS 기록 저장소에 넣습니다. 의료 측정기가 아닙니다.
 * @par 준비물
 * NU54DK와 CGMS collector 또는 StandardCollector(Kind::glucose).
 * @par 설정
 * Feature set BLE NUS, 동봉 prj.conf, 115200 baud. 단일 link 구성입니다.
 * @par 실행 순서
 * 두 Serial Monitor에서 6자리 숫자를 대조하고 일치할 때만 각각 y를 입력합니다.
 * 인증된 L3 link에서 0x2aa7 notification을 구독하며 최소 주기는 1분입니다.
 * @par 성공 출력
 * synthetic glucose stored와 1분 후 collector 수신을 확인합니다.
 * @par 흔한 오류
 * session 만료 뒤 add는 실패합니다. record 16개는 오래된 것부터 교체됩니다.
 * 고정 SDK의 SOCP는 통신주기 read/write만 지원하며 start/stop과 RACP delete는 unsupported입니다.
 * @par 다음 예제
 * StandardCollector와 NCS CGMS session/RACP 절차는 라이브러리 README를 참고합니다.
 */
#include <NUCODE_BLE_Profiles.h>
#include <NUCODE_BLE_Glucose.h>
#include <NUCODE_BLE_Security.h>
using namespace nucode::ble;
nucode::ble::profiles::GlucoseService glucose;
bool running = false;
uint32_t startedAt = 0U;
uint32_t previousAt = 0U;
BLEConnectionHandle confirmationPeer;

/** @brief 숫자를 사용자가 직접 비교하도록 표시하며 Just Works는 거부합니다. */
void onSecurity(const SecurityEventRecord &event, void *)
{
    if (event.event == SecurityEvent::passkey_confirmation_requested ||
        event.event == SecurityEvent::passkey_display)
    {
        char digits[7];
        snprintf(digits, sizeof(digits), "%06lu", static_cast<unsigned long>(event.passkey));
        Serial.print("Compare passkey: ");
        Serial.println(digits);
        if (event.event == SecurityEvent::passkey_confirmation_requested)
        {
            confirmationPeer = event.connection;
            Serial.println("Enter y only if both displays match; n rejects (30 s).");
        }
    }
    else if (event.event == SecurityEvent::pairing_requested)
    {
        static_cast<void>(BLESecurity.acceptPairing(event.connection, false));
        Serial.println("Unauthenticated pairing rejected: CGMS requires L3.");
    }
    else if (event.event == SecurityEvent::security_changed)
    {
        Serial.println(event.level >= SecurityLevel::authenticated
                           ? "authenticated CGMS link"
                           : "CGMS authentication required");
    }
    else if (event.event == SecurityEvent::pairing_cancelled ||
             event.event == SecurityEvent::pairing_failed || event.event == SecurityEvent::timeout)
    {
        confirmationPeer = {};
        Serial.println("pairing cancelled/failed; no authenticated subscription");
    }
}

/** @brief 연결 종료 시 이전 generation에 대한 확인 입력을 폐기합니다. */
void onLink(const BLEEventInfo &event, void *)
{
    if (event.event == BLEEvent::disconnected && event.connection == confirmationPeer)
    {
        confirmationPeer = {};
    }
}

void setup()
{
    Serial.begin(115200);
    SecurityConfig security;
    security.minimum_level = SecurityLevel::authenticated;
    security.io_capability = SecurityIoCapability::display_yes_no;
    BLESecurity.onEvent(onSecurity);
    BLEDevice.onEventInfo(onLink);
    running = BLESecurity.begin(security) && BLEDevice.begin("NU54-GLUCOSE") &&
              glucose.begin(1U, 1U) && BLEAdvertising.clear() &&
              BLEAdvertising.addServiceUuid(BLEUuid(0x181fU)) && BLEAdvertising.start();
    startedAt = millis();
    Serial.println(running ? "glucose ready: synthetic data" : "glucose start failed");
}
void loop()
{
    if (!running)
    {
        return;
    }
    BLEDevice.poll();
    BLESecurity.poll();
    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (confirmationPeer.valid() && (command == 'y' || command == 'n'))
        {
            Serial.println(BLESecurity.confirmPasskey(confirmationPeer, command == 'y')
                               ? "comparison response submitted"
                               : "comparison response failed");
            confirmationPeer = {};
        }
    }
    if (millis() - startedAt >= 185000U)
    {
        if (confirmationPeer.valid())
        {
            static_cast<void>(BLESecurity.cancelPairing(confirmationPeer));
            confirmationPeer = {};
        }
        BLEDevice.end();
        running = false;
        return;
    }
    if (millis() - previousAt >= 10000U)
    {
        previousAt = millis();
        const int16_t syntheticMgDl = 100 + static_cast<int16_t>((millis() / 10000U) % 10U);
        Serial.println(glucose.add(syntheticMgDl) ? "synthetic glucose stored"
                                                  : "glucose store failed");
    }
}
