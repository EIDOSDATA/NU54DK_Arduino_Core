/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 인증된 BLE SMP DFU와 MCUboot image 확인 절차를 실행합니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Secure BLE DFU (MCUboot) (`secure_ble_dfu`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) SecureDfuPeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 외부 ECDSA P-256 signing key와 MCUboot sysbuild가 필요하며 자동 CONFIRM은 하지 않습니다.
 * @par 준비물
 * - NU54DK 보드 1대 — 1) SecureDfuPeripheral (peripheral/server)
 * - 외부 ECDSA P-256 signing key와 MCUboot sysbuild가 필요하며 자동 CONFIRM은 하지 않습니다.
 * @par 설정
 * - Tools → Feature set에서 `secure_ble_dfu` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `DFU image slot=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `version=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `build=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `DFU self-test failed:` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `DFU pairing rejected or timed out` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `DFU image confirm rejected` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE_DirectionFinding/ConnectedCteResponder`
 * - `NUCODE_BLE_DirectionFinding/CteBeacon`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - explicit_security_or_signed_artifact_flow
 * - 예제의 pairing·bond·서명·credential 조건을 생략하지 않고 오류 출력을 확인합니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `ble_dfu`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE_DFU/SecureDfuPeripheral`, sha256 `f806f7e2505799a85325f4395676198c026fe0f1b9f7fb01ce810c597cdb6b55`
 * @nucode_example_setup_end */

/**
 * @file SecureDfuPeripheral.ino
 * @brief 인증된 BLE SMP DFU와 MCUboot image 확인 절차를 실행합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_DFU.h>

#include <string.h>

namespace
{
    /** @brief MCUboot confirm 전에 확인할 초기화 결과입니다. */
    bool self_test_passed = false;

    /** @brief 사용자 응답을 기다리는 SMP 절차입니다. */
    enum class PendingReply : std::uint8_t
    {
        none,
        pairing,
        numeric_comparison,
        passkey_input,
    };

    PendingReply pending_reply = PendingReply::none;
    nucode::ble::BLEConnectionHandle pending_connection = {};
    char command[32] = {};
    std::size_t command_length = 0U;
    bool discarding_command = false;

    /** @brief 초기화 실패를 출력하고 image confirm 없이 정지합니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("DFU self-test failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000);
        }
    }

    /** @brief 현재 MCUboot image의 상태를 UART에 출력합니다. */
    void printStatus()
    {
        const nucode::ble::SecureDfuImageVersion version = BLESecureDfu.version();
        Serial.print("DFU image slot=");
        Serial.print(static_cast<unsigned>(BLESecureDfu.activeSlot()));
        Serial.print(" version=");
        Serial.print(static_cast<unsigned>(version.major));
        Serial.print('.');
        Serial.print(static_cast<unsigned>(version.minor));
        Serial.print('.');
        Serial.print(version.revision);
        Serial.print(" build=");
        Serial.print(version.build);
        Serial.print(" confirmed=");
        Serial.println(BLESecureDfu.confirmed() ? 1 : 0);
    }

    /** @brief 보안 event를 사용자 승인 명령과 해당 connection에 묶습니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            pending_connection = record.connection;
            pending_reply = PendingReply::pairing;
            Serial.println("Pairing request: type PAIR YES or PAIR NO within 30 seconds");
        }
        else if (record.event == nucode::ble::SecurityEvent::passkey_confirmation_requested)
        {
            pending_connection = record.connection;
            pending_reply = PendingReply::numeric_comparison;
            Serial.print("Compare passkey ");
            Serial.print(record.passkey);
            Serial.println(": type VERIFY YES or VERIFY NO within 30 seconds");
        }
        else if (record.event == nucode::ble::SecurityEvent::passkey_input_requested)
        {
            pending_connection = record.connection;
            pending_reply = PendingReply::passkey_input;
            Serial.println("Passkey requested: type PIN followed by six digits");
        }
        else if (record.event == nucode::ble::SecurityEvent::passkey_display)
        {
            Serial.print("Displayed passkey: ");
            Serial.println(record.passkey);
        }
        else if (record.event == nucode::ble::SecurityEvent::security_changed)
        {
            if (record.level >= nucode::ble::SecurityLevel::secure_connections)
            {
                pending_reply = PendingReply::none;
                Serial.println("DFU link authenticated with Secure Connections");
            }
        }
        else if (record.event == nucode::ble::SecurityEvent::pairing_failed ||
                 record.event == nucode::ble::SecurityEvent::pairing_cancelled ||
                 record.event == nucode::ble::SecurityEvent::timeout ||
                 record.event == nucode::ble::SecurityEvent::error)
        {
            pending_reply = PendingReply::none;
            Serial.println("DFU pairing rejected or timed out");
        }
    }

    /** @brief image 확인과 사용자 pairing 응답을 고정 길이 명령으로 처리합니다. */
    void executeCommand(const char *line)
    {
        if (strcmp(line, "STATUS") == 0)
        {
            printStatus();
            return;
        }
        if (strcmp(line, "CONFIRM") == 0)
        {
            if (!self_test_passed || !BLESecureDfu.confirm())
            {
                Serial.println("DFU image confirm rejected");
                return;
            }
            printStatus();
            return;
        }
        if (pending_reply == PendingReply::pairing &&
            (strcmp(line, "PAIR YES") == 0 || strcmp(line, "PAIR NO") == 0))
        {
            const bool accept = strcmp(line, "PAIR YES") == 0;
            const bool applied = BLESecurity.acceptPairing(pending_connection, accept);
            pending_reply = PendingReply::none;
            Serial.println(applied ? "Pairing response applied" : "Pairing response rejected");
            return;
        }
        if (pending_reply == PendingReply::numeric_comparison &&
            (strcmp(line, "VERIFY YES") == 0 || strcmp(line, "VERIFY NO") == 0))
        {
            const bool accept = strcmp(line, "VERIFY YES") == 0;
            const bool applied = BLESecurity.confirmPasskey(pending_connection, accept);
            pending_reply = PendingReply::none;
            Serial.println(applied ? "Numeric comparison applied" : "Numeric comparison rejected");
            return;
        }
        if (pending_reply == PendingReply::passkey_input && strlen(line) == 10U &&
            strncmp(line, "PIN ", 4U) == 0)
        {
            std::uint32_t passkey = 0U;
            for (std::size_t index = 4U; index < 10U; ++index)
            {
                if (line[index] < '0' || line[index] > '9')
                {
                    Serial.println("Passkey format rejected");
                    return;
                }
                passkey = passkey * 10U + static_cast<std::uint32_t>(line[index] - '0');
            }
            const bool applied = BLESecurity.enterPasskey(pending_connection, passkey);
            pending_reply = PendingReply::none;
            Serial.println(applied ? "Passkey applied" : "Passkey rejected");
            return;
        }
        Serial.println("DFU command rejected");
    }

    /** @brief UART의 완결된 줄만 적용하고 overflow는 폐기합니다. */
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
            if (discarding_command)
            {
                if (value == '\n')
                {
                    discarding_command = false;
                }
                continue;
            }
            if (value == '\r')
            {
                continue;
            }
            if (value == '\n')
            {
                command[command_length] = '\0';
                executeCommand(command);
                command_length = 0U;
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                command_length = 0U;
                discarding_command = true;
                Serial.println("DFU command too long");
                continue;
            }
            command[command_length++] = value;
        }
    }
} // namespace

/** @brief MCUboot header·보안·BLE 광고를 확인하고 사용자 명령을 기다립니다. */
void setup()
{
    Serial.begin(115200);
    require(BLESecureDfu.begin(), "mcuboot-image");

    nucode::ble::SecurityConfig security = {};
    security.minimum_level = nucode::ble::SecurityLevel::secure_connections;
    security.bonding = true;
    security.response_timeout_ms = 30000U;
    security.io_capability = nucode::ble::SecurityIoCapability::display_yes_no;
    BLESecurity.onEvent(onSecurityEvent);
    require(BLESecurity.begin(security), "security");
    require(BLEDevice.begin("NU54-Secure-DFU"), "ble-device");
    require(BLEAdvertising.clear(), "advertising-clear");
    require(BLEAdvertising.setConnectable(true), "advertising-connectable");
    require(BLEAdvertising.addServiceUuid(BLESecureDfu.serviceUuid()), "advertising-smp");
    require(BLEAdvertising.setScanResponseName(true), "advertising-name");
    require(BLEAdvertising.start(), "advertising-start");

    self_test_passed = true;
    Serial.println("Secure BLE DFU ready; STATUS reports image, CONFIRM is explicit");
    printStatus();
}

/** @brief SMP 사용자 응답과 명시적 image 확인만 main thread에서 수행합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    pollSerial();
    delay(1);
}
