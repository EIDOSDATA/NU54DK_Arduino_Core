/** @file @brief T13 계획의 모든 직렬 경로를 생산 validator에 전달합니다. */
#include "serial_fabric_routes.h"
#include "internal/pin_description.h"
#include <zephyr/device.h>
#include <iostream>
using namespace nucode::arduino;
using namespace nucode::arduino::internal;
device mock_gpio0{0}, mock_gpio1{1}, mock_gpio2{2};
PinDescription descriptions[96]{};
namespace nucode::arduino::internal
{
    const PinDescription *pinDescription(pin_size_t pin)
    {
        return pin < 96U ? &descriptions[pin] : nullptr;
    }
} // namespace nucode::arduino::internal
int main()
{
    device *ports[]{&mock_gpio0, &mock_gpio1, &mock_gpio2};
    for (unsigned pin = 0U; pin < 96U; ++pin)
    {
        descriptions[pin] = {{ports[pin / 32U], pin % 32U}, PinPolicy::normal, 7U, pin};
    }
    for (unsigned pin = 36U; pin <= 39U; ++pin)
    {
        descriptions[pin].policy = PinPolicy::system_reserved;
        descriptions[pin].capabilities = 0U;
    }
    for (unsigned pin = 0U; pin <= 3U; ++pin)
    {
        descriptions[pin].policy = PinPolicy::conditional_dap_uart;
        descriptions[pin].capabilities = 0U;
    }
    unsigned kind, instance, bank, profile, count;
    while (std::cin >> kind >> instance >> bank >> profile >> count)
    {
        if (count > 6U)
        {
            return 1;
        }
        SerialSignalPin pins[6]{};
        for (unsigned index = 0U; index < count; ++index)
        {
            unsigned signal, pin;
            std::cin >> signal >> pin;
            pins[index] = {static_cast<SerialSignal>(signal), pin};
        }
        ValidatedSerialRoute route{};
        IoResourceId resources[16]{};
        std::size_t resource_count = 0U;
        const auto result = validateNu54dkSerialFabricRoute(
            static_cast<SerialPersonality>(kind), static_cast<std::uint8_t>(instance),
            {static_cast<SerialRouteClass>(bank), static_cast<SerialElectricalProfile>(profile),
             pins, count},
            route, resources, 16U, resource_count);
        std::cout << static_cast<unsigned>(result) << '\n';
    }
}
