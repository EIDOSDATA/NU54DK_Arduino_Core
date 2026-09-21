/**
 * @file NUCODE_BLE_ProfilesBackend.c
 * @brief 암호화 read·notify를 사용하는 표준 ESS 정적 attribute를 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <internal/NUCODE_BLE_ProfilesBackend.h>

#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/uuid.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>

#include <errno.h>

static atomic_t ess_temperature = ATOMIC_INIT(0);
static atomic_t ess_humidity = ATOMIC_INIT(0);

/** @brief 현재 온도를 Bluetooth little-endian 값으로 읽습니다. */
static ssize_t read_temperature(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                                void *buffer, uint16_t length, uint16_t offset)
{
    const int16_t current = (int16_t)atomic_get(&ess_temperature);
    const uint16_t encoded = sys_cpu_to_le16((uint16_t)current);
    return bt_gatt_attr_read(connection, attribute, buffer, length, offset, &encoded,
                             sizeof(encoded));
}

/** @brief 현재 습도를 Bluetooth little-endian 값으로 읽습니다. */
static ssize_t read_humidity(struct bt_conn *connection, const struct bt_gatt_attr *attribute,
                             void *buffer, uint16_t length, uint16_t offset)
{
    const uint16_t current = (uint16_t)atomic_get(&ess_humidity);
    const uint16_t encoded = sys_cpu_to_le16(current);
    return bt_gatt_attr_read(connection, attribute, buffer, length, offset, &encoded,
                             sizeof(encoded));
}

/** @brief ESS notification 구독 상태 변경은 profile facade에 별도 상태를 만들지 않습니다. */
static void subscription_changed(const struct bt_gatt_attr *attribute, uint16_t value)
{
    ARG_UNUSED(attribute);
    ARG_UNUSED(value);
}

BT_GATT_SERVICE_DEFINE(
    nucode_ess_service, BT_GATT_PRIMARY_SERVICE(BT_UUID_ESS),
    BT_GATT_CHARACTERISTIC(BT_UUID_TEMPERATURE, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ_ENCRYPT, read_temperature, NULL, NULL),
    BT_GATT_CCC(subscription_changed, BT_GATT_PERM_READ_ENCRYPT | BT_GATT_PERM_WRITE_ENCRYPT),
    BT_GATT_CHARACTERISTIC(BT_UUID_HUMIDITY, BT_GATT_CHRC_READ | BT_GATT_CHRC_NOTIFY,
                           BT_GATT_PERM_READ_ENCRYPT, read_humidity, NULL, NULL),
    BT_GATT_CCC(subscription_changed, BT_GATT_PERM_READ_ENCRYPT | BT_GATT_PERM_WRITE_ENCRYPT));

int nucode_ble_ess_set_temperature(int16_t hundredths_celsius)
{
    atomic_set(&ess_temperature, (atomic_val_t)hundredths_celsius);
    const uint16_t encoded = sys_cpu_to_le16((uint16_t)hundredths_celsius);
    const int result = bt_gatt_notify(NULL, &nucode_ess_service.attrs[1], &encoded,
                                      sizeof(encoded));
    return result == -ENOTCONN ? 0 : result;
}

int16_t nucode_ble_ess_get_temperature(void)
{
    return (int16_t)atomic_get(&ess_temperature);
}

int nucode_ble_ess_set_humidity(uint16_t hundredths_percent)
{
    atomic_set(&ess_humidity, (atomic_val_t)hundredths_percent);
    const uint16_t encoded = sys_cpu_to_le16(hundredths_percent);
    const int result = bt_gatt_notify(NULL, &nucode_ess_service.attrs[4], &encoded,
                                      sizeof(encoded));
    return result == -ENOTCONN ? 0 : result;
}

uint16_t nucode_ble_ess_get_humidity(void)
{
    return (uint16_t)atomic_get(&ess_humidity);
}

#endif
