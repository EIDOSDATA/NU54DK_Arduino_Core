/** @file @brief 세 보드에서 새 표준 서비스 wire와 ANS link 격리·BMS 거부를 검증합니다.
 * SPDX-License-Identifier: MIT
 */
#include <Arduino.h>
#include <NUCODE_BLE_Profiles.h>
#include <NUCODE_BLE_ObjectTransfer.h>
#include <NUCODE_BLE_Glucose.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <zephyr/device.h>
#include <zephyr/drivers/watchdog.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gatt.h>
#include "ExpectedReject.h"
#include "ExpectedCgms.h"
using namespace nucode::ble;
using namespace nucode::ble::profiles;
namespace
{
    constexpr char protocol[] = "M33PROFILE|1";
    constexpr Kind kinds[] = {Kind::current_time,   Kind::thermometer,  Kind::cycling,
                              Kind::running,        Kind::elapsed_time, Kind::alert,
                              Kind::bond_management};
    constexpr unsigned samples_required = 5U;
    char command[512] = {};
    size_t command_length = 0U;
    char nonce[33] = {};
    uint8_t nonce_bytes[16] = {};
    bool started = false, failed = false, done = false;
    uint32_t began_at = 0U, last_send = 0U;
    BLEConnectionHandle peer;
    unsigned index = 0U, count = 0U, measurements = 0U, rejected = 0U;
    unsigned maximum_links = 0U, email_deliveries = 0U;
    unsigned alert_denied = 0U, alert_slot = 0U, alert_ccc = 0U, alert_sent = 0U;
    uint8_t phase = 0U;
    uint32_t quiet_since = 0U;
    bool move_next = false;
    unsigned last_gatt = 255U;
    uint32_t last_gatt_at = 0U;
    int last_gatt_status = 0;
    unsigned last_att_error = 0U;
    bool hub_advertised = false;
    unsigned no_ccc_errors = 0U, expected_error_events = 0U;
    unsigned sensor_sent[2][5] = {}, sensor_no_ccc[2][5] = {};
    ExpectedReject<BLEConnectionHandle> att_reject;
    unsigned att_gap_rejects = 0U;
    bool cleanup_requested = false, cleanup_started = false, cleanup_complete = false;
    bool stop_requested = false, stop_reported = false, cleanup_expired = false;
    uint32_t cleanup_at = 0U;
    int watchdog_channel = -1;
    const device *const watchdog = DEVICE_DT_GET(DT_NODELABEL(wdt30));
    PeerAddress startup_bonds[16] = {}, fresh_bond_address{};
    size_t startup_bond_count = 0U, bonds_before_delete = 0U;
    bool startup_bonds_valid = false, fresh_bond = false;
    bool bms_requested = false, bms_verified = false, bms_skipped = false;
    unsigned bms_positive = 0U;
    unsigned bms_client_cleanup = 0U;
    bool bms_client_cleanup_requested = false;
    bool bms_write_submitted = false, bms_write_acknowledged = false;
    bool bms_disconnect_seen = false;
    ExpectedReject<BLEConnectionHandle> bms_reject;
    unsigned bms_teardown_errors = 0U;
    uint32_t bms_requested_at = 0U;
    BLEConnectionHandle bms_request_peer;
    BLEConnectionHandle fresh_bond_link;
    BondState watcher_bond_before = BondState::none;
    bool bms_persistence_fresh_mode = false, bms_persistence_restored_mode = false;
    bool bms_restored_candidate = false, bms_restored_verified = false;
    unsigned bms_persistence_preserved = 0U, bms_persistence_restored = 0U;
    SensorService clock_service(Kind::current_time), temperature(Kind::thermometer),
        cycling(Kind::cycling), running(Kind::running), elapsed(Kind::elapsed_time);
    SensorService *sensors[] = {&clock_service, &temperature, &cycling, &running, &elapsed};
    AlertService alerts;
    BondManagementService bonds;
#if defined(M33_PROFILE_NATIVE)
    ObjectTransferServer object_server;
    ObjectTransferClient object_client;
    GlucoseService glucose;
    const uint8_t initial_object[] = "Native profile read";
    const uint8_t edited_object[] = "Native profile edit";
    unsigned object_stage = 0U, object_operations = 0U, object_writes = 0U;
    unsigned glucose_count = 0U, native_checks = 0U;
    uint8_t glucose_stage = 0U;
    bool object_begin = false;
    bool initial_native_complete = false, native_disconnect_expected = false;
    bool restart_native_scan = false, cancel_on_partial = false;
    unsigned native_sessions = 0U, normal_reconnects = 0U, cancel_reconnects = 0U;
    unsigned coc_cancels = 0U, reconnect_reads = 0U, reconnect_writes = 0U;
    unsigned reconnect_stage = 0U, native_links = 0U, native_disconnects = 0U;
    constexpr unsigned native_test_passkey = 472839U;
    BLEConnectionHandle authenticated_link;
    unsigned authenticated_links = 0U, passkey_events = 0U;
    uint8_t cancel_object[512] = {};
    bool identity_probe_mode = false, identity_ready_reported = false;
    bool identity_restored_candidate = false, identity_restored_verified = false;
    bool identity_level_authenticated = false, identity_primary_captured = false;
    bool identity_primary_verified = false, identity_primary_cleanup_reported = false;
    unsigned identity_stage = 0U;
    BLEConnectionHandle identity_link;
    PeerAddress identity_primary_address{}, identity_current_address{};
    bool native_cleanup_mode = false, native_cleanup_ready = false;
    bool native_cleanup_requested = false, native_cleanup_disconnected = false;
    bool native_cleanup_fresh = false, native_cleanup_restored = false;
    bool native_cleanup_candidate = false, native_cleanup_verified = false;
    bool native_cleanup_authenticated = false, native_cleanup_peer_valid = false;
    BLEConnectionHandle native_cleanup_link;
    PeerAddress native_cleanup_address{};
#endif

