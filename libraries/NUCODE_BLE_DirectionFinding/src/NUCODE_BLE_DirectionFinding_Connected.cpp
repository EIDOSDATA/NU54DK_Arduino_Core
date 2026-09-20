/**
 * @file NUCODE_BLE_DirectionFinding_Connected.cpp
 * @brief 연결 기반 AoA CTE 응답의 Zephyr 구현입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_DirectionFinding.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_NUCODE_BLE_DF_RESPONDER)

extern "C"
{
#include <zephyr/bluetooth/direction.h>
}

#include <internal/NUCODE_BLE_Internal.h>

namespace nucode::ble::df
{
    namespace
    {
        bool responder_occupied = false;
    }

    /** @brief 공개 오류와 controller 원본 코드를 보존합니다. */
    Error ConnectedResponder::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    /** @brief 유효한 공개 handle을 연결 reference로 바꿔 응답 파라미터를 설정합니다. */
    Error ConnectedResponder::begin(BLEConnectionHandle connection) noexcept
    {
        if (!connection.valid())
        {
            return record(Error::invalid_argument);
        }
        if (connection_ != nullptr)
        {
            return record(Error::already_started);
        }
        if (responder_occupied)
        {
            return record(Error::busy);
        }

        bt_conn *native_connection = internal::referenceConnection(connection);
        if (native_connection == nullptr)
        {
            return record(Error::not_connected);
        }

        bt_df_conn_cte_tx_param parameters = {};
        parameters.cte_types = BT_DF_CTE_TYPE_AOA;
        const int result = bt_df_set_conn_cte_tx_param(native_connection, &parameters);
        if (result != 0)
        {
            bt_conn_unref(native_connection);
            return record(Error::controller_error, result);
        }

        connection_ = native_connection;
        responder_occupied = true;
        active_ = false;
        return record(Error::none);
    }

    /** @brief 연결에서 CTE 응답 절차를 활성화합니다. */
    Error ConnectedResponder::start() noexcept
    {
        if (connection_ == nullptr)
        {
            return record(Error::not_initialized);
        }
        if (active_)
        {
            return record(Error::already_started);
        }
        auto *native_connection = static_cast<bt_conn *>(connection_);
        const int result = bt_df_conn_cte_rsp_enable(native_connection);
        if (result != 0)
        {
            return record(Error::controller_error, result);
        }
        active_ = true;
        return record(Error::none);
    }

    /** @brief 같은 연결에서 재시작할 수 있도록 CTE 응답을 중단합니다. */
    Error ConnectedResponder::stop() noexcept
    {
        if (connection_ == nullptr)
        {
            return record(Error::not_initialized);
        }
        if (!active_)
        {
            return record(Error::not_started);
        }
        auto *native_connection = static_cast<bt_conn *>(connection_);
        const int result = bt_df_conn_cte_rsp_disable(native_connection);
        if (result != 0)
        {
            return record(Error::controller_error, result);
        }
        active_ = false;
        return record(Error::none);
    }

    /** @brief disconnect 뒤 controller 응답 실패와 무관하게 reference를 반환합니다. */
    void ConnectedResponder::end() noexcept
    {
        if (connection_ == nullptr)
        {
            return;
        }
        auto *native_connection = static_cast<bt_conn *>(connection_);
        if (active_)
        {
            (void)bt_df_conn_cte_rsp_disable(native_connection);
        }
        bt_conn_unref(native_connection);
        connection_ = nullptr;
        active_ = false;
        responder_occupied = false;
        (void)record(Error::not_initialized);
    }

    /** @brief 현재 응답 활성 상태를 반환합니다. */
    bool ConnectedResponder::active() const noexcept
    {
        return active_;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error ConnectedResponder::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 controller 원본 코드를 반환합니다. */
    int ConnectedResponder::nativeCode() const noexcept
    {
        return native_code_;
    }
}

#endif
