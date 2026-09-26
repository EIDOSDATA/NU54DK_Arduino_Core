/**
 * @file GattAuthorization.ino
 * @brief 동기 authorization으로 descriptor 접근을 여는 peripheral 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid serviceUuid("8e7e2905-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid valueUuid("8e7e2906-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid descriptorUuids[] = {
    nucode::ble::BLEUuid("8e7e2910-7d8c-4c1a-9d2d-8b6519f77410"),
    nucode::ble::BLEUuid("8e7e2911-7d8c-4c1a-9d2d-8b6519f77410"),
    nucode::ble::BLEUuid("8e7e2912-7d8c-4c1a-9d2d-8b6519f77410"),
    nucode::ble::BLEUuid("8e7e2913-7d8c-4c1a-9d2d-8b6519f77410"),
};
const uint8_t unlockToken[] = {0x4eU, 0x55U, 0x35U, 0x34U};
nucode::ble::BLEService authorizationService(serviceUuid);
nucode::ble::BLECharacteristic authorizationValue(
    valueUuid, nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write,
    nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, sizeof(unlockToken));
nucode::ble::BLEDescriptor descriptor0(descriptorUuids[0], nucode::ble::BLEPermission::read, 4U);
nucode::ble::BLEDescriptor descriptor1(descriptorUuids[1], nucode::ble::BLEPermission::read, 4U);
nucode::ble::BLEDescriptor descriptor2(descriptorUuids[2], nucode::ble::BLEPermission::read, 4U);
nucode::ble::BLEDescriptor descriptor3(descriptorUuids[3], nucode::ble::BLEPermission::read, 4U);
nucode::ble::BLEDescriptor *descriptors[] = {
    &descriptor0,
    &descriptor1,
    &descriptor2,
    &descriptor3,
};
bool descriptorAccessAllowed = false;
bool running = false;

/**
 * @brief Bluetooth callback 문맥에서 characteristic write를 즉시 판정합니다.
 * @warning blocking Arduino API나 Serial을 호출하지 않습니다.
 */
bool authorizeValue(const nucode::ble::BLEGattAuthorizationRequest &request, void *context)
{
    static_cast<void>(context);
    if (request.operation == nucode::ble::BLEGattAuthorizationOperation::read)
    {
        return true;
    }
    const bool allowed = request.descriptor == nullptr && request.offset == 0U &&
                         !request.prepare && !request.execute && !request.without_response &&
                         request.length == sizeof(unlockToken) && request.data != nullptr &&
                         memcmp(request.data, unlockToken, sizeof(unlockToken)) == 0;
    if (allowed)
    {
        descriptorAccessAllowed = true;
    }
    return allowed;
}

/**
 * @brief Bluetooth callback 문맥에서 unlock된 descriptor read만 허용합니다.
 * @warning 이 callback은 bounded·non-blocking이어야 합니다.
 */
bool authorizeDescriptor(const nucode::ble::BLEGattAuthorizationRequest &request, void *context)
{
    return request.descriptor == static_cast<nucode::ble::BLEDescriptor *>(context) &&
           request.operation == nucode::ble::BLEGattAuthorizationOperation::read &&
           descriptorAccessAllowed;
}

/** @brief authorization 결과를 BLEDevice.poll() main thread에서 출력합니다. */
void onValueEvent(nucode::ble::BLECharacteristic &characteristic,
                  const nucode::ble::BLECharacteristicEventInfo &information, void *context)
{
    static_cast<void>(characteristic);
    static_cast<void>(context);
    if (information.event == nucode::ble::BLECharacteristicEvent::authorization_allowed)
    {
        Serial.println(information.descriptor == nullptr ? "value access allowed"
                                                         : "descriptor access allowed");
    }
    else if (information.event == nucode::ble::BLECharacteristicEvent::authorization_denied)
    {
        Serial.println(information.descriptor == nullptr ? "value access denied"
                                                         : "descriptor access denied");
    }
}

void setup()
{
    Serial.begin(115200);
    authorizationValue.onAuthorize(authorizeValue);
    authorizationValue.onEvent(onValueEvent);
    bool schemaReady = authorizationValue.setValue(unlockToken, sizeof(unlockToken));
    for (size_t index = 0U; index < 4U && schemaReady; ++index)
    {
        uint8_t value[4] = {static_cast<uint8_t>(index), 0x4eU, 0x55U, 0x35U};
        descriptors[index]->onAuthorize(authorizeDescriptor, descriptors[index]);
        schemaReady = descriptors[index]->setValue(value, sizeof(value)) &&
                      authorizationValue.addDescriptor(*descriptors[index]);
    }
    running = schemaReady && authorizationService.addCharacteristic(authorizationValue) &&
              BLEDevice.addService(authorizationService) && BLEDevice.begin("NU54-AUTH") &&
              BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
              BLEAdvertising.addServiceUuid(serviceUuid) &&
              BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    if (!running)
    {
        Serial.print("authorization peripheral start failed: ");
        Serial.println(BLEDevice.lastDriverError());
    }
}

void loop()
{
    if (running)
    {
        BLEDevice.poll();
    }
}
