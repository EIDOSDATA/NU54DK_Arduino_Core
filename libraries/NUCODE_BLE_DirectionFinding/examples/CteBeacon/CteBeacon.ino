/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 기본 안테나에서 connectionless AoA CTE를 시작·중단·재시작합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 1대 — 1) CteBeacon 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 제품 SDC의 IQ RX·AoD는 지원하지 않으며 외부 compatible peer 조건을 확인합니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) CteBeacon 실행 보드
 * - 제품 SDC의 IQ RX·AoD는 지원하지 않으며 외부 compatible peer 조건을 확인합니다.
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Sketch 폴더의 sidecar를 함께 설치합니다: nucode-build.json, prj.conf
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `|nonce=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `|native=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `NUCODE_DF|1|READY|nonce=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `NUCODE_DF|1|ERROR|operation=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `|error=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `NUCODE_DF|1|REJECTED|nonce=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_DirectionFinding/ConnectedCteResponder`
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
 * Recipe `ble_direction_finding`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_DirectionFinding/CteBeacon`, sha256 `b1eb0940abba74eb1f33aecec1e5dc717008295f65f70a06ccc5f9fc0b579cb0`
 * @nucode_example_setup_end */

/**
 * @file CteBeacon.ino
 * @brief 기본 안테나에서 connectionless AoA CTE를 시작·중단·재시작합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_DirectionFinding.h>

#include <string.h>

using nucode::ble::df::Beacon;
using nucode::ble::df::BeaconConfig;
using nucode::ble::df::Error;

namespace
{
    Beacon beacon;
    char command[80] = {};
    char nonce[33] = "none";
    std::size_t command_length = 0U;
    bool beacon_ready = false;
    unsigned int start_count = 0U;
    unsigned int stop_count = 0U;

    /** @brief 수동 명령 또는 128-bit nonce를 가진 bounded 명령인지 확인합니다. */
    bool matches(const char *operation)
    {
        if (strcmp(command, operation) == 0)
        {
            strcpy(nonce, "none");
            return true;
        }
        const std::size_t length = strlen(operation);
        if ((strncmp(command, operation, length) != 0) ||
            (strncmp(command + length, "|nonce=", 7U) != 0) ||
            (command_length != length + 7U + 32U))
        {
            return false;
        }
        for (std::size_t index = 0U; index < 32U; ++index)
        {
            const char value = command[length + 7U + index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        memcpy(nonce, command + length + 7U, 32U);
        nonce[32] = '\0';
        return true;
    }

    /** @brief 공개 오류와 원본 controller 오류 코드를 함께 출력합니다. */
    void printError(const char *operation, Error error)
    {
        Serial.print("NUCODE_DF|1|ERROR|operation=");
        Serial.print(operation);
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|error=");
        Serial.print(static_cast<unsigned int>(error));
        Serial.print("|native=");
        Serial.println(beacon.nativeCode());
    }

    /** @brief Serial 한 명령을 공개 API 호출로 변환합니다. */
    void executeCommand()
    {
        if (matches("PROBE"))
        {
            Serial.print("NUCODE_DF|1|READY|nonce=");
            Serial.print(nonce);
            Serial.print("|role=beacon");
#if !defined(NUCODE_CAPABILITY_PROBE)
            /** @note capability probe에는 최종 build의 revision 매크로가 아직 없습니다. */
            Serial.print("|core=");
            Serial.print(NUCODE_CORE_REVISION);
            Serial.print("|board=");
            Serial.print(NUCODE_BOARD_REVISION);
            Serial.print("|ncs=");
            Serial.print(NUCODE_NCS_REVISION);
            Serial.print("|zephyr=");
            Serial.println(NUCODE_ZEPHYR_REVISION);
#endif
        }
        else if (matches("START"))
        {
            const Error error = beacon.start();
            if (error != Error::none)
            {
                printError("start", error);
                return;
            }
            ++start_count;
            Serial.print("NUCODE_DF|1|STARTED|nonce=");
            Serial.print(nonce);
            Serial.print("|count=");
            Serial.println(start_count);
        }
        else if (matches("STOP"))
        {
            const Error error = beacon.stop();
            if (error != Error::none)
            {
                printError("stop", error);
                return;
            }
            ++stop_count;
            Serial.print("NUCODE_DF|1|STOPPED|nonce=");
            Serial.print(nonce);
            Serial.print("|count=");
            Serial.println(stop_count);
        }
        else if (matches("INVALID"))
        {
            BeaconConfig invalid = {};
            invalid.cte_length_8us = 0U;
            const Error error = beacon.begin(invalid);
            if (error == Error::invalid_argument)
            {
                Serial.print("NUCODE_DF|1|REJECTED|nonce=");
                Serial.print(nonce);
                Serial.println("|reason=cte_length");
            }
            else
            {
                printError("invalid", error);
            }
        }
        else
        {
            Serial.println("NUCODE_DF|1|ERROR|operation=command|error=invalid");
        }
    }

    /** @brief bounded Serial line을 읽고 명령 한 건을 처리합니다. */
    void pollSerial()
    {
        while (Serial.available() > 0)
        {
            const int incoming = Serial.read();
            if (incoming < 0)
            {
                return;
            }
            const char value = static_cast<char>(incoming);
            if (value == '\r')
            {
                continue;
            }
            if (value == '\n')
            {
                command[command_length] = '\0';
                executeCommand();
                command_length = 0U;
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                command_length = 0U;
                Serial.println("NUCODE_DF|1|ERROR|operation=command|error=length");
                return;
            }
            command[command_length++] = value;
        }
    }
}

/** @brief CTE 길이 160 us와 광고 event당 5회 송신을 준비합니다. */
void setup()
{
    Serial.begin(115200);
    BeaconConfig config = {};
    config.cte_length_8us = 20U;
    config.cte_count = 5U;
    beacon_ready = beacon.begin(config) == Error::none;
    if (!beacon_ready)
    {
        printError("begin", beacon.lastError());
    }
}

/** @brief 공개 API의 시작·중단·잘못된 설정을 Serial로 실험합니다. */
void loop()
{
    if (beacon_ready)
    {
        pollSerial();
    }
    delay(1);
}