    /** @brief 모든 protocol record를 역할·nonce·source revision에 결합합니다. */
    void record(const char *kind, const char *detail = "")
    {
        Serial.print(protocol);
        Serial.print('|');
        Serial.print(kind);
        Serial.print("|role=");
        Serial.print(M33_PROFILE_ROLE);
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M33_PROFILE_CORE_REVISION);
        Serial.print(detail);
        Serial.println();
    }
    void fail(const char *reason)
    {
        if (!failed)
        {
            record("FAIL", reason);
        }
        failed = true;
        cleanup_requested = true;
    }
    /** @brief 실행 thread가 멎어도 8초 안에 radio를 reset 경계로 돌립니다. */
    bool startWatchdog()
    {
        if (!device_is_ready(watchdog))
        {
            return false;
        }
        wdt_timeout_cfg timeout{};
        timeout.window.max = 8000U;
        timeout.flags = WDT_FLAG_RESET_SOC;
        watchdog_channel = wdt_install_timeout(watchdog, &timeout);
        if (watchdog_channel < 0 || wdt_setup(watchdog, 0U) != 0)
        {
            watchdog_channel = -1;
            return false;
        }
        return true;
    }
    /** @brief facade가 handle을 지운 뒤에도 native 연결·시도·해제 중 상태를 셉니다. */
    void countNativeConnections(bt_conn *connection, void *context)
    {
        bt_conn_info information{};
        if (bt_conn_get_info(connection, &information) != 0 ||
            information.state != BT_CONN_STATE_DISCONNECTED)
        {
            ++*static_cast<unsigned *>(context);
        }
    }
    /** @brief poll을 유지하며 실제 native 연결 0과 scan/advertising 종료를 확인합니다. */
    void pollCleanup()
    {
        static bool stop_commands_ok = true;
        if (!cleanup_started)
        {
            cleanup_started = true;
            cleanup_at = millis();
            const bool initialized = BLEDevice.initialized();
            BLEDevice.end();
            if (initialized)
            {
#if defined(CONFIG_BT_OBSERVER)
                const int scan_result = bt_le_scan_stop();
                stop_commands_ok = scan_result == 0 || scan_result == -EALREADY;
#endif
#if defined(CONFIG_BT_BROADCASTER)
                const int advertising_result = bt_le_adv_stop();
                stop_commands_ok = stop_commands_ok &&
                                   (advertising_result == 0 || advertising_result == -EALREADY);
#endif
            }
        }
        unsigned native_active = 0U;
        bt_conn_foreach(BT_CONN_TYPE_LE, countNativeConnections, &native_active);
        const bool quiet = native_active == 0U && BLEConnection.count() == 0U &&
                           !BLEConnection.connecting() && !BLEScan.running() &&
                           !BLEAdvertising.running() && !BLEDevice.initialized() &&
                           stop_commands_ok;
        if (quiet && !cleanup_complete)
        {
            if (watchdog_channel >= 0 && wdt_disable(watchdog) != 0)
            {
                stop_commands_ok = false;
                record("FAIL", "|reason=watchdog-stop");
            }
            else
            {
                watchdog_channel = -1;
                cleanup_complete = true;
            }
        }
        if (cleanup_complete && stop_requested && !stop_reported)
        {
            stop_reported = true;
            record("STOPPED", "|native_links=0|links=0|pending=0|scan=0|advertising=0|watchdog=0");
        }
        if (!cleanup_complete && !cleanup_expired && millis() - cleanup_at >= 5000U)
        {
            cleanup_expired = true;
            char detail[100];
            snprintf(detail, sizeof(detail),
                     "|reason=cleanup-timeout|native_links=%u|stop_commands=%u", native_active,
                     stop_commands_ok ? 1U : 0U);
            record("FAIL", detail);
        }
    }
    /** @brief 실패한 초기화 단계와 facade 원시 오류를 숨기지 않고 기록합니다. */
    bool startStep(bool accepted, const char *stage)
    {
        if (!accepted)
        {
            char detail[180];
            snprintf(detail, sizeof(detail),
                     "|reason=start-step|stage=%s|ble_error=%u|ble_driver=%d|security_error=%u|"
                     "security_driver=%d",
                     stage, static_cast<unsigned>(BLEDevice.lastError()),
                     BLEDevice.lastDriverError(), static_cast<unsigned>(BLESecurity.lastError()),
                     BLESecurity.lastDriverError());
            fail(detail);
        }
        return accepted;
    }
    /** @brief 측정·quiet 경로의 정지 위치를 bounded protocol에 남깁니다. */
    void stateRecord(const char *kind, const char *reason)
    {
        char detail[320];
        snprintf(
            detail, sizeof(detail),
            "|reason=%s|profile_index=%u|phase=%u|count=%u|measurements=%u|rejected=%u"
            "|quiet_since=%u|last_gatt=%u|last_gatt_at=%u|last_gatt_status=%d|last_att_error=%u"
            "|level=%u|peer_valid=%u|connected=%u",
            reason, index, phase, count, measurements, rejected, quiet_since, last_gatt,
            last_gatt_at, last_gatt_status, last_att_error,
            static_cast<unsigned>(BLESecurity.currentLevel(peer)), peer.valid() ? 1U : 0U,
            BLEConnection.connected(peer) ? 1U : 0U);
        if (strcmp(kind, "FAIL") == 0)
        {
            fail(detail);
        }
        else
        {
            record(kind, detail);
        }
    }
    /** @brief 현재 nonce 시험에서 새로 생성한 incoming client bond 한 개만 허용합니다. */
    bool authorizeDeletion(const BondDeleteRequest &request, void *)
    {
        const bool owned = __atomic_load_n(&fresh_bond, __ATOMIC_ACQUIRE) ||
                           (bms_persistence_restored_mode && bms_restored_verified);
        return owned && request.peer == fresh_bond_link &&
               request.length == sizeof(nonce_bytes) &&
               memcmp(request.authorization_code, nonce_bytes, sizeof(nonce_bytes)) == 0;
    }
    bool sameAddress(const PeerAddress &left, const PeerAddress &right)
    {
        return left.type == right.type && memcmp(left.value, right.value, sizeof(left.value)) == 0;
    }
    /** @brief 이전 boot의 bond를 삭제 대상으로 오인하지 않도록 연결 전 목록을 고정합니다. */
    void snapshotBonds()
    {
        startup_bond_count = BLESecurity.bondCount();
        startup_bonds_valid = startup_bond_count <= 16U &&
                               BLESecurity.copyBonds(startup_bonds, 16U) == startup_bond_count;
    }
    /** @brief 부팅 시 고정한 목록에 지정 peer identity가 있었는지 확인합니다. */
    bool startupContains(const PeerAddress &address)
    {
        for (size_t bond = 0U; bond < startup_bond_count; ++bond)
        {
            if (sameAddress(startup_bonds[bond], address))
            {
                return true;
            }
        }
        return false;
    }
    /** @brief 시험 소유 bond 삭제 뒤 기존 부팅 목록이 byte-equivalent인지 확인합니다. */
    bool startupBondsUnchanged()
    {
        PeerAddress current_bonds[16] = {};
        const size_t copied = BLESecurity.copyBonds(current_bonds, 16U);
        bool unchanged = startup_bonds_valid && copied == startup_bond_count &&
                         BLESecurity.bondCount() == startup_bond_count;
        for (size_t original = 0U; original < startup_bond_count; ++original)
        {
            bool found = false;
            for (size_t current = 0U; current < copied; ++current)
            {
                found = found || sameAddress(startup_bonds[original], current_bonds[current]);
            }
            unchanged = unchanged && found;
        }
        return unchanged;
    }
    /** @brief 지정 시험 peer 하나만 빠지고 나머지 부팅 bond가 보존됐는지 확인합니다. */
    bool startupBondsWithout(const PeerAddress &removed)
    {
        PeerAddress current_bonds[16] = {};
        const size_t copied = BLESecurity.copyBonds(current_bonds, 16U);
        bool unchanged = startup_bonds_valid && startupContains(removed) &&
                         copied + 1U == startup_bond_count &&
                         BLESecurity.bondCount() == copied;
        for (size_t original = 0U; original < startup_bond_count; ++original)
        {
            bool found = false;
            for (size_t current = 0U; current < copied; ++current)
            {
                found = found || sameAddress(startup_bonds[original], current_bonds[current]);
            }
            unchanged = unchanged && (sameAddress(startup_bonds[original], removed) ? !found : found);
        }
        return unchanged;
    }
    /** @brief 부팅 bond 목록에 이번 시험 peer 하나만 추가됐는지 확인합니다. */
    bool startupBondsPlus(const PeerAddress &added)
    {
        PeerAddress current_bonds[16] = {};
        const size_t copied = BLESecurity.copyBonds(current_bonds, 16U);
        bool unchanged = startup_bonds_valid && !startupContains(added) &&
                         copied == startup_bond_count + 1U &&
                         BLESecurity.bondCount() == copied;
        bool added_found = false;
        for (size_t current = 0U; current < copied; ++current)
        {
            bool found = sameAddress(current_bonds[current], added);
            added_found = added_found || found;
            for (size_t original = 0U; original < startup_bond_count; ++original)
            {
                found = found || sameAddress(current_bonds[current], startup_bonds[original]);
            }
            unchanged = unchanged && found;
        }
        return unchanged && added_found;
    }
    /** @brief test backend에서 실제 link별 CCC를 읽어 구독되지 않은 전송 폭주를 막습니다. */
    bool subscribed(unsigned slot, unsigned profile)
    {
        struct Link
        {
            uint8_t role;
            bt_conn *connection;
        } link{slot == 0U ? BT_CONN_ROLE_CENTRAL : BT_CONN_ROLE_PERIPHERAL, nullptr};
        bt_conn_foreach(
            BT_CONN_TYPE_LE,
            [](bt_conn *connection, void *context)
            {
                auto &selected = *static_cast<Link *>(context);
                bt_conn_info information{};
                if (bt_conn_get_info(connection, &information) == 0 &&
                    information.state == BT_CONN_STATE_CONNECTED &&
                    information.role == selected.role)
                {
                    selected.connection = bt_conn_ref(connection);
                }
            },
            &link);
        if (link.connection == nullptr)
        {
            return false;
        }
        bt_uuid_16 uuid =
            BT_UUID_INIT_16(profile == 5U ? 0x2a46U : Codec::measurementUuid(kinds[profile]));
        const bt_gatt_attr *attribute = bt_gatt_find_by_uuid(nullptr, 0U, &uuid.uuid);
        const bool result =
            attribute != nullptr &&
            bt_gatt_is_subscribed(link.connection, attribute,
                                  Codec::usesIndications(kinds[profile]) ? BT_GATT_CCC_INDICATE
                                                                         : BT_GATT_CCC_NOTIFY);
        bt_conn_unref(link.connection);
        return result;
    }
    /** @brief 이전 실패 run의 RAM 소유 증거와 결합된 정확한 주소 byte만 해석합니다. */
    bool decodeHex(const char *value, uint8_t *output, size_t length)
    {
        for (size_t index = 0U; index < length * 2U; ++index)
        {
            const char digit = value[index];
            if (!((digit >= '0' && digit <= '9') || (digit >= 'a' && digit <= 'f')))
            {
                return false;
            }
            const uint8_t nibble = digit <= '9' ? digit - '0' : digit - 'a' + 10;
            output[index / 2U] = index % 2U == 0U ? nibble << 4U : output[index / 2U] | nibble;
        }
        return true;
    }
    /** @brief 연결 전 snapshot과 test-owned peer의 합집합이 정확히 일치할 때만 한 bond를 지웁니다. */
    void cleanPreviousAttempt(const char *value)
    {
        const size_t length = strlen(value);
        PeerAddress previous[16] = {}, owned{};
        if (started || length < 60U || strncmp(value + 32U, "|peer=", 6U) != 0 ||
            strncmp(value + 52U, "|before=", 8U) != 0 || (length - 60U) % 14U != 0U ||
            (length - 60U) / 14U > 16U || !decodeHex(value, nonce_bytes, 16U) ||
            !decodeHex(value + 38U, reinterpret_cast<uint8_t *>(&owned), sizeof(owned)))
        {
            fail("|reason=invalid-cleanup-proof");
            return;
        }
        const size_t previous_count = (length - 60U) / 14U;
        for (size_t index = 0U; index < previous_count; ++index)
        {
            if (!decodeHex(value + 60U + index * 14U, reinterpret_cast<uint8_t *>(&previous[index]),
                           sizeof(PeerAddress)) ||
                sameAddress(previous[index], owned))
            {
                fail("|reason=invalid-cleanup-baseline");
                return;
            }
        }
        memcpy(nonce, value, 32U);
        started = true;
        began_at = millis();
        if (!startWatchdog() || !BLESecurity.begin(SecurityConfig{}) ||
            !BLEDevice.begin("M33-CLEANUP"))
        {
            fail("|reason=cleanup-init");
            return;
        }
        snapshotBonds();
        bool matches = startup_bonds_valid && startup_bond_count == previous_count + 1U;
        bool owned_present = false;
        for (size_t current = 0U; current < startup_bond_count; ++current)
        {
            bool found = sameAddress(startup_bonds[current], owned);
            owned_present = owned_present || found;
            for (size_t original = 0U; original < previous_count; ++original)
            {
                found = found || sameAddress(startup_bonds[current], previous[original]);
            }
            matches = matches && found;
        }
        if (!matches || !owned_present || !BLESecurity.eraseBond(owned))
        {
            fail("|reason=cleanup-snapshot-mismatch");
            return;
        }
        snapshotBonds();
        matches = startup_bonds_valid && startup_bond_count == previous_count;
        for (size_t original = 0U; original < previous_count; ++original)
        {
            bool found = false;
            for (size_t current = 0U; current < startup_bond_count; ++current)
            {
                found = found || sameAddress(startup_bonds[current], previous[original]);
            }
            matches = matches && found;
        }
        if (!matches)
        {
            fail("|reason=cleanup-existing-bonds-changed");
            return;
        }
        record("CLEANED", "|removed=1|existing_unchanged=1");
        cleanup_requested = true;
        stop_requested = true;
    }
    /** @brief fixture의 기대 wire는 server와 client가 같은 typed 값에서 생성합니다. */
    bool expectedPacket(unsigned profile, Packet &packet)
    {
        switch (profile)
        {
        case 0U:
            return Codec::encode(CurrentTime{}, packet);
        case 1U:
            return Codec::encode(Temperature{}, packet);
        case 2U:
        {
            CyclingMeasurement value;
            value.has_wheel = false;
            value.crank_revolutions = 123U;
            value.crank_event1024 = 1024U;
            return Codec::encode(value, packet);
        }
        case 3U:
        {
            RunningMeasurement value;
            value.speed256 = 768U;
            value.cadence = 90U;
            return Codec::encode(value, packet);
        }
        case 4U:
            return Codec::encode(ElapsedTime{}, packet);
        case 5U:
            return Codec::encode(Alert{1U, 2U, "profile-hil"}, packet);
        default:
            return false;
        }
    }
    void nextProfile()
    {
        count = 0U;
        phase = 0U;
        quiet_since = 0U;
        if (index >= 7U)
        {
            done = true;
            char detail[200];
            snprintf(detail, sizeof(detail),
                      "|profiles=7|measurements=%u|rejected=%u|att_gap_rejects=%u|bms_positive=%u|"
                      "bms_client_cleanup=%"
                      "u|bms_teardown_errors=%u|bms_persistence_preserved=%u|"
                      "bms_persistence_restored=%u|watcher=%u",
                      measurements, rejected, att_gap_rejects, bms_positive, bms_client_cleanup,
                      bms_teardown_errors, bms_persistence_preserved, bms_persistence_restored,
#if defined(M33_PROFILE_WATCHER)
                      1U
#else
                      0U
#endif
            );
            record("RESULT", detail);
            record("END", "|status=pass");
            return;
        }
        const uint16_t uuid = index == 5U   ? 0x2a44U
                              : index == 6U ? 0x2aa4U
                                            : Codec::measurementUuid(kinds[index]);
        stateRecord("PROGRESS", "profile-discover");
        if (!BLEClient.discover(peer, BLEUuid(static_cast<uint16_t>(kinds[index])), BLEUuid(uuid)))
        {
            fail("|reason=discover-submit");
        }
    }
