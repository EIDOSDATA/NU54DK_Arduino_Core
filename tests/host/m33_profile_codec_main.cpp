/** @file @brief 표준 profile의 알려진 bytes와 잘못된 입력을 검사합니다.
 * SPDX-License-Identifier: MIT
 */
#include <NUCODE_BLE_ProfileCodec.h>
#include <cassert>
#include <cstring>

using namespace nucode::ble::profiles;

/** @brief 정상 packet의 모든 truncation과 trailing byte를 거부해야 합니다. */
template <typename T> void boundaries(const Packet &packet, T &output)
{
    for (std::size_t n = 0U; n < packet.length; ++n)
    {
        assert(!Codec::decode(packet.data, n, output));
    }
    assert(!Codec::decode(packet.data, packet.length + 1U, output));
    assert(!Codec::decode(nullptr, packet.length, output));
    assert(Codec::decode(packet.data, packet.length, output));
}

int main()
{
    Packet packet;
    CurrentTime time;
    time.date = {2024U, 2U, 29U, 23U, 59U, 58U};
    time.weekday = 4U;
    time.fractions256 = 128U;
    time.adjust_reason = 1U;
    assert(Codec::encode(time, packet));
    const std::uint8_t expected_time[] = {0xe8U, 7U, 2U, 29U, 23U, 59U, 58U, 4U, 128U, 1U};
    assert(std::memcmp(packet.data, expected_time, sizeof(expected_time)) == 0);
    boundaries(packet, time);
    time.date.year = 2023U;
    assert(!Codec::encode(time, packet));
    assert(packet.length == 0U);
    time.date = {2000U, 2U, 29U, 0U, 0U, 0U};
    assert(Codec::encode(time, packet));
    time.date.year = 1900U;
    assert(!Codec::encode(time, packet));

    Temperature temperature;
    temperature.mantissa = -1234;
    assert(Codec::encode(temperature, packet));
    const std::uint8_t expected_temperature[] = {0U, 0x2eU, 0xfbU, 0xffU, 0xfeU};
    assert(std::memcmp(packet.data, expected_temperature, sizeof(expected_temperature)) == 0);
    boundaries(packet, temperature);
    assert(temperature.mantissa == -1234 && temperature.exponent == -2);
    temperature.has_timestamp = true;
    temperature.has_type = true;
    assert(Codec::encode(temperature, packet));
    assert(packet.length == 13U);
    boundaries(packet, temperature);
    packet.data[0] |= 0x80U;
    assert(!Codec::decode(packet.data, packet.length, temperature));

    CyclingMeasurement cycling;
    cycling.wheel_revolutions = 0x78563412U;
    cycling.wheel_event1024 = 65535U;
    cycling.crank_revolutions = 0U;
    cycling.crank_event1024 = 0U;
    assert(Codec::encode(cycling, packet));
    const std::uint8_t expected_cycle[] = {3U,    0x12U, 0x34U, 0x56U, 0x78U, 0xffU,
                                           0xffU, 0U,    0U,    0U,    0U};
    assert(std::memcmp(packet.data, expected_cycle, sizeof(expected_cycle)) == 0);
    boundaries(packet, cycling);
    cycling.has_wheel = false;
    assert(Codec::encode(cycling, packet) && packet.length == 5U);
    boundaries(packet, cycling);
    packet.data[0] |= 4U;
    assert(!Codec::decode(packet.data, packet.length, cycling));

    RunningMeasurement running;
    running.speed256 = 512U;
    running.cadence = 120U;
    running.has_stride = true;
    running.stride_cm = 100U;
    running.has_distance = true;
    running.distance_decimetres = 10000U;
    running.running = true;
    assert(Codec::encode(running, packet));
    const std::uint8_t expected_running[] = {7U, 0U, 2U, 120U, 100U, 0U, 0x10U, 0x27U, 0U, 0U};
    assert(std::memcmp(packet.data, expected_running, sizeof(expected_running)) == 0);
    boundaries(packet, running);
    assert(running.distance_decimetres == 10000U);

    GlucoseMeasurement glucose;
    glucose.mantissa = 1234;
    glucose.exponent = -1;
    glucose.time_offset_minutes = 42U;
    assert(Codec::encode(glucose, packet));
    const std::uint8_t expected_glucose[] = {6U, 0U, 0xd2U, 0xf4U, 42U, 0U};
    assert(std::memcmp(packet.data, expected_glucose, sizeof(expected_glucose)) == 0);
    boundaries(packet, glucose);
    assert(glucose.mantissa == 1234 && glucose.exponent == -1);
    glucose.mantissa = -2048;
    glucose.exponent = -8;
    assert(Codec::encode(glucose, packet));
    boundaries(packet, glucose);
    assert(glucose.mantissa == -2048 && glucose.exponent == -8);
    glucose.exponent = 8;
    assert(!Codec::encode(glucose, packet));

    ElapsedTime elapsed;
    elapsed.counter = 0x060504030201ULL;
    elapsed.clock_status = 0U;
    assert(Codec::encode(elapsed, packet));
    const std::uint8_t expected_elapsed[] = {0x22U, 1U, 2U, 3U, 4U, 5U, 6U, 7U, 0U, 0U, 0U};
    assert(std::memcmp(packet.data, expected_elapsed, sizeof(expected_elapsed)) == 0);
    boundaries(packet, elapsed);
    elapsed.counter = 0x1000000000000ULL;
    assert(!Codec::encode(elapsed, packet));

    Alert alert;
    alert.category = 1U;
    alert.count = 3U;
    std::memcpy(alert.text, "mail", 5U);
    assert(Codec::encode(alert, packet));
    assert(packet.length == 6U);
    assert(Codec::decode(packet.data, packet.length, alert));
    assert(!Codec::decode(packet.data, 1U, alert));
    const std::uint8_t invalid_utf8[] = {1U, 1U, 0xc0U, 0x80U};
    assert(!Codec::decode(invalid_utf8, sizeof(invalid_utf8), alert));
    const std::uint8_t truncated_utf8[] = {1U, 1U, 0xe3U, 0x81U};
    assert(!Codec::decode(truncated_utf8, sizeof(truncated_utf8), alert));
    const std::uint8_t surrogate_utf8[] = {1U, 1U, 0xedU, 0xa0U, 0x80U};
    assert(!Codec::decode(surrogate_utf8, sizeof(surrogate_utf8), alert));
    const std::uint8_t korean[] = {1U, 1U, 0xeaU, 0xb0U, 0x80U};
    assert(Codec::decode(korean, sizeof(korean), alert));

    AlertControl first;
    AlertControl second;
    const std::uint8_t enable_email[] = {0U, 1U};
    const std::uint8_t replay_email[] = {4U, 1U};
    const std::uint8_t invalid[] = {0U, 10U};
    assert(first.apply(enable_email, sizeof(enable_email)));
    assert(first.newEnabled(1U) && !second.newEnabled(1U));
    assert(!first.apply(invalid, sizeof(invalid)) && !first.apply(enable_email, 1U));
    assert(first.apply(replay_email, sizeof(replay_email)));
    assert(first.takeImmediateNew() == 2U && first.takeImmediateNew() == 0U);
    first.reset();
    assert(!first.newEnabled(1U));
    assert(Codec::measurementUuid(Kind::elapsed_time) == 0x2bf2U);
    assert(!Codec::valid(Kind::bond_management, korean, sizeof(korean)));
    return 0;
}
