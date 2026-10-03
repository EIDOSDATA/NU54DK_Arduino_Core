/**
 * @file main.cpp
 * @brief 두 NU54DK에서 IEEE 802.15.4 단독 송수신과 정리를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_Radio_IEEE802154.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

#ifndef M32_RADIO154_CORE_REVISION
#error "M32_RADIO154_CORE_REVISION is required"
#endif

namespace
{
    constexpr char protocol[] = "M32R154|1";
    constexpr char start_prefix[] = "M32R154|1|START|nonce=";
    constexpr char finish_prefix[] = "M32R154|1|FINISH|nonce=";
    constexpr char stop_prefix[] = "M32R154|1|STOP|nonce=";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::uint32_t iteration_target = 20U;
    constexpr std::uint32_t packets_per_iteration = 100U;
    constexpr std::uint32_t packet_target =
        iteration_target * packets_per_iteration;
    constexpr std::int64_t session_timeout_ms = 240000;

    char command[160] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool started = false;
    bool finished = false;
    bool stop_requested = false;
    bool radio_started = false;
    bool invalid_channel_rejected = false;
    bool invalid_length_rejected = false;
    std::int64_t deadline_ms = 0;

#if defined(NUCODE_M32_RADIO154_TRANSMITTER)
    std::uint32_t submitted_packets = 0U;
    std::uint32_t completed_packets = 0U;
    std::int64_t transmit_started_ms = 0;
    std::uint32_t maximum_latency_ms = 0U;
#else
    bool observed_sequences[packet_target] = {};
    std::uint32_t received_packets = 0U;
    std::uint32_t unique_packets = 0U;
    std::uint32_t corrupt_packets = 0U;
#endif

    /** @brief 현재 image의 고정 역할을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M32_RADIO154_TRANSMITTER)
        return "transmitter";
#else
        return "receiver";
#endif
    }

    /** @brief protocol 결과에 nonce와 exact Core revision을 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M32_RADIO154_CORE_REVISION);
    }

    /** @brief 첫 오류만 bounded protocol로 출력합니다. */
    void fail(const char *stage, int code = 0)
    {
        if (finished)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.println();
        finished = true;
    }

    /** @brief START record의 nonce와 exact revision을 검증합니다. */
    bool acceptStart()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        if (::strncmp(command, start_prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *cursor = command + prefix_length;
        for (std::size_t index = 0U; index < nonce_length; ++index)
        {
            const char value = cursor[index];
            if (!((value >= '0' && value <= '9') ||
                  (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        constexpr char core_prefix[] = "|core=";
        if (::strncmp(cursor + nonce_length, core_prefix,
                      sizeof(core_prefix) - 1U) != 0 ||
            ::strcmp(cursor + nonce_length + sizeof(core_prefix) - 1U,
                     M32_RADIO154_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

    /** @brief sequence에서 재현 가능한 12-byte application payload를 만듭니다. */
    void encodePayload(std::uint32_t sequence, std::uint8_t *payload)
    {
        const std::uint32_t inverse = ~sequence;
        for (std::size_t index = 0U; index < 4U; ++index)
        {
            payload[index] = static_cast<std::uint8_t>(sequence >> (index * 8U));
            payload[index + 4U] =
                static_cast<std::uint8_t>(inverse >> (index * 8U));
        }
        payload[8] = 'N';
        payload[9] = 'U';
        payload[10] = '5';
        payload[11] = '4';
    }

    /** @brief 채널·길이 negative 뒤 고정 단독 radio 역할을 시작합니다. */
    bool beginRadio()
    {
        nucode::radio154::Configuration invalid{};
        invalid.channel = 10U;
        invalid_channel_rejected = !NUCODERadio154.begin(
#if defined(NUCODE_M32_RADIO154_TRANSMITTER)
            nucode::radio154::Role::transmitter,
#else
            nucode::radio154::Role::receiver,
#endif
            invalid);
        if (!invalid_channel_rejected)
        {
            static_cast<void>(NUCODERadio154.stop());
            return false;
        }

        nucode::radio154::Configuration configuration{};
        configuration.pan_id = 0x4e55U;
        configuration.channel = 20U;
#if defined(NUCODE_M32_RADIO154_TRANSMITTER)
        configuration.local_address = 0x0001U;
        configuration.peer_address = 0x0002U;
        const auto role = nucode::radio154::Role::transmitter;
#else
        configuration.local_address = 0x0002U;
        configuration.peer_address = 0x0001U;
        const auto role = nucode::radio154::Role::receiver;
#endif
        if (!NUCODERadio154.begin(role, configuration))
        {
            return false;
        }
        radio_started = true;
        std::uint8_t oversized[nucode::radio154::Packet::payload_capacity + 1U] = {};
        invalid_length_rejected = !NUCODERadio154.send(
            0U, oversized, sizeof(oversized));
        return invalid_length_rejected;
    }

    /** @brief 역할별 최종 통계와 음수 분모를 출력합니다. */
    void printResult()
    {
        const nucode::radio154::Statistics statistics =
            NUCODERadio154.statistics();
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
#if defined(NUCODE_M32_RADIO154_TRANSMITTER)
        Serial.print("|requested=");
        Serial.print(statistics.tx_requested);
        Serial.print("|acknowledged=");
        Serial.print(statistics.tx_acknowledged);
        Serial.print("|failed=");
        Serial.print(statistics.tx_failed);
        Serial.print("|retried=");
        Serial.print(statistics.tx_retried);
        Serial.print("|max_latency_ms=");
        Serial.print(maximum_latency_ms);
#else
        Serial.print("|received=");
        Serial.print(received_packets);
        Serial.print("|unique=");
        Serial.print(unique_packets);
        Serial.print("|duplicates=");
        Serial.print(statistics.rx_duplicates);
        Serial.print("|corrupt=");
        Serial.print(corrupt_packets + statistics.rx_hash_failures);
        Serial.print("|dropped=");
        Serial.print(statistics.rx_dropped);
#endif
        Serial.print("|iterations=");
        Serial.print(iteration_target);
        Serial.print("|invalid_channel_rejected=");
        Serial.print(invalid_channel_rejected ? 1 : 0);
        Serial.print("|invalid_length_rejected=");
        Serial.print(invalid_length_rejected ? 1 : 0);
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        finished = true;
    }

    /** @brief START 뒤 역할을 시작하고 BEGIN record를 출력합니다. */
    void startProtocol()
    {
        if (!acceptStart() || !beginRadio())
        {
            fail("start", NUCODERadio154.lastDriverError());
            return;
        }
        started = true;
        deadline_ms = k_uptime_get() + session_timeout_ms;
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
    }

    /** @brief CR/LF serial 명령을 처리합니다. */
    void processCommand()
    {
        if (::strcmp(command, "M32R154|1|PROBE") == 0)
        {
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|core=");
            Serial.println(M32_RADIO154_CORE_REVISION);
            return;
        }
        if (!started && ::strncmp(command, start_prefix,
                                  ::strlen(start_prefix)) == 0)
        {
            startProtocol();
            return;
        }
#if !defined(NUCODE_M32_RADIO154_TRANSMITTER)
        if (started && !finished &&
            ::strncmp(command, finish_prefix, ::strlen(finish_prefix)) == 0 &&
            ::strcmp(command + ::strlen(finish_prefix), nonce) == 0)
        {
            printResult();
            return;
        }
#endif
        if (started && ::strncmp(command, stop_prefix,
                                 ::strlen(stop_prefix)) == 0 &&
            ::strcmp(command + ::strlen(stop_prefix), nonce) == 0)
        {
            stop_requested = true;
        }
    }

    /** @brief bounded serial command buffer를 갱신합니다. */
    void pollCommand()
    {
        while (Serial.available() > 0)
        {
            const int input = Serial.read();
            if (input == '\r')
            {
                continue;
            }
            if (input != '\n')
            {
                if (command_length + 1U >= sizeof(command))
                {
                    command_length = 0U;
                    fail("command_overflow");
                    return;
                }
                command[command_length++] = static_cast<char>(input);
                command[command_length] = '\0';
                continue;
            }
            processCommand();
            command_length = 0U;
            command[0] = '\0';
        }
    }

#if defined(NUCODE_M32_RADIO154_TRANSMITTER)
    /** @brief ACK 완료를 기다리며 정확히 2,000개 frame을 순차 제출합니다. */
    void driveTransmitter()
    {
        if (NUCODERadio154.busy())
        {
            return;
        }
        if (submitted_packets != completed_packets)
        {
            const std::uint32_t latency = static_cast<std::uint32_t>(
                k_uptime_get() - transmit_started_ms);
            if (latency > maximum_latency_ms)
            {
                maximum_latency_ms = latency;
            }
            ++completed_packets;
        }
        if (submitted_packets == packet_target)
        {
            printResult();
            return;
        }
        std::uint8_t payload[12] = {};
        encodePayload(submitted_packets, payload);
        transmit_started_ms = k_uptime_get();
        if (!NUCODERadio154.send(submitted_packets, payload, sizeof(payload)))
        {
            fail("send", NUCODERadio154.lastDriverError());
            return;
        }
        ++submitted_packets;
    }
#else
    /** @brief 수신 sequence/hash/payload를 bounded bitmap과 대조합니다. */
    void driveReceiver()
    {
        nucode::radio154::Packet packet{};
        while (NUCODERadio154.read(packet))
        {
            ++received_packets;
            std::uint8_t expected[12] = {};
            if (packet.sequence < packet_target)
            {
                encodePayload(packet.sequence, expected);
            }
            if (!packet.hash_valid || packet.sequence >= packet_target ||
                packet.length != sizeof(expected) ||
                ::memcmp(packet.payload, expected, sizeof(expected)) != 0)
            {
                ++corrupt_packets;
                continue;
            }
            if (!observed_sequences[packet.sequence])
            {
                observed_sequences[packet.sequence] = true;
                ++unique_packets;
            }
        }
    }
#endif

    /** @brief cancel·stop으로 RADIO와 buffer를 유한 시간 안에 반환합니다. */
    void stopProtocol()
    {
        bool cleanup = true;
        if (radio_started)
        {
            cleanup = NUCODERadio154.cancel() && cleanup;
            cleanup = NUCODERadio154.stop() && cleanup;
            radio_started = false;
        }
        Serial.print(protocol);
        Serial.print("|STOPPED|role=");
        Serial.print(roleName());
        Serial.print("|cleanup=");
        Serial.print(cleanup ? "pass" : "fail");
        printSuffix();
        Serial.println();
        stop_requested = false;
    }
}

void setup()
{
    Serial.begin(115200);
    const std::int64_t serial_deadline = k_uptime_get() + 5000;
    while (!Serial && k_uptime_get() < serial_deadline)
    {
        delay(10);
    }
}

void loop()
{
    pollCommand();
    if (started && !finished)
    {
#if defined(NUCODE_M32_RADIO154_TRANSMITTER)
        driveTransmitter();
#else
        driveReceiver();
#endif
        if (k_uptime_get() >= deadline_ms)
        {
            fail("session_timeout");
        }
    }
    if (stop_requested)
    {
        stopProtocol();
    }
    delay(1);
}