#if defined(M33_PROFILE_NATIVE)
    /** @brief native object 단계의 event·조건·요청 결과를 분리해 기록합니다. */
    void objectRecord(const char *kind, const char *reason, const ObjectEvent &event, bool accepted)
    {
        constexpr ObjectEventType expected_types[] = {
            ObjectEventType::ready,    ObjectEventType::selected, ObjectEventType::metadata,
            ObjectEventType::received, ObjectEventType::written,  ObjectEventType::metadata,
            ObjectEventType::received, ObjectEventType::created,  ObjectEventType::written,
            ObjectEventType::metadata, ObjectEventType::written,  ObjectEventType::metadata,
            ObjectEventType::received, ObjectEventType::deleted};
        const bool type_ok = object_stage < 14U && event.type == expected_types[object_stage];
        const bool check_initial = object_stage == 2U || object_stage == 3U;
        const bool check_edited = object_stage == 6U || object_stage == 12U;
        const bool length_ok = check_initial        ? event.length == sizeof(initial_object) - 1U
                               : check_edited       ? event.length == sizeof(edited_object) - 1U
                               : object_stage == 9U ? event.length == 0U
                                                    : true;
        const bool data_ok =
            object_stage == 3U ? length_ok && memcmp(event.data, initial_object, event.length) == 0
            : check_edited     ? length_ok && memcmp(event.data, edited_object, event.length) == 0
                               : true;
        char detail[320];
        snprintf(detail, sizeof(detail),
                 "|reason=%s|object_stage=%u|event_type=%u|event_status=%d|object_id=%llu"
                 "|object_length=%u|object_error=%d|type_ok=%u|length_ok=%u|data_ok=%u|accepted=%u|"
                 "object_busy=%u",
                 reason, object_stage, static_cast<unsigned>(event.type), event.status,
                 static_cast<unsigned long long>(event.id), static_cast<unsigned>(event.length),
                 object_client.lastError(), type_ok ? 1U : 0U, length_ok ? 1U : 0U,
                 data_ok ? 1U : 0U, accepted ? 1U : 0U, object_client.busy() ? 1U : 0U);
        if (strcmp(kind, "FAIL") == 0)
        {
            fail(detail);
        }
        else
        {
            record(kind, detail);
        }
    }
    /** @brief 정상 종료와 실제 partial CoC 취소 뒤 재연결 전송을 별도 분모로 확인합니다. */
    void reconnectObject(const ObjectEvent &event)
    {
        bool accepted = false;
        if (event.type == ObjectEventType::ready && reconnect_stage == 0U)
        {
            ++native_sessions;
            if (native_sessions == 2U)
            {
                ++normal_reconnects;
                accepted = object_client.selectFirst();
                reconnect_stage = 1U;
            }
            else if (native_sessions == 3U)
            {
                ++cancel_reconnects;
                accepted = object_client.selectFirst();
                reconnect_stage = 2U;
            }
        }
        else if (event.type == ObjectEventType::selected && reconnect_stage == 1U)
        {
            accepted = object_client.selectNext();
            reconnect_stage = 2U;
        }
        else if (event.type == ObjectEventType::selected && reconnect_stage == 2U)
        {
            accepted = object_client.metadata();
            reconnect_stage = 3U;
        }
        else if (event.type == ObjectEventType::metadata && reconnect_stage == 3U)
        {
            accepted = event.length == (native_sessions == 2U ? sizeof(cancel_object)
                                                              : sizeof(edited_object) - 1U) &&
                       object_client.read();
            cancel_on_partial = native_sessions == 2U;
            reconnect_stage = 4U;
        }
        else if (event.type == ObjectEventType::received && reconnect_stage == 4U &&
                 native_sessions == 3U)
        {
            accepted = event.length == sizeof(edited_object) - 1U &&
                       memcmp(event.data, edited_object, event.length) == 0 &&
                       object_client.write(edited_object, sizeof(edited_object) - 1U);
            reconnect_reads += accepted ? 1U : 0U;
            reconnect_stage = 5U;
        }
        else if (event.type == ObjectEventType::written && reconnect_stage == 5U)
        {
            ++reconnect_writes;
            char detail[280];
            snprintf(
                detail, sizeof(detail),
                "|object_operations=%u|glucose=%u|native_checks=%u|single_link=1|native_sessions=%u"
                "|normal_reconnects=%u|coc_cancels=%u|cancel_reconnects=%u|reconnect_reads=%u|"
                "reconnect_writes=%u|authenticated_links=%u|passkey_events=%u",
                object_operations, glucose_count, native_checks, native_sessions, normal_reconnects,
                coc_cancels, cancel_reconnects, reconnect_reads, reconnect_writes,
                authenticated_links, passkey_events);
            done = true;
            record("RESULT", detail);
            record("END", "|status=pass");
            return;
        }
        if (!accepted)
        {
            objectRecord("FAIL", "reconnect-object-step", event, false);
        }
        else
        {
            objectRecord("PROGRESS", "reconnect-object-step", event, true);
        }
    }
    /** @brief native OTS의 객체 선택부터 CoC round-trip·생성·이름·삭제를 순차 수행합니다. */
    void onObject(const ObjectEvent &event)
    {
        if (event.type == ObjectEventType::disconnected && native_disconnect_expected)
        {
            record("PROGRESS", "|reason=native-disconnected");
            peer = {};
            restart_native_scan = true;
            reconnect_stage = 0U;
            return;
        }
        if (event.type == ObjectEventType::error || event.type == ObjectEventType::disconnected)
        {
            objectRecord("FAIL", "native-object", event, false);
            return;
        }
        if (initial_native_complete)
        {
            reconnectObject(event);
            return;
        }
        bool accepted = false;
        switch (object_stage)
        {
        case 0U:
            if (event.type != ObjectEventType::ready)
            {
                return;
            }
            ++native_sessions;
            native_checks += !object_client.create(513U) && !object_client.select(0U) ? 1U : 0U;
            accepted = object_client.selectFirst();
            break;
        case 1U:
            accepted = event.type == ObjectEventType::selected && object_client.metadata();
            break;
        case 2U:
            accepted = event.type == ObjectEventType::metadata &&
                       event.length == sizeof(initial_object) - 1U && object_client.read();
            break;
        case 3U:
            accepted = event.type == ObjectEventType::received &&
                       event.length == sizeof(initial_object) - 1U &&
                       memcmp(event.data, initial_object, event.length) == 0 &&
                       object_client.write(edited_object, sizeof(edited_object) - 1U);
            break;
        case 4U:
            accepted = event.type == ObjectEventType::written && object_client.metadata();
            break;
        case 5U:
            accepted = event.type == ObjectEventType::metadata && object_client.read();
            break;
        case 6U:
            accepted = event.type == ObjectEventType::received &&
                       event.length == sizeof(edited_object) - 1U &&
                       memcmp(event.data, edited_object, event.length) == 0 &&
                       object_client.create(512U);
            break;
        case 7U:
            accepted =
                event.type == ObjectEventType::created && object_client.rename("native-test");
            break;
        case 8U:
            accepted = event.type == ObjectEventType::written && object_client.metadata();
            break;
        case 9U:
            accepted = event.type == ObjectEventType::metadata && event.length == 0U &&
                       object_client.write(edited_object, sizeof(edited_object) - 1U);
            break;
        case 10U:
            accepted = event.type == ObjectEventType::written && object_client.metadata();
            break;
        case 11U:
            accepted = event.type == ObjectEventType::metadata && object_client.read();
            break;
        case 12U:
            accepted = event.type == ObjectEventType::received &&
                       event.length == sizeof(edited_object) - 1U &&
                       memcmp(event.data, edited_object, event.length) == 0 &&
                       object_client.remove();
            break;
        case 13U:
            accepted = event.type == ObjectEventType::deleted &&
                       BLEClient.discover(peer, BLEUuid(0x181fU), BLEUuid(0x2aa7U));
            break;
        default:
            fail("|reason=extra-object-event");
            return;
        }
        if (!accepted)
        {
            objectRecord("FAIL", "object-step", event, false);
        }
        else
        {
            objectRecord("PROGRESS", "object-step", event, true);
            ++object_stage;
            ++object_operations;
        }
    }
    void nativeRequest(const uint8_t *data, size_t length)
    {
        if (!BLEClient.write(peer, data, length))
        {
            fail("|reason=native-control-submit");
        }
    }
    /** @brief CGMS 실제 지원 명령과 명시적 unsupported 응답을 각각 검증합니다. */
    void nativeGatt(const BLEGattClientEventInfo &event)
    {
        const auto characteristic = BLEClient.remoteCharacteristic(peer);
        char diagnostic[290];
        const auto record_native = [&](const char *kind, const char *reason)
        {
            snprintf(
                diagnostic, sizeof(diagnostic),
                "|reason=%s|glucose_stage=%u|last_gatt=%u|last_gatt_status=%d|"
                "last_att_error=%u|char_valid=%u|char_properties=%u|value_handle=%u|"
                "ccc_handle=%u|client_busy=%u|discovered=%u|ble_error=%u|ble_driver=%d|level=%u",
                reason, glucose_stage, static_cast<unsigned>(event.event), event.status,
                event.att_error, characteristic.valid() ? 1U : 0U,
                static_cast<unsigned>(characteristic.properties()), characteristic.valueHandle(),
                characteristic.cccHandle(), BLEClient.busy(peer) ? 1U : 0U,
                BLEClient.discovered(peer) ? 1U : 0U, static_cast<unsigned>(BLEDevice.lastError()),
                BLEDevice.lastDriverError(), static_cast<unsigned>(BLESecurity.currentLevel(peer)));
            if (strcmp(kind, "FAIL") == 0)
            {
                fail(diagnostic);
            }
            else
            {
                record(kind, diagnostic);
            }
        };
        if (event.event == BLEGattClientEvent::operation_failed)
        {
            record_native("FAIL", "native-gatt");
        }
        else if (event.event == BLEGattClientEvent::discovery_complete)
        {
            record_native("PROGRESS", "native-discovery");
            const bool submitted = glucose_stage == 0U ? BLEClient.subscribeNotifications(peer)
                                                       : BLEClient.subscribeIndications(peer);
            if (!submitted)
            {
                record_native("FAIL", "native-subscribe");
            }
        }
        else if (event.event == BLEGattClientEvent::notification_received)
        {
            GlucoseMeasurement value;
            if (!Codec::decode(event.data, event.length, value) || value.mantissa != 123 ||
                value.exponent != 0)
            {
                fail("|reason=cgms-wire");
                return;
            }
            if (++glucose_count == 2U)
            {
                glucose_stage = 1U;
                if (!BLEClient.unsubscribe(peer))
                {
                    fail("|reason=cgms-unsubscribe");
                }
            }
        }
        else if (event.event == BLEGattClientEvent::unsubscribed)
        {
            const uint16_t uuid = glucose_stage == 1U ? 0x2aacU : 0x2a52U;
            if (!BLEClient.discover(peer, BLEUuid(0x181fU), BLEUuid(uuid)))
            {
                fail("|reason=cgms-control-discover");
            }
        }
        else if (event.event == BLEGattClientEvent::subscribed && glucose_stage != 0U)
        {
            if (glucose_stage == 1U)
            {
                const uint8_t read_interval[] = {2U};
                nativeRequest(read_interval, sizeof(read_interval));
            }
            else
            {
                const uint8_t count_records[] = {4U, 1U};
                nativeRequest(count_records, sizeof(count_records));
            }
        }
        else if (event.event == BLEGattClientEvent::indication_received)
        {
            const uint8_t *data = event.data;
            char response[150];
            char bytes[17] = {};
            for (size_t byte = 0U; byte < event.length && byte < 8U; ++byte)
            {
                snprintf(bytes + byte * 2U, 3U, "%02x", data[byte]);
            }
            snprintf(response, sizeof(response),
                     "|reason=cgms-response|glucose_stage=%u|response_length=%u|response_bytes=%s",
                     glucose_stage, static_cast<unsigned>(event.length), bytes);
            record("PROGRESS", response);
            if (glucose_stage == 1U && expectedCgmsInterval(data, event.length))
            {
                ++native_checks;
                glucose_stage = 2U;
                const uint8_t write_interval[] = {1U, 1U};
                nativeRequest(write_interval, sizeof(write_interval));
            }
            else if (glucose_stage == 2U && event.length == 3U && data[0] == 0x1cU &&
                     data[1] == 1U && data[2] == 1U)
            {
                ++native_checks;
                glucose_stage = 3U;
                const uint8_t start_session[] = {0x1aU};
                nativeRequest(start_session, sizeof(start_session));
            }
            else if (glucose_stage == 3U && event.length == 3U && data[0] == 0x1cU &&
                     data[1] == 0x1aU && data[2] == 2U)
            {
                ++native_checks;
                glucose_stage = 4U;
                const uint8_t stop_session[] = {0x1bU};
                nativeRequest(stop_session, sizeof(stop_session));
            }
            else if (glucose_stage == 4U && event.length == 3U && data[0] == 0x1cU &&
                     data[1] == 0x1bU && data[2] == 2U)
            {
                ++native_checks;
                glucose_stage = 5U;
                if (!BLEClient.unsubscribe(peer))
                {
                    fail("|reason=socp-unsubscribe");
                }
            }
            else if (glucose_stage == 5U && event.length == 4U && data[0] == 5U && data[1] == 0U &&
                     (data[2] != 0U || data[3] != 0U))
            {
                ++native_checks;
                glucose_stage = 6U;
                const uint8_t delete_records[] = {2U, 1U};
                nativeRequest(delete_records, sizeof(delete_records));
            }
            else if (glucose_stage == 6U && event.length == 4U && data[0] == 6U && data[1] == 0U &&
                     data[2] == 2U && data[3] == 2U)
            {
                ++native_checks;
                initial_native_complete = true;
                native_disconnect_expected = true;
                if (!object_client.cancel())
                {
                    fail("|reason=normal-disconnect-submit");
                }
                record("PROGRESS", "|reason=initial-native-session-complete");
            }
            else
            {
                fail("|reason=cgms-control-response");
            }
        }
    }
