/**
 * @file NUCODE_BLE_ChannelSounding_Reflector.cpp
 * @brief Ranging Service reflector의 Zephyr 구현입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_ChannelSounding.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_NUCODE_BLE_CS_REFLECTOR)

extern "C"
{
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/cs.h>
#include <zephyr/sys/atomic.h>
}

#include <internal/NUCODE_BLE_Internal.h>

namespace nucode::ble::cs
{
    namespace
    {
        /** @brief Bluetooth callback과 Arduino main 사이의 고정 상태입니다. */
        struct ReflectorState
        {
            atomic_ptr_t owner = nullptr;
            atomic_ptr_t connection = nullptr;
            atomic_t config_pending = 0;
            atomic_t ready = 0;
            atomic_t active = 0;
            atomic_t hci_error = 0;
        };

        ReflectorState state;

        /** @brief 완료 callback에서 CS 설정 결과만 저장합니다. */
        void configComplete(bt_conn *connection, std::uint8_t status,
                            bt_conn_le_cs_config *config)
        {
            static_cast<void>(config);
            if ((atomic_ptr_get(&state.owner) == nullptr) ||
                (atomic_ptr_get(&state.connection) != connection))
            {
                return;
            }
            if (status != 0U)
            {
                atomic_set(&state.hci_error, status);
            }
            else
            {
                atomic_set(&state.config_pending, 1);
            }
        }

        /** @brief peer의 CS 절차 활성 상태만 저장합니다. */
        void procedureComplete(bt_conn *connection, std::uint8_t status,
                               bt_conn_le_cs_procedure_enable_complete *parameters)
        {
            if ((atomic_ptr_get(&state.owner) == nullptr) ||
                (atomic_ptr_get(&state.connection) != connection))
            {
                return;
            }
            if (status != 0U)
            {
                atomic_set(&state.hci_error, status);
            }
            else
            {
                atomic_set(&state.active,
                           ((parameters != nullptr) && (parameters->state == 1U)) ? 1 : 0);
            }
        }
    }

    BT_CONN_CB_DEFINE(nucode_ras_reflector_callbacks) = {
        .le_cs_config_complete = configComplete,
        .le_cs_procedure_enable_complete = procedureComplete,
    };

    /** @brief 공개 오류와 controller 원본 오류를 함께 보관합니다. */
    Error RasReflector::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    /** @brief 공개 연결에 CS reflector 설정을 적용합니다. */
    Error RasReflector::begin(BLEConnectionHandle connection) noexcept
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

        bt_le_cs_set_default_settings_param settings = {};
        settings.enable_initiator_role = false;
        settings.enable_reflector_role = true;
        settings.cs_sync_antenna_selection = BT_LE_CS_ANTENNA_SELECTION_OPT_REPETITIVE;
        settings.max_tx_power = BT_HCI_OP_LE_CS_MAX_MAX_TX_POWER;
        const int result = bt_le_cs_set_default_settings(native_connection, &settings);
        if (result != 0)
        {
            bt_conn_unref(native_connection);
            atomic_ptr_set(&state.owner, nullptr);
            return record(Error::controller_error, result);
        }

        atomic_ptr_set(&state.connection, native_connection);
        atomic_set(&state.config_pending, 0);
        atomic_set(&state.ready, 0);
        atomic_set(&state.active, 0);
        atomic_set(&state.hci_error, 0);
        state_ = &state;
        return record(Error::none);
    }

    /** @brief 비동기 CS config 뒤 절차 파라미터를 준비합니다. */
    void RasReflector::poll() noexcept
    {
        if (state_ == nullptr)
        {
            return;
        }
        const int hci_error = atomic_set(&state.hci_error, 0);
        if (hci_error != 0)
        {
            (void)record(Error::controller_error, hci_error);
            return;
        }
        if (atomic_set(&state.config_pending, 0) == 0)
        {
            return;
        }
        bt_conn *native_connection = static_cast<bt_conn *>(atomic_ptr_get(&state.connection));
        if (native_connection == nullptr)
        {
            return;
        }

        bt_le_cs_set_procedure_parameters_param parameters = {};
        parameters.config_id = 0U;
        parameters.max_procedure_len = 1000U;
        parameters.min_procedure_interval = 1U;
        parameters.max_procedure_interval = 100U;
        parameters.max_procedure_count = 0U;
        parameters.min_subevent_len = 10000U;
        parameters.max_subevent_len = 75000U;
        parameters.tone_antenna_config_selection =
            BT_LE_CS_TONE_ANTENNA_CONFIGURATION_A1_B1;
        parameters.phy = BT_LE_CS_PROCEDURE_PHY_2M;
        parameters.tx_power_delta = 0x80U;
        parameters.preferred_peer_antenna = BT_LE_CS_PROCEDURE_PREFERRED_PEER_ANTENNA_1;
        parameters.snr_control_initiator = BT_LE_CS_SNR_CONTROL_NOT_USED;
        parameters.snr_control_reflector = BT_LE_CS_SNR_CONTROL_NOT_USED;

        const int result = bt_le_cs_set_procedure_parameters(native_connection, &parameters);
        if (result != 0)
        {
            (void)record(Error::controller_error, result);
            return;
        }
        atomic_set(&state.ready, 1);
        (void)record(Error::none);
    }

    /** @brief 연결 참조와 singleton 소유권을 반환합니다. */
    void RasReflector::end() noexcept
    {
        if (state_ == nullptr)
        {
            return;
        }
        atomic_ptr_set(&state.owner, nullptr);
        bt_conn *native_connection =
            static_cast<bt_conn *>(atomic_ptr_set(&state.connection, nullptr));
        if (native_connection != nullptr)
        {
            bt_conn_unref(native_connection);
        }
        atomic_set(&state.config_pending, 0);
        atomic_set(&state.ready, 0);
        atomic_set(&state.active, 0);
        atomic_set(&state.hci_error, 0);
        state_ = nullptr;
        (void)record(Error::not_connected);
    }

    /** @brief CS 절차 파라미터 준비 상태를 반환합니다. */
    bool RasReflector::ready() const noexcept
    {
        return (state_ != nullptr) && (atomic_get(&state.ready) != 0);
    }

    /** @brief peer가 활성화한 CS 절차 상태를 반환합니다. */
    bool RasReflector::active() const noexcept
    {
        return (state_ != nullptr) && (atomic_get(&state.active) != 0);
    }

    /** @brief 현재 ACL의 실제 L2 이상 보안 상태를 반환합니다. */
    bool RasReflector::secure() const noexcept
    {
        if (state_ == nullptr)
        {
            return false;
        }
        bt_conn *native_connection = static_cast<bt_conn *>(atomic_ptr_get(&state.connection));
        return (native_connection != nullptr) &&
               (bt_conn_get_security(native_connection) >= BT_SECURITY_L2);
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error RasReflector::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 controller·Host 원본 오류를 반환합니다. */
    int RasReflector::nativeCode() const noexcept
    {
        return native_code_;
    }
}

#endif
