/**
 * @file NUCODE_BLE_Audio_BroadcastAssistant.cpp
 * @brief BASS Broadcast Assistant 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_BT_BAP_BROADCAST_ASSISTANT)

#include <NUCODE_BLE.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/audio/bap.h>
#include <zephyr/bluetooth/audio/audio.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        /** @brief 한 Arduino 객체가 소유하는 BASS client 상태입니다. */
        struct AssistantState
        {
            BroadcastAssistant *owner = nullptr;
            bt_conn *connection = nullptr;
            bt_addr_le_t source_address = {};
            std::uint32_t broadcast_id = 0U;
            std::uint32_t updates = 0U;
            std::uint32_t bis_sync = 0U;
            std::uint16_t periodic_interval = 0U;
            std::uint8_t source_sid = 0xffU;
            std::uint8_t receive_state_count = 0U;
            std::uint8_t source_id = 0xffU;
            std::uint8_t pa_state = BT_BAP_PA_STATE_NOT_SYNCED;
            bool selected = false;
            bool has_source = false;
            bool callbacks_registered = false;
            atomic_t stage = ATOMIC_INIT(
                static_cast<atomic_val_t>(BroadcastAssistantStage::idle));
            atomic_t busy = ATOMIC_INIT(0);
            atomic_t error = ATOMIC_INIT(0);
        };

        AssistantState assistant_state;

        /** @brief callback 오류와 비동기 단계를 한 곳에서 갱신합니다. */
        void completeOperation(bt_conn *connection, int error) noexcept
        {
            if ((assistant_state.owner == nullptr) ||
                (connection != assistant_state.connection))
            {
                return;
            }
            atomic_set(&assistant_state.error, error);
            atomic_set(&assistant_state.busy, 0);
            atomic_set(&assistant_state.stage,
                       static_cast<atomic_val_t>(BroadcastAssistantStage::ready));
        }

        /** @brief BASS 검색 결과와 receive state 슬롯 수를 저장합니다. */
        void discovered(bt_conn *connection, int error,
                        std::uint8_t receive_state_count) noexcept
        {
            if ((assistant_state.owner == nullptr) ||
                (connection != assistant_state.connection))
            {
                return;
            }
            if (error == 0)
            {
                assistant_state.receive_state_count = receive_state_count;
            }
            atomic_set(&assistant_state.error, error);
            atomic_set(&assistant_state.busy, 0);
            atomic_set(&assistant_state.stage,
                       static_cast<atomic_val_t>(error == 0
                                                     ? BroadcastAssistantStage::ready
                                                     : BroadcastAssistantStage::failed));
        }

        /** @brief receive state 통지를 bounded 공개 상태로 복사합니다. */
        void receiveState(bt_conn *connection, int error,
                          const bt_bap_scan_delegator_recv_state *state) noexcept
        {
            if ((assistant_state.owner == nullptr) ||
                (connection != assistant_state.connection))
            {
                return;
            }
            if (error != 0)
            {
                completeOperation(connection, error);
                return;
            }
            if (state == nullptr)
            {
                assistant_state.has_source = false;
                assistant_state.source_id = 0xffU;
                assistant_state.pa_state = BT_BAP_PA_STATE_NOT_SYNCED;
                assistant_state.bis_sync = 0U;
            }
            else
            {
                assistant_state.has_source = true;
                assistant_state.source_id = state->src_id;
                assistant_state.pa_state = state->pa_sync_state;
                assistant_state.bis_sync = state->num_subgroups == 0U
                                               ? 0U
                                               : state->subgroups[0].bis_sync;
            }
            ++assistant_state.updates;
            completeOperation(connection, 0);
        }

        /** @brief source 제거 통지를 공개 상태에 반영합니다. */
        void receiveStateRemoved(bt_conn *connection, std::uint8_t source_id) noexcept
        {
            if ((assistant_state.owner == nullptr) ||
                (connection != assistant_state.connection) ||
                (source_id != assistant_state.source_id))
            {
                return;
            }
            assistant_state.has_source = false;
            assistant_state.source_id = 0xffU;
            assistant_state.pa_state = BT_BAP_PA_STATE_NOT_SYNCED;
            assistant_state.bis_sync = 0U;
            ++assistant_state.updates;
        }

        /** @brief add source 쓰기 완료를 기록합니다. */
        void sourceAdded(bt_conn *connection, int error) noexcept
        {
            completeOperation(connection, error);
        }

        /** @brief modify source 쓰기 완료를 기록합니다. */
        void sourceModified(bt_conn *connection, int error) noexcept
        {
            completeOperation(connection, error);
        }

        /** @brief Broadcast Code 쓰기 완료를 기록합니다. */
        void codeWritten(bt_conn *connection, int error) noexcept
        {
            completeOperation(connection, error);
        }

        /** @brief remove source 쓰기 완료를 기록합니다. */
        void sourceRemoved(bt_conn *connection, int error) noexcept
        {
            completeOperation(connection, error);
        }

        bt_bap_broadcast_assistant_cb assistant_callbacks = {
            .discover = discovered,
            .recv_state = receiveState,
            .recv_state_removed = receiveStateRemoved,
            .add_src = sourceAdded,
            .mod_src = sourceModified,
            .broadcast_code = codeWritten,
            .rem_src = sourceRemoved,
        };

        /** @brief Arduino scan payload에서 24-bit Broadcast ID를 찾습니다. */
        bool findBroadcastId(const BLEScanResult &result,
                             std::uint32_t &broadcast_id) noexcept
        {
            std::size_t offset = 0U;
            while (offset < result.payload_length)
            {
                const std::uint8_t field_length = result.payload[offset];
                if (field_length == 0U)
                {
                    break;
                }
                const std::size_t next = offset + static_cast<std::size_t>(field_length) + 1U;
                if ((next > result.payload_length) || (field_length < 1U))
                {
                    return false;
                }
                const std::uint8_t type = result.payload[offset + 1U];
                const std::uint8_t *data = &result.payload[offset + 2U];
                const std::size_t data_length = static_cast<std::size_t>(field_length - 1U);
                if ((type == BT_DATA_SVC_DATA16) &&
                    (data_length >= BT_UUID_SIZE_16 + BT_AUDIO_BROADCAST_ID_SIZE) &&
                    (sys_get_le16(data) == BT_UUID_BROADCAST_AUDIO_VAL))
                {
                    broadcast_id = sys_get_le24(data + BT_UUID_SIZE_16);
                    return true;
                }
                offset = next;
            }
            return false;
        }

        /** @brief 공개 BLE 주소를 Zephyr little-endian 주소로 복사합니다. */
        bool copyAddress(const BLEAddress &source, bt_addr_le_t &destination) noexcept
        {
            if (!source.valid())
            {
                return false;
            }
            destination.type = source.type() == BLEAddress::Type::public_address
                                   ? BT_ADDR_LE_PUBLIC
                                   : BT_ADDR_LE_RANDOM;
            memcpy(destination.a.val, source.data(), sizeof(destination.a.val));
            return true;
        }

        /** @brief 새 비동기 BASS 요청을 시작할 수 있는지 확인합니다. */
        bool beginOperation(BroadcastAssistantStep step) noexcept
        {
            if ((assistant_state.owner == nullptr) ||
                (atomic_get(&assistant_state.stage) !=
                 static_cast<atomic_val_t>(BroadcastAssistantStage::ready)) ||
                !atomic_cas(&assistant_state.busy, 0, 1))
            {
                return false;
            }
            atomic_set(&assistant_state.stage,
                       static_cast<atomic_val_t>(BroadcastAssistantStage::operating));
            atomic_set(&assistant_state.error, 0);
            static_cast<void>(step);
            return true;
        }
    } // namespace

    /** @brief 마지막 공개 오류와 BASS/GATT 원본 오류를 기록합니다. */
    Error BroadcastAssistant::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    /** @brief 연결된 peer에서 BASS를 비동기로 검색합니다. */
    Error BroadcastAssistant::begin(const BLEConnectionHandle &connection) noexcept
    {
        if (started_)
        {
            return record(Error::already_started);
        }
        if (!BLEDevice.initialized())
        {
            return record(Error::not_ready);
        }
        if (!connection.valid())
        {
            return record(Error::invalid_argument);
        }
        if (assistant_state.owner != nullptr)
        {
            return record(Error::busy);
        }

        bt_conn *native_connection = internal::referenceConnection(connection);
        if (native_connection == nullptr)
        {
            return record(Error::not_connected);
        }

        assistant_state = {};
        assistant_state.owner = this;
        assistant_state.connection = native_connection;
        atomic_set(&assistant_state.stage,
                   static_cast<atomic_val_t>(BroadcastAssistantStage::discovering));
        atomic_set(&assistant_state.busy, 1);

        int result = bt_bap_broadcast_assistant_register_cb(&assistant_callbacks);
        assistant_state.callbacks_registered = result == 0;
        if (result == 0)
        {
            result = bt_bap_broadcast_assistant_discover(native_connection);
        }
        if (result != 0)
        {
            if (assistant_state.callbacks_registered)
            {
                (void)bt_bap_broadcast_assistant_unregister_cb(&assistant_callbacks);
            }
            bt_conn_unref(native_connection);
            assistant_state = {};
            return record(Error::stack_error, result);
        }

        started_ = true;
        stage_ = BroadcastAssistantStage::discovering;
        last_step_ = BroadcastAssistantStep::discover;
        return record(Error::none);
    }

    /** @brief scan 결과의 주소·SID·interval·Broadcast ID를 선택합니다. */
    Error BroadcastAssistant::selectSource(const BLEScanResult &result) noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        std::uint32_t broadcast_id = 0U;
        if ((stage() != BroadcastAssistantStage::ready) || result.connectable ||
            (result.periodic_interval == 0U) || (result.sid == 0xffU) ||
            !findBroadcastId(result, broadcast_id) ||
            !copyAddress(result.address, assistant_state.source_address))
        {
            return record(Error::invalid_argument);
        }
        assistant_state.broadcast_id = broadcast_id;
        assistant_state.source_sid = result.sid;
        assistant_state.periodic_interval = result.periodic_interval;
        assistant_state.selected = true;
        last_step_ = BroadcastAssistantStep::select_source;
        return record(Error::none);
    }

    /** @brief 선택한 source를 PA·BIS 1 동기화 요청과 함께 추가합니다. */
    Error BroadcastAssistant::addSource() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (!assistant_state.selected)
        {
            return record(Error::invalid_argument);
        }
        if (!beginOperation(BroadcastAssistantStep::add_source))
        {
            return record(Error::busy);
        }

        bt_bap_bass_subgroup subgroup = {
            .bis_sync = BT_BAP_BIS_SYNC_NO_PREF,
        };
        const bt_bap_broadcast_assistant_add_src_param parameters = {
            .addr = assistant_state.source_address,
            .adv_sid = assistant_state.source_sid,
            .pa_sync = true,
            .broadcast_id = assistant_state.broadcast_id,
            .pa_interval = assistant_state.periodic_interval,
            .num_subgroups = 1U,
            .subgroups = &subgroup,
        };
        last_step_ = BroadcastAssistantStep::add_source;
        const int result = bt_bap_broadcast_assistant_add_src(assistant_state.connection,
                                                               &parameters);
        if (result != 0)
        {
            completeOperation(assistant_state.connection, result);
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief 기존 source의 PA와 BIS 요청 상태를 갱신합니다. */
    Error BroadcastAssistant::modifySource(bool synchronize) noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (!assistant_state.has_source)
        {
            return record(Error::not_ready);
        }
        if (!beginOperation(BroadcastAssistantStep::modify_source))
        {
            return record(Error::busy);
        }

        bt_bap_bass_subgroup subgroup = {
            .bis_sync = synchronize ? BT_BAP_BIS_SYNC_NO_PREF : 0U,
        };
        const bt_bap_broadcast_assistant_mod_src_param parameters = {
            .src_id = assistant_state.source_id,
            .pa_sync = synchronize,
            .pa_interval = assistant_state.periodic_interval,
            .num_subgroups = 1U,
            .subgroups = &subgroup,
        };
        last_step_ = BroadcastAssistantStep::modify_source;
        const int result = bt_bap_broadcast_assistant_mod_src(assistant_state.connection,
                                                               &parameters);
        if (result != 0)
        {
            completeOperation(assistant_state.connection, result);
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief 현재 receive state에 암호화 Broadcast Code를 기록합니다. */
    Error BroadcastAssistant::setBroadcastCode(const BroadcastCode &broadcast_code) noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (!assistant_state.has_source)
        {
            return record(Error::not_ready);
        }
        if (!beginOperation(BroadcastAssistantStep::broadcast_code))
        {
            return record(Error::busy);
        }
        last_step_ = BroadcastAssistantStep::broadcast_code;
        const int result = bt_bap_broadcast_assistant_set_broadcast_code(
            assistant_state.connection, assistant_state.source_id, broadcast_code);
        if (result != 0)
        {
            completeOperation(assistant_state.connection, result);
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief 현재 receive state source를 제거합니다. */
    Error BroadcastAssistant::removeSource() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (!assistant_state.has_source)
        {
            return record(Error::not_ready);
        }
        if (!beginOperation(BroadcastAssistantStep::remove_source))
        {
            return record(Error::busy);
        }
        last_step_ = BroadcastAssistantStep::remove_source;
        const int result = bt_bap_broadcast_assistant_rem_src(assistant_state.connection,
                                                               assistant_state.source_id);
        if (result != 0)
        {
            completeOperation(assistant_state.connection, result);
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief 첫 receive state를 다시 읽습니다. */
    Error BroadcastAssistant::readState() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (assistant_state.receive_state_count == 0U)
        {
            return record(Error::not_ready);
        }
        if (!beginOperation(BroadcastAssistantStep::read_state))
        {
            return record(Error::busy);
        }
        last_step_ = BroadcastAssistantStep::read_state;
        const int result = bt_bap_broadcast_assistant_read_recv_state(
            assistant_state.connection, 0U);
        if (result != 0)
        {
            completeOperation(assistant_state.connection, result);
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief BASS callback과 connection reference를 반환합니다. */
    Error BroadcastAssistant::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        last_step_ = BroadcastAssistantStep::cleanup;
        int result = 0;
        if (assistant_state.callbacks_registered)
        {
            result = bt_bap_broadcast_assistant_unregister_cb(&assistant_callbacks);
        }
        if (assistant_state.connection != nullptr)
        {
            bt_conn_unref(assistant_state.connection);
        }
        assistant_state = {};
        started_ = false;
        stage_ = BroadcastAssistantStage::idle;
        if (result != 0)
        {
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief callback이 갱신한 BASS 비동기 단계를 반환합니다. */
    BroadcastAssistantStage BroadcastAssistant::stage() const noexcept
    {
        if (!started_ || (assistant_state.owner != this))
        {
            return stage_;
        }
        return static_cast<BroadcastAssistantStage>(atomic_get(&assistant_state.stage));
    }

    /** @brief 마지막 Assistant 요청을 반환합니다. */
    BroadcastAssistantStep BroadcastAssistant::lastStep() const noexcept
    {
        return last_step_;
    }

    /** @brief 검색된 receive state 슬롯 수를 반환합니다. */
    std::uint8_t BroadcastAssistant::receiveStateCount() const noexcept
    {
        return started_ ? assistant_state.receive_state_count : 0U;
    }

    /** @brief 유효한 receive state source가 있는지 반환합니다. */
    bool BroadcastAssistant::hasSource() const noexcept
    {
        return started_ && assistant_state.has_source;
    }

    /** @brief receive state source ID를 반환합니다. */
    std::uint8_t BroadcastAssistant::sourceId() const noexcept
    {
        return started_ ? assistant_state.source_id : 0xffU;
    }

    /** @brief PA sync 완료 여부를 반환합니다. */
    bool BroadcastAssistant::periodicSynchronized() const noexcept
    {
        return started_ && (assistant_state.pa_state == BT_BAP_PA_STATE_SYNCED);
    }

    /** @brief BIS 1 sync 완료 여부를 반환합니다. */
    bool BroadcastAssistant::bisSynchronized() const noexcept
    {
        return started_ &&
               ((assistant_state.bis_sync & BT_ISO_BIS_INDEX_BIT(1U)) != 0U);
    }

    /** @brief 수신한 receive state update 수를 반환합니다. */
    std::uint32_t BroadcastAssistant::stateUpdates() const noexcept
    {
        return started_ ? assistant_state.updates : 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error BroadcastAssistant::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 callback 또는 BASS/GATT 오류를 반환합니다. */
    int BroadcastAssistant::nativeCode() const noexcept
    {
        const int callback_error = atomic_get(&assistant_state.error);
        return callback_error != 0 ? callback_error : native_code_;
    }
} // namespace nucode::ble::audio

#else

namespace nucode::ble::audio
{
    Error BroadcastAssistant::begin(const BLEConnectionHandle &) noexcept
    {
        return record(Error::not_ready);
    }

    Error BroadcastAssistant::selectSource(const BLEScanResult &) noexcept
    {
        return record(Error::not_ready);
    }

    Error BroadcastAssistant::addSource() noexcept
    {
        return record(Error::not_ready);
    }

    Error BroadcastAssistant::modifySource(bool) noexcept
    {
        return record(Error::not_ready);
    }

    Error BroadcastAssistant::setBroadcastCode(const BroadcastCode &) noexcept
    {
        return record(Error::not_ready);
    }

    Error BroadcastAssistant::removeSource() noexcept
    {
        return record(Error::not_ready);
    }

    Error BroadcastAssistant::readState() noexcept
    {
        return record(Error::not_ready);
    }

    Error BroadcastAssistant::end() noexcept
    {
        return record(Error::not_started);
    }

    BroadcastAssistantStage BroadcastAssistant::stage() const noexcept
    {
        return stage_;
    }

    BroadcastAssistantStep BroadcastAssistant::lastStep() const noexcept
    {
        return last_step_;
    }

    std::uint8_t BroadcastAssistant::receiveStateCount() const noexcept
    {
        return 0U;
    }

    bool BroadcastAssistant::hasSource() const noexcept
    {
        return false;
    }

    std::uint8_t BroadcastAssistant::sourceId() const noexcept
    {
        return 0xffU;
    }

    bool BroadcastAssistant::periodicSynchronized() const noexcept
    {
        return false;
    }

    bool BroadcastAssistant::bisSynchronized() const noexcept
    {
        return false;
    }

    std::uint32_t BroadcastAssistant::stateUpdates() const noexcept
    {
        return 0U;
    }

    Error BroadcastAssistant::lastError() const noexcept
    {
        return last_error_;
    }

    int BroadcastAssistant::nativeCode() const noexcept
    {
        return native_code_;
    }

    Error BroadcastAssistant::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
} // namespace nucode::ble::audio

#endif
