/**
 * @file L2capCocServer.ino
 * @brief 두 LE CoC channel에서 최대 512-byte SDU를 그대로 돌려주는 echo server 예제입니다.
 */

#include <NUCODE_BLE.h>

constexpr std::uint16_t echoPsm = 0x0080U;
bool restartAdvertising = false;

/** @brief 연결 해제 뒤 connectable advertising 재시작을 예약합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::disconnected)
    {
        restartAdvertising = true;
    }
}

/** @brief main thread에서 받은 SDU를 같은 channel에 echo합니다. */
void onL2capEvent(const nucode::ble::BLEL2capEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEL2capEvent::connected)
    {
        Serial.print("LE CoC connected, remote MTU=");
        Serial.println(information.remote_mtu);
    }
    else if (information.event == nucode::ble::BLEL2capEvent::received)
    {
        if (!BLEL2cap.send(information.channel, information.data, information.length))
        {
            Serial.print("LE CoC echo failed, error=");
            Serial.println(static_cast<unsigned>(BLEDevice.lastError()));
        }
    }
    else if (information.event == nucode::ble::BLEL2capEvent::disconnected)
    {
        Serial.println("LE CoC disconnected");
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEL2cap.onEvent(onL2capEvent);

    if (!BLEDevice.begin("NU54-CoC-Echo") || !BLEL2cap.startServer(echoPsm) ||
        !BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.start())
    {
        Serial.print("LE CoC server start failed, error=");
        Serial.println(static_cast<unsigned>(BLEDevice.lastError()));
        return;
    }
    Serial.print("LE CoC echo PSM=0x");
    Serial.println(BLEL2cap.serverPsm(), HEX);
}

void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && BLEConnection.count() == 0U)
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("BLE advertising restart failed");
        }
    }
}
