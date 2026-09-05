/** @file @brief 경로 Host 검사의 PM reference 경계입니다. */
#pragma once
#include <zephyr/device.h>
bool pm_device_runtime_is_enabled(const device *);
int pm_device_runtime_enable(const device *);
int pm_device_runtime_get(const device *);
int pm_device_runtime_put(const device *);
