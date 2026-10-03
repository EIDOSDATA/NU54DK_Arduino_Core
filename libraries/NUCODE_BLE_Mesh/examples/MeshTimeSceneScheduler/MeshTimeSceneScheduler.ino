/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Time/Scene/Scheduler Client; 2) AppKey가 bind된 Time/Scene/Scheduler Server
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * destination group 0xC000과 scene 1을 server에 미리 구성합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh/MeshTimeSceneScheduler`, sha256 `822eb2bb25f528e016af8f2adfaa166ff049ff90885d79b324162be122aac5c5`
 * @nucode_example_setup_end */

/**
 * @file MeshTimeSceneScheduler.ino
 * @brief Time, Scene Recall과 Scheduler Get 표준 client model을 순환 검증합니다.
 */

#include <NUCODE_BLE_Mesh.h>

nucode::mesh::Destination destination{};
unsigned long lastRequest = 0UL;
std::uint8_t requestIndex = 0U;

/** @brief 수신 표준 model status 종류를 출력합니다. */
void onMeshEvent(const nucode::mesh::EventRecord &record, void *context)
{
    static_cast<void>(context);
    if (record.event == nucode::mesh::Event::model_status)
    {
        Serial.print("Model status: ");
        Serial.println(static_cast<unsigned int>(record.model));
    }
}

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x25U;
    NUCODEMesh.onEvent(onMeshEvent);
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("Time/Scene/Scheduler client start failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    if (!NUCODEMesh.provisioned() || millis() - lastRequest < 5000UL)
    {
        return;
    }
    lastRequest = millis();
    if (requestIndex == 0U)
    {
        static_cast<void>(NUCODEMesh.requestTime(destination));
    }
    else if (requestIndex == 1U)
    {
        static_cast<void>(NUCODEMesh.recallScene(destination, 1U, true));
    }
    else
    {
        static_cast<void>(NUCODEMesh.requestSchedule(destination));
    }
    requestIndex = static_cast<std::uint8_t>((requestIndex + 1U) % 3U);
}
