/**
 * @file main.cpp
 * @brief M32-W10 공존 telemetry와 1-wire 공개 API target compile 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_Radio_Coexistence.h>

/** @brief 모든 bounded 관측 signature를 target compiler로 확인합니다. */
int main()
{
    using nucode::coexistence::Protocol;

    static_cast<void>(NUCODECoexistence.begin(500U));
    NUCODECoexistence.recordRequested(Protocol::ble);
    NUCODECoexistence.recordDelivered(Protocol::ble, 1U, 0x12345678U, true);
    NUCODECoexistence.recordDropped(Protocol::mesh);
    NUCODECoexistence.recordTimeslotFailure(Protocol::esb);
    NUCODECoexistence.recordRestart(Protocol::ieee802154);
    NUCODECoexistence.setActive(Protocol::external_radio, true);
    static_cast<void>(NUCODECoexistence.statistics(Protocol::ble));
    static_cast<void>(NUCODECoexistence.healthy());
    static_cast<void>(NUCODECoexistence.oneWireSupported());
    static_cast<void>(NUCODECoexistence.radioEventCount());

#if defined(CONFIG_NUCODE_RADIO_COEX_ONEWIRE)
    static_cast<void>(NUCODECoexistence.beginOneWire());
    static_cast<void>(NUCODECoexistence.setExternalGrant(true));
#endif
    NUCODECoexistence.stop();
    return 0;
}