#endif
    void onGatt(const BLEGattClientEventInfo &event, void *)
    {
        /** @brief 삭제가 유발한 disconnect와 같은 write의 상세 오류만 GAP 오류에 결합합니다. */
        if (bms_write_submitted && index == 6U && phase == 4U &&
            event.event == BLEGattClientEvent::operation_failed)
        {
            if (!bms_reject.detail(event.connection, index, phase, event.status, event.att_error,
                                   millis()))
            {
                fail("|reason=bms-gap-detail-mismatch");
            }
            return;
        }
        if (att_reject.active())
        {
            if (event.event != BLEGattClientEvent::operation_failed ||
                !att_reject.detail(event.connection, index, phase, event.status, event.att_error,
                                   millis()))
            {
                fail("|reason=att-gap-detail-mismatch");
            }
            return;
        }
        if (event.connection != peer || failed || done)
        {
            return;
        }
        last_gatt = static_cast<unsigned>(event.event);
        last_gatt_at = millis();
        last_gatt_status = event.status;
        last_att_error = event.att_error;
#if defined(M33_PROFILE_NATIVE)
        if (native_disconnect_expected)
        {
            return;
        }
        nativeGatt(event);
        return;
#endif
        if (event.event == BLEGattClientEvent::discovery_complete)
        {
            if (index == 5U && phase == 0U)
            {
                const uint8_t malformed[] = {0U};
                phase = 1U;
                if (!att_reject.begin(peer, index, phase, -EIO, BT_ATT_ERR_AUTHORIZATION) ||
                    !BLEClient.write(peer, malformed, sizeof(malformed)))
                {
                    fail("|reason=malformed-submit");
                }
            }
            else if (index == 6U)
            {
                const uint8_t invalid[] = {6U, 0xa5U};
                phase = 1U;
                if (!att_reject.begin(peer, index, phase, -EIO, BT_ATT_ERR_AUTHORIZATION) ||
                    !BLEClient.write(peer, invalid, sizeof(invalid)))
                {
                    fail("|reason=bms-submit");
                }
            }
            else
            {
                const bool submitted = Codec::usesIndications(kinds[index])
                                           ? BLEClient.subscribeIndications(peer)
                                           : BLEClient.subscribeNotifications(peer);
                if (!submitted)
                {
                    fail("|reason=subscribe-submit");
                }
            }
        }
        else if (event.event == BLEGattClientEvent::operation_failed)
        {
            fail("|reason=unexpected-att-error");
        }
        else if (event.event == BLEGattClientEvent::write_complete)
        {
            if (index == 6U && phase == 4U)
            {
                if (!bms_write_submitted || event.connection != bms_request_peer ||
                    bms_write_acknowledged || bms_teardown_errors != 0U ||
                    !bms_reject.acknowledge())
                {
                    fail("|reason=bms-write-ack-mismatch");
                    return;
                }
                bms_write_acknowledged = true;
                record("PROGRESS", "|reason=bms-positive-write-ack");
                return;
            }
            if (index != 5U || phase != 2U)
            {
                fail("|reason=negative-write-accepted");
                return;
            }
            phase = 3U;
            if (!BLEClient.discover(peer, BLEUuid(0x1811U), BLEUuid(0x2a46U)))
            {
                fail("|reason=alert-discover-submit");
            }
        }
        else if (event.event == BLEGattClientEvent::subscribed)
        {
            quiet_since = millis();
            stateRecord("PROGRESS", "subscribed");
        }
        else if (event.event == BLEGattClientEvent::notification_received ||
                 event.event == BLEGattClientEvent::indication_received)
        {
            Packet packet;
            if (!expectedPacket(index, packet) || packet.length != event.length ||
                memcmp(packet.data, event.data, packet.length) != 0 ||
                !Codec::valid(kinds[index], event.data, event.length))
            {
                fail("|reason=wire-mismatch");
                return;
            }
#if defined(M33_PROFILE_WATCHER)
            if (index == 5U)
            {
                fail("|reason=cross-link-alert-leak");
                return;
            }
#endif
            ++measurements;
            if (++count == samples_required && !BLEClient.unsubscribe(peer))
            {
                fail("|reason=unsubscribe-submit");
            }
        }
        else if (event.event == BLEGattClientEvent::unsubscribed)
        {
            stateRecord("PROGRESS", "unsubscribed");
            ++index;
            move_next = true;
        }
    }
    bool advertise();
    void onSecurity(const SecurityEventRecord &event, void *)
    {
        if (cleanup_requested)
        {
            return;
        }
        char detail[180];
        snprintf(detail, sizeof(detail),
                 "|reason=security-event|security_event=%u|level=%u|same_peer=%u|peer_valid=%u",
                 static_cast<unsigned>(event.event), static_cast<unsigned>(event.level),
                 event.connection == peer ? 1U : 0U, peer.valid() ? 1U : 0U);
        record("PROGRESS", detail);
        if (event.event == SecurityEvent::pairing_requested)
        {
#if defined(M33_PROFILE_NATIVE)
            if (identity_probe_mode)
            {
                static_cast<void>(BLESecurity.acceptPairing(event.connection, false));
                fail("|reason=identity-probe-unexpected-pairing-request");
                return;
            }
#else
            if (bms_persistence_restored_mode)
            {
                static_cast<void>(BLESecurity.acceptPairing(event.connection, false));
                fail("|reason=bms-restored-unexpected-pairing-request");
                return;
            }
#endif
            if (!BLESecurity.acceptPairing(event.connection, true))
            {
                fail("|reason=pairing-accept");
            }
        }
#if defined(M33_PROFILE_NATIVE)
        if (event.event == SecurityEvent::passkey_display)
        {
            if (event.passkey != native_test_passkey)
            {
                fail("|reason=native-test-passkey-display");
                return;
            }
            ++passkey_events;
        }
        if (event.event == SecurityEvent::passkey_input_requested)
        {
            if (!BLESecurity.enterPasskey(event.connection, native_test_passkey))
            {
                fail("|reason=native-test-passkey-input");
                return;
            }
            ++passkey_events;
        }
        if (event.event == SecurityEvent::security_changed &&
            event.level >= SecurityLevel::authenticated && event.connection != authenticated_link)
        {
            authenticated_link = event.connection;
            ++authenticated_links;
        }
        if (event.event == SecurityEvent::pairing_failed || event.event == SecurityEvent::timeout ||
            event.event == SecurityEvent::error)
        {
            fail("|reason=native-authentication");
            return;
        }
        if (native_cleanup_mode)
        {
            const bool fresh_event =
                event.event == SecurityEvent::bond_persistence_pending;
            const bool restored_event =
                event.event == SecurityEvent::bond_restored_candidate;
            if (fresh_event || restored_event)
            {
                if (native_cleanup_peer_valid &&
                    !sameAddress(native_cleanup_address, event.peer))
                {
                    fail("|reason=native-cleanup-peer-changed");
                    return;
                }
                native_cleanup_address = event.peer;
                native_cleanup_link = event.connection;
                native_cleanup_peer_valid = true;
            }
            if (fresh_event)
            {
                if (native_cleanup_restored || startupContains(event.peer))
                {
                    fail("|reason=native-cleanup-fresh-identity");
                    return;
                }
                native_cleanup_fresh = true;
            }
            if (restored_event)
            {
                if (native_cleanup_fresh || !startup_bonds_valid ||
                    !startupContains(event.peer))
                {
                    fail("|reason=native-cleanup-restored-identity");
                    return;
                }
                native_cleanup_restored = true;
                native_cleanup_candidate = true;
            }
            if (event.event == SecurityEvent::bond_verified)
            {
                if (!native_cleanup_restored || !native_cleanup_peer_valid ||
                    !sameAddress(native_cleanup_address, event.peer))
                {
                    fail("|reason=native-cleanup-unexpected-verified");
                    return;
                }
                native_cleanup_verified = true;
            }
            if (event.event == SecurityEvent::security_changed &&
                event.level >= SecurityLevel::authenticated)
            {
                native_cleanup_link = event.connection;
                native_cleanup_authenticated = true;
            }
            const bool origin_valid =
                (native_cleanup_fresh && !native_cleanup_restored &&
                 passkey_events == 1U) ||
                (native_cleanup_restored && !native_cleanup_fresh &&
                 native_cleanup_candidate && native_cleanup_verified &&
                 passkey_events == 0U);
            if (!native_cleanup_ready && native_cleanup_peer_valid &&
                native_cleanup_authenticated && origin_valid)
            {
                const bool unchanged = native_cleanup_fresh
                                           ? startup_bonds_valid &&
                                                 !startupContains(native_cleanup_address)
                                           : startupBondsUnchanged();
                if (!unchanged)
                {
                    fail("|reason=native-cleanup-ready-bonds-changed");
                    return;
                }
                native_cleanup_ready = true;
                char cleanup_detail[190];
                snprintf(cleanup_detail, sizeof(cleanup_detail),
                         "|fresh=%u|restored=%u|passkey_events=%u|candidate=%u|"
                         "verified=%u|startup_bonds=%u|existing_unchanged=1",
                         native_cleanup_fresh ? 1U : 0U,
                         native_cleanup_restored ? 1U : 0U,
                         passkey_events,
                         native_cleanup_candidate ? 1U : 0U,
                         native_cleanup_verified ? 1U : 0U,
                         static_cast<unsigned>(startup_bond_count));
                record("NATIVE_CLEANUP_READY", cleanup_detail);
            }
            return;
        }
        if (identity_probe_mode)
        {
            if (event.event == SecurityEvent::bond_persistence_pending ||
                passkey_events != 0U)
            {
                fail("|reason=identity-probe-unexpected-fresh-pairing");
                return;
            }
            if (event.event == SecurityEvent::bond_restored_candidate)
            {
                if (!startup_bonds_valid || !startupContains(event.peer))
                {
                    fail("|reason=identity-probe-restored-peer-missing");
                    return;
                }
                if (identity_stage == 0U)
                {
#if !defined(M33_PROFILE_SECOND_PEER)
                    identity_primary_address = event.peer;
                    identity_primary_captured = true;
#endif
                }
#if defined(M33_PROFILE_SERVER)
                else if (!identity_primary_captured ||
                         sameAddress(identity_primary_address, event.peer))
                {
                    fail("|reason=identity-probe-cross-peer-alias");
                    return;
                }
#endif
                identity_current_address = event.peer;
                identity_link = event.connection;
                identity_restored_candidate = true;
            }
            if (event.event == SecurityEvent::bond_verified && identity_restored_candidate &&
                sameAddress(identity_current_address, event.peer))
            {
                identity_restored_verified = true;
            }
            if (event.event == SecurityEvent::security_changed &&
                event.level >= SecurityLevel::encrypted)
            {
                identity_level_authenticated = true;
            }
            if (!identity_ready_reported && identity_restored_candidate &&
                identity_restored_verified && identity_level_authenticated &&
                passkey_events == 0U)
            {
                if (!startupBondsUnchanged())
                {
                    fail("|reason=identity-probe-bonds-changed");
                    return;
                }
                const bool second =
#if defined(M33_PROFILE_SERVER)
                    identity_stage == 1U;
#elif defined(M33_PROFILE_SECOND_PEER)
                    true;
#else
                    false;
#endif
                identity_ready_reported = true;
#if !defined(M33_PROFILE_SECOND_PEER)
                if (identity_stage == 0U && identity_primary_captured &&
                    sameAddress(identity_primary_address, identity_current_address))
                {
                    identity_primary_verified = true;
                }
#endif
                char identity_detail[180];
                snprintf(identity_detail, sizeof(identity_detail),
                         "|restored=1|peer_distinct=%u|passkey_events=0|candidate=1|verified=1|"
                         "startup_bonds=%u|existing_unchanged=%u",
                         second ? 1U : 0U,
                         static_cast<unsigned>(startup_bond_count),
                         1U
                );
                record(second ? "IDENTITY_SECOND_READY" : "IDENTITY_PRIMARY_READY",
                       identity_detail);
#if defined(M33_PROFILE_SECOND_PEER)
                done = true;
                record("RESULT",
                       "|identity_second_peer=1|restored=1|passkey_events=0|"
                       "existing_unchanged=1");
                record("END", "|status=pass");
#elif defined(M33_PROFILE_SERVER)
                if (second)
                {
                    done = true;
                    snprintf(identity_detail, sizeof(identity_detail),
                             "|identity_primary=1|identity_second_peer=1|identities_distinct=1|"
                             "restored_links=2|passkey_events=0|existing_unchanged=1|"
                             "startup_bonds=%u",
                             static_cast<unsigned>(startup_bond_count));
                    record("RESULT", identity_detail);
                    record("END", "|status=pass");
                }
#endif
            }
            return;
        }
#endif
#if !defined(M33_PROFILE_NATIVE) && !defined(M33_PROFILE_WATCHER)
        const bool bms_role_link =
#if defined(M33_PROFILE_SERVER)
            BLEConnection.role(event.connection) == BLELinkRole::peripheral;
#else
            event.connection == peer;
#endif
        if (bms_persistence_restored_mode && bms_role_link &&
            event.event == SecurityEvent::bond_restored_candidate)
        {
            if (!startup_bonds_valid || !startupContains(event.peer))
            {
                fail("|reason=bms-restored-peer-missing");
                return;
            }
            bms_restored_candidate = true;
            fresh_bond_link = event.connection;
            fresh_bond_address = event.peer;
        }
        if (bms_persistence_restored_mode && bms_role_link &&
            event.event == SecurityEvent::bond_verified && bms_restored_candidate &&
            sameAddress(fresh_bond_address, event.peer))
        {
            bms_restored_verified = true;
        }
        if (startup_bonds_valid && !__atomic_load_n(&fresh_bond, __ATOMIC_ACQUIRE) &&
            event.event == SecurityEvent::bond_persistence_pending &&
#if defined(M33_PROFILE_SERVER)
            BLEConnection.role(event.connection) == BLELinkRole::peripheral)
#else
            event.connection == peer)
