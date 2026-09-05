/** @file @brief PPIB instance별 metadata를 반환합니다. */
#pragma once
#include <nrf.h>
inline unsigned nrf_ppib_channel_number_get(NRF_PPIB_Type *reg)
{
    return reg == NRF_PPIB11 || reg == NRF_PPIB21   ? 16U
           : reg == NRF_PPIB22 || reg == NRF_PPIB30 ? 4U
                                                    : 8U;
}
