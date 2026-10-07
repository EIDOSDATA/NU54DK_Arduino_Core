/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * Standard Quality 공개 오디오 방송으로 합성 LC3 frame을 보냅니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) PublicAudioBroadcastSource (source/transmitter); 2) PublicAudioBroadcastSink (sink/receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) PublicAudioBroadcastSource (source/transmitter); 2) PublicAudioBroadcastSink (sink/receiver)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `public audio source preparing`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `public audio source stopped`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `public audio source streaming`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `public audio source start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `public audio source stop failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `Bluetooth start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/TelephonyMediaBroadcaster`
 * - `NUCODE_BLE_Audio/TelephonyMediaGateway`
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
 * identity `NUCODE_BLE_Audio/PublicAudioBroadcastSource`, sha256 `1195ec482d9c00c43bea66c0bbc5b36cf3e10c51acdced900bfddf1a679f5908`
 * @nucode_example_setup_end */

/**
 * @file PublicAudioBroadcastSource.ino
 * @brief Standard Quality 공개 오디오 방송으로 합성 LC3 frame을 보냅니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::audio::BroadcastCode;
using nucode::ble::audio::CapStage;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::PublicAudioBroadcastSource;
using nucode::ble::audio::PublicBroadcastQuality;
using nucode::ble::audio::PublicBroadcastSourceConfig;

namespace
{
    constexpr BroadcastCode broadcastCode = {
        0x4e, 0x55, 0x43, 0x4f, 0x44, 0x45, 0x2d, 0x50,
        0x55, 0x42, 0x4c, 0x49, 0x43, 0x2d, 0x30, 0x31,
    };
    PublicBroadcastSourceConfig broadcastConfig = {
        .broadcast_name = "NUCODE-PUBLIC-AUDIO",
        .program_info = "Synthetic 16 kHz audio",
        .quality = PublicBroadcastQuality::standard,
    };
    PublicAudioBroadcastSource audioSource;
    Lc3Codec codec;
    std::uint32_t lastFrameAt = 0U;
    std::uint16_t wavePosition = 0U;
    bool announcedStreaming = false;
    bool broadcasting = false;
    bool recoveryPending = false;
    bool automaticRecovery = true;
    std::uint32_t recoveryAt = 0U;

    /** @brief 다음 정리·재시작 시도를 1초 뒤로 제한합니다. */
    void scheduleRecovery()
    {
        recoveryPending = true;
        recoveryAt = millis() + 1000U;
    }

    /** @brief 16 kHz의 bounded 삼각파 PCM frame 하나를 생성합니다. */
    void fillPcm(std::int16_t (&pcm)[160])
    {
        for (std::size_t index = 0U; index < 160U; index++)
        {
            const std::uint16_t phase =
                static_cast<std::uint16_t>((wavePosition + index) % 160U);
            const std::int32_t rising = (phase < 80U) ? phase : (160U - phase);
            pcm[index] = static_cast<std::int16_t>(rising * 300 - 12000);
        }
        wavePosition = static_cast<std::uint16_t>((wavePosition + 17U) % 160U);
    }

    /** @brief 공개 C++ API로 암호화된 Standard Quality 방송을 시작합니다. */
    bool startBroadcast()
    {
        broadcastConfig.quality = PublicBroadcastQuality::standard;
        const Error result = audioSource.begin(broadcastConfig, broadcastCode);
        if (result != Error::none)
        {
            Serial.print("public audio source start failed: ");
            Serial.println(audioSource.nativeCode());
            broadcasting = audioSource.stage() == CapStage::failed;
            return false;
        }
        broadcasting = true;
        announcedStreaming = false;
        recoveryPending = false;
        Serial.println("public audio source preparing");
        return true;
    }

    /** @brief source teardown이 끝난 경우에만 공개 상태를 stopped로 바꿉니다. */
    bool stopBroadcast()
    {
        if (!broadcasting)
        {
            return true;
        }
        const Error result = audioSource.end();
        if (result != Error::none)
        {
            Serial.print("public audio source stop failed: ");
            Serial.println(audioSource.nativeCode());
            return false;
        }
        broadcasting = false;
        return true;
    }
} // namespace

/** @brief Bluetooth, LC3 codec과 공개 오디오 source를 순서대로 시작합니다. */
void setup()
{
    Serial.begin(115200);
    if (!BLEDevice.begin("NUCODE-PUBLIC-SOURCE"))
    {
        Serial.println("Bluetooth start failed");
        return;
    }
    if (codec.begin() != Error::none)
    {
        Serial.println("LC3 codec start failed");
        return;
    }
    if (!startBroadcast())
    {
        scheduleRecovery();
    }
}

/** @brief LC3 송신과 중단·재시작·미지원 품질 확인 명령을 처리합니다. */
void loop()
{
    BLEDevice.poll();

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            automaticRecovery = false;
            recoveryPending = false;
            if (stopBroadcast())
            {
                Serial.println("public audio source stopped");
            }
        }
        else if (command == 'r')
        {
            automaticRecovery = true;
            if (stopBroadcast() && !startBroadcast())
            {
                scheduleRecovery();
            }
        }
        else if (command == 'h')
        {
            automaticRecovery = true;
            if (stopBroadcast())
            {
                broadcastConfig.quality = PublicBroadcastQuality::high;
                const Error result = audioSource.begin(broadcastConfig, broadcastCode);
                Serial.print("high quality rejected: ");
                Serial.println(static_cast<unsigned int>(result));
                broadcastConfig.quality = PublicBroadcastQuality::standard;
                scheduleRecovery();
            }
        }
    }

    if (broadcasting && automaticRecovery && !recoveryPending &&
        (audioSource.stage() == CapStage::failed))
    {
        Serial.print("public audio source failed: ");
        Serial.println(audioSource.nativeCode());
        scheduleRecovery();
    }
    if (recoveryPending &&
        (static_cast<std::int32_t>(millis() - recoveryAt) >= 0))
    {
        recoveryPending = false;
        if (broadcasting && !stopBroadcast())
        {
            scheduleRecovery();
        }
        else if (!startBroadcast())
        {
            scheduleRecovery();
        }
    }

    if (!audioSource.streaming())
    {
        delay(1U);
        return;
    }
    if (!announcedStreaming)
    {
        announcedStreaming = true;
        lastFrameAt = millis();
        Serial.println("public audio source streaming");
    }

    const std::uint32_t now = millis();
    if ((now - lastFrameAt) < 10U)
    {
        delay(1U);
        return;
    }
    lastFrameAt = now;

    std::int16_t pcm[160] = {};
    std::uint8_t frame[40] = {};
    fillPcm(pcm);
    if (codec.encode(pcm, 160U, frame, sizeof(frame)) != Error::none)
    {
        Serial.println("LC3 encode failed");
        return;
    }
    const Error sent = audioSource.sendFrame(frame);
    if ((sent != Error::none) && (sent != Error::busy))
    {
        Serial.print("public audio send failed: ");
        Serial.println(audioSource.nativeCode());
        return;
    }
    const std::uint32_t count = audioSource.sentFrames();
    if ((sent == Error::none) && ((count % 100U) == 0U))
    {
        Serial.print("public audio sent frames=");
        Serial.println(count);
    }
}
