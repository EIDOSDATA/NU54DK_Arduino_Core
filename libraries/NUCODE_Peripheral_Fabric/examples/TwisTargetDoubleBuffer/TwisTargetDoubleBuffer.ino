/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 두 TX/RX buffer를 예약해 외부 I2C controller의 두 write/read를 처리합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Peripheral Fabric (DAP UART disconnected) (`fabric`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) TWIS21 target 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 3.3 V I2C controller·외부 pull-up·공통 GND를 준비하고 DAP UART 경로를 물리 분리합니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) TWIS21 target 보드
 * - 3.3 V I2C controller·외부 pull-up·공통 GND를 준비하고 DAP UART 경로를 물리 분리합니다.
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
 * - `NUCODE_Peripheral_Fabric/UarteAsyncEcho`
 * - `NUCODE_Peripheral_Fabric/AdcContinuousDma`
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
 * identity `NUCODE_Peripheral_Fabric/TwisTargetDoubleBuffer`, sha256 `33459d9489b6283321c29a0c6ee76e3f6dad0c7399a5a96c47b55ff4cc2f126e`
 * @nucode_example_setup_end */

/**
 * @file TwisTargetDoubleBuffer.ino
 * @brief 두 TX/RX buffer를 예약해 외부 I2C controller의 두 write/read를 처리합니다.
 * @details fabric profile과 DAP UART 분리·외부 pull-up을 먼저 확인합니다.
 * SPDX-License-Identifier: MIT
 */
#include <NUCODE_Peripheral_Fabric.h>

namespace
{
    using namespace nucode::arduino;
    alignas(4) std::uint8_t buffers[4][16]{};
    const SerialSignalPin pins[] = {{SerialSignal::sda, PIN_P1_04}, {SerialSignal::scl, PIN_P1_05}};
    const SerialDmaWorkspace memory[] = {{buffers, sizeof(buffers)}};
    TwisHandle *port = nullptr;
    bool running = false;
    bool failed = false;
    bool previous_button = false;
    std::uint32_t started = 0U;
    volatile unsigned int reads = 0U;
    volatile unsigned int writes = 0U;
    volatile std::uint32_t received_sum = 0U;
    volatile bool completed = false;
    volatile SerialFabricResult last_result = SerialFabricResult::success;
    volatile SerialFabricResult stop_result = SerialFabricResult::success;

    /** @brief 네 buffer는 cancel/deactivate가 성공할 때까지 정적으로 보존합니다. */
    void finish(bool success)
    {
        if (port != nullptr && port->state() == SerialFabricState::active)
        {
            (void)port->cancelBuffers();
            stop_result = port->deactivate(100000U);
        }
        running = false;
        failed = !success || stop_result != SerialFabricResult::success;
        completed = !failed;
        digitalWrite(LED_BUILTIN, completed ? HIGH : LOW);
    }

    /** @brief 첫/둘째 read의 payload를 sketch에서 작성해 각각 예약합니다. */
    void startSession()
    {
        completed = false;
        reads = 0U;
        writes = 0U;
        received_sum = 0U;
        digitalWrite(LED_BUILTIN, LOW);
        for (std::size_t index = 0U; index < 16U; ++index)
        {
            buffers[0][index] = static_cast<std::uint8_t>(0x10U + index);
            buffers[1][index] = static_cast<std::uint8_t>(0x80U + index);
            buffers[2][index] = 0U;
            buffers[3][index] = 0U;
        }
        const SerialFabricConfiguration route{SerialRouteClass::p1_flexible,
                                              SerialElectricalProfile::dap_uart_disabled,
                                              pins,
                                              2U,
                                              memory,
                                              1U};
        last_result = port->configure({0x42U, 0U, false});
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
            last_result = port->queueBuffers(buffers[0], 16U, buffers[2], 16U, buffers[1], 16U,
                                             buffers[3], 16U);
        }
        running = last_result == SerialFabricResult::success;
        started = millis();
        if (!running)
        {
            finish(false);
        }
    }
} // namespace

/** @brief 버튼 입력 전에는 target 주소를 bus에 노출하지 않습니다. */
void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);
    pinMode(PIN_BUTTON0, INPUT_PULLUP);
    port = serialFabric().twis(21U);
    failed = port == nullptr;
    previous_button = digitalRead(PIN_BUTTON0) == LOW;
}

/** @brief 완료된 RX만 읽고 더 많은 transaction이나 5초 초과는 종료합니다. */
void loop()
{
    const bool pressed = digitalRead(PIN_BUTTON0) == LOW;
    if (pressed && !previous_button && !running && !failed)
    {
        startSession();
    }
    previous_button = pressed;
    TwiFabricEvent event{};
    for (unsigned int count = 0U; running && count < 16U && port->takeEvent(event); ++count)
    {
        if (event.type == TwiFabricEventType::read_complete)
        {
            if (reads >= 2U || event.tx_buffer != buffers[reads] || event.tx_transferred != 16U)
            {
                finish(false);
                break;
            }
            ++reads;
        }
        else if (event.type == TwiFabricEventType::write_complete)
        {
            if (writes >= 2U || event.rx_buffer != buffers[2U + writes] ||
                event.rx_transferred != 16U)
            {
                finish(false);
                break;
            }
            const auto *received = static_cast<const std::uint8_t *>(event.rx_buffer);
            for (std::size_t index = 0U; index < event.rx_transferred; ++index)
            {
                received_sum += received[index];
            }
            ++writes;
        }
        else if (event.type == TwiFabricEventType::error ||
                 event.type == TwiFabricEventType::overrun ||
                 event.type == TwiFabricEventType::bus_error ||
                 event.type == TwiFabricEventType::transfer_cancelled)
        {
            finish(false);
        }
        if (running && reads == 2U && writes == 2U)
        {
            finish(true);
        }
    }
    if (running && static_cast<std::uint32_t>(millis() - started) >= 5000U)
    {
        finish(false);
    }
    delay(1U);
}
