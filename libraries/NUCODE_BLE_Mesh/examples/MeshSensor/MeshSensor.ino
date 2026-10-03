/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Sensor Client; 2) AppKey가 bind된 Sensor Server
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * destination group 0xC000을 구성하고 Sensor Status는 32-byte snapshot으로 관찰합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh/MeshSensor`, sha256 `738e64fcdf44c1620ba203807d3475651d2dea60843ff07013bccd57eea2e674`
 * @nucode_example_setup_end */

/**
 * @file MeshSensor.ino
 * @brief Sensor Get과 bounded raw Sensor Status callback을 사용합니다.
 */

#include <NUCODE_BLE_Mesh.h>

nucode::mesh::Destination destination{};
unsigned long lastRequest = 0UL;

/** @brief Sensor Status의 원본 길이와 truncation 여부를 출력합니다. */
void onMeshEvent(const nucode::mesh::EventRecord &record, void *context)
{
    static_cast<void>(context);
    if (record.event == nucode::mesh::Event::model_status &&
        record.model == nucode::mesh::Model::sensor)
    {
        Serial.print("Sensor status bytes: ");
        Serial.println(record.payload_size);
        if (record.payload_truncated)
        {
            Serial.println("Sensor status truncated to bounded snapshot");
        }
    }
}

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x24U;
    NUCODEMesh.onEvent(onMeshEvent);
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("Sensor client start failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    if (NUCODEMesh.provisioned() && millis() - lastRequest >= 5000UL)
    {
        lastRequest = millis();
        static_cast<void>(NUCODEMesh.requestSensor(destination));
    }
}
