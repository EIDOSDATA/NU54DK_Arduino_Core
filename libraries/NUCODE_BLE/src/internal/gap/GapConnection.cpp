/** @file @brief GAP Connection의 callback과 public API 구현입니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "GapInternal.h"
namespace nucode::ble::internal::gap
{
    namespace
    {
        /** @brief callback connection이 현재 session의 active link인지 검사합니다. */
        bool activeConnectionGeneration(struct bt_conn *connection,
                                        std::uint32_t &generation) noexcept
        {
            k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
            const bool matches = gapState().active_connection == connection &&
                                 gapState().active_connection_generation != 0U;
            generation = matches ? gapState().active_connection_generation : 0U;
            k_spin_unlock(&gapState().connection_lock, key);
            return matches && generation == static_cast<std::uint32_t>(
                                                atomic_get(&gapState().device_session_generation));
        }
        /** @brief MTU 교환 완료를 main-thread event로 변환합니다. */
        void mtuExchangeCompleted(struct bt_conn *connection, std::uint8_t error,
                                  struct bt_gatt_exchange_params *parameters) noexcept
        {
            ARG_UNUSED(parameters);
            std::uint32_t generation = 0U;
            if (!activeConnectionGeneration(connection, generation))
            {
                return;
            }
            atomic_set(&gapState().mtu_exchange_active, 0);
            if (error != 0U)
            {
                nucode::ble::internal::recordError(BLEError::driver_error, -static_cast<int>(error),
                                                   true);
                return;
            }
            queueEvent(BLEEvent::mtu_changed, generation);
        }

        /** @brief GATT layer가 관찰한 ATT MTU 변경을 main thread에 전달합니다. */
        void mtuUpdated(struct bt_conn *connection, std::uint16_t transmit,
                        std::uint16_t receive) noexcept
        {
            ARG_UNUSED(transmit);
            ARG_UNUSED(receive);
            std::uint32_t generation = 0U;
            if (atomic_get(&gapState().device_initialized) != 0 &&
                activeConnectionGeneration(connection, generation))
            {
                queueEvent(BLEEvent::mtu_changed, generation);
            }
        }

        struct bt_gatt_cb gatt_callbacks = {
            .att_mtu_updated = mtuUpdated,
        };

        /** @brief generic BLE incoming/outgoing connection을 단일 slot에 연결합니다. */
        void connectionEstablished(struct bt_conn *connection, std::uint8_t error) noexcept
        {
            bool owns_connection = false;
            bool handles_current_attempt = false;
            struct bt_conn *release_connection = nullptr;
            std::uint32_t connection_generation = 0U;
            const std::uint32_t current_generation =
                static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation));
            k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
            if (gapState().pending_connection == connection)
            {
                handles_current_attempt =
                    gapState().pending_connection_generation == current_generation &&
                    atomic_get(&gapState().device_initialized) != 0;
                connection_generation = gapState().pending_connection_generation;
                if (error == 0U && handles_current_attempt &&
                    gapState().active_connection == nullptr)
                {
                    gapState().active_connection = gapState().pending_connection;
                    gapState().active_connection_generation =
                        gapState().pending_connection_generation;
                    gapState().pending_connection = nullptr;
                    gapState().pending_connection_generation = 0U;
                    owns_connection = true;
                }
                else
                {
                    release_connection = gapState().pending_connection;
                    gapState().pending_connection = nullptr;
                    gapState().pending_connection_generation = 0U;
                }
            }
            else if (error == 0U && atomic_get(&gapState().device_initialized) != 0 &&
                     atomic_get(&gapState().advertising_active) != 0 &&
                     gapState().active_connection == nullptr)
            {
                owns_connection = true;
                gapState().active_connection = bt_conn_ref(connection);
                gapState().active_connection_generation = current_generation;
                connection_generation = current_generation;
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

            if (!owns_connection && !(handles_current_attempt && error != 0U))
            {
                return;
            }
            atomic_set(&gapState().connection_connecting, 0);
            if (error != 0U)
            {
                atomic_set(&gapState().connection_active, 0);
                nucode::ble::internal::recordError(BLEError::driver_error, -static_cast<int>(error),
                                                   true);
                return;
            }

            if (atomic_get(&gapState().device_initialized) == 0 ||
                connection_generation !=
                    static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation)))
            {
                atomic_set(&gapState().connection_active, 0);
                static_cast<void>(bt_conn_disconnect(connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
                return;
            }
            atomic_set(&gapState().advertising_active, 0);
            atomic_set(&gapState().connection_active, 1);
            if (atomic_get(&gapState().device_initialized) == 0 ||
                connection_generation !=
                    static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation)))
            {
                atomic_set(&gapState().connection_active, 0);
                static_cast<void>(bt_conn_disconnect(connection, BT_HCI_ERR_REMOTE_USER_TERM_CONN));
                return;
            }
            nucode::ble::internal::gattConnected(connection, connection_generation);
            nucode::ble::internal::securityConnected(connection);
            queueEvent(BLEEvent::connected, connection_generation);
        }

        /** @brief disconnect에서 모든 generic handle/reference를 먼저 무효화합니다. */
        void connectionDisconnected(struct bt_conn *connection, std::uint8_t reason) noexcept
        {
            ARG_UNUSED(reason);
            bool owns_connection = false;
            std::uint32_t connection_generation = 0U;
            k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
            if (gapState().active_connection == connection)
            {
                owns_connection = true;
                connection_generation = gapState().active_connection_generation;
                gapState().active_connection = nullptr;
                gapState().active_connection_generation = 0U;
            }
            k_spin_unlock(&gapState().connection_lock, key);
            if (!owns_connection)
            {
                return;
            }

            nucode::ble::internal::gattDisconnected(connection, connection_generation);
            nucode::ble::internal::securityDisconnected(connection);
            bt_conn_unref(connection);
            atomic_set(&gapState().connection_active, 0);
            atomic_set(&gapState().connection_connecting, 0);
            atomic_set(&gapState().mtu_exchange_active, 0);
            if (atomic_get(&gapState().device_initialized) != 0)
            {
                queueEvent(BLEEvent::disconnected, connection_generation);
            }
        }

        /** @brief LE connection parameter update를 main-thread event로 변환합니다. */
        void parametersUpdated(struct bt_conn *connection, std::uint16_t interval,
                               std::uint16_t latency, std::uint16_t timeout) noexcept
        {
            ARG_UNUSED(interval);
            ARG_UNUSED(latency);
            ARG_UNUSED(timeout);
            std::uint32_t generation = 0U;
            if (atomic_get(&gapState().device_initialized) != 0 &&
                activeConnectionGeneration(connection, generation))
            {
                queueEvent(BLEEvent::parameters_changed, generation);
            }
        }

