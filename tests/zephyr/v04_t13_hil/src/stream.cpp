/** @file @brief SAADC·PWM capture·I2S·PDM의 동시 연속 실행을 조합합니다. */
#include "stream_types.h"

t13::StreamStats t13::stream_stats[4]{};
bool t13::streams_quiesced = false;

bool t13::streamPrepare(const Case &test, std::uint32_t seed)
{
    for (auto &stats : stream_stats)
    {
        stats = {};
    }
    streams_quiesced = false;
    return adcPrepare(test) && pwmPrepare(test) && audioPrepare(test, seed) && pdmPrepare(test);
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
