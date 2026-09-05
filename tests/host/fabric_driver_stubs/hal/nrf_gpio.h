/** @file @brief Fabric pin 변환에 필요한 GPIO HAL 상수입니다. */
#pragma once
#include "../../serial_fabric_stubs/hal/nrf_gpio.h"
#define NRF_GPIO_PIN_MAP(port, pin) ((port) * 32U + (pin))
