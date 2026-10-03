/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Light Lightness Client; 2) AppKey가 bind된 Light Lightness Server
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * destination group 0xC000과 reliable segmented transport를 허용합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh/MeshLight`, sha256 `5a8f870e9e57f3f7ae680df449109c7f47c57615e44b193fc851499a419f7d87`
 * @nucode_example_setup_end */

/**
 * @file MeshLight.ino
 * @brief Light Lightness Set을 reliable segmented transport로 전송합니다.
 */

#include <NUCODE_BLE_Mesh.h>

nucode::mesh::Destination destination{};
unsigned long lastSend = 0UL;
std::uint16_t lightness = 8000U;

void setup()
{
    Serial.begin(115200);
    destination.force_segment_acknowledgment = true;
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x23U;
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("Lightness client start failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    if (NUCODEMesh.provisioned() && millis() - lastSend >= 5000UL)
    {
        lastSend = millis();
        lightness = lightness == 8000U ? 50000U : 8000U;
        static_cast<void>(NUCODEMesh.sendLightness(destination, lightness, true));
    }
}
