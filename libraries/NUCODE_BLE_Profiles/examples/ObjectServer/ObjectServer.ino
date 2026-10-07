/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 이름·payload·쓰기 권한이 보이는 OTS RAM object server입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) RAM OTS object server; 2) ObjectClient
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 단일 암호화 연결, object 최대 4개×512 byte와 이름 32 octet을 사용합니다. 재부팅하면 RAM object는 사라집니다.
 * @par 준비물
 * - NU54DK 보드 2대 — 1) RAM OTS object server; 2) ObjectClient
 * - 단일 암호화 연결, object 최대 4개×512 byte와 이름 32 octet을 사용합니다. 재부팅하면 RAM object는 사라집니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `client object payload:`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `object server stopped; reset to restart`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Profiles/StandardCollector`
 * - `NUCODE_BLE_Profiles/StandardSensor`
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
 * Recipe `ble_profiles_and_ecosystems`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_Profiles/ObjectServer`, sha256 `1d1da8234ff6a18bf26d0c4274807e8238dace7faf4ac533a00cbb3855952de5`
 * @nucode_example_setup_end */

/**
 * @file ObjectServer.ino
 * @brief 이름·payload·쓰기 권한이 보이는 OTS RAM object server입니다.
 * @par 목적
 * 실제 표준 OTS metadata/OACP/OLCP와 L2CAP CoC로 최대 512-byte object를 공유합니다.
 * @par 준비물
 * NU54DK 2대: ObjectServer와 ObjectClient. 외장 flash는 필요하지 않습니다.
 * @par 설정
 * Feature set BLE NUS, 동봉 prj.conf, 115200 baud. 단일 link·RAM 4-object 한도입니다.
 * @par 실행 순서
 * server를 시작한 뒤 client를 실행합니다. 새 pairing은 이 데모에서 Just Works로 허용합니다.
 * @par 성공 출력
 * object server ready와 client object payload를 확인합니다. client write는 server에 표시됩니다.
 * @par 흔한 오류
 * 미암호화·512 byte 초과·4개 pool 소진·read-only object 쓰기는 실패합니다.
 * @par 다음 예제
 * ObjectClient의 create/rename/select/read/write/delete 및 Serial s 중단을 참고합니다.
 */
#include <NUCODE_BLE_ObjectTransfer.h>
#include <NUCODE_BLE_Security.h>
using namespace nucode::ble;
using namespace nucode::ble::profiles;
ObjectTransferServer objects;
bool running = false;
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
    SecurityConfig config;
    config.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurity);
    const uint8_t greeting[] = "Hello from the object server";
    uint64_t id = 0U;
    running = BLESecurity.begin(config) && BLEDevice.begin("NU54-OBJECT") && objects.begin() &&
              objects.add("greeting.txt", greeting, sizeof(greeting) - 1U, true, true, id) &&
              BLEAdvertising.clear() && BLEAdvertising.addServiceUuid(BLEUuid(0x1825U)) &&
              BLEAdvertising.start();
    Serial.println(running ? "object server ready" : "object server failed");
}
void loop()
{
    if (!running)
    {
        return;
    }
    BLEDevice.poll();
    BLESecurity.poll();
    ObjectEvent event;
    while (objects.readEvent(event))
    {
        if (event.type == ObjectEventType::received)
        {
            Serial.print("client object payload: ");
            Serial.write(event.data, event.length);
            Serial.println();
        }
        else if (event.type == ObjectEventType::created || event.type == ObjectEventType::deleted)
        {
            Serial.print(event.type == ObjectEventType::created ? "created object: "
                                                                : "deleted object: ");
            Serial.println(static_cast<uint32_t>(event.id));
        }
    }
    if (Serial.available() > 0 && Serial.read() == 's')
    {
        BLEDevice.end();
        running = false;
        Serial.println("object server stopped; reset to restart");
    }
}
