/**
 * @file p2_gatt_peripheral.ino
 * @brief 512 B long write와 재연결에 대한 P2 peripheral 계측입니다.
 */

#include <NUCODE_BLE.h>
#include <P2MemoryTelemetry.h>

const nucode::ble::BLEUuid serviceUuid("8e7e2903-7d8c-4c1a-9d2d-8b6519f77410");
const nucode::ble::BLEUuid valueUuid("8e7e2904-7d8c-4c1a-9d2d-8b6519f77410");
nucode::ble::BLEService writeService(serviceUuid);
nucode::ble::BLECharacteristic writeValue(
    valueUuid, nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write,
    nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, 512U);
bool running = false;
bool restartAdvertising = false;
bool waitingForRecycle = false;
unsigned int receivedWrites = 0U;
unsigned long lastReport = 0UL;

/** @brief 오류를 한 줄로 기록하고 시험을 중단합니다. */
void fail(const char *stage)
{
    Serial.print("P2_FAIL stage=");
    Serial.print(stage);
    Serial.print(" driver=");
    Serial.println(BLEDevice.lastDriverError());
    running = false;
}

/** @brief 완전한 long write만 누적합니다. */
void onValueEvent(nucode::ble::BLECharacteristic &characteristic,
                  const nucode::ble::BLECharacteristicEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event != nucode::ble::BLECharacteristicEvent::written)
    {
        return;
    }
    if (!information.connection.valid() || information.offset != 0U ||
        information.without_response || information.length != 512U ||
        characteristic.valueLength() != 512U)
    {
        fail("partial-write");
        return;
    }
    ++receivedWrites;
    Serial.print("P2_RX writes=");
    Serial.println(receivedWrites);
}

/** @brief 연결 해제 뒤 advertising을 main loop에서 재시작합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::error)
    {
        fail("ble-event");
    }
    else if (information.event == nucode::ble::BLEEvent::disconnected)
    {
        waitingForRecycle = true;
        Serial.println("P2_LINK disconnected");
    }
    else if (information.event == nucode::ble::BLEEvent::connection_recycled &&
             waitingForRecycle)
    {
        waitingForRecycle = false;
        restartAdvertising = true;
    }
    else if (information.event == nucode::ble::BLEEvent::connected)
    {
        Serial.println("P2_LINK connected");
    }
}

/** @brief 테스트용 GATT server를 시작합니다. */
void setup()
{
    Serial.begin(115200);
    writeValue.onEvent(onValueEvent);
    BLEDevice.onEventInfo(onBleEvent);
    running = writeService.addCharacteristic(writeValue) && BLEDevice.addService(writeService) &&
              BLEDevice.begin("P2-GATT-P") && BLEAdvertising.clear() &&
              BLEAdvertising.setConnectable(true) && BLEAdvertising.addServiceUuid(serviceUuid) &&
              BLEAdvertising.setScanResponseName(true) && BLEAdvertising.start();
    if (!running)
    {
        fail("start");
        return;
    }
    Serial.println("P2_READY role=peripheral");
    nucode::test::reportMemory("ready");
    lastReport = millis();
}

/** @brief 수신·재광고·계측을 bounded main loop에서 수행합니다. */
void loop()
{
    if (!running)
    {
        return;
    }
    BLEDevice.poll();
    if (restartAdvertising)
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            fail("advertising-restart");
        }
    }
    if (millis() - lastReport >= 10000UL)
    {
        nucode::test::reportMemory("traffic");
        lastReport = millis();
    }
    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 's')
        {
            if (!BLEAdvertising.stop())
            {
                fail("stop");
            }
            nucode::test::reportMemory("stopped");
            Serial.print("P2_STOP writes=");
            Serial.println(receivedWrites);
            running = false;
        }
    }
}
