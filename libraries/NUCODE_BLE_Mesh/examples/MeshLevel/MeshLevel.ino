/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) Generic Level Client; 2) AppKey가 bind된 Generic Level Server
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * destination group 0xC000에 client publish와 server subscribe를 구성합니다.
 * @par Metadata
 * identity `NUCODE_BLE_Mesh/MeshLevel`, sha256 `46554f48811d1150a0c2d728721dda371bee63e395f84a4a977695fbc1be125d`
 * @nucode_example_setup_end */

/**
 * @file MeshLevel.ino
 * @brief Generic Level Set으로 그룹의 signed level을 왕복시킵니다.
 */

#include <NUCODE_BLE_Mesh.h>

nucode::mesh::Destination destination{};
unsigned long lastSend = 0UL;
std::int16_t level = -20000;

void setup()
{
    Serial.begin(115200);
    nucode::mesh::Configuration configuration{};
    configuration.uuid[0] = 0x54U;
    configuration.uuid[1] = 0x22U;
    if (!NUCODEMesh.begin(configuration))
    {
        Serial.println("Level client start failed");
    }
}

void loop()
{
    NUCODEMesh.poll();
    if (NUCODEMesh.provisioned() && millis() - lastSend >= 5000UL)
    {
        lastSend = millis();
        level = static_cast<std::int16_t>(-level);
        static_cast<void>(NUCODEMesh.sendLevel(destination, level, true));
    }
}
