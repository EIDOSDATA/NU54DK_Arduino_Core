/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 내부 VDD 입력을 연속 double-buffer로 받아 반환된 RAM을 재사용합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Peripheral Fabric (DAP UART disconnected) (`fabric`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) SAADC continuous DMA 실행 보드
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 외부 analog 결선 없이 내부 VDD만 측정하며 raw 평균을 교정된 전압으로 해석하지 않습니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) SAADC continuous DMA 실행 보드
 * - 외부 analog 결선 없이 내부 VDD만 측정하며 raw 평균을 교정된 전압으로 해석하지 않습니다.
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
 * - `NUCODE_Peripheral_Fabric/FabricCapabilities`
 * - `NUCODE_Peripheral_Fabric/PwmSequencePlayback`
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
 * identity `NUCODE_Peripheral_Fabric/AdcContinuousDma`, sha256 `1ca04653d3332b84a493b335d692825f542bd72ffd2af7f0709f8b7dfb19b25f`
 * @nucode_example_setup_end */

/**
 * @file AdcContinuousDma.ino
 * @brief 내부 VDD 입력을 연속 double-buffer로 받아 반환된 RAM을 재사용합니다.
 * @details raw 평균은 교정된 전압 측정이 아닙니다. 외부 analog 입력은 연결하지 않습니다.
 * SPDX-License-Identifier: MIT
 */
#include <NUCODE_Peripheral_Fabric.h>

namespace
{
    using namespace nucode::arduino;
    alignas(4) std::int16_t samples[2][128]{};
    const SaadcChannelConfiguration channel{SaadcInput::vdd, SaadcInput::disabled,
                                            SaadcGain::one_quarter};
    bool running = false;
    bool failed = false;
    bool previous_button = false;
    std::uint32_t started = 0U;
    volatile unsigned int completed_buffers = 0U;
    volatile std::int32_t average_raw = 0;
    volatile bool completed = false;
    volatile AnalogFabricResult last_result = AnalogFabricResult::success;
    volatile AnalogFabricResult stop_result = AnalogFabricResult::success;

    /** @brief STOP 실패 시 DMA RAM을 보존하고 reset 전 재시작을 금지합니다. */
    void finish(bool success)
    {
        auto &adc = analogFabric().saadc();
        if (adc.state() == AnalogFabricState::active || adc.state() == AnalogFabricState::stopping)
        {
            stop_result = adc.stop(100000U);
        }
        running = false;
        failed = !success || stop_result != AnalogFabricResult::success;
        completed = !failed;
        digitalWrite(LED_BUILTIN, completed ? HIGH : LOW);
    }

    /** @brief 고정 nrfx 내부 timer의 최대 128 us 간격으로 두 정적 buffer를 준비합니다. */
    void startSession()
    {
        auto &adc = analogFabric().saadc();
        completed = false;
        completed_buffers = 0U;
        average_raw = 0;
        digitalWrite(LED_BUILTIN, LOW);
        last_result = adc.configure({&channel, 1U, 12U, 1U, 128U});
        if (last_result == AnalogFabricResult::success)
        {
            last_result = adc.start(samples[0], 128U, samples[1], 128U);
        }
        running = last_result == AnalogFabricResult::success;
        started = millis();
        if (!running)
        {
            finish(false);
        }
    }
} // namespace

/** @brief 버튼을 누르기 전에는 ADC를 시작하지 않습니다. */
void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);
    pinMode(PIN_BUTTON0, INPUT_PULLUP);
    previous_button = digitalRead(PIN_BUTTON0) == LOW;
}

/** @brief 8개 완료 buffer를 처리하고 정상 STOP 후 버튼으로 다시 시작할 수 있습니다. */
void loop()
{
    const bool pressed = digitalRead(PIN_BUTTON0) == LOW;
    if (pressed && !previous_button && !running && !failed)
    {
        startSession();
    }
    previous_button = pressed;
    auto &adc = analogFabric().saadc();
    SaadcEvent event{};
    for (unsigned int count = 0U; running && count < 16U && adc.takeEvent(event); ++count)
    {
        if (event.type == SaadcEventType::buffer_complete)
        {
            if ((event.buffer != samples[0] && event.buffer != samples[1]) || event.samples != 128U)
            {
                finish(false);
                break;
            }
            std::int32_t sum = 0;
            for (std::size_t index = 0U; index < event.samples; ++index)
            {
                sum += event.buffer[index];
            }
            average_raw = sum / static_cast<std::int32_t>(event.samples);
            ++completed_buffers;
            if (completed_buffers == 8U)
            {
                finish(true);
            }
            else
            {
                /** @brief takeEvent가 소유권을 반환한 완료 buffer만 다시 queue합니다. */
                last_result = adc.queueBuffer(event.buffer, event.samples);
                if (last_result != AnalogFabricResult::success)
                {
                    finish(false);
                }
            }
        }
        else if (event.type == SaadcEventType::error || event.type == SaadcEventType::finished)
        {
            finish(false);
        }
    }
    if (running && static_cast<std::uint32_t>(millis() - started) >= 2000U)
    {
        finish(false);
    }
    delay(1U);
}
