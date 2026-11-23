/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * OTS 목록·metadata·CoC read/write와 object 생성·삭제를 수행합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) OTC object client; 2) ObjectServer
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 단일 암호화 연결에서 Serial 명령으로 metadata/read/write/create/name/delete를 하나씩 요청합니다. checksum·execute·append/truncate는 지원 범위가 아닙니다.
 * @par 준비물
 * - NU54DK 보드 2대 — 1) OTC object client; 2) ObjectServer
 * - 단일 암호화 연결에서 Serial 명령으로 metadata/read/write/create/name/delete를 하나씩 요청합니다. checksum·execute·append/truncate는 지원 범위가 아닙니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `object client ready: f/n/m/r/w/c/t/d/s`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `metadata:`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `bytes=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `object connect failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `security request failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `object discovery failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Profiles/ObjectServer`
 * - `NUCODE_BLE_Profiles/StandardCollector`
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
 * identity `NUCODE_BLE_Profiles/ObjectClient`, sha256 `039fe6bc791c09998f24f00e873bce08a6d2ff900e55ca49381b37fa5f23505e`
 * @nucode_example_setup_end */

/**
 * @file ObjectClient.ino
 * @brief OTS 목록·metadata·CoC read/write와 object 생성·삭제를 수행합니다.
 * @par 목적
 * 표준 OTC 동작을 Serial 명령으로 시작하고 사용자 payload를 .ino에서 수정합니다.
 * @par 준비물
 * NU54DK 2대: ObjectServer와 이 client.
 * @par 설정
 * Feature set BLE NUS, 동봉 prj.conf, 115200 baud, 단일 link 구성입니다.
 * @par 실행 순서
 * server 먼저 시작. ready 뒤 f 첫 object, n 다음, m metadata, r 읽기, w 쓰기,
 * c 생성, t 이름 설정, d 삭제, s 중단. 각 완료 출력 뒤 다음 명령을 보냅니다.
 * @par 성공 출력
 * object client ready, metadata, object payload, object operation complete를 확인합니다.
 * @par 흔한 오류
 * write 전에 metadata가 필요합니다. 진행 중 요청은 거부하며 10초 timeout은 연결을 종료합니다.
 * @par 다음 예제
 * ObjectServer와 StandardCollector를 참고합니다. 재연결은 reset 후 수행할 수 있습니다.
 */
#include <NUCODE_BLE_ObjectTransfer.h>
#include <NUCODE_BLE_Security.h>
using namespace nucode::ble;
using namespace nucode::ble::profiles;
ObjectTransferClient objects;
BLEConnectionHandle peer;
bool running = false;
bool startObjects = false;
void onScan(const BLEScanResult &result, void *)
{
    if (!peer.valid() && result.connectable)
    {
        if (!BLEScan.stop() || !BLEConnection.connect(result.address, peer))
        {
            Serial.println("object connect failed");
        }
    }
}
void onLink(const BLEEventInfo &event, void *)
{
    if (event.connection == peer && event.event == BLEEvent::connected)
    {
        if (!BLESecurity.requestSecurity(peer))
        {
            Serial.println("security request failed");
        }
    }
}
void onSecurity(const SecurityEventRecord &event, void *)
{
    if (event.event == SecurityEvent::pairing_requested)
    {
        static_cast<void>(BLESecurity.acceptPairing(event.connection, true));
    }
    if (event.connection == peer && event.event == SecurityEvent::security_changed &&
        event.level >= SecurityLevel::encrypted)
    {
        startObjects = true;
    }
}
void setup()
{
    Serial.begin(115200);
    SecurityConfig config;
    config.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurity);
    BLEDevice.onEventInfo(onLink);
    BLEScan.onResult(onScan);
    running = BLESecurity.begin(config) && BLEDevice.begin("NU54-OBJECT-C") &&
              BLEScan.filterServiceUuid(BLEUuid(0x1825U)) && BLEScan.start(true);
    Serial.println(running ? "object client scanning" : "object client failed");
}
void loop()
{
    if (!running)
    {
        return;
    }
    BLEDevice.poll();
    BLESecurity.poll();
    objects.poll();
    if (startObjects)
    {
        startObjects = false;
        if (!objects.begin(peer))
        {
            Serial.println("object discovery failed");
        }
    }
    ObjectEvent event;
    while (objects.readEvent(event))
    {
        if (event.type == ObjectEventType::ready)
        {
            Serial.println("object client ready: f/n/m/r/w/c/t/d/s");
        }
        else if (event.type == ObjectEventType::metadata)
        {
            Serial.print("metadata: ");
            Serial.print(event.name);
            Serial.print(" bytes=");
            Serial.println(event.length);
        }
        else if (event.type == ObjectEventType::received)
        {
            Serial.print("object payload: ");
            Serial.write(event.data, event.length);
            Serial.println();
        }
        else if (event.type == ObjectEventType::error ||
                 event.type == ObjectEventType::disconnected)
        {
            Serial.print("object operation failed/disconnected: ");
            Serial.println(event.status);
        }
        else
        {
            Serial.print("object operation complete: ");
            Serial.println(event.status);
        }
    }
    if (Serial.available() <= 0)
    {
        return;
    }
    const int command = Serial.read();
    const uint8_t message[] = "Message written by Arduino";
    bool accepted = false;
    switch (command)
    {
    case 'f':
        accepted = objects.selectFirst();
        break;
    case 'n':
        accepted = objects.selectNext();
        break;
    case 'm':
        accepted = objects.metadata();
        break;
    case 'r':
        accepted = objects.read();
        break;
    case 'w':
        accepted = objects.write(message, sizeof(message) - 1U);
        break;
    case 'c':
        accepted = objects.create(512U);
        break;
    case 't':
        accepted = objects.rename("arduino.txt");
        break;
    case 'd':
        accepted = objects.remove();
        break;
    case 's':
        accepted = objects.cancel();
        break;
    default:
        return;
    }
    Serial.println(accepted ? "object request queued" : "object request rejected");
}
