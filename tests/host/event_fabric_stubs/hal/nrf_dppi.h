/** @file @brief DPPI register enable과 endpoint write/clear를 관측합니다. */
#pragma once
#include <nrf.h>
using nrf_dppi_channel_group_t = unsigned;
inline unsigned nrf_dppi_channel_number_get(NRF_DPPIC_Type *reg)
{
    return reg == NRF_DPPIC00 ? 8U : reg == NRF_DPPIC10 ? 24U : reg == NRF_DPPIC20 ? 16U : 4U;
}
inline unsigned nrf_dppi_group_number_get(NRF_DPPIC_Type *)
{
    return 0U;
}
inline void nrf_dppi_channels_enable(NRF_DPPIC_Type *reg, std::uint32_t mask)
{
    reg->enabled |= mask;
}
inline void nrf_dppi_channels_disable(NRF_DPPIC_Type *reg, std::uint32_t mask)
{
    reg->enabled &= ~mask;
}
inline void nrf_dppi_channels_group_set(NRF_DPPIC_Type *, std::uint32_t, unsigned)
{
}
inline void nrf_dppi_group_disable(NRF_DPPIC_Type *, unsigned)
{
}
inline void nrf_dppi_group_clear(NRF_DPPIC_Type *, unsigned)
{
}
#define NRF_DPPI_ENDPOINT_SETUP(address, channel) (mock_endpoints[(address)] = (channel))
#define NRF_DPPI_ENDPOINT_CLEAR(address) (mock_endpoints.erase(address))
