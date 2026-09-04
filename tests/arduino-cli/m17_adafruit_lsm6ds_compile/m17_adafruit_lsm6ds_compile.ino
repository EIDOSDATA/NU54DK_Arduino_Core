#include <Adafruit_LSM6DS3TRC.h>
#include <SPI.h>
#include <Wire.h>

Adafruit_LSM6DS3TRC sensor;

void setup()
{
    Wire.begin();
    (void)sensor.begin_I2C();
}

void loop()
{
}
