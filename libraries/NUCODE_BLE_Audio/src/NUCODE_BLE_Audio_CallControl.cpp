/**
 * @file NUCODE_BLE_Audio_CallControl.cpp
 * @brief CCP/TBS 합성 call server와 client 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) &&                                                   \
    (defined(CONFIG_BT_CCP_CALL_CONTROL_SERVER) || defined(CONFIG_BT_TBS_CLIENT))

#include <NUCODE_BLE.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/audio/ccp.h>
#include <zephyr/bluetooth/audio/tbs.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/kernel.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        constexpr std::size_t maximumProviderLength = 31U;
        constexpr std::size_t maximumSchemeLength = 31U;
        constexpr std::size_t maximumUriLength = 63U;

        /** @brief native errno와 TBS result code를 공개 오류로 변환합니다. */
        Error mapCallError(int error) noexcept
        {
            if (error == 0)
            {
                return Error::none;
            }
            if ((error == -EINVAL) || (error == BT_TBS_RESULT_CODE_INVALID_CALL_INDEX) ||
                (error == BT_TBS_RESULT_CODE_INVALID_URI))
            {
                return Error::invalid_argument;
            }
            if ((error == -EALREADY) || (error == -EEXIST))
            {
                return Error::already_started;
            }
            if ((error == -EBUSY) || (error == -EINPROGRESS) ||
                (error == BT_TBS_RESULT_CODE_OUT_OF_RESOURCES))
            {
                return Error::busy;
            }
            if ((error == -ENOTCONN) || (error == -ECONNRESET))
            {
                return Error::not_connected;
            }
            if ((error == -ENOTSUP) || (error == -ENOENT) ||
                (error == BT_TBS_RESULT_CODE_OPCODE_NOT_SUPPORTED))
            {
                return Error::unsupported;
            }
            if ((error == BT_TBS_RESULT_CODE_OPERATION_NOT_POSSIBLE) ||
                (error == BT_TBS_RESULT_CODE_STATE_MISMATCH))
            {
                return Error::not_ready;
            }
            return Error::stack_error;
        }

        /** @brief TBS call state를 공개 enum으로 변환합니다. */
        CallState callState(std::uint8_t state) noexcept
        {
            switch (state)
            {
            case BT_TBS_CALL_STATE_INCOMING:
                return CallState::incoming;
            case BT_TBS_CALL_STATE_DIALING:
                return CallState::dialing;
            case BT_TBS_CALL_STATE_ALERTING:
                return CallState::alerting;
            case BT_TBS_CALL_STATE_ACTIVE:
                return CallState::active;
            case BT_TBS_CALL_STATE_LOCALLY_HELD:
                return CallState::locally_held;
            case BT_TBS_CALL_STATE_REMOTELY_HELD:
                return CallState::remotely_held;
            case BT_TBS_CALL_STATE_LOCALLY_AND_REMOTELY_HELD:
                return CallState::locally_and_remotely_held;
            default:
                return CallState::none;
            }
        }

        /** @brief bounded non-empty ASCII/UTF-8 문자열인지 확인합니다. */
        bool validText(const char *text, std::size_t maximum) noexcept
        {
            return (text != nullptr) && (text[0] != '\0') &&
                   (strnlen(text, maximum + 1U) <= maximum);
        }

        /** @brief 고정 길이 backend 문자열로 복사합니다. */
        template <std::size_t Size>
        void copyText(char (&destination)[Size], const char *source) noexcept
        {
            (void)strncpy(destination, source, Size - 1U);
            destination[Size - 1U] = '\0';
        }
    } // namespace

