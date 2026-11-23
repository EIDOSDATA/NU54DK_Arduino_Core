/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 버튼 확인 뒤 bonding하고 암호화 BLE HID key report를 보냅니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) SecureKeyboard 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 동작에 필요한 compatible BLE peer 또는 mobile/host client를 별도로 준비합니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) SecureKeyboard 실행 보드
 * - 동작에 필요한 compatible BLE peer 또는 mobile/host client를 별도로 준비합니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `BLE pairing confirmation requested; press SW0`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `BLE pairing completed`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `BLE bond pending reboot verification`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `BLE security operation failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `SecureKeyboard start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Security/SecureMouse`
 * - `NUCODE_BLE_Security/EnvironmentalSensing`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - explicit_security_or_signed_artifact_flow
 * - 예제의 pairing·bond·서명·credential 조건을 생략하지 않고 오류 출력을 확인합니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `ble_profiles_and_ecosystems`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_Security/SecureKeyboard`, sha256 `019db4f70fba8f6ab9928d3b94594398f0c7207837d2ddd43509d7935b44db92`
 * @nucode_example_setup_end */

/**
 * @file SecureKeyboard.ino
 * @brief 버튼 확인 뒤 bonding하고 암호화 BLE HID key report를 보냅니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_Security.h>

namespace
{

    constexpr std::uint8_t hid_usage_a = 0x04U;
    bool pairing_confirmation_pending = false;
    bool previous_button_pressed = false;

    /** @brief passkey 값이나 key material을 Serial에 출력하지 않고 상태만 보존합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        (void)context;
        switch (record.event)
        {
        case nucode::ble::SecurityEvent::pairing_requested:
            pairing_confirmation_pending = true;
            Serial.println("BLE pairing confirmation requested; press SW0");
            break;
        case nucode::ble::SecurityEvent::paired:
            Serial.println("BLE pairing completed");
            break;
        case nucode::ble::SecurityEvent::bond_persistence_pending:
            Serial.println("BLE bond pending reboot verification");
            break;
        case nucode::ble::SecurityEvent::bond_restored_candidate:
            Serial.println("BLE restored bond candidate awaiting encrypted reconnect");
            break;
        case nucode::ble::SecurityEvent::bond_verified:
            Serial.println("BLE bond restored and verified after reboot");
            break;
        case nucode::ble::SecurityEvent::bond_removal_requested:
        case nucode::ble::SecurityEvent::all_bonds_removal_requested:
            Serial.println("BLE bond removal request accepted; verify after reboot");
            break;
        case nucode::ble::SecurityEvent::pairing_cancelled:
        case nucode::ble::SecurityEvent::pairing_failed:
        case nucode::ble::SecurityEvent::timeout:
        case nucode::ble::SecurityEvent::error:
            pairing_confirmation_pending = false;
            Serial.println("BLE security operation failed");
            break;
        default:
            break;
        }
    }

    /** @brief 실패 시 민감하지 않은 단계 이름만 출력하고 실행을 멈춥니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("SecureKeyboard start failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000);
        }
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    pinMode(PIN_BUTTON0, INPUT_PULLUP);

    nucode::ble::SecurityConfig security = {};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.response_timeout_ms = 30000U;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    require(BLESecurity.begin(security), "security");
    require(BLEKeyboard.begin(), "hid");
    require(BLEDevice.begin("NU54-Secure-HID"), "device");

    const nucode::ble::DeviceInformation information = {"NUCODE", "NU54DK-HID", "UNSET",
                                                        "0.3.0",  "NU54DK",     "0.3.0"};
    require(BLEDeviceInformation.configure(information), "dis");
    require(BLEBattery.setLevel(100U), "bas");

    require(BLEAdvertising.clear(), "advertising-clear");
    require(BLEAdvertising.setConnectable(true), "advertising-connectable");
    require(BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x1812U)), "advertising-hids");
    require(BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x180FU)), "advertising-bas");
    require(BLEAdvertising.setScanResponseName(true), "advertising-name");
    require(BLEAdvertising.start(), "advertising-start");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();

    const bool pressed = digitalRead(PIN_BUTTON0) == LOW;
    if (pressed && !previous_button_pressed)
    {
        if (pairing_confirmation_pending)
        {
            pairing_confirmation_pending = false;
            static_cast<void>(BLESecurity.acceptPairing(true));
        }
        else if (BLESecurity.currentLevel() >= nucode::ble::SecurityLevel::encrypted &&
                 BLEKeyboard.connected())
        {
            if (BLEKeyboard.press(hid_usage_a))
            {
                delay(15);
                static_cast<void>(BLEKeyboard.releaseAll());
            }
        }
    }
    previous_button_pressed = pressed;
    delay(5);
}
