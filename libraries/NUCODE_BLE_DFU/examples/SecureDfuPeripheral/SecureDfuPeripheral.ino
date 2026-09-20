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