#if defined(CONFIG_BT_CCP_CALL_CONTROL_SERVER)
    namespace
    {
        /** @brief 한 image의 GTBS service와 합성 call 상태입니다. */
        struct CallServerBackend
        {
            CallControlServer *owner = nullptr;
            struct bt_ccp_call_control_server_bearer *bearer = nullptr;
            CallSnapshot snapshot = {};
            char provider[maximumProviderLength + 1U] = {};
            char schemes[maximumSchemeLength + 1U] = {};
            bool callbacks_registered = false;
        };

        CallServerBackend callServer;
        K_MUTEX_DEFINE(callServerMutex);

        bool callServerOriginated(struct bt_conn *, std::uint8_t call_index, const char *) noexcept
        {
            k_mutex_lock(&callServerMutex, K_FOREVER);
            const bool accept = callServer.owner != nullptr;
            if (accept)
            {
                callServer.snapshot.call_index = call_index;
                callServer.snapshot.state = CallState::alerting;
                callServer.snapshot.result_code = BT_TBS_RESULT_CODE_SUCCESS;
                ++callServer.snapshot.updates;
            }
            k_mutex_unlock(&callServerMutex);
            return accept;
        }

        void callServerTerminated(struct bt_conn *, std::uint8_t call_index,
                                  std::uint8_t reason) noexcept
        {
            k_mutex_lock(&callServerMutex, K_FOREVER);
            if ((callServer.owner != nullptr) && (callServer.snapshot.call_index == call_index))
            {
                callServer.snapshot.state = CallState::none;
                callServer.snapshot.result_code = reason;
                ++callServer.snapshot.updates;
            }
            k_mutex_unlock(&callServerMutex);
        }

        void callServerHeld(struct bt_conn *, std::uint8_t call_index) noexcept
        {
            k_mutex_lock(&callServerMutex, K_FOREVER);
            if (callServer.owner != nullptr)
            {
                callServer.snapshot.call_index = call_index;
                callServer.snapshot.state = CallState::locally_held;
                callServer.snapshot.result_code = BT_TBS_RESULT_CODE_SUCCESS;
                ++callServer.snapshot.updates;
            }
            k_mutex_unlock(&callServerMutex);
        }

        void callServerAccepted(struct bt_conn *, std::uint8_t call_index) noexcept
        {
            k_mutex_lock(&callServerMutex, K_FOREVER);
            if (callServer.owner != nullptr)
            {
                callServer.snapshot.call_index = call_index;
                callServer.snapshot.state = CallState::active;
                callServer.snapshot.result_code = BT_TBS_RESULT_CODE_SUCCESS;
                ++callServer.snapshot.updates;
            }
            k_mutex_unlock(&callServerMutex);
        }

        void callServerRetrieved(struct bt_conn *connection, std::uint8_t call_index) noexcept
        {
            callServerAccepted(connection, call_index);
        }

        void callServerJoined(struct bt_conn *, std::uint8_t count,
                              const std::uint8_t *indexes) noexcept
        {
            k_mutex_lock(&callServerMutex, K_FOREVER);
            if ((callServer.owner != nullptr) && (count != 0U) && (indexes != nullptr))
            {
                callServer.snapshot.call_index = indexes[0];
                callServer.snapshot.state = CallState::active;
                callServer.snapshot.result_code = BT_TBS_RESULT_CODE_SUCCESS;
                ++callServer.snapshot.updates;
            }
            k_mutex_unlock(&callServerMutex);
        }

        bool authorizeCallController(struct bt_conn *) noexcept
        {
            k_mutex_lock(&callServerMutex, K_FOREVER);
            const bool authorized = callServer.owner != nullptr;
            k_mutex_unlock(&callServerMutex);
            return authorized;
        }

        struct bt_tbs_cb callServerCallbacks = {
            .originate_call = callServerOriginated,
            .terminate_call = callServerTerminated,
            .hold_call = callServerHeld,
            .accept_call = callServerAccepted,
            .retrieve_call = callServerRetrieved,
            .join_calls = callServerJoined,
            .authorize = authorizeCallController,
        };

        /** @brief server local operation 결과와 snapshot을 함께 기록합니다. */
        Error finishServerOperation(CallControlServer *owner, int result, CallState state,
                                    std::uint8_t index) noexcept
        {
            k_mutex_lock(&callServerMutex, K_FOREVER);
            if ((callServer.owner == owner) && ((result == 0) || (result > 0)))
            {
                if ((result == 0) || (state == CallState::incoming))
                {
                    callServer.snapshot.call_index = index;
                    callServer.snapshot.state = state;
                    callServer.snapshot.result_code = BT_TBS_RESULT_CODE_SUCCESS;
                    ++callServer.snapshot.updates;
                }
            }
            k_mutex_unlock(&callServerMutex);
            return mapCallError((state == CallState::incoming) && (result > 0) ? 0 : result);
        }
    } // namespace

    Error CallControlServer::begin(const char *provider_name, const char *uri_schemes) noexcept
    {
        if (!BLEDevice.initialized())
        {
            return record(Error::not_ready);
        }
        if (!validText(provider_name, maximumProviderLength) ||
            !validText(uri_schemes, maximumSchemeLength))
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        k_mutex_lock(&callServerMutex, K_FOREVER);
        if (started_ || (callServer.owner != nullptr))
        {
            k_mutex_unlock(&callServerMutex);
            return record(started_ ? Error::already_started : Error::busy);
        }
        copyText(callServer.provider, provider_name);
        copyText(callServer.schemes, uri_schemes);
        callServer.owner = this;
        callServer.snapshot = {};
        if (!callServer.callbacks_registered)
        {
            bt_tbs_register_cb(&callServerCallbacks);
            callServer.callbacks_registered = true;
        }
        k_mutex_unlock(&callServerMutex);

        struct bt_tbs_register_param parameters = {};
        parameters.provider_name = callServer.provider;
        parameters.uci = const_cast<char *>("un000");
        parameters.uri_schemes_supported = callServer.schemes;
        parameters.gtbs = true;
        parameters.authorization_required = true;
        parameters.technology = BT_TBS_TECHNOLOGY_5G;
        parameters.supported_features = BT_TBS_FEATURE_HOLD;
        struct bt_ccp_call_control_server_bearer *bearer = nullptr;
        const int result = bt_ccp_call_control_server_register_bearer(&parameters, &bearer);

        k_mutex_lock(&callServerMutex, K_FOREVER);
        if ((callServer.owner == this) && (result == 0))
        {
            callServer.bearer = bearer;
            started_ = true;
        }
        else if (callServer.owner == this)
        {
            callServer.owner = nullptr;
        }
        k_mutex_unlock(&callServerMutex);
        return record(mapCallError(result), result);
    }

    Error CallControlServer::incoming(const char *to, const char *from,
                                      const char *friendly_name) noexcept
    {
        if (!validText(to, maximumUriLength) || !validText(from, maximumUriLength) ||
            !validText(friendly_name, maximumProviderLength))
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        if (!ready())
        {
            return record(Error::not_started);
        }
        const int result = bt_tbs_remote_incoming(BT_TBS_GTBS_INDEX, to, from, friendly_name);
        const std::uint8_t index = result > 0 ? static_cast<std::uint8_t>(result) : 0U;
        const Error error = finishServerOperation(this, result, CallState::incoming, index);
        return record(error, error == Error::none ? 0 : result);
    }

