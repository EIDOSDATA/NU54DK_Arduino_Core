/** @file @brief 경로 Host 검사의 PM 상태 경계입니다. */
#pragma once
#include <zephyr/device.h>
enum pm_device_state
{
    PM_DEVICE_STATE_ACTIVE,
    PM_DEVICE_STATE_SUSPENDED,
};
int pm_device_state_get(const device *, pm_device_state *);
