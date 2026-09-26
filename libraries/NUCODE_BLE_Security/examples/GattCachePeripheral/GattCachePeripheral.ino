/**
 * @file GattCachePeripheral.ino
 * @brief bonded peer에 Database Hash와 Service Changed 기반 GATT cache를 제공하는 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Security.h>

namespace
{

    constexpr std::uint32_t databaseRevision = 1U;
    const nucode::ble::BLEUuid serviceUuid("8e7e2950-7d8c-4c1a-9d2d-8b6519f77410");
    const nucode::ble::BLEUuid valueUuid("8e7e2951-7d8c-4c1a-9d2d-8b6519f77410");
    nucode::ble::BLEService cacheService(serviceUuid);
    nucode::ble::BLECharacteristic
        cacheValue(valueUuid,
                   nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write |
                       nucode::ble::BLEProperty::notify,
                   nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, 32U);
    bool securityRequestPending = false;

    /** @brief pairing 요청은 main thread에서 명시적으로 승인합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(true))
            {
                Serial.println("GATT cache pairing approval failed");
            }
        }
        else if (record.event == nucode::ble::SecurityEvent::paired ||
                 record.event == nucode::ble::SecurityEvent::bond_verified)
        {
            Serial.println("GATT cache peer bonded");
        }
        else if (record.event == nucode::ble::SecurityEvent::pairing_failed ||
                 record.event == nucode::ble::SecurityEvent::error)
        {
            Serial.println("GATT cache security failed");
        }
    }

    /** @brief 새 peripheral link마다 encrypted bonded session을 요청합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected &&
            information.role == nucode::ble::BLELinkRole::peripheral)
        {
            securityRequestPending = true;
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            securityRequestPending = false;
        }
    }

    /** @brief peer write를 cached value와 notification에 반영합니다. */
    void onCharacteristicEvent(nucode::ble::BLECharacteristic &characteristic,
                               const nucode::ble::BLECharacteristicEventInfo &information,
                               void *context)
    {
        static_cast<void>(context);
        if (&characteristic == &cacheValue &&
            information.event == nucode::ble::BLECharacteristicEvent::written)
        {
            if (!cacheValue.notify(information.connection))
            {
                Serial.println("GATT cache notification failed");
            }
        }
    }

    /** @brief 시작 실패 단계만 출력하고 잘못된 부분 실행을 막습니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("GattCachePeripheral start failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000U);
        }
    }

} // namespace

void setup()
{
    Serial.begin(115200);

    nucode::ble::SecurityConfig security{};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    cacheValue.onEvent(onCharacteristicEvent);

    const std::uint8_t initialValue[] = {'c', 'a', 'c', 'h', 'e', '-', 'v', '1'};
    require(BLEGattDatabase.setRevision(databaseRevision), "database-revision");
    require(BLESecurity.begin(security), "security");
    require(cacheValue.setValue(initialValue, sizeof(initialValue)), "initial-value");
    require(cacheService.addCharacteristic(cacheValue), "characteristic");
    require(BLEDevice.addService(cacheService), "service");
    require(BLEDevice.begin("NU54-GATT-CACHE"), "device");
    require(BLEAdvertising.clear(), "advertising-clear");
    require(BLEAdvertising.setConnectable(true), "advertising-connectable");
    require(BLEAdvertising.addServiceUuid(serviceUuid), "advertising-service");
    require(BLEAdvertising.setScanResponseName(true), "advertising-name");
    require(BLEAdvertising.start(), "advertising-start");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    if (securityRequestPending)
    {
        securityRequestPending = false;
        if (!BLESecurity.requestSecurity())
        {
            Serial.println("GATT cache security request failed");
        }
    }
    delay(1U);
}