#define NUCODE_CALL_SERVER_REMOTE(name, native_call, state_value)                                  \
    Error CallControlServer::name(std::uint8_t call_index) noexcept                                \
    {                                                                                              \
        if ((call_index == 0U) || !ready())                                                        \
        {                                                                                          \
            return record(call_index == 0U ? Error::invalid_argument : Error::not_started,         \
                          call_index == 0U ? -EINVAL : 0);                                         \
        }                                                                                          \
        const int result = native_call(call_index);                                                \
        const Error error = finishServerOperation(this, result, state_value, call_index);          \
        return record(error, result);                                                              \
    }

    NUCODE_CALL_SERVER_REMOTE(remoteAnswer, bt_tbs_remote_answer, CallState::active)
    NUCODE_CALL_SERVER_REMOTE(remoteHold, bt_tbs_remote_hold, CallState::remotely_held)
    NUCODE_CALL_SERVER_REMOTE(remoteRetrieve, bt_tbs_remote_retrieve, CallState::active)
    NUCODE_CALL_SERVER_REMOTE(remoteTerminate, bt_tbs_remote_terminate, CallState::none)

#undef NUCODE_CALL_SERVER_REMOTE

    Error CallControlServer::end() noexcept
    {
        k_mutex_lock(&callServerMutex, K_FOREVER);
        if (!started_ || (callServer.owner != this))
        {
            k_mutex_unlock(&callServerMutex);
            return record(Error::not_started);
        }
        struct bt_ccp_call_control_server_bearer *bearer = callServer.bearer;
        k_mutex_unlock(&callServerMutex);
        const int result = bt_ccp_call_control_server_unregister_bearer(bearer);
        if (result != 0)
        {
            return record(mapCallError(result), result);
        }
        k_mutex_lock(&callServerMutex, K_FOREVER);
        callServer.owner = nullptr;
        callServer.bearer = nullptr;
        callServer.snapshot = {};
        started_ = false;
        k_mutex_unlock(&callServerMutex);
        return record(Error::none);
    }

    bool CallControlServer::ready() const noexcept
    {
        k_mutex_lock(&callServerMutex, K_FOREVER);
        const bool value = started_ && (callServer.owner == this) && (callServer.bearer != nullptr);
        k_mutex_unlock(&callServerMutex);
        return value;
    }

    CallSnapshot CallControlServer::snapshot() const noexcept
    {
        k_mutex_lock(&callServerMutex, K_FOREVER);
        const CallSnapshot value = callServer.owner == this ? callServer.snapshot : CallSnapshot{};
        k_mutex_unlock(&callServerMutex);
        return value;
    }
