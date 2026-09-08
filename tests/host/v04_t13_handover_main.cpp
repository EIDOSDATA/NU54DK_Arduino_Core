/** @file @brief 실제 target 역할 변환을 생산 route validator와 독립 Host 기대값으로 대조합니다. */
#include "serial_fabric_routes.h"
#include "internal/pin_description.h"
#include "cases.h"
#include "handover.h"
#include <zephyr/device.h>
#include <cstring>
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
    static_assert(static_cast<unsigned>(SerialSignal::mosi) == 6U);
    static_assert(static_cast<unsigned>(SerialSignal::miso) == 7U);
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
    for (const auto &original : t13::cases)
    {
        auto test = original;
        const bool accepted = t13::reverseSerialCase(test);
        std::cout << "CASE " << test.id << ' ' << accepted << '\n';
        if (!accepted)
        {
            if (std::memcmp(&test, &original, sizeof(test)) != 0)
            {
                return 1;
            }
            continue;
        }
        for (unsigned role = 0U; role < 2U; ++role)
        {
            const auto &endpoint = test.serial[role][0];
            SerialSignalPin pins[4]{};
            for (unsigned index = 0U; index < endpoint.pin_count; ++index)
            {
                pins[index] = {static_cast<SerialSignal>(endpoint.signals[index]),
                               endpoint.pins[index]};
            }
            ValidatedSerialRoute route{};
            IoResourceId resources[16]{};
            std::size_t resource_count = 0U;
            const auto result = validateNu54dkSerialFabricRoute(
                static_cast<SerialPersonality>(static_cast<unsigned>(endpoint.kind) - 1U),
                static_cast<std::uint8_t>(endpoint.instance),
                {static_cast<SerialRouteClass>(endpoint.bank),
                 static_cast<SerialElectricalProfile>(endpoint.profile), pins, endpoint.pin_count},
                route, resources, 16U, resource_count);
            std::cout << "END " << test.id << ' ' << role << ' '
                      << static_cast<unsigned>(endpoint.kind) << ' '
                      << static_cast<unsigned>(result);
            for (unsigned index = 0U; index < endpoint.pin_count; ++index)
            {
                std::cout << ' ' << endpoint.signals[index] << ' ' << endpoint.pins[index];
            }
            std::cout << '\n';
        }
        if (!t13::reverseSerialCase(test) || std::memcmp(&test, &original, sizeof(test)) != 0)
        {
            return 2;
        }
    }
}
