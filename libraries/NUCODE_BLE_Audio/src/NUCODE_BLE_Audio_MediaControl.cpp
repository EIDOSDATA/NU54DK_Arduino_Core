/**
 * @file NUCODE_BLE_Audio_MediaControl.cpp
 * @brief MCP/MCS 합성 player와 controller 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && (defined(CONFIG_BT_MPL) || defined(CONFIG_BT_MCC))

#include <NUCODE_BLE.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/audio/mcc.h>
#include <zephyr/bluetooth/audio/media_proxy.h>
#include <zephyr/bluetooth/audio/mcs.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/kernel.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        /** @brief native 오류를 공개 Audio 오류로 변환합니다. */
        Error mapMediaError(int error) noexcept
        {
            if (error == 0)
            {
                return Error::none;
            }
            if (error == -EINVAL)
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
            if ((error == -ENOTCONN) || (error == -ECONNRESET))
            {
                return Error::not_connected;
            }
            if ((error == -ENOTSUP) || (error == -ENOENT))
            {
                return Error::unsupported;
            }
            return Error::stack_error;
        }

        /** @brief 원격 media state 값을 안정 공개 enum으로 변환합니다. */
        MediaState mediaState(std::uint8_t state) noexcept
        {
            switch (state)
            {
            case BT_MCS_MEDIA_STATE_PLAYING:
                return MediaState::playing;
            case BT_MCS_MEDIA_STATE_PAUSED:
                return MediaState::paused;
            case BT_MCS_MEDIA_STATE_SEEKING:
                return MediaState::seeking;
            default:
                return MediaState::inactive;
            }
        }

        /** @brief 공개 명령을 고정 SDK Media Control Point opcode로 변환합니다. */
        std::uint8_t mediaOpcode(MediaCommand command) noexcept
        {
            switch (command)
            {
            case MediaCommand::play:
                return MEDIA_PROXY_OP_PLAY;
            case MediaCommand::pause:
                return MEDIA_PROXY_OP_PAUSE;
            case MediaCommand::fast_rewind:
                return MEDIA_PROXY_OP_FAST_REWIND;
            case MediaCommand::fast_forward:
                return MEDIA_PROXY_OP_FAST_FORWARD;
            case MediaCommand::stop:
                return MEDIA_PROXY_OP_STOP;
            case MediaCommand::previous_track:
                return MEDIA_PROXY_OP_PREV_TRACK;
            case MediaCommand::next_track:
                return MEDIA_PROXY_OP_NEXT_TRACK;
            }
            return 0U;
        }

        /** @brief callback 문자열을 고정 caller snapshot으로 복사합니다. */
        template <std::size_t Size>
        void copyText(char (&destination)[Size], const char *source) noexcept
        {
            if (source == nullptr)
            {
                destination[0] = '\0';
                return;
            }
            (void)strncpy(destination, source, Size - 1U);
            destination[Size - 1U] = '\0';
        }
    } // namespace

#if defined(CONFIG_BT_MPL) && defined(CONFIG_BT_MCS)
    namespace
    {
        MediaControlPlayer *playerOwner = nullptr;
        bool playerInitialized = false;
        K_MUTEX_DEFINE(playerMutex);
    } // namespace

    Error MediaControlPlayer::begin() noexcept
    {
        if (!BLEDevice.initialized())
        {
            return record(Error::not_ready);
        }
        k_mutex_lock(&playerMutex, K_FOREVER);
        if (started_)
        {
            k_mutex_unlock(&playerMutex);
            return record(Error::already_started);
        }
        if ((playerOwner != nullptr) || playerInitialized)
        {
            k_mutex_unlock(&playerMutex);
            return record(Error::busy, -EALREADY);
        }
        playerOwner = this;
        k_mutex_unlock(&playerMutex);

        const int result = media_proxy_pl_init();
        k_mutex_lock(&playerMutex, K_FOREVER);
        if (result == 0)
        {
            playerInitialized = true;
            started_ = true;
        }
        else
        {
            playerOwner = nullptr;
        }
        k_mutex_unlock(&playerMutex);
        return record(mapMediaError(result), result);
    }

    Error MediaControlPlayer::end() noexcept
    {
        k_mutex_lock(&playerMutex, K_FOREVER);
        if (!started_ || (playerOwner != this))
        {
            k_mutex_unlock(&playerMutex);
            return record(Error::not_started);
        }
        started_ = false;
        playerOwner = nullptr;
        k_mutex_unlock(&playerMutex);
        return record(Error::none);
    }

    bool MediaControlPlayer::ready() const noexcept
    {
        k_mutex_lock(&playerMutex, K_FOREVER);
        const bool value = started_ && (playerOwner == this) && playerInitialized;
        k_mutex_unlock(&playerMutex);
        return value;
    }
