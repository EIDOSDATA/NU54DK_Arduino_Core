/** @file @brief 실제 onLink/onSecurity/onScan body로 제한된 비대칭 정리 전이를 비교합니다. */
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cerrno>
#include <string>
#include <vector>
#include <functional>
#include "ExpectedReject.h"

#define BT_HCI_ERR_CONN_FAIL_TO_ESTAB 0x3e
#define BT_HCI_ERR_REMOTE_USER_TERM_CONN 0x13
#define BT_HCI_ERR_LOCALHOST_TERM_CONN 0x16
#define BT_SECURITY_ERR_UNSPECIFIED 9
#define BT_SECURITY_ERR_AUTH_REQUIREMENT 4

namespace
{
    /** @brief 값마다 서로 다른 공개 handle generation을 모사하며 주소와 동일시하지 않습니다. */
    struct BLEConnectionHandle
    {
        unsigned value = 0U;
        bool valid() const
        {
            return value != 0U;
        }
    };
    bool operator==(BLEConnectionHandle left, BLEConnectionHandle right)
    {
        return left.value == right.value;
    }
    [[maybe_unused]] bool operator!=(BLEConnectionHandle left, BLEConnectionHandle right)
    {
        return !(left == right);
    }
    struct PeerAddress
    {
        uint8_t type = 0U;
        uint8_t value[6] = {};
    };
    struct BLEAddress
    {
        enum class Type : uint8_t
        {
            public_address,
            random_address,
        };
        PeerAddress bytes{};
        bool is_valid = true;
        bool valid() const
        {
            return is_valid;
        }
        Type type() const
        {
            return bytes.type == 0U ? Type::public_address : Type::random_address;
        }
        const uint8_t *data() const
        {
            return bytes.value;
        }
    };
    struct BLEScanResult
    {
        bool connectable = true;
        uint8_t payload[64] = {};
        size_t payload_length = 0U;
        BLEAddress address{};
    };
    enum class BLEEvent : uint8_t
    {
        connected = 7,
        disconnected = 8,
        error = 38,
        connection_recycled = 39,
    };
    enum class BLEError : uint8_t
    {
        none = 0,
        not_connected = 11,
    };
    enum class BLELinkRole : uint8_t
    {
        none,
        central,
        peripheral,
    };
    enum class SecurityLevel : uint8_t
    {
        none = 1,
        encrypted = 2,
        authenticated = 3,
    };
    enum class SecurityError : uint8_t
    {
        none = 0,
        busy = 6,
    };
    enum class SecurityEvent : uint8_t
    {
        pairing_requested = 0,
        bond_persistence_pending = 8,
        bond_restored_candidate = 9,
        bond_verified = 10,
        pairing_failed = 13,
        security_changed = 14,
        bond_removal_requested = 15,
        timeout = 17,
        error = 18,
    };
    struct SecurityEventRecord
    {
        SecurityEvent event = SecurityEvent::error;
        BLEConnectionHandle connection{};
        SecurityLevel level = SecurityLevel::none;
        PeerAddress peer{};
        uint8_t reason = 0U;
    };
    struct BLEEventInfo
    {
        BLEEvent event = BLEEvent::connected;
        BLEConnectionHandle connection{};
        BLELinkRole role = BLELinkRole::central;
        BLEError error = BLEError::none;
        int driver_error = 0;
        uint8_t reason = 0U;
    };

    /** @brief 원격 정리 guard가 읽는 시작 및 본문 전 상태의 외부 입력입니다. */
    [[maybe_unused]] bool started = true;
    [[maybe_unused]] unsigned count = 0U, measurements = 0U;
    uint32_t now_ms = 0U;
    [[maybe_unused]] bool failed = false, cleanup_requested = false, done = false;
    [[maybe_unused]] bool stop_requested = false;
    bool local_bond = true, erase_ok = true, disconnect_ok = true;
    bool erase_verification_ok = true;
    bool scan_running = true, scan_start_ok = true;
    bool connected_links[16] = {};
    unsigned connects = 0U, disconnects = 0U, security_requests = 0U, pairing_accepts = 0U;
    unsigned scan_starts = 0U, scan_stops = 0U, advertisements = 0U, bond_erases = 0U;
    std::vector<std::string> records;
    [[maybe_unused]] BLEConnectionHandle peer{}, fresh_bond_link{}, bms_request_peer{};
    PeerAddress startup_bonds[16] = {};
    bool startup_bonds_valid = true;
    [[maybe_unused]] size_t startup_bond_count = 1U, maximum_links = 0U;
    bool bms_persistence_fresh_mode = true, bms_persistence_restored_mode = false;
#if !defined(M33_PROFILE_WATCHER)
    PeerAddress fresh_bond_address{};
    bool fresh_bond = false, bms_restored_candidate = false, bms_restored_verified = false;
#endif
    [[maybe_unused]] bool hub_advertised = false, hub_security_started = false, move_next = false;
    [[maybe_unused]] bool bms_write_submitted = false, bms_write_acknowledged = false,
                          bms_disconnect_seen = false;
    [[maybe_unused]] unsigned bms_teardown_errors = 0U, expected_error_events = 0U,
                              no_ccc_errors = 0U;
    unsigned index = 0U, phase = 0U, alert_slot = 0U, alert_ccc = 0U, alert_sent = 0U;
    [[maybe_unused]] unsigned att_gap_rejects = 0U;
    [[maybe_unused]] ExpectedReject<BLEConnectionHandle> bms_reject, att_reject;
    [[maybe_unused]] uint8_t nonce_bytes[16] = {};
#include "stale-declarations.inc"
#if defined(M33_PROFILE_WATCHER)
    /** @brief 외부 queue 입력만 제공하고 판정은 추출한 실제 callback과 poll에 맡깁니다. */
    std::vector<std::function<void()>> gap_inputs, security_inputs;
    std::function<void()> erase_hook;
    std::vector<unsigned> drained_events;
    void onSecurity(const SecurityEventRecord &event, void *);
    void drainInputs(std::vector<std::function<void()>> &inputs)
    {
        while (!inputs.empty())
        {
            auto next = inputs.front();
            inputs.erase(inputs.begin());
            next();
        }
    }
#endif

