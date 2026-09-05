/** @file @brief R02의 실제 thread IRQ 모델을 Fabric driver에도 적용합니다. */
#pragma once
#include "../../serial_driver_stubs/zephyr/irq.h"
#define IRQ_PRIO_LOWEST 3
#define SAADC_IRQn 0
#define PWM20_IRQn 1
#define PWM21_IRQn 2
#define PWM22_IRQn 3
#define PDM20_IRQn 4
#define PDM21_IRQn 5
#define I2S20_IRQn 6
#define QDEC20_IRQn 7
#define QDEC21_IRQn 8
#define IRQ_CONNECT(irq, priority, fn, context, flags) (void)&fn
