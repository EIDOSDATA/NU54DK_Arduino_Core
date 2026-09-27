/**
 * @file p0_spi_include_only.ino
 * @brief SPI header include만으로 backend가 선택되지 않는지 검증합니다.
 */

#include <SPI.h>

void setup()
{
    Serial.begin(115200);
    Serial.println("P0 include only");
}

void loop()
{
}