#else
    Error CallControlServer::begin(const char *, const char *) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error CallControlServer::incoming(const char *, const char *, const char *) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
#define NUCODE_CALL_SERVER_STUB(name)                                                              \
    Error CallControlServer::name(std::uint8_t) noexcept                                           \
    {                                                                                              \
        return record(Error::unsupported, -ENOTSUP);                                               \
    }
    NUCODE_CALL_SERVER_STUB(remoteAnswer)
    NUCODE_CALL_SERVER_STUB(remoteHold)
    NUCODE_CALL_SERVER_STUB(remoteRetrieve)
    NUCODE_CALL_SERVER_STUB(remoteTerminate)
#undef NUCODE_CALL_SERVER_STUB
    Error CallControlServer::end() noexcept
    {
        return record(Error::not_started);
    }
    bool CallControlServer::ready() const noexcept
    {
        return false;
    }
    CallSnapshot CallControlServer::snapshot() const noexcept
    {
        return {};
    }
#endif

    Error CallControlServer::lastError() const noexcept
    {
        return last_error_;
    }

    int CallControlServer::nativeCode() const noexcept
    {
        return native_code_;
    }

    Error CallControlServer::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

#if defined(CONFIG_BT_TBS_CLIENT)
    namespace
    {
        /** @brief 한 연결에 결합한 TBS client callback 상태입니다. */
        struct CallClientBackend
        {
            CallControlClient *owner = nullptr;
            BLEConnectionHandle handle = {};
            struct bt_conn *connection = nullptr;
            CallSnapshot snapshot = {};
            std::uint32_t generation = 0U;
            RemoteControlStage stage = RemoteControlStage::idle;
            int error = 0;
            bool callbacks_registered = false;
            bool pending = false;
            bool refresh_pending = false;
            bool gtbs_found = false;
        };

        CallClientBackend callClient;
        K_MUTEX_DEFINE(callClientMutex);

        bool currentCallConnection(struct bt_conn *connection) noexcept
        {
            return (callClient.owner != nullptr) && (callClient.connection == connection);
        }

        void callClientDiscovered(struct bt_conn *connection, int error, std::uint8_t,
                                  bool gtbs_found) noexcept
        {
            k_mutex_lock(&callClientMutex, K_FOREVER);
            if (currentCallConnection(connection))
            {
                callClient.pending = false;
                callClient.error = error;
                callClient.gtbs_found = gtbs_found;
                if ((error == 0) && gtbs_found)
                {
                    callClient.stage = RemoteControlStage::ready;
                    callClient.refresh_pending = true;
                }
                else
                {
                    callClient.error = error == 0 ? -ENOENT : error;
                    callClient.stage = RemoteControlStage::failed;
                }
            }
            k_mutex_unlock(&callClientMutex);
        }

        void callClientOperation(struct bt_conn *connection, int error, std::uint8_t,
                                 std::uint8_t call_index) noexcept
        {
            k_mutex_lock(&callClientMutex, K_FOREVER);
            if (currentCallConnection(connection))
            {
                callClient.pending = false;
                callClient.error = error;
                callClient.snapshot.call_index = call_index;
                callClient.snapshot.result_code = error > 0 ? static_cast<std::uint8_t>(error) : 0U;
                ++callClient.snapshot.updates;
                callClient.stage =
                    error == 0 ? RemoteControlStage::ready : RemoteControlStage::failed;
                callClient.refresh_pending = error == 0;
            }
            k_mutex_unlock(&callClientMutex);
        }

        void callClientStates(struct bt_conn *connection, int error, std::uint8_t,
                              std::uint8_t count,
                              const struct bt_tbs_client_call_state *states) noexcept
        {
            k_mutex_lock(&callClientMutex, K_FOREVER);
            if (currentCallConnection(connection))
            {
                callClient.pending = false;
                callClient.error = error;
                if (error == 0)
                {
                    if ((count != 0U) && (states != nullptr))
                    {
                        callClient.snapshot.call_index = states[0].index;
                        callClient.snapshot.state = callState(states[0].state);
                    }
                    else
                    {
                        callClient.snapshot.call_index = 0U;
                        callClient.snapshot.state = CallState::none;
                    }
                    ++callClient.snapshot.updates;
                    callClient.stage = RemoteControlStage::ready;
                }
                else
                {
                    callClient.stage = RemoteControlStage::failed;
                }
            }
            k_mutex_unlock(&callClientMutex);
        }

        void callClientTerminated(struct bt_conn *connection, int error, std::uint8_t,
                                  std::uint8_t call_index, std::uint8_t reason) noexcept
        {
            k_mutex_lock(&callClientMutex, K_FOREVER);
            if (currentCallConnection(connection))
            {
                callClient.snapshot.call_index = call_index;
                callClient.snapshot.state = CallState::none;
                callClient.snapshot.result_code = reason;
                callClient.error = error;
                ++callClient.snapshot.updates;
            }
            k_mutex_unlock(&callClientMutex);
        }

        struct bt_tbs_client_cb callClientCallbacks = {
            .discover = callClientDiscovered,
#if defined(CONFIG_BT_TBS_CLIENT_ORIGINATE_CALL)
            .originate_call = callClientOperation,
#endif
#if defined(CONFIG_BT_TBS_CLIENT_TERMINATE_CALL)
            .terminate_call = callClientOperation,
#endif
#if defined(CONFIG_BT_TBS_CLIENT_HOLD_CALL)
            .hold_call = callClientOperation,
#endif
#if defined(CONFIG_BT_TBS_CLIENT_ACCEPT_CALL)
            .accept_call = callClientOperation,
#endif
#if defined(CONFIG_BT_TBS_CLIENT_RETRIEVE_CALL)
            .retrieve_call = callClientOperation,
#endif
            .call_state = callClientStates,
            .termination_reason = callClientTerminated,
        };

        void callConnectionDisconnected(struct bt_conn *connection, std::uint8_t) noexcept
        {
            struct bt_conn *release = nullptr;
            k_mutex_lock(&callClientMutex, K_FOREVER);
            if (currentCallConnection(connection))
            {
                release = callClient.connection;
                callClient.connection = nullptr;
                callClient.owner = nullptr;
                callClient.pending = false;
                callClient.stage = RemoteControlStage::idle;
                ++callClient.generation;
            }
            k_mutex_unlock(&callClientMutex);
            if (release != nullptr)
            {
                bt_conn_unref(release);
            }
        }

        BT_CONN_CB_DEFINE(callConnectionCallbacks) = {
            .disconnected = callConnectionDisconnected,
        };

        /** @brief client operation을 시작하기 위한 소유권과 busy 상태를 검사합니다. */
        struct bt_conn *startCallOperation(CallControlClient *owner) noexcept
        {
            k_mutex_lock(&callClientMutex, K_FOREVER);
            if ((callClient.owner != owner) || (callClient.stage != RemoteControlStage::ready) ||
                callClient.pending)
            {
                k_mutex_unlock(&callClientMutex);
                return nullptr;
            }
            callClient.pending = true;
            callClient.stage = RemoteControlStage::operating;
            struct bt_conn *connection = callClient.connection;
            k_mutex_unlock(&callClientMutex);
            return connection;
        }

        void failCallStart(struct bt_conn *connection, int error) noexcept
        {
            k_mutex_lock(&callClientMutex, K_FOREVER);
            if (currentCallConnection(connection))
            {
                callClient.pending = false;
                callClient.error = error;
                callClient.stage = RemoteControlStage::failed;
            }
            k_mutex_unlock(&callClientMutex);
        }
    } // namespace

    Error CallControlClient::begin(const BLEConnectionHandle &connection) noexcept
    {
        if (!BLEDevice.initialized())
        {
            return record(Error::not_ready);
        }
        struct bt_conn *native = internal::referenceConnection(connection);
        if (native == nullptr)
        {
            return record(Error::not_connected, -ENOTCONN);
        }
        k_mutex_lock(&callClientMutex, K_FOREVER);
        if (started_ || (callClient.owner != nullptr))
        {
            k_mutex_unlock(&callClientMutex);
            bt_conn_unref(native);
            return record(started_ ? Error::already_started : Error::busy);
        }
        if (!callClient.callbacks_registered)
        {
            const int callback_result = bt_tbs_client_register_cb(&callClientCallbacks);
            if ((callback_result != 0) && (callback_result != -EEXIST))
            {
                k_mutex_unlock(&callClientMutex);
                bt_conn_unref(native);
                return record(mapCallError(callback_result), callback_result);
            }
            callClient.callbacks_registered = true;
        }
        ++callClient.generation;
        if (callClient.generation == 0U)
        {
            ++callClient.generation;
        }
        callClient.owner = this;
        callClient.handle = connection;
        callClient.connection = native;
        callClient.snapshot = {};
        callClient.error = 0;
        callClient.pending = true;
        callClient.refresh_pending = false;
        callClient.gtbs_found = false;
        callClient.stage = RemoteControlStage::discovering;
        started_ = true;
        generation_ = callClient.generation;
        k_mutex_unlock(&callClientMutex);

        const int result = bt_tbs_client_discover(native);
        if (result != 0)
        {
            (void)end();
            return record(mapCallError(result), result);
        }
        return record(Error::none);
    }

    void CallControlClient::poll() noexcept
    {
        k_mutex_lock(&callClientMutex, K_FOREVER);
        if (!started_ || (callClient.owner != this) || (callClient.generation != generation_) ||
            !callClient.refresh_pending || callClient.pending ||
            (callClient.stage != RemoteControlStage::ready))
        {
            k_mutex_unlock(&callClientMutex);
            return;
        }
        callClient.refresh_pending = false;
        callClient.pending = true;
        callClient.stage = RemoteControlStage::reading;
        struct bt_conn *connection = callClient.connection;
        k_mutex_unlock(&callClientMutex);
        const int result = bt_tbs_client_read_call_state(connection, BT_TBS_GTBS_INDEX);
        if (result != 0)
        {
            failCallStart(connection, result);
        }
    }

    Error CallControlClient::refresh() noexcept
    {
        k_mutex_lock(&callClientMutex, K_FOREVER);
        if (!started_ || (callClient.owner != this) || (callClient.generation != generation_))
        {
            k_mutex_unlock(&callClientMutex);
            return record(Error::not_started);
        }
        if (callClient.pending || (callClient.stage == RemoteControlStage::discovering) ||
            (callClient.stage == RemoteControlStage::reading) ||
            (callClient.stage == RemoteControlStage::operating))
        {
            k_mutex_unlock(&callClientMutex);
            return record(Error::busy, -EBUSY);
        }
        callClient.refresh_pending = true;
        callClient.stage = RemoteControlStage::ready;
        k_mutex_unlock(&callClientMutex);
        return record(Error::none);
    }

    Error CallControlClient::originate(const char *uri) noexcept
    {
#if !defined(CONFIG_BT_TBS_CLIENT_ORIGINATE_CALL)
        static_cast<void>(uri);
        return record(Error::unsupported, -ENOTSUP);
#else
        if (!validText(uri, maximumUriLength))
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        struct bt_conn *connection = startCallOperation(this);
        if (connection == nullptr)
        {
            return record(Error::not_ready);
        }
        const int result = bt_tbs_client_originate_call(connection, BT_TBS_GTBS_INDEX, uri);
        if (result != 0)
        {
            failCallStart(connection, result);
        }
        return record(mapCallError(result), result);
#endif
    }

