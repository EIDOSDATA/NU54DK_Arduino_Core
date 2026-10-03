/**
 * @file main.cpp
 * @brief 세 NU54DK에서 identity·accept list·재연결 경계를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <stdlib.h>
#include <string.h>

#ifndef M32_PRIV_CORE_REVISION
#error "M32_PRIV_CORE_REVISION is required"
#endif

namespace
{

    constexpr char protocol[] = "M32PRIV|1";
    constexpr char start_prefix[] = "M32PRIV|1|START|nonce=";
    constexpr char arm_prefix[] = "M32PRIV|1|ARM|nonce=";
    constexpr char stop_prefix[] = "M32PRIV|1|STOP|nonce=";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::uint32_t iteration_target = 20U;
    constexpr std::uint32_t reports_per_connection = 5U;
    constexpr std::uint32_t packet_target = 200U;
    constexpr std::uint32_t connection_target = 40U;
    constexpr std::uint8_t manufacturer_type = 0xffU;
    constexpr std::uint8_t privacy_payload_magic[] = {
        0x4dU, 0x33U, 0x32U, 0x50U, 0x52U,
    };
    constexpr std::int64_t session_timeout_ms = 290000;
    constexpr std::int64_t unauthorized_window_ms = 3000;
    constexpr std::int64_t radio_recovery_ms = 250;
    constexpr std::int64_t disconnect_delay_ms = 100;

    char command[256] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool started = false;
    bool finished = false;
    bool stop_requested = false;
    bool callback_context_valid = true;
    std::int64_t deadline_ms = 0;
    struct k_thread *main_thread = nullptr;
    nucode::ble::BLEAddress local_address;

#if defined(NUCODE_M32_PRIV_TARGET)
    nucode::ble::BLEAddress authorized_peer;
    nucode::ble::BLEAddress identity_a_address;
    nucode::ble::BLEAdvertisingSetHandle advertising_set;
    bool advertising_configured = false;
    bool armed = false;
    bool restart_pending = false;
    bool wrong_identity_rejected = false;
    bool active_list_change_rejected = false;
    bool unauthorized_peer_rejected = false;
    std::uint32_t connections = 0U;
    std::uint32_t disconnections = 0U;
    std::int64_t next_action_ms = 0;
#if NUCODE_M32_PRIV_INDEX == 1
    struct bt_conn *unauthorized_connection = nullptr;
    bool unauthorized_pending = false;
    bool unauthorized_cancel_wait = false;
#endif
#else
    enum class PeerPhase : std::uint8_t
    {
        idle,
        recovery,
        scanning,
        connecting,
        connected,
        disconnecting,
        complete,
    };
    nucode::ble::BLEAddress targets[2];
    nucode::ble::BLEAddress observed_target;
    nucode::ble::BLEConnectionHandle active_connection;
    PeerPhase peer_phase = PeerPhase::idle;
    std::uint8_t target_index = 0U;
    std::uint32_t completed_iterations = 0U;
    std::uint32_t current_reports = 0U;
    std::uint32_t packets = 0U;
    std::uint32_t connections[2] = {};
    std::uint32_t disconnections[2] = {};
    std::uint32_t maximum_latency_ms = 0U;
    bool scan_stop_pending = false;
    std::int64_t connect_started_ms = 0;
    std::int64_t next_action_ms = 0;
#endif

    /** @brief 현재 image의 고정 역할 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M32_PRIV_TARGET)
#if NUCODE_M32_PRIV_INDEX == 0
        return "identity_a";
#else
        return "identity_b";
#endif
#else
        return "peer";
#endif
    }

    /** @brief 모든 결과 record에 nonce와 exact Core revision을 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M32_PRIV_CORE_REVISION);
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

    /** @brief 명령에서 exact key의 다음 field를 고정 buffer로 복사합니다. */
    bool copyField(const char *key, char *output, std::size_t capacity)
    {
        const char *begin = ::strstr(command, key);
        if (begin == nullptr || capacity == 0U)
        {
            return false;
        }
        begin += ::strlen(key);
        const char *end = ::strchr(begin, '|');
        const std::size_t length = end == nullptr
                                       ? ::strlen(begin)
                                       : static_cast<std::size_t>(end - begin);
        if (length == 0U || length >= capacity)
        {
            return false;
        }
        ::memcpy(output, begin, length);
        output[length] = '\0';
        return true;
    }

    /** @brief START의 nonce와 exact revision 공통부를 검증합니다. */
    bool acceptStartBase()
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
        char core[41] = {};
        if (!copyField("|core=", core, sizeof(core)) ||
            ::strcmp(core, M32_PRIV_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

    /** @brief address 문자열과 type field를 공개 BLEAddress로 해석합니다. */
    bool parseAddress(const char *address_key, const char *type_key,
                      nucode::ble::BLEAddress &address)
    {
        char text[18] = {};
        char type_text[4] = {};
        if (!copyField(address_key, text, sizeof(text)) ||
            !copyField(type_key, type_text, sizeof(type_text)))
        {
            return false;
        }
        char *end = nullptr;
        const long type = ::strtol(type_text, &end, 10);
        if (end == nullptr || *end != '\0' || type < 0L || type > 1L)
        {
            return false;
        }
        address = nucode::ble::BLEAddress(
            text, type == 0L
                      ? nucode::ble::BLEAddress::Type::public_address
                      : nucode::ble::BLEAddress::Type::random_address);
        return address.valid();
    }

    /** @brief local identity address와 type을 READY record에 기록합니다. */
    void printReady()
    {
        char address[18] = {};
        if (!local_address.format(address, sizeof(address)))
        {
            fail("address_format");
            return;
        }
        Serial.print(protocol);
        Serial.print("|READY|role=");
        Serial.print(roleName());
        Serial.print("|address=");
        Serial.print(address);
        Serial.print("|type=");
        Serial.print(static_cast<unsigned int>(local_address.type()));
        Serial.print("|core=");
        Serial.println(M32_PRIV_CORE_REVISION);
    }

#if defined(NUCODE_M32_PRIV_TARGET)
    /** @brief 고정 role payload를 사용해 filtered connectable 광고를 시작합니다. */
    bool startAdvertising()
    {
        if (!advertising_configured)
        {
            nucode::ble::BLEExtendedAdvertisingParameters parameters{};
            parameters.connectable = true;
            parameters.use_identity_address = true;
            parameters.filter_connections = true;
            parameters.identity = 0U;
            parameters.sid = static_cast<std::uint8_t>(NUCODE_M32_PRIV_INDEX);
            parameters.interval_min = 0x0050U;
            parameters.interval_max = 0x0050U;
            const std::uint8_t payload[] = {
                7U, 0xffU, 0x4dU, 0x33U, 0x32U, 0x50U, 0x52U,
                static_cast<std::uint8_t>(NUCODE_M32_PRIV_INDEX),
            };
            if (!BLEExtendedAdvertising.create(parameters, advertising_set) ||
                !BLEExtendedAdvertising.setData(advertising_set, payload,
                                                sizeof(payload)))
            {
                return false;
            }
            advertising_configured = true;
        }
        return BLEExtendedAdvertising.start(advertising_set);
    }

    /** @brief 잘못된 identity와 실행 중 list 변경을 각 한 번 거부합니다. */
    bool configureTarget()
    {
        if (!BLEAdvertisingLists.clearFilterAccept() ||
            !BLEAdvertisingLists.addFilterAccept(authorized_peer))
        {
            return false;
        }
        nucode::ble::BLEExtendedAdvertisingParameters invalid{};
        invalid.identity = 3U;
        invalid.sid = 0x0fU;
        nucode::ble::BLEAdvertisingSetHandle ignored;
        wrong_identity_rejected = !BLEExtendedAdvertising.create(invalid, ignored);
        return wrong_identity_rejected;
    }

    /** @brief production 광고를 시작한 상태에서 Filter Accept List 변경을 거부합니다. */
    bool startFilteredAdvertising()
    {
        if (!startAdvertising())
        {
            return false;
        }
        active_list_change_rejected = !BLEAdvertisingLists.clearFilterAccept();
        return active_list_change_rejected;
    }

#if NUCODE_M32_PRIV_INDEX == 1
    /** @brief identity_b 기본 identity로 identity_a 연결을 시작해 FAL 거부를 확인합니다. */
    bool startUnauthorizedAttempt()
    {
        bt_addr_le_t peer{};
        peer.type = identity_a_address.type() ==
                            nucode::ble::BLEAddress::Type::public_address
                        ? BT_ADDR_LE_PUBLIC
                        : BT_ADDR_LE_RANDOM;
        ::memcpy(peer.a.val, identity_a_address.data(), sizeof(peer.a.val));
        const int result = bt_conn_le_create(&peer, BT_CONN_LE_CREATE_CONN,
                                             BT_LE_CONN_PARAM_DEFAULT,
                                             &unauthorized_connection);
        if (result != 0 || unauthorized_connection == nullptr)
        {
            return false;
        }
        unauthorized_pending = true;
        next_action_ms = k_uptime_get() + unauthorized_window_ms;
        return true;
    }

    /** @brief 3초 동안 연결되지 않은 unauthorized attempt를 취소합니다. */
    void driveUnauthorizedAttempt()
    {
        const std::int64_t now = k_uptime_get();
        if (unauthorized_pending && now >= next_action_ms)
        {
            unauthorized_pending = false;
            struct bt_conn_info information{};
            if (bt_conn_get_info(unauthorized_connection, &information) == 0 &&
                information.state == BT_CONN_STATE_CONNECTED)
            {
                fail("unauthorized_peer_accepted");
                return;
            }
            static_cast<void>(bt_conn_disconnect(
                unauthorized_connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            bt_conn_unref(unauthorized_connection);
            unauthorized_connection = nullptr;
            unauthorized_cancel_wait = true;
            next_action_ms = now + 1000;
        }
        if (unauthorized_cancel_wait && now >= next_action_ms)
        {
            unauthorized_cancel_wait = false;
            unauthorized_peer_rejected = true;
            if (!startFilteredAdvertising())
            {
                fail("filtered_advertising", BLEDevice.lastDriverError());
                return;
            }
            Serial.print(protocol);
            Serial.print("|NEG|role=identity_b|unauthorized_peer_rejected=1");
            printSuffix();
            Serial.println();
        }
    }
#endif

    /** @brief target의 20회 연결·해제 결과를 출력합니다. */
    void finishTarget()
    {
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
        Serial.print("|connections=");
        Serial.print(connections);
        Serial.print("|disconnections=");
        Serial.print(disconnections);
        Serial.print("|wrong_identity_rejected=");
        Serial.print(wrong_identity_rejected ? 1 : 0);
        Serial.print("|active_list_change_rejected=");
        Serial.print(active_list_change_rejected ? 1 : 0);
        Serial.print("|unauthorized_peer_rejected=");
        Serial.print(unauthorized_peer_rejected ? 1 : 0);
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
#else
    /** @brief 현재 target payload를 찾기 위한 extended scan을 시작합니다. */
    bool startPeerScan()
    {
        current_reports = 0U;
        if (!BLEScan.clearFilters() ||
            !BLEScan.startExtended(false, false, false))
        {
            return false;
        }
        peer_phase = PeerPhase::scanning;
        return true;
    }

    /** @brief AD stream에서 현재 identity 역할의 제조사 payload를 찾습니다. */
    bool matchesTargetPayload(const nucode::ble::BLEScanResult &result)
    {
        if (!result.extended)
        {
            return false;
        }
        std::size_t offset = 0U;
        while (offset < result.payload_length)
        {
            const std::uint8_t length = result.payload[offset];
            if (length == 0U || offset + length >= result.payload_length)
            {
                return false;
            }
            if (length == 7U &&
                result.payload[offset + 1U] == manufacturer_type &&
                ::memcmp(&result.payload[offset + 2U], privacy_payload_magic,
                         sizeof(privacy_payload_magic)) == 0 &&
                result.payload[offset + 7U] == target_index)
            {
                return true;
            }
            offset += static_cast<std::size_t>(length) + 1U;
        }
        return false;
    }

    /** @brief 한 connection마다 역할 payload 광고 5개를 분모에 추가합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *)
    {
        checkCallbackContext();
        if (finished || peer_phase != PeerPhase::scanning ||
            !matchesTargetPayload(result))
        {
            return;
        }
        observed_target = result.address;
        if (current_reports < reports_per_connection)
        {
            ++current_reports;
            ++packets;
        }
        if (current_reports == reports_per_connection)
        {
            scan_stop_pending = true;
        }
    }

    /** @brief 40회 재연결과 200개 identity 광고 분모 결과를 출력합니다. */
    void finishPeer()
    {
        Serial.print(protocol);
        Serial.print("|RESULT|role=peer|connections_a=");
        Serial.print(connections[0]);
        Serial.print("|connections_b=");
        Serial.print(connections[1]);
        Serial.print("|disconnections_a=");
        Serial.print(disconnections[0]);
        Serial.print("|disconnections_b=");
        Serial.print(disconnections[1]);
        Serial.print("|packets=");
        Serial.print(packets);
        Serial.print("|max_latency_ms=");
        Serial.print(maximum_latency_ms);
        Serial.print("|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=peer|status=pass");
        printSuffix();
        Serial.println();
        peer_phase = PeerPhase::complete;
        finished = true;
    }
#endif

    /** @brief 연결 event를 target 재광고 또는 peer 순차 재연결 상태에 반영합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *)
    {
        checkCallbackContext();
#if defined(NUCODE_M32_PRIV_TARGET)
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            if (!armed || information.role != nucode::ble::BLELinkRole::peripheral)
            {
                fail("unauthorized_peer_accepted");
                return;
            }
            ++connections;
            if (connections > iteration_target)
            {
                fail("connection_overflow");
            }
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected && armed)
        {
            ++disconnections;
            if (disconnections > iteration_target || disconnections > connections)
            {
                fail("disconnection_mismatch");
                return;
            }
            if (disconnections == iteration_target)
            {
                finishTarget();
            }
            else
            {
                restart_pending = true;
                next_action_ms = k_uptime_get() + radio_recovery_ms;
            }
        }
#else
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            if (peer_phase != PeerPhase::connecting ||
                information.role != nucode::ble::BLELinkRole::central)
            {
                fail("cross_identity_connection");
                return;
            }
            active_connection = information.connection;
            const std::uint32_t latency = static_cast<std::uint32_t>(
                k_uptime_get() - connect_started_ms);
            if (latency > 1000U)
            {
                fail("connection_latency", static_cast<int>(latency));
                return;
            }
            maximum_latency_ms = latency > maximum_latency_ms
                                     ? latency : maximum_latency_ms;
            ++connections[target_index];
            peer_phase = PeerPhase::connected;
            next_action_ms = k_uptime_get() + disconnect_delay_ms;
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            if (peer_phase != PeerPhase::disconnecting)
            {
                fail("unexpected_disconnect");
                return;
            }
            ++disconnections[target_index];
            active_connection = nucode::ble::BLEConnectionHandle{};
            if (target_index == 0U)
            {
                target_index = 1U;
            }
            else
            {
                target_index = 0U;
                ++completed_iterations;
            }
            if (completed_iterations == iteration_target)
            {
                if (packets != packet_target ||
                    connections[0] + connections[1] != connection_target)
                {
                    fail("denominator_mismatch");
                    return;
                }
                finishPeer();
            }
            else
            {
                peer_phase = PeerPhase::recovery;
                next_action_ms = k_uptime_get() + radio_recovery_ms;
            }
        }
#endif
    }

#if defined(NUCODE_M32_PRIV_TARGET)
    /** @brief target START의 authorized peer와 identity_b 음수 대상 주소를 해석합니다. */
    bool beginTarget()
    {
        if (!acceptStartBase() ||
            !parseAddress("|p=", "|pt=", authorized_peer))
        {
            return false;
        }
#if NUCODE_M32_PRIV_INDEX == 1
        if (!parseAddress("|a=", "|at=", identity_a_address))
        {
            return false;
        }
#endif
        if (!configureTarget())
        {
            return false;
        }
        started = true;
        deadline_ms = k_uptime_get() + session_timeout_ms;
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
#if NUCODE_M32_PRIV_INDEX == 0
        return startFilteredAdvertising();
#else
        return startUnauthorizedAttempt();
#endif
    }

    /** @brief runner ARM 뒤에만 FAL의 authorized peer 연결을 허용합니다. */
    bool armTarget()
    {
        const char *requested_nonce = command + ::strlen(arm_prefix);
        if (!started || armed || ::strcmp(requested_nonce, nonce) != 0 ||
            !advertising_configured || !BLEExtendedAdvertising.running(advertising_set))
        {
            return false;
        }
        armed = true;
        Serial.print(protocol);
        Serial.print("|ARMED|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
        return true;
    }
#else
    /** @brief peer START의 두 exact identity 주소를 해석하고 첫 scan을 시작합니다. */
    bool beginPeer()
    {
        if (!acceptStartBase() ||
            !parseAddress("|a=", "|at=", targets[0]) ||
            !parseAddress("|b=", "|bt=", targets[1]) ||
            targets[0] == targets[1])
        {
            return false;
        }
        started = true;
        deadline_ms = k_uptime_get() + session_timeout_ms;
        Serial.print(protocol);
        Serial.print("|BEGIN|role=peer");
        printSuffix();
        Serial.println();
        return startPeerScan();
    }
#endif

    /** @brief STOP 때 scan·link·set·accept list를 bounded하게 회수합니다. */
    void stopProtocol()
    {
#if defined(NUCODE_M32_PRIV_TARGET)
        bool cleanup = true;
        if (BLEExtendedAdvertising.running(advertising_set))
        {
            cleanup = BLEExtendedAdvertising.stop(advertising_set) && cleanup;
        }
        if (BLEExtendedAdvertising.exists(advertising_set))
        {
            cleanup = BLEExtendedAdvertising.remove(advertising_set) && cleanup;
        }
        cleanup = BLEAdvertisingLists.clearFilterAccept() && cleanup;
#else
        bool cleanup = true;
        if (BLEScan.running())
        {
            cleanup = BLEScan.stop() && cleanup;
        }
        if (active_connection.valid())
        {
            cleanup = BLEConnection.disconnect(active_connection) && cleanup;
        }
#endif
        BLEDevice.end();
        Serial.print(protocol);
        Serial.print("|STOPPED|role=");
        Serial.print(roleName());
        Serial.print("|cleanup=");
        Serial.print(cleanup ? "pass" : "fail");
        printSuffix();
        Serial.println();
        stop_requested = false;
    }

    /** @brief PROBE·START·ARM·STOP 명령만 고정 buffer로 처리합니다. */
    void processCommand()
    {
        if (::strcmp(command, "M32PRIV|1|PROBE") == 0)
        {
            printReady();
            return;
        }
        if (!started && ::strncmp(command, start_prefix,
                                  ::strlen(start_prefix)) == 0)
        {
#if defined(NUCODE_M32_PRIV_TARGET)
            if (!beginTarget())
#else
            if (!beginPeer())
#endif
            {
                fail("start", BLEDevice.lastDriverError());
            }
            return;
        }
#if defined(NUCODE_M32_PRIV_TARGET)
        if (::strncmp(command, arm_prefix, ::strlen(arm_prefix)) == 0)
        {
            if (!armTarget())
            {
                fail("arm");
            }
            return;
        }
#endif
        if (started && ::strncmp(command, stop_prefix,
                                 ::strlen(stop_prefix)) == 0 &&
            ::strcmp(command + ::strlen(stop_prefix), nonce) == 0)
        {
            stop_requested = true;
        }
    }

    /** @brief CR/LF serial 입력을 한 줄씩 processCommand()로 전달합니다. */
    void pollCommand()
    {
        while (Serial.available() > 0)
        {
            const int input = Serial.read();
            if (input == '\r')
            {
                continue;
            }
            if (input != '\n')
            {
                if (command_length + 1U >= sizeof(command))
                {
                    command_length = 0U;
                    fail("command_overflow");
                    return;
                }
                command[command_length++] = static_cast<char>(input);
                command[command_length] = '\0';
                continue;
            }
            processCommand();
            command_length = 0U;
            command[0] = '\0';
        }
    }

#if !defined(NUCODE_M32_PRIV_TARGET)
    /** @brief peer의 scan-stop·connect·disconnect·recovery를 callback 밖에서 진행합니다. */
    void drivePeer()
    {
        const std::int64_t now = k_uptime_get();
        if (scan_stop_pending)
        {
            scan_stop_pending = false;
            if (!BLEScan.stop())
            {
                fail("scan_stop", BLEDevice.lastDriverError());
                return;
            }
            connect_started_ms = now;
            peer_phase = PeerPhase::connecting;
            if (!observed_target.valid() ||
                !BLEConnection.connect(observed_target, active_connection))
            {
                fail("connect", BLEDevice.lastDriverError());
            }
        }
        else if (peer_phase == PeerPhase::connected && now >= next_action_ms)
        {
            peer_phase = PeerPhase::disconnecting;
            if (!BLEConnection.disconnect(active_connection))
            {
                fail("disconnect", BLEDevice.lastDriverError());
            }
        }
        else if (peer_phase == PeerPhase::recovery && now >= next_action_ms)
        {
            if (!startPeerScan())
            {
                fail("scan_restart", BLEDevice.lastDriverError());
            }
        }
    }
#endif

} // namespace

void setup()
{
    main_thread = k_current_get();
    Serial.begin(115200);
    const std::int64_t serial_deadline = k_uptime_get() + 5000;
    while (!Serial && k_uptime_get() < serial_deadline)
    {
        delay(10);
    }
    BLEDevice.onEventInfo(onBleEvent);
#if !defined(NUCODE_M32_PRIV_TARGET)
    BLEScan.onResult(onScanResult);
#endif
    if (!BLEDevice.begin(roleName()) ||
        !BLEIdentity.address(0U, local_address))
    {
        fail("device_begin", BLEDevice.lastDriverError());
    }
}

void loop()
{
    pollCommand();
    if (BLEDevice.initialized())
    {
        BLEDevice.poll();
    }
    if (started && !finished && k_uptime_get() >= deadline_ms)
    {
        fail("session_timeout");
    }
#if defined(NUCODE_M32_PRIV_TARGET)
#if NUCODE_M32_PRIV_INDEX == 1
    if (started && !finished)
    {
        driveUnauthorizedAttempt();
    }
#endif
    if (restart_pending && k_uptime_get() >= next_action_ms)
    {
        restart_pending = false;
        if (!startAdvertising())
        {
            fail("advertising_restart", BLEDevice.lastDriverError());
        }
    }
#else
    if (started && !finished)
    {
        drivePeer();
    }
#endif
    if (stop_requested)
    {
        stopProtocol();
    }
    delay(1);
}
