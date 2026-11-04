/** @file @brief 실제 backend callback 선언입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include "nrf_802154.h"
#ifdef __cplusplus
extern "C"
{
#endif
void nrf_802154_received_raw(uint8_t *, int8_t, uint8_t);
void nrf_802154_receive_failed(nrf_802154_rx_error_t, uint32_t);
void nrf_802154_transmitted_raw(uint8_t *, const nrf_802154_transmit_done_metadata_t *);
void nrf_802154_transmit_failed(uint8_t *, nrf_802154_tx_error_t, const nrf_802154_transmit_done_metadata_t *);
#ifdef __cplusplus
}
#endif
