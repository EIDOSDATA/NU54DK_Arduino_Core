/** @file @brief 실제 ArduinoCore-API와 NU54DK SPI 공개 형식을 연결합니다. */
#pragma once
#include <NUCODEPeripheral.h>
using SPIClass = nucode::arduino::Nu54SPIClass;
using arduino::SPISettings;