#define NUCODE_CALL_CLIENT_OPERATION(name, native_call)                                            \
    Error CallControlClient::name(std::uint8_t call_index) noexcept                                \
    {                                                                                              \
        if (call_index == 0U)                                                                      \
        {                                                                                          \
            return record(Error::invalid_argument, -EINVAL);                                       \
        }                                                                                          \
        struct bt_conn *connection = startCallOperation(this);                                     \
        if (connection == nullptr)                                                                 \
        {                                                                                          \
            return record(Error::not_ready);                                                       \
        }                                                                                          \
        const int result = native_call(connection, BT_TBS_GTBS_INDEX, call_index);                 \
        if (result != 0)                                                                           \
        {                                                                                          \
            failCallStart(connection, result);                                                     \
        }                                                                                          \
        return record(mapCallError(result), result);                                               \
    }

#define NUCODE_CALL_CLIENT_UNSUPPORTED(name)                                                       \
    Error CallControlClient::name(std::uint8_t) noexcept                                           \
    {                                                                                              \
        return record(Error::unsupported, -ENOTSUP);                                               \
    }

#if defined(CONFIG_BT_TBS_CLIENT_ACCEPT_CALL)
    NUCODE_CALL_CLIENT_OPERATION(accept, bt_tbs_client_accept_call)