#else
    Error MediaControlPlayer::begin() noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlPlayer::end() noexcept
    {
        return record(Error::not_started);
    }
    bool MediaControlPlayer::ready() const noexcept
    {
        return false;
    }
#endif

    Error MediaControlPlayer::lastError() const noexcept
    {
        return last_error_;
    }

    int MediaControlPlayer::nativeCode() const noexcept
    {
        return native_code_;
    }

    Error MediaControlPlayer::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

#if defined(CONFIG_BT_MCC)
    namespace
    {
        /** @brief MCC 초기 snapshot을 순차로 읽는 내부 단계입니다. */
        enum class MediaReadStep : std::uint8_t
        {
            none,
            player_name,
            track_title,
            track_duration,
            track_position,
            media_state,
            supported_commands,
            content_control_id,
            current_track_id,
            complete,
        };

        /** @brief 한 연결에 결합한 MCC callback 상태입니다. */
        struct MediaClientBackend
        {
            MediaControlClient *owner = nullptr;
            BLEConnectionHandle handle = {};
            struct bt_conn *connection = nullptr;
            MediaSnapshot snapshot = {};
            std::uint64_t observed_track_id = 0U;
            std::uint32_t generation = 0U;
            RemoteControlStage stage = RemoteControlStage::idle;
            MediaReadStep read_step = MediaReadStep::none;
            int error = 0;
            bool callbacks_registered = false;
            bool pending = false;
            bool refresh_pending = false;
            bool observed_track_id_valid = false;
        };

        MediaClientBackend mediaClient;
        K_MUTEX_DEFINE(mediaClientMutex);

        /** @brief callback connection과 현재 generation이 같은지 검사합니다. */
        bool currentMediaConnection(struct bt_conn *connection) noexcept
        {
            return (mediaClient.owner != nullptr) && (mediaClient.connection == connection);
        }

        /** @brief 비동기 읽기 결과를 기록하고 다음 단계로 이동합니다. */
        void finishMediaRead(struct bt_conn *connection, int error, MediaReadStep next) noexcept
        {
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection))
            {
                mediaClient.error = error;
                if ((mediaClient.stage == RemoteControlStage::reading) && mediaClient.pending)
                {
                    mediaClient.pending = false;
                    if (error == 0)
                    {
                        mediaClient.read_step = next;
                        ++mediaClient.snapshot.updates;
                    }
                    else
                    {
                        mediaClient.stage = RemoteControlStage::failed;
                    }
                }
            }
            k_mutex_unlock(&mediaClientMutex);
        }

        void mediaDiscovered(struct bt_conn *connection, int error) noexcept
        {
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection))
            {
                mediaClient.pending = false;
                mediaClient.error = error;
                if (error == 0)
                {
                    mediaClient.stage = RemoteControlStage::reading;
                    mediaClient.read_step = MediaReadStep::player_name;
                }
                else
                {
                    mediaClient.stage = RemoteControlStage::failed;
                }
            }
            k_mutex_unlock(&mediaClientMutex);
        }

        void mediaPlayerName(struct bt_conn *connection, int error, const char *name) noexcept
        {
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection) && (error == 0))
            {
                copyText(mediaClient.snapshot.player_name, name);
            }
            k_mutex_unlock(&mediaClientMutex);
            finishMediaRead(connection, error, MediaReadStep::track_title);
        }

