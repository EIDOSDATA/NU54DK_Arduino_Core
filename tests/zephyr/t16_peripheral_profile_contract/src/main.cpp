/**
 * @file main.cpp
 * @brief T16 설치 facade와 지원 Fabric factory가 한 image에 링크되는지 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_Peripheral_Fabric.h>

namespace
{
    volatile bool fabric_ready = false;
}

void setup()
{
    using namespace nucode::arduino;
    using namespace nucode::peripheral;

    fabric_ready = serialFabric().uarte(0U) != nullptr && serialFabric().spim(0U) != nullptr &&
                   serialFabric().spis(0U) != nullptr && serialFabric().twim(20U) != nullptr &&
                   serialFabric().twis(20U) != nullptr && analogFabric().pwm(20U) != nullptr &&
                   eventFabric().timer(20U) != nullptr && eventFabric().egu(20U) != nullptr &&
                   eventFabric().gpiote(20U) != nullptr && eventFabric().dppi(20U) != nullptr &&
                   eventFabric().ppib(20U) != nullptr && streamFabric().pdm(20U) != nullptr &&
                   streamFabric().i2s(20U) != nullptr && streamFabric().qdec(20U) != nullptr &&
                   streamFabric().qdec(21U) != nullptr && systemFabric().watchdog(30U) != nullptr &&
                   peripheralInventorySize() == 75U && isSupported(capabilities.serial) &&
                   isSupported(capabilities.analog) && isSupported(capabilities.event) &&
                   isSupported(capabilities.pdm) && isSupported(capabilities.i2s) &&
                   isSupported(capabilities.qdec) && isSupported(capabilities.system);
}

void loop()
{
    delay(fabric_ready ? 1000U : 100U);
}
