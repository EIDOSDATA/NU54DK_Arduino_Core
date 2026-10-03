/**
 * @file main.cpp
 * @brief 두 NU54DK에서 LE Power Control과 Path Loss를 유한 반복 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

#ifndef M32_POWER_CORE_REVISION
#error "M32_POWER_CORE_REVISION is required"
#endif

namespace
{

    constexpr char protocol[] = "M32PWR|1";
    constexpr char start_prefix[] = "M32PWR|1|START|nonce=";
    constexpr char peer_name[] = "NU54-M32-PWR";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::uint32_t power_report_target = 20U;
    constexpr std::uint32_t path_report_target = 60U;
    constexpr std::uint32_t power_request_retry_limit = 50U;
    constexpr std::int64_t session_timeout_ms = 240000;

    char command[128] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool started = false;
    bool finished = false;
    bool stop_requested = false;
    bool callback_context_valid = true;
    std::uint32_t power_reports = 0U;
    std::int8_t minimum_power = 127;
    std::int8_t maximum_power = -127;
#if defined(NUCODE_M32_POWER_CENTRAL)
    std::uint32_t path_reports = 0U;
    bool path_started = false;
    std::uint8_t minimum_path_loss = 0xffU;
    std::uint8_t maximum_path_loss = 0U;
#endif
    std::int64_t deadline_ms = 0;
    struct k_thread *main_thread = nullptr;
    nucode::ble::BLEConnectionHandle connection_handle;

    /** @brief 현재 image의 고정 역할 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M32_POWER_CENTRAL)
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief 모든 결과 record에 nonce와 exact Core revision을 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M32_POWER_CORE_REVISION);
    }

    /** @brief 첫 오류만 bounded protocol로 출력합니다. */
    void fail(const char *stage, int code = 0)
    {
        if (finished)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.println();
        finished = true;
    }

    /** @brief callback이 Arduino main thread에서 dispatch됐는지 확인합니다. */
    void checkCallbackContext()
    {
        if (k_current_get() != main_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
    }

    /** @brief START record의 nonce와 exact revision을 검증합니다. */
    bool acceptStart()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        if (::strncmp(command, start_prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *cursor = command + prefix_length;
        for (std::size_t index = 0U; index < nonce_length; ++index)
        {
            const char value = cursor[index];
            if (!((value >= '0' && value <= '9') ||
                  (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        constexpr char core_prefix[] = "|core=";
        if (::strncmp(cursor + nonce_length, core_prefix,
                      sizeof(core_prefix) - 1U) != 0 ||
            ::strcmp(cursor + nonce_length + sizeof(core_prefix) - 1U,
                     M32_POWER_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

    /** @brief 현재 link의 remote 송신 전력 읽기를 하나 제출합니다. */
    bool requestPowerReport()
    {
        for (std::uint32_t attempt = 0U; attempt < power_request_retry_limit; ++attempt)
        {
            if (BLEConnection.requestRemoteTransmitPower(
                    connection_handle, nucode::ble::BLETransmitPowerPhy::le_1m))
            {
                return true;
            }
            if (BLEDevice.lastDriverError() != -EIO)
            {
                return false;
            }
            k_msleep(100);
        }
        return false;
    }

#if defined(NUCODE_M32_POWER_CENTRAL)
    /** @brief low/middle/high 순서로 현재 path loss를 재분류합니다. */
    bool startPathStage()
    {
        nucode::ble::BLEPathLossParameters parameters;
        parameters.high_hysteresis_db = 0U;
        parameters.low_hysteresis_db = 0U;
        const std::uint32_t stage = path_reports % 3U;
        if (stage == 0U)
        {
            parameters.high_threshold_db = 250U;
            parameters.low_threshold_db = 200U;
        }
        else if (stage == 1U)
        {
            parameters.high_threshold_db = 200U;
            parameters.low_threshold_db = 1U;
        }
        else
        {
            parameters.high_threshold_db = 2U;
            parameters.high_hysteresis_db = 0U;
            parameters.low_threshold_db = 0U;
            parameters.low_hysteresis_db = 0U;
        }
        parameters.minimum_connection_events = 1U;
        if (path_started &&
            !BLEConnection.setPathLossMonitoring(connection_handle, false))
        {
            return false;
        }
        if (!BLEConnection.configurePathLossMonitoring(connection_handle, parameters) ||
            !BLEConnection.setPathLossMonitoring(connection_handle, true))
        {
            return false;
        }
        path_started = true;
        return true;
    }

    /** @brief 현재 stage가 기대한 zone인지 검사합니다. */
    bool expectedZone(nucode::ble::BLEPathLossZone zone)
    {
        const std::uint32_t stage = path_reports % 3U;
        return (stage == 0U && zone == nucode::ble::BLEPathLossZone::low) ||
               (stage == 1U && zone == nucode::ble::BLEPathLossZone::middle) ||
               (stage == 2U && zone == nucode::ble::BLEPathLossZone::high);
    }
#endif

    /** @brief 역할별 분모가 끝나면 RESULT와 END를 한 번 출력합니다. */
    void finishIfComplete()
    {
#if defined(NUCODE_M32_POWER_CENTRAL)
        if (power_reports != power_report_target || path_reports != path_report_target)
        {
            return;
        }
#else
        if (power_reports != power_report_target)
        {
            return;
        }
#endif
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
        Serial.print("|power_reports=");
        Serial.print(power_reports);
        Serial.print("|power_min=");
        Serial.print(minimum_power);
        Serial.print("|power_max=");
        Serial.print(maximum_power);
#if defined(NUCODE_M32_POWER_CENTRAL)
        Serial.print("|path_reports=");
        Serial.print(path_reports);
        Serial.print("|path_min=");
        Serial.print(minimum_path_loss);
        Serial.print("|path_max=");
        Serial.print(maximum_path_loss);
#endif
        Serial.print("|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        finished = true;
    }

#if defined(NUCODE_M32_POWER_CENTRAL)
    /** @brief exact name의 connectable peer 하나만 연결합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (finished || (!result.connectable && !result.scan_response))
        {
            return;
        }
        if (!BLEScan.stop() || !BLEConnection.connect(result.address,
                                                      connection_handle))
        {
            fail("connect_start");
        }
    }
#endif

    /** @brief 연결·송신 전력·Path Loss callback을 exact link에 귀속합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (finished && !stop_requested)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            connection_handle = information.connection;
            nucode::ble::BLETransmitPowerLevel local;
            if (!BLEConnection.setTransmitPowerReporting(connection_handle, true, true))
            {
                fail("power_reporting", BLEDevice.lastDriverError());
                return;
            }
            if (!BLEConnection.localTransmitPower(
                    connection_handle, nucode::ble::BLETransmitPowerPhy::le_1m,
                    local))
            {
                fail("local_power", BLEDevice.lastDriverError());
                return;
            }
            if (!requestPowerReport())
            {
                fail("remote_power", BLEDevice.lastDriverError());
                return;
            }
        }
        else if (information.event == nucode::ble::BLEEvent::transmit_power_report &&
                 information.connection == connection_handle &&
                 information.transmit_power.reason ==
                     nucode::ble::BLETransmitPowerReportReason::remote_read_completed)
        {
            const std::int8_t level = information.transmit_power.level_dbm;
            if (level == 127 || level == 126)
            {
                fail("remote_power_unavailable", level);
                return;
            }
            minimum_power = level < minimum_power ? level : minimum_power;
            maximum_power = level > maximum_power ? level : maximum_power;
            ++power_reports;
            Serial.print(protocol);
            Serial.print("|POWER|role=");
            Serial.print(roleName());
            Serial.print("|index=");
            Serial.print(power_reports);
            Serial.print("|level=");
            Serial.print(level);
            printSuffix();
            Serial.println();
            if (power_reports < power_report_target && !requestPowerReport())
            {
                fail("power_request", BLEDevice.lastDriverError());
                return;
            }
#if defined(NUCODE_M32_POWER_CENTRAL)
            if (power_reports == power_report_target && !path_started &&
                !startPathStage())
            {
                fail("path_setup", BLEDevice.lastDriverError());
                return;
            }
#endif
            finishIfComplete();
        }
#if defined(NUCODE_M32_POWER_CENTRAL)
        else if (information.event == nucode::ble::BLEEvent::path_loss_changed &&
                 information.connection == connection_handle)
        {
            if (!expectedZone(information.path_loss.zone))
            {
                fail("path_zone", static_cast<int>(information.path_loss.zone));
                return;
            }
            const std::uint8_t loss = information.path_loss.path_loss_db;
            minimum_path_loss = loss < minimum_path_loss ? loss : minimum_path_loss;
            maximum_path_loss = loss > maximum_path_loss ? loss : maximum_path_loss;
            ++path_reports;
            Serial.print(protocol);
            Serial.print("|PATH|role=central|index=");
            Serial.print(path_reports);
            Serial.print("|zone=");
            Serial.print(static_cast<unsigned int>(information.path_loss.zone));
            Serial.print("|loss=");
            Serial.print(loss);
            printSuffix();
            Serial.println();
            if (path_reports < path_report_target && !startPathStage())
            {
                fail("path_restart", BLEDevice.lastDriverError());
                return;
            }
            finishIfComplete();
        }
#endif
        else if (information.event == nucode::ble::BLEEvent::disconnected &&
                 stop_requested)
        {
            Serial.print(protocol);
            Serial.print("|STOPPED|role=");
            Serial.print(roleName());
            printSuffix();
            Serial.println();
            stop_requested = false;
        }
    }

    /** @brief PROBE·START·STOP command를 최대 고정 길이로 해석합니다. */
    void processCommand()
    {
        if (::strcmp(command, "M32PWR|1|PROBE") == 0)
        {
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|core=");
            Serial.println(M32_POWER_CORE_REVISION);
            return;
        }
        if (!started && acceptStart())
        {
            started = true;
            deadline_ms = k_uptime_get() + session_timeout_ms;
            Serial.print(protocol);
            Serial.print("|BEGIN|role=");
            Serial.print(roleName());
            printSuffix();
            Serial.println();
#if defined(NUCODE_M32_POWER_CENTRAL)
            if (!BLEScan.clearFilters() || !BLEScan.filterName(peer_name) ||
                !BLEScan.start(true))
#else
            if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
                !BLEAdvertising.setScanResponseName(true) || !BLEAdvertising.start())
#endif
            {
                fail("radio_start", BLEDevice.lastDriverError());
            }
            return;
        }
        constexpr char stop_prefix[] = "M32PWR|1|STOP|nonce=";
        if (finished && ::strncmp(command, stop_prefix,
                                  sizeof(stop_prefix) - 1U) == 0 &&
            ::strcmp(command + sizeof(stop_prefix) - 1U, nonce) == 0)
        {
            stop_requested = true;
            if (!connection_handle.valid() ||
                !BLEConnection.connected(connection_handle))
            {
                Serial.print(protocol);
                Serial.print("|STOPPED|role=");
                Serial.print(roleName());
                printSuffix();
                Serial.println();
                stop_requested = false;
            }
            else if (!BLEConnection.disconnect(connection_handle))
            {
                fail("disconnect", BLEDevice.lastDriverError());
            }
            return;
        }
        fail("command");
    }

    /** @brief 한 줄 command를 overflow 없이 수집합니다. */
    void pollSerial()
    {
        while (Serial.available() > 0)
        {
            const int incoming = Serial.read();
            if (incoming == '\r')
            {
                continue;
            }
            if (incoming == '\n')
            {
                command[command_length] = '\0';
                processCommand();
                command_length = 0U;
                continue;
            }
            if (incoming < 0 || command_length + 1U >= sizeof(command))
            {
                fail("command_length");
                command_length = 0U;
                continue;
            }
            command[command_length++] = static_cast<char>(incoming);
        }
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    main_thread = k_current_get();
    BLEDevice.onEventInfo(onBleEvent);
#if defined(NUCODE_M32_POWER_CENTRAL)
    BLEScan.onResult(onScanResult);
#endif
    if (!BLEDevice.begin(peer_name))
    {
        fail("ble_begin", BLEDevice.lastDriverError());
    }
}

void loop()
{
    BLEDevice.poll();
    pollSerial();
    if (started && !finished && k_uptime_get() > deadline_ms)
    {
        fail("timeout");
    }
}
