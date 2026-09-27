/**
 * @file main.cpp
 * @brief M28 고정 2-slot과 generation handle의 target compile/link 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GAP.h>

#include <cstdint>

static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT == 1);
static_assert(nucode::ble::Device::maximumConnections() == 2U);

/** @brief 기존 callback signature의 source 호환을 고정합니다. */
void onLegacyEvent(nucode::ble::BLEEvent event, void *context)
{
    auto *value = static_cast<volatile std::uint8_t *>(context);
    if (value != nullptr)
    {
        *value = static_cast<std::uint8_t>(event);
    }
}

/** @brief link handle과 역할을 포함하는 상세 callback signature를 고정합니다. */
void onDetailedEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    auto *value = static_cast<volatile std::uint8_t *>(context);
    if (value != nullptr && information.connection.valid())
    {
        *value = static_cast<std::uint8_t>(information.role);
    }
}

int main()
{
    volatile std::uint8_t observed = 0U;
    nucode::ble::BLEConnectionHandle central;
    const nucode::ble::BLEAddress address("C0:12:34:56:78:9A",
                                          nucode::ble::BLEAddress::Type::random_address);

    BLEDevice.onEvent(onLegacyEvent, const_cast<std::uint8_t *>(&observed));
    BLEDevice.onEventInfo(onDetailedEvent, const_cast<std::uint8_t *>(&observed));
    static_cast<void>(BLEConnection.connect(address, central));
    static_cast<void>(BLEConnection.connecting(central));
    static_cast<void>(BLEConnection.connected(central));
    static_cast<void>(BLEConnection.count());
    static_cast<void>(BLEConnection.handle(nucode::ble::BLELinkRole::central));
    static_cast<void>(BLEConnection.role(central));
    static_cast<void>(BLEConnection.peerAddress(central));
    static_cast<void>(BLEConnection.mtu(central));
    static_cast<void>(BLEConnection.requestMtu(central));
    static_cast<void>(BLEConnection.phy(central));
    static_cast<void>(BLEConnection.requestPhy(central, true, true));
    std::int8_t power = 0;
    static_cast<void>(BLEConnection.txPower(central, power));
    static_cast<void>(BLEConnection.requestParameters(central, 24U, 40U, 0U, 400U));
    static_cast<void>(BLEConnection.disconnect(central));
    static_cast<void>(BLEConnection.reconnect(central));
    return 0;
}
