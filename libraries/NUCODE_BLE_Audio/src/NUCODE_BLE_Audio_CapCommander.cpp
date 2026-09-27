/**
 * @file NUCODE_BLE_Audio_CapCommander.cpp
 * @brief CAP Commander broadcast 수신 절차 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_BT_CAP_COMMANDER) && \
    defined(CONFIG_BT_BAP_BROADCAST_ASSISTANT)

#include <NUCODE_BLE.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/audio/bap.h>
#include <zephyr/bluetooth/audio/cap.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/iso.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>

#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        /** @brief 한 Arduino 객체가 소유하는 CAP Commander 상태입니다. */
        struct CommanderState
        {
            CapCommander *owner = nullptr;
            bt_conn *connection = nullptr;
            bt_addr_le_t source_address = {};
            std::uint32_t broadcast_id = 0U;
            std::uint32_t updates = 0U;
            std::uint32_t bis_sync = 0U;
            std::uint16_t periodic_interval = 0U;
            std::uint8_t source_sid = 0xffU;
            std::uint8_t source_id = 0xffU;
            std::uint8_t pa_state = BT_BAP_PA_STATE_NOT_SYNCED;
            std::uint8_t receive_state_count = 0U;
            bool selected = false;
            bool has_source = false;
            bool cap_callbacks_registered = false;
            bool bass_callbacks_registered = false;
            atomic_t stage = ATOMIC_INIT(static_cast<atomic_val_t>(CapStage::idle));
            atomic_t step = ATOMIC_INIT(
                static_cast<atomic_val_t>(CapCommanderStep::none));
            atomic_t busy = ATOMIC_INIT(0);
            atomic_t error = ATOMIC_INIT(0);
        };

        CommanderState commander_state;

        /** @brief callback 오류와 공개 단계를 한 곳에서 갱신합니다. */
        void completeOperation(int error) noexcept
        {
            if (commander_state.owner == nullptr)
            {
                return;
            }
            atomic_set(&commander_state.error, error);
            atomic_set(&commander_state.busy, 0);
            atomic_set(&commander_state.stage,
                       static_cast<atomic_val_t>(error == 0 ? CapStage::ready
                                                           : CapStage::failed));
        }

        /** @brief BASS 검색 결과와 receive state 슬롯 수를 저장합니다. */
        void bassDiscovered(bt_conn *connection, int error,
                            std::uint8_t receive_state_count) noexcept
        {
            if ((commander_state.owner == nullptr) ||
                (connection != commander_state.connection))
            {
                return;
            }
            if (error == 0)
            {
                commander_state.receive_state_count = receive_state_count;
            }
            completeOperation(error);
        }

        /** @brief CAS 검색 뒤 같은 연결의 BASS 검색을 연속 실행합니다. */
        void capDiscovered(
            bt_conn *connection, int error,
            const bt_csip_set_coordinator_set_member *member,
            const bt_csip_set_coordinator_csis_inst *csis_instance) noexcept
        {
            static_cast<void>(member);
            static_cast<void>(csis_instance);
            if ((commander_state.owner == nullptr) ||
                (connection != commander_state.connection))
            {
                return;
            }
            if (error != 0)
            {
                completeOperation(error);
                return;
            }

            atomic_set(&commander_state.step,
                       static_cast<atomic_val_t>(CapCommanderStep::broadcast_assistant));
            const int result = bt_bap_broadcast_assistant_discover(connection);
            if (result != 0)
            {
                completeOperation(result);
            }
        }

        /** @brief receive state 통지를 bounded 공개 상태로 복사합니다. */
        void receiveState(bt_conn *connection, int error,
                          const bt_bap_scan_delegator_recv_state *state) noexcept
        {
            if ((commander_state.owner == nullptr) ||
                (connection != commander_state.connection))
            {
                return;
            }
            if (error != 0)
            {
                atomic_set(&commander_state.error, error);
                return;
            }
            if (state == nullptr)
            {
                commander_state.has_source = false;
                commander_state.source_id = 0xffU;
                commander_state.pa_state = BT_BAP_PA_STATE_NOT_SYNCED;
                commander_state.bis_sync = 0U;
            }
            else
            {
                commander_state.has_source = true;
                commander_state.source_id = state->src_id;
                commander_state.pa_state = state->pa_sync_state;
                commander_state.bis_sync = state->num_subgroups == 0U
                                               ? 0U
                                               : state->subgroups[0].bis_sync;
            }
            ++commander_state.updates;
        }

        /** @brief source 제거 통지를 공개 상태에 반영합니다. */
        void receiveStateRemoved(bt_conn *connection, std::uint8_t source_id) noexcept
        {
            if ((commander_state.owner == nullptr) ||
                (connection != commander_state.connection) ||
                (source_id != commander_state.source_id))
            {
                return;
            }
            commander_state.has_source = false;
            commander_state.source_id = 0xffU;
            commander_state.pa_state = BT_BAP_PA_STATE_NOT_SYNCED;
            commander_state.bis_sync = 0U;
            ++commander_state.updates;
        }

        /** @brief CAP broadcast 수신 시작 절차 완료를 기록합니다. */
        void receptionStarted(bt_conn *connection, int error) noexcept
        {
            if ((connection == nullptr) || (connection == commander_state.connection))
            {
                completeOperation(error);
            }
        }

        /** @brief CAP broadcast 수신 중단 절차 완료를 기록합니다. */
        void receptionStopped(bt_conn *connection, int error) noexcept
        {
            if ((connection == nullptr) || (connection == commander_state.connection))
            {
                completeOperation(error);
            }
        }

        /** @brief CAP Broadcast Code 배포 절차 완료를 기록합니다. */
        void codeDistributed(bt_conn *connection, int error) noexcept
        {
            if ((connection == nullptr) || (connection == commander_state.connection))
            {
                completeOperation(error);
            }
        }

        /** @brief BASS receive state 제거 완료를 기록합니다. */
        void sourceRemoved(bt_conn *connection, int error) noexcept
        {
            if (connection == commander_state.connection)
            {
                completeOperation(error);
            }
        }

        bt_cap_commander_cb cap_commander_callbacks = {
            .discovery_complete = capDiscovered,
            .broadcast_reception_start = receptionStarted,
            .broadcast_reception_stop = receptionStopped,
            .distribute_broadcast_code = codeDistributed,
        };

        bt_bap_broadcast_assistant_cb bass_callbacks = {
            .discover = bassDiscovered,
            .recv_state = receiveState,
            .recv_state_removed = receiveStateRemoved,
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
                const std::size_t next =
                    offset + static_cast<std::size_t>(field_length) + 1U;
                if ((next > result.payload_length) || (field_length < 1U))
                {
                    return false;
                }
                const std::uint8_t type = result.payload[offset + 1U];
                const std::uint8_t *data = &result.payload[offset + 2U];
                const std::size_t data_length =
                    static_cast<std::size_t>(field_length - 1U);
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

        /** @brief 새 CAP Commander 절차를 시작할 수 있는지 확인합니다. */
        bool beginOperation(CapCommanderStep step) noexcept
        {
            if ((commander_state.owner == nullptr) ||
                (atomic_get(&commander_state.stage) !=
                 static_cast<atomic_val_t>(CapStage::ready)) ||
                !atomic_cas(&commander_state.busy, 0, 1))
            {
                return false;
            }
            atomic_set(&commander_state.step, static_cast<atomic_val_t>(step));
            atomic_set(&commander_state.stage,
                       static_cast<atomic_val_t>(CapStage::operating));
            atomic_set(&commander_state.error, 0);
            return true;
        }
    } // namespace

    /** @brief 마지막 공개 오류와 CAP/BASS 원본 오류를 기록합니다. */
    Error CapCommander::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    /** @brief 연결된 peer에서 CAS와 BASS를 비동기로 검색합니다. */
    Error CapCommander::begin(const BLEConnectionHandle &connection) noexcept
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
        if (commander_state.owner != nullptr)
        {
            return record(Error::busy);
        }

        bt_conn *native_connection = internal::referenceConnection(connection);
        if (native_connection == nullptr)
        {
            return record(Error::not_connected);
        }

        commander_state = {};
        commander_state.owner = this;
        commander_state.connection = native_connection;
        atomic_set(&commander_state.stage,
                   static_cast<atomic_val_t>(CapStage::discovering));
        atomic_set(&commander_state.step,
                   static_cast<atomic_val_t>(CapCommanderStep::common_audio_service));
        atomic_set(&commander_state.busy, 1);

        int result = bt_cap_commander_register_cb(&cap_commander_callbacks);
        commander_state.cap_callbacks_registered = result == 0;
        if (result == 0)
        {
            result = bt_bap_broadcast_assistant_register_cb(&bass_callbacks);
            commander_state.bass_callbacks_registered = result == 0;
        }
        if (result == 0)
        {
            result = bt_cap_commander_discover(native_connection);
        }
        if (result != 0)
        {
            if (commander_state.bass_callbacks_registered)
            {
                (void)bt_bap_broadcast_assistant_unregister_cb(&bass_callbacks);
            }
            if (commander_state.cap_callbacks_registered)
            {
                (void)bt_cap_commander_unregister_cb(&cap_commander_callbacks);
            }
            bt_conn_unref(native_connection);
            commander_state = {};
            stage_ = CapStage::failed;
            return record(Error::stack_error, result);
        }

        started_ = true;
        stage_ = CapStage::discovering;
        last_step_ = CapCommanderStep::common_audio_service;
        return record(Error::none);
    }

    /** @brief scan 결과의 주소·SID·interval·Broadcast ID를 선택합니다. */
    Error CapCommander::selectSource(const BLEScanResult &result) noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        std::uint32_t broadcast_id = 0U;
        if (!ready() || result.connectable || (result.periodic_interval == 0U) ||
            (result.sid == 0xffU) || !findBroadcastId(result, broadcast_id) ||
            !copyAddress(result.address, commander_state.source_address))
        {
            return record(Error::invalid_argument);
        }
        commander_state.broadcast_id = broadcast_id;
        commander_state.source_sid = result.sid;
        commander_state.periodic_interval = result.periodic_interval;
        commander_state.selected = true;
        atomic_set(&commander_state.step,
                   static_cast<atomic_val_t>(CapCommanderStep::select_source));
        last_step_ = CapCommanderStep::select_source;
        return record(Error::none);
    }

    /** @brief CAP coordinated procedure로 source 수신 시작을 요청합니다. */
    Error CapCommander::startReception() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (!commander_state.selected)
        {
            return record(Error::invalid_argument);
        }
        if (commander_state.has_source)
        {
            return record(Error::already_started);
        }
        if (!beginOperation(CapCommanderStep::start_reception))
        {
            return record(Error::busy);
        }

        bt_cap_commander_broadcast_reception_start_member_param member = {};
        member.member.member = commander_state.connection;
        member.addr = commander_state.source_address;
        member.adv_sid = commander_state.source_sid;
        member.pa_interval = commander_state.periodic_interval;
        member.broadcast_id = commander_state.broadcast_id;
        member.subgroups[0].bis_sync = BT_ISO_BIS_INDEX_BIT(1U);
        member.num_subgroups = 1U;
        const bt_cap_commander_broadcast_reception_start_param parameters = {
            .type = BT_CAP_SET_TYPE_AD_HOC,
            .param = &member,
            .count = 1U,
        };
        last_step_ = CapCommanderStep::start_reception;
        const int result = bt_cap_commander_broadcast_reception_start(&parameters);
        if (result != 0)
        {
            completeOperation(result);
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief CAP coordinated procedure로 Broadcast Code를 배포합니다. */
    Error CapCommander::distributeBroadcastCode(
        const BroadcastCode &broadcast_code) noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (!commander_state.has_source)
        {
            return record(Error::not_ready);
        }
        if (!beginOperation(CapCommanderStep::distribute_code))
        {
            return record(Error::busy);
        }

        bt_cap_commander_distribute_broadcast_code_member_param member = {};
        member.member.member = commander_state.connection;
        member.src_id = commander_state.source_id;
        bt_cap_commander_distribute_broadcast_code_param parameters = {
            .type = BT_CAP_SET_TYPE_AD_HOC,
            .param = &member,
            .count = 1U,
        };
        memcpy(parameters.broadcast_code, broadcast_code,
               sizeof(parameters.broadcast_code));
        last_step_ = CapCommanderStep::distribute_code;
        const int result = bt_cap_commander_distribute_broadcast_code(&parameters);
        if (result != 0)
        {
            completeOperation(result);
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief CAP coordinated procedure로 source 수신 중단을 요청합니다. */
    Error CapCommander::stopReception() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (!commander_state.has_source)
        {
            return record(Error::not_ready);
        }
        if (!beginOperation(CapCommanderStep::stop_reception))
        {
            return record(Error::busy);
        }

        bt_cap_commander_broadcast_reception_stop_member_param member = {};
        member.member.member = commander_state.connection;
        member.src_id = commander_state.source_id;
        member.num_subgroups = 1U;
        const bt_cap_commander_broadcast_reception_stop_param parameters = {
            .type = BT_CAP_SET_TYPE_AD_HOC,
            .param = &member,
            .count = 1U,
        };
        last_step_ = CapCommanderStep::stop_reception;
        const int result = bt_cap_commander_broadcast_reception_stop(&parameters);
        if (result != 0)
        {
            completeOperation(result);
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief 중단된 source의 BASS receive state를 제거합니다. */
    Error CapCommander::removeSource() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        if (!commander_state.has_source)
        {
            return record(Error::not_ready);
        }
        if (!beginOperation(CapCommanderStep::remove_source))
        {
            return record(Error::busy);
        }
        last_step_ = CapCommanderStep::remove_source;
        const int result = bt_bap_broadcast_assistant_rem_src(
            commander_state.connection, commander_state.source_id);
        if (result != 0)
        {
            completeOperation(result);
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief CAP/BASS callback과 connection reference를 반환합니다. */
    Error CapCommander::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }

        last_step_ = CapCommanderStep::cleanup;
        if (atomic_get(&commander_state.busy) != 0)
        {
            (void)bt_cap_commander_cancel();
        }
        int result = 0;
        if (commander_state.bass_callbacks_registered)
        {
            result = bt_bap_broadcast_assistant_unregister_cb(&bass_callbacks);
        }
        if (commander_state.cap_callbacks_registered)
        {
            const int cap_result =
                bt_cap_commander_unregister_cb(&cap_commander_callbacks);
            if (result == 0)
            {
                result = cap_result;
            }
        }
        if (commander_state.connection != nullptr)
        {
            bt_conn_unref(commander_state.connection);
        }
        commander_state = {};
        started_ = false;
        stage_ = CapStage::idle;
        if (result != 0)
        {
            return record(Error::stack_error, result);
        }
        return record(Error::none);
    }

    /** @brief callback이 갱신한 CAP Commander 단계를 반환합니다. */
    CapStage CapCommander::stage() const noexcept
    {
        if (!started_ || (commander_state.owner != this))
        {
            return stage_;
        }
        return static_cast<CapStage>(atomic_get(&commander_state.stage));
    }

    /** @brief 마지막 CAP Commander 작업을 반환합니다. */
    CapCommanderStep CapCommander::lastStep() const noexcept
    {
        if (!started_ || (commander_state.owner != this))
        {
            return last_step_;
        }
        return static_cast<CapCommanderStep>(atomic_get(&commander_state.step));
    }

    /** @brief CAS와 BASS 검색 완료 여부를 반환합니다. */
    bool CapCommander::ready() const noexcept
    {
        return stage() == CapStage::ready;
    }

    /** @brief 유효한 receive state source가 있는지 반환합니다. */
    bool CapCommander::hasSource() const noexcept
    {
        return started_ && commander_state.has_source;
    }

    /** @brief receive state source ID를 반환합니다. */
    std::uint8_t CapCommander::sourceId() const noexcept
    {
        return started_ ? commander_state.source_id : 0xffU;
    }

    /** @brief PA sync 완료 여부를 반환합니다. */
    bool CapCommander::periodicSynchronized() const noexcept
    {
        return started_ && (commander_state.pa_state == BT_BAP_PA_STATE_SYNCED);
    }

    /** @brief BIS 1 sync 완료 여부를 반환합니다. */
    bool CapCommander::bisSynchronized() const noexcept
    {
        return started_ &&
               ((commander_state.bis_sync & BT_ISO_BIS_INDEX_BIT(1U)) != 0U);
    }

    /** @brief receive state update 수를 반환합니다. */
    std::uint32_t CapCommander::stateUpdates() const noexcept
    {
        return started_ ? commander_state.updates : 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error CapCommander::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 callback 또는 CAP/BASS 오류를 반환합니다. */
    int CapCommander::nativeCode() const noexcept
    {
        const int callback_error = atomic_get(&commander_state.error);
        return callback_error != 0 ? callback_error : native_code_;
    }
} // namespace nucode::ble::audio

#else

namespace nucode::ble::audio
{
    Error CapCommander::begin(const BLEConnectionHandle &) noexcept
    {
        stage_ = CapStage::failed;
        return record(Error::not_ready);
    }

    Error CapCommander::selectSource(const BLEScanResult &) noexcept
    {
        return record(Error::not_ready);
    }

    Error CapCommander::startReception() noexcept
    {
        return record(Error::not_ready);
    }

    Error CapCommander::distributeBroadcastCode(const BroadcastCode &) noexcept
    {
        return record(Error::not_ready);
    }

    Error CapCommander::stopReception() noexcept
    {
        return record(Error::not_ready);
    }

    Error CapCommander::removeSource() noexcept
    {
        return record(Error::not_ready);
    }

    Error CapCommander::end() noexcept
    {
        return record(Error::not_started);
    }

    CapStage CapCommander::stage() const noexcept
    {
        return stage_;
    }

    CapCommanderStep CapCommander::lastStep() const noexcept
    {
        return last_step_;
    }

    bool CapCommander::ready() const noexcept
    {
        return false;
    }

    bool CapCommander::hasSource() const noexcept
    {
        return false;
    }

    std::uint8_t CapCommander::sourceId() const noexcept
    {
        return 0xffU;
    }

    bool CapCommander::periodicSynchronized() const noexcept
    {
        return false;
    }

    bool CapCommander::bisSynchronized() const noexcept
    {
        return false;
    }

    std::uint32_t CapCommander::stateUpdates() const noexcept
    {
        return 0U;
    }

    Error CapCommander::lastError() const noexcept
    {
        return last_error_;
    }

    int CapCommander::nativeCode() const noexcept
    {
        return native_code_;
    }

    Error CapCommander::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
} // namespace nucode::ble::audio

#endif
