/**
 * @file NUCODE_BLE_Audio_ProfileRoles.cpp
 * @brief TMAP과 GMAP 역할 게시·검색 공개 API의 backend입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/audio/gmap.h>
extern "C"
{
#include <zephyr/bluetooth/audio/tmap.h>
}
#include <zephyr/kernel.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        constexpr std::uint16_t all_tmap_roles =
            static_cast<std::uint16_t>(TelephonyMediaRole::call_gateway) |
            static_cast<std::uint16_t>(TelephonyMediaRole::call_terminal) |
            static_cast<std::uint16_t>(TelephonyMediaRole::unicast_media_sender) |
            static_cast<std::uint16_t>(TelephonyMediaRole::unicast_media_receiver) |
            static_cast<std::uint16_t>(TelephonyMediaRole::broadcast_media_sender) |
            static_cast<std::uint16_t>(TelephonyMediaRole::broadcast_media_receiver);

        constexpr std::uint8_t all_gmap_roles =
            static_cast<std::uint8_t>(GamingAudioRole::unicast_game_gateway) |
            static_cast<std::uint8_t>(GamingAudioRole::unicast_game_terminal) |
            static_cast<std::uint8_t>(GamingAudioRole::broadcast_game_sender) |
            static_cast<std::uint8_t>(GamingAudioRole::broadcast_game_receiver);

        /** @brief native 오류를 안정된 공개 오류로 변환합니다. */
        Error publicError(int error) noexcept
        {
            if (error == 0)
            {
                return Error::none;
            }
            if ((error == -EINVAL) || (error == -ERANGE))
            {
                return Error::invalid_argument;
            }
            if (error == -EALREADY)
            {
                return Error::already_started;
            }
            if ((error == -EBUSY) || (error == -EINPROGRESS))
            {
                return Error::busy;
            }
            if (error == -ENOTCONN)
            {
                return Error::not_connected;
            }
            if (error == -ENOTSUP)
            {
                return Error::unsupported;
            }
            return Error::stack_error;
        }

        /** @brief 현재 image Kconfig가 요청한 TMAP 역할을 모두 제공하는지 검사합니다. */
        bool supportsTmapRoles(std::uint16_t roles) noexcept
        {
            if ((roles == 0U) || ((roles & ~all_tmap_roles) != 0U))
            {
                return false;
            }
            if (((roles & static_cast<std::uint16_t>(TelephonyMediaRole::call_gateway)) != 0U) &&
                !IS_ENABLED(CONFIG_BT_TMAP_CG_SUPPORTED))
            {
                return false;
            }
            if (((roles & static_cast<std::uint16_t>(TelephonyMediaRole::call_terminal)) != 0U) &&
                !IS_ENABLED(CONFIG_BT_TMAP_CT_SUPPORTED))
            {
                return false;
            }
            if (((roles & static_cast<std::uint16_t>(TelephonyMediaRole::unicast_media_sender)) !=
                 0U) &&
                !IS_ENABLED(CONFIG_BT_TMAP_UMS_SUPPORTED))
            {
                return false;
            }
            if (((roles & static_cast<std::uint16_t>(TelephonyMediaRole::unicast_media_receiver)) !=
                 0U) &&
                !IS_ENABLED(CONFIG_BT_TMAP_UMR_SUPPORTED))
            {
                return false;
            }
            if (((roles & static_cast<std::uint16_t>(TelephonyMediaRole::broadcast_media_sender)) !=
                 0U) &&
                !IS_ENABLED(CONFIG_BT_TMAP_BMS_SUPPORTED))
            {
                return false;
            }
            if (((roles & static_cast<std::uint16_t>(
                              TelephonyMediaRole::broadcast_media_receiver)) != 0U) &&
                !IS_ENABLED(CONFIG_BT_TMAP_BMR_SUPPORTED))
            {
                return false;
            }
            return true;
        }

        /** @brief 현재 image Kconfig가 요청한 GMAP 역할을 모두 제공하는지 검사합니다. */
        bool supportsGmapRoles(std::uint8_t roles) noexcept
        {
            if ((roles == 0U) || ((roles & ~all_gmap_roles) != 0U))
            {
                return false;
            }
            if (((roles & static_cast<std::uint8_t>(GamingAudioRole::unicast_game_gateway)) !=
                 0U) &&
                !IS_ENABLED(CONFIG_BT_GMAP_UGG_SUPPORTED))
            {
                return false;
            }
            if (((roles & static_cast<std::uint8_t>(GamingAudioRole::unicast_game_terminal)) !=
                 0U) &&
                !IS_ENABLED(CONFIG_BT_GMAP_UGT_SUPPORTED))
            {
                return false;
            }
            if (((roles & static_cast<std::uint8_t>(GamingAudioRole::broadcast_game_sender)) !=
                 0U) &&
                !IS_ENABLED(CONFIG_BT_GMAP_BGS_SUPPORTED))
            {
                return false;
            }
            if (((roles & static_cast<std::uint8_t>(GamingAudioRole::broadcast_game_receiver)) !=
                 0U) &&
                !IS_ENABLED(CONFIG_BT_GMAP_BGR_SUPPORTED))
            {
                return false;
            }
            return true;
        }

        /** @brief 역할에 없는 feature와 예약 bit를 upstream 등록 전에 거부합니다. */
        bool validGmapFeatures(std::uint8_t roles, const GamingAudioFeatures &features) noexcept
        {
            constexpr std::uint8_t gateway_mask =
                static_cast<std::uint8_t>(GamingGatewayFeature::multiplex) |
                static_cast<std::uint8_t>(GamingGatewayFeature::source_96_kbps) |
                static_cast<std::uint8_t>(GamingGatewayFeature::multiple_sinks);
            constexpr std::uint8_t terminal_mask =
                static_cast<std::uint8_t>(GamingTerminalFeature::source) |
                static_cast<std::uint8_t>(GamingTerminalFeature::source_80_kbps) |
                static_cast<std::uint8_t>(GamingTerminalFeature::sink) |
                static_cast<std::uint8_t>(GamingTerminalFeature::sink_64_kbps) |
                static_cast<std::uint8_t>(GamingTerminalFeature::multiplex) |
                static_cast<std::uint8_t>(GamingTerminalFeature::multiple_sinks) |
                static_cast<std::uint8_t>(GamingTerminalFeature::multiple_sources);
            constexpr std::uint8_t sender_mask =
                static_cast<std::uint8_t>(GamingBroadcastSenderFeature::source_96_kbps);
            constexpr std::uint8_t receiver_mask =
                static_cast<std::uint8_t>(GamingBroadcastReceiverFeature::multiple_sinks) |
                static_cast<std::uint8_t>(GamingBroadcastReceiverFeature::multiplex);

            const bool gateway =
                (roles & static_cast<std::uint8_t>(GamingAudioRole::unicast_game_gateway)) != 0U;
            const bool terminal =
                (roles & static_cast<std::uint8_t>(GamingAudioRole::unicast_game_terminal)) != 0U;
            const bool sender =
                (roles & static_cast<std::uint8_t>(GamingAudioRole::broadcast_game_sender)) != 0U;
            const bool receiver =
                (roles & static_cast<std::uint8_t>(GamingAudioRole::broadcast_game_receiver)) != 0U;
            return (features.unicast_gateway & ~gateway_mask) == 0U &&
                   (features.unicast_terminal & ~terminal_mask) == 0U &&
                   (features.broadcast_sender & ~sender_mask) == 0U &&
                   (features.broadcast_receiver & ~receiver_mask) == 0U &&
                   (gateway || (features.unicast_gateway == 0U)) &&
                   (terminal || (features.unicast_terminal == 0U)) &&
                   (sender || (features.broadcast_sender == 0U)) &&
                   (receiver || (features.broadcast_receiver == 0U));
        }

        /** @brief TMAP singleton service와 한 discovery session을 결합합니다. */
        struct TmapContext
        {
            const TelephonyMediaRoles *owner = nullptr;
            BLEConnectionHandle connection;
            std::uint16_t local_roles = 0U;
            std::uint16_t peer_roles = 0U;
            TelephonyMediaStage stage = TelephonyMediaStage::idle;
            Error last_error = Error::not_started;
            int native_code = 0;
            bool service_registered = false;
            struct k_spinlock lock;
        };

        TmapContext tmap_context;

        /** @brief GMAP singleton service와 한 discovery session을 결합합니다. */
        struct GmapContext
        {
            const GamingAudioRoles *owner = nullptr;
            BLEConnectionHandle connection;
            GamingAudioPeer peer;
            GamingAudioFeatures local_features;
            std::uint8_t local_roles = 0U;
            GamingAudioStage stage = GamingAudioStage::idle;
            Error last_error = Error::not_started;
            int native_code = 0;
            bool callbacks_registered = false;
            bool service_registered = false;
            struct k_spinlock lock;
        };

        GmapContext gmap_context;

        /** @brief TMAP callback을 exact public handle의 현재 검색에만 반영합니다. */
        void tmapDiscoveryComplete(enum bt_tmap_role roles, struct bt_conn *connection,
                                   int error) noexcept
        {
            const BLEConnectionHandle handle = internal::handleForActiveConnection(connection);
            k_spinlock_key_t key = k_spin_lock(&tmap_context.lock);
            if ((tmap_context.owner == nullptr) ||
                (tmap_context.stage != TelephonyMediaStage::discovering) || !handle.valid() ||
                (handle != tmap_context.connection))
            {
                k_spin_unlock(&tmap_context.lock, key);
                return;
            }
            tmap_context.native_code = error;
            tmap_context.last_error = publicError(error);
            if (error == 0)
            {
                tmap_context.peer_roles = static_cast<std::uint16_t>(roles);
                tmap_context.stage = TelephonyMediaStage::discovered;
            }
            else
            {
                tmap_context.peer_roles = 0U;
                tmap_context.stage = TelephonyMediaStage::failed;
            }
            k_spin_unlock(&tmap_context.lock, key);
        }

        const struct bt_tmap_cb tmap_callbacks = {
            .discovery_complete = tmapDiscoveryComplete,
        };

        /** @brief GMAP callback을 exact public handle의 현재 검색에만 반영합니다. */
        void gmapDiscoveryComplete(struct bt_conn *connection, int error, enum bt_gmap_role roles,
                                   struct bt_gmap_feat features) noexcept
        {
            const BLEConnectionHandle handle = internal::handleForActiveConnection(connection);
            k_spinlock_key_t key = k_spin_lock(&gmap_context.lock);
            if ((gmap_context.owner == nullptr) ||
                (gmap_context.stage != GamingAudioStage::discovering) || !handle.valid() ||
                (handle != gmap_context.connection))
            {
                k_spin_unlock(&gmap_context.lock, key);
                return;
            }
            gmap_context.native_code = error;
            gmap_context.last_error = publicError(error);
            if (error == 0)
            {
                gmap_context.peer.roles = static_cast<std::uint8_t>(roles);
                gmap_context.peer.features.unicast_gateway =
                    static_cast<std::uint8_t>(features.ugg_feat);
                gmap_context.peer.features.unicast_terminal =
                    static_cast<std::uint8_t>(features.ugt_feat);
                gmap_context.peer.features.broadcast_sender =
                    static_cast<std::uint8_t>(features.bgs_feat);
                gmap_context.peer.features.broadcast_receiver =
                    static_cast<std::uint8_t>(features.bgr_feat);
                gmap_context.stage = GamingAudioStage::discovered;
            }
            else
            {
                gmap_context.peer = {};
                gmap_context.stage = GamingAudioStage::failed;
            }
            k_spin_unlock(&gmap_context.lock, key);
        }

        const struct bt_gmap_cb gmap_callbacks = {
            .discover = gmapDiscoveryComplete,
        };

        /** @brief 공개 GMAP feature를 upstream 구조체로 변환합니다. */
        struct bt_gmap_feat nativeFeatures(const GamingAudioFeatures &features) noexcept
        {
            struct bt_gmap_feat native = {};
            native.ugg_feat = static_cast<enum bt_gmap_ugg_feat>(features.unicast_gateway);
            native.ugt_feat = static_cast<enum bt_gmap_ugt_feat>(features.unicast_terminal);
            native.bgs_feat = static_cast<enum bt_gmap_bgs_feat>(features.broadcast_sender);
            native.bgr_feat = static_cast<enum bt_gmap_bgr_feat>(features.broadcast_receiver);
            return native;
        }

        /** @brief 두 공개 GMAP feature 묶음의 byte 값을 비교합니다. */
        bool sameFeatures(const GamingAudioFeatures &left,
                          const GamingAudioFeatures &right) noexcept
        {
            return left.unicast_gateway == right.unicast_gateway &&
                   left.unicast_terminal == right.unicast_terminal &&
                   left.broadcast_sender == right.broadcast_sender &&
                   left.broadcast_receiver == right.broadcast_receiver;
        }
    } // namespace

    Error TelephonyMediaRoles::begin(TelephonyMediaRole roles) noexcept
    {
#if defined(CONFIG_BT_TMAP)
        const std::uint16_t role_bits = static_cast<std::uint16_t>(roles);
        if (!supportsTmapRoles(role_bits))
        {
            return Error::unsupported;
        }

        bool update_service = false;
        k_spinlock_key_t key = k_spin_lock(&tmap_context.lock);
        if (tmap_context.owner != nullptr)
        {
            const Error result = tmap_context.owner == this ? Error::already_started : Error::busy;
            k_spin_unlock(&tmap_context.lock, key);
            return result;
        }
        update_service = tmap_context.service_registered;
        k_spin_unlock(&tmap_context.lock, key);

        int result = 0;
        if (update_service)
        {
            bt_tmap_set_role(static_cast<enum bt_tmap_role>(role_bits));
        }
        else
        {
            result = bt_tmap_register(static_cast<enum bt_tmap_role>(role_bits));
        }
        if (result != 0)
        {
            return publicError(result);
        }

        key = k_spin_lock(&tmap_context.lock);
        if (tmap_context.owner != nullptr)
        {
            k_spin_unlock(&tmap_context.lock, key);
            return Error::busy;
        }
        tmap_context.owner = this;
        tmap_context.connection = {};
        tmap_context.local_roles = role_bits;
        tmap_context.peer_roles = 0U;
        tmap_context.stage = TelephonyMediaStage::ready;
        tmap_context.last_error = Error::none;
        tmap_context.native_code = 0;
        tmap_context.service_registered = true;
        k_spin_unlock(&tmap_context.lock, key);
        return Error::none;
#else
        static_cast<void>(roles);
        return Error::unsupported;
#endif
    }

    Error TelephonyMediaRoles::discover(const BLEConnectionHandle &connection) noexcept
    {
#if defined(CONFIG_BT_TMAP)
        if (!connection.valid() || !BLEConnection.connected(connection))
        {
            return Error::not_connected;
        }
        k_spinlock_key_t key = k_spin_lock(&tmap_context.lock);
        if (tmap_context.owner != this)
        {
            k_spin_unlock(&tmap_context.lock, key);
            return Error::not_started;
        }
        if (tmap_context.stage == TelephonyMediaStage::discovering)
        {
            k_spin_unlock(&tmap_context.lock, key);
            return Error::busy;
        }
        tmap_context.connection = connection;
        tmap_context.peer_roles = 0U;
        tmap_context.stage = TelephonyMediaStage::discovering;
        tmap_context.last_error = Error::none;
        tmap_context.native_code = 0;
        k_spin_unlock(&tmap_context.lock, key);

        struct bt_conn *native = internal::referenceConnection(connection);
        if (native == nullptr)
        {
            key = k_spin_lock(&tmap_context.lock);
            if ((tmap_context.owner == this) && (tmap_context.connection == connection))
            {
                tmap_context.stage = TelephonyMediaStage::failed;
                tmap_context.last_error = Error::not_connected;
                tmap_context.native_code = -ENOTCONN;
            }
            k_spin_unlock(&tmap_context.lock, key);
            return Error::not_connected;
        }
        const int result = bt_tmap_discover(native, &tmap_callbacks);
        bt_conn_unref(native);
        if (result != 0)
        {
            key = k_spin_lock(&tmap_context.lock);
            if ((tmap_context.owner == this) && (tmap_context.connection == connection) &&
                (tmap_context.stage == TelephonyMediaStage::discovering))
            {
                tmap_context.stage = TelephonyMediaStage::failed;
                tmap_context.last_error = publicError(result);
                tmap_context.native_code = result;
            }
            k_spin_unlock(&tmap_context.lock, key);
        }
        return publicError(result);
#else
        static_cast<void>(connection);
        return Error::unsupported;
#endif
    }

    void TelephonyMediaRoles::poll() noexcept
    {
#if defined(CONFIG_BT_TMAP)
        BLEConnectionHandle connection;
        k_spinlock_key_t key = k_spin_lock(&tmap_context.lock);
        if (tmap_context.owner == this)
        {
            connection = tmap_context.connection;
        }
        k_spin_unlock(&tmap_context.lock, key);
        if (connection.valid() && !BLEConnection.connected(connection))
        {
            key = k_spin_lock(&tmap_context.lock);
            if ((tmap_context.owner == this) && (tmap_context.connection == connection))
            {
                tmap_context.connection = {};
                tmap_context.peer_roles = 0U;
                tmap_context.stage = TelephonyMediaStage::ready;
                tmap_context.last_error = Error::not_connected;
                tmap_context.native_code = -ENOTCONN;
            }
            k_spin_unlock(&tmap_context.lock, key);
        }
#endif
    }

    Error TelephonyMediaRoles::end() noexcept
    {
#if defined(CONFIG_BT_TMAP)
        k_spinlock_key_t key = k_spin_lock(&tmap_context.lock);
        if (tmap_context.owner != this)
        {
            k_spin_unlock(&tmap_context.lock, key);
            return Error::not_started;
        }
        tmap_context.owner = nullptr;
        tmap_context.connection = {};
        tmap_context.peer_roles = 0U;
        tmap_context.stage = TelephonyMediaStage::idle;
        tmap_context.last_error = Error::not_started;
        tmap_context.native_code = 0;
        k_spin_unlock(&tmap_context.lock, key);
        return Error::none;
#else
        return Error::unsupported;
#endif
    }

    std::uint16_t TelephonyMediaRoles::localRoles() const noexcept
    {
#if defined(CONFIG_BT_TMAP)
        k_spinlock_key_t key = k_spin_lock(&tmap_context.lock);
        const std::uint16_t result = tmap_context.owner == this ? tmap_context.local_roles : 0U;
        k_spin_unlock(&tmap_context.lock, key);
        return result;
#else
        return 0U;
#endif
    }

    std::uint16_t TelephonyMediaRoles::peerRoles() const noexcept
    {
#if defined(CONFIG_BT_TMAP)
        k_spinlock_key_t key = k_spin_lock(&tmap_context.lock);
        const std::uint16_t result = tmap_context.owner == this ? tmap_context.peer_roles : 0U;
        k_spin_unlock(&tmap_context.lock, key);
        return result;
#else
        return 0U;
#endif
    }

    bool TelephonyMediaRoles::peerSupports(TelephonyMediaRole roles) const noexcept
    {
        const std::uint16_t requested = static_cast<std::uint16_t>(roles);
        return (requested != 0U) && ((peerRoles() & requested) == requested);
    }

    TelephonyMediaStage TelephonyMediaRoles::stage() const noexcept
    {
#if defined(CONFIG_BT_TMAP)
        k_spinlock_key_t key = k_spin_lock(&tmap_context.lock);
        const TelephonyMediaStage result =
            tmap_context.owner == this ? tmap_context.stage : TelephonyMediaStage::idle;
        k_spin_unlock(&tmap_context.lock, key);
        return result;
#else
        return TelephonyMediaStage::idle;
#endif
    }

    Error TelephonyMediaRoles::lastError() const noexcept
    {
#if defined(CONFIG_BT_TMAP)
        k_spinlock_key_t key = k_spin_lock(&tmap_context.lock);
        const Error result =
            tmap_context.owner == this ? tmap_context.last_error : Error::not_started;
        k_spin_unlock(&tmap_context.lock, key);
        return result;
#else
        return Error::unsupported;
#endif
    }

    int TelephonyMediaRoles::nativeCode() const noexcept
    {
#if defined(CONFIG_BT_TMAP)
        k_spinlock_key_t key = k_spin_lock(&tmap_context.lock);
        const int result = tmap_context.owner == this ? tmap_context.native_code : -ENOTSUP;
        k_spin_unlock(&tmap_context.lock, key);
        return result;
#else
        return -ENOTSUP;
#endif
    }

    Error GamingAudioRoles::begin(GamingAudioRole roles,
                                  const GamingAudioFeatures &features) noexcept
    {
#if defined(CONFIG_BT_GMAP)
        const std::uint8_t role_bits = static_cast<std::uint8_t>(roles);
        if (!supportsGmapRoles(role_bits))
        {
            return Error::unsupported;
        }
        if (!validGmapFeatures(role_bits, features))
        {
            return Error::invalid_argument;
        }

        bool register_callbacks = false;
        bool register_service = false;
        k_spinlock_key_t key = k_spin_lock(&gmap_context.lock);
        if (gmap_context.owner != nullptr)
        {
            const Error result = gmap_context.owner == this ? Error::already_started : Error::busy;
            k_spin_unlock(&gmap_context.lock, key);
            return result;
        }
        if (gmap_context.service_registered &&
            ((gmap_context.local_roles != role_bits) ||
             !sameFeatures(gmap_context.local_features, features)))
        {
            k_spin_unlock(&gmap_context.lock, key);
            return Error::unsupported;
        }
        register_callbacks = !gmap_context.callbacks_registered;
        register_service = !gmap_context.service_registered;
        k_spin_unlock(&gmap_context.lock, key);

        if (register_callbacks)
        {
            const int callback_result = bt_gmap_cb_register(&gmap_callbacks);
            if (callback_result != 0)
            {
                return publicError(callback_result);
            }
        }
        if (register_service)
        {
            const int service_result = bt_gmap_register(static_cast<enum bt_gmap_role>(role_bits),
                                                        nativeFeatures(features));
            if (service_result != 0)
            {
                return publicError(service_result);
            }
        }

        key = k_spin_lock(&gmap_context.lock);
        if (gmap_context.owner != nullptr)
        {
            k_spin_unlock(&gmap_context.lock, key);
            return Error::busy;
        }
        gmap_context.owner = this;
        gmap_context.connection = {};
        gmap_context.peer = {};
        gmap_context.local_roles = role_bits;
        gmap_context.local_features = features;
        gmap_context.stage = GamingAudioStage::ready;
        gmap_context.last_error = Error::none;
        gmap_context.native_code = 0;
        gmap_context.callbacks_registered = true;
        gmap_context.service_registered = true;
        k_spin_unlock(&gmap_context.lock, key);
        return Error::none;
#else
        static_cast<void>(roles);
        static_cast<void>(features);
        return Error::unsupported;
#endif
    }

    Error GamingAudioRoles::discover(const BLEConnectionHandle &connection) noexcept
    {
#if defined(CONFIG_BT_GMAP)
        if (!connection.valid() || !BLEConnection.connected(connection))
        {
            return Error::not_connected;
        }
        k_spinlock_key_t key = k_spin_lock(&gmap_context.lock);
        if (gmap_context.owner != this)
        {
            k_spin_unlock(&gmap_context.lock, key);
            return Error::not_started;
        }
        if (gmap_context.stage == GamingAudioStage::discovering)
        {
            k_spin_unlock(&gmap_context.lock, key);
            return Error::busy;
        }
        gmap_context.connection = connection;
        gmap_context.peer = {};
        gmap_context.stage = GamingAudioStage::discovering;
        gmap_context.last_error = Error::none;
        gmap_context.native_code = 0;
        k_spin_unlock(&gmap_context.lock, key);

        struct bt_conn *native = internal::referenceConnection(connection);
        if (native == nullptr)
        {
            key = k_spin_lock(&gmap_context.lock);
            if ((gmap_context.owner == this) && (gmap_context.connection == connection))
            {
                gmap_context.stage = GamingAudioStage::failed;
                gmap_context.last_error = Error::not_connected;
                gmap_context.native_code = -ENOTCONN;
            }
            k_spin_unlock(&gmap_context.lock, key);
            return Error::not_connected;
        }
        const int result = bt_gmap_discover(native);
        bt_conn_unref(native);
        if (result != 0)
        {
            key = k_spin_lock(&gmap_context.lock);
            if ((gmap_context.owner == this) && (gmap_context.connection == connection) &&
                (gmap_context.stage == GamingAudioStage::discovering))
            {
                gmap_context.stage = GamingAudioStage::failed;
                gmap_context.last_error = publicError(result);
                gmap_context.native_code = result;
            }
            k_spin_unlock(&gmap_context.lock, key);
        }
        return publicError(result);
#else
        static_cast<void>(connection);
        return Error::unsupported;
#endif
    }

    void GamingAudioRoles::poll() noexcept
    {
#if defined(CONFIG_BT_GMAP)
        BLEConnectionHandle connection;
        k_spinlock_key_t key = k_spin_lock(&gmap_context.lock);
        if (gmap_context.owner == this)
        {
            connection = gmap_context.connection;
        }
        k_spin_unlock(&gmap_context.lock, key);
        if (connection.valid() && !BLEConnection.connected(connection))
        {
            key = k_spin_lock(&gmap_context.lock);
            if ((gmap_context.owner == this) && (gmap_context.connection == connection))
            {
                gmap_context.connection = {};
                gmap_context.peer = {};
                gmap_context.stage = GamingAudioStage::ready;
                gmap_context.last_error = Error::not_connected;
                gmap_context.native_code = -ENOTCONN;
            }
            k_spin_unlock(&gmap_context.lock, key);
        }
#endif
    }

    Error GamingAudioRoles::end() noexcept
    {
#if defined(CONFIG_BT_GMAP)
        k_spinlock_key_t key = k_spin_lock(&gmap_context.lock);
        if (gmap_context.owner != this)
        {
            k_spin_unlock(&gmap_context.lock, key);
            return Error::not_started;
        }
        gmap_context.owner = nullptr;
        gmap_context.connection = {};
        gmap_context.peer = {};
        gmap_context.stage = GamingAudioStage::idle;
        gmap_context.last_error = Error::not_started;
        gmap_context.native_code = 0;
        k_spin_unlock(&gmap_context.lock, key);
        return Error::none;
#else
        return Error::unsupported;
#endif
    }

    std::uint8_t GamingAudioRoles::localRoles() const noexcept
    {
#if defined(CONFIG_BT_GMAP)
        k_spinlock_key_t key = k_spin_lock(&gmap_context.lock);
        const std::uint8_t result = gmap_context.owner == this ? gmap_context.local_roles : 0U;
        k_spin_unlock(&gmap_context.lock, key);
        return result;
#else
        return 0U;
#endif
    }

    Error GamingAudioRoles::peer(GamingAudioPeer &information) const noexcept
    {
#if defined(CONFIG_BT_GMAP)
        k_spinlock_key_t key = k_spin_lock(&gmap_context.lock);
        if ((gmap_context.owner != this) || (gmap_context.stage != GamingAudioStage::discovered))
        {
            const Error result = gmap_context.owner == this ? Error::not_ready : Error::not_started;
            k_spin_unlock(&gmap_context.lock, key);
            return result;
        }
        information = gmap_context.peer;
        k_spin_unlock(&gmap_context.lock, key);
        return Error::none;
#else
        static_cast<void>(information);
        return Error::unsupported;
#endif
    }

    bool GamingAudioRoles::peerSupports(GamingAudioRole roles) const noexcept
    {
        GamingAudioPeer information;
        const std::uint8_t requested = static_cast<std::uint8_t>(roles);
        return (requested != 0U) && (peer(information) == Error::none) &&
               ((information.roles & requested) == requested);
    }

    GamingAudioStage GamingAudioRoles::stage() const noexcept
    {
#if defined(CONFIG_BT_GMAP)
        k_spinlock_key_t key = k_spin_lock(&gmap_context.lock);
        const GamingAudioStage result =
            gmap_context.owner == this ? gmap_context.stage : GamingAudioStage::idle;
        k_spin_unlock(&gmap_context.lock, key);
        return result;
#else
        return GamingAudioStage::idle;
#endif
    }

    Error GamingAudioRoles::lastError() const noexcept
    {
#if defined(CONFIG_BT_GMAP)
        k_spinlock_key_t key = k_spin_lock(&gmap_context.lock);
        const Error result =
            gmap_context.owner == this ? gmap_context.last_error : Error::not_started;
        k_spin_unlock(&gmap_context.lock, key);
        return result;
#else
        return Error::unsupported;
#endif
    }

    int GamingAudioRoles::nativeCode() const noexcept
    {
#if defined(CONFIG_BT_GMAP)
        k_spinlock_key_t key = k_spin_lock(&gmap_context.lock);
        const int result = gmap_context.owner == this ? gmap_context.native_code : -ENOTSUP;
        k_spin_unlock(&gmap_context.lock, key);
        return result;
#else
        return -ENOTSUP;
#endif
    }
} // namespace nucode::ble::audio

#endif
