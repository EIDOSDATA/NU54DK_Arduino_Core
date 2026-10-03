/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Generic OnOff Client; 2) AppKey가 bind된 Generic OnOff Server
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * destination group 0xC000에 client publish와 server subscribe를 구성합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh/MeshOnOff`, sha256 `55aec8a0453380b71c486ead5ec032b7c9de541dac066ac19ad0e0e2a94f117d`
 * @nucode_example_setup_end */

/**
 * @file MeshOnOff.ino
 * @brief Generic OnOff acknowledged와 unacknowledged 전송을 번갈아 실행합니다.
 */

#include <NUCODE_BLE_Mesh.h>

nucode::mesh::Destination destination{};
unsigned long lastSend = 0UL;
bool enabled = false;

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x21U;
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("OnOff client start failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    if (NUCODEMesh.provisioned() && millis() - lastSend >= 5000UL)
    {
        lastSend = millis();
        enabled = !enabled;
        if (!NUCODEMesh.sendOnOff(destination, enabled, enabled))
        {
            Serial.println("OnOff send failed; verify AppKey binding");
        }
    }
}
