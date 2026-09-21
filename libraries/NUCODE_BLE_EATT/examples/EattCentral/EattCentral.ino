/**
 * @file EattCentral.ino
 * @brief 두 enhanced bearer pool을 열고 GATT round trip을 반복하는 central 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_EATT.h>

#include <string.h>

namespace
{

    const nucode::ble::BLEUuid serviceUuid("8e7e2980-7d8c-4c1a-9d2d-8b6519f77410");
    const nucode::ble::BLEUuid valueUuid("8e7e2981-7d8c-4c1a-9d2d-8b6519f77410");
    nucode::ble::BLEConnectionHandle peer;
    nucode::ble::BLEAddress peerAddress;
    bool peerFound = false;
    bool scanPending = false;
    bool securityPending = false;
    bool eattConnectPending = false;
    bool writePending = false;
    bool readPending = false;
    std::uint32_t sequence = 0U;
    nucode::ble::BLEGattBearer selectedBearer = nucode::ble::BLEGattBearer::enhanced;

    /** @brief service UUID를 광고하는 connectable peer를 선택합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable && !result.scan_response)
        {
            peerAddress = result.address;
            peerFound = true;
            if (!BLEScan.stop())
            {
                Serial.println("EATT scan stop failed");
            }
        }
    }

    /** @brief 연결마다 암호화를 요청하고 해제 시 재검색합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected &&
            information.role == nucode::ble::BLELinkRole::central)
        {
            peer = information.connection;
            securityPending = true;
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected &&
                 information.connection == peer)
        {
            peer = nucode::ble::BLEConnectionHandle{};
            peerFound = false;
            scanPending = true;
            eattConnectPending = false;
            writePending = false;
            readPending = false;
        }
    }

    /** @brief pairing 승인 뒤 exact characteristic discovery를 시작합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(true))
            {
                Serial.println("EATT pairing approval failed");
            }
        }
        else if ((record.event == nucode::ble::SecurityEvent::paired ||
                  record.event == nucode::ble::SecurityEvent::bond_verified ||
                  record.event == nucode::ble::SecurityEvent::security_changed) &&
                 peer.valid() && !BLEClient.discovered(peer) && !BLEClient.busy(peer))
        {
            if (!BLEClient.discover(peer, serviceUuid, valueUuid))
            {
                Serial.println("EATT discovery failed");
            }
        }
    }

    /** @brief enhanced bearer 결과를 검증하고 write/read sequence를 진행합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.connection != peer)
        {
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete)
        {
            eattConnectPending = true;
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::write_complete)
        {
            if (information.bearer != selectedBearer)
            {
                Serial.println("EATT write bearer mismatch");
            }
            readPending = true;
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::read_complete)
        {
            std::uint32_t observed = 0U;
            if (information.bearer != selectedBearer || information.length != sizeof(observed))
            {
                Serial.println("EATT read bearer or length mismatch");
                return;
            }
            ::memcpy(&observed, information.data, sizeof(observed));
            Serial.println(observed == sequence ? "EATT enhanced round trip PASS"
                                                : "EATT payload mismatch");
            writePending = true;
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            Serial.print("EATT operation failed: ");
            Serial.println(information.status);
        }
    }

    /** @brief service UUID active scan을 시작합니다. */
    bool startScan()
    {
        return BLEScan.clearFilters() && BLEScan.filterServiceUuid(serviceUuid) &&
               BLEScan.start(true);
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
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-EATT-C") || !startScan())
    {
        Serial.println("EattCentral start failed");
    }
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    if (peerFound && !peer.valid() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress, peer))
        {
            scanPending = true;
        }
    }
    if (securityPending)
    {
        securityPending = false;
        if (!BLESecurity.requestSecurity())
        {
            Serial.println("EATT security request failed");
        }
    }
    if (scanPending && !peer.valid() && !BLEScan.running() && !BLEConnection.connecting())
    {
        scanPending = false;
        if (!startScan())
        {
            Serial.println("EATT scan restart failed");
        }
    }
    if (eattConnectPending && peer.valid() && !BLEClient.busy(peer))
    {
        eattConnectPending = false;
        if (!BLEEatt.connect(peer, 2U))
        {
            Serial.println("EATT two-bearer connection failed");
        }
    }
    if (BLEEatt.count(peer) == 2U && !writePending && !readPending && !BLEClient.busy(peer))
    {
        writePending = true;
    }
    if (writePending && !BLEClient.busy(peer))
    {
        writePending = false;
        ++sequence;
        if (!BLEClient.write(peer, &sequence, sizeof(sequence), selectedBearer))
        {
            Serial.println("EATT enhanced write start failed");
        }
    }
    if (readPending && !BLEClient.busy(peer))
    {
        readPending = false;
        if (!BLEClient.read(peer, selectedBearer))
        {
            Serial.println("EATT enhanced read start failed");
        }
    }
    delay(1U);
}