    uint32_t millis()
    {
        return now_ms;
    }
    void record(const char *kind, const char *detail)
    {
        records.emplace_back(std::string(kind) + detail);
    }
    void fail(const char *reason);
    /** @brief 실패 판정은 실제 fail body에 맡기며 출력 장식만 Host에서 생략합니다. */
    [[maybe_unused]] void stateRecord(const char *kind, const char *reason)
    {
        if (std::strcmp(kind, "FAIL") == 0)
        {
            fail(reason);
        }
        else
        {
            record(kind, reason);
        }
    }
    PeerAddress address(unsigned value = 41U, uint8_t type = 0U)
    {
        PeerAddress result{};
        result.type = type;
        result.value[0] = static_cast<uint8_t>(value);
        return result;
    }
    bool startupContains(const PeerAddress &value)
    {
        const PeerAddress expected = address();
        return local_bond && value.type == expected.type &&
               std::memcmp(value.value, expected.value, 6U) == 0;
    }
    bool startupBondsWithout(const PeerAddress &)
    {
        return !local_bond && erase_verification_ok;
    }
    void snapshotBonds()
    {
        startup_bond_count = local_bond ? 1U : 0U;
        startup_bonds[0] = address();
    }
    struct SecurityBoundary
    {
        bool eraseBond(const PeerAddress &)
        {
            ++bond_erases;
            if (erase_ok)
            {
                local_bond = false;
#if defined(M33_PROFILE_WATCHER)
                security_inputs.emplace_back([]()
                {
                    SecurityEventRecord removed{};
                    removed.event = SecurityEvent::bond_removal_requested;
                    drained_events.push_back(115U);
                    onSecurity(removed, nullptr);
                });
                if (erase_hook)
                {
                    erase_hook();
                }
#endif
            }
            return erase_ok;
        }
        void poll()
        {
#if defined(M33_PROFILE_WATCHER)
            drainInputs(security_inputs);
#endif
        }
        bool acceptPairing(BLEConnectionHandle, bool)
        {
            ++pairing_accepts;
            return true;
        }
        bool requestSecurity(BLEConnectionHandle)
        {
            ++security_requests;
            return true;
        }
        SecurityError lastError() const
        {
            return SecurityError::none;
        }
        int lastDriverError() const
        {
            return 0;
        }
    } BLESecurity;
    struct ConnectionBoundary
    {
        bool connected(BLEConnectionHandle handle) const
        {
            return handle.value < 16U && connected_links[handle.value];
        }
        bool disconnect(BLEConnectionHandle)
        {
            ++disconnects;
            /** @note 반환 성공과 실제 GAP 종료 callback은 별도 입력입니다. */
            return disconnect_ok;
        }
        bool connect(const BLEAddress &, BLEConnectionHandle &handle)
        {
            ++connects;
            handle.value = connects;
            connected_links[handle.value] = true;
            return true;
        }
        size_t count() const
        {
            size_t result = 0U;
            for (bool live : connected_links)
            {
                result += live ? 1U : 0U;
            }
            return result;
        }
        BLELinkRole role(BLEConnectionHandle) const
        {
            return BLELinkRole::central;
        }
    } BLEConnection;
    struct ScanBoundary
    {
        bool start(bool active)
        {
            ++scan_starts;
            scan_running = active && scan_start_ok;
            return scan_running;
        }
        bool stop()
        {
            ++scan_stops;
            const bool previous = scan_running;
            scan_running = false;
            return previous;
        }
        bool running() const
        {
            return scan_running;
        }
    } BLEScan;
    struct DeviceBoundary
    {
        void poll()
        {
#if defined(M33_PROFILE_WATCHER)
            drainInputs(gap_inputs);
#endif
        }
        int lastDriverError() const
        {
            return 0;
        }
    } BLEDevice;
    struct ClientBoundary
    {
        unsigned lastAttError(BLEConnectionHandle) const
        {
            return 0U;
        }
    } BLEClient;
    bool advertise()
    {
        ++advertisements;
        return true;
    }

#include "stale-functions.inc"

