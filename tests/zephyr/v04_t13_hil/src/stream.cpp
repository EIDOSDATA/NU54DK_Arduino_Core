/** @file @brief T13 stream 측정 구현 전 해당 시험의 실행을 명시적으로 거부합니다. */
#include "engine.h"

bool t13::streamPrepare(const Case &test, std::uint32_t)
{
    return test.adc_channels == 0U && test.pwm_instance == 0U && test.pdm_instance == 0U &&
           !test.i2s;
}

bool t13::streamStart()
{
    return true;
}

void t13::streamService()
{
}

bool t13::streamStop()
{
    return true;
}

bool t13::streamHealthy()
{
    return true;
}

void t13::streamSnapshot(unsigned, std::uint32_t *, std::uint32_t &count)
{
    count = 0U;
}
