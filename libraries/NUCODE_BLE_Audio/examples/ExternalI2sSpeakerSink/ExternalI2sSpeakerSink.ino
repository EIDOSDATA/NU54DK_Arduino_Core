/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 수신한 LC3 audio를 외부 I2S codec 또는 speaker로 재생합니다.
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
 * - `NUCODE_BLE_Audio/ExternalPdmMicrophoneSource`
 * - `NUCODE_BLE_Audio/GamingAudioBroadcaster`
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
 * identity `NUCODE_BLE_Audio/ExternalI2sSpeakerSink`, sha256 `a3885a33d65d2c14bc78458ed0d0671965d5d34d19b96030f068f3b3d4e7bebc`
 * @nucode_example_setup_end */

/**
 * @file ExternalI2sSpeakerSink.ino
 * @brief 수신한 LC3 audio를 외부 I2S codec 또는 speaker로 재생합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_Peripheral_Fabric.h>

using nucode::arduino::I2sBuffers;
using nucode::arduino::I2sChannels;
using nucode::arduino::I2sConfiguration;
using nucode::arduino::I2sEvent;
using nucode::arduino::I2sEventType;
using nucode::arduino::I2sFabric;
using nucode::arduino::I2sSampleWidth;
using nucode::arduino::StreamElectricalProfile;
using nucode::arduino::streamFabric;
using nucode::arduino::StreamFabricResult;
using nucode::ble::BLEAddress;
using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLELinkRole;
using nucode::ble::BLEScanResult;
using nucode::ble::BLEUuid;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::UnicastClient;
using nucode::ble::audio::UnicastClientMode;
using nucode::ble::audio::UnicastClientStage;

namespace
{
    constexpr std::size_t samplesPerFrame = 160U;
    alignas(4) std::uint32_t speakerBuffers[2][samplesPerFrame] = {};
    std::int16_t latestPcm[samplesPerFrame] = {};
    I2sFabric *speaker = nullptr;
    UnicastClient audioClient;
    Lc3Codec codec;
    BLEAddress peerAddress;
    BLEConnectionHandle peer;
    bool peerFound = false;
    bool restartScan = false;
    bool ready = false;

    /** @brief ASCS를 광고하는 첫 연결 가능한 audio source를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            static_cast<void>(BLEScan.stop());
        }
    }

    /** @brief BLE 연결 수명을 unicast client에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) && (event.role == BLELinkRole::central))
        {
            peer = event.connection;
            ready = audioClient.begin(peer, UnicastClientMode::duplex) == Error::none;
        }
        else if ((event.event == BLEEvent::disconnected) && (event.connection == peer))
        {
            static_cast<void>(audioClient.end());
            peer = BLEConnectionHandle();
            peerFound = false;
            restartScan = true;
            ready = false;
        }
    }

    /** @brief mono PCM 한 frame을 16-bit stereo I2S word로 복제합니다. */
    void fillSpeakerBuffer(std::uint32_t *output)
    {
        for (std::size_t index = 0U; index < samplesPerFrame; index++)
        {
            const std::uint32_t sample = static_cast<std::uint16_t>(latestPcm[index]);
            output[index] = sample | (sample << 16U);
        }
    }
} // namespace

/** @brief BLE Audio client와 16 kHz I2S output DMA를 시작합니다. */
void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);
    BLEScan.onResult(onScanResult);
    BLEDevice.onEventInfo(onBleEvent);

    speaker = streamFabric().i2s(20U);
    const I2sConfiguration speakerConfiguration{PIN_P1_04,
                                                PIN_P1_05,
                                                0xFFU,
                                                PIN_P1_07,
                                                0xFFU,
                                                16000U,
                                                I2sSampleWidth::bits16,
                                                I2sChannels::stereo,
                                                true,
                                                StreamElectricalProfile::dap_uart_disabled};
    if ((speaker == nullptr) || (codec.begin() != Error::none) ||
        (speaker->configure(speakerConfiguration) != StreamFabricResult::success) ||
        (speaker->start({nullptr, speakerBuffers[0], samplesPerFrame}) !=
         StreamFabricResult::success) ||
        (speaker->queueBuffers({nullptr, speakerBuffers[1], samplesPerFrame}) !=
         StreamFabricResult::success) ||
        !BLEDevice.begin("NU54-I2S-AUDIO") || !BLEScan.clearFilters() ||
        !BLEScan.filterServiceUuid(BLEUuid(0x184EU)) || !BLEScan.start(true))
    {
        return;
    }
}

/** @brief 수신 LC3를 복호화하고 반환된 DMA buffer를 다음 I2S frame으로 채웁니다. */
void loop()
{
    BLEDevice.poll();
    audioClient.poll();

    std::uint8_t frame[40] = {};
    while (audioClient.readFrame(frame))
    {
        if (codec.decode(frame, sizeof(frame), latestPcm, samplesPerFrame) != Error::none)
        {
            ready = false;
        }
    }

    I2sEvent event{};
    while ((speaker != nullptr) && speaker->takeEvent(event))
    {
        if ((event.type == I2sEventType::buffers_complete) && (event.released.transmit != nullptr))
        {
            auto *const released = const_cast<std::uint32_t *>(event.released.transmit);
            fillSpeakerBuffer(released);
            if (speaker->queueBuffers({nullptr, released, samplesPerFrame}) !=
                StreamFabricResult::success)
            {
                ready = false;
            }
        }
        else if ((event.type == I2sEventType::underrun) || (event.type == I2sEventType::error))
        {
            ready = false;
        }
    }

    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress))
        {
            restartScan = true;
        }
    }
    if (restartScan && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        restartScan = false;
        if (!BLEScan.running())
        {
            static_cast<void>(BLEScan.start(true));
        }
    }

    const UnicastClientStage stage = audioClient.stage();
    if (stage == UnicastClientStage::failed)
    {
        ready = false;
        if (BLEConnection.connected(peer))
        {
            static_cast<void>(BLEConnection.disconnect(peer));
        }
    }
    else if (stage == UnicastClientStage::streaming)
    {
        ready = true;
    }
    digitalWrite(LED_BUILTIN, ready ? HIGH : LOW);
    delay(1U);
}
