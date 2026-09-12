/**
 * @file PawrAdvertiser.ino
 * @brief 4 subevent × 4 response slot PAwR train을 송신하고 response를 읽습니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSet;
uint8_t extendedPayload[] = {3U, 0x09U, 'P', 'R'};

/** @brief main-thread로 전달된 PAwR response의 위치와 길이를 출력합니다. */
void onResponse(const nucode::ble::BLEPawrResponse &response, void *)
{
    Serial.print("response subevent=");
    Serial.print(response.subevent);
    Serial.print(" slot=");
    Serial.print(response.response_slot);
    Serial.print(" bytes=");
    Serial.println(response.payload_length);
}

void setup()
{
    Serial.begin(115200);
    nucode::ble::BLEExtendedAdvertisingParameters extendedParameters{};
    extendedParameters.sid = 3U;
    if (!BLEDevice.begin("NU54-PAWR-ADV") ||
        !BLEExtendedAdvertising.create(extendedParameters, advertisingSet) ||
        !BLEExtendedAdvertising.setData(advertisingSet, extendedPayload,
                                        sizeof(extendedPayload)) ||
        !BLEPawr.configureAdvertiser(advertisingSet))
    {
        return;
    }
    for (uint8_t subevent = 0U; subevent < 4U; ++subevent)
    {
        const uint8_t payload[] = {subevent, 0xa5U};
        if (!BLEPawr.setSubeventData(advertisingSet, subevent, payload,
                                    sizeof(payload)))
        {
            return;
        }
    }
    BLEPawr.onResponse(onResponse);
    static_cast<void>(BLEPeriodicAdvertising.start(advertisingSet));
    static_cast<void>(BLEExtendedAdvertising.start(advertisingSet));
}

void loop()
{
    BLEDevice.poll();
}