#endif
        {
            bool existed = false;
            for (size_t bond = 0U; bond < startup_bond_count; ++bond)
            {
                existed = existed || sameAddress(startup_bonds[bond], event.peer);
            }
            if (!existed)
            {
                fresh_bond_link = event.connection;
                fresh_bond_address = event.peer;
                __atomic_store_n(&fresh_bond, true, __ATOMIC_RELEASE);
                record("PROGRESS", "|reason=fresh-test-bond");
            }
        }
#endif
#if defined(M33_PROFILE_SERVER) && !defined(M33_PROFILE_NATIVE)
        if (event.connection == peer && event.event == SecurityEvent::security_changed &&
            event.level >= SecurityLevel::encrypted && !hub_advertised)
        {
            if (advertise())
            {
                hub_advertised = true;
                record("PROGRESS", "|reason=hub-ready");
            }
        }
#elif !defined(M33_PROFILE_SERVER)
        if (event.connection == peer && event.event == SecurityEvent::security_changed &&
#if defined(M33_PROFILE_NATIVE)
            event.level >= SecurityLevel::authenticated)
#else
            event.level >= SecurityLevel::encrypted)
#endif
        {
#if defined(M33_PROFILE_NATIVE)
            object_begin = true;
#else
            move_next = true;
#endif
        }
