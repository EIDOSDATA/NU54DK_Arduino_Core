/** @file @brief SAADC·PWM capture·I2S·PDM의 동시 연속 실행을 조합합니다. */
#include "stream_types.h"

t13::StreamStats t13::stream_stats[4]{};
bool t13::streams_quiesced = false;
t13::StreamFault t13::stream_fault{};

bool t13::streamPrepare(const Case &test, std::uint32_t seed)
{
    for (auto &stats : stream_stats)
    {
        stats = {};
    }
    streams_quiesced = false;
    stream_fault = {};
    return adcPrepare(test) && pwmPrepare(test) && audioPrepare(test, seed) && pdmPrepare(test);
}

bool t13::streamArmFault(const Case &test, std::uint32_t mode)
{
    if (test.serial_count != 0U || test.adc_channels != 0U || test.pwm_instance != 0U ||
        (mode == 1U && (!test.i2s || test.pdm_instance != 0U)) ||
        (mode == 2U && (test.i2s || test.pdm_instance == 0U || CONFIG_NUCODE_V04_HIL_ROLE != 1)))
    {
        return false;
    }
    return stream_fault.arm(mode, mode == 1U ? 20U : test.pdm_instance, CONFIG_NUCODE_V04_HIL_ROLE,
                            CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC);
}

void t13::streamFaultSnapshot(std::uint32_t *out, std::uint32_t &count)
{
    for (unsigned index = 0U; index < 20U; ++index)
    {
        out[index] = stream_fault.words[index];
    }
    count = 20U;
}

bool t13::streamStart()
{
    return adcStart() && pwmStart() && audioStart() && pdmStart();
}

void t13::streamService()
{
    captureService();
    adcService();
    captureService();
    audioService();
    captureService();
    pdmService();
    captureService();
    pwmService();
}

void t13::streamQuiesce()
{
    streams_quiesced = true;
}

bool t13::streamStop()
{
    streams_quiesced = true;
    const bool adc = adcStop();
    const bool audio = audioStop();
    const bool pdm = pdmStop();
    const bool pwm = pwmStop();
    return adc && audio && pdm && pwm;
}

bool t13::streamHealthy()
{
    return adcHealthy() && audioHealthy() && pdmHealthy() && pwmHealthy();
}

void t13::streamSnapshot(unsigned stream, std::uint32_t *out, std::uint32_t &count)
{
    if (stream == 0U)
    {
        adcSnapshot(out);
    }
    else if (stream == 1U)
    {
        pwmSnapshot(out);
    }
    else if (stream == 2U)
    {
        audioSnapshot(out);
    }
    else if (stream == 3U)
    {
        pdmSnapshot(out);
    }
    count = stream < 4U ? 20U : 0U;
}

void t13::streamTiming(unsigned stream, unsigned metric, std::uint32_t *out, std::uint32_t &count)
{
    if (stream >= 4U || metric >= 2U)
    {
        count = 0U;
        return;
    }
    (metric == 0U ? stream_stats[stream].queue_time : stream_stats[stream].completion_time)
        .snapshot(out);
    count = 20U;
}
