/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 외부 PDM microphone의 PCM을 LC3 unicast source로 전송합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE Audio external I/O (DAP UART disconnected) (`ble_audio_io`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) ExternalPdmMicrophoneSource (source/transmitter); 2) ExternalI2sSpeakerSink (sink/receiver)
 * @par Serial Monitor
 * 사용하지 않음
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * DAP UART를 분리하고 PDM 또는 I2S 외장 장치의 전압·clock·GND 결선을 확인합니다.
 * @par 준비물
 * - NU54DK 보드 2대 — 1) ExternalPdmMicrophoneSource (source/transmitter); 2) ExternalI2sSpeakerSink (sink/receiver)
 * - DAP UART를 분리하고 PDM 또는 I2S 외장 장치의 전압·clock·GND 결선을 확인합니다.
 * @par 설정
 * - Tools → Feature set에서 `ble_audio_io` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: prj.conf
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
 * - `NUCODE_BLE_Audio/GamingAudioBroadcaster`
 * - `NUCODE_BLE_Audio/GamingAudioGateway`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - wireless_example_no_implicit_security_claim
 * - 무선 연결 성공만으로 인증·암호화·상호운용 보안을 주장하지 않습니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `ble_audio`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_Audio/ExternalPdmMicrophoneSource`, sha256 `076061fcbf8c15278a0276ea6d04740a1b51da56685830ad03c2f464a90b679d`
 * @nucode_example_setup_end */

/**
 * @file ExternalPdmMicrophoneSource.ino
 * @brief 외부 PDM microphone의 PCM을 LC3 unicast source로 전송합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_Peripheral_Fabric.h>

using nucode::arduino::PdmConfiguration;
using nucode::arduino::PdmEvent;
using nucode::arduino::PdmEventType;
using nucode::arduino::PdmFabric;
using nucode::arduino::StreamElectricalProfile;
using nucode::arduino::streamFabric;
using nucode::arduino::StreamFabricResult;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::UnicastServer;
using nucode::ble::audio::UnicastServerMode;

namespace
{
    constexpr std::size_t samplesPerFrame = 160U;
    alignas(4) std::int16_t microphoneBuffers[2][samplesPerFrame] = {};
    PdmFabric *microphone = nullptr;
    UnicastServer audioServer;
    Lc3Codec codec;
    bool restartAdvertising = false;
    bool ready = false;

    /** @brief peer가 끊기면 같은 audio source 광고를 다시 시작합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
        }
    }

    /** @brief PDM frame을 LC3로 압축해 활성 source ASE로 보냅니다. */
    void sendMicrophoneFrame(const std::int16_t *samples)
    {
        if (!audioServer.sourceStreaming())
        {
            return;
        }
        std::uint8_t frame[40] = {};
        if (codec.encode(samples, samplesPerFrame, frame, sizeof(frame)) == Error::none)
        {
            const Error sent = audioServer.sendFrame(frame);
            if ((sent != Error::none) && (sent != Error::busy))
            {
                ready = false;
            }
        }
    }
} // namespace

/** @brief BLE Audio source와 16 kHz PDM microphone의 연속 DMA capture를 시작합니다. */
void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);
    BLEDevice.onEventInfo(onBleEvent);

    microphone = streamFabric().pdm(20U);
    const PdmConfiguration microphoneConfiguration{
        PIN_P1_04, PIN_P1_06, 16000U, false, false, StreamElectricalProfile::dap_uart_disabled};
    if ((microphone == nullptr) || !BLEDevice.begin("NU54-PDM-AUDIO") ||
        (audioServer.begin(UnicastServerMode::duplex) != Error::none) ||
        (codec.begin() != Error::none) ||
        (microphone->configure(microphoneConfiguration) != StreamFabricResult::success) ||
        (microphone->start(microphoneBuffers[0], samplesPerFrame) != StreamFabricResult::success) ||
        (microphone->queueBuffer(microphoneBuffers[1], samplesPerFrame) !=
         StreamFabricResult::success))
    {
        return;
    }

    constexpr std::uint8_t announcement[] = {1U, 0x03U, 0x00U, 0x00U, 0x00U, 0U};
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x184EU)) ||
        !BLEAdvertising.setServiceData(BLEUuid(0x184EU), announcement, sizeof(announcement)) ||
        !BLEAdvertising.start())
    {
        return;
    }
    ready = true;
}

/** @brief 완료된 PDM buffer를 전송하고 즉시 다음 DMA 구간으로 반환합니다. */
void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        ready = BLEAdvertising.start();
    }

    PdmEvent event{};
    while ((microphone != nullptr) && microphone->takeEvent(event))
    {
        if ((event.type == PdmEventType::buffer_complete) && (event.samples == samplesPerFrame) &&
            (event.buffer != nullptr))
        {
            sendMicrophoneFrame(event.buffer);
            if (microphone->queueBuffer(event.buffer, event.samples) != StreamFabricResult::success)
            {
                ready = false;
            }
        }
        else if ((event.type == PdmEventType::overflow) || (event.type == PdmEventType::error))
        {
            ready = false;
        }
    }

    digitalWrite(LED_BUILTIN, ready && audioServer.sourceStreaming() ? HIGH : LOW);
    delay(1U);
}
