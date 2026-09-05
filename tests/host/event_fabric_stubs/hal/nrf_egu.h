/** @file @brief 고정 EGU channel metadata를 반환합니다. */
#pragma once
#include <nrf.h>
inline unsigned nrf_egu_channel_count(NRF_EGU_Type *reg)
{
    return reg == NRF_EGU10 ? 16U : 6U;
}
