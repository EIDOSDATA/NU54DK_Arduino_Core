/**
 * @file LegacySignedWritePeripheral.ino
 * @brief deprecated Authenticated Signed Write를 명시적으로 받는 peripheral 예제입니다.
 *
 * 이 기능은 기본 BLE profile에서 꺼져 있습니다. 처음에는 legacy pairing으로 CSRK를
 * 교환하고, 이후 암호화하지 않은 bonded 재연결에서 signed write를 사용합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_LegacySigning.h>

namespace
{

    const nucode::ble::BLEUuid serviceUuid("8e7e2970-7d8c-4c1a-9d2d-8b6519f77410");
    const nucode::ble::BLEUuid signedValueUuid("8e7e2971-7d8c-4c1a-9d2d-8b6519f77410");
    nucode::ble::BLEService signingService(serviceUuid);
    nucode::ble::BLECharacteristic signedValue(
        signedValueUuid, nucode::ble::BLEProperty::authenticated_signed_write,
        nucode::ble::BLEPermission::write, 32U);
    bool securityPending = false;
    bool restartAdvertising = false;

    /** @brief pairing 요청을 main thread에서 승인합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(true))
            {
                Serial.println("legacy signing pairing approval failed");
            }
        }
        else if (record.event == nucode::ble::SecurityEvent::paired)
        {
            Serial.println("CSRK paired; reconnect without encryption for signed writes");
        }
    }

    /** @brief 최초 연결만 CSRK 교환을 위해 암호화하고 저장 bond 연결은 L1로 둡니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected &&
            information.role == nucode::ble::BLELinkRole::peripheral)
        {
            securityPending = BLESecurity.bondCount() == 0U;
            if (!securityPending)
            {
                Serial.println("bond restored; waiting for authenticated signed write");
            }
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            securityPending = false;
            restartAdvertising = true;
        }
    }

    /** @brief counter 영속화까지 끝난 signed value와 상태를 출력합니다. */
    void onSignedValue(nucode::ble::BLECharacteristic &characteristic,
                       const nucode::ble::BLECharacteristicEventInfo &information,
                       void *context)
    {
        static_cast<void>(context);
        if (&characteristic != &signedValue ||
            information.event != nucode::ble::BLECharacteristicEvent::written)
        {
            return;
        }
        Serial.print(information.status == 0 ? "signed write persisted, bytes="
                                             : "signed write persistence failed, status=");
        Serial.println(information.status == 0 ? static_cast<int>(information.length)
                                               : information.status);
    }

    /** @brief 시작 실패를 보고하고 불완전한 보안 image 실행을 막습니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("LegacySignedWritePeripheral failed: ");
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
    Serial.println("WARNING: Authenticated Signed Write is deprecated legacy opt-in");

    nucode::ble::SecurityConfig security{};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    signedValue.onEvent(onSignedValue);

    require(BLESecurity.begin(security), "security");
    require(signingService.addCharacteristic(signedValue), "characteristic");
    require(BLEDevice.addService(signingService), "service");
    require(BLEDevice.begin("NU54-SIGN-P"), "device");
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
            Serial.println("legacy signing security request failed");
        }
    }
    if (restartAdvertising && BLEConnection.count() == 0U)
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("legacy signing advertising restart failed");
        }
    }
    delay(1U);
}
