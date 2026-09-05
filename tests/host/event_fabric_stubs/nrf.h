/** @file @brief Event registry의 고정 instance와 DPPI endpoint 접근을 관측합니다. */
#pragma once
#include <cstdint>
#include <map>
struct NRF_TIMER_Type
{
};
struct NRF_EGU_Type
{
};
struct NRF_GPIOTE_Type
{
};
struct NRF_PPIB_Type
{
};
struct NRF_DPPIC_Type
{
    std::uint32_t enabled{0U};
};
inline NRF_TIMER_Type mock_timers[7];
inline NRF_EGU_Type mock_egus[2];
inline NRF_GPIOTE_Type mock_gpiotes[2];
inline NRF_PPIB_Type mock_ppibs[8];
inline NRF_DPPIC_Type mock_dppis[4];
inline std::map<std::uintptr_t, std::uint32_t> mock_endpoints;
#define NRF_TIMER00 (&mock_timers[0])
#define NRF_TIMER10 (&mock_timers[1])
#define NRF_TIMER20 (&mock_timers[2])
#define NRF_TIMER21 (&mock_timers[3])
#define NRF_TIMER22 (&mock_timers[4])
#define NRF_TIMER23 (&mock_timers[5])
#define NRF_TIMER24 (&mock_timers[6])
#define NRF_EGU10 (&mock_egus[0])
#define NRF_EGU20 (&mock_egus[1])
#define NRF_GPIOTE20 (&mock_gpiotes[0])
#define NRF_GPIOTE30 (&mock_gpiotes[1])
#define NRF_DPPIC00 (&mock_dppis[0])
#define NRF_DPPIC10 (&mock_dppis[1])
#define NRF_DPPIC20 (&mock_dppis[2])
#define NRF_DPPIC30 (&mock_dppis[3])
#define NRF_PPIB00 (&mock_ppibs[0])
#define NRF_PPIB01 (&mock_ppibs[1])
#define NRF_PPIB10 (&mock_ppibs[2])
#define NRF_PPIB11 (&mock_ppibs[3])
#define NRF_PPIB20 (&mock_ppibs[4])
#define NRF_PPIB21 (&mock_ppibs[5])
#define NRF_PPIB22 (&mock_ppibs[6])
#define NRF_PPIB30 (&mock_ppibs[7])
