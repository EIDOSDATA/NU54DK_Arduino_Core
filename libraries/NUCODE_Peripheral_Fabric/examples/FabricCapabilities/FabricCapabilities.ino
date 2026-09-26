/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Peripheral Fabric (DAP UART disconnected) (`fabric`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) FabricCapabilities 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * DAP UART 공유 핀을 분리하고 예제가 요구하는 외장 I/O 결선을 확인합니다.
 * @par Metadata
 * identity `NUCODE_Peripheral_Fabric/FabricCapabilities`, sha256 `8dbe28b713e4292535ff6391ef34999c84601a5974e6574ee77780a74f40c776`
 * @nucode_example_setup_end */

#include <NUCODE_Peripheral_Fabric.h>

namespace
{
    volatile bool fabric_ready = false;
}

void setup()
{
    using namespace nucode::arduino;
    using namespace nucode::peripheral;

    const bool serial_ready =
        serialFabric().uarte(0U) != nullptr && serialFabric().spim(0U) != nullptr &&
        serialFabric().spis(0U) != nullptr && serialFabric().twim(20U) != nullptr &&
        serialFabric().twis(20U) != nullptr;
    const bool analog_ready = analogFabric().pwm(20U) != nullptr;
    const bool event_ready =
        eventFabric().timer(20U) != nullptr && eventFabric().egu(20U) != nullptr &&
        eventFabric().gpiote(20U) != nullptr && eventFabric().dppi(20U) != nullptr &&
        eventFabric().ppib(20U) != nullptr;
    const bool stream_ready =
        streamFabric().pdm(20U) != nullptr && streamFabric().i2s(20U) != nullptr &&
        streamFabric().qdec(20U) != nullptr && streamFabric().qdec(21U) != nullptr;
    const bool system_ready = systemFabric().watchdog(30U) != nullptr;
    const bool inventory_ready = peripheralInventorySize() == 75U;

    fabric_ready = serial_ready && analog_ready && event_ready && stream_ready && system_ready &&
                   inventory_ready && isSupported(capabilities.serial) &&
                   isSupported(capabilities.analog) && isSupported(capabilities.event) &&
                   isSupported(capabilities.pdm) && isSupported(capabilities.i2s) &&
                   isSupported(capabilities.qdec) && isSupported(capabilities.system);

    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, fabric_ready ? HIGH : LOW);
}

void loop()
{
    delay(1000U);
}
