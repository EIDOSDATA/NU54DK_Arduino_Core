/**
 * @file CounterAlarm.ino
 * @brief GRTC absolute counter와 one-shot alarm을 사용합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_NU54DK.h>

#include <stdio.h>

using nucode::nu54dk::Error;

namespace
{
    /** @brief system work queue에서 alarm 완료 시각을 출력합니다. */
    void onAlarm(std::uint64_t scheduled_ticks, void *context)
    {
        (void)context;
        char message[64] = {};
        snprintf(message, sizeof(message), "alarm fired at tick=%llu",
                 static_cast<unsigned long long>(scheduled_ticks));
        Serial.println(message);
    }
} // namespace

void setup()
{
    Serial.begin(115200);
    delay(200);

    char message[96] = {};
    snprintf(message, sizeof(message), "GRTC frequency=%lu Hz current=%llu",
             static_cast<unsigned long>(NU54DK.hardwareCounterFrequency()),
             static_cast<unsigned long long>(NU54DK.hardwareCounterTicks()));
    Serial.println(message);

    const Error result = NU54DK.alarmAfterMicroseconds(2000000ULL, onAlarm);
    Serial.println((result == Error::none) ? "alarm scheduled" : "alarm schedule failed");
}

void loop()
{
    delay(100);
}
