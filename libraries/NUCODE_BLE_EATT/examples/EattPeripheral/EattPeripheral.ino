/**
 * @file EattPeripheral.ino
 * @brief 암호화 link에서 두 EATT bearer를 제공하는 experimental peripheral 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_EATT.h>

namespace
{

    const nucode::ble::BLEUuid serviceUuid("8e7e2980-7d8c-4c1a-9d2d-8b6519f77410");
    const nucode::ble::BLEUuid valueUuid("8e7e2981-7d8c-4c1a-9d2d-8b6519f77410");
    nucode::ble::BLEService eattService(serviceUuid);
    nucode::ble::BLECharacteristic
        eattValue(valueUuid, nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write,
                  nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write,
                  sizeof(std::uint32_t));
    bool securityPending = false;
    bool restartAdvertising = false;

    /** @brief Just Works pairing을 main thread에서 승인합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == nucode::ble::SecurityEvent::pairing_requested &&
            !BLESecurity.acceptPairing(true))
        {
            Serial.println("EATT pairing approval failed");
        }
    }

    /** @brief 새 peripheral link마다 EATT 필수 암호화를 요청합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected &&
            information.role == nucode::ble::BLELinkRole::peripheral)
        {
            securityPending = true;
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            securityPending = false;
            restartAdvertising = true;
        }
    }

    /** @brief 쓰인 sequence를 읽기 경로가 즉시 확인할 수 있게 보고합니다. */
    void onValue(nucode::ble::BLECharacteristic &characteristic,
                 const nucode::ble::BLECharacteristicEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (&characteristic == &eattValue &&
            information.event == nucode::ble::BLECharacteristicEvent::written)
        {
            Serial.print("EATT value bytes: ");
            Serial.println(information.length);
        }
    }

    /** @brief 시작 실패 뒤 불완전한 experimental image를 멈춥니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("EattPeripheral failed: ");
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
    Serial.println("WARNING: EATT is experimental opt-in, maximum two bearers per link");
    nucode::ble::SecurityConfig security{};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    eattValue.onEvent(onValue);
    const std::uint32_t initialValue = 0U;
    require(BLESecurity.begin(security), "security");
    require(eattValue.setValue(&initialValue, sizeof(initialValue)), "initial-value");
    require(eattService.addCharacteristic(eattValue), "characteristic");
    require(BLEDevice.addService(eattService), "service");
    require(BLEDevice.begin("NU54-EATT-P"), "device");
    require(BLEAdvertising.clear(), "advertising-clear");
    require(BLEAdvertising.setConnectable(true), "advertising-connectable");
    require(BLEAdvertising.addServiceUuid(serviceUuid), "advertising-service");
    require(BLEAdvertising.start(), "advertising-start");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    if (securityPending)
    {
        securityPending = false;
        if (!BLESecurity.requestSecurity())
        {
            Serial.println("EATT security request failed");
        }
    }
    if (restartAdvertising && BLEConnection.count() == 0U)
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("EATT advertising restart failed");
        }
    }
    delay(1U);
}