#if defined(CONFIG_BT_MCC_READ_TRACK_TITLE)
        void mediaTrackTitle(struct bt_conn *connection, int error, const char *title) noexcept
        {
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection) && (error == 0))
            {
                copyText(mediaClient.snapshot.track_title, title);
            }
            k_mutex_unlock(&mediaClientMutex);
            finishMediaRead(connection, error, MediaReadStep::track_duration);
        }
#endif

#if defined(CONFIG_BT_MCC_READ_TRACK_DURATION)
        void mediaTrackDuration(struct bt_conn *connection, int error,
                                std::int32_t duration) noexcept
        {
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection) && (error == 0))
            {
                mediaClient.snapshot.track_duration = duration;
            }
            k_mutex_unlock(&mediaClientMutex);
            finishMediaRead(connection, error, MediaReadStep::track_position);
        }
#endif

#if defined(CONFIG_BT_MCC_READ_TRACK_POSITION)
        void mediaTrackPosition(struct bt_conn *connection, int error,
                                std::int32_t position) noexcept
        {
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection) && (error == 0))
            {
                mediaClient.snapshot.track_position = position;
            }
            k_mutex_unlock(&mediaClientMutex);
            finishMediaRead(connection, error, MediaReadStep::media_state);
        }
#endif

#if defined(CONFIG_BT_MCC_READ_MEDIA_STATE)
        void mediaStateChanged(struct bt_conn *connection, int error, std::uint8_t state) noexcept
        {
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection) && (error == 0))
            {
                mediaClient.snapshot.state = mediaState(state);
                if ((mediaClient.stage != RemoteControlStage::reading) || !mediaClient.pending ||
                    (mediaClient.read_step != MediaReadStep::media_state))
                {
                    ++mediaClient.snapshot.state_notifications;
                }
            }
            k_mutex_unlock(&mediaClientMutex);
            finishMediaRead(connection, error, MediaReadStep::supported_commands);
        }
#endif

#if defined(CONFIG_BT_MCC_READ_MEDIA_CONTROL_POINT_OPCODES_SUPPORTED)
        void mediaSupportedCommands(struct bt_conn *connection, int error,
                                    std::uint32_t commands) noexcept
        {
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection) && (error == 0))
            {
                mediaClient.snapshot.supported_commands = commands;
            }
            k_mutex_unlock(&mediaClientMutex);
            finishMediaRead(connection, error, MediaReadStep::content_control_id);
        }
#endif

#if defined(CONFIG_BT_MCC_READ_CONTENT_CONTROL_ID)
        void mediaContentControlId(struct bt_conn *connection, int error,
                                   std::uint8_t identifier) noexcept
        {
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection) && (error == 0))
            {
                mediaClient.snapshot.content_control_id = identifier;
            }
            k_mutex_unlock(&mediaClientMutex);
            finishMediaRead(connection, error, MediaReadStep::current_track_id);
        }
#endif

#if defined(CONFIG_BT_OTS_CLIENT)
        void mediaCurrentTrackId(struct bt_conn *connection, int error,
                                 std::uint64_t identifier) noexcept
        {
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection) && (error == 0))
            {
                mediaClient.snapshot.current_track_id = identifier;
                mediaClient.observed_track_id = identifier;
                mediaClient.observed_track_id_valid = true;
            }
            k_mutex_unlock(&mediaClientMutex);
            finishMediaRead(connection, error, MediaReadStep::complete);
        }
#endif

        /** @brief write/command callback에서 busy 상태와 원본 오류를 갱신합니다. */
        void finishMediaOperation(struct bt_conn *connection, int error) noexcept
        {
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection))
            {
                mediaClient.pending = false;
                mediaClient.error = error;
                mediaClient.stage =
                    error == 0 ? RemoteControlStage::ready : RemoteControlStage::failed;
                mediaClient.refresh_pending = error == 0;
            }
            k_mutex_unlock(&mediaClientMutex);
        }

