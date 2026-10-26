/** @file @brief 실제 onLink/onSecurity/onScan body로 제한된 비대칭 정리 전이를 비교합니다. */
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cerrno>
#include <string>
#include <vector>
#include "ExpectedReject.h"

#define BT_HCI_ERR_CONN_FAIL_TO_ESTAB 0x3e
#define BT_HCI_ERR_REMOTE_USER_TERM_CONN 0x13
#define BT_HCI_ERR_LOCALHOST_TERM_CONN 0x16
#define BT_SECURITY_ERR_UNSPECIFIED 9

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
        error = 9,
    };
    enum class BLEError : uint8_t
    {
        none,
        not_connected,
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
        none,
        busy,
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

    uint32_t now_ms = 0U;
    [[maybe_unused]] bool failed = false, cleanup_requested = false, done = false;
    bool local_bond = true, erase_ok = true, disconnect_ok = true;
    bool scan_running = true, scan_start_ok = true;
    bool connected_links[16] = {};
    unsigned connects = 0U, disconnects = 0U, security_requests = 0U, pairing_accepts = 0U;
    unsigned scan_starts = 0U, scan_stops = 0U, advertisements = 0U, bond_erases = 0U;
    std::vector<std::string> records;
    [[maybe_unused]] BLEConnectionHandle peer{}, fresh_bond_link{}, bms_request_peer{};
    PeerAddress startup_bonds[16] = {}, fresh_bond_address{};
    bool startup_bonds_valid = true, fresh_bond = false;
    [[maybe_unused]] size_t startup_bond_count = 1U, maximum_links = 0U;
    bool bms_persistence_fresh_mode = true, bms_persistence_restored_mode = false;
    bool bms_restored_candidate = false, bms_restored_verified = false;
    [[maybe_unused]] bool hub_advertised = false, hub_security_started = false, move_next = false;
    [[maybe_unused]] bool bms_write_submitted = false, bms_write_acknowledged = false,
                          bms_disconnect_seen = false;
    [[maybe_unused]] unsigned bms_teardown_errors = 0U, expected_error_events = 0U,
                              no_ccc_errors = 0U;
    unsigned index = 0U, phase = 0U, alert_slot = 0U, alert_ccc = 0U, alert_sent = 0U;
    [[maybe_unused]] unsigned att_gap_rejects = 0U;
    [[maybe_unused]] ExpectedReject<BLEConnectionHandle> bms_reject, att_reject;
    uint8_t nonce_bytes[16] = {};
#include "stale-declarations.inc"

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
        return !local_bond;
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
            }
            return erase_ok;
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
    bool run(const std::string &test)
    {
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
    return ok ? 0 : 1;
}
