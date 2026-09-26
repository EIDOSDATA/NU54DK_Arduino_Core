/**
 * @file MediaControlPlayer.ino
 * @brief 합성 track과 Media Control Service를 제공하는 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_BLE_Security.h>

using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLEUuid;
using nucode::ble::SecurityConfig;
using nucode::ble::SecurityEvent;
using nucode::ble::SecurityEventRecord;
using nucode::ble::SecurityIoCapability;
using nucode::ble::SecurityLevel;
using nucode::ble::audio::Error;
using nucode::ble::audio::MediaControlPlayer;

namespace
{
    MediaControlPlayer player;
    bool restartAdvertising = false;
    std::uint32_t restartAt = 0U;

    /** @brief MCS UUID와 전체 장치 이름을 광고합니다. */
    bool startAdvertising()
    {
        return BLEAdvertising.clear() && BLEAdvertising.setConnectable(true) &&
               BLEAdvertising.addServiceUuid(BLEUuid(0x1848U)) &&
               BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    }

    /** @brief Just Works pairing 요청을 승인합니다. */
    void onSecurityEvent(const SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == SecurityEvent::pairing_requested)
        {
            static_cast<void>(BLESecurity.acceptPairing(event.connection, true));
        }
    }

    /** @brief controller 연결 해제 뒤 MCS 광고를 다시 시작합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == BLEEvent::connected)
        {
            Serial.println("Media controller connected");
        }
        else if (event.event == BLEEvent::disconnected)
        {
            restartAdvertising = true;
            restartAt = millis() + 100U;
            Serial.print("Media controller disconnected reason=");
            Serial.println(event.reason);
        }
    }
} // namespace

/** @brief 보안과 합성 media player를 광고 전에 준비합니다. */
void setup()
{
    Serial.begin(115200);
    SecurityConfig security;
    security.minimum_level = SecurityLevel::encrypted;
    security.bonding = false;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-MEDIA-PLAYER") ||
        (player.begin() != Error::none) || !startAdvertising())
    {
        Serial.print("Media player start failed native=");
        Serial.println(player.nativeCode());
        return;
    }
    Serial.println("Media player ready; s=status x=stop service ownership");
}

/** @brief BLE lifecycle과 사용자가 선택한 service 상태 명령을 처리합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    if (restartAdvertising && !BLEAdvertising.running() &&
        (static_cast<std::int32_t>(millis() - restartAt) >= 0))
    {
        if (startAdvertising())
        {
            restartAdvertising = false;
            Serial.println("Media advertising restarted");
        }
        else
        {
            restartAt = millis() + 1000U;
        }
    }
    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            Serial.print("Media player ready=");
            Serial.println(player.ready() ? 1 : 0);
        }
        else if (command == 'x')
        {
            static_cast<void>(BLEAdvertising.stop());
            const Error result = player.end();
            Serial.print("Media player stopped result=");
            Serial.println(static_cast<unsigned int>(result));
        }
    }
    delay(1U);
}
