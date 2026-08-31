/**
 * @file NUCODE_BLE_Security.cpp
 * @brief NCS SMP, Settings, BAS, DIS와 HIDS 기반 M21 backend를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_Security.h>

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <internal/NUCODE_BLE_Internal.h>
#include <internal/NUCODE_BLE_HidsBackend.h>

#include <bluetooth/services/hids.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/services/bas.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace
{

    using nucode::ble::BondState;
    using nucode::ble::DeviceInformation;
    using nucode::ble::KeyboardReport;
    using nucode::ble::PeerAddress;
    using nucode::ble::SecurityConfig;
    using nucode::ble::SecurityError;
    using nucode::ble::SecurityEvent;
    using nucode::ble::SecurityEventCallback;
    using nucode::ble::SecurityEventRecord;
    using nucode::ble::SecurityLevel;

    /** @brief 사용자 응답을 기다리는 SMP 요청 종류입니다. */
    enum class PendingResponse : std::uint8_t
    {
        none,
        pairing_confirmation,
        passkey_entry,
        passkey_confirmation,
    };

    /** @brief 단일 connection의 사용자 응답 대기 상태입니다. */
    struct PendingState
    {
        struct bt_conn *connection = nullptr;
        PendingResponse response = PendingResponse::none;
        std::int64_t deadline_ms = 0;
    };

    /** @brief 현재 peer의 bond 검증 상태를 보존합니다. */
    struct BondLifecycleState
    {
        bt_addr_le_t peer = {};
        BondState state = BondState::none;
        bool peer_valid = false;
        bool paired_this_connection = false;
    };

    /** @brief 한 HIDS connection의 protocol mode와 등록 상태입니다. */
    struct HidConnectionState
    {
        struct bt_conn *connection = nullptr;
        bool registered = false;
        bool in_boot_mode = false;
    };

    constexpr std::size_t security_event_capacity = 24U;
    constexpr std::size_t maximum_dis_string_length = 32U;
    constexpr std::uint8_t keyboard_report_id = 1U;
    constexpr std::uint8_t keyboard_report_index = 0U;

    K_MSGQ_DEFINE(security_event_queue, sizeof(SecurityEventRecord),
                  security_event_capacity, alignof(SecurityEventRecord));
    K_MUTEX_DEFINE(hid_api_mutex);

    atomic_t security_initialized = ATOMIC_INIT(0);
    atomic_t paired_value = ATOMIC_INIT(0);
    atomic_t bond_state_value = ATOMIC_INIT(static_cast<atomic_val_t>(BondState::none));
    atomic_t startup_bond_snapshot_ready = ATOMIC_INIT(0);
    atomic_t current_level_value = ATOMIC_INIT(static_cast<atomic_val_t>(SecurityLevel::none));
    atomic_t security_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(SecurityError::none));
    atomic_t security_driver_error_value = ATOMIC_INIT(0);
    atomic_t hid_initialized = ATOMIC_INIT(0);
    atomic_t hid_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(SecurityError::none));
    atomic_t hid_driver_error_value = ATOMIC_INIT(0);
    atomic_t battery_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(SecurityError::none));
    atomic_t dis_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(SecurityError::none));

    struct k_spinlock connection_lock;
    struct k_spinlock pending_lock;
    struct k_spinlock bond_lock;
    struct k_spinlock startup_bond_lock;
    struct k_spinlock hid_state_lock;
    struct bt_conn *active_connection = nullptr;
    PendingState pending_state = {};
    BondLifecycleState bond_lifecycle = {};
    bt_addr_le_t startup_bonds[CONFIG_BT_MAX_PAIRED] = {};
    std::size_t startup_bond_count = 0U;
    HidConnectionState hid_connection_state = {};
    SecurityConfig security_config = {};
    SecurityEventCallback security_event_callback = nullptr;
    void *security_event_context = nullptr;

    struct bt_conn_auth_cb authentication_callbacks = {};
    struct bt_conn_auth_info_cb authentication_info_callbacks = {};

    static_assert(sizeof(KeyboardReport) == 8U,
                  "BLE HID keyboard report는 정확히 8 byte여야 합니다.");

    /** @brief 표준 keyboard input report descriptor입니다. */
    constexpr std::uint8_t keyboard_report_map[] = {
        0x05,
        0x01, /** 일반 데스크톱 사용 페이지입니다. */
        0x09,
        0x06, /** 키보드 사용 항목입니다. */
        0xA1,
        0x01, /** 애플리케이션 collection 시작입니다. */
        0x85,
        keyboard_report_id, /** 입력 report ID입니다. */
        0x05,
        0x07, /** 키보드 사용 페이지입니다. */
        0x19,
        0xE0, /** 왼쪽 Control 최소 사용 ID입니다. */
        0x29,
        0xE7, /** 오른쪽 GUI 최대 사용 ID입니다. */
        0x15,
        0x00, /** modifier 논리 최소값입니다. */
        0x25,
        0x01, /** modifier 논리 최대값입니다. */
        0x75,
        0x01, /** modifier report 크기입니다. */
        0x95,
        0x08, /** modifier report 개수입니다. */
        0x81,
        0x02, /** 가변 절대 입력입니다. */
        0x95,
        0x01, /** 예약 byte report 개수입니다. */
        0x75,
        0x08, /** 예약 byte report 크기입니다. */
        0x81,
        0x01, /** 예약 상수 입력입니다. */
        0x95,
        0x06, /** 동시 key report 개수입니다. */
        0x75,
        0x08, /** key report 크기입니다. */
        0x15,
        0x00, /** key 논리 최소값입니다. */
        0x25,
        0x65, /** key 논리 최대값입니다. */
        0x05,
        0x07, /** 키보드 사용 페이지입니다. */
        0x19,
        0x00, /** key 사용 ID 최소값입니다. */
        0x29,
        0x65, /** key 사용 ID 최대값입니다. */
        0x81,
        0x00, /** 배열 입력입니다. */
        0xC0, /** collection 종료입니다. */
    };

    /** @brief keyboard report의 모든 key usage가 descriptor 범위 안인지 확인합니다. */
    bool validKeyboardReport(const KeyboardReport &report) noexcept
    {
        for (const std::uint8_t usage : report.keys)
        {
            if (usage > 0x65U)
            {
                return false;
            }
        }
        return true;
    }

    /** @brief thread 문맥 전용 공개 API인지 확인합니다. */
    bool requireThreadContext() noexcept
    {
        if (k_is_in_isr())
        {
            atomic_set(&security_error_value,
                       static_cast<atomic_val_t>(SecurityError::invalid_context));
            atomic_set(&security_driver_error_value, -EWOULDBLOCK);
            return false;
        }
        return true;
    }

    /** @brief 마지막 security 오류와 원본 driver 오류를 함께 기록합니다. */
    void recordSecurityError(SecurityError error, int driver_error = 0) noexcept
    {
        atomic_set(&security_error_value, static_cast<atomic_val_t>(error));
        atomic_set(&security_driver_error_value, driver_error);
    }

    /** @brief 마지막 HID 오류와 원본 driver 오류를 함께 기록합니다. */
    void recordHidError(SecurityError error, int driver_error = 0) noexcept
    {
        atomic_set(&hid_error_value, static_cast<atomic_val_t>(error));
        atomic_set(&hid_driver_error_value, driver_error);
    }

    /** @brief Zephyr peer 주소를 공개 고정 길이 표현으로 복사합니다. */
    PeerAddress publicAddress(const bt_addr_le_t *address) noexcept
    {
        PeerAddress result = {};
        if (address != nullptr)
        {
            result.type = address->type;
            ::memcpy(result.value, address->a.val, sizeof(result.value));
        }
        return result;
    }

    /** @brief 공개 peer 주소를 Zephyr identity 주소로 복사합니다. */
    bt_addr_le_t nativeAddress(const PeerAddress &address) noexcept
    {
        bt_addr_le_t result = {};
        result.type = address.type;
        ::memcpy(result.a.val, address.value, sizeof(address.value));
        return result;
    }

    /** @brief 공개 가능한 현재 bond 상태 snapshot을 반환합니다. */
    BondState currentBondState() noexcept
    {
        return static_cast<BondState>(atomic_get(&bond_state_value));
    }

    /** @brief 현재 peer의 bond 상태를 원자적으로 교체합니다. */
    void setBondLifecycle(const bt_addr_le_t *peer, BondState state,
                          bool paired_this_connection) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&bond_lock);
        bond_lifecycle = {};
        if (peer != nullptr)
        {
            bt_addr_le_copy(&bond_lifecycle.peer, peer);
            bond_lifecycle.peer_valid = true;
        }
        bond_lifecycle.state = state;
        bond_lifecycle.paired_this_connection = paired_this_connection;
        k_spin_unlock(&bond_lock, key);
        atomic_set(&bond_state_value, static_cast<atomic_val_t>(state));
    }

    /** @brief 지정 peer와 현재 bond 후보가 같은지 확인합니다. */
    bool bondLifecycleMatches(const bt_addr_le_t *peer) noexcept
    {
        if (peer == nullptr)
        {
            return false;
        }
        bool matches = false;
        k_spinlock_key_t key = k_spin_lock(&bond_lock);
        matches = bond_lifecycle.peer_valid &&
                  bt_addr_le_eq(&bond_lifecycle.peer, peer);
        k_spin_unlock(&bond_lock, key);
        return matches;
    }

    /** @brief 오류 rollback에 사용할 bond 상태 snapshot을 복사합니다. */
    BondLifecycleState copyBondLifecycle() noexcept
    {
        BondLifecycleState snapshot = {};
        k_spinlock_key_t key = k_spin_lock(&bond_lock);
        snapshot = bond_lifecycle;
        k_spin_unlock(&bond_lock, key);
        return snapshot;
    }

    /** @brief 이전 bond 상태 snapshot을 복원합니다. */
    void restoreBondLifecycle(const BondLifecycleState &snapshot) noexcept
    {
        setBondLifecycle(snapshot.peer_valid ? &snapshot.peer : nullptr,
                         snapshot.state, snapshot.paired_this_connection);
    }

    /** @brief boot 때 로드된 bond 목록에 peer가 있었는지 확인합니다. */
    bool isStartupBond(const bt_addr_le_t *peer) noexcept
    {
        if (peer == nullptr)
        {
            return false;
        }
        bool found = false;
        k_spinlock_key_t key = k_spin_lock(&startup_bond_lock);
        for (std::size_t index = 0U; index < startup_bond_count; ++index)
        {
            if (bt_addr_le_eq(&startup_bonds[index], peer))
            {
                found = true;
                break;
            }
        }
        k_spin_unlock(&startup_bond_lock, key);
        return found;
    }

    /** @brief 실제 삭제 callback을 받은 peer를 boot bond snapshot에서 제거합니다. */
    void removeStartupBond(const bt_addr_le_t *peer) noexcept
    {
        if (peer == nullptr)
        {
            return;
        }
        k_spinlock_key_t key = k_spin_lock(&startup_bond_lock);
        for (std::size_t index = 0U; index < startup_bond_count; ++index)
        {
            if (!bt_addr_le_eq(&startup_bonds[index], peer))
            {
                continue;
            }
            for (std::size_t move = index + 1U; move < startup_bond_count; ++move)
            {
                bt_addr_le_copy(&startup_bonds[move - 1U], &startup_bonds[move]);
            }
            --startup_bond_count;
            break;
        }
        k_spin_unlock(&startup_bond_lock, key);
    }

    /** @brief connection의 security snapshot event를 만듭니다. */
    SecurityEventRecord makeEvent(SecurityEvent event, struct bt_conn *connection,
                                  std::uint32_t passkey = 0U,
                                  std::uint8_t reason = 0U) noexcept
    {
        SecurityEventRecord record = {};
        record.event = event;
        record.level = connection == nullptr
                           ? static_cast<SecurityLevel>(atomic_get(&current_level_value))
                           : static_cast<SecurityLevel>(bt_conn_get_security(connection));
        record.peer = publicAddress(connection == nullptr ? nullptr : bt_conn_get_dst(connection));
        record.passkey = passkey;
        record.reason = reason;
        record.bond_state = currentBondState();
        record.bonded = record.bond_state == BondState::verified;
        return record;
    }

    /** @brief 주소만 가진 bond event를 만듭니다. */
    SecurityEventRecord makePeerEvent(SecurityEvent event,
                                      const bt_addr_le_t *peer,
                                      BondState state) noexcept
    {
        SecurityEventRecord record = {};
        record.event = event;
        record.level = static_cast<SecurityLevel>(atomic_get(&current_level_value));
        record.peer = publicAddress(peer);
        record.bond_state = state;
        record.bonded = state == BondState::verified;
        return record;
    }

    /** @brief bounded event queue overflow를 공개 오류로 보존합니다. */
    void queueEvent(const SecurityEventRecord &record) noexcept
    {
        if (k_msgq_put(&security_event_queue, &record, K_NO_WAIT) != 0)
        {
            recordSecurityError(SecurityError::busy, -ENOBUFS);
        }
    }

    /** @brief active connection에 호출자 수명 동안 reference를 얻습니다. */
    struct bt_conn *referenceActiveConnection() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        struct bt_conn *connection = active_connection;
        if (connection != nullptr)
        {
            bt_conn_ref(connection);
        }
        k_spin_unlock(&connection_lock, key);
        return connection;
    }

    /** @brief callback connection이 현재 API가 소유한 exact connection인지 확인합니다. */
    bool isActiveConnection(struct bt_conn *connection) noexcept
    {
        struct bt_conn *active = referenceActiveConnection();
        const bool matches = active != nullptr && active == connection;
        if (active != nullptr)
        {
            bt_conn_unref(active);
        }
        return matches;
    }

    /** @brief 첫 연결에서 boot 시작 bond 목록을 최초 한 번만 고정합니다. */
    void captureStartupBonds() noexcept
    {
        if (!atomic_cas(&startup_bond_snapshot_ready, 0, 1))
        {
            return;
        }

        struct Snapshot
        {
            bt_addr_le_t bonds[ARRAY_SIZE(startup_bonds)] = {};
            std::size_t count = 0U;
        } snapshot;
        if (nucode::ble::internal::settingsReady())
        {
            bt_foreach_bond(
                BT_ID_DEFAULT,
                [](const struct bt_bond_info *information, void *context)
                {
                    Snapshot *output = static_cast<Snapshot *>(context);
                    if (information != nullptr && output != nullptr &&
                        output->count < ARRAY_SIZE(output->bonds))
                    {
                        bt_addr_le_copy(&output->bonds[output->count],
                                        &information->addr);
                        ++output->count;
                    }
                },
                &snapshot);
        }

        k_spinlock_key_t key = k_spin_lock(&startup_bond_lock);
        startup_bond_count = snapshot.count;
        for (std::size_t index = 0U; index < snapshot.count; ++index)
        {
            bt_addr_le_copy(&startup_bonds[index], &snapshot.bonds[index]);
        }
        k_spin_unlock(&startup_bond_lock, key);
    }

    /** @brief pending SMP 사용자 응답 connection을 안전하게 해제합니다. */
    void clearPending(struct bt_conn *matching_connection = nullptr) noexcept
    {
        struct bt_conn *released = nullptr;
        k_spinlock_key_t key = k_spin_lock(&pending_lock);
        if (pending_state.connection != nullptr &&
            (matching_connection == nullptr ||
             matching_connection == pending_state.connection))
        {
            released = pending_state.connection;
            pending_state = {};
        }
        k_spin_unlock(&pending_lock, key);
        if (released != nullptr)
        {
            bt_conn_unref(released);
        }
    }

    /** @brief 사용자 응답이 필요한 SMP 요청을 하나만 보존합니다. */
    bool setPending(struct bt_conn *connection, PendingResponse response,
                    SecurityEvent event, std::uint32_t passkey = 0U) noexcept
    {
        if (connection == nullptr)
        {
            return false;
        }
        if (!isActiveConnection(connection))
        {
            static_cast<void>(bt_conn_auth_cancel(connection));
            return false;
        }
        bool accepted = false;
        k_spinlock_key_t key = k_spin_lock(&pending_lock);
        if (pending_state.connection == nullptr)
        {
            pending_state.connection = bt_conn_ref(connection);
            pending_state.response = response;
            pending_state.deadline_ms =
                k_uptime_get() + static_cast<std::int64_t>(security_config.response_timeout_ms);
            accepted = true;
        }
        k_spin_unlock(&pending_lock, key);
        if (!accepted)
        {
            recordSecurityError(SecurityError::busy, -EBUSY);
            queueEvent(makeEvent(SecurityEvent::error, connection));
            static_cast<void>(bt_conn_auth_cancel(connection));
            return false;
        }
        queueEvent(makeEvent(event, connection, passkey));
        return true;
    }

    /** @brief 예상 종류의 pending connection 소유권을 호출자에게 넘깁니다. */
    struct bt_conn *takePending(PendingResponse expected) noexcept
    {
        struct bt_conn *connection = nullptr;
        k_spinlock_key_t key = k_spin_lock(&pending_lock);
        if (pending_state.connection != nullptr && pending_state.response == expected)
        {
            connection = pending_state.connection;
            pending_state = {};
        }
        k_spin_unlock(&pending_lock, key);
        return connection;
    }

    /** @brief timeout이 지난 pending pairing 요청을 취소합니다. */
    void processPendingTimeout() noexcept
    {
        struct bt_conn *connection = nullptr;
        k_spinlock_key_t key = k_spin_lock(&pending_lock);
        if (pending_state.connection != nullptr &&
            k_uptime_get() >= pending_state.deadline_ms)
        {
            connection = pending_state.connection;
            pending_state = {};
        }
        k_spin_unlock(&pending_lock, key);
        if (connection == nullptr)
        {
            return;
        }
        static_cast<void>(bt_conn_auth_cancel(connection));
        recordSecurityError(SecurityError::timeout, -ETIMEDOUT);
        queueEvent(makeEvent(SecurityEvent::timeout, connection));
        bt_conn_unref(connection);
    }

    /** @brief 새 SMP pairing 시작 시 restored candidate를 즉시 무효화합니다. */
    void markPairingStarted(struct bt_conn *connection) noexcept
    {
        if (!isActiveConnection(connection))
        {
            return;
        }
        const bt_addr_le_t *const peer = bt_conn_get_dst(connection);
        if (bondLifecycleMatches(peer) &&
            currentBondState() == BondState::restored_candidate)
        {
            setBondLifecycle(peer, BondState::none, true);
        }
        atomic_set(&paired_value, 0);
    }

    /** @brief 모든 SMP pairing req/rsp를 허용하되 새 pairing 여부를 먼저 기록합니다. */
    enum bt_security_err pairingAccept(
        struct bt_conn *connection,
        const struct bt_conn_pairing_feat *features)
    {
        ARG_UNUSED(features);
        markPairingStarted(connection);
        return BT_SECURITY_ERR_SUCCESS;
    }

    /** @brief passkey display 요청을 main-thread event로 전달합니다. */
    void passkeyDisplay(struct bt_conn *connection, unsigned int passkey)
    {
        markPairingStarted(connection);
        if (isActiveConnection(connection))
        {
            queueEvent(makeEvent(SecurityEvent::passkey_display, connection, passkey));
        }
    }

    /** @brief passkey 입력 요청을 main-thread event로 전달합니다. */
    void passkeyEntry(struct bt_conn *connection)
    {
        markPairingStarted(connection);
        static_cast<void>(setPending(connection, PendingResponse::passkey_entry,
                                     SecurityEvent::passkey_input_requested));
    }

    /** @brief numeric comparison 요청을 main-thread event로 전달합니다. */
    void passkeyConfirm(struct bt_conn *connection, unsigned int passkey)
    {
        markPairingStarted(connection);
        static_cast<void>(setPending(connection, PendingResponse::passkey_confirmation,
                                     SecurityEvent::passkey_confirmation_requested,
                                     passkey));
    }

    /** @brief Just Works pairing도 명시적 Sketch 승인 뒤에만 진행합니다. */
    void pairingConfirm(struct bt_conn *connection)
    {
        markPairingStarted(connection);
        static_cast<void>(setPending(connection, PendingResponse::pairing_confirmation,
                                     SecurityEvent::pairing_requested));
    }

    /** @brief stack이 사용자 요청을 취소하면 pending reference를 회수합니다. */
    void authenticationCancelled(struct bt_conn *connection)
    {
        clearPending(connection);
        if (isActiveConnection(connection))
        {
            queueEvent(makeEvent(SecurityEvent::pairing_cancelled, connection));
        }
    }

    /** @brief pairing 성공을 기록하되 같은 boot에서 persistence 완료로 승격하지 않습니다. */
    void pairingComplete(struct bt_conn *connection, bool bonded)
    {
        clearPending(connection);
        if (!isActiveConnection(connection))
        {
            return;
        }
        atomic_set(&paired_value, 1);
        atomic_set(&current_level_value,
                   static_cast<atomic_val_t>(bt_conn_get_security(connection)));
        const bt_addr_le_t *const peer = bt_conn_get_dst(connection);
        if (bonded && security_config.bonding)
        {
            setBondLifecycle(peer, BondState::persistence_pending, true);
            queueEvent(makeEvent(SecurityEvent::paired, connection));
            queueEvent(makePeerEvent(SecurityEvent::bond_persistence_pending, peer,
                                     BondState::persistence_pending));
        }
        else
        {
            setBondLifecycle(peer, BondState::none, true);
            queueEvent(makeEvent(SecurityEvent::paired, connection));
        }
    }

    /** @brief pairing 실패 reason을 key material 없이 event로 전달합니다. */
    void pairingFailed(struct bt_conn *connection, enum bt_security_err reason)
    {
        clearPending(connection);
        if (!isActiveConnection(connection))
        {
            return;
        }
        atomic_set(&paired_value, 0);
        if (bondLifecycleMatches(bt_conn_get_dst(connection)))
        {
            setBondLifecycle(nullptr, BondState::none, false);
        }
        recordSecurityError(SecurityError::rejected, -static_cast<int>(reason));
        queueEvent(makeEvent(SecurityEvent::pairing_failed, connection, 0U,
                             static_cast<std::uint8_t>(reason)));
    }

    /** @brief runtime bond 삭제 callback을 내부 snapshot에만 반영합니다. */
    void bondDeleted(std::uint8_t identity, const bt_addr_le_t *peer)
    {
        ARG_UNUSED(identity);
        removeStartupBond(peer);
        if (bondLifecycleMatches(peer))
        {
            if (currentBondState() != BondState::removal_requested)
            {
                setBondLifecycle(nullptr, BondState::none, false);
            }
            atomic_set(&paired_value, 0);
        }
    }

    /** @brief public API가 참조하는 auth callback storage를 구성합니다. */
    void prepareAuthenticationCallbacks() noexcept
    {
        authentication_callbacks = {};
        authentication_callbacks.pairing_accept = pairingAccept;
        authentication_callbacks.passkey_display = passkeyDisplay;
        authentication_callbacks.passkey_entry = passkeyEntry;
        authentication_callbacks.passkey_confirm = passkeyConfirm;
        authentication_callbacks.cancel = authenticationCancelled;
        authentication_callbacks.pairing_confirm = pairingConfirm;

        authentication_info_callbacks = {};
        authentication_info_callbacks.pairing_complete = pairingComplete;
        authentication_info_callbacks.pairing_failed = pairingFailed;
        authentication_info_callbacks.bond_deleted = bondDeleted;
    }

    /** @brief active connection이 지정 peer인지 확인하고 제거합니다. */
    bool releaseActiveConnection(struct bt_conn *matching) noexcept
    {
        struct bt_conn *released = nullptr;
        k_spinlock_key_t key = k_spin_lock(&connection_lock);
        if (active_connection != nullptr && active_connection == matching)
        {
            released = active_connection;
            active_connection = nullptr;
        }
        k_spin_unlock(&connection_lock, key);
        if (released != nullptr)
        {
            bt_conn_unref(released);
            return true;
        }
        return false;
    }

    /** @brief DIS 문자열을 caller 수명과 분리된 fixed buffer로 검증·복사합니다. */
    bool copyDisString(const char *source,
                       char (&destination)[maximum_dis_string_length + 1U],
                       bool required) noexcept
    {
        if (source == nullptr)
        {
            destination[0] = '\0';
            return !required;
        }
        const std::size_t length = ::strnlen(source, maximum_dis_string_length + 1U);
        if ((required && length == 0U) || length > maximum_dis_string_length)
        {
            return false;
        }
        ::memcpy(destination, source, length);
        destination[length] = '\0';
        return true;
    }

    /** @brief runtime DIS cache에 null terminator를 포함해 값을 설정합니다. */
    int setDisValue(const char *key, const char *value) noexcept
    {
        return settings_runtime_set(key, value, ::strlen(value) + 1U);
    }

    /** @brief host가 선택한 HIDS protocol mode를 exact connection slot에 반영합니다. */
    void hidsProtocolModeChanged(enum bt_hids_pm_evt event,
                                 struct bt_conn *connection)
    {
        k_spinlock_key_t key = k_spin_lock(&hid_state_lock);
        if (hid_connection_state.registered &&
            hid_connection_state.connection == connection)
        {
            if (event == BT_HIDS_PM_EVT_BOOT_MODE_ENTERED)
            {
                hid_connection_state.in_boot_mode = true;
            }
            else if (event == BT_HIDS_PM_EVT_REPORT_MODE_ENTERED)
            {
                hid_connection_state.in_boot_mode = false;
            }
        }
        k_spin_unlock(&hid_state_lock, key);
    }

    /** @brief hid_api_mutex를 보유한 상태에서 connection을 HIDS slot에 등록합니다. */
    int attachHidsLocked(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr || atomic_get(&hid_initialized) == 0)
        {
            return 0;
        }
        k_spinlock_key_t key = k_spin_lock(&hid_state_lock);
        const bool already_registered = hid_connection_state.registered &&
                                        hid_connection_state.connection == connection;
        const bool occupied = hid_connection_state.registered &&
                              hid_connection_state.connection != connection;
        k_spin_unlock(&hid_state_lock, key);
        if (already_registered)
        {
            return 0;
        }
        if (occupied)
        {
            return -ENOMEM;
        }

        const int result = bt_hids_connected(nucode_ble_hids_backend(), connection);
        if (result < 0)
        {
            return result;
        }
        key = k_spin_lock(&hid_state_lock);
        if (!hid_connection_state.registered)
        {
            hid_connection_state.connection = bt_conn_ref(connection);
            hid_connection_state.registered = true;
            hid_connection_state.in_boot_mode = false;
        }
        else
        {
            k_spin_unlock(&hid_state_lock, key);
            static_cast<void>(bt_hids_disconnected(nucode_ble_hids_backend(), connection));
            return -EALREADY;
        }
        k_spin_unlock(&hid_state_lock, key);
        return 0;
    }

    /** @brief hid_api_mutex를 보유한 상태에서 exact connection slot을 회수합니다. */
    int detachHidsLocked(struct bt_conn *connection) noexcept
    {
        if (connection == nullptr || atomic_get(&hid_initialized) == 0)
        {
            return 0;
        }
        k_spinlock_key_t key = k_spin_lock(&hid_state_lock);
        const bool matches = hid_connection_state.registered &&
                             hid_connection_state.connection == connection;
        k_spin_unlock(&hid_state_lock, key);
        if (!matches)
        {
            return 0;
        }

        const int result = bt_hids_disconnected(nucode_ble_hids_backend(), connection);
        struct bt_conn *released = nullptr;
        key = k_spin_lock(&hid_state_lock);
        if (hid_connection_state.registered &&
            hid_connection_state.connection == connection)
        {
            released = hid_connection_state.connection;
            hid_connection_state = {};
        }
        k_spin_unlock(&hid_state_lock, key);
        if (released != nullptr)
        {
            bt_conn_unref(released);
        }
        return result;
    }

    /** @brief 현재 HIDS exact connection과 protocol mode snapshot을 참조합니다. */
    struct bt_conn *referenceHidConnection(bool *boot_mode) noexcept
    {
        struct bt_conn *connection = nullptr;
        k_spinlock_key_t key = k_spin_lock(&hid_state_lock);
        if (hid_connection_state.registered &&
            hid_connection_state.connection != nullptr)
        {
            connection = bt_conn_ref(hid_connection_state.connection);
            if (boot_mode != nullptr)
            {
                *boot_mode = hid_connection_state.in_boot_mode;
            }
        }
        k_spin_unlock(&hid_state_lock, key);
        return connection;
    }

}

