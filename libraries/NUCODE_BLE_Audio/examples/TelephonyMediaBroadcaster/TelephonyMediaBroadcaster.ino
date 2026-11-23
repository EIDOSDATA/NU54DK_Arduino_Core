/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * TMAP broadcast sender가 합성 PCM을 LC3 방송으로 전송합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) TelephonyMediaBroadcaster (broadcaster); 2) TelephonyMediaReceiver (receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) TelephonyMediaBroadcaster (broadcaster); 2) TelephonyMediaReceiver (receiver)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `TMAP broadcast streaming`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `TMAP local roles=0x10 service=TMAS`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `TMAP broadcast stop result=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `TMAP broadcast start failed native=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `TMAP broadcaster start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `TMAP LC3 encode failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_Audio/TelephonyMediaGateway`
 * - `NUCODE_BLE_Audio/TelephonyMediaReceiver`
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
 * identity `NUCODE_BLE_Audio/TelephonyMediaBroadcaster`, sha256 `0853fea141aa8bc50e7fc8df2c5fc6e6534d1d4705dc6a9e66ea4812704ae9a4`
 * @nucode_example_setup_end */

/**
 * @file TelephonyMediaBroadcaster.ino
 * @brief TMAP broadcast sender가 합성 PCM을 LC3 방송으로 전송합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

namespace
{
    using nucode::ble::audio::BroadcastSource;
    using nucode::ble::audio::Error;
    using nucode::ble::audio::Lc3Codec;
    using nucode::ble::audio::TelephonyMediaRole;
    using nucode::ble::audio::TelephonyMediaRoles;

    constexpr const char *broadcastName = "NU54-TMAP-AUDIO";
    TelephonyMediaRoles profile;
    BroadcastSource audioSource;
    Lc3Codec codec;
    std::uint32_t lastFrameAt = 0U;
    std::uint32_t sentFrames = 0U;
    std::uint16_t wavePosition = 0U;

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

    /** @brief BAP broadcast source를 다시 시작합니다. */
    bool startBroadcast()
    {
        const Error result = audioSource.begin(broadcastName);
        if (result != Error::none)
        {
            Serial.print("TMAP broadcast start failed native=");
            Serial.println(audioSource.nativeCode());
            return false;
        }
        Serial.println("TMAP broadcast streaming");
        return true;
    }

    /** @brief 초기화 실패가 성공 출력으로 가려지지 않게 멈춥니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("TMAP broadcaster start failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000U);
        }
    }
} // namespace

void setup()
{
    Serial.begin(115200);
    require(BLEDevice.begin("NU54-TMAP-BROADCASTER"), "device");
    require(profile.begin(TelephonyMediaRole::broadcast_media_sender) == Error::none, "roles");
    Serial.println("TMAP local roles=0x10 service=TMAS");
    require(codec.begin() == Error::none, "codec");
    require(startBroadcast(), "broadcast");
}

void loop()
{
    BLEDevice.poll();
    profile.poll();

    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            const Error result = audioSource.end();
            Serial.print("TMAP broadcast stop result=");
            Serial.println(static_cast<unsigned int>(result));
        }
        else if (command == 'r')
        {
            static_cast<void>(startBroadcast());
        }
        else if (command == 'x')
        {
            TelephonyMediaRoles unsupported;
            Serial.println(unsupported.begin(TelephonyMediaRole::broadcast_media_receiver) ==
                                   Error::unsupported
                               ? "Unsupported TMAP role rejected"
                               : "Unsupported TMAP role unexpectedly accepted");
        }
        else if (command == 'q')
        {
            Lc3Codec incompatibleCodec;
            nucode::ble::audio::Lc3Config incompatibleQuality;
            incompatibleQuality.frame_duration_us = 5000U;
            Serial.println(incompatibleCodec.begin(incompatibleQuality) == Error::invalid_argument
                               ? "TMAP quality mismatch rejected"
                               : "TMAP quality mismatch unexpectedly accepted");
        }
    }

    if (!audioSource.streaming())
    {
        delay(1U);
        return;
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
        Serial.println("TMAP LC3 encode failed");
        return;
    }
    const Error sent = audioSource.sendFrame(frame);
    if (sent == Error::none)
    {
        sentFrames++;
        if ((sentFrames % 100U) == 0U)
        {
            Serial.print("TMAP broadcast sent=");
            Serial.println(sentFrames);
        }
    }
    else if (sent != Error::busy)
    {
        Serial.print("TMAP broadcast send failed native=");
        Serial.println(audioSource.nativeCode());
    }
}
