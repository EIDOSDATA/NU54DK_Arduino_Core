#include <NUCODE_Peripheral_Fabric.h>

namespace
{
    volatile bool fabric_ready = false;
}

void setup()
{
    using namespace nucode::arduino;
    using namespace nucode::peripheral;

    const bool serial_ready =
        serialFabric().uarte(0U) != nullptr && serialFabric().spim(0U) != nullptr &&
        serialFabric().spis(0U) != nullptr && serialFabric().twim(20U) != nullptr &&
        serialFabric().twis(20U) != nullptr;
    const bool analog_ready = analogFabric().pwm(20U) != nullptr;
    const bool event_ready =
        eventFabric().timer(20U) != nullptr && eventFabric().egu(20U) != nullptr &&
        eventFabric().gpiote(20U) != nullptr && eventFabric().dppi(20U) != nullptr &&
        eventFabric().ppib(20U) != nullptr;
    const bool stream_ready =
        streamFabric().pdm(20U) != nullptr && streamFabric().i2s(20U) != nullptr;
    const bool system_ready = systemFabric().watchdog(30U) != nullptr;
    const bool inventory_ready = peripheralInventorySize() == 75U;

    fabric_ready = serial_ready && analog_ready && event_ready && stream_ready && system_ready &&
                   inventory_ready && isSupported(capabilities.serial) &&
                   isSupported(capabilities.analog) && isSupported(capabilities.event) &&
                   isSupported(capabilities.pdm) && isSupported(capabilities.i2s) &&
                   capabilities.qdec == Support::unsupported && isSupported(capabilities.system);

    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, fabric_ready ? HIGH : LOW);
}

void loop()
{
    delay(1000U);
}