namespace nucode::ble
{

    bool SecurityManager::begin(const SecurityConfig &config) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        const unsigned int level = static_cast<unsigned int>(config.minimum_level);
        if (level < static_cast<unsigned int>(SecurityLevel::encrypted) ||
            level > static_cast<unsigned int>(SecurityLevel::secure_connections) ||
            config.response_timeout_ms < 1000U || config.response_timeout_ms > 300000U)
        {
            recordSecurityError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }
        if (!atomic_cas(&security_initialized, 0, 1))
        {
            recordSecurityError(SecurityError::busy, -EALREADY);
            return false;
        }

        security_config = config;
        k_msgq_purge(&security_event_queue);
        k_spinlock_key_t startup_key = k_spin_lock(&startup_bond_lock);
        startup_bond_count = 0U;
        k_spin_unlock(&startup_bond_lock, startup_key);
        atomic_set(&startup_bond_snapshot_ready, 0);
        atomic_set(&paired_value, 0);
        setBondLifecycle(nullptr, BondState::none, false);
        prepareAuthenticationCallbacks();
        int result = bt_conn_auth_cb_register(&authentication_callbacks);
        if (result == 0)
        {
            result = bt_conn_auth_info_cb_register(&authentication_info_callbacks);
        }
        if (result < 0)
        {
            atomic_set(&security_initialized, 0);
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        bt_set_bondable(config.bonding);
        recordSecurityError(SecurityError::none);
        return true;
    }

