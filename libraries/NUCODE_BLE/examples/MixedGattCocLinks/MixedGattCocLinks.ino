/**
 * @file MixedGattCocLinks.ino
 * @brief 세 NU54DK에서 mixed-role 2-link GATT·LE CoC를 함께 실행하는 예제입니다.
 *
 * 같은 Sketch의 `nodeRole`만 바꿔 다음 순서로 세 보드에 업로드합니다.
 * 1. `NodeRole::peripheral`: upstream GATT·CoC server
 * 2. `NodeRole::mixed`: upstream에는 central, downstream에는 peripheral
 * 3. `NodeRole::central`: mixed 보드의 downstream client
 *
 * 추가 GPIO 배선은 필요하지 않습니다. 세 보드의 전원을 켜면 mixed 보드가 두 link에서
 * GATT write와 32-byte CoC echo를 1초마다 병렬 실행합니다.
 * 도구 → Feature set → BLE NUS를 선택해야 합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>

#include "MixedGattCocPayload.h"

namespace
{

    /** @brief 한 번에 한 보드에 지정할 예제 role입니다. */
    enum class NodeRole : std::uint8_t
    {
        peripheral,
        mixed,
        central,
    };

    constexpr NodeRole nodeRole = NodeRole::mixed;
    constexpr std::uint16_t cocPsm = 0x0082U;
    constexpr std::uint8_t gattTransport = 0x47U;
    constexpr std::uint8_t cocTransport = 0x43U;
    constexpr std::uint32_t sendIntervalMs = 1000U;

    const nucode::ble::BLEUuid serviceUuid("90bf2a50-14f5-4d3d-92c7-299334932a20");
    const nucode::ble::BLEUuid characteristicUuid("90bf2a51-14f5-4d3d-92c7-299334932a20");
    nucode::ble::BLEService exampleService(serviceUuid);
    nucode::ble::BLECharacteristic exampleCharacteristic(
        characteristicUuid, nucode::ble::BLEProperty::write,
        nucode::ble::BLEPermission::write, mixed_gatt_coc::Payload::length);

    nucode::ble::BLEAddress peerAddress;
    nucode::ble::BLEConnectionHandle clientConnection;
    nucode::ble::BLEConnectionHandle serverConnection;
    nucode::ble::BLEL2capChannelHandle clientChannel;
    nucode::ble::BLEL2capChannelHandle serverChannel;
    std::uint8_t gattPayload[mixed_gatt_coc::Payload::length] = {};
    std::uint8_t cocPayload[mixed_gatt_coc::Payload::length] = {};
    std::uint32_t sequence = 0U;
    std::uint32_t lastSendMs = 0U;
    bool peerFound = false;
    bool scanStarted = false;
    bool clientGattReady = false;
    bool clientCocReady = false;
    bool advertisingStarted = false;
    bool gattPending = false;
    bool cocPending = false;
    bool trafficActive = false;
    bool stopped = false;

    /** @brief 두 transport 완료 뒤에만 같은 sequence의 성공을 확정합니다. */
    void finishTrafficIfComplete();

    /** @brief 현재 image가 client 역할을 갖는지 반환합니다. */
    constexpr bool hasClient()
    {
        return nodeRole != NodeRole::peripheral;
    }

    /** @brief 현재 image가 server 역할을 갖는지 반환합니다. */
    constexpr bool hasServer()
    {
        return nodeRole != NodeRole::central;
    }

    /** @brief 현재 role의 advertising local name을 반환합니다. */
    const char *localName()
    {
        if (nodeRole == NodeRole::peripheral)
        {
            return "NU54-M29-UP";
        }
        if (nodeRole == NodeRole::mixed)
        {
            return "NU54-M29-MIX";
        }
        return "NU54-M29-C";
    }

    /** @brief client role이 검색할 upstream 이름을 반환합니다. */
    const char *peerName()
    {
        return nodeRole == NodeRole::mixed ? "NU54-M29-UP" : "NU54-M29-MIX";
    }

    /** @brief payload에 기록할 local role marker를 반환합니다. */
    constexpr std::uint8_t roleMarker()
    {
        return nodeRole == NodeRole::mixed ? 0xb2U : 0xc3U;
    }

    /** @brief 첫 runtime 오류를 출력하고 추가 전송을 중단합니다. */
    void fail(const char *stage)
    {
        if (stopped)
        {
            return;
        }
        stopped = true;
        Serial.print("M29 mixed example stopped: ");
        Serial.print(stage);
        Serial.print(", error=");
        Serial.println(BLEDevice.lastDriverError());
    }

    /** @brief server role의 connectable advertising을 한 번 시작합니다. */
    bool startAdvertising()
    {
        if (advertisingStarted)
        {
            return true;
        }
        advertisingStarted = BLEAdvertising.clear() &&
                             BLEAdvertising.setConnectable(true) &&
                             BLEAdvertising.addServiceUuid(serviceUuid) &&
                             BLEAdvertising.setScanResponseName(true) &&
                             BLEAdvertising.start();
        return advertisingStarted;
    }

    /** @brief exact local name으로 upstream active scan을 시작합니다. */
    bool startScan()
    {
        scanStarted = BLEScan.clearFilters() && BLEScan.filterName(peerName()) &&
                      BLEScan.start(true);
        return scanStarted;
    }

    /** @brief mixed role의 두 upstream transport가 준비되면 downstream 광고를 엽니다. */
    void advertiseMixedIfReady()
    {
        if (nodeRole == NodeRole::mixed && clientGattReady && clientCocReady &&
            !startAdvertising())
        {
            fail("mixed advertising");
        }
    }

    /** @brief exact-name scan 결과 하나의 주소를 main loop에 전달합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
        }
    }

    /** @brief GATT client 완료를 generation 기반 upstream link와 대조합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.connection != clientConnection)
        {
            fail("cross-link GATT event");
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::discovery_complete)
        {
            clientGattReady = true;
            advertiseMixedIfReady();
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::write_complete)
        {
            gattPending = false;
            finishTrafficIfComplete();
        }
        else if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            fail("GATT client operation");
        }
    }

    /** @brief downstream GATT write의 link와 payload 길이를 확인합니다. */
    void onCharacteristic(nucode::ble::BLECharacteristic &characteristic,
                          const nucode::ble::BLECharacteristicEventInfo &information,
                          void *context)
    {
        static_cast<void>(characteristic);
        static_cast<void>(context);
        if (information.event != nucode::ble::BLECharacteristicEvent::written)
        {
            return;
        }
        if (information.connection != serverConnection ||
            information.length != mixed_gatt_coc::Payload::length)
        {
            fail("cross-link or malformed GATT write");
            return;
        }
        Serial.println("downstream GATT write received");
    }

    /** @brief local role을 이용해 두 generation connection handle을 분리합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            if (information.role == nucode::ble::BLELinkRole::central && hasClient())
            {
                clientConnection = information.connection;
                if (!BLEL2cap.connect(clientConnection, cocPsm, clientChannel) ||
                    !BLEClient.discover(clientConnection, serviceUuid, characteristicUuid))
                {
                    fail("upstream setup");
                }
            }
            else if (information.role == nucode::ble::BLELinkRole::peripheral && hasServer())
            {
                serverConnection = information.connection;
                Serial.println("downstream link connected");
            }
            else
            {
                fail("unexpected link role");
            }
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            fail("unexpected disconnect");
        }
        else if (information.event == nucode::ble::BLEEvent::error)
        {
            fail("GAP event");
        }
    }

    /** @brief upstream echo와 downstream echo를 channel handle로 분리합니다. */
    void onL2capEvent(const nucode::ble::BLEL2capEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEL2capEvent::connected)
        {
            if (information.connection == clientConnection &&
                information.channel == clientChannel)
            {
                clientCocReady = true;
                advertiseMixedIfReady();
            }
            else if (information.connection == serverConnection && hasServer())
            {
                serverChannel = information.channel;
            }
            else
            {
                fail("cross-link CoC connect");
            }
            return;
        }
        if (information.event == nucode::ble::BLEL2capEvent::disconnected)
        {
            fail("CoC disconnect");
            return;
        }
        if (information.event != nucode::ble::BLEL2capEvent::received)
        {
            return;
        }
        if (information.channel == clientChannel)
        {
            if (!cocPending || !mixed_gatt_coc::Payload::matches(
                                   information.data, information.length, cocPayload))
            {
                fail("upstream CoC echo");
                return;
            }
            cocPending = false;
            finishTrafficIfComplete();
            return;
        }
        if (information.channel != serverChannel ||
            !BLEL2cap.send(serverChannel, information.data, information.length))
        {
            fail("downstream CoC echo");
        }
    }

    /** @brief GATT 응답과 CoC echo가 모두 끝난 sequence만 성공으로 출력합니다. */
    void finishTrafficIfComplete()
    {
        if (!trafficActive || gattPending || cocPending)
        {
            return;
        }
        trafficActive = false;
        Serial.print("GATT+CoC PASS, sequence=");
        Serial.println(sequence);
        ++sequence;
    }

    /** @brief client role에서 GATT write와 CoC echo를 같은 sequence로 함께 시작합니다. */
    void issueTraffic()
    {
        if (!hasClient() || !clientGattReady || !clientCocReady || trafficActive ||
            gattPending || cocPending || BLEClient.busy(clientConnection) ||
            BLEL2cap.availableForWrite() < 2U)
        {
            return;
        }
        const std::uint32_t now = millis();
        if (now - lastSendMs < sendIntervalMs)
        {
            return;
        }
        lastSendMs = now;
        mixed_gatt_coc::Payload::build(gattPayload, roleMarker(), gattTransport, sequence);
        mixed_gatt_coc::Payload::build(cocPayload, roleMarker(), cocTransport, sequence);
        if (!BLEClient.write(clientConnection, gattPayload, sizeof(gattPayload)))
        {
            fail("GATT write start");
            return;
        }
        gattPending = true;
        if (!BLEL2cap.send(clientChannel, cocPayload, sizeof(cocPayload)))
        {
            fail("CoC send start");
            return;
        }
        cocPending = true;
        trafficActive = true;
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    if (hasServer())
    {
        exampleCharacteristic.onEvent(onCharacteristic);
        if (!exampleService.addCharacteristic(exampleCharacteristic) ||
            !BLEDevice.addService(exampleService))
        {
            fail("GATT schema");
            return;
        }
    }
    BLEDevice.onEventInfo(onBleEvent);
    BLEL2cap.onEvent(onL2capEvent);
    if (hasClient())
    {
        BLEScan.onResult(onScanResult);
        BLEClient.onDetailedEvent(onClientEvent);
    }
    if (!BLEDevice.begin(localName()) || (hasServer() && !BLEL2cap.startServer(cocPsm)))
    {
        fail("BLE begin");
        return;
    }
    if ((nodeRole == NodeRole::peripheral && !startAdvertising()) ||
        (hasClient() && !startScan()))
    {
        fail("radio start");
        return;
    }
    Serial.print("M29 mixed example ready, role=");
    Serial.println(localName());
}

void loop()
{
    BLEDevice.poll();
    if (stopped)
    {
        delay(10);
        return;
    }
    if (peerFound && scanStarted)
    {
        peerFound = false;
        scanStarted = false;
        if (!BLEScan.stop() || !BLEConnection.connect(peerAddress, clientConnection))
        {
            fail("upstream connect");
            return;
        }
    }
    issueTraffic();
}