#endif
    }
    bool advertise()
    {
        constexpr uint16_t company =
#if defined(M33_PROFILE_WATCHER)
            0x054eU;
#else
            0x054dU;
#endif
        return startStep(BLEAdvertising.clear(), "advertising-clear") &&
               startStep(
                   BLEAdvertising.setManufacturerData(company, nonce_bytes, sizeof(nonce_bytes)),
                   "advertising-data") &&
               startStep(BLEAdvertising.start(), "advertising-start");
    }
    void onLink(const BLEEventInfo &event, void *)
    {
        if (cleanup_requested)
        {
            return;
        }
        if (event.event == BLEEvent::error)
        {
            if (BLEDevice.lastDriverError() == -ENOTCONN && expected_error_events != 0U)
            {
                --expected_error_events;
                ++no_ccc_errors;
                return;
            }
#if !defined(M33_PROFILE_NATIVE) && !defined(M33_PROFILE_SERVER)
            if (bms_write_submitted && !bms_write_acknowledged && bms_teardown_errors == 0U &&
                index == 6U && phase == 4U && peer == bms_request_peer &&
                bms_reject.gap(peer, index, phase, BLEDevice.lastDriverError(),
                               BLEClient.lastAttError(peer), millis()))
            {
                return;
            }
            if (att_reject.active() && att_gap_rejects < 3U && BLEConnection.connected(peer) &&
                att_reject.gap(peer, index, phase, BLEDevice.lastDriverError(),
                               BLEClient.lastAttError(peer), millis()))
            {
                return;
            }
#endif
            char detail[230];
            snprintf(detail, sizeof(detail),
                     "|reason=unexpected-gap-error|ble_error=%u|ble_driver=%d|last_att_error=%u|"
                     "profile_index=%u|phase=%u|alert_slot=%u|alert_ccc=%u|alert_sent=%u",
                     static_cast<unsigned>(BLEDevice.lastError()), BLEDevice.lastDriverError(),
                     static_cast<unsigned>(BLEClient.lastAttError(peer)), index, phase, alert_slot,
                     alert_ccc, alert_sent);
            fail(detail);
            return;
        }
        if (event.event == BLEEvent::connected || event.event == BLEEvent::disconnected ||
            event.event == BLEEvent::error)
        {
            char detail[200];
            snprintf(detail, sizeof(detail),
                     "|reason=gap-event|gap_event=%u|link_role=%u|hci_reason=%u|same_peer=%u|"
                     "event_handle_valid=%u|peer_valid=%u|connected=%u|ble_driver=%d",
                     static_cast<unsigned>(event.event), static_cast<unsigned>(event.role),
                     static_cast<unsigned>(event.reason), event.connection == peer ? 1U : 0U,
                     event.connection.valid() ? 1U : 0U, peer.valid() ? 1U : 0U,
                     BLEConnection.connected(event.connection) ? 1U : 0U,
                     BLEDevice.lastDriverError());
            record("PROGRESS", detail);
        }
#if defined(M33_PROFILE_NATIVE)
        if (native_cleanup_mode && event.event == BLEEvent::disconnected &&
            event.connection == native_cleanup_link)
        {
            ++native_disconnects;
            native_cleanup_disconnected = true;
            return;
        }
#endif
#if defined(M33_PROFILE_SERVER)
        static bool hub_started = false;
        if (event.event == BLEEvent::connected)
        {
#if defined(M33_PROFILE_NATIVE)
            ++native_links;
            if (identity_probe_mode || native_cleanup_mode)
            {
                if (identity_probe_mode)
                {
                    identity_link = event.connection;
                }
                else
                {
                    native_cleanup_link = event.connection;
                }
                if (!BLESecurity.requestSecurity(event.connection))
                {
                    fail(native_cleanup_mode
                             ? "|reason=native-cleanup-security-submit"
                             : "|reason=identity-security-submit");
                }
                return;
            }
#endif
            if (BLEConnection.count() > maximum_links)
            {
                maximum_links = BLEConnection.count();
            }
            if (event.connection == peer && !hub_started)
            {
                hub_started = true;
                if (!BLESecurity.requestSecurity(peer))
                {
                    fail("|reason=watcher-security");
                    return;
                }
                record("PROGRESS", "|reason=hub-security-submitted");
            }
        }
#if defined(M33_PROFILE_NATIVE)
        if (event.event == BLEEvent::disconnected)
        {
            ++native_disconnects;
            if (identity_probe_mode && event.connection == identity_link)
            {
                if (identity_stage != 0U || !identity_ready_reported)
                {
                    fail("|reason=identity-primary-release-state");
                    return;
                }
                if (!startupBondsUnchanged())
                {
                    fail("|reason=identity-primary-bonds-changed");
                    return;
                }
                identity_stage = 1U;
                identity_ready_reported = false;
                identity_restored_candidate = false;
                identity_restored_verified = false;
                identity_level_authenticated = false;
                identity_link = {};
                if (!advertise())
                {
                    fail("|reason=identity-second-peer-readvertise");
                    return;
                }
                record("IDENTITY_PRIMARY_RELEASED",
                       "|primary_preserved=1|existing_unchanged=1");
                return;
            }
            if (!advertise())
            {
                fail("|reason=native-readvertise");
            }
        }
#endif
        if (event.event == BLEEvent::disconnected && event.connection == peer)
        {
            stateRecord("FAIL", "hub-watcher-disconnected");
        }
#else
#if !defined(M33_PROFILE_NATIVE) && !defined(M33_PROFILE_WATCHER)
        if (bms_write_submitted && index == 6U && phase == 4U &&
            event.event == BLEEvent::disconnected && event.connection == bms_request_peer)
        {
            if (bms_disconnect_seen)
            {
                fail("|reason=bms-duplicate-disconnect");
                return;
            }
            bms_disconnect_seen = true;
        }
#endif
#if defined(M33_PROFILE_WATCHER)
        if (event.event == BLEEvent::connected)
        {
            peer = event.connection;
        }
#endif
#if !defined(M33_PROFILE_WATCHER)
        if (event.connection == peer && event.event == BLEEvent::connected &&
            !BLESecurity.requestSecurity(peer))
        {
            fail("|reason=security-submit");
        }
#endif
        if (event.connection == peer && event.event == BLEEvent::disconnected && !done
#if defined(M33_PROFILE_NATIVE)
            && !native_disconnect_expected
#elif !defined(M33_PROFILE_WATCHER)
            && !(index == 6U && phase == 4U)
#endif
        )
        {
            fail("|reason=early-disconnect");
        }
#endif
    }
    void onScan(const BLEScanResult &result, void *)
    {
        if (cleanup_requested || peer.valid() || !result.connectable)
        {
            return;
        }
        size_t cursor = 0U;
        while (cursor < result.payload_length)
        {
            const uint8_t length = result.payload[cursor];
            if (length == 0U || cursor + length >= result.payload_length)
            {
                return;
            }
            constexpr uint8_t company_low =
#if defined(M33_PROFILE_SERVER)
                0x4eU;
#else
                0x4dU;
#endif
            if (length == 19U && result.payload[cursor + 1U] == 0xffU &&
                result.payload[cursor + 2U] == company_low &&
                result.payload[cursor + 3U] == 0x05U &&
                memcmp(result.payload + cursor + 4U, nonce_bytes, sizeof(nonce_bytes)) == 0)
            {
                record("PROGRESS", "|reason=scan-match");
                if (!BLEScan.stop() || !BLEConnection.connect(result.address, peer))
                {
                    fail("|reason=connect-submit");
                }
                else
                {
                    record("PROGRESS", "|reason=connect-submitted");
                }
                return;
            }
            cursor += length + 1U;
        }
    }
    bool start(const char *line)
    {
        constexpr char prefix[] = "M33PROFILE|1|START|nonce=";
        if (started || strncmp(line, prefix, sizeof(prefix) - 1U) != 0)
        {
            return false;
        }
        const char *value = line + sizeof(prefix) - 1U;
        constexpr size_t base_length = 78U;
        const size_t value_length = strlen(value);
        if (value_length < base_length || strncmp(value + 32U, "|core=", 6U) != 0 ||
            strncmp(value + 38U, M33_PROFILE_CORE_REVISION, 40U) != 0)
        {
            return false;
        }
#if defined(M33_PROFILE_NATIVE)
        identity_probe_mode = value_length == base_length + 24U &&
                              strcmp(value + base_length, "|mode=native-second-peer") == 0;
        native_cleanup_mode = value_length == base_length + 20U &&
                              strcmp(value + base_length, "|mode=native-cleanup") == 0;
        if (value_length != base_length && !identity_probe_mode && !native_cleanup_mode)
        {
            return false;
        }
#else
        bms_persistence_fresh_mode = value_length == base_length + 15U &&
                                     strcmp(value + base_length, "|mode=bms-fresh") == 0;
        bms_persistence_restored_mode = value_length == base_length + 18U &&
                                        strcmp(value + base_length, "|mode=bms-restored") == 0;
        if (value_length != base_length && !bms_persistence_fresh_mode &&
            !bms_persistence_restored_mode)
        {
            return false;
        }
#endif
        for (size_t i = 0U; i < 32U; ++i)
        {
            const char digit = value[i];
            if (!((digit >= '0' && digit <= '9') || (digit >= 'a' && digit <= 'f')))
            {
                return false;
            }
            const uint8_t nibble = digit <= '9' ? digit - '0' : digit - 'a' + 10;
            nonce_bytes[i / 2U] = (i % 2U == 0U) ? nibble << 4U : nonce_bytes[i / 2U] | nibble;
        }
        memcpy(nonce, value, 32U);
        started = true;
        began_at = millis();
        if (!startWatchdog())
        {
            fail("|reason=watchdog-start");
            return false;
        }
        SecurityConfig security;
#if defined(M33_PROFILE_NATIVE)
        security.minimum_level = identity_probe_mode ? SecurityLevel::encrypted
                                                     : SecurityLevel::authenticated;
        if (identity_probe_mode)
        {
            security.io_capability = SecurityIoCapability::no_input_output;
        }
#if defined(M33_PROFILE_SERVER)
        else
        {
            security.io_capability = SecurityIoCapability::display_only;
        }
#else
        else
        {
            security.io_capability = SecurityIoCapability::keyboard_only;
        }
#endif
        if (!identity_probe_mode && bt_passkey_set(native_test_passkey) != 0)
        {
            fail("|reason=native-fixed-passkey-setup");
            return false;
        }
#else
        security.io_capability = SecurityIoCapability::no_input_output;
#endif
        BLESecurity.onEvent(onSecurity);
        BLEDevice.onEventInfo(onLink);
        BLEClient.onDetailedEvent(onGatt);
        BLEScan.onResult(onScan);
        if (!startStep(BLESecurity.begin(security), "security-begin"))
        {
            return false;
        }
#if defined(M33_PROFILE_SERVER)
#if defined(M33_PROFILE_NATIVE)
        uint64_t id = 0U;
        for (unsigned byte = 0U; byte < sizeof(cancel_object); ++byte)
        {
            cancel_object[byte] = static_cast<uint8_t>(byte);
        }
        if (!startStep(BLEDevice.begin("M33-NATIVE"), "native-device-begin"))
        {
            return false;
        }
        if (!identity_probe_mode && !native_cleanup_mode &&
            (!startStep(object_server.begin(), "object-server-begin") ||
             !startStep(glucose.begin(), "glucose-begin") ||
             !startStep(object_server.add("native-initial", initial_object,
                                          sizeof(initial_object) - 1U, true, true, id),
                        "object-add") ||
             !startStep(object_server.add("native-cancel", cancel_object, sizeof(cancel_object),
                                          true, true, id),
                        "cancel-object-add")))
        {
            return false;
        }
        if (identity_probe_mode || native_cleanup_mode)
        {
            snapshotBonds();
        }
        if (!advertise())
        {
            return false;
        }
#else
        for (unsigned sensor_index = 0U; sensor_index < 5U; ++sensor_index)
        {
            char stage[32];
            snprintf(stage, sizeof(stage), "sensor-begin-%u", sensor_index);
            if (!startStep(sensors[sensor_index]->begin(), stage))
            {
                return false;
            }
        }
        if (!startStep(alerts.begin(), "alerts-begin") ||
            !startStep(bonds.begin(authorizeDeletion), "bonds-begin") ||
            !startStep(BLEDevice.begin("M33-PROFILES"), "standard-device-begin"))
        {
            return false;
        }
        snapshotBonds();
        if (!startStep(BLEScan.start(true), "hub-scan-start"))
        {
            return false;
        }
        record("PROGRESS", "|reason=hub-scan-ready");
#endif
#else
        if (!startStep(BLEDevice.begin("M33-PROFILE-C"), "peer-device-begin"))
        {
            return false;
        }
        snapshotBonds();
        if (
#if defined(M33_PROFILE_WATCHER)
            !advertise()
#else
            !startStep(BLEScan.start(true), "client-scan-start")
#endif
        )
        {
            return false;
        }
#if defined(M33_PROFILE_WATCHER)
        record("PROGRESS", "|reason=advertising-ready");
#endif
#endif
        record("BEGIN");
        return true;
    }
    void handleCommand()
    {
#if defined(M33_PROFILE_NATIVE)
        constexpr char native_cleanup_command[] =
            "M33PROFILE|1|NATIVE_CLEAN|nonce=";
#endif
        if (strcmp(command, "M33PROFILE|1|PROBE") == 0)
        {
            record("READY");
        }
        else if (strncmp(command, "M33PROFILE|1|CLEAN|nonce=", 25U) == 0)
        {
            cleanPreviousAttempt(command + 25U);
        }
#if defined(M33_PROFILE_NATIVE)
        else if (strncmp(command, native_cleanup_command,
                         sizeof(native_cleanup_command) - 1U) == 0 &&
                 strcmp(command + sizeof(native_cleanup_command) - 1U, nonce) == 0 &&
                 native_cleanup_mode && native_cleanup_ready &&
                 !native_cleanup_requested && !cleanup_requested)
        {
            native_cleanup_requested = true;
            native_disconnect_expected = true;
            if (!BLEConnection.disconnect(native_cleanup_link))
            {
                fail("|reason=native-cleanup-disconnect");
            }
        }
        else if (strncmp(command, "M33PROFILE|1|IDENTITY_RELEASE|nonce=", 36U) == 0 &&
                 strcmp(command + 36U, nonce) == 0 && identity_probe_mode &&
                 identity_ready_reported && !cleanup_requested)
        {
#if defined(M33_PROFILE_SERVER) || defined(M33_PROFILE_SECOND_PEER)
            fail("|reason=identity-release-role");
#else
            if (!startupBondsUnchanged())
            {
                fail("|reason=identity-primary-bonds-changed");
                return;
            }
            done = true;
            native_disconnect_expected = true;
            record("RESULT",
                   "|identity_primary=1|restored=1|passkey_events=0|existing_unchanged=1");
            record("END", "|status=pass");
            if (!BLEConnection.disconnect(peer))
            {
                fail("|reason=identity-primary-disconnect");
            }
#endif
        }
        else if (strncmp(command, "M33PROFILE|1|CLEAN_PRIMARY|nonce=", 34U) == 0 &&
                 strcmp(command + 34U, nonce) == 0 && identity_probe_mode &&
                 identity_primary_captured && identity_primary_verified &&
                 !identity_primary_cleanup_reported && !cleanup_requested)
        {
#if defined(M33_PROFILE_SECOND_PEER)
            fail("|reason=identity-primary-cleanup-role");
#else
            bool second_peer_preserved = true;
#if defined(M33_PROFILE_SERVER)
            second_peer_preserved = identity_stage == 1U && identity_ready_reported &&
                                    identity_restored_verified &&
                                    !sameAddress(identity_primary_address,
                                                 identity_current_address) &&
                                    startupContains(identity_current_address) &&
                                    BLESecurity.bondState(identity_link) == BondState::verified;
#else
            second_peer_preserved = identity_stage == 0U && identity_ready_reported && done;
#endif
            if (!second_peer_preserved ||
                !BLESecurity.eraseBond(identity_primary_address) ||
                !startupBondsWithout(identity_primary_address))
            {
                fail("|reason=identity-primary-scoped-cleanup");
                return;
            }
            identity_primary_cleanup_reported = true;
#if defined(M33_PROFILE_SERVER)
            record("IDENTITY_PRIMARY_CLEANED",
                   "|removed=1|primary_absent=1|existing_unchanged=1|"
                   "second_peer_preserved=1");
#else
            record("IDENTITY_PRIMARY_CLEANED",
                   "|removed=1|primary_absent=1|existing_unchanged=1|"
                   "second_peer_preserved=not_applicable");
#endif
#endif
        }
#endif
#if !defined(M33_PROFILE_NATIVE)
        else if (((strncmp(command, "M33PROFILE|1|ARM|nonce=", 23U) == 0 &&
                   strcmp(command + 23U, nonce) == 0) ||
                  (strncmp(command, "M33PROFILE|1|ARM_RESTORED|nonce=", 32U) == 0 &&
                   strcmp(command + 32U, nonce) == 0)) &&
                 started && !cleanup_requested)
        {
            const bool restored = bms_persistence_restored_mode && bms_restored_verified &&
                                  BLESecurity.bondState(fresh_bond_link) == BondState::verified;
            const bool fresh = __atomic_load_n(&fresh_bond, __ATOMIC_ACQUIRE) &&
                               BLESecurity.bondState(fresh_bond_link) ==
                                   BondState::persistence_pending;
            if ((fresh || restored) && BLEConnection.connected(peer))
            {
                bonds_before_delete = BLESecurity.bondCount();
                watcher_bond_before = BLESecurity.bondState(peer);
                bms_requested = true;
                bonds.setArmed(true);
                record("BMS_ARMED", restored ? "|fresh=0|restored=1"
                                              : "|fresh=1|restored=0");
            }
            else
            {
                bms_skipped = true;
                record("BMS_SKIPPED", "|reason=preexisting-or-unproven-bond");
            }
        }
        else if (strncmp(command, "M33PROFILE|1|PRESERVE|nonce=", 28U) == 0 &&
                 strcmp(command + 28U, nonce) == 0 && bms_persistence_fresh_mode &&
                 __atomic_load_n(&fresh_bond, __ATOMIC_ACQUIRE) && !cleanup_requested)
        {
            if (!startupBondsPlus(fresh_bond_address))
            {
                fail("|reason=bms-persistence-fresh-snapshot");
                return;
            }
            bms_persistence_preserved = 1U;
            record("BMS_PRESERVED", "|fresh=1|bond_present=1|existing_unchanged=1");
        }
        else if (strncmp(command, "M33PROFILE|1|BMS_DELETE|nonce=", 30U) == 0 &&
                 strcmp(command + 30U, nonce) == 0 && index == 6U && phase == 3U &&
                 !cleanup_requested)
        {
            uint8_t request[17] = {3U};
            memcpy(request + 1U, nonce_bytes, sizeof(nonce_bytes));
            phase = 4U;
            bms_request_peer = peer;
            bms_write_submitted = true;
            bms_requested_at = millis();
            if (!bms_reject.begin(peer, index, phase, -ENOTCONN, 0U) ||
                !BLEClient.write(peer, request, sizeof(request)))
            {
                fail("|reason=bms-positive-submit");
            }
        }
        else if (strncmp(command, "M33PROFILE|1|BMS_PRESERVED|nonce=", 33U) == 0 &&
                 strcmp(command + 33U, nonce) == 0 && bms_persistence_fresh_mode &&
                 index == 6U && phase == 3U && !cleanup_requested)
        {
            if (!__atomic_load_n(&fresh_bond, __ATOMIC_ACQUIRE) ||
                !startupBondsPlus(fresh_bond_address))
            {
                fail("|reason=bms-client-persistence-fresh-snapshot");
                return;
            }
            bms_persistence_preserved = 1U;
            ++index;
            move_next = true;
        }
        else if (((strncmp(command, "M33PROFILE|1|BMS_DONE|nonce=", 28U) == 0 && phase == 4U) ||
                  (strncmp(command, "M33PROFILE|1|BMS_SKIP|nonce=", 28U) == 0 && phase == 3U)) &&
                 strcmp(command + 28U, nonce) == 0 && index == 6U && !cleanup_requested)
        {
            bms_positive = phase == 4U ? 1U : 0U;
            if (bms_positive != 0U)
            {
                bms_client_cleanup_requested = true;
            }
            else
            {
                ++index;
                move_next = true;
            }
        }
#endif
        else if (strncmp(command, "M33PROFILE|1|STOP|nonce=", 24U) == 0)
        {
            if (!started && strlen(command + 24U) == 32U)
            {
                for (size_t digit = 24U; digit < 56U; ++digit)
                {
                    if (!((command[digit] >= '0' && command[digit] <= '9') ||
                          (command[digit] >= 'a' && command[digit] <= 'f')))
                    {
                        fail("|reason=invalid-stop-nonce");
                        return;
                    }
                }
                memcpy(nonce, command + 24U, 32U);
            }
            if (strcmp(command + 24U, nonce) != 0)
            {
                fail("|reason=stop-nonce-mismatch");
                return;
            }
            char detail[160];
            snprintf(detail, sizeof(detail),
                      "|max_links=%u|email_deliveries=%u|alert_denied=%u|bond_deletions=%u|bms_"
                      "positive=%u|bms_"
                      "skipped=%u|bms_persistence_preserved=%u|bms_persistence_restored=%u",
                      maximum_links, email_deliveries, alert_denied,
                      static_cast<unsigned>(bonds.acceptedCount()), bms_verified ? 1U : 0U,
                      bms_skipped ? 1U : 0U, bms_persistence_preserved,
                      bms_persistence_restored);
            record("SERVER_STATS", detail);
#if defined(M33_PROFILE_SERVER) && !defined(M33_PROFILE_NATIVE)
            for (unsigned slot = 0U; slot < 2U; ++slot)
            {
                for (unsigned profile = 0U; profile < 5U; ++profile)
                {
                    snprintf(detail, sizeof(detail), "|slot=%u|profile=%u|sent=%u|no_ccc=%u", slot,
                             profile, sensor_sent[slot][profile], sensor_no_ccc[slot][profile]);
                    record("SEND_STATS", detail);
                }
            }
            snprintf(detail, sizeof(detail),
                     "|no_ccc_errors=%u|pending_errors=%u|dropped_events=%u", no_ccc_errors,
                     expected_error_events, static_cast<unsigned>(BLEDevice.droppedEvents()));
            record("ERROR_STATS", detail);
#endif
#if defined(M33_PROFILE_NATIVE)
            snprintf(detail, sizeof(detail),
                     "|object_writes=%u|single_link=1|cgms_session=%u|native_links=%u|native_"
                     "disconnects=%u|authenticated_links=%u|passkey_events=%u",
                     object_writes, glucose.sessionActive() ? 1U : 0U, native_links,
                     native_disconnects, authenticated_links, passkey_events);
            record("NATIVE_STATS", detail);
#endif
            cleanup_requested = true;
            stop_requested = true;
            done = true;
        }
        else if (!start(command) && !failed)
        {
            fail("|reason=invalid-start-command");
        }
    }
} // namespace
void setup()
{
    Serial.begin(115200);
}
void loop()
{
    while (Serial.available() > 0)
    {
        const int byte = Serial.read();
        if (byte == '\n')
        {
            command[command_length] = '\0';
            handleCommand();
            command_length = 0U;
        }
        else if (byte != '\r')
        {
            if (command_length + 1U >= sizeof(command))
            {
                command_length = 0U;
                fail("|reason=command-overflow");
            }
            else
            {
                command[command_length++] = static_cast<char>(byte);
            }
        }
    }
    BLEDevice.poll();
    BLESecurity.poll();
    if (watchdog_channel >= 0 && !cleanup_expired)
    {
        static_cast<void>(wdt_feed(watchdog, watchdog_channel));
    }
    if (cleanup_requested)
    {
        pollCleanup();
        delay(1);
        return;
    }
    if (started && millis() - began_at > 170000U)
    {
        stateRecord("FAIL", "deadline");
        pollCleanup();
        return;
    }
    if (!started || failed || done)
    {
        delay(1);
        return;
    }
    if (BLEDevice.droppedEvents() != 0U)
    {
        fail("|reason=dropped-gap-event");
        return;
    }
    if (att_reject.expired(millis()))
    {
        fail("|reason=att-gap-pair-missing");
        return;
    }
    if (att_reject.matched())
    {
        static_cast<void>(att_reject.finish());
        ++att_gap_rejects;
        ++rejected;
        if (index == 5U && phase == 1U)
        {
            phase = 2U;
            const uint8_t enable[] = {0U,
#if defined(M33_PROFILE_WATCHER)
                                      2U
#else
                                      1U
#endif
            };
            if (!BLEClient.write(peer, enable, sizeof(enable)))
            {
                fail("|reason=enable-submit");
            }
        }
        else if (index == 6U && phase == 1U)
        {
            const uint8_t unarmed[] = {3U, 0xa5U};
            phase = 2U;
            if (!att_reject.begin(peer, index, phase, -EIO, BT_ATT_ERR_AUTHORIZATION) ||
                !BLEClient.write(peer, unarmed, sizeof(unarmed)))
            {
                fail("|reason=bms-unarmed-submit");
            }
        }
        else if (index == 6U && phase == 2U)
        {
#if defined(M33_PROFILE_WATCHER)
            ++index;
            move_next = true;
#else
            phase = 3U;
            if (bms_persistence_restored_mode)
            {
                if (!bms_restored_candidate || !bms_restored_verified)
                {
                    fail("|reason=bms-client-restored-bond-unproven");
                    return;
                }
                bms_persistence_restored = 1U;
                record("BMS_RESTORED_READY",
                       "|negative_checks=2|client_restored=1|candidate=1|verified=1");
            }
            else if (!__atomic_load_n(&fresh_bond, __ATOMIC_ACQUIRE))
            {
                fail("|reason=bms-client-fresh-bond-unproven");
                return;
            }
            else
            {
                record("BMS_READY", "|negative_checks=2|client_fresh=1");
            }
#endif
        }
        else
        {
            fail("|reason=att-gap-phase-mismatch");
        }
    }
    if (bms_reject.expired(millis()))
    {
        fail("|reason=bms-gap-pair-missing");
        return;
    }
    if (bms_reject.matched())
    {
        static_cast<void>(bms_reject.finish());
        ++bms_teardown_errors;
        record("PROGRESS", "|reason=bms-write-teardown-pending|bms_teardown_errors=1");
    }
    if (bms_write_submitted && bms_client_cleanup == 0U && millis() - bms_requested_at > 5000U)
    {
        fail("|reason=bms-delete-proof-timeout");
        return;
    }
    alerts.poll();
#if defined(M33_PROFILE_NATIVE)
    if (native_cleanup_mode)
    {
        if (native_cleanup_requested && native_cleanup_disconnected && !done)
        {
            unsigned active = 0U;
            bt_conn_foreach(BT_CONN_TYPE_LE, countNativeConnections, &active);
            if (active == 0U && BLEConnection.count() == 0U &&
                !BLEConnection.connecting())
            {
                if (!native_cleanup_peer_valid ||
                    !BLESecurity.eraseBond(native_cleanup_address))
                {
                    fail("|reason=native-cleanup-scoped-delete");
                    return;
                }
                const bool unchanged = native_cleanup_fresh
                                           ? startupBondsUnchanged()
                                           : startupBondsWithout(native_cleanup_address);
                if (!unchanged)
                {
                    fail("|reason=native-cleanup-bonds-changed");
                    return;
                }
                done = true;
                char cleanup_detail[150];
                snprintf(cleanup_detail, sizeof(cleanup_detail),
                         "|removed=1|fresh=%u|restored=%u|existing_unchanged=1|"
                         "disconnected=1",
                         native_cleanup_fresh ? 1U : 0U,
                         native_cleanup_restored ? 1U : 0U);
                record("NATIVE_CLEANED", cleanup_detail);
                record("RESULT", cleanup_detail);
                record("END", "|status=pass");
            }
        }
    }
    else
    {
#if defined(M33_PROFILE_SERVER)
    if (!identity_probe_mode && !native_cleanup_mode && millis() - last_send >= 10000U)
    {
        last_send = millis();
        if (!glucose.add(123))
        {
            fail("|reason=cgms-record");
        }
    }
    ObjectEvent object_event;
    while (!identity_probe_mode && !native_cleanup_mode && object_server.readEvent(object_event))
    {
        if (object_event.type == ObjectEventType::received)
        {
            ++object_writes;
        }
    }
#else
    if (!identity_probe_mode && !native_cleanup_mode)
    {
        object_client.poll();
        if (object_begin)
        {
            object_begin = false;
            native_disconnect_expected = false;
            if (!object_client.begin(peer))
            {
                fail("|reason=object-begin");
            }
        }
        ObjectEvent object_event;
        while (object_client.readEvent(object_event))
        {
            onObject(object_event);
            if (failed)
            {
                break;
            }
        }
        if (!failed && cancel_on_partial && object_client.busy() &&
            object_client.bytesReceived() > 0U && object_client.bytesReceived() < sizeof(cancel_object))
        {
            cancel_on_partial = false;
            native_disconnect_expected = true;
            if (!object_client.cancel())
            {
                fail("|reason=partial-cancel-submit");
            }
            else
            {
                ++coc_cancels;
                record("PROGRESS", "|reason=partial-coc-cancel");
            }
        }
        if (!failed && restart_native_scan)
        {
            unsigned active = 0U;
            bt_conn_foreach(BT_CONN_TYPE_LE, countNativeConnections, &active);
            if (active == 0U && BLEConnection.count() == 0U && !BLEConnection.connecting())
            {
                restart_native_scan = false;
                if (!BLEScan.start(true))
                {
                    fail("|reason=native-rescan");
                }
                record("PROGRESS", "|reason=native-clean-rescan");
            }
        }
    }
#endif
    }
#elif defined(M33_PROFILE_SERVER)
    if (bms_requested && !bms_verified && bonds.acceptedCount() != 0U)
    {
        PeerAddress current_bonds[16] = {};
        const size_t copied = BLESecurity.copyBonds(current_bonds, 16U);
        bool requester_present = false;
        for (size_t bond = 0U; bond < copied; ++bond)
        {
            requester_present =
                requester_present || sameAddress(current_bonds[bond], fresh_bond_address);
        }
        if (bonds.acceptedCount() != 1U || requester_present ||
            BLESecurity.bondCount() + 1U != bonds_before_delete ||
            BLESecurity.bondState(peer) != watcher_bond_before || !BLEConnection.connected(peer) ||
            BLESecurity.currentLevel(peer) < SecurityLevel::encrypted)
        {
            fail("|reason=bms-scoped-delete-verification");
        }
        else
        {
            bms_verified = true;
            bms_persistence_restored = bms_persistence_restored_mode ? 1U : 0U;
            record("BMS_DELETED",
                   bms_persistence_restored_mode
                       ? "|accepted=1|fresh=0|restored=1|watcher_unchanged=1|requester_absent=1"
                       : "|accepted=1|fresh=1|restored=0|watcher_unchanged=1|requester_absent=1");
        }
    }
    if (millis() - last_send >= 200U)
    {
        last_send = millis();
        for (unsigned slot = 0U; slot < 2U; ++slot)
        {
            const auto connection =
                BLEConnection.handle(slot == 0U ? BLELinkRole::central : BLELinkRole::peripheral);
            if (!BLEConnection.connected(connection))
            {
                continue;
            }
            for (unsigned profile = 0U; profile < 5U; ++profile)
            {
                Packet packet;
                if (!expectedPacket(profile, packet) || !sensors[profile]->setValue(packet))
                {
                    fail("|reason=fixture");
                }
                if (!subscribed(slot, profile))
                {
                    if (sensor_no_ccc[slot][profile] == 0U)
                    {
                        ++expected_error_events;
                        if (sensors[profile]->send(connection) ||
                            BLEDevice.lastDriverError() != -ENOTCONN)
                        {
                            fail("|reason=no-ccc-negative");
                            return;
                        }
                        ++sensor_no_ccc[slot][profile];
                        BLEDevice.poll();
                    }
                    continue;
                }
                if (!sensors[profile]->send(connection))
                {
                    fail("|reason=subscribed-send");
                    return;
                }
                ++sensor_sent[slot][profile];
            }
            alert_slot = slot;
            alert_ccc = subscribed(slot, 5U) ? 1U : 0U;
            alert_sent = 0U;
            if (alert_ccc != 0U)
            {
                alert_sent = alerts.send(connection, Alert{1U, 2U, "profile-hil"}) ? 1U : 0U;
                if (slot == 0U && alert_sent == 0U)
                {
                    ++alert_denied;
                }
                else if (slot == 1U && alert_sent != 0U)
                {
                    ++email_deliveries;
                }
                else
                {
                    fail("|reason=alert-link-delivery");
                    return;
                }
            }
        }
    }
#else
    if (bms_client_cleanup_requested)
    {
        unsigned active = 0U;
        bt_conn_foreach(BT_CONN_TYPE_LE, countNativeConnections, &active);
        if (active == 0U && BLEConnection.count() == 0U && !BLEConnection.connecting() &&
            bms_disconnect_seen && !bms_reject.active() &&
            (bms_write_acknowledged || bms_teardown_errors == 1U))
        {
            bms_client_cleanup_requested = false;
            const bool owned = __atomic_load_n(&fresh_bond, __ATOMIC_ACQUIRE) ||
                               (bms_persistence_restored_mode && bms_restored_verified);
            if (!startup_bonds_valid || !owned ||
                !BLESecurity.eraseBond(fresh_bond_address))
            {
                fail("|reason=bms-client-scoped-cleanup");
                return;
            }
            const bool unchanged = bms_persistence_restored_mode
                                       ? startupBondsWithout(fresh_bond_address)
                                       : startupBondsUnchanged();
            if (!unchanged)
            {
                fail("|reason=bms-client-bonds-changed");
                return;
            }
            bms_client_cleanup = 1U;
            record("BMS_CLEANED",
                   bms_persistence_restored_mode
                       ? "|fresh=0|restored=1|server_absent=1|existing_unchanged=1|disconnected=1"
                       : "|fresh=1|restored=0|server_absent=1|existing_unchanged=1|disconnected=1");
            ++index;
            move_next = true;
        }
    }
    if (move_next)
    {
        move_next = false;
        nextProfile();
    }
#if defined(M33_PROFILE_WATCHER)
    if (index == 5U && phase == 3U && quiet_since != 0U && millis() - quiet_since >= 6000U)
    {
        stateRecord("PROGRESS", "quiet-unsubscribe-submit");
        quiet_since = 0U;
        if (!BLEClient.unsubscribe(peer))
        {
            fail("|reason=quiet-unsubscribe");
        }
    }
#endif
#endif
    delay(1);
}
