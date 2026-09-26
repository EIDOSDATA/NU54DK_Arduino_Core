/**
 * @file GattCacheCentral.ino
 * @brief bonded peer의 hash를 확인해 GATT handle cache를 복원하거나 재탐색하는 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Security.h>

namespace
{

    constexpr std::uint16_t cacheSchemaVersion = 1U;
    const nucode::ble::BLEUuid serviceUuid("8e7e2950-7d8c-4c1a-9d2d-8b6519f77410");
    const nucode::ble::BLEUuid valueUuid("8e7e2951-7d8c-4c1a-9d2d-8b6519f77410");
    nucode::ble::BLEAddress peerAddress;
    nucode::ble::BLEConnectionHandle peerConnection;
    bool peerFound = false;
    bool cachePending = false;
    bool scanPending = false;

    /** @brief service filter를 통과한 connectable peer 주소를 복사합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable && !result.scan_response)
        {
            peerAddress = result.address;
            peerFound = true;
            if (!BLEScan.stop())
            {
                Serial.println("GATT cache scan stop failed");
            }
        }
    }

    /** @brief 연결 수명에 맞춰 security 요청과 재검색을 예약합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected &&
            information.role == nucode::ble::BLELinkRole::central)
        {
            peerConnection = information.connection;
            if (!BLESecurity.requestSecurity())
            {
                Serial.println("GATT cache security request failed");
            }
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected &&
                 information.connection == peerConnection)
        {
            cachePending = false;
            peerFound = false;
            scanPending = true;
        }
    }

    /** @brief pairing을 승인하고 bonded encrypted link에서 cache 동기화를 예약합니다. */
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
            cachePending = true;
        }
        else if (record.event == nucode::ble::SecurityEvent::pairing_failed ||
                 record.event == nucode::ble::SecurityEvent::error)
        {
            Serial.println("GATT cache security failed");
        }
    }

    /** @brief cache 저장·복원·무효화와 비동기 GATT 결과를 처리합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.connection != peerConnection)
        {
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::cache_saved)
        {
            Serial.println("GATT cache saved after discovery");
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::cache_restored)
        {
            Serial.println("GATT cache restored after hash match");
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::service_changed)
        {
            Serial.println("Service Changed invalidated cached handles");
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete)
        {
            if (!BLEClient.read(peerConnection))
            {
                Serial.println("GATT cache read start failed");
            }
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::read_complete)
        {
            Serial.print("Cached value bytes: ");
            Serial.println(information.length);
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            Serial.println("GATT cache operation failed");
        }
    }

    /** @brief 시작 실패 단계만 출력하고 잘못된 부분 실행을 막습니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("GattCacheCentral start failed: ");
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
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);

    require(BLESecurity.begin(security), "security");
    require(BLEDevice.begin("NU54-GATT-CACHE-C"), "device");
    require(BLEScan.clearFilters(), "scan-clear");
    require(BLEScan.filterServiceUuid(serviceUuid), "scan-service");
    require(BLEScan.start(true), "scan-start");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress, peerConnection))
        {
            Serial.println("GATT cache connection failed");
            scanPending = true;
        }
    }
    if (scanPending && !BLEScan.running() && !BLEConnection.connecting())
    {
        scanPending = false;
        if (!BLEScan.start(true))
        {
            Serial.println("GATT cache scan restart failed");
        }
    }
    if (cachePending && !BLEClient.busy(peerConnection))
    {
        cachePending = false;
        if (!BLEClient.discoverCached(peerConnection, serviceUuid, valueUuid, cacheSchemaVersion))
        {
            Serial.println("GATT cache synchronization failed");
        }
    }
    delay(1U);
}
