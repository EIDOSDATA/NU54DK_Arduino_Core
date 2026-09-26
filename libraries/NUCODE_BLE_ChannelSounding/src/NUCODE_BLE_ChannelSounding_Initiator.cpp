/**
 * @file NUCODE_BLE_ChannelSounding_Initiator.cpp
 * @brief Ranging Requestor의 보안·GATT·CS·raw step 구현입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_ChannelSounding.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_NUCODE_BLE_CS_INITIATOR)

extern "C"
{
#include <bluetooth/gatt_dm.h>
#include <bluetooth/services/ras.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/cs.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/atomic.h>
}

#include <internal/NUCODE_BLE_Internal.h>

namespace nucode::ble::cs
{
    namespace
    {
        constexpr std::uint8_t config_id = 0U;
        constexpr std::size_t local_capacity =
            (BT_RAS_MAX_STEPS_PER_PROCEDURE * sizeof(bt_le_cs_subevent_step)) +
            (BT_RAS_MAX_STEPS_PER_PROCEDURE * BT_RAS_MAX_STEP_DATA_LEN);

        NET_BUF_SIMPLE_DEFINE_STATIC(local_steps, local_capacity);
        NET_BUF_SIMPLE_DEFINE_STATIC(peer_steps, BT_RAS_PROCEDURE_MEM);
        K_MSGQ_DEFINE(reading_queue, sizeof(RasReading), 8, 4);

        /** @brief 완료 callback이 Arduino main에 전달하는 단일 단계 결과입니다. */
        enum class NativeEvent : int
        {
            none = 0,
            secured,
            mtu_exchanged,
            discovered,
            features_read,
            capabilities_read,
            configured,
            cs_secured,
            procedure_changed,
        };

        /** @brief 단일 initiator의 controller·RAS callback 상태입니다. */
        struct InitiatorState
        {
            atomic_ptr_t owner = nullptr;
            atomic_ptr_t connection = nullptr;
            atomic_t event = 0;
            atomic_t error = 0;
            atomic_t ras_features = 0;
            atomic_t procedure_enabled = 0;
            atomic_t procedure_pending = 0;
            atomic_t local_busy = 0;
            atomic_t completed = 0;
            atomic_t local_busy_drops = 0;
            atomic_t local_overflows = 0;
            atomic_t procedure_aborts = 0;
            atomic_t subevent_aborts = 0;
            atomic_t ras_counter_mismatches = 0;
            atomic_t ras_errors = 0;
            atomic_t local_missing = 0;
            atomic_t invalid_readings = 0;
            atomic_t reading_queue_full = 0;
            bool rreq_allocated = false;
            int32_t local_counter = -1;
            int32_t dropped_counter = -1;
            bt_conn_le_cs_config config = {};
            bt_gatt_exchange_params mtu_parameters = {};
        };

        InitiatorState state;

        /** @brief 이 객체가 소유한 연결의 callback인지 판정합니다. */
        bool sameConnection(bt_conn *connection)
        {
            return (atomic_ptr_get(&state.owner) != nullptr) &&
                   (atomic_ptr_get(&state.connection) == connection);
        }

        /** @brief 비동기 실패를 Arduino main에 전달합니다. */
        void fail(int error)
        {
            atomic_set(&state.error, (error == 0) ? -1 : error);
        }

        /** @brief L2 보안 완료를 알립니다. */
        void securityChanged(bt_conn *connection, bt_security_t level,
                             bt_security_err error)
        {
            if (!sameConnection(connection))
            {
                return;
            }
            if (error != BT_SECURITY_ERR_SUCCESS)
            {
                fail(static_cast<int>(error));
            }
            else if (level >= BT_SECURITY_L2)
            {
                atomic_set(&state.event, static_cast<int>(NativeEvent::secured));
            }
        }

        /** @brief ATT MTU 교환 결과를 알립니다. */
        void mtuExchanged(bt_conn *connection, std::uint8_t error,
                          bt_gatt_exchange_params *parameters)
        {
            static_cast<void>(parameters);
            if (!sameConnection(connection))
            {
                return;
            }
            if (error != 0U)
            {
                fail(error);
            }
            else
            {
                atomic_set(&state.event, static_cast<int>(NativeEvent::mtu_exchanged));
            }
        }

        /** @brief Ranging Service handle을 할당하고 탐색 자원을 반환합니다. */
        void discovered(bt_gatt_dm *discovery, void *context)
        {
            static_cast<void>(context);
            bt_conn *connection = bt_gatt_dm_conn_get(discovery);
            if (sameConnection(connection))
            {
                const int result = bt_ras_rreq_alloc_and_assign_handles(discovery, connection);
                if (result == 0)
                {
                    state.rreq_allocated = true;
                    atomic_set(&state.event, static_cast<int>(NativeEvent::discovered));
                }
                else
                {
                    fail(result);
                }
            }
            (void)bt_gatt_dm_data_release(discovery);
        }

        /** @brief 대상 peer에 Ranging Service가 없으면 실패로 기록합니다. */
        void serviceMissing(bt_conn *connection, void *context)
        {
            static_cast<void>(context);
            if (sameConnection(connection))
            {
                fail(-2);
            }
        }

        /** @brief GATT 탐색 오류를 기록합니다. */
        void discoveryError(bt_conn *connection, int error, void *context)
        {
            static_cast<void>(context);
            if (sameConnection(connection))
            {
                fail(error);
            }
        }

        bt_gatt_dm_cb discovery_callbacks = {
            .completed = discovered,
            .service_not_found = serviceMissing,
            .error_found = discoveryError,
        };

        /** @brief RAS 실시간 데이터 지원 여부를 저장합니다. */
        void featuresRead(bt_conn *connection, std::uint32_t bits, int error)
        {
            if (!sameConnection(connection))
            {
                return;
            }
            if (error != 0)
            {
                fail(error);
            }
            else
            {
                atomic_set(&state.ras_features, static_cast<atomic_val_t>(bits));
                atomic_set(&state.event, static_cast<int>(NativeEvent::features_read));
            }
        }

        /** @brief 상대 controller의 CS capability 교환 결과를 저장합니다. */
        void capabilitiesRead(bt_conn *connection, std::uint8_t status,
                              bt_conn_le_cs_capabilities *capabilities)
        {
            static_cast<void>(capabilities);
            if (sameConnection(connection))
            {
                if (status != 0U)
                {
                    fail(status);
                }
                else
                {
                    atomic_set(&state.event,
                               static_cast<int>(NativeEvent::capabilities_read));
                }
            }
        }

        /** @brief 두 장치에 생성된 CS 설정을 보존합니다. */
        void configured(bt_conn *connection, std::uint8_t status,
                        bt_conn_le_cs_config *config)
        {
            if (!sameConnection(connection))
            {
                return;
            }
            if ((status != 0U) || (config == nullptr))
            {
                fail(status);
            }
            else
            {
                state.config = *config;
                atomic_set(&state.event, static_cast<int>(NativeEvent::configured));
            }
        }

        /** @brief CS 보안 절차의 완료를 저장합니다. */
        void csSecured(bt_conn *connection, std::uint8_t status)
        {
            if (sameConnection(connection))
            {
                if (status != 0U)
                {
                    fail(status);
                }
                else
                {
                    atomic_set(&state.event, static_cast<int>(NativeEvent::cs_secured));
                }
            }
        }

        /** @brief CS procedure 활성·중단 결과를 저장합니다. */
        void procedureChanged(bt_conn *connection, std::uint8_t status,
                              bt_conn_le_cs_procedure_enable_complete *parameters)
        {
            if (!sameConnection(connection))
            {
                return;
            }
            if ((status != 0U) || (parameters == nullptr))
            {
                fail(status);
            }
            else
            {
                atomic_set(&state.procedure_enabled, parameters->state == 1U ? 1 : 0);
                atomic_set(&state.event,
                           static_cast<int>(NativeEvent::procedure_changed));
            }
        }

        /** @brief 양쪽 RAS header가 유효하면 계속 파싱합니다. */
        bool parseHeader(ras_ranging_header *header, void *context)
        {
            static_cast<void>(header);
            static_cast<void>(context);
            return true;
        }

        /** @brief 한 procedure에서 유효한 mode 1 왕복 시간을 합산합니다. */
        struct ReadingContext
        {
            RasReading reading = {};
            std::int32_t rtt_half_ns = 0;
        };

        /** @brief 같은 counter의 step을 계수하고 mode 1 왕복 시간을 검증합니다. */
        bool parseStep(bt_le_cs_subevent_step *local, bt_le_cs_subevent_step *remote,
                       void *context)
        {
            ReadingContext *measurement = static_cast<ReadingContext *>(context);
            RasReading *reading = &measurement->reading;
            if ((local == nullptr) || (remote == nullptr))
            {
                return false;
            }
            ++reading->local_steps;
            ++reading->peer_steps;
            if (local->mode == BT_HCI_OP_LE_CS_MAIN_MODE_1)
            {
                ++reading->mode_1_steps;
                if ((remote->mode == BT_HCI_OP_LE_CS_MAIN_MODE_1) &&
                    (local->data_len >= sizeof(bt_hci_le_cs_step_data_mode_1)) &&
                    (remote->data_len >= sizeof(bt_hci_le_cs_step_data_mode_1)))
                {
                    const auto *local_data =
                        reinterpret_cast<const bt_hci_le_cs_step_data_mode_1 *>(local->data);
                    const auto *remote_data =
                        reinterpret_cast<const bt_hci_le_cs_step_data_mode_1 *>(remote->data);
                    if ((local_data->packet_quality_aa_check ==
                         BT_HCI_LE_CS_PACKET_QUALITY_AA_CHECK_SUCCESSFUL) &&
                        (remote_data->packet_quality_aa_check ==
                         BT_HCI_LE_CS_PACKET_QUALITY_AA_CHECK_SUCCESSFUL) &&
                        (local_data->packet_rssi != BT_HCI_LE_CS_PACKET_RSSI_NOT_AVAILABLE) &&
                        (remote_data->packet_rssi != BT_HCI_LE_CS_PACKET_RSSI_NOT_AVAILABLE) &&
                        (local_data->tod_toa_reflector !=
                         BT_HCI_LE_CS_TIME_DIFFERENCE_NOT_AVAILABLE) &&
                        (remote_data->tod_toa_reflector !=
                         BT_HCI_LE_CS_TIME_DIFFERENCE_NOT_AVAILABLE))
                    {
                        measurement->rtt_half_ns += local_data->toa_tod_initiator -
                                                    remote_data->tod_toa_reflector;
                        ++reading->valid_rtt_samples;
                    }
                }
            }
            else if (local->mode == BT_HCI_OP_LE_CS_MAIN_MODE_2)
            {
                ++reading->mode_2_steps;
            }
            return true;
        }

        /** @brief 상대 RAS data가 완성되면 raw step 대조 결과를 queue에 저장합니다. */
        void rangingData(bt_conn *connection, std::uint16_t counter, int error)
        {
            if (!sameConnection(connection))
            {
                return;
            }
            if (counter != state.local_counter)
            {
                /** @note 늦게 도착한 이전 RAS가 현재 절차의 로컬 step을 지우지 않게 합니다. */
                atomic_inc(&state.ras_counter_mismatches);
                return;
            }
            if (error != 0)
            {
                atomic_inc(&state.ras_errors);
                net_buf_simple_reset(&local_steps);
                atomic_set(&state.local_busy, 0);
                fail(error);
                return;
            }
            if (local_steps.len == 0U)
            {
                atomic_inc(&state.local_missing);
                atomic_set(&state.local_busy, 0);
                return;
            }

            ReadingContext measurement = {};
            measurement.reading.ranging_counter = counter;
            bt_ras_rreq_rd_subevent_data_parse(&peer_steps, &local_steps,
                                               state.config.role, parseHeader,
                                               nullptr, parseStep, &measurement);
            RasReading &reading = measurement.reading;
            if (reading.valid_rtt_samples > 0U)
            {
                const float meters =
                    (static_cast<float>(measurement.rtt_half_ns) * 0.5F * 0.5F *
                     0.299792458F) /
                    static_cast<float>(reading.valid_rtt_samples);
                reading.rtt_distance_meters = (meters > 0.0F) ? meters : 0.0F;
            }
            net_buf_simple_reset(&local_steps);
            atomic_set(&state.local_busy, 0);
            if ((reading.local_steps > 0U) && (reading.valid_rtt_samples == 0U))
            {
                /** @note 유효 RTT가 없는 단편 RAS는 거리 결과로 공개하지 않습니다. */
                atomic_inc(&state.invalid_readings);
            }
            else if (reading.local_steps > 0U)
            {
                if (k_msgq_put(&reading_queue, &reading, K_NO_WAIT) == 0)
                {
                    atomic_inc(&state.completed);
                }
                else
                {
                    atomic_inc(&state.reading_queue_full);
                }
            }
        }

        /** @brief 같은 procedure의 로컬 step byte를 고정 버퍼에 누적합니다. */
        void subeventResult(bt_conn *connection, bt_conn_le_cs_subevent_result *result)
        {
            if (!sameConnection(connection) || (result == nullptr))
            {
                return;
            }
            const int32_t counter =
                bt_ras_rreq_get_ranging_counter(result->header.procedure_counter);
            if (state.dropped_counter == counter)
            {
                return;
            }
            if (state.local_counter != counter)
            {
                if (!atomic_cas(&state.local_busy, 0, 1))
                {
                    atomic_inc(&state.local_busy_drops);
                    state.dropped_counter = counter;
                    return;
                }
                state.local_counter = counter;
            }
            if (result->header.procedure_done_status == BT_CONN_LE_CS_PROCEDURE_ABORTED)
            {
                /** @note 중단된 절차에는 RAS 통지가 없을 수 있으므로 잠금을 반환합니다. */
                atomic_inc(&state.procedure_aborts);
                net_buf_simple_reset(&local_steps);
                atomic_set(&state.local_busy, 0);
                state.dropped_counter = counter;
                return;
            }
            if (result->header.subevent_done_status == BT_CONN_LE_CS_SUBEVENT_ABORTED)
            {
                /** @note 같은 절차의 다음 subevent는 유효할 수 있으므로 다시 수집합니다. */
                atomic_inc(&state.subevent_aborts);
                net_buf_simple_reset(&local_steps);
                atomic_set(&state.local_busy, 0);
                state.local_counter = -1;
                return;
            }
            if (result->step_data_buf != nullptr)
            {
                const std::uint16_t length = result->step_data_buf->len;
                if (length > net_buf_simple_tailroom(&local_steps))
                {
                    atomic_inc(&state.local_overflows);
                    net_buf_simple_reset(&local_steps);
                    atomic_set(&state.local_busy, 0);
                    state.dropped_counter = counter;
                    return;
                }
                std::uint8_t *bytes = static_cast<std::uint8_t *>(
                    net_buf_simple_pull_mem(result->step_data_buf, length));
                net_buf_simple_add_mem(&local_steps, bytes, length);
            }
            state.dropped_counter = -1;
        }

        BT_CONN_CB_DEFINE(nucode_ras_initiator_callbacks) = {
            .security_changed = securityChanged,
            .le_cs_read_remote_capabilities_complete = capabilitiesRead,
            .le_cs_config_complete = configured,
            .le_cs_subevent_data_available = subeventResult,
            .le_cs_security_enable_complete = csSecured,
            .le_cs_procedure_enable_complete = procedureChanged,
        };
    }

    /** @brief 공개 오류와 원본 controller·Host 코드를 저장합니다. */
    Error RasInitiator::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        if (error == Error::controller_error)
        {
            stage_ = InitiatorStage::failed;
        }
        return error;
    }

    /** @brief 공개 연결 reference를 확보하고 L2 보안을 요청합니다. */
    Error RasInitiator::begin(BLEConnectionHandle connection) noexcept
    {
        if (!connection.valid())
        {
            return record(Error::invalid_argument);
        }
        if (state_ != nullptr)
        {
            return record(Error::already_started);
        }
        if (!atomic_ptr_cas(&state.owner, nullptr, this))
        {
            return record(Error::busy);
        }
        bt_conn *native_connection = internal::referenceConnection(connection);
        if (native_connection == nullptr)
        {
            atomic_ptr_set(&state.owner, nullptr);
            return record(Error::not_connected);
        }
        atomic_ptr_set(&state.connection, native_connection);
        atomic_set(&state.event, 0);
        atomic_set(&state.error, 0);
        atomic_set(&state.ras_features, 0);
        atomic_set(&state.procedure_enabled, 0);
        atomic_set(&state.procedure_pending, 0);
        atomic_set(&state.local_busy, 0);
        atomic_set(&state.completed, 0);
        atomic_set(&state.local_busy_drops, 0);
        atomic_set(&state.local_overflows, 0);
        atomic_set(&state.procedure_aborts, 0);
        atomic_set(&state.subevent_aborts, 0);
        atomic_set(&state.ras_counter_mismatches, 0);
        atomic_set(&state.ras_errors, 0);
        atomic_set(&state.local_missing, 0);
        atomic_set(&state.invalid_readings, 0);
        atomic_set(&state.reading_queue_full, 0);
        state.rreq_allocated = false;
        state.local_counter = -1;
        state.dropped_counter = -1;
        net_buf_simple_reset(&local_steps);
        net_buf_simple_reset(&peer_steps);
        k_msgq_purge(&reading_queue);
        state_ = &state;
        stage_ = InitiatorStage::securing;
        if (bt_conn_get_security(native_connection) >= BT_SECURITY_L2)
        {
            atomic_set(&state.event, static_cast<int>(NativeEvent::secured));
        }
        else
        {
            const int result = bt_conn_set_security(native_connection, BT_SECURITY_L2);
            if (result != 0)
            {
                end();
                return record(Error::controller_error, result);
            }
        }
        return record(Error::none);
    }

    /** @brief 비동기 단계 결과를 한 번씩 소비해 다음 요청을 시작합니다. */
    void RasInitiator::poll() noexcept
    {
        if ((state_ == nullptr) || (stage_ == InitiatorStage::failed))
        {
            return;
        }
        const int error = atomic_set(&state.error, 0);
        if (error != 0)
        {
            (void)record(Error::controller_error, error);
            return;
        }
        const NativeEvent event = static_cast<NativeEvent>(atomic_set(&state.event, 0));
        if (event == NativeEvent::none)
        {
            return;
        }
        bt_conn *connection = static_cast<bt_conn *>(atomic_ptr_get(&state.connection));
        if (connection == nullptr)
        {
            (void)record(Error::not_connected);
            return;
        }

        int result = 0;
        if (event == NativeEvent::secured)
        {
            stage_ = InitiatorStage::discovering;
            state.mtu_parameters.func = mtuExchanged;
            result = bt_gatt_exchange_mtu(connection, &state.mtu_parameters);
        }
        else if (event == NativeEvent::mtu_exchanged)
        {
            result = bt_gatt_dm_start(connection, BT_UUID_RANGING_SERVICE,
                                      &discovery_callbacks, nullptr);
        }
        else if (event == NativeEvent::discovered)
        {
            bt_le_cs_set_default_settings_param settings = {};
            settings.enable_initiator_role = true;
            settings.enable_reflector_role = false;
            settings.cs_sync_antenna_selection = BT_LE_CS_ANTENNA_SELECTION_OPT_REPETITIVE;
            settings.max_tx_power = BT_HCI_OP_LE_CS_MAX_MAX_TX_POWER;
            result = bt_le_cs_set_default_settings(connection, &settings);
            if (result == 0)
            {
                result = bt_ras_rreq_read_features(connection, featuresRead);
            }
        }
        else if (event == NativeEvent::features_read)
        {
            if ((atomic_get(&state.ras_features) & RAS_FEAT_REALTIME_RD) == 0)
            {
                last_error_ = Error::unsupported;
                stage_ = InitiatorStage::failed;
                return;
            }
            result = bt_ras_rreq_realtime_rd_subscribe(connection, &peer_steps, rangingData);
            if (result == 0)
            {
                stage_ = InitiatorStage::configuring;
                result = bt_le_cs_read_remote_supported_capabilities(connection);
            }
        }
        else if (event == NativeEvent::capabilities_read)
        {
            bt_le_cs_create_config_params config = {};
            config.id = config_id;
            config.mode = BT_CONN_LE_CS_MAIN_MODE_2_SUB_MODE_1;
            config.min_main_mode_steps = 2U;
            config.max_main_mode_steps = 5U;
            config.main_mode_repetition = 0U;
            config.mode_0_steps = 3U;
            config.role = BT_CONN_LE_CS_ROLE_INITIATOR;
            config.rtt_type = BT_CONN_LE_CS_RTT_TYPE_AA_ONLY;
            config.cs_sync_phy = BT_CONN_LE_CS_SYNC_1M_PHY;
            config.channel_map_repetition = 1U;
            config.channel_selection_type = BT_CONN_LE_CS_CHSEL_TYPE_3B;
            config.ch3c_shape = BT_CONN_LE_CS_CH3C_SHAPE_HAT;
            config.ch3c_jump = 2U;
            bt_le_cs_set_valid_chmap_bits(config.channel_map);
            result = bt_le_cs_create_config(connection, &config,
                                            BT_LE_CS_CREATE_CONFIG_CONTEXT_LOCAL_AND_REMOTE);
        }
        else if (event == NativeEvent::configured)
        {
            result = bt_le_cs_security_enable(connection);
        }
        else if (event == NativeEvent::cs_secured)
        {
            stage_ = InitiatorStage::ready;
        }
        else if (event == NativeEvent::procedure_changed)
        {
            atomic_set(&state.procedure_pending, 0);
            stage_ = (atomic_get(&state.procedure_enabled) != 0) ?
                         InitiatorStage::ranging : InitiatorStage::ready;
        }
        if (result != 0)
        {
            (void)record(Error::controller_error, result);
        }
    }

    /** @brief 준비된 연결의 CS 절차를 시작합니다. */
    Error RasInitiator::start() noexcept
    {
        if ((state_ == nullptr) || (stage_ != InitiatorStage::ready) ||
            (atomic_get(&state.procedure_pending) != 0))
        {
            return record(Error::not_ready);
        }
        bt_conn *connection = static_cast<bt_conn *>(atomic_ptr_get(&state.connection));
        bt_le_cs_set_procedure_parameters_param parameters = {};
        parameters.config_id = config_id;
        parameters.max_procedure_len = 128U;
        parameters.min_procedure_interval = 5U;
        parameters.max_procedure_interval = 5U;
        parameters.max_procedure_count = 0U;
        parameters.min_subevent_len = 16000U;
        parameters.max_subevent_len = 16000U;
        parameters.tone_antenna_config_selection =
            BT_LE_CS_TONE_ANTENNA_CONFIGURATION_A1_B1;
        parameters.phy = BT_LE_CS_PROCEDURE_PHY_2M;
        parameters.tx_power_delta = 0x80U;
        parameters.preferred_peer_antenna = BT_LE_CS_PROCEDURE_PREFERRED_PEER_ANTENNA_1;
        parameters.snr_control_initiator = BT_LE_CS_SNR_CONTROL_NOT_USED;
        parameters.snr_control_reflector = BT_LE_CS_SNR_CONTROL_NOT_USED;
        int result = bt_le_cs_set_procedure_parameters(connection, &parameters);
        if (result == 0)
        {
            bt_le_cs_procedure_enable_param enable = {};
            enable.config_id = config_id;
            enable.enable = BT_CONN_LE_CS_PROCEDURES_ENABLED;
            result = bt_le_cs_procedure_enable(connection, &enable);
        }
        if (result != 0)
        {
            return record(Error::controller_error, result);
        }
        atomic_set(&state.procedure_pending, 1);
        return record(Error::none);
    }

    /** @brief 진행 중인 CS 절차를 중단합니다. */
    Error RasInitiator::stop() noexcept
    {
        if ((state_ == nullptr) || (stage_ != InitiatorStage::ranging) ||
            (atomic_get(&state.procedure_pending) != 0))
        {
            return record(Error::not_started);
        }
        bt_conn *connection = static_cast<bt_conn *>(atomic_ptr_get(&state.connection));
        bt_le_cs_procedure_enable_param disable = {};
        disable.config_id = config_id;
        disable.enable = BT_CONN_LE_CS_PROCEDURES_DISABLED;
        const int result = bt_le_cs_procedure_enable(connection, &disable);
        if (result != 0)
        {
            return record(Error::controller_error, result);
        }
        atomic_set(&state.procedure_pending, 1);
        return record(Error::none);
    }

    /** @brief RAS context와 공개 연결 reference를 반환합니다. */
    void RasInitiator::end() noexcept
    {
        if (state_ == nullptr)
        {
            return;
        }
        atomic_ptr_set(&state.owner, nullptr);
        bt_conn *connection = static_cast<bt_conn *>(atomic_ptr_set(&state.connection, nullptr));
        if (connection != nullptr)
        {
            if (state.rreq_allocated)
            {
                bt_ras_rreq_free(connection);
                state.rreq_allocated = false;
            }
            bt_conn_unref(connection);
        }
        net_buf_simple_reset(&local_steps);
        net_buf_simple_reset(&peer_steps);
        k_msgq_purge(&reading_queue);
        state_ = nullptr;
        stage_ = InitiatorStage::idle;
        (void)record(Error::not_connected);
    }

    /** @brief 현재 보안·CS 단계를 반환합니다. */
    InitiatorStage RasInitiator::stage() const noexcept
    {
        return stage_;
    }

    /** @brief 수신한 raw step 대조 결과 하나를 반환합니다. */
    bool RasInitiator::read(RasReading &reading) noexcept
    {
        return (state_ != nullptr) &&
               (k_msgq_get(&reading_queue, &reading, K_NO_WAIT) == 0);
    }

    /** @brief queue가 수용한 누적 결과 수를 반환합니다. */
    std::uint32_t RasInitiator::completed() const noexcept
    {
        return (state_ == nullptr) ? 0U :
                                       static_cast<std::uint32_t>(atomic_get(&state.completed));
    }

    /** @brief 연결 수명 동안 누적한 결과 누락 경로를 원자적으로 스냅샷합니다. */
    RasStatistics RasInitiator::statistics() const noexcept
    {
        RasStatistics snapshot = {};
        if (state_ != nullptr)
        {
            snapshot.local_busy_drops = atomic_get(&state.local_busy_drops);
            snapshot.local_overflows = atomic_get(&state.local_overflows);
            snapshot.procedure_aborts = atomic_get(&state.procedure_aborts);
            snapshot.subevent_aborts = atomic_get(&state.subevent_aborts);
            snapshot.ras_counter_mismatches = atomic_get(&state.ras_counter_mismatches);
            snapshot.ras_errors = atomic_get(&state.ras_errors);
            snapshot.local_missing = atomic_get(&state.local_missing);
            snapshot.invalid_readings = atomic_get(&state.invalid_readings);
            snapshot.reading_queue_full = atomic_get(&state.reading_queue_full);
        }
        return snapshot;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error RasInitiator::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 controller·Host 원본 오류를 반환합니다. */
    int RasInitiator::nativeCode() const noexcept
    {
        return native_code_;
    }
}

#endif