#if defined(CONFIG_BT_MCC_SET_TRACK_POSITION)
        void mediaSetPosition(struct bt_conn *connection, int error, std::int32_t position) noexcept
        {
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection) && (error == 0))
            {
                mediaClient.snapshot.track_position = position;
                ++mediaClient.snapshot.updates;
            }
            k_mutex_unlock(&mediaClientMutex);
            finishMediaOperation(connection, error);
        }
#endif

#if defined(CONFIG_BT_OTS_CLIENT)
        void mediaSetTrack(struct bt_conn *connection, int error, std::uint64_t identifier) noexcept
        {
            static_cast<void>(identifier);
            finishMediaOperation(connection, error);
        }
#endif

#if defined(CONFIG_BT_MCC_SET_MEDIA_CONTROL_POINT)
        void mediaCommandSent(struct bt_conn *connection, int error,
                              const struct mpl_cmd *) noexcept
        {
            if (error != 0)
            {
                finishMediaOperation(connection, error);
            }
        }
#endif

        void mediaCommandResult(struct bt_conn *connection, int error,
                                const struct mpl_cmd_ntf *result) noexcept
        {
            const int command_error = (error == 0) && (result != nullptr) &&
                                              (result->result_code != BT_MCS_OPC_NTF_SUCCESS)
                                          ? -ENOTSUP
                                          : error;
            finishMediaOperation(connection, command_error);
        }

        struct bt_mcc_cb mediaCallbacks = {
            .discover_mcs = mediaDiscovered,
            .read_player_name = mediaPlayerName,
#if defined(CONFIG_BT_MCC_READ_TRACK_TITLE)
            .read_track_title = mediaTrackTitle,
#endif
#if defined(CONFIG_BT_MCC_READ_TRACK_DURATION)
            .read_track_duration = mediaTrackDuration,
#endif
#if defined(CONFIG_BT_MCC_READ_TRACK_POSITION)
            .read_track_position = mediaTrackPosition,
#endif
#if defined(CONFIG_BT_MCC_SET_TRACK_POSITION)
            .set_track_position = mediaSetPosition,
#endif
#if defined(CONFIG_BT_OTS_CLIENT)
            .read_current_track_obj_id = mediaCurrentTrackId,
            .set_current_track_obj_id = mediaSetTrack,
#endif
#if defined(CONFIG_BT_MCC_READ_MEDIA_STATE)
            .read_media_state = mediaStateChanged,
#endif
#if defined(CONFIG_BT_MCC_SET_MEDIA_CONTROL_POINT)
            .send_cmd = mediaCommandSent,
#endif
            .cmd_ntf = mediaCommandResult,
#if defined(CONFIG_BT_MCC_READ_MEDIA_CONTROL_POINT_OPCODES_SUPPORTED)
            .read_opcodes_supported = mediaSupportedCommands,
#endif
#if defined(CONFIG_BT_MCC_READ_CONTENT_CONTROL_ID)
            .read_content_control_id = mediaContentControlId,
#endif
        };

        void mediaConnectionDisconnected(struct bt_conn *connection, std::uint8_t) noexcept
        {
            struct bt_conn *release = nullptr;
            k_mutex_lock(&mediaClientMutex, K_FOREVER);
            if (currentMediaConnection(connection))
            {
                release = mediaClient.connection;
                mediaClient.connection = nullptr;
                mediaClient.owner = nullptr;
                mediaClient.pending = false;
                mediaClient.observed_track_id = 0U;
                mediaClient.observed_track_id_valid = false;
                mediaClient.stage = RemoteControlStage::idle;
                ++mediaClient.generation;
            }
            k_mutex_unlock(&mediaClientMutex);
            if (release != nullptr)
            {
                bt_conn_unref(release);
            }
        }

        BT_CONN_CB_DEFINE(mediaConnectionCallbacks) = {
            .disconnected = mediaConnectionDisconnected,
        };
    } // namespace

    Error MediaControlClient::begin(const BLEConnectionHandle &connection) noexcept
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

        k_mutex_lock(&mediaClientMutex, K_FOREVER);
        if (started_ || (mediaClient.owner != nullptr))
        {
            k_mutex_unlock(&mediaClientMutex);
            bt_conn_unref(native);
            return record(started_ ? Error::already_started : Error::busy);
        }
        if (!mediaClient.callbacks_registered)
        {
            const int init_result = bt_mcc_init(&mediaCallbacks);
            if ((init_result != 0) && (init_result != -EALREADY))
            {
                k_mutex_unlock(&mediaClientMutex);
                bt_conn_unref(native);
                return record(mapMediaError(init_result), init_result);
            }
            mediaClient.callbacks_registered = true;
        }
        ++mediaClient.generation;
        if (mediaClient.generation == 0U)
        {
            ++mediaClient.generation;
        }
        mediaClient.owner = this;
        mediaClient.handle = connection;
        mediaClient.connection = native;
        mediaClient.snapshot = {};
        mediaClient.observed_track_id = 0U;
        mediaClient.observed_track_id_valid = false;
        mediaClient.error = 0;
        mediaClient.pending = true;
        mediaClient.refresh_pending = false;
        mediaClient.read_step = MediaReadStep::none;
        mediaClient.stage = RemoteControlStage::discovering;
        started_ = true;
        generation_ = mediaClient.generation;
        k_mutex_unlock(&mediaClientMutex);

        const int result = bt_mcc_discover_mcs(native, true);
        if (result != 0)
        {
            (void)end();
            return record(mapMediaError(result), result);
        }
        return record(Error::none);
    }

    void MediaControlClient::poll() noexcept
    {
        k_mutex_lock(&mediaClientMutex, K_FOREVER);
        if (!started_ || (mediaClient.owner != this) || (mediaClient.generation != generation_))
        {
            k_mutex_unlock(&mediaClientMutex);
            return;
        }
        if (mediaClient.refresh_pending && !mediaClient.pending)
        {
            mediaClient.refresh_pending = false;
            mediaClient.read_step = MediaReadStep::player_name;
            mediaClient.stage = RemoteControlStage::reading;
        }
        if ((mediaClient.stage != RemoteControlStage::reading) || mediaClient.pending)
        {
            k_mutex_unlock(&mediaClientMutex);
            return;
        }
        const MediaReadStep step = mediaClient.read_step;
        struct bt_conn *connection = mediaClient.connection;
        mediaClient.pending = step != MediaReadStep::complete;
        if (step == MediaReadStep::complete)
        {
            mediaClient.stage = RemoteControlStage::ready;
            k_mutex_unlock(&mediaClientMutex);
            return;
        }
        k_mutex_unlock(&mediaClientMutex);

        int result = 0;
        switch (step)
        {
        case MediaReadStep::player_name:
            result = bt_mcc_read_player_name(connection);
            break;
        case MediaReadStep::track_title:
#if defined(CONFIG_BT_MCC_READ_TRACK_TITLE)
            result = bt_mcc_read_track_title(connection);
#else
            finishMediaRead(connection, 0, MediaReadStep::track_duration);
#endif
            break;
        case MediaReadStep::track_duration:
#if defined(CONFIG_BT_MCC_READ_TRACK_DURATION)
            result = bt_mcc_read_track_duration(connection);
#else
            finishMediaRead(connection, 0, MediaReadStep::track_position);
#endif
            break;
        case MediaReadStep::track_position:
#if defined(CONFIG_BT_MCC_READ_TRACK_POSITION)
            result = bt_mcc_read_track_position(connection);
#else
            finishMediaRead(connection, 0, MediaReadStep::media_state);
#endif
            break;
        case MediaReadStep::media_state:
#if defined(CONFIG_BT_MCC_READ_MEDIA_STATE)
            result = bt_mcc_read_media_state(connection);
#else
            finishMediaRead(connection, 0, MediaReadStep::supported_commands);
#endif
            break;
        case MediaReadStep::supported_commands:
#if defined(CONFIG_BT_MCC_READ_MEDIA_CONTROL_POINT_OPCODES_SUPPORTED)
            result = bt_mcc_read_opcodes_supported(connection);
#else
            finishMediaRead(connection, 0, MediaReadStep::content_control_id);
#endif
            break;
        case MediaReadStep::content_control_id:
#if defined(CONFIG_BT_MCC_READ_CONTENT_CONTROL_ID)
            result = bt_mcc_read_content_control_id(connection);
#else
            finishMediaRead(connection, 0, MediaReadStep::current_track_id);
#endif
            break;
        case MediaReadStep::current_track_id:
#if defined(CONFIG_BT_OTS_CLIENT)
            result = bt_mcc_read_current_track_obj_id(connection);
#else
            finishMediaRead(connection, 0, MediaReadStep::complete);
#endif
            break;
        default:
            result = -EINVAL;
            break;
        }
        if (result != 0)
        {
            finishMediaRead(connection, result, MediaReadStep::complete);
        }
    }

    Error MediaControlClient::refresh() noexcept
    {
        k_mutex_lock(&mediaClientMutex, K_FOREVER);
        if (!started_ || (mediaClient.owner != this) || (mediaClient.generation != generation_))
        {
            k_mutex_unlock(&mediaClientMutex);
            return record(Error::not_started);
        }
        if (mediaClient.pending || (mediaClient.stage == RemoteControlStage::discovering))
        {
            k_mutex_unlock(&mediaClientMutex);
            return record(Error::busy, -EBUSY);
        }
        mediaClient.read_step = MediaReadStep::player_name;
        mediaClient.stage = RemoteControlStage::reading;
        mediaClient.error = 0;
        k_mutex_unlock(&mediaClientMutex);
        return record(Error::none);
    }

    Error MediaControlClient::command(MediaCommand command_value) noexcept
    {
        const std::uint8_t opcode = mediaOpcode(command_value);
        if (opcode == 0U)
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        return commandOpcode(opcode);
    }

    Error MediaControlClient::commandOpcode(std::uint8_t opcode) noexcept
    {
#if !defined(CONFIG_BT_MCC_SET_MEDIA_CONTROL_POINT)
        static_cast<void>(opcode);
        return record(Error::unsupported, -ENOTSUP);
#else
        if (opcode == 0U)
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        struct mpl_cmd command = {};
        command.opcode = opcode;
        command.use_param = false;

        k_mutex_lock(&mediaClientMutex, K_FOREVER);
        if (!started_ || (mediaClient.owner != this) ||
            (mediaClient.stage != RemoteControlStage::ready))
        {
            k_mutex_unlock(&mediaClientMutex);
            return record(Error::not_ready);
        }
        if (mediaClient.pending)
        {
            k_mutex_unlock(&mediaClientMutex);
            return record(Error::busy, -EBUSY);
        }
        struct bt_conn *connection = mediaClient.connection;
        mediaClient.pending = true;
        mediaClient.stage = RemoteControlStage::operating;
        k_mutex_unlock(&mediaClientMutex);
        const int result = bt_mcc_send_cmd(connection, &command);
        if (result != 0)
        {
            finishMediaOperation(connection, result);
        }
        return record(mapMediaError(result), result);
#endif
    }

    Error MediaControlClient::moveRelative(std::int32_t hundredths) noexcept
    {
#if !defined(CONFIG_BT_MCC_SET_MEDIA_CONTROL_POINT)
        static_cast<void>(hundredths);
        return record(Error::unsupported, -ENOTSUP);
#else
        if (hundredths == 0)
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        struct mpl_cmd command = {};
        command.opcode = MEDIA_PROXY_OP_MOVE_RELATIVE;
        command.use_param = true;
        command.param = hundredths;
        k_mutex_lock(&mediaClientMutex, K_FOREVER);
        if (!started_ || (mediaClient.owner != this) ||
            (mediaClient.stage != RemoteControlStage::ready) || mediaClient.pending)
        {
            const Error failure = mediaClient.pending ? Error::busy : Error::not_ready;
            k_mutex_unlock(&mediaClientMutex);
            return record(failure, failure == Error::busy ? -EBUSY : 0);
        }
        struct bt_conn *connection = mediaClient.connection;
        mediaClient.pending = true;
        mediaClient.stage = RemoteControlStage::operating;
        k_mutex_unlock(&mediaClientMutex);
        const int result = bt_mcc_send_cmd(connection, &command);
        if (result != 0)
        {
            finishMediaOperation(connection, result);
        }
        return record(mapMediaError(result), result);
#endif
    }

    Error MediaControlClient::setTrackPosition(std::int32_t hundredths) noexcept
    {
#if !defined(CONFIG_BT_MCC_SET_TRACK_POSITION)
        static_cast<void>(hundredths);
        return record(Error::unsupported, -ENOTSUP);
#else
        k_mutex_lock(&mediaClientMutex, K_FOREVER);
        if (!started_ || (mediaClient.owner != this) ||
            (mediaClient.stage != RemoteControlStage::ready) || mediaClient.pending)
        {
            const Error failure = mediaClient.pending ? Error::busy : Error::not_ready;
            k_mutex_unlock(&mediaClientMutex);
            return record(failure, failure == Error::busy ? -EBUSY : 0);
        }
        struct bt_conn *connection = mediaClient.connection;
        mediaClient.pending = true;
        mediaClient.stage = RemoteControlStage::operating;
        k_mutex_unlock(&mediaClientMutex);
        const int result = bt_mcc_set_track_position(connection, hundredths);
        if (result != 0)
        {
            finishMediaOperation(connection, result);
        }
        return record(mapMediaError(result), result);
#endif
    }

    Error MediaControlClient::selectTrack(std::uint64_t object_id) noexcept
    {
#if !defined(CONFIG_BT_OTS_CLIENT)
        static_cast<void>(object_id);
        return record(Error::unsupported, -ENOTSUP);
#else
        if ((object_id < 0x000000000100ULL) || (object_id > 0xffffffffffffULL))
        {
            return record(Error::invalid_argument, -EINVAL);
        }
        k_mutex_lock(&mediaClientMutex, K_FOREVER);
        if (!started_ || (mediaClient.owner != this) ||
            (mediaClient.stage != RemoteControlStage::ready) || mediaClient.pending)
        {
            const Error failure = mediaClient.pending ? Error::busy : Error::not_ready;
            k_mutex_unlock(&mediaClientMutex);
            return record(failure, failure == Error::busy ? -EBUSY : 0);
        }
        if (!mediaClient.observed_track_id_valid || mediaClient.refresh_pending ||
            (mediaClient.observed_track_id != object_id))
        {
            k_mutex_unlock(&mediaClientMutex);
            return record(Error::invalid_argument, -EINVAL);
        }
        struct bt_conn *connection = mediaClient.connection;
        mediaClient.pending = true;
        mediaClient.stage = RemoteControlStage::operating;
        k_mutex_unlock(&mediaClientMutex);
        const int result = bt_mcc_set_current_track_obj_id(connection, object_id);
        if (result != 0)
        {
            finishMediaOperation(connection, result);
        }
        return record(mapMediaError(result), result);
#endif
    }

    Error MediaControlClient::end() noexcept
    {
        struct bt_conn *release = nullptr;
        k_mutex_lock(&mediaClientMutex, K_FOREVER);
        if (!started_ || (mediaClient.owner != this))
        {
            k_mutex_unlock(&mediaClientMutex);
            return record(Error::not_started);
        }
        release = mediaClient.connection;
        mediaClient.connection = nullptr;
        mediaClient.owner = nullptr;
        mediaClient.pending = false;
        mediaClient.refresh_pending = false;
        mediaClient.observed_track_id = 0U;
        mediaClient.observed_track_id_valid = false;
        mediaClient.stage = RemoteControlStage::idle;
        ++mediaClient.generation;
        started_ = false;
        generation_ = 0U;
        k_mutex_unlock(&mediaClientMutex);
        if (release != nullptr)
        {
            bt_conn_unref(release);
        }
        return record(Error::none);
    }

    bool MediaControlClient::ready() const noexcept
    {
        return stage() == RemoteControlStage::ready;
    }

    RemoteControlStage MediaControlClient::stage() const noexcept
    {
        k_mutex_lock(&mediaClientMutex, K_FOREVER);
        const RemoteControlStage value =
            started_ && (mediaClient.owner == this) && (mediaClient.generation == generation_)
                ? mediaClient.stage
                : RemoteControlStage::idle;
        k_mutex_unlock(&mediaClientMutex);
        return value;
    }

    MediaSnapshot MediaControlClient::snapshot() const noexcept
    {
        k_mutex_lock(&mediaClientMutex, K_FOREVER);
        const MediaSnapshot value =
            started_ && (mediaClient.owner == this) && (mediaClient.generation == generation_)
                ? mediaClient.snapshot
                : MediaSnapshot{};
        k_mutex_unlock(&mediaClientMutex);
        return value;
    }

    Error MediaControlClient::lastError() const noexcept
    {
        k_mutex_lock(&mediaClientMutex, K_FOREVER);
        const int error = (mediaClient.owner == this) ? mediaClient.error : 0;
        k_mutex_unlock(&mediaClientMutex);
        return error == 0 ? last_error_ : mapMediaError(error);
    }

    int MediaControlClient::nativeCode() const noexcept
    {
        k_mutex_lock(&mediaClientMutex, K_FOREVER);
        const int error = (mediaClient.owner == this) ? mediaClient.error : native_code_;
        k_mutex_unlock(&mediaClientMutex);
        return error;
    }

    Error MediaControlClient::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
