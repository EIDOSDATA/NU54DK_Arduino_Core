/**
 * @file main.cpp
 * @brief M28-W03 extended advertising/scanning 공개 API의 target 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GAP.h>

static_assert(CONFIG_BT_EXT_ADV == 1);
static_assert(CONFIG_BT_EXT_ADV_MAX_ADV_SET == 1);
static_assert(CONFIG_BT_CTLR_ADV_DATA_LEN_MAX == 255);
static_assert(nucode::ble::ExtendedAdvertising::maximum_payload_length == 255U);
static_assert(nucode::ble::BLEScanResult::maximum_payload_length == 255U);

int main()
{
    nucode::ble::BLEExtendedAdvertisingParameters parameters{};
    parameters.sid = 3U;
    parameters.coded = true;
    parameters.include_tx_power = true;
    nucode::ble::BLEAdvertisingSetHandle advertising_set;
    std::uint8_t payload[255]{};
    payload[0] = 254U;
    payload[1] = 0xffU;

    static_cast<void>(BLEExtendedAdvertising.create(parameters, advertising_set));
    static_cast<void>(BLEExtendedAdvertising.setData(advertising_set, payload,
                                                     sizeof(payload)));
    static_cast<void>(BLEExtendedAdvertising.start(advertising_set, 100U, 10U));
    static_cast<void>(BLEExtendedAdvertising.running(advertising_set));
    static_cast<void>(BLEExtendedAdvertising.stop(advertising_set));
    static_cast<void>(BLEExtendedAdvertising.remove(advertising_set));
    static_cast<void>(BLEScan.startExtended(true, true));
    return 0;
}
