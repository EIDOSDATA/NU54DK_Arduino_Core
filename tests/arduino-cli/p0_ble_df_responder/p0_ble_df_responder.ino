/**
 * @file p0_ble_df_responder.ino
 * @brief P0 adaptive BLE 역할의 저수준 설정 없는 build fixture입니다.
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_DirectionFinding.h>

/** @brief 역할별 library source가 compile되는 최소 Arduino 진입점입니다. */
void setup()
{
    Serial.begin(115200);
}

/** @brief build-only fixture의 반복 진입점입니다. */
void loop()
{
}
