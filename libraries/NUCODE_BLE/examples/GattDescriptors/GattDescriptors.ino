/**
 * @file GattDescriptors.ino
 * @brief 네 descriptor를 찾고 한 ATT Read Multiple로 읽는 M29 central 예제입니다.
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
nucode::ble::BLEConnectionHandle peer;
uint16_t descriptorHandles[4] = {};
size_t descriptorIndex = 0U;
bool running = false;
bool restartScan = false;

/** @brief 현재 BLE driver 오류를 Serial에 출력합니다. */
void reportFailure(const char *operation)
{
    Serial.print(operation);
    Serial.print(" failed: ");
    Serial.println(BLEDevice.lastDriverError());
}

/** @brief 다음 exact descriptor를 찾거나 unlock write를 시작합니다. */
void continueDiscovery()
{
    if (descriptorIndex < 4U)
    {
        if (!BLEClient.discoverDescriptor(peer, descriptorUuids[descriptorIndex]))
        {
            reportFailure("descriptor discovery");
        }
        return;
    }
    if (!BLEClient.write(peer, unlockToken, sizeof(unlockToken)))
    {
        reportFailure("unlock write");
    }
}

/** @brief service UUID를 가진 connectable peer 하나에 연결합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (peer.valid() || !result.connectable || result.scan_response)
    {
        return;
    }
    if (!BLEScan.stop() || !BLEConnection.connect(result.address, peer))
    {
        reportFailure("connect");
        restartScan = true;
    }
}

/** @brief exact generation link의 연결·MTU·해제 수명을 처리합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::error)
    {
        reportFailure("BLE");
    }
    else if (information.event == nucode::ble::BLEEvent::connected &&
             information.connection == peer && !BLEConnection.requestMtu(peer))
    {
        reportFailure("MTU request");
    }
    else if (information.event == nucode::ble::BLEEvent::mtu_changed &&
             information.connection == peer && !BLEClient.discover(peer, serviceUuid, valueUuid))
    {
        reportFailure("GATT discovery");
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected &&
             information.connection == peer)
    {
        peer = nucode::ble::BLEConnectionHandle{};
        descriptorIndex = 0U;
        restartScan = true;
    }
}

/** @brief discovery·unlock·Read Multiple 결과를 main thread에서 순서대로 처리합니다. */
void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.connection != peer)
    {
        return;
    }
    if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
    {
        Serial.print("GATT operation failed, ATT=");
        Serial.println(information.att_error);
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete)
    {
        continueDiscovery();
    }
    else if (information.event ==
             nucode::ble::BLEGattClientEvent::descriptor_discovery_complete)
    {
        const nucode::ble::BLERemoteDescriptor descriptor =
            BLEClient.remoteDescriptor(peer, descriptorIndex);
        if (!descriptor.valid() || descriptor.uuid() != descriptorUuids[descriptorIndex])
        {
            Serial.println("descriptor identity mismatch");
            return;
        }
        descriptorHandles[descriptorIndex++] = descriptor.handle();
        continueDiscovery();
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::write_complete)
    {
        if (!BLEClient.readMultiple(peer, descriptorHandles, 4U))
        {
            reportFailure("read multiple");
        }
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::read_multiple_complete)
    {
        Serial.print("four descriptor bytes: ");
        Serial.println(information.length);
    }
}

/** @brief service filter를 유지한 active scan을 시작합니다. */
bool startScan()
{
    return BLEScan.clearFilters() && BLEScan.filterServiceUuid(serviceUuid) && BLEScan.start(true);
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
    running = BLEDevice.begin("NU54-DESC") && startScan();
    if (!running)
    {
        reportFailure("descriptor central start");
    }
}

void loop()
{
    if (!running)
    {
        return;
    }
    BLEDevice.poll();
    if (restartScan && !peer.valid())
    {
        restartScan = false;
        if (!startScan())
        {
            reportFailure("scan restart");
        }
    }
}
