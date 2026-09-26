/**
 * @file LegacySignedWriteCentral.ino
 * @brief CSRK 저장 뒤 암호화하지 않은 재연결에서 signed write를 보내는 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_LegacySigning.h>

namespace
{

    const nucode::ble::BLEUuid serviceUuid("8e7e2970-7d8c-4c1a-9d2d-8b6519f77410");
    const nucode::ble::BLEUuid signedValueUuid("8e7e2971-7d8c-4c1a-9d2d-8b6519f77410");
    nucode::ble::BLEConnectionHandle peer;
    nucode::ble::BLEAddress peerAddress;
    bool peerFound = false;
    bool scanPending = false;
    bool securityPending = false;
    bool disconnectAfterPairing = false;
    bool signedWritePending = false;
    std::uint32_t sequence = 0U;

    /** @brief service filter를 통과한 connectable peer를 선택합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable && !result.scan_response)
        {
            peerAddress = result.address;
            peerFound = true;
            if (!BLEScan.stop())
            {
                Serial.println("legacy signing scan stop failed");
            }
        }
    }

    /** @brief 최초 pairing과 이후 unencrypted signed-write 연결을 분리합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected &&
            information.role == nucode::ble::BLELinkRole::central)
        {
            peer = information.connection;
            if (BLESecurity.bondCount() == 0U)
            {
                securityPending = true;
            }
            else if (!BLEClient.discover(peer, serviceUuid, signedValueUuid))
            {
                Serial.println("legacy signing discovery failed");
            }
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected &&
                 information.connection == peer)
        {
            peer = nucode::ble::BLEConnectionHandle{};
            peerFound = false;
            scanPending = true;
        }
    }

    /** @brief pairing을 승인하고 CSRK 저장 뒤 L1 재연결을 예약합니다. */
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
            disconnectAfterPairing = true;
        }
    }

    /** @brief discovery와 counter 영속화 완료를 다음 signed write로 연결합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.connection != peer)
        {
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete ||
            information.event == nucode::ble::BLEGattClientEvent::signed_write_complete)
        {
            if (information.event == nucode::ble::BLEGattClientEvent::signed_write_complete)
            {
                Serial.print("signed write persisted, sequence=");
                Serial.println(sequence);
            }
            signedWritePending = true;
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            Serial.print("signed write failed, status=");
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
    Serial.println("WARNING: Authenticated Signed Write is deprecated legacy opt-in");
    nucode::ble::SecurityConfig security{};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-SIGN-C") || !startScan())
    {
        Serial.println("LegacySignedWriteCentral start failed");
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
            Serial.println("legacy signing security request failed");
        }
    }
    if (disconnectAfterPairing && peer.valid())
    {
        disconnectAfterPairing = false;
        if (!BLEConnection.disconnect(peer))
        {
            Serial.println("legacy signing reconnect transition failed");
        }
    }
    if (scanPending && !peer.valid() && !BLEScan.running() && !BLEConnection.connecting())
    {
        scanPending = false;
        if (!startScan())
        {
            Serial.println("legacy signing scan restart failed");
        }
    }
    if (signedWritePending && peer.valid() && !BLEClient.busy(peer))
    {
        signedWritePending = false;
        ++sequence;
        if (!BLEClient.writeSigned(peer, &sequence, sizeof(sequence)))
        {
            Serial.println("legacy signed write start failed");
        }
    }
    delay(1U);
}