#else
    Error MediaControlClient::begin(const BLEConnectionHandle &) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    void MediaControlClient::poll() noexcept
    {
    }
    Error MediaControlClient::refresh() noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlClient::command(MediaCommand) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlClient::commandOpcode(std::uint8_t) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlClient::moveRelative(std::int32_t) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlClient::setTrackPosition(std::int32_t) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlClient::selectTrack(std::uint64_t) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlClient::end() noexcept
    {
        return record(Error::not_started);
    }
    bool MediaControlClient::ready() const noexcept
    {
        return false;
    }
    RemoteControlStage MediaControlClient::stage() const noexcept
    {
        return RemoteControlStage::idle;
    }
    MediaSnapshot MediaControlClient::snapshot() const noexcept
    {
        return {};
    }
    Error MediaControlClient::lastError() const noexcept
    {
        return last_error_;
    }
    int MediaControlClient::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error MediaControlClient::record(Error error, int native_code) noexcept
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
    Error MediaControlPlayer::begin() noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlPlayer::end() noexcept
    {
        return record(Error::not_started);
    }
    bool MediaControlPlayer::ready() const noexcept
    {
        return false;
    }
    Error MediaControlPlayer::lastError() const noexcept
    {
        return last_error_;
    }
    int MediaControlPlayer::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error MediaControlPlayer::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    Error MediaControlClient::begin(const BLEConnectionHandle &) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    void MediaControlClient::poll() noexcept
    {
    }
    Error MediaControlClient::refresh() noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlClient::command(MediaCommand) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlClient::commandOpcode(std::uint8_t) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlClient::moveRelative(std::int32_t) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlClient::setTrackPosition(std::int32_t) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlClient::selectTrack(std::uint64_t) noexcept
    {
        return record(Error::unsupported, -ENOTSUP);
    }
    Error MediaControlClient::end() noexcept
    {
        return record(Error::not_started);
    }
    bool MediaControlClient::ready() const noexcept
    {
        return false;
    }
    RemoteControlStage MediaControlClient::stage() const noexcept
    {
        return RemoteControlStage::idle;
    }
    MediaSnapshot MediaControlClient::snapshot() const noexcept
    {
        return {};
    }
    Error MediaControlClient::lastError() const noexcept
    {
        return last_error_;
    }
    int MediaControlClient::nativeCode() const noexcept
    {
        return native_code_;
    }
    Error MediaControlClient::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
} // namespace nucode::ble::audio

#endif
