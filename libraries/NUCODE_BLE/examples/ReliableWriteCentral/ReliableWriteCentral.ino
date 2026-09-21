/**
 * @file ReliableWriteCentral.ino
 * @brief exact generation link로 512-byte reliable write를 수행하는 central 예제입니다.
 */

#include <NUCODE_BLE.h>

const nucode::ble::BLEUuid serviceUuid("8e7e2903-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid valueUuid("8e7e2904-7d8c-4c1a-9d2d-8b6519f77410");
nucode::ble::BLEConnectionHandle peer;
uint8_t payload[512] = {};
bool running = false;
bool restartScan = false;

/** @brief index만으로 재현 가능한 512-byte 값을 만듭니다. */
void buildPayload()
{
    for (size_t index = 0U; index < sizeof(payload); ++index)
    {
        payload[index] = static_cast<uint8_t>(0x5aU ^ static_cast<uint8_t>(index) ^
                                              static_cast<uint8_t>(index >> 8U));
    }
}

/** @brief peripheral에서 다시 읽은 512-byte 값을 검증합니다. */
bool validPayload(const uint8_t *data, size_t length)
{
    return data != nullptr && length == sizeof(payload) &&
           memcmp(data, payload, sizeof(payload)) == 0;
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
    if (information.event == nucode::ble::BLEEvent::mtu_changed && information.connection == peer)
    {
        if (!BLEClient.discover(peer, serviceUuid, valueUuid))
        {
            reportFailure("GATT discovery");
        }
        return;
    }
    if (information.event == nucode::ble::BLEEvent::disconnected && information.connection == peer)
    {
        peer = nucode::ble::BLEConnectionHandle{};
        restartScan = true;
    }
}

/** @brief discovery 뒤 write하고 같은 exact link에서 값을 다시 읽습니다. */
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
        if (!BLEClient.write(peer, payload, sizeof(payload)))
        {
            reportFailure("reliable write");
        }
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::write_complete)
    {
        if (!BLEClient.read(peer))
        {
            reportFailure("read back");
        }
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::read_complete)
    {
        Serial.println(validPayload(information.data, information.length)
                           ? "512-byte reliable write PASS"
                           : "512-byte reliable write mismatch");
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
    buildPayload();
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
    running = BLEDevice.begin("NU54-WRITE-C") && startScan();
    if (!running)
    {
        reportFailure("reliable write central start");
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