#else
    NUCODE_CALL_CLIENT_UNSUPPORTED(accept)
#endif
#if defined(CONFIG_BT_TBS_CLIENT_HOLD_CALL)
    NUCODE_CALL_CLIENT_OPERATION(hold, bt_tbs_client_hold_call)
#else
    NUCODE_CALL_CLIENT_UNSUPPORTED(hold)
#endif
#if defined(CONFIG_BT_TBS_CLIENT_RETRIEVE_CALL)
    NUCODE_CALL_CLIENT_OPERATION(retrieve, bt_tbs_client_retrieve_call)
#else
    NUCODE_CALL_CLIENT_UNSUPPORTED(retrieve)
#endif
#if defined(CONFIG_BT_TBS_CLIENT_TERMINATE_CALL)
    NUCODE_CALL_CLIENT_OPERATION(terminate, bt_tbs_client_terminate_call)
#else
    NUCODE_CALL_CLIENT_UNSUPPORTED(terminate)
#endif

#undef NUCODE_CALL_CLIENT_OPERATION
#undef NUCODE_CALL_CLIENT_UNSUPPORTED

    Error CallControlClient::end() noexcept
    {
        struct bt_conn *release = nullptr;
        k_mutex_lock(&callClientMutex, K_FOREVER);
        if (!started_ || (callClient.owner != this))
        {
            k_mutex_unlock(&callClientMutex);
            return record(Error::not_started);
        }
        release = callClient.connection;
        callClient.owner = nullptr;
        callClient.connection = nullptr;
        callClient.pending = false;
        callClient.refresh_pending = false;
        callClient.stage = RemoteControlStage::idle;
        ++callClient.generation;
        started_ = false;
        generation_ = 0U;
        k_mutex_unlock(&callClientMutex);
        if (release != nullptr)
        {
            bt_conn_unref(release);
        }
        return record(Error::none);
    }

    bool CallControlClient::ready() const noexcept
    {
        return stage() == RemoteControlStage::ready;
    }

    RemoteControlStage CallControlClient::stage() const noexcept
    {
        k_mutex_lock(&callClientMutex, K_FOREVER);
        const RemoteControlStage value =
            started_ && (callClient.owner == this) && (callClient.generation == generation_)
                ? callClient.stage
                : RemoteControlStage::idle;
        k_mutex_unlock(&callClientMutex);
        return value;
    }

    CallSnapshot CallControlClient::snapshot() const noexcept
    {
        k_mutex_lock(&callClientMutex, K_FOREVER);
        const CallSnapshot value =
            started_ && (callClient.owner == this) && (callClient.generation == generation_)
                ? callClient.snapshot
                : CallSnapshot{};
        k_mutex_unlock(&callClientMutex);
        return value;
    }

    Error CallControlClient::lastError() const noexcept
    {
        k_mutex_lock(&callClientMutex, K_FOREVER);
        const int error = callClient.owner == this ? callClient.error : 0;
        k_mutex_unlock(&callClientMutex);
        return error == 0 ? last_error_ : mapCallError(error);
    }

    int CallControlClient::nativeCode() const noexcept
    {
        k_mutex_lock(&callClientMutex, K_FOREVER);
        const int error = callClient.owner == this ? callClient.error : native_code_;
        k_mutex_unlock(&callClientMutex);
        return error;
    }

    Error CallControlClient::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
