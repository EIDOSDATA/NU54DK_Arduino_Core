/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 외부 MOSI-MISO jumper를 통해 비동기 SPI payload를 비교합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Peripheral Fabric (DAP UART disconnected) (`fabric`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) SPIM20 async loopback 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 전원을 끈 상태에서 P2.02(MOSI)와 P2.04(MISO)를 연결하고 P2.01(SCK)에 다른 output을 연결하지 않습니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) SPIM20 async loopback 보드
 * - 전원을 끈 상태에서 P2.02(MOSI)와 P2.04(MISO)를 연결하고 P2.01(SCK)에 다른 output을 연결하지 않습니다.
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
 * - `NUCODE_Peripheral_Fabric/TwisTargetDoubleBuffer`
 * - `NUCODE_Peripheral_Fabric/UarteAsyncEcho`
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
 * identity `NUCODE_Peripheral_Fabric/SpiAsyncLoopback`, sha256 `2318772d66b28e19cd75ded2bd2d704cb4aaefbe0ba32898555018f18b1483f6`
 * @nucode_example_setup_end */

/**
 * @file SpiAsyncLoopback.ino
 * @brief 외부 MOSI-MISO jumper를 통해 비동기 SPI payload를 비교합니다.
 * @details fabric profile, README의 전기 조건과 결선을 확인한 뒤 BUTTON0을 누릅니다.
 * SPDX-License-Identifier: MIT
 */
#include <NUCODE_Peripheral_Fabric.h>

namespace
{
    using namespace nucode::arduino;
    alignas(4) std::uint8_t tx[32]{};
    alignas(4) std::uint8_t rx[32]{};
    const SerialSignalPin pins[] = {{SerialSignal::sck, PIN_P2_01},
                                    {SerialSignal::mosi, PIN_P2_02},
                                    {SerialSignal::miso, PIN_P2_04}};
    const SerialDmaWorkspace memory[] = {{tx, sizeof(tx)}, {rx, sizeof(rx)}};
    SpimHandle *port = nullptr;
    bool running = false;
    bool failed = false;
    bool previous_button = false;
    std::uint32_t started = 0U;
    std::uint8_t generation = 0U;
    volatile bool completed = false;
    volatile std::size_t matched_bytes = 0U;
    volatile SerialFabricResult last_result = SerialFabricResult::success;
    volatile SerialFabricResult stop_result = SerialFabricResult::success;

    /** @brief 취소 후 실제 lifecycle 해제를 확인하고 실패 시 재시작을 막습니다. */
    void finish(bool success)
    {
        if (port != nullptr && port->state() == SerialFabricState::active)
        {
            (void)port->cancelTransfer();
            stop_result = port->deactivate(100000U);
        }
        running = false;
        failed = !success || stop_result != SerialFabricResult::success;
        completed = !failed;
        digitalWrite(LED_BUILTIN, completed ? HIGH : LOW);
    }

    /** @brief application이 payload를 만들며 DMA 실행 중에는 두 buffer를 유지합니다. */
    void startSession()
    {
        completed = false;
        matched_bytes = 0U;
        digitalWrite(LED_BUILTIN, LOW);
        for (std::size_t index = 0U; index < sizeof(tx); ++index)
        {
            tx[index] = static_cast<std::uint8_t>(index ^ generation ^ 0x5AU);
            rx[index] = 0U;
        }
        ++generation;
        const SerialFabricConfiguration route{SerialRouteClass::p2_dedicated20,
                                              SerialElectricalProfile::connector_fixture,
                                              pins,
                                              3U,
                                              memory,
                                              2U};
        last_result =
            port->configure({1000000U, SpiFabricMode::mode0, SpiFabricBitOrder::msb_first, 0xFFU});
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
            last_result = port->transferAsync(tx, sizeof(tx), rx, sizeof(rx));
        }
        running = last_result == SerialFabricResult::success;
        started = millis();
        if (!running)
        {
            finish(false);
        }
    }
} // namespace

/** @brief 시작 버튼과 정적 handle만 준비합니다. */
void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);
    pinMode(PIN_BUTTON0, INPUT_PULLUP);
    port = serialFabric().spim(20U);
    failed = port == nullptr;
    previous_button = digitalRead(PIN_BUTTON0) == LOW;
}

/** @brief 실제 완료 길이·buffer identity·전체 payload를 검사합니다. */
void loop()
{
    const bool pressed = digitalRead(PIN_BUTTON0) == LOW;
    if (pressed && !previous_button && !running && !failed)
    {
        startSession();
    }
    previous_button = pressed;
    SpiFabricEvent event{};
    for (unsigned int count = 0U; running && count < 16U && port->takeEvent(event); ++count)
    {
        if (event.type == SpiFabricEventType::transfer_complete)
        {
            bool identical = event.tx_buffer == tx && event.rx_buffer == rx &&
                             event.tx_transferred == sizeof(tx) &&
                             event.rx_transferred == sizeof(rx);
            for (std::size_t index = 0U; identical && index < sizeof(tx); ++index)
            {
                identical = tx[index] == rx[index];
                if (identical)
                {
                    ++matched_bytes;
                }
            }
            finish(identical);
        }
        else if (event.type == SpiFabricEventType::error ||
                 event.type == SpiFabricEventType::transfer_cancelled)
        {
            finish(false);
        }
    }
    if (running && static_cast<std::uint32_t>(millis() - started) >= 1000U)
    {
        finish(false);
    }
    delay(1U);
}
