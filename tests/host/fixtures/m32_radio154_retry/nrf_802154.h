/** @file @brief 재전송 회귀의 최소 SDK 경계입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C"
{
#endif
typedef uint8_t nrf_802154_tx_error_t;
typedef uint8_t nrf_802154_rx_error_t;
#define NRF_802154_TX_ERROR_NONE 0x00
#define NRF_802154_TX_ERROR_NO_ACK 0x05
#define NRF_802154_TX_ERROR_TIMESLOT_DENIED 0x07
typedef struct
{
    bool is_secured;
    bool dynamic_data_is_set;
} nrf_802154_transmitted_frame_props_t;
typedef struct
{
    bool use_metadata_value;
    int8_t power;
} nrf_802154_tx_power_metadata_t;
typedef struct
{
    bool use_metadata_value;
    uint8_t channel;
} nrf_802154_tx_channel_metadata_t;
#define NRF_802154_TRANSMITTED_FRAME_PROPS_DEFAULT_INIT {false, false}
typedef struct
{
    nrf_802154_transmitted_frame_props_t frame_props;
    bool cca;
    nrf_802154_tx_power_metadata_t tx_power;
    nrf_802154_tx_channel_metadata_t tx_channel;
    bool tx_timestamp_encode;
} nrf_802154_transmit_metadata_t;
typedef struct
{
    nrf_802154_transmitted_frame_props_t frame_props;
    union
    {
        struct
        {
            uint8_t *p_ack;
            uint8_t length;
            int8_t power;
            uint8_t lqi;
            uint64_t time;
        } transmitted;
    } data;
} nrf_802154_transmit_done_metadata_t;
void nrf_802154_init(void);
bool nrf_802154_reinit(void);
void nrf_802154_pan_id_set(const uint8_t *);
void nrf_802154_short_address_set(const uint8_t *);
void nrf_802154_channel_set(uint8_t);
void nrf_802154_tx_power_set(int8_t);
void nrf_802154_promiscuous_set(bool);
void nrf_802154_auto_ack_set(bool);
bool nrf_802154_receive(void);
bool nrf_802154_sleep(void);
void nrf_802154_buffer_free_raw(uint8_t *);
nrf_802154_tx_error_t nrf_802154_transmit_raw(uint8_t *, const nrf_802154_transmit_metadata_t *);
#ifdef __cplusplus
}
#endif
