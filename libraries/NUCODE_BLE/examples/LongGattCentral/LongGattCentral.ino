/**
 * @file LongGattCentral.ino
 * @brief generation handle로 512-byte value를 읽는 M29 long read central 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid serviceUuid("8e7e2901-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid valueUuid("8e7e2902-7d8c-4c1a-9d2d-8b6519f77410");
nucode::ble::BLEConnectionHandle peer;
bool running = false;
bool restartScan = false;

/** @brief peripheral 예제와 같은 index의 기대 byte를 반환합니다. */
uint8_t expectedByte(size_t index)
{
    return static_cast<uint8_t>(0xa5U ^ static_cast<uint8_t>(index) ^
                                static_cast<uint8_t>(index >> 8U));
}

/** @brief 512-byte long read payload 전체를 검증합니다. */
bool validPayload(const uint8_t *data, size_t length)
{
    if (data == nullptr || length != 512U)
    {
        return false;
    }
    for (size_t index = 0U; index < length; ++index)
    {
        if (data[index] != expectedByte(index))
        {
            return false;
        }
    }
    return true;
}

/** @brief 현재 BLE driver 오류를 Serial에 출력합니다. */
void reportFailure(const char *operation)
{
    Serial.print(operation);
    Serial.print(" failed: ");
    Serial.println(BLEDevice.lastDriverError());
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
        return;
    }
    if (information.event == nucode::ble::BLEEvent::connected && information.connection == peer)
    {
        if (!BLEConnection.requestMtu(peer))
        {
            reportFailure("MTU request");
        }
        return;
    }
    if (information.event == nucode::ble::BLEEvent::mtu_changed &&
        information.connection == peer)
    {
        Serial.print("ATT MTU: ");
        Serial.println(BLEConnection.mtu(peer));
        if (!BLEClient.discover(peer, serviceUuid, valueUuid))
        {
            reportFailure("GATT discovery");
        }
        return;
    }
    if (information.event == nucode::ble::BLEEvent::disconnected &&
        information.connection == peer)
    {
        peer = nucode::ble::BLEConnectionHandle{};
        restartScan = true;
    }
}

/** @brief link가 식별된 discovery와 long read 결과를 처리합니다. */
void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.connection != peer)
    {
        return;
    }
    if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
    {
        Serial.print("GATT operation failed, status=");
        Serial.print(information.status);
        Serial.print(", ATT=");
        Serial.println(information.att_error);
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete)
    {
        if (!BLEClient.read(peer))
        {
            reportFailure("long read");
        }
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::read_complete)
    {
        Serial.println(validPayload(information.data, information.length)
                           ? "512-byte long read PASS"
                           : "512-byte long read payload mismatch");
    }
}

/** @brief service filter를 유지한 active scan을 시작합니다. */
bool startScan()
{
    return BLEScan.clearFilters() && BLEScan.filterServiceUuid(serviceUuid) &&
           BLEScan.start(true);
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
    running = BLEDevice.begin("NU54-LONG-C") && startScan();
    if (!running)
    {
        reportFailure("long GATT central start");
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
