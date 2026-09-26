/**
 * @file p2_gatt_central.ino
 * @brief 512 B write/read와 20회 재연결에 대한 P2 central 계측입니다.
 */

#include <NUCODE_BLE.h>
#include <P2MemoryTelemetry.h>

const nucode::ble::BLEUuid serviceUuid("8e7e2903-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid valueUuid("8e7e2904-7d8c-4c1a-9d2d-8b6519f77410");
nucode::ble::BLEConnectionHandle peer;
uint8_t payload[512] = {};
bool running = false;
bool restartScan = false;
bool waitingForRecycle = false;
bool cycleComplete = false;
bool discoveryStarted = false;
bool pendingConnectFailure = false;
unsigned int completedCycles = 0U;
unsigned int completedWrites = 0U;
unsigned int connectionRetries = 0U;
unsigned long lastProgress = 0UL;
unsigned long lastReport = 0UL;
unsigned long recycledAt = 0UL;

/** @brief 오류를 기록하고 더 이상의 연결 시도를 중단합니다. */
void fail(const char *stage)
{
    Serial.print("P2_FAIL stage=");
    Serial.print(stage);
    Serial.print(" driver=");
    Serial.println(BLEDevice.lastDriverError());
    running = false;
}

/** @brief 512 B 재현 가능한 값을 만듭니다. */
void buildPayload()
{
    for (size_t index = 0U; index < sizeof(payload); ++index)
    {
        payload[index] = static_cast<uint8_t>(0x5aU ^ static_cast<uint8_t>(index) ^
                                              static_cast<uint8_t>(index >> 8U));
    }
}

/** @brief service filter를 유지한 active scan을 시작합니다. */
bool startScan()
{
    return BLEScan.clearFilters() && BLEScan.filterServiceUuid(serviceUuid) && BLEScan.start(true);
}

/** @brief 발견한 service peer 하나에 연결합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (peer.valid() || !result.connectable || result.scan_response)
    {
        return;
    }
    if (!BLEScan.stop() || !BLEConnection.connect(result.address, peer))
    {
        fail("connect");
    }
}

/** @brief 연결·MTU·해제 수명을 20회 반복합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::error)
    {
        Serial.print("P2_BLE_ERROR code=");
        Serial.print(static_cast<unsigned int>(BLEDevice.lastError()));
        Serial.print(" driver=");
        Serial.print(BLEDevice.lastDriverError());
        Serial.print(" dropped=");
        Serial.println(BLEDevice.droppedEvents());
        if (BLEDevice.lastError() == nucode::ble::BLEError::driver_error &&
            BLEDevice.lastDriverError() == -14 && !cycleComplete)
        {
            pendingConnectFailure = true;
            return;
        }
        fail("ble-event");
    }
    else if (information.event == nucode::ble::BLEEvent::connected &&
             information.connection == peer)
    {
        pendingConnectFailure = false;
        discoveryStarted = false;
        lastProgress = millis();
        if (!BLEConnection.requestMtu(peer))
        {
            fail("mtu-request");
        }
    }
    else if (information.event == nucode::ble::BLEEvent::mtu_changed &&
             information.connection == peer && !discoveryStarted)
    {
        discoveryStarted = true;
        if (!BLEClient.discover(peer, serviceUuid, valueUuid))
        {
            fail("discover");
        }
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected &&
             information.connection == peer)
    {
        Serial.print("P2_DISCONNECT reason=");
        Serial.println(information.reason);
        peer = nucode::ble::BLEConnectionHandle{};
        discoveryStarted = false;
        if (!cycleComplete)
        {
            if (pendingConnectFailure && information.reason == 0x3eU &&
                connectionRetries < 3U)
            {
                pendingConnectFailure = false;
                ++connectionRetries;
                waitingForRecycle = true;
                lastProgress = millis();
                Serial.print("P2_RETRY connection=");
                Serial.println(connectionRetries);
                return;
            }
            fail("early-disconnect");
            return;
        }
        cycleComplete = false;
        ++completedCycles;
        lastProgress = millis();
        Serial.print("P2_CYCLE pass=");
        Serial.println(completedCycles);
        if (completedCycles >= 20U)
        {
            nucode::test::reportMemory("complete");
            Serial.print("P2_DONE cycles=");
            Serial.print(completedCycles);
            Serial.print(" writes=");
            Serial.println(completedWrites);
            running = false;
        }
        else
        {
            waitingForRecycle = true;
        }
    }
    else if (information.event == nucode::ble::BLEEvent::connection_recycled &&
             waitingForRecycle)
    {
        waitingForRecycle = false;
        restartScan = true;
        recycledAt = millis();
    }
}

/** @brief 동일 link의 512 B write/read 결과를 확인합니다. */
void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEGattClientEvent::handles_invalidated)
    {
        Serial.println("P2_INVALIDATED");
        return;
    }
    if (information.connection != peer)
    {
        fail("cross-link");
        return;
    }
    if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
    {
        Serial.print("P2_GATT_ERROR status=");
        Serial.print(information.status);
        Serial.print(" att=");
        Serial.println(information.att_error);
        fail("gatt-operation");
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete)
    {
        if (!BLEClient.write(peer, payload, sizeof(payload)))
        {
            fail("write");
        }
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::write_complete)
    {
        ++completedWrites;
        if (!BLEClient.read(peer))
        {
            fail("read");
        }
    }
    else if (information.event == nucode::ble::BLEGattClientEvent::read_complete)
    {
        if (information.data == nullptr || information.length != sizeof(payload) ||
            memcmp(information.data, payload, sizeof(payload)) != 0)
        {
            fail("read-mismatch");
            return;
        }
        cycleComplete = true;
        if (!BLEConnection.disconnect(peer))
        {
            fail("disconnect");
        }
    }
}

/** @brief central 반복 시험을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    buildPayload();
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
    running = BLEDevice.begin("P2-GATT-C") && startScan();
    if (!running)
    {
        fail("start");
        return;
    }
    Serial.println("P2_READY role=central");
    nucode::test::reportMemory("ready");
    lastProgress = millis();
    lastReport = millis();
}

/** @brief 재탐색과 bounded timeout, 주기적 계측을 수행합니다. */
void loop()
{
    if (!running)
    {
        return;
    }
    BLEDevice.poll();
    if (restartScan && !peer.valid() && millis() - recycledAt >= 1000UL)
    {
        restartScan = false;
        if (!startScan())
        {
            fail("scan-restart");
        }
    }
    if (millis() - lastReport >= 10000UL)
    {
        nucode::test::reportMemory("traffic");
        lastReport = millis();
    }
    if (millis() - lastProgress >= 30000UL)
    {
        fail("timeout");
    }
}
