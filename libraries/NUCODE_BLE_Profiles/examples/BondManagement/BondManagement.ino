/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) 사용자 무장 BMS server; 2) 암호화·bond된 BMS 요청 peer
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 기본 미무장입니다. Serial 명령과 예제 authorization을 명시 승인한 한 요청 peer의 bond만 opcode 03으로 삭제하며 전체 삭제를 제공하지 않습니다.
 * @par Metadata
 * identity `NUCODE_BLE_Profiles/BondManagement`, sha256 `0ae1685ae7ccaf65e13bc7e59044494eec5fc557a0da57c4ae10638d3e42a62a`
 * @nucode_example_setup_end */

/**
 * @file BondManagement.ino
 * @brief 명시적으로 무장한 동안 요청 peer 자신의 LE bond만 삭제합니다.
 * @par 목적
 * 암호화·bond 확인과 application authorization을 함께 사용하는 BMS 예제입니다.
 * @par 준비물
 * NU54DK와 BMS write가 가능한 bonded BLE client.
 * @par 설정
 * Feature set BLE NUS, 115200 baud. 인증코드 "delete-this-bond"는 데모 의사 확인 문구입니다.
 * @par 실행 순서
 * client를 pairing한 뒤 Serial 'a'로 30초 무장합니다. client가 0x2aa4에 opcode 03과
 * 문구 bytes를 Write Request로 보냅니다. 's'를 입력하면 종료합니다.
 * @par 성공 출력
 * bond deletion accepted의 수가 증가합니다. 영속 삭제는 재연결/재부팅으로 별도 확인합니다.
 * @par 흔한 오류
 * 미무장·미암호화·잘못된 문구·다른 opcode는 거부합니다. 전체 bond 삭제는 지원하지 않습니다.
 * @par 다음 예제
 * NUCODE_BLE_Security의 GattCachePeripheral과 pairing 예제를 참고합니다.
 */
#include <NUCODE_BLE_Profiles.h>
#include <NUCODE_BLE_Security.h>
using namespace nucode::ble;
using namespace nucode::ble::profiles;
BondManagementService bonds;
uint32_t armedAt = 0U;
uint32_t lastAccepted = 0U;
bool running = false;

/** @brief callback에서 블로킹 없이 데모 삭제 의도를 확인합니다. */
bool authorizeDelete(const BondDeleteRequest &request, void *)
{
    const char expected[] = "delete-this-bond";
    if (request.length != sizeof(expected) - 1U)
    {
        return false;
    }
    uint8_t difference = 0U;
    for (size_t i = 0U; i < request.length; ++i)
    {
        difference |= request.authorization_code[i] ^ static_cast<uint8_t>(expected[i]);
    }
    return difference == 0U;
}
void onSecurity(const SecurityEventRecord &event, void *)
{
    if (event.event == SecurityEvent::pairing_requested)
    {
        static_cast<void>(BLESecurity.acceptPairing(event.connection, true));
    }
}
void setup()
{
    Serial.begin(115200);
    SecurityConfig security;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurity);
    running = BLESecurity.begin(security) && bonds.begin(authorizeDelete) &&
              BLEDevice.begin("NU54-BONDS") && BLEAdvertising.clear() &&
              BLEAdvertising.addServiceUuid(BLEUuid(0x181eU)) && BLEAdvertising.start();
    Serial.println(running ? "bond service ready; Serial a arms 30 seconds"
                           : "bond service failed");
}
void loop()
{
    if (!running)
    {
        return;
    }
    BLEDevice.poll();
    BLESecurity.poll();
    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if (command == 'a')
        {
            armedAt = millis();
            bonds.setArmed(true);
            Serial.println("bond deletion armed");
        }
        else if (command == 's')
        {
            bonds.setArmed(false);
            BLEDevice.end();
            running = false;
        }
    }
    if (bonds.armed() && millis() - armedAt >= 30000U)
    {
        bonds.setArmed(false);
    }
    if (bonds.acceptedCount() != lastAccepted)
    {
        lastAccepted = bonds.acceptedCount();
        bonds.setArmed(false);
        Serial.println("bond deletion accepted");
    }
}
