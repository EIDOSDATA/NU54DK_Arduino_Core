/** @file @brief Security pairing·bond·profile의 private 상태와 lifecycle 경계입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <NUCODE_BLE_Security.h>

#include <internal/NUCODE_BLE_Internal.h>
#include <internal/NUCODE_BLE_HidsBackend.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/kernel.h>
#include <zephyr/settings/settings.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace nucode::ble::internal::security
{
    inline constexpr std::size_t maximum_security_links = 2U;
    inline constexpr std::size_t maximum_bond_records = 4U;

    using nucode::ble::BondState;
    using nucode::ble::DeviceInformation;
    using nucode::ble::KeyboardReport;
    using nucode::ble::OobRole;
    using nucode::ble::PeerAddress;
    using nucode::ble::SecurityConfig;
    using nucode::ble::SecurityError;
    using nucode::ble::SecurityEvent;
    using nucode::ble::SecurityEventCallback;
    using nucode::ble::SecurityEventRecord;
    using nucode::ble::SecurityIoCapability;
    using nucode::ble::SecurityLevel;
    using nucode::ble::SecureConnectionsOobRecord;

    /** @brief 역할 하나가 소유하는 local·remote OOB material입니다. */
    struct OobSlot
    {
        OobRole role = OobRole::peripheral;
        SecureConnectionsOobRecord local = {};
        SecureConnectionsOobRecord remote = {};
        struct bt_le_oob_sc_data native_local = {};
        struct bt_le_oob_sc_data native_remote = {};
        bool local_valid = false;
        bool remote_valid = false;
    };

    /** @brief OOB 구현이 단일 소유하는 두 역할 고정 상태입니다. */
    struct OobState
    {
        struct k_spinlock lock;
        OobSlot slots[maximum_security_links] = {};
    };
    OobState &oobState() noexcept;

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
        BLEConnectionHandle handle = {};
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

    /** @brief 비밀 key material 없이 저장 record 검증값만 보존합니다. */
    struct BondMetadataSnapshot
    {
        PeerAddress peer = {};
        std::uint16_t database_revision = 0U;
        std::uint8_t key_size = 0U;
        std::uint8_t security_level = 0U;
        std::uint8_t flags = 0U;
        bool valid = false;
    };

    /** @brief 한 generation 연결이 소유하는 보안·bond snapshot입니다. */
    struct SecurityLinkState
    {
        BLEConnectionHandle handle = {};
        struct bt_conn *connection = nullptr;
        atomic_t paired_value = ATOMIC_INIT(0);
        atomic_t current_level_value =
            ATOMIC_INIT(static_cast<atomic_val_t>(SecurityLevel::none));
        atomic_t published_level_value = ATOMIC_INIT(0);
        atomic_t pending_security_event = ATOMIC_INIT(0);
        BondLifecycleState bond_lifecycle = {};
    };

    /** @brief 한 HIDS connection의 protocol mode와 등록 상태입니다. */
    struct HidConnectionState
    {
        struct bt_conn *connection = nullptr;
        bool registered = false;
        bool in_boot_mode = false;
    };

    /** @brief pairingState 구현이 단일 소유하는 고정 상태입니다. */
    struct PairingState
    {
        struct k_spinlock pending_lock;
        PendingState pending_states[maximum_security_links] = {};
        struct bt_conn_auth_cb authentication_callbacks = {};
        struct bt_conn_auth_info_cb authentication_info_callbacks = {};
    };
    PairingState &pairingState() noexcept;
    /** @brief bondStorage 구현이 단일 소유하는 고정 상태입니다. */
    struct BondStorage
    {
        atomic_t bond_state_value = ATOMIC_INIT(static_cast<atomic_val_t>(BondState::none));
        atomic_t startup_bond_snapshot_ready = ATOMIC_INIT(0);
        atomic_t migration_count = ATOMIC_INIT(0);
        atomic_t rejected_count = ATOMIC_INIT(0);
        struct k_spinlock bond_lock;
        struct k_spinlock startup_bond_lock;
        BondLifecycleState bond_lifecycle = {};
        BondMetadataSnapshot metadata[maximum_bond_records] = {};
        std::size_t startup_bond_count = 0U;
    };
    BondStorage &bondStorage() noexcept;
    /** @brief hidState 구현이 단일 소유하는 고정 상태입니다. */
    struct HidState
    {
        atomic_t hid_initialized = ATOMIC_INIT(0);
        atomic_t hid_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(SecurityError::none));
        atomic_t hid_driver_error_value = ATOMIC_INIT(0);
        struct k_spinlock hid_state_lock;
        HidConnectionState hid_connection_state = {};
    };
    HidState &hidState() noexcept;
    /** @brief securityState 구현이 단일 소유하는 고정 상태입니다. */
    struct SecurityState
    {
        atomic_t security_initialized = ATOMIC_INIT(0);
        atomic_t paired_value = ATOMIC_INIT(0);
        atomic_t current_level_value = ATOMIC_INIT(static_cast<atomic_val_t>(SecurityLevel::none));
        atomic_t published_level_value = ATOMIC_INIT(0);
        atomic_t pending_security_event = ATOMIC_INIT(0);
        atomic_t security_error_value = ATOMIC_INIT(static_cast<atomic_val_t>(SecurityError::none));
        atomic_t security_driver_error_value = ATOMIC_INIT(0);
        struct k_spinlock connection_lock;
        struct bt_conn *active_connection = nullptr;
        SecurityLinkState links[maximum_security_links] = {};
        SecurityConfig security_config = {};
        SecurityEventCallback security_event_callback = nullptr;
        void *security_event_context = nullptr;
    };
    SecurityState &securityState() noexcept;
    /** @brief Zephyr peer 주소를 공개 고정 길이 표현으로 복사합니다. */
    inline PeerAddress publicAddress(const bt_addr_le_t *address) noexcept
    {
        PeerAddress result = {};
        if (address != nullptr)
        {
            const bool public_type = address->type == BT_ADDR_LE_PUBLIC ||
                                     address->type == BT_ADDR_LE_PUBLIC_ID;
            result.type = public_type ? BT_ADDR_LE_PUBLIC : BT_ADDR_LE_RANDOM;
            ::memcpy(result.value, address->a.val, sizeof(result.value));
        }
        return result;
    }

    /** @brief 아직 identity로 해석되지 않은 random 주소가 RPA인지 확인합니다. */
    inline bool isResolvablePrivateAddress(const bt_addr_le_t *address) noexcept
    {
        return address != nullptr && address->type == BT_ADDR_LE_RANDOM &&
               (address->a.val[5] & 0xc0U) == 0x40U;
    }

    /** @brief 공개 peer 주소를 Zephyr identity 주소로 복사합니다. */
    inline bt_addr_le_t nativeAddress(const PeerAddress &address) noexcept
    {
        bt_addr_le_t result = {};
        result.type = address.type;
        ::memcpy(result.a.val, address.value, sizeof(address.value));
        return result;
    }

    /** @brief 내부 module 호출이며 공개 Arduino API가 아닙니다. */
    bool requireThreadContext() noexcept;
    void recordSecurityError(SecurityError error, int driver_error = 0) noexcept;
    void recordHidError(SecurityError error, int driver_error = 0) noexcept;
    BondState currentBondState() noexcept;
    BondState currentBondState(struct bt_conn *connection) noexcept;
    void setBondLifecycle(const bt_addr_le_t *peer, BondState state,
                          bool paired_this_connection) noexcept;
    void setBondLifecycle(struct bt_conn *connection, const bt_addr_le_t *peer, BondState state,
                          bool paired_this_connection) noexcept;
    bool bondLifecycleMatches(const bt_addr_le_t *peer) noexcept;
    bool bondLifecycleMatches(struct bt_conn *connection, const bt_addr_le_t *peer) noexcept;
    BondLifecycleState copyBondLifecycle() noexcept;
    BondLifecycleState copyBondLifecycle(struct bt_conn *connection) noexcept;
    void restoreBondLifecycle(const BondLifecycleState &snapshot) noexcept;
    bool isStartupBond(const bt_addr_le_t *peer) noexcept;
    void removeStartupBond(const bt_addr_le_t *peer) noexcept;
    SecurityEventRecord makeEvent(SecurityEvent event, struct bt_conn *connection,
                                  std::uint32_t passkey = 0U, std::uint8_t reason = 0U) noexcept;
    SecurityEventRecord makePeerEvent(SecurityEvent event, const bt_addr_le_t *peer,
                                      BondState state) noexcept;
    void queueEvent(const SecurityEventRecord &record) noexcept;
    void verifySecureBond(struct bt_conn *connection, bt_security_t level) noexcept;
    void queueSecurityChangedIfNew(struct bt_conn *connection, bt_security_t level) noexcept;
    bool synchronizeSatisfiedSecurity(struct bt_conn *connection,
                                      bt_security_t required_level) noexcept;
    struct bt_conn *referenceActiveConnection() noexcept;
    struct bt_conn *referenceConnection(BLEConnectionHandle handle) noexcept;
    bool isActiveConnection(struct bt_conn *connection) noexcept;
    bool isActiveConnection(BLEConnectionHandle handle, struct bt_conn *connection) noexcept;
    BLEConnectionHandle securityHandle(struct bt_conn *connection) noexcept;
    bool copyLinkState(BLEConnectionHandle handle, bool &paired, SecurityLevel &level,
                       BondState &bond_state) noexcept;
    void setLinkPaired(struct bt_conn *connection, bool paired) noexcept;
    void setLinkLevel(struct bt_conn *connection, bt_security_t level) noexcept;
    void captureStartupBonds() noexcept;
    bool bondMetadataValid(const bt_addr_le_t *peer) noexcept;
    bool bondMetadataValid(struct bt_conn *connection) noexcept;
    bool persistBondMetadata(struct bt_conn *connection) noexcept;
    void eraseBondMetadata(const bt_addr_le_t *peer) noexcept;
    void eraseAllBondMetadata() noexcept;
    void clearPending(struct bt_conn *matching_connection = nullptr) noexcept;
    void clearPending(BLEConnectionHandle handle) noexcept;
    bool setPending(struct bt_conn *connection, PendingResponse response, SecurityEvent event,
                    std::uint32_t passkey = 0U) noexcept;
    struct bt_conn *takePending(PendingResponse expected) noexcept;
    struct bt_conn *takePending(BLEConnectionHandle handle, PendingResponse expected) noexcept;
    struct bt_conn *takePending(BLEConnectionHandle handle) noexcept;
    void processPendingTimeout() noexcept;
    void resetOobState() noexcept;
    void oobDataRequest(struct bt_conn *connection, struct bt_conn_oob_info *information);
    void markPairingStarted(struct bt_conn *connection) noexcept;
    enum bt_security_err pairingAccept(struct bt_conn *connection,
                                       const struct bt_conn_pairing_feat *features);
    void passkeyDisplay(struct bt_conn *connection, unsigned int passkey);
    void passkeyEntry(struct bt_conn *connection);
    void passkeyConfirm(struct bt_conn *connection, unsigned int passkey);
    void pairingConfirm(struct bt_conn *connection);
    void authenticationCancelled(struct bt_conn *connection);
    void pairingComplete(struct bt_conn *connection, bool bonded);
    void pairingFailed(struct bt_conn *connection, enum bt_security_err reason);
    void bondDeleted(std::uint8_t identity, const bt_addr_le_t *peer);
    void prepareAuthenticationCallbacks(SecurityIoCapability capability) noexcept;
    bool releaseActiveConnection(struct bt_conn *matching) noexcept;
    void hidsProtocolModeChanged(bool boot_mode, struct bt_conn *connection);
    int attachHidsLocked(struct bt_conn *connection) noexcept;
    int detachHidsLocked(struct bt_conn *connection) noexcept;
    struct bt_conn *referenceHidConnection(bool *boot_mode) noexcept;
    k_msgq &securityEventQueue() noexcept;
    void lockHidApi() noexcept;
    void unlockHidApi() noexcept;
} // namespace nucode::ble::internal::security
