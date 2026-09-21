/**
 * @file p0_serial_spi.ino
 * @brief P0 adaptive profile이 실제 SPI 참조만 추가하는지 검증합니다.
 */

#include <SPI.h>

void setup()
{
    Serial.begin(115200);
    SPI.begin();
}

void loop()
{
}
