/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) CapUnicastInitiator (initiator); 2) CapUnicastAcceptor (acceptor)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE_Audio/CapUnicastAcceptor`, sha256 `887c4267cb1ac7831c5eb5e8cfbc4f41ce7b3a3a5dc8e7a34fcc9bdaab234390`
 * @nucode_example_setup_end */

/**
 * @file CapUnicastAcceptor.ino
 * @brief CAP Acceptor의 unicast LC3 stream을 수신하고 PCM으로 복호화합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>

using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::audio::CapAcceptor;
using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::UnicastServer;

namespace
{
    CapAcceptor acceptor;
    UnicastServer audioSink;
    Lc3Codec codec;
    bool restartAdvertising = false;
    bool setupReady = false;
    const char *statusMessage = "starting";
    std::uint32_t decodedFrames = 0U;
    std::uint32_t lastStatusAt = 0U;

    /** @brief 연결 해제 뒤 다음 Initiator를 받을 광고를 예약합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            Serial.print("CAP Initiator disconnected reason=");
            Serial.println(event.reason);
        }
    }

    /** @brief PCM frame의 절대값 합으로 실제 decode 결과를 확인합니다. */
    std::uint32_t frameEnergy(const std::int16_t (&pcm)[160])
    {
        std::uint32_t energy = 0U;
        for (const std::int16_t sample : pcm)
        {
            const std::int32_t value = sample;
            energy += static_cast<std::uint32_t>((value < 0) ? -value : value);
        }
        return energy;
    }
} // namespace

/** @brief CAS와 PACS/ASCS sink, codec, 연결 가능 광고를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("CAP Acceptor starting");
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLEDevice.begin("NU54-CAP-UNICAST-SINK"))
    {
        statusMessage = "BLE start failed";
        Serial.println("CAP Acceptor BLE start failed");
        return;
    }
    Serial.println("CAP Acceptor BLE ready");

    if (acceptor.begin() != Error::none)
    {
        statusMessage = "service registration failed";
        Serial.print("CAP service registration failed: ");
        Serial.println(acceptor.nativeCode());
        return;
    }
    Serial.println("CAP service ready");

    if (audioSink.begin() != Error::none)
    {
        statusMessage = "unicast server failed";
        Serial.print("CAP unicast server failed: ");
        Serial.println(audioSink.nativeCode());
        return;
    }
    Serial.println("CAP unicast server ready");

    if (codec.begin() != Error::none)
    {
        statusMessage = "codec failed";
        Serial.println("CAP codec failed");
        return;
    }
    Serial.println("CAP codec ready");

    constexpr std::uint8_t announcement[] = {1U, 0x03U, 0x00U, 0x00U, 0x00U, 0U};
    if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x1853U)) ||
        !BLEAdvertising.addServiceUuid(BLEUuid(0x184EU)) ||
        !BLEAdvertising.setServiceData(BLEUuid(0x184EU), announcement, sizeof(announcement)) ||
        !BLEAdvertising.start())
    {
        statusMessage = "advertising failed";
        Serial.println("CAP Acceptor advertising failed");
        return;
    }
    setupReady = true;
    statusMessage = "waiting for Initiator";
    Serial.println("CAP unicast Acceptor ready");
}

/** @brief 수신 LC3 frame을 공개 codec으로 복호화하고 통계를 출력합니다. */
void loop()
{
    const std::uint32_t now = millis();
    if ((now - lastStatusAt) >= 2000U)
    {
        lastStatusAt = now;
        Serial.print("CAP Acceptor status: ");
        Serial.println(statusMessage);
    }
    if (!setupReady)
    {
        delay(1U);
        return;
    }

    BLEDevice.poll();
    if (restartAdvertising && !BLEConnection.connected())
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            restartAdvertising = true;
            Serial.println("CAP Acceptor advertising restart failed");
        }
    }

    std::uint8_t frame[40] = {};
    while (audioSink.readFrame(frame))
    {
        std::int16_t pcm[160] = {};
        if (codec.decode(frame, sizeof(frame), pcm, 160U) != Error::none)
        {
            Serial.println("CAP decode failed");
            continue;
        }
        decodedFrames++;
        if ((decodedFrames % 100U) == 0U)
        {
            Serial.print("CAP decoded frames=");
            Serial.print(decodedFrames);
            Serial.print(" energy=");
            Serial.print(frameEnergy(pcm));
            Serial.print(" dropped=");
            Serial.println(audioSink.droppedFrames());
        }
    }
    delay(1U);
}