#else
    Error CallControlClient::begin(const BLEConnectionHandle &) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    void CallControlClient::poll() noexcept
    {
    }
    Error CallControlClient::refresh() noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error CallControlClient::originate(const char *) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
#define NUCODE_CALL_CLIENT_STUB(name)                                                              \
    Error CallControlClient::name(std::uint8_t) noexcept                                           \
    {                                                                                              \
        return record(Error::unsupported, -ENOTSUP);                                               \
    }
    NUCODE_CALL_CLIENT_STUB(accept)
    NUCODE_CALL_CLIENT_STUB(hold)
    NUCODE_CALL_CLIENT_STUB(retrieve)
    NUCODE_CALL_CLIENT_STUB(terminate)
#undef NUCODE_CALL_CLIENT_STUB
    Error CallControlClient::end() noexcept
    {
        return record(Error::not_started);
    }
    bool CallControlClient::ready() const noexcept
    {
        return false;
    }
    RemoteControlStage CallControlClient::stage() const noexcept
    {
        return RemoteControlStage::idle;
    }
    CallSnapshot CallControlClient::snapshot() const noexcept
    {
        return {};
    }
    Error CallControlClient::lastError() const noexcept
    {
        return last_error_;
    }
    int CallControlClient::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error CallControlClient::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
