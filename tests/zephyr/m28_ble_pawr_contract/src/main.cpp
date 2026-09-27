/**
 * @file main.cpp
 * @brief M28-W05 PAwR advertiser·scanner 공개 API의 target 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GAP.h>

static_assert(CONFIG_BT_PER_ADV_RSP == 1);
static_assert(CONFIG_BT_PER_ADV_SYNC_RSP == 1);
static_assert(CONFIG_BT_CTLR_SDC_PAWR_ADV_COUNT == 1);
static_assert(CONFIG_BT_CTLR_SDC_PERIODIC_ADV_RSP_TX_BUFFER_COUNT == 4);
static_assert(CONFIG_BT_CTLR_SDC_PERIODIC_ADV_RSP_TX_MAX_DATA_SIZE == 249);
static_assert(CONFIG_BT_CTLR_SDC_PERIODIC_ADV_RSP_RX_BUFFER_COUNT == 4);
static_assert(nucode::ble::Pawr::maximum_subevents == 4U);
static_assert(nucode::ble::Pawr::maximum_response_slots == 4U);
static_assert(nucode::ble::Pawr::maximum_payload_length == 249U);

int main()
{
    nucode::ble::BLEAdvertisingSetHandle advertising_set;
    nucode::ble::BLEPeriodicSyncHandle sync;
    nucode::ble::BLEPawrAdvertisingParameters parameters{};
    nucode::ble::BLEPawrResponse response{};
    const std::uint8_t subevents[] = {0U, 1U, 2U, 3U};
    std::uint8_t payload[249]{};

    static_cast<void>(BLEPawr.configureAdvertiser(advertising_set, parameters));
    static_cast<void>(BLEPawr.setSubeventData(advertising_set, 0U, payload,
                                             sizeof(payload)));
    static_cast<void>(BLEPawr.configureScanner(sync, subevents, sizeof(subevents)));
    static_cast<void>(BLEPawr.sendResponse(sync, 1U, 0U, 0U, 0U, payload,
                                          sizeof(payload)));
    static_cast<void>(BLEPawr.available());
    static_cast<void>(BLEPawr.read(response));
    static_cast<void>(BLEPawr.droppedResponses());
    return 0;
}