    bool check(bool value, const char *name)
    {
        if (!value)
        {
            std::printf("EXPECTATION_FAILED:%s\n", name);
        }
        return value;
    }
#if !defined(M33_PROFILE_WATCHER)
    BLEScanResult frame(bool ready)
    {
        BLEScanResult result{};
        result.address.bytes = address();
        result.payload_length = 21U;
        result.payload[0] = 20U;
        result.payload[1] = 0xffU;
#if defined(M33_PROFILE_SERVER)
        result.payload[2] = 0x4eU;
#else
        result.payload[2] = 0x4dU;
#endif
        result.payload[3] = 0x05U;
        std::memcpy(result.payload + 4U, nonce_bytes, sizeof(nonce_bytes));
        result.payload[20] = ready ? 1U : 0U;
        return result;
    }
    void link(unsigned handle, BLEEvent event, uint8_t reason = 0U, bool update_state = true)
    {
        if (update_state)
        {
            connected_links[handle] = event == BLEEvent::connected;
        }
        BLEEventInfo value{};
        value.event = event;
        value.connection.value = handle;
        value.reason = reason;
        onLink(value, nullptr);
    }
    void security(unsigned handle, SecurityEvent event, uint8_t reason = 0U,
                  SecurityLevel level = SecurityLevel::none, PeerAddress remote = address())
    {
        SecurityEventRecord value{};
        value.event = event;
        value.connection.value = handle;
        value.peer = remote;
        value.reason = reason;
        value.level = level;
        onSecurity(value, nullptr);
    }
    bool prepareH1(uint8_t reason = BT_HCI_ERR_CONN_FAIL_TO_ESTAB)
    {
        snapshotBonds();
        onScan(frame(false), nullptr);
        link(1U, BLEEvent::connected);
        security(1U, SecurityEvent::bond_restored_candidate);
        if (!check(!failed && stale_recovery_count == 1U && disconnects == 1U,
                   "actual_H1_security_scoped_recovery"))
        {
            return false;
        }
        link(1U, BLEEvent::disconnected, reason);
        return check(!failed && !peer.valid() && stale_recovery_disconnected[0] &&
                         stale_recovery_count == 1U,
                     "actual_H1_owned_disconnect");
    }
    bool advanceScan()
    {
        const uint32_t began = stale_recovery_restart_at;
        const unsigned previous = scan_starts;
        now_ms = began + 749U;
        pollStaleRecoveryRestart();
        if (!check(scan_starts == previous, "750ms_delay_preserved"))
        {
            return false;
        }
        now_ms = began + 750U;
        pollStaleRecoveryRestart();
        return check(!failed && scan_starts == previous + 1U && scan_running,
                     "new_scan_epoch_started");
    }
    bool prepareH2()
    {
        if (!prepareH1() || !advanceScan())
        {
            return false;
        }
        onScan(frame(false), nullptr);
        link(2U, BLEEvent::connected);
        return check(!failed && peer.value == 2U && connects == 2U && security_requests == 2U,
                     "actual_H2_active_connected_requests_security");
    }
    bool finalConnection()
    {
        if (!advanceScan())
        {
            return false;
        }
        onScan(frame(false), nullptr);
        if (!check(connects == 2U && scan_running, "H3_rejects_ready0"))
        {
            return false;
        }
        auto foreign = frame(true);
        foreign.address.bytes.type = 1U;
        onScan(foreign, nullptr);
        foreign = frame(true);
        foreign.address.bytes.value[5] = 1U;
        onScan(foreign, nullptr);
        if (!check(connects == 2U, "H3_requires_exact_typed_peer"))
        {
            return false;
        }
        onScan(frame(true), nullptr);
        link(3U, BLEEvent::connected);
        return check(!failed && connects == 3U && security_requests == 3U &&
                         stale_recovery_count == 1U && bond_erases == 1U,
                     "H3_normal_connection_no_extra_primary_or_erase");
    }
    /** @brief 새 누락 사례에서만 실제 중앙 역할과 현재 연결 상태를 명시합니다. */
    void remoteLink(unsigned handle, BLEEvent event, uint8_t reason = 0U,
                    BLELinkRole role = BLELinkRole::central, bool update_state = true)
    {
        if (update_state)
        {
            connected_links[handle] = event == BLEEvent::connected;
        }
        BLEEventInfo value{};
        value.event = event;
        value.connection.value = handle;
        value.role = role;
        value.reason = reason;
        onLink(value, nullptr);
    }

    /** @brief local 후보 event 없이 실제 선택과 연결 callback만 시작합니다. */
    bool remoteBegin(bool report_connected = true, bool initial_ready = false,
                     bool queued_connected = false, uint8_t connected_reason = 0U)
    {
        snapshotBonds();
        onScan(frame(initial_ready), nullptr);
        if (report_connected)
        {
            if (queued_connected)
            {
                connected_links[1U] = false;
            }
            remoteLink(1U, BLEEvent::connected, connected_reason, BLELinkRole::central,
                       !queued_connected);
        }
        return check(!failed && connects == 1U && peer.value == 1U && stale_recovery_count == 0U &&
                         bond_erases == 0U && disconnects == 0U,
                     "remote_H1_has_no_local_candidate_prune_or_disconnect");
    }

