/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
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
 * @par Metadata
 * identity `NUCODE_BLE_Profiles/ObjectServer`, sha256 `96b4e3bc5c4912f284a1e4c1d5f88f44b3b2aab97d433b08d409e0b1ec4777c6`
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
