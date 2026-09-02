/**
 * @file WatchdogBasic.ino
 * @brief NU54DK WDT31을 시작하고 주기적으로 feed합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_NU54DK.h>

using nucode::nu54dk::Error;

namespace
{
	constexpr std::uint32_t watchdog_timeout_ms = 5000U;
	constexpr std::uint32_t feed_interval_ms = 1000U;
	std::uint32_t previous_feed_ms = 0U;
}

void setup()
{
	Serial.begin(115200);
	delay(200);
	const Error result = NU54DK.watchdogBegin(watchdog_timeout_ms);
	Serial.println((result == Error::none) ? "watchdog started" : "watchdog start failed");
}

void loop()
{
	const std::uint32_t now = millis();
	if ((now - previous_feed_ms) >= feed_interval_ms)
	{
		previous_feed_ms = now;
		Serial.println((NU54DK.watchdogFeed() == Error::none) ? "watchdog fed"
													 : "watchdog feed failed");
	}
}
