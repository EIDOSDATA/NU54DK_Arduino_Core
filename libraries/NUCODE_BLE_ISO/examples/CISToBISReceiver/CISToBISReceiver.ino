/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 동기화한 BIS의 사용자 SDU와 순서를 Arduino 코드에서 검사합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 3대 — 1) CISToBISPeer (peer); 2) CISToBISBridge (bridge); 3) CISToBISReceiver (receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 3대 — 1) CISToBISPeer (peer); 2) CISToBISBridge (bridge); 3) CISToBISReceiver (receiver)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `CIS BIS received frames=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `CIS BIS receiver scanning`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `CIS BIS core revision=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `missing=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `errors=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `CIS BIS start failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_ISO/BISEncryptedReceiver`
 * - `NUCODE_BLE_ISO/BISEncryptedSource`
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
 * identity `NUCODE_BLE_ISO/CISToBISReceiver`, sha256 `03647058afa4e30aaa7c62074032bce42ccbf3aecff7219bc2457f42bbb569ac`
 * @nucode_example_setup_end */

/**
 * @file CISToBISReceiver.ino
 * @brief 동기화한 BIS의 사용자 SDU와 순서를 Arduino 코드에서 검사합니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::BisFrame;
using nucode::ble::iso::Error;
using nucode::ble::iso::RawBis;
using nucode::ble::iso::Role;

namespace
{
    /** @brief source 예제와 공유하는 16-byte session ID입니다. */
    constexpr char sessionId[] = "NUCODE-C2B-BIS01";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    RawBis bis;
    std::uint16_t received = 0U;
    std::uint16_t errors = 0U;
    std::uint16_t missing = 0U;
    std::uint16_t last_sequence = 0U;
    std::uint32_t session_ms = 0U;
    std::uint32_t restart_ms = 0U;
    bool running = false;
    bool closing = false;
    bool connection_reported = false;
    bool have_frame = false;

    /** @brief 수신 payload와 예상 sequence를 사용자 영역에서 검사합니다. */
    bool validFrame(const BisFrame &frame, std::uint16_t &number)
    {
        if (frame.length != 8U || frame.data[0] != 'C' || frame.data[1] != 'B' ||
            frame.data[6] != 0xC1U || frame.data[7] != 0x52U)
        {
            return false;
        }
        number = static_cast<std::uint16_t>(frame.data[2]) |
                 (static_cast<std::uint16_t>(frame.data[3]) << 8U);
        return number < 100U &&
               frame.data[4] == static_cast<std::uint8_t>(number ^ 0x5AU) &&
               frame.data[5] == static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
    }

    /** @brief 수신량·누락·오류를 한 session의 종료 결과로 표시합니다. */
    void reportSession()
    {
        if (have_frame)
        {
            missing += static_cast<std::uint16_t>(99U - last_sequence);
        }
        Serial.print("CIS BIS received frames=");
        Serial.print(received);
        Serial.print(" missing=");
        Serial.print(missing);
        Serial.print(" errors=");
        Serial.println(errors);
        bis.stop();
        closing = true;
    }

    /** @brief session ID가 일치하는 periodic advertising을 찾습니다. */
    void startSession()
    {
        const Error result = bis.begin(Role::cis_to_bis_receiver,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("CIS BIS start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restart_ms = millis() + 1000U;
            return;
        }
        received = 0U;
        errors = 0U;
        missing = 0U;
        last_sequence = 0U;
        have_frame = false;
        session_ms = millis();
        running = true;
        closing = false;
        connection_reported = false;
        Serial.println("CIS BIS receiver scanning");
    }
}

/** @brief 공개 API와 Core image revision을 표시합니다. */
void setup()
{
    Serial.begin(115200);
    /** 세 보드의 순차적 전원·리셋 뒤 이전 BIG이 해제될 시간을 둡니다. */
    delay(3000);
    Serial.print("CIS BIS core revision=");
    Serial.println(RawBis::buildRevision());
    startSession();
}

/** @brief 받은 SDU 100개의 payload를 검증하고 sync를 반환합니다. */
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
    if (!connection_reported && bis.connected())
    {
        connection_reported = true;
        Serial.print("CIS BIS receiver synchronized ms=");
        Serial.println(millis() - session_ms);
    }
    BisFrame frame = {};
    while (!closing && bis.readFrame(frame))
    {
        std::uint16_t number = 0U;
        if (!validFrame(frame, number))
        {
            ++errors;
            continue;
        }
        if (!have_frame)
        {
            Serial.print("CIS BIS first frame=");
            Serial.println(number);
            missing = number;
            have_frame = true;
        }
        else if (number <= last_sequence)
        {
            ++errors;
            continue;
        }
        else
        {
            missing += static_cast<std::uint16_t>(number - last_sequence - 1U);
        }
        last_sequence = number;
        ++received;
    }
    if (!closing && received == 100U)
    {
        reportSession();
    }
    if (!closing && progress == Error::peer_stopped)
    {
        if (received >= 99U && missing + (99U - last_sequence) <= 1U &&
            errors == 0U)
        {
            reportSession();
        }
        else
        {
            Serial.print("CIS BIS peer stopped before enough frames: ");
            Serial.print(received);
            Serial.print(" missing=");
            Serial.print(missing);
            Serial.print(" errors=");
            Serial.println(errors);
            bis.stop();
            closing = true;
        }
    }
    if (!closing && progress == Error::transport_failure)
    {
        Serial.print("CIS BIS error: ");
        Serial.print(bis.nativeError());
        Serial.print(" frames=");
        Serial.print(received);
        Serial.print(" missing=");
        Serial.print(missing);
        Serial.print(" errors=");
        Serial.println(errors);
        bis.stop();
        closing = true;
    }
    if (!closing && millis() - session_ms >= 15000U)
    {
        Serial.print("CIS BIS receive timeout frames=");
        Serial.println(received);
        bis.stop();
        closing = true;
    }
    if (closing && bis.stopped())
    {
        Serial.println("CIS BIS stopped");
        running = false;
        restart_ms = millis() + 1000U;
    }
    delay(1);
}
