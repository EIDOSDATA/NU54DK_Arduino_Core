/**
 * @file L2capCocClient.ino
 * @brief 한 BLE link에 두 LE CoC channel을 열고 512-byte echo를 확인하는 client 예제입니다.
 */

#include <NUCODE_BLE.h>
#include <P2MemoryTelemetry.h>

#include <string.h>

constexpr std::uint16_t echoPsm = 0x0080U;
constexpr std::size_t channelCount = 2U;

nucode::ble::BLEAddress peerAddress;
nucode::ble::BLEConnectionHandle peerConnection;
nucode::ble::BLEL2capChannelHandle channels[channelCount];
std::uint8_t payload[nucode::ble::L2capCoc::maximum_sdu_length] = {};
std::uint32_t sequence = 0U;
std::uint32_t lastSendMs = 0U;
std::size_t connectedChannels = 0U;
std::size_t echoCount = 0U;
std::size_t pendingEchoes = 0U;
bool peerFound = false;
bool restartScan = false;
unsigned long p2LastReport = 0UL;
bool p2Stopped = false;
bool burstActive = false;
std::size_t burstStartEchoes = 0U;
std::size_t burstSent = 0U;
bool burstBackpressure = false;

/** @brief exact local-name scan 결과의 주소를 main thread에서 보존합니다. */
void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
{
    static_cast<void>(context);
    if (!peerFound)
    {
        peerAddress = result.address;
        peerFound = true;
    }
}

/** @brief GAP 연결 뒤 동일 PSM에 두 channel 연결을 시작합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::connected &&
        information.role == nucode::ble::BLELinkRole::central)
    {
        peerConnection = information.connection;
        for (std::size_t index = 0U; index < channelCount; ++index)
        {
            if (!BLEL2cap.connect(peerConnection, echoPsm, channels[index]))
            {
                Serial.print("LE CoC connect failed, channel=");
                Serial.println(index);
                break;
            }
        }
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected)
    {
        connectedChannels = 0U;
        pendingEchoes = 0U;
        peerConnection = nucode::ble::BLEConnectionHandle{};
        restartScan = !p2Stopped;
        Serial.println("P2_COC_DISCONNECTED");
    }
}

/** @brief channel 연결과 echo payload를 main thread에서 검증합니다. */
void onL2capEvent(const nucode::ble::BLEL2capEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEL2capEvent::connected)
    {
        ++connectedChannels;
        Serial.print("LE CoC channel ready, count=");
        Serial.println(connectedChannels);
    }
    else if (information.event == nucode::ble::BLEL2capEvent::received)
    {
        if (information.length != sizeof(payload) ||
            ::memcmp(information.data, payload, sizeof(payload)) != 0)
        {
            Serial.println("LE CoC echo corrupt");
            return;
        }
        ++echoCount;
        if (pendingEchoes != 0U)
        {
            --pendingEchoes;
        }
        Serial.print("LE CoC echo PASS, count=");
        Serial.println(echoCount);
    }
}

/** @brief sequence와 byte offset으로 검증 가능한 512-byte SDU를 만듭니다. */
void preparePayload()
{
    for (std::size_t index = 0U; index < sizeof(payload); ++index)
    {
        payload[index] = static_cast<std::uint8_t>((sequence + index * 13U) & 0xffU);
    }
    ++sequence;
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLEL2cap.onEvent(onL2capEvent);
    if (!BLEDevice.begin("NU54-CoC-Client") || !BLEScan.clearFilters() ||
        !BLEScan.filterName("NU54-CoC-Echo") || !BLEScan.start(true))
    {
        Serial.print("LE CoC client start failed, error=");
        Serial.println(static_cast<unsigned>(BLEDevice.lastError()));
        Serial.println("P2_FAIL stage=coc-client-start");
        p2Stopped = true;
        return;
    }
    Serial.println("P2_READY role=coc-client");
    nucode::test::reportMemory("ready");
    p2LastReport = millis();
}

void loop()
{
    if (p2Stopped)
    {
        return;
    }
    BLEDevice.poll();
    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        static_cast<void>(BLEScan.stop());
        if (!BLEConnection.connect(peerAddress))
        {
            Serial.println("BLE peer connect failed");
        }
    }
    if (restartScan && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        restartScan = false;
        if (!BLEScan.start(true))
        {
            Serial.println("P2_FAIL stage=coc-scan-restart");
        }
    }

    const std::uint32_t now = millis();
    if (connectedChannels == channelCount && pendingEchoes == 0U &&
        !burstActive &&
        now - lastSendMs >= 1000U &&
        BLEL2cap.availableForWrite() >= channelCount)
    {
        lastSendMs = now;
        preparePayload();
        for (const nucode::ble::BLEL2capChannelHandle channel : channels)
        {
            if (!BLEL2cap.send(channel, payload, sizeof(payload)))
            {
                Serial.print("LE CoC send backpressure, free=");
                Serial.println(BLEL2cap.availableForWrite());
                break;
            }
            ++pendingEchoes;
        }
    }
    if (Serial.available() > 0)
    {
        const int command = Serial.read();
        if (command == 'b')
        {
            if ((connectedChannels != channelCount) || (pendingEchoes != 0U) ||
                burstActive || (BLEL2cap.availableForWrite() < nucode::ble::L2capCoc::transmit_buffers))
            {
                Serial.println("P2_COC_BURST_REJECTED");
            }
            else
            {
                preparePayload();
                burstStartEchoes = echoCount;
                burstSent = 0U;
                burstBackpressure = false;
                burstActive = true;
                for (std::size_t index = 0U;
                     index <= nucode::ble::L2capCoc::transmit_buffers; ++index)
                {
                    if (!BLEL2cap.send(channels[0], payload, sizeof(payload)))
                    {
                        burstBackpressure =
                            BLEDevice.lastError() == nucode::ble::BLEError::busy;
                        break;
                    }
                    ++burstSent;
                    ++pendingEchoes;
                }
                Serial.print("P2_COC_BURST_START sent=");
                Serial.print(burstSent);
                Serial.print(" backpressure=");
                Serial.println(burstBackpressure ? 1 : 0);
            }
        }
        else if ((command == 'd') && peerConnection.valid())
        {
            if (!BLEConnection.disconnect(peerConnection))
            {
                Serial.println("P2_FAIL stage=coc-disconnect");
            }
            else
            {
                Serial.println("P2_COC_DISCONNECT_REQUESTED");
            }
        }
        else if (command == 's')
        {
            p2Stopped = true;
            BLEDevice.end();
            nucode::test::reportMemory("stopped");
            Serial.print("P2_STOP role=coc-client echoes=");
            Serial.println(echoCount);
            return;
        }
    }
    if (burstActive && (pendingEchoes == 0U))
    {
        burstActive = false;
        Serial.print("P2_COC_BURST_DONE sent=");
        Serial.print(burstSent);
        Serial.print(" echoes=");
        Serial.println(echoCount - burstStartEchoes);
    }
    if (millis() - p2LastReport >= 10000UL)
    {
        nucode::test::reportMemory("traffic");
        p2LastReport = millis();
    }
}
