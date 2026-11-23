/** @file @brief NCS 3.4.0 CGMS 구현을 사용자 측정값 API에 연결합니다.
 * SPDX-License-Identifier: MIT
 */
#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include "NUCODE_BLE_Glucose.h"
#include <errno.h>
#if defined(CONFIG_BT_CGMS) && CONFIG_BT_MAX_CONN == 1
#include <bluetooth/services/cgms.h>
#include <zephyr/sys/atomic.h>
#endif
namespace nucode::ble::profiles
{
    namespace
    {
        int last_error = 0;
#if defined(CONFIG_BT_CGMS) && CONFIG_BT_MAX_CONN == 1
        atomic_t session_active = ATOMIC_INIT(0);
        bool initialized = false;
        void sessionChanged(const bool active)
        {
            atomic_set(&session_active, active ? 1 : 0);
        }
        bt_cgms_cb callbacks = {sessionChanged};
#endif
    } // namespace
    bool GlucoseService::begin(std::uint16_t session_hours,
                               std::uint16_t notification_minutes) noexcept
    {
#if defined(CONFIG_BT_CGMS) && CONFIG_BT_MAX_CONN == 1
        if (initialized || session_hours == 0U || notification_minutes == 0U ||
            notification_minutes > 255U)
        {
            last_error = -EINVAL;
            return false;
        }
        bt_cgms_init_param parameters{};
        parameters.type = BT_CGMS_FEAT_TYPE_FLUID;
        parameters.sample_location = BT_CGMS_FEAT_LOC_SUB_TISSUE;
        parameters.session_run_time = session_hours;
        parameters.initial_comm_interval = notification_minutes;
        parameters.cb = &callbacks;
        last_error = bt_cgms_init(&parameters);
        initialized = last_error == 0;
        return initialized;
#else
        static_cast<void>(session_hours);
        static_cast<void>(notification_minutes);
        last_error = -ENOTSUP;
        return false;
#endif
    }
    bool GlucoseService::add(std::int16_t mantissa, std::int8_t exponent) noexcept
    {
        Packet packet;
        const GlucoseMeasurement value{mantissa, exponent, 0U};
        if (!Codec::encode(value, packet))
        {
            last_error = -EINVAL;
            return false;
        }
#if defined(CONFIG_BT_CGMS) && CONFIG_BT_MAX_CONN == 1
        if (!initialized)
        {
            last_error = -EACCES;
            return false;
        }
        bt_cgms_measurement measurement{};
        measurement.glucose.val = static_cast<std::uint16_t>(packet.data[2]) |
                                  (static_cast<std::uint16_t>(packet.data[3]) << 8U);
        last_error = bt_cgms_measurement_add(measurement);
        return last_error == 0;
#else
        last_error = -ENOTSUP;
        return false;
#endif
    }
    bool GlucoseService::sessionActive() const noexcept
    {
#if defined(CONFIG_BT_CGMS) && CONFIG_BT_MAX_CONN == 1
        return atomic_get(&session_active) != 0;
#else
        return false;
#endif
    }
    int GlucoseService::lastError() const noexcept
    {
        return last_error;
    }
} // namespace nucode::ble::profiles
#endif
