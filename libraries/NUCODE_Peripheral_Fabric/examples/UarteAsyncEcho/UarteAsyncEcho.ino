/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 외부 UART의 32-byte 입력을 비동기로 수신하고 그대로 반환합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Peripheral Fabric (DAP UART disconnected) (`fabric`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) UARTE20 async echo 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 3.3 V USB-UART peer와 공통 GND를 사용하며 5 V 신호를 연결하지 않습니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) UARTE20 async echo 보드
 * - 3.3 V USB-UART peer와 공통 GND를 사용하며 5 V 신호를 연결하지 않습니다.
 * @par 설정
 * - Tools → Feature set에서 `fabric` profile을 선택합니다.
 * - 이 예제는 Serial Monitor 출력을 필수 결과로 사용하지 않습니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - 목적에 적힌 LED·pin·peer 동작을 직접 확인합니다. Compile PASS만으로 runtime PASS로 처리하지 않습니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * @par 다음 예제
 * - `NUCODE_Peripheral_Fabric/AdcContinuousDma`
 * - `NUCODE_Peripheral_Fabric/FabricCapabilities`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - no_security_property_claimed
 * - 이 예제는 별도의 보안 속성을 주장하지 않습니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `peripheral_fabric`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_Peripheral_Fabric/UarteAsyncEcho`, sha256 `3a5826c1d45da7a62669e904def5bd2b9a8ed5b836a6628eede67fa136fb75f2`
 * @nucode_example_setup_end */

/**
 * @file UarteAsyncEcho.ino
 * @brief 외부 UART의 32-byte 입력을 비동기로 수신하고 그대로 반환합니다.
 * @details fabric profile과 README의 결선을 확인한 후 BUTTON0을 누릅니다.
 *          Serial Monitor는 사용하지 않습니다. DMA buffer는 종료 확인까지 유지합니다.
 * SPDX-License-Identifier: MIT
 */
#include <NUCODE_Peripheral_Fabric.h>

namespace
{
    using namespace nucode::arduino;
    alignas(4) std::uint8_t payload[32]{};
    const SerialSignalPin pins[] = {{SerialSignal::txd, PIN_P2_02}, {SerialSignal::rxd, PIN_P2_00}};
    const SerialDmaWorkspace memory[] = {{payload, sizeof(payload)}};
    UarteHandle *port = nullptr;
    bool running = false;
    bool failed = false;
    bool previous_button = false;
    bool transmitting = false;
    std::uint32_t started = 0U;
    volatile std::size_t echoed_bytes = 0U;
    volatile bool completed = false;
    volatile SerialFabricResult last_result = SerialFabricResult::success;
    volatile SerialFabricResult stop_result = SerialFabricResult::success;

    /** @brief STOP 성공 전에는 buffer를 다시 쓰거나 새 세션을 시작하지 않습니다. */
    void finish(bool success)
    {
        if (port != nullptr && port->state() == SerialFabricState::active)
        {
            if (transmitting)
            {
                (void)port->cancelTransmit();
            }
            (void)port->cancelReceive();
            stop_result = port->deactivate(100000U);
        }
        running = false;
        failed = !success || stop_result != SerialFabricResult::success;
        completed = !failed;
        digitalWrite(LED_BUILTIN, completed ? HIGH : LOW);
    }

    /** @brief 사용자 payload를 받을 RAM을 먼저 lease한 뒤 수신을 시작합니다. */
    void startSession()
    {
        completed = false;
        echoed_bytes = 0U;
        transmitting = false;
        digitalWrite(LED_BUILTIN, LOW);
        const SerialFabricConfiguration route{SerialRouteClass::p2_dedicated20,
                                              SerialElectricalProfile::connector_fixture,
                                              pins,
                                              2U,
                                              memory,
                                              1U};
        last_result = port->configure({115200U, UarteParity::none, false, false});
        if (last_result == SerialFabricResult::success)
        {
            last_result = port->stage(route);
        }
        if (last_result == SerialFabricResult::success)
        {
            last_result = port->activate();
        }
        if (last_result == SerialFabricResult::success)
        {
            last_result = port->receiveAsync(payload, sizeof(payload));
        }
        running = last_result == SerialFabricResult::success;
        started = millis();
        if (!running)
        {
            finish(false);
        }
    }
} // namespace

/** @brief factory 조회와 사용자 시작 버튼만 준비하며 UART를 자동 시작하지 않습니다. */
void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);
    pinMode(PIN_BUTTON0, INPUT_PULLUP);
    port = serialFabric().uarte(20U);
    failed = port == nullptr;
    previous_button = digitalRead(PIN_BUTTON0) == LOW;
}

/** @brief 실제 RX/TX 완료를 처리하고 3초 deadline 뒤에는 취소·해제합니다. */
void loop()
{
    const bool pressed = digitalRead(PIN_BUTTON0) == LOW;
    if (pressed && !previous_button && !running && !failed)
    {
        startSession();
    }
    previous_button = pressed;
    UarteEvent event{};
    for (unsigned int count = 0U; running && count < 16U && port->takeEvent(event); ++count)
    {
        if (event.type == UarteEventType::rx_complete)
        {
            if (event.buffer != payload || event.transferred != sizeof(payload))
            {
                finish(false);
                break;
            }
            /** @brief 수신 완료로 반환된 RAM을 수정하지 않고 TX DMA에 전달합니다. */
            last_result = port->transmitAsync(payload, event.transferred);
            transmitting = last_result == SerialFabricResult::success;
            if (!transmitting)
            {
                finish(false);
            }
        }
        else if (event.type == UarteEventType::tx_complete)
        {
            echoed_bytes = event.transferred;
            transmitting = false;
            finish(event.buffer == payload && event.transferred == sizeof(payload));
        }
        else if (event.type == UarteEventType::error ||
                 event.type == UarteEventType::rx_cancelled ||
                 event.type == UarteEventType::tx_cancelled)
        {
            finish(false);
        }
    }
    if (running && static_cast<std::uint32_t>(millis() - started) >= 3000U)
    {
        finish(false);
    }
    delay(1U);
}
