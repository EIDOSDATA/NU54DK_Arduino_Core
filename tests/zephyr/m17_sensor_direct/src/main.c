/* SPDX-License-Identifier: Apache-2.0 */

#include <errno.h>
#include <stddef.h>

#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/kernel.h>
#include <zephyr/drivers/sensor.h>

#if DT_NODE_EXISTS(DT_ALIAS(accel0))
static const struct device *const accelerometer = DEVICE_DT_GET(DT_ALIAS(accel0));
#else
static const struct device *const accelerometer = NULL;
#endif

/**
 * @brief 실제 devicetree가 제공하는 가속도 센서를 Zephyr sensor API로 읽습니다.
 *
 * @return 센서가 없거나 준비되지 않았으면 -ENODEV, API 호출 결과를 반환합니다.
 */
static int read_acceleration(void)
{
	struct sensor_value acceleration[3];
	int result;

	if ((accelerometer == NULL) || !device_is_ready(accelerometer))
	{
		return -ENODEV;
	}

	result = sensor_sample_fetch(accelerometer);
	if (result != 0)
	{
		return result;
	}

	return sensor_channel_get(accelerometer, SENSOR_CHAN_ACCEL_XYZ, acceleration);
}

/**
 * @brief M17 direct sensor API build 계약 진입점입니다.
 *
 * @return sensor API 호출 결과를 반환합니다.
 */
int main(void)
{
	return read_acceleration();
}
