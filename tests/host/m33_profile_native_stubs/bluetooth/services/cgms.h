/** @file @brief CGMS 초기화·session·record 결과를 주입합니다. */
#pragma once
#include <cstdint>
constexpr int BT_CGMS_FEAT_TYPE_FLUID = 2, BT_CGMS_FEAT_LOC_SUB_TISSUE = 5;
struct bt_cgms_cb
{
    void (*session_state_changed)(bool);
};
struct bt_cgms_init_param
{
    int type, sample_location;
    std::uint16_t session_run_time, initial_comm_interval;
    bt_cgms_cb *cb;
};
struct bt_cgms_measurement
{
    struct
    {
        std::uint16_t val;
    } glucose;
};
inline bt_cgms_cb *native_glucose_callbacks = nullptr;
inline int native_glucose_error = 0;
inline std::uint16_t native_glucose_value = 0U;
inline int bt_cgms_init(bt_cgms_init_param *parameters)
{
    native_glucose_callbacks = parameters->cb;
    if (native_glucose_error == 0)
    {
        parameters->cb->session_state_changed(true);
    }
    return native_glucose_error;
}
inline int bt_cgms_measurement_add(bt_cgms_measurement measurement)
{
    native_glucose_value = measurement.glucose.val;
    return native_glucose_error;
}