    /** @brief 원형 순서의 반대편 정리만 있는 callback 입력과 제한된 후속을 비교합니다. */
    bool runRemote(const std::string &test)
    {
        local_bond = test == "remote_local_bond";
        if (test == "remote_restored")
        {
            bms_persistence_fresh_mode = false;
            bms_persistence_restored_mode = true;
        }
        if (test == "remote_started_false")
        {
            started = false;
        }
        if (test == "remote_preprofile")
        {
            count = 1U;
        }
        if (!remoteBegin(test != "remote_no_connected_event", test == "remote_initial_ready1",
                         test == "remote_queued_connected",
                         test == "remote_connected_error" ? 1U : 0U))
        {
            return false;
        }
        if (test == "remote_first_l2")
        {
            local_bond = true;
            security(1U, SecurityEvent::security_changed, 0U, SecurityLevel::encrypted);
            if (!check(!failed, "remote_first_L2_original_callback_completed"))
            {
                return false;
            }
        }
        const uint8_t reason = test == "remote_hci62" ? BT_HCI_ERR_CONN_FAIL_TO_ESTAB
                                                      : BT_HCI_ERR_REMOTE_USER_TERM_CONN;
        const BLELinkRole role =
            test == "remote_wrong_role" ? BLELinkRole::peripheral : BLELinkRole::central;
        remoteLink(1U, BLEEvent::disconnected, reason, role);
        const bool original_failure_required =
            test == "remote_local_bond" || test == "remote_restored" ||
            test == "remote_started_false" || test == "remote_preprofile" ||
            test == "remote_first_l2" || test == "remote_hci62" || test == "remote_wrong_role" ||
            test == "remote_connected_error" || test == "remote_no_connected_event" ||
            test == "remote_initial_ready1";
        if (original_failure_required)
        {
            return check(failed && cleanup_requested && connects == 1U && scan_starts == 0U &&
                             bond_erases == 0U && disconnects == 0U,
                         "remote_guard_keeps_original_failure_without_retry");
        }
        if (!check(!failed && !cleanup_requested && !peer.valid() && connects == 1U &&
                       scan_starts == 0U && bond_erases == 0U && disconnects == 0U,
                   "remote_only_H1_park_before_ready1"))
        {
            return false;
        }
        if (test == "remote_stop_delay")
        {
            cleanup_requested = true;
            now_ms = 1000U;
            pollStaleRecoveryRestart();
            onScan(frame(true), nullptr);
            return check(!failed && scan_starts == 0U && connects == 1U && bond_erases == 0U &&
                             disconnects == 0U,
                         "remote_STOP_cancels_delay_without_operations");
        }
        if (test == "remote_retired_conflict" || test == "remote_retired_wrong_peer" ||
            test == "remote_retired_timeout" || test == "remote_retired_gap_conflict" ||
            test == "remote_retired_role_conflict" || test == "remote_retired_error_conflict")
        {
            if (test == "remote_retired_conflict")
            {
                security(1U, SecurityEvent::security_changed, 0U, SecurityLevel::encrypted);
            }
            else if (test == "remote_retired_wrong_peer")
            {
                security(1U, SecurityEvent::error, BT_SECURITY_ERR_AUTH_REQUIREMENT,
                         SecurityLevel::none, address(42U));
            }
            else if (test == "remote_retired_timeout")
            {
                security(1U, SecurityEvent::timeout, BT_SECURITY_ERR_UNSPECIFIED);
            }
            else if (test == "remote_retired_role_conflict")
            {
                remoteLink(1U, BLEEvent::disconnected, BT_HCI_ERR_REMOTE_USER_TERM_CONN,
                           BLELinkRole::peripheral);
            }
            else if (test == "remote_retired_error_conflict")
            {
                BLEEventInfo conflicting{};
                conflicting.event = BLEEvent::connected;
                conflicting.connection.value = 1U;
                conflicting.role = BLELinkRole::central;
                conflicting.error = BLEError::not_connected;
                conflicting.driver_error = -ENOTCONN;
                onLink(conflicting, nullptr);
            }
            else
            {
                remoteLink(1U, BLEEvent::disconnected, BT_HCI_ERR_LOCALHOST_TERM_CONN);
            }
            return check(failed && connects == 1U && scan_starts == 0U && bond_erases == 0U &&
                             disconnects == 0U,
                         "remote_retired_conflict_stops_without_scan");
        }
        if (test == "remote_retired_duplicates")
        {
            remoteLink(1U, BLEEvent::disconnected, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
            security(1U, SecurityEvent::error, BT_SECURITY_ERR_AUTH_REQUIREMENT);
            security(1U, SecurityEvent::pairing_failed, BT_SECURITY_ERR_AUTH_REQUIREMENT);
            if (!check(!failed && connects == 1U && disconnects == 0U,
                       "remote_retired_expected_events_no_new_ownership"))
            {
                return false;
            }
        }
        if (!advanceScan())
        {
            return false;
        }
        if (test == "remote_ready0_no_reconnect" || test == "remote_stop_wait")
        {
            onScan(frame(false), nullptr);
            now_ms += 20000U;
            pollStaleRecoveryRestart();
            onScan(frame(false), nullptr);
            if (!check(!failed && connects == 1U && scan_starts == 1U,
                       "remote_ready0_never_authorizes_reconnect"))
            {
                return false;
            }
            cleanup_requested = true;
            pollStaleRecoveryRestart();
            onScan(frame(true), nullptr);
            return check(!failed && connects == 1U && scan_starts == 1U && bond_erases == 0U &&
                             disconnects == 0U,
                         "remote_STOP_cancels_wait_without_operations");
        }
        if (test == "remote_binding_guards")
        {
            onScan(frame(false), nullptr);
            auto bad = frame(true);
            bad.payload[4] ^= 1U;
            onScan(bad, nullptr);
            bad = frame(true);
            bad.payload[2] ^= 1U;
            onScan(bad, nullptr);
            bad = frame(true);
            bad.address.bytes.type = 1U;
            onScan(bad, nullptr);
            bad = frame(true);
            bad.address.bytes.value[5] = 1U;
            onScan(bad, nullptr);
            scan_running = false;
            onScan(frame(true), nullptr);
            scan_running = true;
            const uint32_t correct_epoch = stale_scan_epoch;
            ++stale_scan_epoch;
            onScan(frame(true), nullptr);
            stale_scan_epoch = correct_epoch;
            if (!check(!failed && connects == 1U && scan_starts == 1U && scan_stops == 1U,
                       "remote_ready1_requires_nonce_company_typed_peer_scan_epoch"))
            {
                return false;
            }
        }
        onScan(frame(true), nullptr);
        remoteLink(2U, BLEEvent::connected);
        if (!check(!failed && connects == 2U && peer.value == 2U && security_requests == 2U &&
                       bond_erases == 0U && disconnects == 0U && stale_recovery_count == 0U,
                   "remote_ready1_second_link_has_no_local_erase_or_primary_slot"))
        {
            return false;
        }
        if (test == "remote_second_disconnect")
        {
            remoteLink(2U, BLEEvent::disconnected, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        }
        else if (test == "remote_second_security_error")
        {
            security(2U, SecurityEvent::error, BT_SECURITY_ERR_AUTH_REQUIREMENT);
        }
        else if (test == "remote_second_wrong_peer")
        {
            security(2U, SecurityEvent::pairing_requested, 0U, SecurityLevel::none, address(42U));
        }
        else
        {
            local_bond = true;
            security(2U, SecurityEvent::security_changed, 0U, SecurityLevel::encrypted);
            if (!check(!failed, "remote_second_L2_is_original_success_path"))
            {
                return false;
            }
            if (test == "remote_second_l2_disconnect")
            {
                remoteLink(2U, BLEEvent::disconnected, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
            }
            else
            {
                return check(connects == 2U && scan_starts == 1U && bond_erases == 0U &&
                                 disconnects == 0U && stale_recovery_count == 0U,
                             "remote_ready1_success_is_one_bounded_followup_only");
            }
        }
        const unsigned before_connects = connects;
        now_ms += 2000U;
        pollStaleRecoveryRestart();
        onScan(frame(true), nullptr);
        return check(failed && cleanup_requested && connects == before_connects && connects == 2U &&
                         scan_starts == 1U && bond_erases == 0U && disconnects == 0U,
                     "remote_second_failure_has_no_third_connection");
    }
    bool run(const std::string &test)
    {
        if (test.rfind("remote_", 0U) == 0U)
        {
            return runRemote(test);
        }
        PeerAddress copied{};
        BLEAddress typed{};
        typed.bytes = address(41U, 1U);
        if (!check(copyPeerAddress(typed, copied) && sameAddress(copied, typed.bytes),
                   "actual_typed_copy_retains_type_and_six_bytes"))
        {
            return false;
        }
        if (test == "normal19" || test == "normal22")
        {
            if (!prepareH1(test == "normal19" ? 0x13U : 0x16U) || !advanceScan())
            {
                return false;
            }
            onScan(frame(false), nullptr);
            if (!check(connects == 1U, "normal_disconnect_requires_ready1"))
            {
                return false;
            }
            onScan(frame(true), nullptr);
            return check(!failed && connects == 2U, "normal_ready1_original_path");
        }
        if (test == "pending_queue" || test == "cleanup" || test == "foreign_scan" ||
            test == "no_local_prune" || test == "ready1_direct" || test == "scan_not_running")
        {
            if (test == "no_local_prune")
            {
                local_bond = false;
            }
            if (!prepareH1())
            {
                return false;
            }
            if (test == "cleanup")
            {
                cleanup_requested = true;
                now_ms = 1000U;
                pollStaleRecoveryRestart();
                onScan(frame(true), nullptr);
                return check(scan_starts == 0U && connects == 1U && !failed,
                             "STOP_cancels_without_extra_operations");
            }
            if (test == "pending_queue")
            {
                now_ms = 100U;
                onScan(frame(false), nullptr);
                if (!check(!failed && connects == 1U && scan_stops == 1U,
                           "old_queued_frame_during_delay_ignored"))
                {
                    return false;
                }
            }
            if (!advanceScan())
            {
                return false;
            }
            if (test == "no_local_prune")
            {
                onScan(frame(false), nullptr);
                return check(!failed && connects == 1U && bond_erases == 0U,
                             "no_local_delete_no_ready0_exception");
            }
            if (test == "scan_not_running")
            {
                scan_running = false;
                onScan(frame(false), nullptr);
                return check(!failed && connects == 1U && scan_stops == 1U,
                             "scan_running_required_before_budget_claim");
            }
            if (test == "foreign_scan")
            {
                auto other = frame(false);
                other.payload[4] ^= 1U;
                onScan(other, nullptr);
                other = frame(false);
                other.payload[2] ^= 1U;
                onScan(other, nullptr);
                other = frame(false);
                other.payload[20] = 2U;
                onScan(other, nullptr);
                other = frame(false);
                other.connectable = false;
                onScan(other, nullptr);
                other = frame(false);
                other.address.bytes.type = 1U;
                onScan(other, nullptr);
                other = frame(false);
                other.address.bytes.value[5] = 1U;
                onScan(other, nullptr);
                return check(!failed && connects == 1U && scan_stops == 1U,
                             "nonce_company_marker_connectable_typed_peer_guards");
            }
            onScan(frame(test == "ready1_direct"), nullptr);
            link(2U, BLEEvent::connected);
            if (test == "ready1_direct")
            {
                security(2U, SecurityEvent::error, BT_SECURITY_ERR_UNSPECIFIED);
                return check(failed && disconnects == 1U && scan_starts == 1U,
                             "ready1_direct_has_no_H2_permission");
            }
            return check(!failed && connects == 2U, "delayed_H2_only_once");
        }
        if (!prepareH2())
        {
            return false;
        }
        if (test == "active_pairing")
        {
            security(2U, SecurityEvent::pairing_requested);
            return check(!failed && pairing_accepts == 1U && disconnects == 1U,
                         "ACTIVE_pairing_original_callback_once");
        }
        if (test == "timeout" || test == "security_other" || test == "wrong_peer" ||
            test == "wrong_generation" || test == "H2_62" || test == "unsolicited22" ||
            test == "disconnect_rejected")
        {
            if (test == "timeout")
            {
                security(2U, SecurityEvent::timeout, BT_SECURITY_ERR_UNSPECIFIED);
            }
            else if (test == "security_other")
            {
                security(2U, SecurityEvent::error, 2U);
            }
            else if (test == "wrong_peer")
            {
                security(2U, SecurityEvent::pairing_requested, 0U, SecurityLevel::none,
                         address(42U));
            }
            else if (test == "wrong_generation")
            {
                security(4U, SecurityEvent::error, BT_SECURITY_ERR_UNSPECIFIED);
            }
            else if (test == "disconnect_rejected")
            {
                disconnect_ok = false;
                security(2U, SecurityEvent::error, BT_SECURITY_ERR_UNSPECIFIED);
            }
            else
            {
                link(2U, BLEEvent::disconnected,
                     test == "H2_62" ? BT_HCI_ERR_CONN_FAIL_TO_ESTAB
                                     : BT_HCI_ERR_LOCALHOST_TERM_CONN);
            }
            return check(failed && scan_starts == 1U && connects == 2U && pairing_accepts == 0U,
                         "unsupported_H2_event_fails_without_new_scan");
        }
        if (test == "L2_early_disconnect" || test == "L2_BMS_disconnect" || test == "L2_error")
        {
            local_bond = true;
            security(2U, SecurityEvent::security_changed, 0U, SecurityLevel::encrypted);
            if (!check(!failed, "L2_original_callback_runs"))
            {
                return false;
            }
            if (test == "L2_BMS_disconnect")
            {
#if defined(M33_PROFILE_SERVER)
                /** @note server의 BMS 상대는 peripheral이며 hub H2와 별개인 원형 범위입니다. */
                connected_links[4] = true;
                link(4U, BLEEvent::disconnected, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
                return check(!failed && peer.value == 2U,
                             "server_other_BMS_link_original_handling");
#else
                bms_write_submitted = true;
                bms_request_peer = peer;
                index = 6U;
                phase = 4U;
                link(2U, BLEEvent::disconnected, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
                return check(!failed && bms_disconnect_seen && scan_starts == 1U,
                             "L2_original_expected_BMS_disconnect_preserved");
#endif
            }
            if (test == "L2_error")
            {
                security(2U, SecurityEvent::error, BT_SECURITY_ERR_UNSPECIFIED);
            }
            else
            {
                link(2U, BLEEvent::disconnected, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
            }
            return check(failed && scan_starts == 1U && disconnects == 1U,
                         "L2_revokes_exception_original_failure_preserved");
        }
        const bool disconnect_first = test == "disconnect_first";
        if (!disconnect_first)
        {
            security(2U,
                     test == "pairing_first" ? SecurityEvent::pairing_failed : SecurityEvent::error,
                     BT_SECURITY_ERR_UNSPECIFIED);
            if (!check(!failed && disconnects == 2U, "second_error_does_not_fail_original_caller"))
            {
                return false;
            }
            if (test == "retiring_pairing")
            {
                security(2U, SecurityEvent::pairing_requested);
                return check(failed && pairing_accepts == 0U && disconnects == 2U,
                             "RETIRING_pairing_rejected_before_security_side_effect");
            }
            if (test == "cross_error" || test == "retiring_connected" || test == "pairing_first")
            {
                security(2U, SecurityEvent::pairing_failed, BT_SECURITY_ERR_UNSPECIFIED);
                security(2U, SecurityEvent::error, BT_SECURITY_ERR_UNSPECIFIED);
                link(2U, BLEEvent::connected);
                if (!check(!failed && disconnects == 2U && security_requests == 2U,
                           "RETIRING_duplicate_error_and_connected_no_new_requests"))
                {
                    return false;
                }
            }
        }
        link(2U, BLEEvent::disconnected,
             test == "error_local22" ? BT_HCI_ERR_LOCALHOST_TERM_CONN
                                     : BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        if (!check(!failed && !peer.valid() && stale_recovery_count == 1U,
                   "actual_H2_disconnect_schedules_ready1"))
        {
            return false;
        }
        if (test == "late_L2" || test == "late_timeout" || test == "retired_pairing")
        {
            security(2U,
                     test == "late_L2"        ? SecurityEvent::security_changed
                     : test == "late_timeout" ? SecurityEvent::timeout
                                              : SecurityEvent::pairing_requested,
                     BT_SECURITY_ERR_UNSPECIFIED,
                     test == "late_L2" ? SecurityLevel::encrypted : SecurityLevel::none);
            return check(failed && pairing_accepts == 0U && connects == 2U,
                         "retired_conflict_rejected_before_side_effect");
        }
        if (test == "late_events")
        {
            security(2U, SecurityEvent::pairing_failed, BT_SECURITY_ERR_UNSPECIFIED);
            security(2U, SecurityEvent::error, BT_SECURITY_ERR_UNSPECIFIED);
            link(2U, BLEEvent::disconnected, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
            link(2U, BLEEvent::connected, 0U, false);
            link(1U, BLEEvent::connected, 0U, false);
            if (!check(!failed && disconnects == 2U && security_requests == 2U,
                       "owned_late_events_do_not_restart_or_authenticate"))
            {
                return false;
            }
        }
        if (!finalConnection())
        {
            return false;
        }
        if (test == "H3_error" || test == "H3_62")
        {
            if (test == "H3_error")
            {
                security(3U, SecurityEvent::error, BT_SECURITY_ERR_UNSPECIFIED);
            }
            else
            {
                link(3U, BLEEvent::disconnected, BT_HCI_ERR_CONN_FAIL_TO_ESTAB);
            }
            now_ms += 5000U;
            pollStaleRecoveryRestart();
            onScan(frame(true), nullptr);
            return check(failed && connects == 3U && scan_starts == 2U &&
                             stale_recovery_count == 1U,
                         "H3_failure_has_no_H4_or_primary_retry");
        }
        local_bond = true;
        security(3U, SecurityEvent::security_changed, 0U, SecurityLevel::encrypted);
        if (test == "primary_second_peer")
        {
            connected_links[4] = true;
            security(4U, SecurityEvent::error, BT_SECURITY_ERR_UNSPECIFIED, SecurityLevel::none,
                     address(42U));
            return check(!failed && stale_recovery_count == 2U &&
                             stale_recovery_links[0].value == 1U &&
                             stale_recovery_links[1].value == 4U && bond_erases == 1U,
                         "second_primary_peer_capacity_is_not_consumed_by_H2");
        }
        return check(!failed && connects == 3U && bond_erases == 1U && stale_recovery_count == 1U &&
                         stale_recovery_links[0].value == 1U && stale_recovery_disconnected[0],
                     "final_original_L2_and_H1_history_preserved");
    }
#else
    /** @brief RAM에서 관측한 GAP 역할과 별도 security queue 입력을 그대로 전달합니다. */
    void watcherLink(unsigned handle, BLEEvent event, uint8_t reason = 0U,
                     BLELinkRole role = BLELinkRole::peripheral,
                     BLEError error = BLEError::none, int driver_error = 0)
    {
        BLEEventInfo value{};
        value.connection.value = handle;
        value.event = event;
        value.role = role;
        value.reason = reason;
        value.error = error;
        value.driver_error = driver_error;
        if (handle < 16U && (event == BLEEvent::connected || event == BLEEvent::disconnected))
        {
            connected_links[handle] = event == BLEEvent::connected;
        }
        drained_events.push_back(static_cast<unsigned>(event));
        onLink(value, nullptr);
    }
    void watcherSecurity(SecurityEvent event = SecurityEvent::bond_restored_candidate,
                         unsigned handle = 1U, PeerAddress remote = address(),
                         SecurityLevel level = SecurityLevel::none, uint8_t reason = 0U)
    {
        SecurityEventRecord value{};
        value.event = event;
        value.connection.value = handle;
        value.peer = remote;
        value.level = level;
        value.reason = reason;
        drained_events.push_back(100U + static_cast<unsigned>(event));
        onSecurity(value, nullptr);
    }
    bool watcherFailed(const char *expected, unsigned erases = 0U)
    {
        unsigned failures = 0U;
        bool first_exact = false;
        for (const auto &entry : records)
        {
            if (entry.rfind("FAIL", 0U) == 0U)
            {
                first_exact =
                    failures == 0U ? entry == std::string("FAIL") + expected : first_exact;
                ++failures;
            }
        }
        now_ms += 1000U;
        pollStaleRecoveryRestart();
        return check(failed && cleanup_requested && first_exact && failures == 1U &&
                         !watcher_disconnect.pending && !watcher_disconnect.poll_active &&
                         bond_erases == erases && connects == 0U && disconnects == 0U &&
                         security_requests == 0U && pairing_accepts == 0U && advertisements == 0U &&
                         stale_recovery_restart == StaleRecoveryRestart::none,
                     "watcher_first_failure_exact_no_retry_or_security_side_effects");
    }
    bool run(const std::string &test)
    {
        snapshotBonds();
        const char *const pending_detail =
            "|reason=early-disconnect|link_role=2|hci_reason=19|same_peer=1|event_handle_valid=1";
        const bool candidate_before = test == "candidate_before_disconnect" ||
                                      test == "candidate_before_disconnect_late_errors";
        if (candidate_before || test == "post_l2")
        {
            gap_inputs.emplace_back([]()
            {
                watcherLink(1U, BLEEvent::connected);
            });
            security_inputs.emplace_back([&test]()
            {
                if (test == "post_l2")
                {
                    watcherSecurity(SecurityEvent::security_changed, 1U, address(),
                                    SecurityLevel::encrypted);
                }
                else
                {
                    watcherSecurity();
                }
            });
            pollProfileEvents();
            if (!check(!failed && (test == "post_l2" ? move_next : bond_erases == 1U),
                       "actual_security_callback_precedes_next_poll_disconnect"))
            {
                return false;
            }
        }
        else
        {
            gap_inputs.emplace_back([]()
            {
                watcherLink(1U, BLEEvent::connected);
            });
        }
        if (test == "no_local_bond")
        {
            local_bond = false;
        }
        if (test == "erase_rejected")
        {
            erase_ok = false;
        }
        if (test == "erase_verification_failed")
        {
            erase_verification_ok = false;
        }
        if (test == "existing_address_slot" || test == "capacity_exhausted" ||
            test == "existing_address_live_slot" || test == "existing_consumed_handle")
        {
            stale_recovery_count = test == "capacity_exhausted" ? stale_recovery_capacity : 1U;
            stale_recovery_links[0].value = test == "existing_consumed_handle" ? 1U : 4U;
            stale_recovery_addresses[0] = address();
            stale_recovery_local_pruned[0] = test != "existing_consumed_handle";
            stale_recovery_disconnected[0] = true;
            connected_links[4] = test == "existing_address_live_slot";
            if (test == "existing_consumed_handle")
            {
                /** @note 이미 격리한 connected는 peer를 갱신하지 않으므로 현재 peer를 고정합니다. */
                peer.value = 1U;
            }
        }
        if (test == "stop_before_poll")
        {
            stop_requested = true;
            cleanup_requested = true;
            done = true;
        }
        if (test == "already_failed")
        {
            fail("|reason=prior-failure");
        }
        if (test == "restored")
        {
            bms_persistence_fresh_mode = false;
            bms_persistence_restored_mode = true;
        }
        if (test == "not_started")
        {
            started = false;
        }
        if (test == "invalid_startup")
        {
            startup_bonds_valid = false;
        }
        if (test == "profile_started")
        {
            index = 1U;
        }
        if (test == "reentrant_during_erase")
        {
            erase_hook = []()
            {
                pollProfileEvents();
            };
        }
        gap_inputs.emplace_back([&test]()
        {
            watcherLink(1U, BLEEvent::disconnected,
                        test == "reason62" ? 62U : test == "reason22" ? 22U : 19U,
                        test == "wrong_link_role" ? BLELinkRole::central : BLELinkRole::peripheral,
                        test == "disconnect_error" ? BLEError::not_connected : BLEError::none,
                        test == "disconnect_driver_error" ? -EIO : 0);
        });
        gap_inputs.emplace_back([&test]()
        {
            watcherLink(test == "recycled_conflict" ? 1U : 0U,
                        BLEEvent::connection_recycled,
                        test == "recycled_wrong_reason" ? 19U : 0U,
                        test == "recycled_wrong_role" ? BLELinkRole::peripheral : BLELinkRole::none,
                        test == "recycled_wrong_error" ? BLEError::not_connected : BLEError::none,
                        test == "recycled_wrong_driver" ? -EIO : 0);
            if (test == "duplicate_disconnect" || test == "foreign_disconnect")
            {
                watcherLink(test == "foreign_disconnect" ? 2U : 1U, BLEEvent::disconnected, 19U);
            }
            else if (test == "foreign_connected")
            {
                watcherLink(2U, BLEEvent::connected);
            }
            else if (test == "gap_error")
            {
                watcherLink(1U, BLEEvent::error, 0U, BLELinkRole::none,
                            BLEError::not_connected, -EIO);
            }
            else if (test == "reentrant_poll")
            {
                pollProfileEvents();
            }
            else if (test == "other_failure")
            {
                fail("|reason=later-failure");
            }
            else if (test == "stop_pending")
            {
                finishWatcherDisconnect();
                stop_requested = true;
                cleanup_requested = true;
                done = true;
            }
            else if (test == "cleanup_pending")
            {
                cleanup_requested = true;
            }
            else if (test == "done_pending")
            {
                done = true;
            }
        });
        if (test == "pairing_before_candidate" || test == "error_before_candidate" ||
            test == "timeout_before_candidate" || test == "l2_before_candidate" ||
            test == "removal_before_candidate")
        {
            security_inputs.emplace_back([&test]()
            {
                const SecurityEvent event =
                    test == "pairing_before_candidate" ? SecurityEvent::pairing_requested :
                    test == "error_before_candidate" ? SecurityEvent::error :
                    test == "timeout_before_candidate" ? SecurityEvent::timeout :
                    test == "l2_before_candidate" ? SecurityEvent::security_changed :
                    SecurityEvent::bond_removal_requested;
                watcherSecurity(event, 1U, address(),
                                test == "l2_before_candidate" ? SecurityLevel::encrypted
                                                              : SecurityLevel::none);
            });
        }
        if (test != "candidate_absent" && test != "candidate_next_poll" &&
            !candidate_before)
        {
            security_inputs.emplace_back([&test]()
            {
                watcherSecurity(SecurityEvent::bond_restored_candidate,
                                test == "wrong_candidate_handle" ? 2U : 1U,
                                address(test == "wrong_candidate_address" ? 42U : 41U,
                                        test == "wrong_candidate_type" ? 1U : 0U),
                                test == "candidate_wrong_level" ? SecurityLevel::encrypted
                                                                : SecurityLevel::none,
                                test == "candidate_wrong_reason" ? 1U : 0U);
            });
        }
        if (test == "duplicate_candidate")
        {
            security_inputs.emplace_back([]()
            {
                watcherSecurity();
            });
        }
        if (test == "delayed_candidate_late_errors" ||
            test == "candidate_before_disconnect_late_errors")
        {
            security_inputs.emplace_back([]()
            {
                watcherSecurity();
                watcherSecurity(SecurityEvent::error, 1U, address(), SecurityLevel::none, 9U);
                watcherSecurity(SecurityEvent::timeout);
                watcherSecurity(SecurityEvent::pairing_failed);
            });
        }
        if (test == "outside_poll")
        {
            BLEDevice.poll();
            BLESecurity.poll();
        }
        else
        {
            pollProfileEvents();
        }
        if (test == "candidate_next_poll")
        {
            if (!watcherFailed(pending_detail))
            {
                return false;
            }
            security_inputs.emplace_back([]()
            {
                watcherSecurity();
            });
            pollProfileEvents();
        }
        if (test == "stop_before_poll")
        {
            pollStaleRecoveryRestart();
            return check(!failed && stop_requested && cleanup_requested && done &&
                             !watcher_disconnect.pending && !watcher_disconnect.poll_active &&
                             bond_erases == 0U && advertisements == 0U && pairing_accepts == 0U,
                         "STOP_before_poll_preserves_original_cleanup_without_arming");
        }
        if (test == "already_failed")
        {
            return watcherFailed("|reason=prior-failure");
        }
        if (test == "delayed_candidate" || candidate_before ||
            test == "duplicate_candidate" || test == "resolved_stop" ||
            test == "delayed_candidate_late_errors")
        {
            if (!check(!failed && !cleanup_requested && !watcher_disconnect.pending &&
                           !watcher_disconnect.poll_active && !peer.valid() &&
                           stale_recovery_count == 1U && stale_recovery_links[0].value == 1U &&
                           stale_recovery_local_pruned[0] && stale_recovery_disconnected[0] &&
                           bond_erases == 1U && !local_bond && connects == 0U &&
                           security_requests == 0U && pairing_accepts == 0U &&
                           advertisements == 0U &&
                           disconnects == (candidate_before ? 1U : 0U) &&
                           stale_recovery_restart == StaleRecoveryRestart::watcher_advertise,
                       "exact_new_candidate_prune_consumes_existing_watcher_restart_only"))
            {
                return false;
            }
            if (test == "delayed_candidate")
            {
                if (!check(drained_events == std::vector<unsigned>{7U, 8U, 39U, 109U, 115U},
                           "GAP_drained_then_candidate_and_own_removal_without_failure"))
                {
                    return false;
                }
            }
            now_ms = stale_recovery_restart_at + 249U;
            pollStaleRecoveryRestart();
            if (!check(advertisements == 0U, "existing_advertiser_250ms_delay_unchanged"))
            {
                return false;
            }
            if (test == "resolved_stop")
            {
                stop_requested = true;
                cleanup_requested = true;
                done = true;
            }
            ++now_ms;
            pollStaleRecoveryRestart();
            pollStaleRecoveryRestart();
            return check(!failed && advertisements == (test == "resolved_stop" ? 0U : 1U) &&
                             stale_recovery_restart == StaleRecoveryRestart::none,
                         "existing_restart_once_or_STOP_cancels");
        }
        const bool immediate = test == "restored" || test == "not_started" ||
            test == "invalid_startup" || test == "profile_started" || test == "post_l2" ||
            test == "wrong_link_role" || test == "disconnect_driver_error" ||
            test == "disconnect_error" || test == "reason62" || test == "reason22" ||
            test == "outside_poll" || test == "existing_consumed_handle";
        const unsigned erases = test == "erase_rejected" || test == "erase_verification_failed" ||
            test == "reentrant_during_erase" ? 1U : 0U;
        return watcherFailed(immediate ? "|reason=early-disconnect" : pending_detail, erases);
    }
#endif
} // namespace

int main(int argc, char **argv)
{
    if (argc != 2)
    {
        return 2;
    }
    const bool ok = run(argv[1]);
    std::printf("HOST_ONLY:pass=%u:connects=%u:disconnect_requests=%u:primary_count=%u\n",
                ok ? 1U : 0U, connects, disconnects, static_cast<unsigned>(stale_recovery_count));
    if (std::strncmp(argv[1], "remote_", 7U) == 0)
    {
        for (const auto &entry : records)
        {
            if (entry.rfind("FAIL", 0U) == 0U)
            {
                std::printf("OBSERVED_ORIGINAL_OR_CANDIDATE_FAILURE:%s\n", entry.c_str());
            }
        }
    }
    return ok ? 0 : 1;
}
