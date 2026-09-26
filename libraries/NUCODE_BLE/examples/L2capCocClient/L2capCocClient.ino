/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) L2capCocClient (client/controller); 2) L2capCocServer (server/device)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE/L2capCocClient`, sha256 `0086bbacad110d2302ff9588fff10c6f2af0c3f1fc75ab4dc20f7fdfbd797dc8`
 * @nucode_example_setup_end */

/**
 * @file L2capCocClient.ino
 * @brief 한 BLE link에 두 LE CoC channel을 열고 512-byte echo를 확인하는 client 예제입니다.
 */

#include <NUCODE_BLE.h>

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
    }
}

void loop()
{
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

    const std::uint32_t now = millis();
    if (connectedChannels == channelCount && pendingEchoes == 0U &&
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
}
