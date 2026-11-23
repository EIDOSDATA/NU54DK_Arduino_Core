/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 사용자 데이터를 암호화한 Broadcast Isochronous Stream으로 보냅니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) BISEncryptedSource (source/transmitter); 2) BISEncryptedReceiver (receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) BISEncryptedSource (source/transmitter); 2) BISEncryptedReceiver (receiver)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `BIS source advertising`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `BIS core revision=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `BIS sent frames=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `BIS start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `BIS error:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `BIS send failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_ISO/BISReceiver`
 * - `NUCODE_BLE_ISO/BISSource`
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
 * Recipe `ble_iso`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_ISO/BISEncryptedSource`, sha256 `3ed15486b6e144b6bf383347ec6e59c4e11748d20cf45b4c2c8beae428d85a26`
 * @nucode_example_setup_end */

/**
 * @file BISEncryptedSource.ino
 * @brief 사용자 데이터를 암호화한 Broadcast Isochronous Stream으로 보냅니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::Error;
using nucode::ble::iso::RawBis;
using nucode::ble::iso::Role;

namespace
{
    /** @brief receiver와 공유하는 16-byte 예제 session ID입니다. */
    constexpr char sessionId[] = "NUCODE-ENC-BIS01";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    /** @brief 예제용 Broadcast Code이며 양쪽 보드에서 동일하게 설정합니다. */
    constexpr char broadcastCode[] = "NUCODE-BIS-CODE1";
    static_assert(sizeof(broadcastCode) == 17U, "broadcast code must be 16 bytes");

    RawBis bis;
    std::uint16_t sequence = 0U;
    std::uint32_t connected_ms = 0U;
    std::uint32_t last_send_ms = 0U;
    std::uint32_t restart_ms = 0U;
    bool running = false;
    bool closing = false;

    /** @brief 사용자가 편집할 수 있는 8-byte 측정 SDU를 만듭니다. */
    void makeFrame(std::uint16_t number, std::uint8_t payload[8])
    {
        payload[0] = 'B';
        payload[1] = 'I';
        payload[2] = static_cast<std::uint8_t>(number);
        payload[3] = static_cast<std::uint8_t>(number >> 8U);
        payload[4] = static_cast<std::uint8_t>(number ^ 0x5AU);
        payload[5] = static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
        payload[6] = 0xB1U;
        payload[7] = 0x50U;
    }

    /** @brief 사용자 ID로 periodic 광고와 BIG을 시작합니다. */
    void startSession()
    {
        const Error result = bis.begin(Role::bis_encrypted_source,
                                       reinterpret_cast<const std::uint8_t *>(sessionId),
                                       reinterpret_cast<const std::uint8_t *>(broadcastCode));
        if (result != Error::none)
        {
            Serial.print("BIS start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restart_ms = millis() + 1000U;
            return;
        }
        sequence = 0U;
        connected_ms = 0U;
        last_send_ms = 0U;
        running = true;
        closing = false;
        Serial.println("BIS source advertising");
    }
}

/** @brief 공개 API와 Core image revision을 Serial에 표시합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.print("BIS core revision=");
    Serial.println(RawBis::buildRevision());
    startSession();
}

/** @brief receiver 동기화 뒤 사용자 SDU 100개를 보내고 BIG을 해제합니다. */
void loop()
{
    if (!running)
    {
        if (static_cast<std::int32_t>(millis() - restart_ms) >= 0)
        {
            startSession();
        }
        delay(1);
        return;
    }
    const Error progress = bis.poll();
    if (progress == Error::transport_failure && !closing)
    {
        Serial.print("BIS error: ");
        Serial.println(bis.nativeError());
        bis.stop();
        closing = true;
    }
    if (!closing && bis.connected() && connected_ms == 0U)
    {
        connected_ms = millis();
    }
    if (!closing && connected_ms != 0U && millis() - connected_ms >= 2000U &&
        sequence < 100U && millis() - last_send_ms >= 20U)
    {
        std::uint8_t payload[8] = {};
        makeFrame(sequence, payload);
        const Error result = bis.sendFrame(payload, sizeof(payload));
        if (result == Error::none)
        {
            ++sequence;
            last_send_ms = millis();
        }
        else if (result != Error::busy && result != Error::not_ready)
        {
            Serial.print("BIS send failed: ");
            Serial.println(static_cast<unsigned>(result));
            bis.stop();
            closing = true;
        }
    }
    if (!closing && sequence == 100U && millis() - last_send_ms >= 500U)
    {
        Serial.print("BIS sent frames=");
        Serial.println(sequence);
        bis.stop();
        closing = true;
    }
    if (closing && bis.stopped())
    {
        running = false;
        restart_ms = millis() + 1000U;
    }
    delay(1);
}
