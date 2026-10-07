/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 동기 authorization으로 descriptor 접근을 여는 peripheral 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) GattAuthorization 실행 보드; 2) GattDescriptors 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) GattAuthorization 실행 보드; 2) GattDescriptors 실행 보드
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial Monitor에서 오류 문구 없이 목적 기능의 상태 전이가 완료되는지 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `authorization peripheral start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE/GattDescriptors`
 * - `NUCODE_BLE/L2capCocClient`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - wireless_example_no_implicit_security_claim
 * - 무선 연결 성공만으로 인증·암호화·상호운용 보안을 주장하지 않습니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `ble_gatt`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE/GattAuthorization`, sha256 `5e8498857578715be47122b955d3a74e804e581eb65d58d12dd17c8ae9c6f1a5`
 * @nucode_example_setup_end */

/**
 * @file GattAuthorization.ino
 * @brief 동기 authorization으로 descriptor 접근을 여는 peripheral 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid serviceUuid("8e7e2905-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid valueUuid("8e7e2906-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid descriptorUuids[] = {
    nucode::ble::BLEUuid("8e7e2910-7d8c-4c1a-9d2d-8b6519f77410"),
    nucode::ble::BLEUuid("8e7e2911-7d8c-4c1a-9d2d-8b6519f77410"),
    nucode::ble::BLEUuid("8e7e2912-7d8c-4c1a-9d2d-8b6519f77410"),
    nucode::ble::BLEUuid("8e7e2913-7d8c-4c1a-9d2d-8b6519f77410"),
};
const uint8_t unlockToken[] = {0x4eU, 0x55U, 0x35U, 0x34U};
nucode::ble::BLEService authorizationService(serviceUuid);
nucode::ble::BLECharacteristic authorizationValue(
    valueUuid, nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write,
    nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, sizeof(unlockToken));
nucode::ble::BLEDescriptor descriptor0(descriptorUuids[0], nucode::ble::BLEPermission::read, 4U);
nucode::ble::BLEDescriptor descriptor1(descriptorUuids[1], nucode::ble::BLEPermission::read, 4U);
nucode::ble::BLEDescriptor descriptor2(descriptorUuids[2], nucode::ble::BLEPermission::read, 4U);
nucode::ble::BLEDescriptor descriptor3(descriptorUuids[3], nucode::ble::BLEPermission::read, 4U);
nucode::ble::BLEDescriptor *descriptors[] = {
    &descriptor0,
    &descriptor1,
    &descriptor2,
    &descriptor3,
};
bool descriptorAccessAllowed = false;
bool running = false;

/**
 * @brief Bluetooth callback 문맥에서 characteristic write를 즉시 판정합니다.
 * @warning blocking Arduino API나 Serial을 호출하지 않습니다.
 */
bool authorizeValue(const nucode::ble::BLEGattAuthorizationRequest &request, void *context)
{
    static_cast<void>(context);
    if (request.operation == nucode::ble::BLEGattAuthorizationOperation::read)
    {
        return true;
    }
    const bool allowed = request.descriptor == nullptr && request.offset == 0U &&
                         !request.prepare && !request.execute && !request.without_response &&
                         request.length == sizeof(unlockToken) && request.data != nullptr &&
                         memcmp(request.data, unlockToken, sizeof(unlockToken)) == 0;
    if (allowed)
    {
        descriptorAccessAllowed = true;
    }
    return allowed;
}

/**
 * @brief Bluetooth callback 문맥에서 unlock된 descriptor read만 허용합니다.
 * @warning 이 callback은 bounded·non-blocking이어야 합니다.
 */
bool authorizeDescriptor(const nucode::ble::BLEGattAuthorizationRequest &request, void *context)
{
    return request.descriptor == static_cast<nucode::ble::BLEDescriptor *>(context) &&
           request.operation == nucode::ble::BLEGattAuthorizationOperation::read &&
           descriptorAccessAllowed;
}

/** @brief authorization 결과를 BLEDevice.poll() main thread에서 출력합니다. */
void onValueEvent(nucode::ble::BLECharacteristic &characteristic,
                  const nucode::ble::BLECharacteristicEventInfo &information, void *context)
{
    static_cast<void>(characteristic);
    static_cast<void>(context);
    if (information.event == nucode::ble::BLECharacteristicEvent::authorization_allowed)
    {
        Serial.println(information.descriptor == nullptr ? "value access allowed"
                                                         : "descriptor access allowed");
    }
    else if (information.event == nucode::ble::BLECharacteristicEvent::authorization_denied)
    {
        Serial.println(information.descriptor == nullptr ? "value access denied"
                                                         : "descriptor access denied");
    }
}

void setup()
{
    Serial.begin(115200);
    authorizationValue.onAuthorize(authorizeValue);
    authorizationValue.onEvent(onValueEvent);
    bool schemaReady = authorizationValue.setValue(unlockToken, sizeof(unlockToken));
    for (size_t index = 0U; index < 4U && schemaReady; ++index)
    {
        uint8_t value[4] = {static_cast<uint8_t>(index), 0x4eU, 0x55U, 0x35U};
        descriptors[index]->onAuthorize(authorizeDescriptor, descriptors[index]);
        schemaReady = descriptors[index]->setValue(value, sizeof(value)) &&
                      authorizationValue.addDescriptor(*descriptors[index]);
    }
    running = schemaReady && authorizationService.addCharacteristic(authorizationValue) &&
              BLEDevice.addService(authorizationService) && BLEDevice.begin("NU54-AUTH") &&
              BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
              BLEAdvertising.addServiceUuid(serviceUuid) &&
              BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    if (!running)
    {
        Serial.print("authorization peripheral start failed: ");
        Serial.println(BLEDevice.lastDriverError());
    }
}

void loop()
{
    if (running)
    {
        BLEDevice.poll();
    }
}
