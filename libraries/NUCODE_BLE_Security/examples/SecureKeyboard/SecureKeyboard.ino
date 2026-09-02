/**
 * @file SecureKeyboard.ino
 * @brief 버튼 확인 뒤 bonding하고 암호화 BLE HID key report를 보냅니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_Security.h>

namespace
{

    constexpr std::uint8_t hid_usage_a = 0x04U;
    bool pairing_confirmation_pending = false;
    bool previous_button_pressed = false;

    /** @brief passkey 값이나 key material을 Serial에 출력하지 않고 상태만 보존합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        (void)context;
        switch (record.event)
        {
        case nucode::ble::SecurityEvent::pairing_requested:
            pairing_confirmation_pending = true;
            Serial.println("BLE pairing confirmation requested; press SW0");
            break;
        case nucode::ble::SecurityEvent::paired:
            Serial.println("BLE pairing completed");
            break;
        case nucode::ble::SecurityEvent::bond_persistence_pending:
            Serial.println("BLE bond pending reboot verification");
            break;
        case nucode::ble::SecurityEvent::bond_restored_candidate:
            Serial.println("BLE restored bond candidate awaiting encrypted reconnect");
            break;
        case nucode::ble::SecurityEvent::bond_verified:
            Serial.println("BLE bond restored and verified after reboot");
            break;
        case nucode::ble::SecurityEvent::bond_removal_requested:
        case nucode::ble::SecurityEvent::all_bonds_removal_requested:
            Serial.println("BLE bond removal request accepted; verify after reboot");
            break;
        case nucode::ble::SecurityEvent::pairing_cancelled:
        case nucode::ble::SecurityEvent::pairing_failed:
        case nucode::ble::SecurityEvent::timeout:
        case nucode::ble::SecurityEvent::error:
            pairing_confirmation_pending = false;
            Serial.println("BLE security operation failed");
            break;
        default:
            break;
        }
    }

    /** @brief 실패 시 민감하지 않은 단계 이름만 출력하고 실행을 멈춥니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("SecureKeyboard start failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000);
        }
    }

}

void setup()
{
    Serial.begin(115200);
    pinMode(PIN_BUTTON0, INPUT_PULLUP);

    nucode::ble::SecurityConfig security = {};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.response_timeout_ms = 30000U;
    security.io_capability =
        nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    require(BLESecurity.begin(security), "security");
    require(BLEKeyboard.begin(), "hid");
    require(BLEDevice.begin("NU54-Secure-HID"), "device");

    const nucode::ble::DeviceInformation information = {
        "NUCODE", "NU54DK-HID", "UNSET", "0.3.0", "NU54DK", "0.3.0"};
    require(BLEDeviceInformation.configure(information), "dis");
    require(BLEBattery.setLevel(100U), "bas");

    require(BLEAdvertising.clear(), "advertising-clear");
    require(BLEAdvertising.setConnectable(true), "advertising-connectable");
    require(BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x1812U)),
            "advertising-hids");
    require(BLEAdvertising.addServiceUuid(nucode::ble::BLEUuid(0x180FU)),
            "advertising-bas");
    require(BLEAdvertising.setScanResponseName(true), "advertising-name");
    require(BLEAdvertising.start(), "advertising-start");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();

    const bool pressed = digitalRead(PIN_BUTTON0) == LOW;
    if (pressed && !previous_button_pressed)
    {
        if (pairing_confirmation_pending)
        {
            pairing_confirmation_pending = false;
            static_cast<void>(BLESecurity.acceptPairing(true));
        }
        else if (BLESecurity.currentLevel() >=
                     nucode::ble::SecurityLevel::encrypted &&
                 BLEKeyboard.connected())
        {
            if (BLEKeyboard.press(hid_usage_a))
            {
                delay(15);
                static_cast<void>(BLEKeyboard.releaseAll());
            }
        }
    }
    previous_button_pressed = pressed;
    delay(5);
}
