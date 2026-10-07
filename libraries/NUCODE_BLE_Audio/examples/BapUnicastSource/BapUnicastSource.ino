/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 합성 PCM을 LC3로 encode해 LE Audio unicast sink로 보냅니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) BapUnicastSource (source/transmitter); 2) BapUnicastSink (sink/receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) BapUnicastSource (source/transmitter); 2) BapUnicastSink (sink/receiver)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `LE Audio sink found`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `LE Audio connected; preparing`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `LE Audio peer disconnected`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `LE Audio scan stop failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `LE Audio client begin failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `LE Audio client end failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/CallControlClient`
 * - `NUCODE_BLE_Audio/CallControlServer`
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
 * identity `NUCODE_BLE_Audio/BapUnicastSource`, sha256 `a2cb47a466fa727ea49212c62e5ee3a5dcd6103e8f489995794b50dea70313ed`
 * @nucode_example_setup_end */

/**
 * @file BapUnicastSource.ino
 * @brief 합성 PCM을 LC3로 encode해 LE Audio unicast sink로 보냅니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

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
using nucode::ble::audio::UnicastClientStage;

namespace
{
    UnicastClient audioSource;
    Lc3Codec codec;
    BLEAddress peerAddress;
    BLEConnectionHandle peer;
    bool peerFound = false;
    bool restartScan = false;
    bool announcedStreaming = false;
    bool announcedStopped = false;
    bool reportedFailure = false;
    std::uint32_t lastFrameAt = 0U;
    std::uint16_t wavePosition = 0U;

    /** @brief ASCS UUID를 광고하는 첫 연결 가능한 sink를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            Serial.println("LE Audio sink found");
            if (!BLEScan.stop())
            {
                Serial.println("LE Audio scan stop failed");
            }
        }
    }

    /** @brief 공개 BLE 연결의 수명을 unicast client에 전달합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) && (event.role == BLELinkRole::central))
        {
            peer = event.connection;
            announcedStopped = false;
            const Error result = audioSource.begin(peer);
            if (result == Error::none)
            {
                Serial.println("LE Audio connected; preparing");
            }
            else
            {
                Serial.print("LE Audio client begin failed: ");
                Serial.println(audioSource.nativeCode());
                static_cast<void>(BLEConnection.disconnect(peer));
            }
        }
        else if ((event.event == BLEEvent::disconnected) && (event.connection == peer))
        {
            const Error result = audioSource.end();
            if ((result != Error::none) && (result != Error::not_started))
            {
                Serial.print("LE Audio client end failed: ");
                Serial.println(audioSource.nativeCode());
            }
            peer = BLEConnectionHandle();
            peerFound = false;
            restartScan = true;
            announcedStreaming = false;
            announcedStopped = false;
            reportedFailure = false;
            Serial.println("LE Audio peer disconnected");
        }
    }

    /** @brief 16 kHz의 bounded 삼각파 PCM frame 하나를 생성합니다. */
    void fillPcm(std::int16_t (&pcm)[160])
    {
        for (std::size_t index = 0U; index < 160U; index++)
        {
            const std::uint16_t phase = static_cast<std::uint16_t>((wavePosition + index) % 160U);
            const std::int32_t rising = (phase < 80U) ? phase : (160U - phase);
            pcm[index] = static_cast<std::int16_t>(rising * 300 - 12000);
        }
        wavePosition = static_cast<std::uint16_t>((wavePosition + 17U) % 160U);
    }
} // namespace

/** @brief codec와 공개 BLE 검색을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    if (codec.begin() != Error::none)
    {
        Serial.println("LE Audio codec start failed");
        return;
    }
    BLEScan.onResult(onScanResult);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-AUDIO-SRC") || !BLEScan.clearFilters() ||
        !BLEScan.filterServiceUuid(BLEUuid(0x184EU)) || !BLEScan.start(true))
    {
        Serial.println("LE Audio scan start failed");
    }
}

/** @brief PACS/ASCS 단계를 진행하고 합성 LC3 frame을 10 ms 간격으로 보냅니다. */
void loop()
{
    BLEDevice.poll();
    audioSource.poll();

    while (Serial.available() > 0)
    {
        if (Serial.read() == 's')
        {
            const Error result = audioSource.stop();
            if (result != Error::none)
            {
                Serial.print("LE Audio stop failed: ");
                Serial.print(static_cast<unsigned int>(result));
                Serial.print(" native=");
                Serial.println(audioSource.nativeCode());
            }
        }
    }

    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress))
        {
            restartScan = true;
            Serial.println("LE Audio connect failed");
        }
    }
    if (restartScan && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        restartScan = false;
        if (!BLEScan.running() && !BLEScan.start(true))
        {
            Serial.println("LE Audio scan restart failed");
        }
        else
        {
            Serial.println("LE Audio scan restarted");
        }
    }

    const UnicastClientStage stage = audioSource.stage();
    if ((stage == UnicastClientStage::released) && !announcedStopped)
    {
        announcedStopped = true;
        Serial.println("LE Audio stream stopped");
        if (!BLEConnection.disconnect(peer))
        {
            Serial.println("LE Audio disconnect failed");
        }
    }
    if ((stage == UnicastClientStage::failed) && !reportedFailure)
    {
        reportedFailure = true;
        Serial.print("LE Audio setup failed at stage=");
        Serial.print(static_cast<unsigned int>(audioSource.failedAt()));
        Serial.print(" error=");
        Serial.print(static_cast<unsigned int>(audioSource.lastError()));
        Serial.print(" step=");
        Serial.print(static_cast<unsigned int>(audioSource.lastStep()));
        Serial.print(" native=");
        Serial.println(audioSource.nativeCode());
        if (BLEConnection.connected(peer))
        {
            static_cast<void>(BLEConnection.disconnect(peer));
        }
    }
    if (stage != UnicastClientStage::streaming)
    {
        delay(1);
        return;
    }
    if (!announcedStreaming)
    {
        announcedStreaming = true;
        lastFrameAt = millis();
        Serial.println("LE Audio source streaming");
    }
    const std::uint32_t now = millis();
    if ((now - lastFrameAt) < 10U)
    {
        delay(1);
        return;
    }
    lastFrameAt = now;

    std::int16_t pcm[160] = {};
    std::uint8_t frame[40] = {};
    fillPcm(pcm);
    const Error encoded = codec.encode(pcm, 160U, frame, sizeof(frame));
    if (encoded != Error::none)
    {
        Serial.println("LE Audio encode failed");
        return;
    }
    const Error sent = audioSource.sendFrame(frame);
    if ((sent != Error::none) && (sent != Error::busy))
    {
        Serial.print("LE Audio send failed: ");
        Serial.println(audioSource.nativeCode());
    }
    const std::uint32_t count = audioSource.sentFrames();
    if ((sent == Error::none) && (count % 100U) == 0U)
    {
        Serial.print("LE Audio sent frames=");
        Serial.println(count);
    }
}
