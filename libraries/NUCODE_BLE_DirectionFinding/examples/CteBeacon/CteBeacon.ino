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
            Serial.print("|role=beacon|core=");
            Serial.print(NUCODE_CORE_REVISION);
            Serial.print("|board=");
            Serial.print(NUCODE_BOARD_REVISION);
            Serial.print("|ncs=");
            Serial.print(NUCODE_NCS_REVISION);
            Serial.print("|zephyr=");
            Serial.println(NUCODE_ZEPHYR_REVISION);
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
