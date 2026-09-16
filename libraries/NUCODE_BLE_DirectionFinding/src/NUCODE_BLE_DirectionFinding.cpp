/**
 * @file NUCODE_BLE_DirectionFinding.cpp
 * @brief 기본 안테나 AoA CTE 송신을 Zephyr Bluetooth에 연결합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_DirectionFinding.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#if defined(CONFIG_NUCODE_BLE_DF_BEACON)

#include <errno.h>

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/gap.h>

extern "C"
{
#include <zephyr/bluetooth/direction.h>
}
namespace nucode::ble::df
{
    namespace
    {
        constexpr char beacon_name[] = "NU54-CTE";
        bool occupied = false;
    }

    /** @brief 마지막 오류와 원본 Host/controller 코드를 함께 기록합니다. */
    Error Beacon::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    /** @brief 유효 설정에서 Bluetooth와 CTE 광고 set을 준비합니다. */
    Error Beacon::begin(const BeaconConfig &config) noexcept
    {
        if ((config.cte_length_8us < 2U) || (config.cte_length_8us > 20U) ||
            (config.cte_count == 0U) || (config.cte_count > 16U))
        {
            return record(Error::invalid_argument);
        }
        if (advertisement_ != nullptr)
        {
            return record(Error::already_started);
        }
        if (occupied)
        {
            return record(Error::busy);
        }

        int result = bt_enable(nullptr);
        if ((result != 0) && (result != -EALREADY))
        {
            return record(Error::controller_error, result);
        }

        bt_le_adv_param advertising_parameters = {};
        advertising_parameters.id = BT_ID_DEFAULT;
        advertising_parameters.options = BT_LE_ADV_OPT_EXT_ADV | BT_LE_ADV_OPT_USE_IDENTITY;
        advertising_parameters.interval_min = BT_GAP_ADV_FAST_INT_MIN_2;
        advertising_parameters.interval_max = BT_GAP_ADV_FAST_INT_MAX_2;
        bt_le_ext_adv *advertisement = nullptr;
        result = bt_le_ext_adv_create(&advertising_parameters, nullptr, &advertisement);
        if (result != 0)
        {
            return record(Error::controller_error, result);
        }

        const bt_data data = {
            BT_DATA_NAME_COMPLETE,
            sizeof(beacon_name) - 1U,
            reinterpret_cast<const std::uint8_t *>(beacon_name),
        };
        result = bt_le_ext_adv_set_data(advertisement, &data, 1U, nullptr, 0U);
        if (result == 0)
        {
            bt_df_adv_cte_tx_param cte_parameters = {};
            cte_parameters.cte_len = config.cte_length_8us;
            cte_parameters.cte_count = config.cte_count;
            cte_parameters.cte_type = BT_DF_CTE_TYPE_AOA;
            result = bt_df_set_adv_cte_tx_param(advertisement, &cte_parameters);
        }
        if (result == 0)
        {
            bt_le_per_adv_param periodic_parameters = {};
            periodic_parameters.interval_min = BT_GAP_PER_ADV_SLOW_INT_MIN;
            periodic_parameters.interval_max = BT_GAP_PER_ADV_SLOW_INT_MAX;
            periodic_parameters.options = BT_LE_ADV_OPT_USE_TX_POWER;
            result = bt_le_per_adv_set_param(advertisement, &periodic_parameters);
        }
        if (result != 0)
        {
            (void)bt_le_ext_adv_delete(advertisement);
            return record(Error::controller_error, result);
        }

        advertisement_ = advertisement;
        occupied = true;
        return record(Error::none);
    }

    /** @brief CTE를 먼저 활성화한 뒤 periodic와 extended 광고를 시작합니다. */
    Error Beacon::start() noexcept
    {
        if (advertisement_ == nullptr)
        {
            return record(Error::not_initialized);
        }
        if (active_)
        {
            return record(Error::already_started);
        }
        auto *advertisement = static_cast<bt_le_ext_adv *>(advertisement_);
        int result = bt_df_adv_cte_tx_enable(advertisement);
        if (result != 0)
        {
            return record(Error::controller_error, result);
        }
        result = bt_le_per_adv_start(advertisement);
        if (result != 0)
        {
            (void)bt_df_adv_cte_tx_disable(advertisement);
            return record(Error::controller_error, result);
        }
        bt_le_ext_adv_start_param start_parameters = {};
        result = bt_le_ext_adv_start(advertisement, &start_parameters);
        if (result != 0)
        {
            (void)bt_le_per_adv_stop(advertisement);
            (void)bt_df_adv_cte_tx_disable(advertisement);
            return record(Error::controller_error, result);
        }
        active_ = true;
        return record(Error::none);
    }

    /** @brief 광고와 CTE를 역순으로 해제해 재시작 상태로 돌아갑니다. */
    Error Beacon::stop() noexcept
    {
        if (advertisement_ == nullptr)
        {
            return record(Error::not_initialized);
        }
        if (!active_)
        {
            return record(Error::not_started);
        }
        auto *advertisement = static_cast<bt_le_ext_adv *>(advertisement_);
        int result = bt_le_ext_adv_stop(advertisement);
        if ((result != 0) && (result != -EALREADY))
        {
            return record(Error::controller_error, result);
        }
        result = bt_le_per_adv_stop(advertisement);
        if ((result != 0) && (result != -EALREADY))
        {
            return record(Error::controller_error, result);
        }
        result = bt_df_adv_cte_tx_disable(advertisement);
        if ((result != 0) && (result != -EALREADY))
        {
            return record(Error::controller_error, result);
        }
        active_ = false;
        return record(Error::none);
    }

    /** @brief 준비한 광고 set을 삭제하고 새로운 객체가 소유할 수 있게 합니다. */
    void Beacon::end() noexcept
    {
        if (advertisement_ == nullptr)
        {
            return;
        }
        if (active_ && (stop() != Error::none))
        {
            return;
        }
        auto *advertisement = static_cast<bt_le_ext_adv *>(advertisement_);
        const int result = bt_le_ext_adv_delete(advertisement);
        if (result != 0)
        {
            (void)record(Error::controller_error, result);
            return;
        }
        advertisement_ = nullptr;
        occupied = false;
        active_ = false;
        (void)record(Error::not_initialized);
    }

    /** @brief 실제 송신 활성 상태를 반환합니다. */
    bool Beacon::active() const noexcept
    {
        return active_;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error Beacon::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 controller/Host 오류 코드를 반환합니다. */
    int Beacon::nativeCode() const noexcept
    {
        return native_code_;
    }
}

#endif

#endif
