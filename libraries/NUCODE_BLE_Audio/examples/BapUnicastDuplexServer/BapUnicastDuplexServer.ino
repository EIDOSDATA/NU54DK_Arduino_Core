/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 한 CIS의 양방향 LC3 stream을 받아 복호화하고 합성 PCM을 보냅니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) BapUnicastDuplexClient (client/controller); 2) BapUnicastDuplexServer (server/device)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) BapUnicastDuplexClient (client/controller); 2) BapUnicastDuplexServer (server/device)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `LE Audio duplex peer disconnected`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `LE Audio duplex`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `native=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `LE Audio Bluetooth start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `LE Audio duplex advertising failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/BapUnicastSink`
 * - `NUCODE_BLE_Audio/BapUnicastSource`
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
 * identity `NUCODE_BLE_Audio/BapUnicastDuplexServer`, sha256 `242c4f1905673792c9d2428797121d2fa8c76ce8e6c0cc0a4b89efce7eae9f7c`
 * @nucode_example_setup_end */

/**
 * @file BapUnicastDuplexServer.ino
 * @brief 한 CIS의 양방향 LC3 stream을 받아 복호화하고 합성 PCM을 보냅니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::UnicastServer;
using nucode::ble::audio::UnicastServerMode;

namespace
{
    UnicastServer audioServer;
    Lc3Codec codec;
    bool restartAdvertising = false;
    std::uint32_t decodedFrames = 0U;
    std::uint32_t lastFrameAt = 0U;
    std::uint32_t lastReportedSent = 0U;
    std::uint16_t wavePosition = 0U;

    /** @brief 연결 해제 뒤 새 client를 위한 광고를 예약합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            Serial.println("LE Audio duplex peer disconnected");
        }
    }

    /** @brief 고정 16 kHz 삼각파 PCM frame을 만듭니다. */
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

    /** @brief 공개 API 오류와 원본 stack 코드를 출력합니다. */
    void printError(const char *step, Error error)
    {
        Serial.print("LE Audio duplex ");
        Serial.print(step);
        Serial.print(" failed: ");
        Serial.print(static_cast<unsigned int>(error));
        Serial.print(" native=");
        Serial.println(audioServer.nativeCode());
    }
} // namespace

/** @brief PACS/ASCS 양방향 역할과 LC3 codec을 준비하고 연결 가능 광고를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-AUDIO-DPX"))
    {
        Serial.println("LE Audio Bluetooth start failed");
        return;
    }
    const Error serverResult = audioServer.begin(UnicastServerMode::duplex);
    if (serverResult != Error::none)
    {
        printError("server", serverResult);
        return;
    }
    const Error codecResult = codec.begin();
    if (codecResult != Error::none)
    {
        printError("codec", codecResult);
        return;
    }

    /** @brief ASCS UUID와 일반 audio announcement를 광고합니다. */
    constexpr std::uint8_t announcement[] = {1U, 0x03U, 0x00U, 0x00U, 0x00U, 0U};
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x184EU)) ||
        !BLEAdvertising.setServiceData(BLEUuid(0x184EU), announcement, sizeof(announcement)) ||
        !BLEAdvertising.start())
    {
        Serial.println("LE Audio duplex advertising failed");
        return;
    }
    Serial.println("LE Audio duplex server advertising");
}

/** @brief 수신 frame을 복호화하고 10 ms마다 반대 방향 LC3 frame을 전송합니다. */
void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("LE Audio duplex advertising restart failed");
        }
    }

    std::uint8_t receivedFrame[40] = {};
    std::int16_t decodedPcm[160] = {};
    while (audioServer.readFrame(receivedFrame))
    {
        const Error result = codec.decode(receivedFrame, sizeof(receivedFrame), decodedPcm, 160U);
        if (result != Error::none)
        {
            printError("decode", result);
            continue;
        }
        decodedFrames++;
        if ((decodedFrames % 100U) == 0U)
        {
            std::uint32_t energy = 0U;
            for (const std::int16_t sample : decodedPcm)
            {
                const std::int32_t value = sample;
                energy += static_cast<std::uint32_t>((value < 0) ? -value : value);
            }
            Serial.print("LE Audio duplex received=");
            Serial.print(decodedFrames);
            Serial.print(" energy=");
            Serial.print(energy);
            Serial.print(" dropped=");
            Serial.println(audioServer.droppedFrames());
        }
    }

    const std::uint32_t now = millis();
    if (audioServer.sourceStreaming() && ((now - lastFrameAt) >= 10U))
    {
        lastFrameAt = now;
        std::int16_t pcm[160] = {};
        std::uint8_t frame[40] = {};
        fillPcm(pcm);
        const Error encoded = codec.encode(pcm, 160U, frame, sizeof(frame));
        if (encoded != Error::none)
        {
            printError("encode", encoded);
        }
        else
        {
            const Error sent = audioServer.sendFrame(frame);
            if ((sent != Error::none) && (sent != Error::busy) &&
                !((sent == Error::not_ready) && !audioServer.sourceStreaming()))
            {
                printError("send", sent);
            }
            const std::uint32_t sentFrames = audioServer.sentFrames();
            if ((sentFrames % 100U) == 0U && (sentFrames != lastReportedSent))
            {
                lastReportedSent = sentFrames;
                Serial.print("LE Audio duplex sent=");
                Serial.println(sentFrames);
            }
        }
    }
    delay(1);
}
