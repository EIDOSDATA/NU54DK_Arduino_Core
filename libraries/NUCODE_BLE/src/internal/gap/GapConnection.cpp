/** @file @brief GAP Connection의 고정 2-slot callback과 public API 구현입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "GapInternal.h"
namespace nucode::ble::internal::gap
{
    namespace
    {
        /** @brief 0을 건너뛰는 image 수명 connection generation을 발급합니다. */
        std::uint32_t nextConnectionGeneration() noexcept
        {
            std::uint32_t generation =
                static_cast<std::uint32_t>(atomic_inc(&gapState().next_connection_generation)) +
                1U;
            if (generation == 0U)
            {
                generation = static_cast<std::uint32_t>(
                                 atomic_inc(&gapState().next_connection_generation)) +
                             1U;
            }
            return generation;
        }

        /** @brief slot index와 generation을 불투명 public handle로 결합합니다. */
        BLEConnectionHandle makeHandle(std::size_t slot, std::uint32_t generation) noexcept
        {
            return BLEConnectionHandleAccess::make(slot, generation);
        }

        /** @brief handle의 slot 범위와 generation을 lock 안에서 검증합니다. */
        bool matchesSlotLocked(BLEConnectionHandle handle, std::size_t &slot_index,
                               bool allow_pending) noexcept
        {
            if (!handle.valid())
            {
                return false;
            }
            slot_index = BLEConnectionHandleAccess::slot(handle);
            if (slot_index >= maximum_connection_slots)
            {
                return false;
            }
            const ConnectionSlot &slot = gapState().connection_slots[slot_index];
            return slot.generation == BLEConnectionHandleAccess::generation(handle) &&
                   (slot.active != nullptr || (allow_pending && slot.pending != nullptr));
        }

        /** @brief aggregate legacy 상태를 두 slot의 현재 값으로 갱신합니다. */
        void refreshConnectionFlags() noexcept
        {
            bool active = false;
            bool connecting = false;
            k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
            for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
            {
                active = active || gapState().connection_slots[index].active != nullptr;
                connecting = connecting || gapState().connection_slots[index].pending != nullptr;
            }
            k_spin_unlock(&gapState().connection_lock, key);
            atomic_set(&gapState().connection_active, active ? 1 : 0);
            atomic_set(&gapState().connection_connecting, connecting ? 1 : 0);
        }

        /** @brief callback connection을 현재 slot handle과 역할로 변환합니다. */
        bool activeConnectionHandle(struct bt_conn *connection, BLEConnectionHandle &handle,
                                    BLELinkRole &role,
                                    std::uint32_t &device_generation) noexcept
        {
            bool found = false;
            k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
            for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
            {
                const ConnectionSlot &slot = gapState().connection_slots[index];
                if (slot.active == connection && slot.generation != 0U)
                {
                    handle = makeHandle(index, slot.generation);
                    role = slot.role;
                    device_generation = slot.device_generation;
                    found = true;
                    break;
                }
            }
            k_spin_unlock(&gapState().connection_lock, key);
            return found && device_generation == static_cast<std::uint32_t>(
                                                     atomic_get(&gapState().device_session_generation));
        }

        /** @brief 기존 API가 사용할 central 우선, peripheral 차선 handle을 반환합니다. */
        BLEConnectionHandle legacyHandle() noexcept
        {
            BLEConnectionHandle handle;
            k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
            for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
            {
                const ConnectionSlot &slot = gapState().connection_slots[index];
                if (slot.active != nullptr && slot.generation != 0U)
                {
                    handle = makeHandle(index, slot.generation);
                    break;
                }
            }
            k_spin_unlock(&gapState().connection_lock, key);
            return handle;
        }

        /** @brief 연결 설정에 사용된 주소가 resolvable private address인지 확인합니다. */
        bool isResolvablePrivateAddress(const bt_addr_le_t *address) noexcept
        {
            return address != nullptr && address->type == BT_ADDR_LE_RANDOM &&
                   (address->a.val[5] & 0xc0U) == 0x40U;
        }

        /** @brief 성공한 연결의 controller 역할이 지원 범위인지 확인합니다. */
        bool connectionRole(struct bt_conn *connection, std::uint8_t &role) noexcept
        {
            struct bt_conn_info information = {};
            if (bt_conn_get_info(connection, &information) < 0 ||
                information.type != BT_CONN_TYPE_LE ||
                (information.role != BT_CONN_ROLE_CENTRAL &&
                 information.role != BT_CONN_ROLE_PERIPHERAL))
            {
                return false;
            }
            role = information.role;
            return true;
        }

        /** @brief stack의 identity와 실제 연결 주소를 callback 밖 값으로 복사합니다. */
        void connectionAddresses(struct bt_conn *connection, BLEAddress &identity,
                                 BLEAddress &connection_address,
                                 bool &identity_resolved) noexcept
        {
            const bt_addr_le_t *const fallback = bt_conn_get_dst(connection);
            identity = fallback == nullptr ? BLEAddress{} : fromZephyrAddress(*fallback);
            connection_address = identity;
            identity_resolved = !isResolvablePrivateAddress(fallback);

            struct bt_conn_info information = {};
            if (bt_conn_get_info(connection, &information) < 0 ||
                information.type != BT_CONN_TYPE_LE)
            {
                return;
            }
            if (information.le.remote != nullptr)
            {
                connection_address = fromZephyrAddress(*information.le.remote);
            }
            if (information.le.dst != nullptr)
            {
                identity = fromZephyrAddress(*information.le.dst);
            }
            identity_resolved = !isResolvablePrivateAddress(information.le.remote) ||
                                (information.le.dst != nullptr &&
                                 information.le.remote != nullptr &&
                                 (information.le.dst->type != information.le.remote->type ||
                                  ::memcmp(information.le.dst->a.val,
                                           information.le.remote->a.val,
                                           sizeof(information.le.dst->a.val)) != 0));
        }

        /** @brief legacy 또는 현재 connectable extended set이 incoming link를 기다리는지 확인합니다. */
        bool acceptsIncomingConnection() noexcept
        {
            if (atomic_get(&gapState().advertising_active) != 0)
            {
                return true;
            }
            bool accepts = false;
            k_spinlock_key_t key = k_spin_lock(&gapState().configuration_lock);
            const ExtendedAdvertisingContext &context = gapState().extended_advertising;
            accepts = context.instance != nullptr && context.connectable &&
                      atomic_get(&context.active) != 0;
            k_spin_unlock(&gapState().configuration_lock, key);
            return accepts;
        }

        /** @brief MTU callback parameter가 소유한 고정 요청 context를 찾습니다. */
        MtuExchangeContext *findMtuContext(struct bt_gatt_exchange_params *parameters) noexcept
        {
            for (std::size_t index = 0U; index < maximum_mtu_exchange_contexts; ++index)
            {
                MtuExchangeContext &context = gapState().mtu_exchange_contexts[index];
                if (&context.parameters == parameters)
                {
                    return &context;
                }
            }
            return nullptr;
        }

        /** @brief MTU 교환 완료를 exact generation의 main-thread event로 변환합니다. */
        void mtuExchangeCompleted(struct bt_conn *connection, std::uint8_t error,
                                  struct bt_gatt_exchange_params *parameters) noexcept
        {
            MtuExchangeContext *context = findMtuContext(parameters);
            if (context == nullptr || !atomic_cas(&context->active, 1, 0))
            {
                return;
            }
            const BLEConnectionHandle handle = context->connection;
            context->connection = BLEConnectionHandle{};
            struct bt_conn *current = referenceConnection(handle);
            if (current == nullptr)
            {
                return;
            }
            const bool matches = current == connection;
            bt_conn_unref(current);
            if (!matches)
            {
                return;
            }
            const BLELinkRole role = BLEConnection.role(handle);
            if (error != 0U)
            {
                nucode::ble::internal::recordError(BLEError::driver_error, -static_cast<int>(error),
                                                   true);
                return;
            }
            queueEvent(BLEEvent::mtu_changed, handle, role);
        }

        /** @brief GATT layer가 관찰한 ATT MTU 변경을 exact link event로 전달합니다. */
        void mtuUpdated(struct bt_conn *connection, std::uint16_t transmit,
                        std::uint16_t receive) noexcept
        {
            ARG_UNUSED(transmit);
            ARG_UNUSED(receive);
            BLEConnectionHandle handle;
            BLELinkRole role = BLELinkRole::none;
            std::uint32_t device_generation = 0U;
            if (atomic_get(&gapState().device_initialized) != 0 &&
                activeConnectionHandle(connection, handle, role, device_generation))
            {
                queueEvent(BLEEvent::mtu_changed, handle, role, device_generation);
            }
        }

        struct bt_gatt_cb gatt_callbacks = {
            .att_mtu_updated = mtuUpdated,
        };

        /** @brief incoming/outgoing connection을 역할 고정 slot에 연결합니다. */
        void connectionEstablished(struct bt_conn *connection, std::uint8_t error) noexcept
        {
            bool owns_connection = false;
            bool handles_current_attempt = false;
            bool reject_connection = false;
            bool duplicate_connection = false;
            struct bt_conn *release_connection = nullptr;
            BLEConnectionHandle handle;
            BLELinkRole role = BLELinkRole::none;
            std::uint8_t native_role = 0xffU;
            bool native_role_valid = false;
            std::uint32_t device_generation = 0U;
            const std::uint32_t current_device_generation = static_cast<std::uint32_t>(
                atomic_get(&gapState().device_session_generation));
            const bt_addr_le_t *const peer = bt_conn_get_dst(connection);
            const BLEAddress peer_address =
                peer == nullptr ? BLEAddress{} : fromZephyrAddress(*peer);
            BLEAddress identity_address = peer_address;
            BLEAddress connection_address = peer_address;
            bool identity_resolved = true;
            if (error == 0U)
            {
                native_role_valid = connectionRole(connection, native_role);
                connectionAddresses(connection, identity_address, connection_address,
                                    identity_resolved);
            }

            k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
            ConnectionSlot &central = gapState().connection_slots[central_connection_slot];
            for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
            {
                if (gapState().connection_slots[index].active == connection)
                {
                    duplicate_connection = true;
                    break;
                }
            }
            if (duplicate_connection)
            {
                k_spin_unlock(&gapState().connection_lock, key);
                return;
            }
            if (central.pending == connection)
            {
                handles_current_attempt =
                    central.device_generation == current_device_generation &&
                    atomic_get(&gapState().device_initialized) != 0;
                handle = makeHandle(central_connection_slot, central.generation);
                role = central.role;
                device_generation = central.device_generation;
                if (error == 0U && handles_current_attempt && central.active == nullptr &&
                    native_role_valid && native_role == BT_CONN_ROLE_CENTRAL)
                {
                    central.active = central.pending;
                    central.pending = nullptr;
                    central.peer_address = identity_address;
                    central.connection_address = connection_address;
                    central.identity_resolved = identity_resolved;
                    owns_connection = true;
                }
                else
                {
                    release_connection = central.pending;
                    central.pending = nullptr;
                    central.generation = 0U;
                    central.device_generation = 0U;
                    central.peer_address = BLEAddress{};
                    central.connection_address = BLEAddress{};
                    central.identity_resolved = false;
                }
            }
            else if (error == 0U)
            {
                if (native_role_valid && native_role == BT_CONN_ROLE_PERIPHERAL &&
                    atomic_get(&gapState().device_initialized) != 0 &&
                    acceptsIncomingConnection())
                {
                    ConnectionSlot &peripheral =
                        gapState().connection_slots[peripheral_connection_slot];
                    if (peripheral.active == nullptr && peripheral.pending == nullptr)
                    {
                        peripheral.generation = nextConnectionGeneration();
                        peripheral.device_generation = current_device_generation;
                        peripheral.peer_address = identity_address;
                        peripheral.connection_address = connection_address;
                        peripheral.identity_resolved = identity_resolved;
                        peripheral.active = bt_conn_ref(connection);
                        handle = makeHandle(peripheral_connection_slot, peripheral.generation);
                        role = peripheral.role;
                        device_generation = peripheral.device_generation;
                        owns_connection = true;
                    }
                    else
                    {
                        reject_connection = true;
                    }
                }
                else
                {
                    reject_connection = true;
                }
            }
            k_spin_unlock(&gapState().connection_lock, key);

            if (release_connection != nullptr)
            {
                if (error == 0U)
                {
                    static_cast<void>(
                        bt_conn_disconnect(release_connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
                }
                bt_conn_unref(release_connection);
            }
            if (reject_connection)
            {
                static_cast<void>(bt_conn_disconnect(connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            }
            refreshConnectionFlags();

            if (!owns_connection && !(handles_current_attempt && error != 0U))
            {
                return;
            }
            if (error != 0U)
            {
                nucode::ble::internal::recordError(BLEError::driver_error, -static_cast<int>(error),
                                                   true);
                return;
            }
            if (atomic_get(&gapState().device_initialized) == 0 ||
                device_generation != static_cast<std::uint32_t>(
                                         atomic_get(&gapState().device_session_generation)))
            {
                static_cast<void>(bt_conn_disconnect(connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
                return;
            }
            if (role == BLELinkRole::peripheral)
            {
                atomic_set(&gapState().advertising_active, 0);
            }
            if (role == BLELinkRole::central)
            {
                nucode::ble::internal::gattConnected(
                    connection, BLEConnectionHandleAccess::generation(handle));
            }
            nucode::ble::internal::securityConnected(connection);
            queueEvent(BLEEvent::connected, handle, role, device_generation);
        }

        /** @brief disconnect에서 exact slot handle과 reference를 먼저 무효화합니다. */
        void connectionDisconnected(struct bt_conn *connection, std::uint8_t reason) noexcept
        {
            ARG_UNUSED(reason);
            bool owns_connection = false;
            BLEConnectionHandle handle;
            BLELinkRole role = BLELinkRole::none;
            std::uint32_t device_generation = 0U;
            k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
            for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
            {
                ConnectionSlot &slot = gapState().connection_slots[index];
                if (slot.active == connection)
                {
                    owns_connection = true;
                    handle = makeHandle(index, slot.generation);
                    role = slot.role;
                    device_generation = slot.device_generation;
                    slot.active = nullptr;
                    slot.generation = 0U;
                    slot.device_generation = 0U;
                    slot.peer_address = BLEAddress{};
                    slot.connection_address = BLEAddress{};
                    slot.identity_resolved = false;
                    break;
                }
            }
            k_spin_unlock(&gapState().connection_lock, key);
            if (!owns_connection)
            {
                return;
            }

            if (role == BLELinkRole::central)
            {
                nucode::ble::internal::gattDisconnected(
                    connection, BLEConnectionHandleAccess::generation(handle));
            }
            nucode::ble::internal::securityDisconnected(connection);
            bt_conn_unref(connection);
            refreshConnectionFlags();
            if (atomic_get(&gapState().device_initialized) != 0)
            {
                queueEvent(BLEEvent::disconnected, handle, role, device_generation);
            }
        }

        /** @brief LE connection parameter update를 exact link event로 변환합니다. */
        void parametersUpdated(struct bt_conn *connection, std::uint16_t interval,
                               std::uint16_t latency, std::uint16_t timeout) noexcept
        {
            ARG_UNUSED(interval);
            ARG_UNUSED(latency);
            ARG_UNUSED(timeout);
            BLEConnectionHandle handle;
            BLELinkRole role = BLELinkRole::none;
            std::uint32_t device_generation = 0U;
            if (atomic_get(&gapState().device_initialized) != 0 &&
                activeConnectionHandle(connection, handle, role, device_generation))
            {
                queueEvent(BLEEvent::parameters_changed, handle, role, device_generation);
            }
        }

#if defined(CONFIG_BT_USER_PHY_UPDATE)
        /** @brief LE PHY update를 exact link event로 변환합니다. */
        void phyUpdated(struct bt_conn *connection,
                        struct bt_conn_le_phy_info *information) noexcept
        {
            ARG_UNUSED(information);
            BLEConnectionHandle handle;
            BLELinkRole role = BLELinkRole::none;
            std::uint32_t device_generation = 0U;
            if (atomic_get(&gapState().device_initialized) != 0 &&
                activeConnectionHandle(connection, handle, role, device_generation))
            {
                queueEvent(BLEEvent::phy_changed, handle, role, device_generation);
            }
        }
#endif

#if defined(CONFIG_BT_SMP)
        /** @brief RPA에 대응하는 identity를 exact active link slot에 반영합니다. */
        void identityResolved(struct bt_conn *connection, const bt_addr_le_t *rpa,
                              const bt_addr_le_t *identity) noexcept
        {
            if (identity == nullptr || rpa == nullptr)
            {
                return;
            }
            BLEConnectionHandle handle;
            BLELinkRole role = BLELinkRole::none;
            std::uint32_t device_generation = 0U;
            bool found = false;
            k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
            for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
            {
                ConnectionSlot &slot = gapState().connection_slots[index];
                if (slot.active == connection && slot.generation != 0U)
                {
                    slot.connection_address = fromZephyrAddress(*rpa);
                    slot.peer_address = fromZephyrAddress(*identity);
                    slot.identity_resolved = true;
                    handle = makeHandle(index, slot.generation);
                    role = slot.role;
                    device_generation = slot.device_generation;
                    found = true;
                    break;
                }
            }
            k_spin_unlock(&gapState().connection_lock, key);
            if (found && atomic_get(&gapState().device_initialized) != 0 &&
                device_generation == static_cast<std::uint32_t>(
                                         atomic_get(&gapState().device_session_generation)))
            {
                queueEvent(BLEEvent::identity_resolved, handle, role, device_generation);
            }
        }
#endif

#if defined(CONFIG_BT_REMOTE_INFO)
        /** @brief remote feature/version 준비 callback을 exact link event로 변환합니다. */
        void remoteInformationAvailable(struct bt_conn *connection,
                                        struct bt_conn_remote_info *information) noexcept
        {
            ARG_UNUSED(information);
            BLEConnectionHandle handle;
            BLELinkRole role = BLELinkRole::none;
            std::uint32_t device_generation = 0U;
            if (atomic_get(&gapState().device_initialized) != 0 &&
                activeConnectionHandle(connection, handle, role, device_generation))
            {
                queueEvent(BLEEvent::remote_information_available, handle, role,
                           device_generation);
            }
        }
#endif

#if defined(CONFIG_BT_USER_DATA_LEN_UPDATE)
        /** @brief Data Length 변경 callback을 exact link event로 변환합니다. */
        void dataLengthUpdated(struct bt_conn *connection,
                               struct bt_conn_le_data_len_info *information) noexcept
        {
            ARG_UNUSED(information);
            BLEConnectionHandle handle;
            BLELinkRole role = BLELinkRole::none;
            std::uint32_t device_generation = 0U;
            if (atomic_get(&gapState().device_initialized) != 0 &&
                activeConnectionHandle(connection, handle, role, device_generation))
            {
                queueEvent(BLEEvent::data_length_changed, handle, role, device_generation);
            }
        }
#endif

#if defined(CONFIG_BT_SMP) || defined(CONFIG_BT_CLASSIC)
        /** @brief security 변경을 M21의 bounded event 계층으로 전달합니다. */
        void linkSecurityChanged(struct bt_conn *connection, bt_security_t level,
                                 enum bt_security_err error) noexcept
        {
            nucode::ble::internal::securityChanged(connection, level, error);
        }
#endif

        BT_CONN_CB_DEFINE(nucode_ble_gap_connection_callbacks) = {
            .connected = connectionEstablished,
            .disconnected = connectionDisconnected,
            .le_param_updated = parametersUpdated,
#if defined(CONFIG_BT_SMP)
            .identity_resolved = identityResolved,
#endif
#if defined(CONFIG_BT_SMP) || defined(CONFIG_BT_CLASSIC)
            .security_changed = linkSecurityChanged,
#endif
#if defined(CONFIG_BT_REMOTE_INFO)
            .remote_info_available = remoteInformationAvailable,
#endif
#if defined(CONFIG_BT_USER_PHY_UPDATE)
            .le_phy_updated = phyUpdated,
#endif
#if defined(CONFIG_BT_USER_DATA_LEN_UPDATE)
            .le_data_len_updated = dataLengthUpdated,
#endif
        };

#if defined(CONFIG_BT_USER_PHY_UPDATE)
        /** @brief BLE PHY bit를 portable enum으로 변환합니다. */
        BLEPhy publicPhy(std::uint8_t phy) noexcept
        {
            if ((phy & BT_GAP_LE_PHY_2M) != 0U)
            {
                return BLEPhy::le_2m;
            }
            if ((phy & BT_GAP_LE_PHY_CODED) != 0U)
            {
                return BLEPhy::coded;
            }
            if ((phy & BT_GAP_LE_PHY_1M) != 0U)
            {
                return BLEPhy::le_1m;
            }
            return BLEPhy::unknown;
        }
#endif

    } // namespace

    struct bt_conn *referenceConnection(BLEConnectionHandle handle) noexcept
    {
        struct bt_conn *connection = nullptr;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        std::size_t slot_index = 0U;
        if (matchesSlotLocked(handle, slot_index, false))
        {
            connection = gapState().connection_slots[slot_index].active;
            bt_conn_ref(connection);
        }
        k_spin_unlock(&gapState().connection_lock, key);
        return connection;
    }

    struct bt_conn *referenceLegacyConnection() noexcept
    {
        return referenceConnection(legacyHandle());
    }

    bt_gatt_cb &gattCallbacks() noexcept
    {
        return gatt_callbacks;
    }
} // namespace nucode::ble::internal::gap
namespace nucode::ble
{
    using namespace internal::gap;

    bool Connection::connect(const BLEAddress &address) noexcept
    {
        BLEConnectionHandle ignored;
        return connect(address, ignored);
    }

    bool Connection::connect(const BLEAddress &address,
                             BLEConnectionHandle &connection_handle) noexcept
    {
        connection_handle = BLEConnectionHandle{};
        if (!requireThreadContext())
        {
            return false;
        }
        if (atomic_get(&gapState().device_initialized) == 0)
        {
            internal::recordError(BLEError::not_initialized, -EPERM, true);
            return false;
        }
        if (!address.valid())
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }

        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        const ConnectionSlot &central = gapState().connection_slots[central_connection_slot];
        const bool central_busy = central.active != nullptr || central.pending != nullptr;
        k_spin_unlock(&gapState().connection_lock, key);
        if (central_busy)
        {
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        if (atomic_get(&gapState().scanning_active) != 0 && !BLEScan.stop())
        {
            return false;
        }

        bt_addr_le_t peer = {};
        if (!toZephyrAddress(address, peer))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        struct bt_conn *connection = nullptr;
        const int result =
            bt_conn_le_create(&peer, BT_CONN_LE_CREATE_CONN, BT_LE_CONN_PARAM_DEFAULT, &connection);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }

        const std::uint32_t generation = nextConnectionGeneration();
        const std::uint32_t device_generation = static_cast<std::uint32_t>(
            atomic_get(&gapState().device_session_generation));
        key = k_spin_lock(&gapState().connection_lock);
        ConnectionSlot &slot = gapState().connection_slots[central_connection_slot];
        if (slot.active != nullptr || slot.pending != nullptr)
        {
            k_spin_unlock(&gapState().connection_lock, key);
            static_cast<void>(bt_conn_disconnect(connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
            bt_conn_unref(connection);
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        slot.pending = connection;
        slot.generation = generation;
        slot.device_generation = device_generation;
        slot.peer_address = address;
        slot.connection_address = address;
        slot.identity_resolved = address.type() != BLEAddress::Type::random_address ||
                                 (address.data()[5] & 0xc0U) != 0x40U;
        gapState().last_central_address = address;
        connection_handle = makeHandle(central_connection_slot, generation);
        k_spin_unlock(&gapState().connection_lock, key);
        refreshConnectionFlags();
        queueEvent(BLEEvent::connecting, connection_handle, BLELinkRole::central,
                   device_generation);
        return true;
    }

    bool Connection::disconnect() noexcept
    {
        return disconnect(legacyHandle());
    }

    bool Connection::disconnect(BLEConnectionHandle connection_handle) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const int result = bt_conn_disconnect(connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN);
        bt_conn_unref(connection);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool Connection::reconnect() noexcept
    {
        BLEConnectionHandle ignored;
        return reconnect(ignored);
    }

    bool Connection::reconnect(BLEConnectionHandle &connection_handle) noexcept
    {
        BLEAddress address;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        address = gapState().last_central_address;
        k_spin_unlock(&gapState().connection_lock, key);
        if (!address.valid())
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            connection_handle = BLEConnectionHandle{};
            return false;
        }
        return connect(address, connection_handle);
    }

    bool Connection::connecting() const noexcept
    {
        return atomic_get(&gapState().connection_connecting) != 0;
    }

    bool Connection::connecting(BLEConnectionHandle connection_handle) const noexcept
    {
        bool result = false;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        std::size_t slot_index = 0U;
        if (matchesSlotLocked(connection_handle, slot_index, true))
        {
            result = gapState().connection_slots[slot_index].pending != nullptr;
        }
        k_spin_unlock(&gapState().connection_lock, key);
        return result;
    }

    bool Connection::connected() const noexcept
    {
        return atomic_get(&gapState().connection_active) != 0;
    }

    bool Connection::connected(BLEConnectionHandle connection_handle) const noexcept
    {
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            return false;
        }
        bt_conn_unref(connection);
        return true;
    }

    std::size_t Connection::count() const noexcept
    {
        std::size_t count = 0U;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
        {
            if (gapState().connection_slots[index].active != nullptr)
            {
                ++count;
            }
        }
        k_spin_unlock(&gapState().connection_lock, key);
        return count;
    }

    BLEConnectionHandle Connection::handle(BLELinkRole requested_role) const noexcept
    {
        BLEConnectionHandle result;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        for (std::size_t index = 0U; index < maximum_connection_slots; ++index)
        {
            const ConnectionSlot &slot = gapState().connection_slots[index];
            if (slot.role == requested_role && slot.generation != 0U &&
                (slot.active != nullptr || slot.pending != nullptr))
            {
                result = makeHandle(index, slot.generation);
                break;
            }
        }
        k_spin_unlock(&gapState().connection_lock, key);
        return result;
    }

    BLELinkRole Connection::role(BLEConnectionHandle connection_handle) const noexcept
    {
        BLELinkRole result = BLELinkRole::none;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        std::size_t slot_index = 0U;
        if (matchesSlotLocked(connection_handle, slot_index, true))
        {
            result = gapState().connection_slots[slot_index].role;
        }
        k_spin_unlock(&gapState().connection_lock, key);
        return result;
    }

    BLEAddress Connection::peerAddress() const noexcept
    {
        const BLEConnectionHandle connection_handle = legacyHandle();
        if (connection_handle.valid())
        {
            return peerAddress(connection_handle);
        }
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        const BLEAddress address = gapState().last_central_address;
        k_spin_unlock(&gapState().connection_lock, key);
        return address;
    }

    BLEAddress Connection::peerAddress(BLEConnectionHandle connection_handle) const noexcept
    {
        BLEAddress address;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        std::size_t slot_index = 0U;
        if (matchesSlotLocked(connection_handle, slot_index, true))
        {
            address = gapState().connection_slots[slot_index].peer_address;
        }
        k_spin_unlock(&gapState().connection_lock, key);
        return address;
    }

    BLEAddress Connection::connectionAddress(BLEConnectionHandle connection_handle) const noexcept
    {
        BLEAddress address;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        std::size_t slot_index = 0U;
        if (matchesSlotLocked(connection_handle, slot_index, true))
        {
            address = gapState().connection_slots[slot_index].connection_address;
        }
        k_spin_unlock(&gapState().connection_lock, key);
        return address;
    }

    bool Connection::identityResolved(BLEConnectionHandle connection_handle) const noexcept
    {
        bool resolved = false;
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        std::size_t slot_index = 0U;
        if (matchesSlotLocked(connection_handle, slot_index, false))
        {
            resolved = gapState().connection_slots[slot_index].identity_resolved;
        }
        k_spin_unlock(&gapState().connection_lock, key);
        return resolved;
    }

    std::size_t Connection::mtu() const noexcept
    {
        return mtu(legacyHandle());
    }

    std::size_t Connection::mtu(BLEConnectionHandle connection_handle) const noexcept
    {
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            return 0U;
        }
        const std::size_t value = bt_gatt_get_mtu(connection);
        bt_conn_unref(connection);
        return value;
    }

    bool Connection::requestMtu() noexcept
    {
        return requestMtu(legacyHandle());
    }

    bool Connection::requestMtu(BLEConnectionHandle connection_handle) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        MtuExchangeContext *request = nullptr;
        for (std::size_t index = 0U; index < maximum_mtu_exchange_contexts; ++index)
        {
            MtuExchangeContext &candidate = gapState().mtu_exchange_contexts[index];
            if (atomic_cas(&candidate.active, 0, 1))
            {
                request = &candidate;
                break;
            }
        }
        if (request == nullptr)
        {
            bt_conn_unref(connection);
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        request->connection = connection_handle;
        request->parameters.func = mtuExchangeCompleted;
        const int result = bt_gatt_exchange_mtu(connection, &request->parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            request->connection = BLEConnectionHandle{};
            atomic_set(&request->active, 0);
            internal::recordError(result == -EALREADY ? BLEError::already_started
                                                      : BLEError::driver_error,
                                  result, true);
            return false;
        }
        return true;
    }

    BLEPhy Connection::phy() const noexcept
    {
        return phy(legacyHandle());
    }

    BLEPhy Connection::phy(BLEConnectionHandle connection_handle) const noexcept
    {
#if defined(CONFIG_BT_USER_PHY_UPDATE)
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            return BLEPhy::unknown;
        }
        struct bt_conn_info information = {};
        const int result = bt_conn_get_info(connection, &information);
        bt_conn_unref(connection);
        if (result < 0 || information.type != BT_CONN_TYPE_LE || information.le.phy == nullptr)
        {
            return BLEPhy::unknown;
        }
        return publicPhy(information.le.phy->tx_phy);
#else
        ARG_UNUSED(connection_handle);
        return BLEPhy::unknown;
#endif
    }

    bool Connection::requestPhy(bool allow_2m, bool allow_coded) noexcept
    {
        return requestPhy(legacyHandle(), allow_2m, allow_coded);
    }

    bool Connection::requestPhy(BLEConnectionHandle connection_handle, bool allow_2m,
                                bool allow_coded) noexcept
    {
#if defined(CONFIG_BT_USER_PHY_UPDATE)
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        std::uint8_t mask = BT_GAP_LE_PHY_1M;
        if (allow_2m)
        {
            mask |= BT_GAP_LE_PHY_2M;
        }
        if (allow_coded)
        {
            mask |= BT_GAP_LE_PHY_CODED;
        }
        const struct bt_conn_le_phy_param parameters = {
            .options = BT_CONN_LE_PHY_OPT_NONE,
            .pref_tx_phy = mask,
            .pref_rx_phy = mask,
        };
        const int result = bt_conn_le_phy_update(connection, &parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
#else
        ARG_UNUSED(connection_handle);
        ARG_UNUSED(allow_2m);
        ARG_UNUSED(allow_coded);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool Connection::txPower(std::int8_t &dbm) const noexcept
    {
        return txPower(legacyHandle(), dbm);
    }

    bool Connection::txPower(BLEConnectionHandle connection_handle, std::int8_t &dbm) const noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        struct bt_conn_le_tx_power power = {
            .phy = 0U,
            .current_level = 0,
            .max_level = 0,
        };
        const int result = bt_conn_le_get_tx_power_level(connection, &power);
        bt_conn_unref(connection);
        if (result < 0)
        {
            internal::recordError(
                result == -ENOTSUP ? BLEError::unsupported : BLEError::driver_error, result, true);
            return false;
        }
        dbm = power.current_level;
        return true;
    }

    bool Connection::requestParameters(std::uint16_t interval_min, std::uint16_t interval_max,
                                       std::uint16_t latency, std::uint16_t timeout) noexcept
    {
        return requestParameters(legacyHandle(), interval_min, interval_max, latency, timeout);
    }

    bool Connection::requestParameters(BLEConnectionHandle connection_handle,
                                       std::uint16_t interval_min, std::uint16_t interval_max,
                                       std::uint16_t latency, std::uint16_t timeout) noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        const std::uint64_t supervision_units = static_cast<std::uint64_t>(timeout) * 4U;
        const std::uint64_t connection_event_units =
            static_cast<std::uint64_t>(latency + 1U) * interval_max;
        if (interval_min < 6U || interval_max > 3200U || interval_min > interval_max ||
            latency > 499U || timeout < 10U || timeout > 3200U ||
            supervision_units <= connection_event_units)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const struct bt_le_conn_param parameters = {
            .interval_min = interval_min,
            .interval_max = interval_max,
            .latency = latency,
            .timeout = timeout,
        };
        const int result = bt_conn_le_param_update(connection, &parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
    }

    bool Connection::parameters(BLEConnectionHandle connection_handle,
                                BLEConnectionParameters &information) const noexcept
    {
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            return false;
        }
        struct bt_conn_info native_information = {};
        const int result = bt_conn_get_info(connection, &native_information);
        bt_conn_unref(connection);
        if (result < 0 || native_information.type != BT_CONN_TYPE_LE)
        {
            return false;
        }
        information.interval_us = native_information.le.interval_us;
        information.latency = native_information.le.latency;
        information.supervision_timeout = native_information.le.timeout;
        return true;
    }

    bool Connection::requestDataLength(BLEConnectionHandle connection_handle,
                                       std::uint16_t transmit_octets,
                                       std::uint16_t transmit_time_us) noexcept
    {
#if defined(CONFIG_BT_USER_DATA_LEN_UPDATE)
        if (!requireThreadContext())
        {
            return false;
        }
        if (transmit_octets < BT_GAP_DATA_LEN_DEFAULT ||
            transmit_octets > BT_GAP_DATA_LEN_MAX ||
            transmit_time_us < BT_GAP_DATA_TIME_DEFAULT ||
            transmit_time_us > BT_GAP_DATA_TIME_MAX)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const struct bt_conn_le_data_len_param parameters = {
            .tx_max_len = transmit_octets,
            .tx_max_time = transmit_time_us,
        };
        const int result = bt_conn_le_data_len_update(connection, &parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        return true;
#else
        ARG_UNUSED(connection_handle);
        ARG_UNUSED(transmit_octets);
        ARG_UNUSED(transmit_time_us);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool Connection::dataLength(BLEConnectionHandle connection_handle,
                                BLEDataLengthInfo &information) const noexcept
    {
#if defined(CONFIG_BT_USER_DATA_LEN_UPDATE)
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            return false;
        }
        struct bt_conn_info native_information = {};
        const int result = bt_conn_get_info(connection, &native_information);
        bt_conn_unref(connection);
        if (result < 0 || native_information.type != BT_CONN_TYPE_LE ||
            native_information.le.data_len == nullptr)
        {
            return false;
        }
        information.transmit_octets = native_information.le.data_len->tx_max_len;
        information.transmit_time_us = native_information.le.data_len->tx_max_time;
        information.receive_octets = native_information.le.data_len->rx_max_len;
        information.receive_time_us = native_information.le.data_len->rx_max_time;
        return true;
#else
        ARG_UNUSED(connection_handle);
        ARG_UNUSED(information);
        return false;
#endif
    }

    bool Connection::remoteInformation(BLEConnectionHandle connection_handle,
                                       BLERemoteInformation &information) const noexcept
    {
#if defined(CONFIG_BT_REMOTE_INFO)
        struct bt_conn *connection = referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            return false;
        }
        struct bt_conn_remote_info native_information = {};
        const int result = bt_conn_get_remote_info(connection, &native_information);
        bt_conn_unref(connection);
        if (result < 0 || native_information.type != BT_CONN_TYPE_LE ||
            native_information.le.features == nullptr)
        {
            return false;
        }
        information.version = native_information.version;
        information.manufacturer = native_information.manufacturer;
        information.subversion = native_information.subversion;
        ::memcpy(information.features, native_information.le.features,
                 sizeof(information.features));
        return true;
#else
        ARG_UNUSED(connection_handle);
        ARG_UNUSED(information);
        return false;
#endif
    }
} // namespace nucode::ble
#endif