    void SecurityManager::poll() noexcept
    {
        if (!requireThreadContext())
        {
            return;
        }
        if (atomic_get(&security_initialized) == 0)
        {
            recordSecurityError(SecurityError::not_initialized, -EACCES);
            return;
        }
        processPendingTimeout();

        SecurityEventRecord event = {};
        while (k_msgq_get(&security_event_queue, &event, K_NO_WAIT) == 0)
        {
            SecurityEventCallback callback = security_event_callback;
            if (callback != nullptr)
            {
                callback(event, security_event_context);
            }
        }
    }

    bool SecurityManager::requestSecurity() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        if (atomic_get(&security_initialized) == 0)
        {
            recordSecurityError(SecurityError::not_initialized, -EACCES);
            return false;
        }
        struct bt_conn *connection = referenceActiveConnection();
        if (connection == nullptr)
        {
            recordSecurityError(SecurityError::not_connected, -ENOTCONN);
            return false;
        }
        const int result = bt_conn_set_security(
            connection, static_cast<bt_security_t>(security_config.minimum_level));
        bt_conn_unref(connection);
        if (result < 0)
        {
            recordSecurityError(result == -EBUSY ? SecurityError::busy
                                                 : SecurityError::driver_error,
                                result);
            return false;
        }
        recordSecurityError(SecurityError::none);
        return true;
    }

    bool SecurityManager::acceptPairing(bool accept) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = takePending(PendingResponse::pairing_confirmation);
        if (connection == nullptr)
        {
            recordSecurityError(SecurityError::invalid_state, -EALREADY);
            return false;
        }
        const int result = accept ? bt_conn_auth_pairing_confirm(connection)
                                  : bt_conn_auth_cancel(connection);
        bt_conn_unref(connection);
        if (result < 0)
        {
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        if (!accept)
        {
            recordSecurityError(SecurityError::rejected, -ECANCELED);
        }
        else
        {
            recordSecurityError(SecurityError::none);
        }
        return true;
    }

    bool SecurityManager::enterPasskey(std::uint32_t passkey) noexcept
    {
        if (!requireThreadContext() || passkey > 999999U)
        {
            if (passkey > 999999U)
            {
                recordSecurityError(SecurityError::invalid_argument, -EINVAL);
            }
            return false;
        }
        struct bt_conn *connection = takePending(PendingResponse::passkey_entry);
        if (connection == nullptr)
        {
            recordSecurityError(SecurityError::invalid_state, -EALREADY);
            return false;
        }
        const int result = bt_conn_auth_passkey_entry(connection, passkey);
        bt_conn_unref(connection);
        if (result < 0)
        {
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        recordSecurityError(SecurityError::none);
        return true;
    }

    bool SecurityManager::confirmPasskey(bool accept) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = takePending(PendingResponse::passkey_confirmation);
        if (connection == nullptr)
        {
            recordSecurityError(SecurityError::invalid_state, -EALREADY);
            return false;
        }
        const int result = accept ? bt_conn_auth_passkey_confirm(connection)
                                  : bt_conn_auth_cancel(connection);
        bt_conn_unref(connection);
        if (result < 0)
        {
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        recordSecurityError(accept ? SecurityError::none : SecurityError::rejected,
                            accept ? 0 : -ECANCELED);
        return true;
    }

    bool SecurityManager::cancelPairing() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = nullptr;
        k_spinlock_key_t key = k_spin_lock(&pending_lock);
        if (pending_state.connection != nullptr)
        {
            connection = pending_state.connection;
            pending_state = {};
        }
        k_spin_unlock(&pending_lock, key);
        if (connection == nullptr)
        {
            recordSecurityError(SecurityError::invalid_state, -EALREADY);
            return false;
        }
        const int result = bt_conn_auth_cancel(connection);
        bt_conn_unref(connection);
        if (result < 0)
        {
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        recordSecurityError(SecurityError::none);
        return true;
    }

    std::size_t SecurityManager::bondCount() const noexcept
    {
        std::size_t count = 0U;
        bt_foreach_bond(
            BT_ID_DEFAULT,
            [](const struct bt_bond_info *information, void *context)
            {
                ARG_UNUSED(information);
                std::size_t *value = static_cast<std::size_t *>(context);
                if (value != nullptr)
                {
                    ++(*value);
                }
            },
            &count);
        return count;
    }

    std::size_t SecurityManager::copyBonds(PeerAddress *buffer,
                                           std::size_t capacity) const noexcept
    {
        if (buffer == nullptr || capacity == 0U)
        {
            return 0U;
        }
        struct Context
        {
            PeerAddress *buffer;
            std::size_t capacity;
            std::size_t count;
        } context = {buffer, capacity, 0U};
        bt_foreach_bond(
            BT_ID_DEFAULT,
            [](const struct bt_bond_info *information, void *opaque)
            {
                Context *output = static_cast<Context *>(opaque);
                if (output != nullptr && output->count < output->capacity)
                {
                    output->buffer[output->count++] = publicAddress(&information->addr);
                }
            },
            &context);
        return context.count;
    }

    bool SecurityManager::eraseBond(const PeerAddress &peer) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        const bt_addr_le_t address = nativeAddress(peer);
        const BondLifecycleState previous = copyBondLifecycle();
        if (bondLifecycleMatches(&address))
        {
            setBondLifecycle(&address, BondState::removal_requested, false);
        }
        const int result = bt_unpair(BT_ID_DEFAULT, &address);
        if (result < 0)
        {
            restoreBondLifecycle(previous);
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        queueEvent(makePeerEvent(SecurityEvent::bond_removal_requested, &address,
                                 BondState::removal_requested));
        recordSecurityError(SecurityError::none);
        return true;
    }

    bool SecurityManager::eraseAllBonds() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        const BondLifecycleState previous = copyBondLifecycle();
        setBondLifecycle(previous.peer_valid ? &previous.peer : nullptr,
                         BondState::removal_requested, false);
        const int result = bt_unpair(BT_ID_DEFAULT, BT_ADDR_LE_ANY);
        if (result < 0)
        {
            restoreBondLifecycle(previous);
            recordSecurityError(SecurityError::driver_error, result);
            return false;
        }
        queueEvent(makePeerEvent(SecurityEvent::all_bonds_removal_requested, nullptr,
                                 BondState::removal_requested));
        recordSecurityError(SecurityError::none);
        return true;
    }

    bool SecurityManager::paired() const noexcept
    {
        return atomic_get(&paired_value) != 0;
    }

    bool SecurityManager::bonded() const noexcept
    {
        return currentBondState() == BondState::verified;
    }

    BondState SecurityManager::bondState() const noexcept
    {
        return currentBondState();
    }

    SecurityLevel SecurityManager::currentLevel() const noexcept
    {
        return static_cast<SecurityLevel>(atomic_get(&current_level_value));
    }

    void SecurityManager::onEvent(SecurityEventCallback callback, void *context) noexcept
    {
        if (!requireThreadContext())
        {
            return;
        }
        security_event_callback = callback;
        security_event_context = context;
    }

    SecurityError SecurityManager::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&security_error_value));
    }

    int SecurityManager::lastDriverError() const noexcept
    {
        return static_cast<int>(atomic_get(&security_driver_error_value));
    }

    bool BatteryService::setLevel(std::uint8_t percent) noexcept
    {
        if (k_is_in_isr())
        {
            atomic_set(&battery_error_value,
                       static_cast<atomic_val_t>(SecurityError::invalid_context));
            return false;
        }
        if (percent > 100U)
        {
            atomic_set(&battery_error_value,
                       static_cast<atomic_val_t>(SecurityError::invalid_argument));
            return false;
        }
        const int result = bt_bas_set_battery_level(percent);
        atomic_set(&battery_error_value,
                   static_cast<atomic_val_t>(result < 0 ? SecurityError::driver_error
                                                        : SecurityError::none));
        return result >= 0;
    }

    std::uint8_t BatteryService::level() const noexcept
    {
        return bt_bas_get_battery_level();
    }

    SecurityError BatteryService::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&battery_error_value));
    }

    bool DeviceInformationService::configure(
        const DeviceInformation &information) noexcept
    {
        if (!requireThreadContext())
        {
            atomic_set(&dis_error_value,
                       static_cast<atomic_val_t>(SecurityError::invalid_context));
            return false;
        }
        char manufacturer[maximum_dis_string_length + 1U] = {};
        char model[maximum_dis_string_length + 1U] = {};
        char serial[maximum_dis_string_length + 1U] = {};
        char firmware[maximum_dis_string_length + 1U] = {};
        char hardware[maximum_dis_string_length + 1U] = {};
        char software[maximum_dis_string_length + 1U] = {};
        if (!copyDisString(information.manufacturer, manufacturer, true) ||
            !copyDisString(information.model, model, true) ||
            !copyDisString(information.serial_number, serial, false) ||
            !copyDisString(information.firmware_revision, firmware, false) ||
            !copyDisString(information.hardware_revision, hardware, false) ||
            !copyDisString(information.software_revision, software, false))
        {
            atomic_set(&dis_error_value,
                       static_cast<atomic_val_t>(SecurityError::invalid_argument));
            return false;
        }

        const struct
        {
            const char *key;
            const char *value;
        } values[] = {
            {"bt/dis/manuf", manufacturer},
            {"bt/dis/model", model},
            {"bt/dis/serial", serial},
            {"bt/dis/fw", firmware},
            {"bt/dis/hw", hardware},
            {"bt/dis/sw", software},
        };
        for (const auto &value : values)
        {
            const int result = setDisValue(value.key, value.value);
            if (result < 0)
            {
                atomic_set(&dis_error_value,
                           static_cast<atomic_val_t>(SecurityError::driver_error));
                return false;
            }
        }
        atomic_set(&dis_error_value, static_cast<atomic_val_t>(SecurityError::none));
        return true;
    }

    SecurityError DeviceInformationService::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&dis_error_value));
    }

    bool HidKeyboard::begin() noexcept
    {
        if (!requireThreadContext())
        {
            recordHidError(SecurityError::invalid_context, -EWOULDBLOCK);
            return false;
        }
        k_mutex_lock(&hid_api_mutex, K_FOREVER);
        if (atomic_get(&hid_initialized) != 0)
        {
            k_mutex_unlock(&hid_api_mutex);
            recordHidError(SecurityError::busy, -EALREADY);
            return false;
        }
        struct bt_hids_init_param parameters = {};
        parameters.rep_map.data = keyboard_report_map;
        parameters.rep_map.size = sizeof(keyboard_report_map);
        parameters.info.bcd_hid = 0x0111U;
        parameters.info.b_country_code = 0U;
        parameters.info.flags = BT_HIDS_REMOTE_WAKE | BT_HIDS_NORMALLY_CONNECTABLE;
        parameters.inp_rep_group_init.reports[keyboard_report_index].id = keyboard_report_id;
        parameters.inp_rep_group_init.reports[keyboard_report_index].size = sizeof(KeyboardReport);
        parameters.inp_rep_group_init.cnt = 1U;
        parameters.is_kb = true;
        parameters.pm_evt_handler = hidsProtocolModeChanged;

        struct bt_hids *const keyboard_hids = nucode_ble_hids_backend();
        int result = bt_hids_init(keyboard_hids, &parameters);
        if (result == 0)
        {
            atomic_set(&hid_initialized, 1);
            struct bt_conn *connection = referenceActiveConnection();
            if (connection != nullptr)
            {
                result = attachHidsLocked(connection);
                bt_conn_unref(connection);
            }
        }
        k_mutex_unlock(&hid_api_mutex);
        if (result < 0)
        {
            recordHidError(SecurityError::driver_error, result);
            return false;
        }
        recordHidError(SecurityError::none);
        return true;
    }

    bool HidKeyboard::sendReport(const KeyboardReport &report) noexcept
    {
        if (!requireThreadContext())
        {
            recordHidError(SecurityError::invalid_context, -EWOULDBLOCK);
            return false;
        }
        if (!validKeyboardReport(report))
        {
            recordHidError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }
        if (atomic_get(&hid_initialized) == 0)
        {
            recordHidError(SecurityError::not_initialized, -EACCES);
            return false;
        }
        k_mutex_lock(&hid_api_mutex, K_FOREVER);
        bool boot_mode = false;
        struct bt_conn *connection = referenceHidConnection(&boot_mode);
        if (connection == nullptr)
        {
            k_mutex_unlock(&hid_api_mutex);
            recordHidError(SecurityError::not_connected, -ENOTCONN);
            return false;
        }
        if (bt_conn_get_security(connection) < BT_SECURITY_L2)
        {
            bt_conn_unref(connection);
            k_mutex_unlock(&hid_api_mutex);
            recordHidError(SecurityError::invalid_state, -EACCES);
            return false;
        }
        const auto *const bytes = reinterpret_cast<const std::uint8_t *>(&report);
        const int result = boot_mode
                               ? bt_hids_boot_kb_inp_rep_send(
                                     nucode_ble_hids_backend(), connection, bytes,
                                     sizeof(report), nullptr)
                               : bt_hids_inp_rep_send(
                                     nucode_ble_hids_backend(), connection,
                                     keyboard_report_index, bytes, sizeof(report), nullptr);
        bt_conn_unref(connection);
        k_mutex_unlock(&hid_api_mutex);
        if (result < 0)
        {
            recordHidError(result == -EACCES ? SecurityError::not_subscribed
                                             : SecurityError::driver_error,
                           result);
            return false;
        }
        recordHidError(SecurityError::none);
        return true;
    }

    bool HidKeyboard::press(std::uint8_t usage, std::uint8_t modifiers) noexcept
    {
        if (usage == 0U || usage > 0x65U)
        {
            recordHidError(SecurityError::invalid_argument, -EINVAL);
            return false;
        }
        KeyboardReport report = {};
        report.modifiers = modifiers;
        report.keys[0] = usage;
        return sendReport(report);
    }

    bool HidKeyboard::releaseAll() noexcept
    {
        return sendReport(KeyboardReport{});
    }

    bool HidKeyboard::connected() const noexcept
    {
        bool boot_mode = false;
        struct bt_conn *connection = referenceHidConnection(&boot_mode);
        ARG_UNUSED(boot_mode);
        if (connection == nullptr)
        {
            return false;
        }
        bt_conn_unref(connection);
        return atomic_get(&hid_initialized) != 0;
    }

    SecurityError HidKeyboard::lastError() const noexcept
    {
        return static_cast<SecurityError>(atomic_get(&hid_error_value));
    }

    int HidKeyboard::lastDriverError() const noexcept
    {
        return static_cast<int>(atomic_get(&hid_driver_error_value));
    }

    namespace internal
    {

        void securityConnected(struct bt_conn *connection) noexcept
        {
            if (connection == nullptr)
            {
                return;
            }
            bool inserted = false;
            k_spinlock_key_t key = k_spin_lock(&connection_lock);
            if (active_connection == nullptr)
            {
                active_connection = bt_conn_ref(connection);
                inserted = true;
            }
            k_spin_unlock(&connection_lock, key);
            if (!inserted)
            {
                return;
            }
            atomic_set(&current_level_value,
                       static_cast<atomic_val_t>(bt_conn_get_security(connection)));
            atomic_set(&paired_value, 0);
            captureStartupBonds();
            const bt_addr_le_t *const peer = bt_conn_get_dst(connection);
            if (isStartupBond(peer))
            {
                setBondLifecycle(peer, BondState::restored_candidate, false);
                queueEvent(makePeerEvent(SecurityEvent::bond_restored_candidate, peer,
                                         BondState::restored_candidate));
            }
            else
            {
                setBondLifecycle(nullptr, BondState::none, false);
            }
            if (atomic_get(&hid_initialized) != 0)
            {
                k_mutex_lock(&hid_api_mutex, K_FOREVER);
                const int result = attachHidsLocked(connection);
                k_mutex_unlock(&hid_api_mutex);
                if (result < 0)
                {
                    recordHidError(SecurityError::driver_error, result);
                }
            }
        }

        void securityDisconnected(struct bt_conn *connection) noexcept
        {
            if (connection == nullptr)
            {
                return;
            }
            if (atomic_get(&hid_initialized) != 0)
            {
                k_mutex_lock(&hid_api_mutex, K_FOREVER);
                const int result = detachHidsLocked(connection);
                k_mutex_unlock(&hid_api_mutex);
                if (result < 0)
                {
                    recordHidError(SecurityError::driver_error, result);
                }
            }
            clearPending(connection);
            if (releaseActiveConnection(connection))
            {
                if (bondLifecycleMatches(bt_conn_get_dst(connection)) &&
                    currentBondState() != BondState::removal_requested)
                {
                    setBondLifecycle(nullptr, BondState::none, false);
                }
                atomic_set(&paired_value, 0);
                atomic_set(&current_level_value,
                           static_cast<atomic_val_t>(SecurityLevel::none));
            }
        }

        void securityChanged(struct bt_conn *connection, bt_security_t level,
                             enum bt_security_err error) noexcept
        {
            if (connection == nullptr)
            {
                return;
            }
            struct bt_conn *active = referenceActiveConnection();
            const bool is_active = active == connection;
            if (active != nullptr)
            {
                bt_conn_unref(active);
            }
            if (!is_active)
            {
                return;
            }
            if (error != BT_SECURITY_ERR_SUCCESS)
            {
                if (bondLifecycleMatches(bt_conn_get_dst(connection)))
                {
                    setBondLifecycle(nullptr, BondState::none, false);
                }
                atomic_set(&paired_value, 0);
                recordSecurityError(SecurityError::driver_error,
                                    -static_cast<int>(error));
                queueEvent(makeEvent(SecurityEvent::error, connection, 0U,
                                     static_cast<std::uint8_t>(error)));
                return;
            }
            atomic_set(&current_level_value, static_cast<atomic_val_t>(level));
            const bt_addr_le_t *const peer = bt_conn_get_dst(connection);
            if (level >= BT_SECURITY_L2 && bondLifecycleMatches(peer) &&
                currentBondState() == BondState::restored_candidate)
            {
                setBondLifecycle(peer, BondState::verified, false);
                atomic_set(&paired_value, 1);
                queueEvent(makePeerEvent(SecurityEvent::bond_verified, peer,
                                         BondState::verified));
            }
            else if (level >= BT_SECURITY_L2 &&
                     currentBondState() != BondState::removal_requested)
            {
                atomic_set(&paired_value, 1);
            }
            queueEvent(makeEvent(SecurityEvent::security_changed, connection));
        }

    }

}

nucode::ble::SecurityManager BLESecurity;
nucode::ble::BatteryService BLEBattery;
nucode::ble::DeviceInformationService BLEDeviceInformation;
nucode::ble::HidKeyboard BLEKeyboard;

#endif