#endif
} // namespace nucode::ble::audio

#else

#include <errno.h>

namespace nucode::ble::audio
{
    Error CallControlServer::begin(const char *, const char *) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error CallControlServer::incoming(const char *, const char *, const char *) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
#define NUCODE_CALL_SERVER_STUB(name)                                                              \
    Error CallControlServer::name(std::uint8_t) noexcept                                           \
    {                                                                                              \
        return record(Error::unsupported, -ENOTSUP);                                               \
    }
    NUCODE_CALL_SERVER_STUB(remoteAnswer)
    NUCODE_CALL_SERVER_STUB(remoteHold)
    NUCODE_CALL_SERVER_STUB(remoteRetrieve)
    NUCODE_CALL_SERVER_STUB(remoteTerminate)
#undef NUCODE_CALL_SERVER_STUB
    Error CallControlServer::end() noexcept
    {
        return record(Error::not_started);
    }
    bool CallControlServer::ready() const noexcept
    {
        return false;
    }
    CallSnapshot CallControlServer::snapshot() const noexcept
    {
        return {};
    }
    Error CallControlServer::lastError() const noexcept
    {
        return last_error_;
    }
    int CallControlServer::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error CallControlServer::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    Error CallControlClient::begin(const BLEConnectionHandle &) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    void CallControlClient::poll() noexcept
    {
    }
    Error CallControlClient::refresh() noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error CallControlClient::originate(const char *) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
#define NUCODE_CALL_CLIENT_STUB(name)                                                              \
    Error CallControlClient::name(std::uint8_t) noexcept                                           \
    {                                                                                              \
        return record(Error::unsupported, -ENOTSUP);                                               \
    }
    NUCODE_CALL_CLIENT_STUB(accept)
    NUCODE_CALL_CLIENT_STUB(hold)
    NUCODE_CALL_CLIENT_STUB(retrieve)
    NUCODE_CALL_CLIENT_STUB(terminate)
#undef NUCODE_CALL_CLIENT_STUB
    Error CallControlClient::end() noexcept
    {
        return record(Error::not_started);
    }
    bool CallControlClient::ready() const noexcept
    {
        return false;
    }
    RemoteControlStage CallControlClient::stage() const noexcept
    {
        return RemoteControlStage::idle;
    }
    CallSnapshot CallControlClient::snapshot() const noexcept
    {
        return {};
    }
    Error CallControlClient::lastError() const noexcept
    {
        return last_error_;
    }
    int CallControlClient::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error CallControlClient::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
} // namespace nucode::ble::audio

#endif
