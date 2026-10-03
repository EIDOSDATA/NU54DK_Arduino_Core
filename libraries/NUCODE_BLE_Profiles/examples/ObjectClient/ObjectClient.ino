/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
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
 * @par Metadata
 * identity `NUCODE_BLE_Profiles/ObjectClient`, sha256 `28b721d6aed536a87c9b797d568dde9df0af4f3564d44744995eac2c95a54f97`
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
