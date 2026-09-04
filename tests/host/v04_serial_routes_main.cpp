// Execute the real NU54DK validator with controlled board descriptors.
#include "serial_fabric_routes.h"
#include "internal/pin_description.h"
#include <zephyr/device.h>
#include <cassert>
#include <initializer_list>
using namespace nucode::arduino;
using namespace nucode::arduino::internal;
device mock_gpio0{0}, mock_gpio1{1}, mock_gpio2{2};
PinDescription descriptions[96]{};
namespace nucode::arduino::internal
{
    const PinDescription *pinDescription(pin_size_t pin) { return pin < 96 ? &descriptions[pin] : nullptr; }
}
SerialFabricResult check(SerialPersonality kind, unsigned instance, SerialRouteClass bank,
    SerialElectricalProfile electrical, const SerialSignalPin *pins, unsigned count)
{
    ValidatedSerialRoute route{};
    IoResourceId resources[16]{};
    std::size_t resource_count = 0;
    return validateNu54dkSerialFabricRoute(kind, instance, {bank, electrical, pins, count}, route, resources, 16, resource_count);
}
int main()
{
    device *ports[] = {&mock_gpio0, &mock_gpio1, &mock_gpio2};
    for (unsigned pin = 0; pin < 96; ++pin)
        descriptions[pin] = {{ports[pin / 32], pin % 32}, PinPolicy::normal, 7, pin};
    for (unsigned pin = 36; pin <= 39; ++pin)
    { descriptions[pin].policy = PinPolicy::system_reserved; descriptions[pin].capabilities = 0; }
    for (unsigned pin = 0; pin <= 3; ++pin)
    { descriptions[pin].policy = PinPolicy::conditional_dap_uart; descriptions[pin].capabilities = 0; }
    for (unsigned pin : {32U, 33U, 40U, 41U, 43U, 45U})
        descriptions[pin].policy = PinPolicy::input_only;
    const auto expected = TEST_UART_STATUS ? SerialFabricResult::unsafe_electrical_profile : SerialFabricResult::success;
    for (unsigned port = 0; port < 2; ++port)
    {
        const unsigned base = port ? 36 : 0;
        const unsigned instance = port ? 21 : 30;
        const auto bank = port ? SerialRouteClass::p1_flexible : SerialRouteClass::p0_flexible;
        const SerialSignalPin uart[] = {{SerialSignal::txd, base}, {SerialSignal::rxd, base + 1}};
        const SerialSignalPin spi[] = {{SerialSignal::sck, base}, {SerialSignal::mosi, base + 1}, {SerialSignal::miso, base + 2}, {SerialSignal::csn, base + 3}};
        const SerialSignalPin twi[] = {{SerialSignal::sda, base}, {SerialSignal::scl, base + 1}};
        assert(check(SerialPersonality::uarte, instance, bank, SerialElectricalProfile::dap_uart_disabled, uart, 2) == expected);
        for (auto kind : {SerialPersonality::spim, SerialPersonality::spis})
        {
            assert(check(kind, instance, bank, SerialElectricalProfile::dap_uart_disabled, spi, 4) == expected);
            assert(check(kind, instance, bank, SerialElectricalProfile::dap_uart_bridge, spi, 4) == SerialFabricResult::unsafe_electrical_profile);
        }
        for (auto kind : {SerialPersonality::twim, SerialPersonality::twis})
            assert(check(kind, instance, bank, SerialElectricalProfile::dap_uart_disabled, twi, 2) == expected);
    }
    const SerialSignalPin pmic[] = {{SerialSignal::sda, 34}, {SerialSignal::scl, 35}};
    assert(check(SerialPersonality::twim, 22, SerialRouteClass::p1_flexible, SerialElectricalProfile::pmic_read_only, pmic, 2) == SerialFabricResult::success);
    assert(check(SerialPersonality::twis, 22, SerialRouteClass::p1_flexible, SerialElectricalProfile::dap_uart_disabled, pmic, 2) == SerialFabricResult::unsafe_electrical_profile);
    const SerialSignalPin illegal[] = {{SerialSignal::txd, 70}, {SerialSignal::rxd, 72}};
    assert(check(SerialPersonality::uarte, 0, SerialRouteClass::p2_dedicated20, SerialElectricalProfile::connector_fixture, illegal, 2) == SerialFabricResult::unsupported_route);
    // MISO is an output for SPIS, MOSI/SCK/CSN inputs. Capabilities intentionally asymmetric.
    const SerialSignalPin asymmetric[] = {{SerialSignal::sck, 42}, {SerialSignal::mosi, 44}, {SerialSignal::miso, 46}, {SerialSignal::csn, 47}};
    descriptions[42].capabilities = descriptions[44].capabilities = descriptions[47].capabilities = 1;
    descriptions[46].capabilities = 2;
    assert(check(SerialPersonality::spis, 21, SerialRouteClass::p1_flexible, SerialElectricalProfile::connector_fixture, asymmetric, 4) == SerialFabricResult::success);
    assert(check(SerialPersonality::spim, 21, SerialRouteClass::p1_flexible, SerialElectricalProfile::connector_fixture, asymmetric, 4) == SerialFabricResult::unsupported_route);
}