#if defined(CONFIG_BT_USER_PHY_UPDATE)
        /** @brief LE PHY update를 main-thread event로 변환합니다. */
        void phyUpdated(struct bt_conn *connection,
                        struct bt_conn_le_phy_info *information) noexcept
        {
            ARG_UNUSED(information);
            std::uint32_t generation = 0U;
            if (atomic_get(&gapState().device_initialized) != 0 &&
                activeConnectionGeneration(connection, generation))
            {
                queueEvent(BLEEvent::phy_changed, generation);
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
#if defined(CONFIG_BT_SMP) || defined(CONFIG_BT_CLASSIC)
            .security_changed = linkSecurityChanged,
#endif
#if defined(CONFIG_BT_USER_PHY_UPDATE)
            .le_phy_updated = phyUpdated,
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
    /** @brief active connection에 race-safe 임시 reference를 얻습니다. */
    struct bt_conn *referenceActiveConnection() noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        struct bt_conn *connection = gapState().active_connection;
        if (connection != nullptr)
        {
            bt_conn_ref(connection);
        }
        k_spin_unlock(&gapState().connection_lock, key);
        return connection;
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
        if (connecting() || connected())
        {
            internal::recordError(BLEError::already_started, -EALREADY, true);
            return false;
        }
        if (atomic_get(&gapState().advertising_active) != 0)
        {
            internal::recordError(BLEError::busy, -EBUSY, true);
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
        k_spinlock_key_t key = k_spin_lock(&gapState().connection_lock);
        gapState().pending_connection = connection;
        gapState().pending_connection_generation =
            static_cast<std::uint32_t>(atomic_get(&gapState().device_session_generation));
        gapState().last_peer_address = address;
        k_spin_unlock(&gapState().connection_lock, key);
        atomic_set(&gapState().connection_connecting, 1);
        queueEvent(BLEEvent::connecting);
        return true;
    }

    bool Connection::disconnect() noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceActiveConnection();
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
        if (!gapState().last_peer_address.valid())
        {
            internal::recordError(BLEError::wrong_state, -ENOENT, true);
            return false;
        }
        return connect(gapState().last_peer_address);
    }

    bool Connection::connecting() const noexcept
    {
        return atomic_get(&gapState().connection_connecting) != 0;
    }

    bool Connection::connected() const noexcept
    {
        return atomic_get(&gapState().connection_active) != 0;
    }

    BLEAddress Connection::peerAddress() const noexcept
    {
        return gapState().last_peer_address;
    }

    std::size_t Connection::mtu() const noexcept
    {
        struct bt_conn *connection = referenceActiveConnection();
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
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceActiveConnection();
        if (connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        if (!atomic_cas(&gapState().mtu_exchange_active, 0, 1))
        {
            bt_conn_unref(connection);
            internal::recordError(BLEError::busy, -EBUSY, true);
            return false;
        }
        gapState().mtu_exchange_parameters.func = mtuExchangeCompleted;
        const int result = bt_gatt_exchange_mtu(connection, &gapState().mtu_exchange_parameters);
        bt_conn_unref(connection);
        if (result < 0)
        {
            atomic_set(&gapState().mtu_exchange_active, 0);
            internal::recordError(result == -EALREADY ? BLEError::already_started
                                                      : BLEError::driver_error,
                                  result, true);
            return false;
        }
        return true;
    }

    BLEPhy Connection::phy() const noexcept
    {
#if defined(CONFIG_BT_USER_PHY_UPDATE)
        struct bt_conn *connection = referenceActiveConnection();
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
        return BLEPhy::unknown;
#endif
    }

    bool Connection::requestPhy(bool allow_2m, bool allow_coded) noexcept
    {
#if defined(CONFIG_BT_USER_PHY_UPDATE)
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceActiveConnection();
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
        ARG_UNUSED(allow_2m);
        ARG_UNUSED(allow_coded);
        internal::recordError(BLEError::unsupported, -ENOTSUP, true);
        return false;
#endif
    }

    bool Connection::txPower(std::int8_t &dbm) const noexcept
    {
        if (!requireThreadContext())
        {
            return false;
        }
        struct bt_conn *connection = referenceActiveConnection();
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
        struct bt_conn *connection = referenceActiveConnection();
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

} // namespace nucode::ble
#endif
