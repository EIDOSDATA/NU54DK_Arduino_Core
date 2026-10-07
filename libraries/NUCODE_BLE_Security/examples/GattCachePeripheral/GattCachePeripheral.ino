/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * bonded peer에 Database Hash와 Service Changed 기반 GATT cache를 제공하는 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) GattCacheCentral (central/client); 2) GattCachePeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) GattCacheCentral (central/client); 2) GattCachePeripheral (peripheral/server)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `GATT cache peer bonded`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `GATT cache pairing approval failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `GATT cache security failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `GATT cache notification failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Security/HeartRate`
 * - `NUCODE_BLE_Security/SecureConsumerControl`
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
 * identity `NUCODE_BLE_Security/GattCachePeripheral`, sha256 `5ecbfdd93491e51b2a06de981a86296301cd5c3a9685ada325d173f6463312b3`
 * @nucode_example_setup_end */

/**
 * @file GattCachePeripheral.ino
 * @brief bonded peer에 Database Hash와 Service Changed 기반 GATT cache를 제공하는 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Security.h>

namespace
{

    constexpr std::uint32_t databaseRevision = 1U;
    const nucode::ble::BLEUuid serviceUuid("8e7e2950-7d8c-4c1a-9d2d-8b6519f77410");
    const nucode::ble::BLEUuid valueUuid("8e7e2951-7d8c-4c1a-9d2d-8b6519f77410");
    nucode::ble::BLEService cacheService(serviceUuid);
    nucode::ble::BLECharacteristic
        cacheValue(valueUuid,
                   nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write |
                       nucode::ble::BLEProperty::notify,
                   nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, 32U);
    bool securityRequestPending = false;

    /** @brief pairing 요청은 main thread에서 명시적으로 승인합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(true))
            {
                Serial.println("GATT cache pairing approval failed");
            }
        }
        else if (record.event == nucode::ble::SecurityEvent::paired ||
                 record.event == nucode::ble::SecurityEvent::bond_verified)
        {
            Serial.println("GATT cache peer bonded");
        }
        else if (record.event == nucode::ble::SecurityEvent::pairing_failed ||
                 record.event == nucode::ble::SecurityEvent::error)
        {
            Serial.println("GATT cache security failed");
        }
    }

    /** @brief 새 peripheral link마다 encrypted bonded session을 요청합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected &&
            information.role == nucode::ble::BLELinkRole::peripheral)
        {
            securityRequestPending = true;
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            securityRequestPending = false;
        }
    }

    /** @brief peer write를 cached value와 notification에 반영합니다. */
    void onCharacteristicEvent(nucode::ble::BLECharacteristic &characteristic,
                               const nucode::ble::BLECharacteristicEventInfo &information,
                               void *context)
    {
        static_cast<void>(context);
        if (&characteristic == &cacheValue &&
            information.event == nucode::ble::BLECharacteristicEvent::written)
        {
            if (!cacheValue.notify(information.connection))
            {
                Serial.println("GATT cache notification failed");
            }
        }
    }

    /** @brief 시작 실패 단계만 출력하고 잘못된 부분 실행을 막습니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("GattCachePeripheral start failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000U);
        }
    }

} // namespace

void setup()
{
    Serial.begin(115200);

    nucode::ble::SecurityConfig security{};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    cacheValue.onEvent(onCharacteristicEvent);

    const std::uint8_t initialValue[] = {'c', 'a', 'c', 'h', 'e', '-', 'v', '1'};
    require(BLEGattDatabase.setRevision(databaseRevision), "database-revision");
    require(BLESecurity.begin(security), "security");
    require(cacheValue.setValue(initialValue, sizeof(initialValue)), "initial-value");
    require(cacheService.addCharacteristic(cacheValue), "characteristic");
    require(BLEDevice.addService(cacheService), "service");
    require(BLEDevice.begin("NU54-GATT-CACHE"), "device");
    require(BLEAdvertising.clear(), "advertising-clear");
    require(BLEAdvertising.setConnectable(true), "advertising-connectable");
    require(BLEAdvertising.addServiceUuid(serviceUuid), "advertising-service");
    require(BLEAdvertising.setScanResponseName(true), "advertising-name");
    require(BLEAdvertising.start(), "advertising-start");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    if (securityRequestPending)
    {
        securityRequestPending = false;
        if (!BLESecurity.requestSecurity())
        {
            Serial.println("GATT cache security request failed");
        }
    }
    delay(1U);
}
