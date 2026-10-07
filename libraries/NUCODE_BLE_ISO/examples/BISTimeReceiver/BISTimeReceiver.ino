/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * BIS 사용자 SDU와 수신 HCI 시각의 단조성을 검사합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) BISTimeSource (source/transmitter); 2) BISTimeReceiver (receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) BISTimeSource (source/transmitter); 2) BISTimeReceiver (receiver)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `BIS time received frames=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `timestamps=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `BIS time receiver scanning`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `errors=0` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `BIS time invalid frames=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `errors=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_ISO/BISTimeSource`
 * - `NUCODE_BLE_ISO/CISCentral`
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
 * identity `NUCODE_BLE_ISO/BISTimeReceiver`, sha256 `db1bf6d70a09b91bce6d3a8ccded27d61685aa3f8ecd44300d4f73e39e3ae8b3`
 * @nucode_example_setup_end */

/**
 * @file BISTimeReceiver.ino
 * @brief BIS 사용자 SDU와 수신 HCI 시각의 단조성을 검사합니다.
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
    constexpr char sessionId[] = "NUCODE-TIME-BIS1";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    RawBis bis;
    std::uint16_t received = 0U;
    std::uint16_t timestamped = 0U;
    std::uint16_t errors = 0U;
    std::uint32_t last_timestamp_us = 0U;
    std::uint32_t session_ms = 0U;
    std::uint32_t restart_ms = 0U;
    bool running = false;
    bool closing = false;
    bool connection_reported = false;

    /** @brief 수신 payload와 예상 sequence를 사용자 영역에서 검사합니다. */
    bool validFrame(const BisFrame &frame, std::uint16_t &number)
    {
        if (frame.length != 8U || frame.data[0] != 'T' || frame.data[1] != 'I' ||
            frame.data[6] != 0xB1U || frame.data[7] != 0x50U)
        {
            return false;
        }
        number = static_cast<std::uint16_t>(frame.data[2]) |
                 (static_cast<std::uint16_t>(frame.data[3]) << 8U);
        return number < 100U &&
               frame.data[4] == static_cast<std::uint8_t>(number ^ 0x5AU) &&
               frame.data[5] == static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
    }

    /** @brief 수신 payload와 timestamp 검증 결과를 표시합니다. */
    void reportSession()
    {
        if (received == 100U && timestamped == 100U && errors == 0U)
        {
            Serial.print("BIS time received frames=");
            Serial.print(received);
            Serial.print(" timestamps=");
            Serial.print(timestamped);
            Serial.println(" errors=0");
        }
        else
        {
            Serial.print("BIS time invalid frames=");
            Serial.print(received);
            Serial.print(" timestamps=");
            Serial.print(timestamped);
            Serial.print(" errors=");
            Serial.println(errors);
        }
        bis.stop();
        closing = true;
    }

    /** @brief session ID가 일치하는 periodic advertising을 찾습니다. */
    void startSession()
    {
        const Error result = bis.begin(Role::bis_time_receiver,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("BIS start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restart_ms = millis() + 1000U;
            return;
        }
        received = 0U;
        timestamped = 0U;
        errors = 0U;
        last_timestamp_us = 0U;
        session_ms = millis();
        running = true;
        closing = false;
        connection_reported = false;
        Serial.println("BIS time receiver scanning");
    }
}

/** @brief 공개 API와 Core image revision을 표시합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.print("BIS core revision=");
    Serial.println(RawBis::buildRevision());
    startSession();
}

/** @brief 받은 SDU 100개의 payload와 controller 시각을 검증합니다. */
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
        Serial.print("BIS time receiver synchronized ms=");
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
        if (received == 0U)
        {
            Serial.print("BIS time first frame=");
            Serial.println(number);
        }
        if (number != received)
        {
            ++errors;
        }
        if (!frame.timestamp_valid ||
            (timestamped > 0U &&
             static_cast<std::int32_t>(frame.timestamp_us - last_timestamp_us) <= 0))
        {
            ++errors;
        }
        else
        {
            ++timestamped;
            last_timestamp_us = frame.timestamp_us;
        }
        ++received;
    }
    if (!closing && received == 100U)
    {
        reportSession();
    }
    if (!closing && progress == Error::peer_stopped)
    {
        reportSession();
    }
    if (!closing && progress == Error::transport_failure)
    {
        Serial.print("BIS time error: ");
        Serial.print(bis.nativeError());
        Serial.print(" frames=");
        Serial.print(received);
        Serial.print(" timestamps=");
        Serial.print(timestamped);
        Serial.print(" errors=");
        Serial.println(errors);
        bis.stop();
        closing = true;
    }
    if (!closing && millis() - session_ms >= 15000U)
    {
        Serial.print("BIS time receive timeout frames=");
        Serial.println(received);
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
