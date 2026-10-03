/**
 * @file NUCODE_Radio_ESB.cpp
 * @brief Nordic ESB 단독 PTX/PRX backend입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_Radio_ESB.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <esb.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>

#include <errno.h>
#include <string.h>

namespace
{
    constexpr std::uint8_t maximum_channel = 100U;
    constexpr std::uint8_t maximum_pipe = 7U;
    constexpr std::uint8_t maximum_retry_count = 15U;
    constexpr std::size_t application_header_size = 7U;
    constexpr std::size_t hash_size = 4U;
    constexpr std::uint8_t magic0 = 0x45U;
    constexpr std::uint8_t magic1 = 0x53U;

    struct BackendState
    {
        nucode::esb::Configuration configuration{};
        nucode::esb::Statistics statistics{};
        nucode::esb::Role role = nucode::esb::Role::primary_receiver;
        nucode::esb::Error error = nucode::esb::Error::none;
        int driver_error = 0;
        std::uint32_t last_sequence = UINT32_MAX;
        bool started = false;
        bool tx_busy = false;
    };

    BackendState state{};
    K_MSGQ_DEFINE(rx_queue, sizeof(nucode::esb::Packet), 8, alignof(nucode::esb::Packet));

    /** @brief byte 범위의 FNV-1a hash를 계산합니다. */
    std::uint32_t packetHash(const std::uint8_t *data, std::size_t length) noexcept
    {
        std::uint32_t hash = 2166136261U;
        for (std::size_t index = 0U; index < length; ++index)
        {
            hash ^= data[index];
            hash *= 16777619U;
        }
        return hash;
    }

    /** @brief 32-bit 값을 little-endian으로 기록합니다. */
    void write32(std::uint8_t *destination, std::uint32_t value) noexcept
    {
        destination[0] = static_cast<std::uint8_t>(value);
        destination[1] = static_cast<std::uint8_t>(value >> 8U);
        destination[2] = static_cast<std::uint8_t>(value >> 16U);
        destination[3] = static_cast<std::uint8_t>(value >> 24U);
    }

    /** @brief little-endian 32-bit 값을 읽습니다. */
    std::uint32_t read32(const std::uint8_t *source) noexcept
    {
        return static_cast<std::uint32_t>(source[0]) |
               (static_cast<std::uint32_t>(source[1]) << 8U) |
               (static_cast<std::uint32_t>(source[2]) << 16U) |
               (static_cast<std::uint32_t>(source[3]) << 24U);
    }

    /** @brief MPSL timeslot 기반 ESB가 유한 시간 안에 idle이 될 때까지 기다립니다. */
    bool waitForIdle(std::uint16_t timeout_ms) noexcept
    {
        const std::int64_t deadline = k_uptime_get() + timeout_ms;
        while (!esb_is_idle())
        {
            if (k_uptime_get() >= deadline)
            {
                return false;
            }
            k_sleep(K_MSEC(1));
        }
        return true;
    }

    /** @brief 수신 FIFO를 모두 복사하고 format/hash를 검증합니다. */
    void drainReceiveQueue() noexcept
    {
        esb_payload raw{};
        int result = 0;
        while ((result = esb_read_rx_payload(&raw)) == 0)
        {
            nucode::esb::Packet packet{};
            if (raw.length < application_header_size + hash_size ||
                raw.data[0] != magic0 || raw.data[1] != magic1)
            {
                ++state.statistics.rx_hash_failures;
                continue;
            }
            const std::size_t length = raw.data[6];
            if (length > nucode::esb::Packet::payload_capacity ||
                raw.length != application_header_size + length + hash_size)
            {
                ++state.statistics.rx_hash_failures;
                continue;
            }
            packet.sequence = read32(&raw.data[2]);
            packet.length = length;
            packet.pipe = raw.pipe;
            packet.duplicate = packet.sequence == state.last_sequence;
            packet.hash_valid = read32(&raw.data[application_header_size + length]) ==
                                packetHash(raw.data, application_header_size + length);
            memcpy(packet.payload, &raw.data[application_header_size], length);
            state.last_sequence = packet.sequence;
            ++state.statistics.rx_received;
            if (packet.duplicate)
            {
                ++state.statistics.rx_duplicates;
            }
            if (!packet.hash_valid)
            {
                ++state.statistics.rx_hash_failures;
            }
            if (k_msgq_put(&rx_queue, &packet, K_NO_WAIT) != 0)
            {
                ++state.statistics.rx_dropped;
                state.error = nucode::esb::Error::queue_full;
            }
        }
        if (result != -ENODATA)
        {
            state.driver_error = result;
            state.error = nucode::esb::Error::driver_error;
        }
    }

    /** @brief ESB IRQ event를 고정 통계와 복사 queue로 변환합니다. */
    void eventHandler(const esb_evt *event) noexcept
    {
        if (event == nullptr || !state.started)
        {
            return;
        }
        switch (event->evt_id)
        {
            case ESB_EVENT_TX_SUCCESS:
                state.tx_busy = false;
                ++state.statistics.tx_acknowledged;
                state.statistics.tx_attempts += event->tx_attempts;
                state.error = nucode::esb::Error::none;
                break;
            case ESB_EVENT_TX_FAILED:
                state.tx_busy = false;
                ++state.statistics.tx_failed;
                state.statistics.tx_attempts += event->tx_attempts;
                state.error = nucode::esb::Error::driver_error;
                state.driver_error = -EIO;
                break;
            case ESB_EVENT_RX_RECEIVED:
                drainReceiveQueue();
                break;
#if defined(CONFIG_ESB_MPSL_TIMESLOT)
            case ESB_EVENT_TIMESLOT_FAILED:
                ++state.statistics.timeslot_failures;
                state.error = nucode::esb::Error::driver_error;
                state.driver_error = -EBUSY;
                break;
#endif
            default:
                break;
        }
    }

    /** @brief 공개 전송률을 ESB driver 값으로 변환합니다. */
    bool driverBitrate(nucode::esb::Bitrate bitrate, esb_bitrate &result) noexcept
    {
        switch (bitrate)
        {
            case nucode::esb::Bitrate::mbps1:
                result = ESB_BITRATE_1MBPS;
                return true;
            case nucode::esb::Bitrate::mbps2:
                result = ESB_BITRATE_2MBPS;
                return true;
            default:
                return false;
        }
    }
}

namespace nucode::esb
{
    bool EsbRadio::begin(Role role, const Configuration &configuration) noexcept
    {
        esb_bitrate bitrate = ESB_BITRATE_2MBPS;
        if (state.started || configuration.channel > maximum_channel ||
            configuration.pipe > maximum_pipe ||
            configuration.retransmit_count > maximum_retry_count ||
            configuration.retransmit_delay_us < 250U ||
            configuration.stop_timeout_ms == 0U ||
            !driverBitrate(configuration.bitrate, bitrate))
        {
            state.error = state.started ? Error::busy : Error::invalid_argument;
            return false;
        }

        k_msgq_purge(&rx_queue);
        state = {};
        state.configuration = configuration;
        state.role = role;
        state.last_sequence = UINT32_MAX;

        esb_config config = ESB_DEFAULT_CONFIG;
        config.protocol = ESB_PROTOCOL_ESB_DPL;
        config.mode = role == Role::primary_transmitter ? ESB_MODE_PTX : ESB_MODE_PRX;
        config.bitrate = bitrate;
        config.crc = ESB_CRC_16BIT;
        config.retransmit_delay = configuration.retransmit_delay_us;
        config.retransmit_count = configuration.retransmit_count;
        config.payload_length = 32U;
        config.selective_auto_ack = true;
        config.event_handler = eventHandler;

        int result = esb_init(&config);
        static const std::uint8_t base_address0[4] = {0xE7U, 0xE7U, 0xE7U, 0xE7U};
        static const std::uint8_t base_address1[4] = {0xC2U, 0xC2U, 0xC2U, 0xC2U};
        static const std::uint8_t prefixes[8] = {
            0xE7U, 0xC2U, 0xC3U, 0xC4U, 0xC5U, 0xC6U, 0xC7U, 0xC8U,
        };
        if (result == 0)
        {
            result = esb_set_base_address_0(base_address0);
        }
        if (result == 0)
        {
            result = esb_set_base_address_1(base_address1);
        }
        if (result == 0)
        {
            result = esb_set_prefixes(prefixes, sizeof(prefixes));
        }
        if (result == 0)
        {
            result = esb_set_rf_channel(configuration.channel);
        }
        if (result == 0 && role == Role::primary_receiver)
        {
            result = esb_start_rx();
        }
        if (result != 0)
        {
            state.driver_error = result;
            state.error = Error::driver_error;
            esb_disable();
            return false;
        }
        state.started = true;
        return true;
    }

    bool EsbRadio::send(std::uint32_t sequence,
                        const std::uint8_t *payload,
                        std::size_t length) noexcept
    {
        if (!state.started)
        {
            state.error = Error::not_started;
            return false;
        }
        if (payload == nullptr || length == 0U || length > Packet::payload_capacity)
        {
            state.error = Error::invalid_argument;
            return false;
        }
        if (state.role == Role::primary_transmitter && state.tx_busy)
        {
            state.error = Error::busy;
            return false;
        }

        esb_payload frame{};
        frame.pipe = state.configuration.pipe;
        frame.noack = false;
        frame.length = static_cast<std::uint8_t>(application_header_size + length + hash_size);
        frame.data[0] = magic0;
        frame.data[1] = magic1;
        write32(&frame.data[2], sequence);
        frame.data[6] = static_cast<std::uint8_t>(length);
        memcpy(&frame.data[application_header_size], payload, length);
        write32(&frame.data[application_header_size + length],
                packetHash(frame.data, application_header_size + length));

        const int result = esb_write_payload(&frame);
        if (result != 0)
        {
            state.driver_error = result;
            state.error = result == -ENOSPC ? Error::queue_full : Error::driver_error;
            return false;
        }
        ++state.statistics.tx_requested;
        if (state.role == Role::primary_transmitter)
        {
            state.tx_busy = true;
        }
        return true;
    }

    bool EsbRadio::available() const noexcept
    {
        return k_msgq_num_used_get(&rx_queue) != 0U;
    }

    bool EsbRadio::read(Packet &packet) noexcept
    {
        return k_msgq_get(&rx_queue, &packet, K_NO_WAIT) == 0;
    }

    bool EsbRadio::cancel() noexcept
    {
        if (!state.started)
        {
            state.error = Error::not_started;
            return false;
        }
        int result = esb_suspend();
        if (result == -EALREADY)
        {
            result = 0;
        }
        if (result == 0 && !waitForIdle(state.configuration.stop_timeout_ms))
        {
            state.driver_error = -ETIMEDOUT;
            state.error = Error::stop_timeout;
            return false;
        }
        if (result == 0)
        {
            result = esb_flush_tx();
        }
        if (result == 0)
        {
            result = esb_flush_rx();
        }
        if (result == 0 && state.role == Role::primary_receiver)
        {
            result = esb_start_rx();
        }
        state.tx_busy = false;
        k_msgq_purge(&rx_queue);
        if (result != 0)
        {
            state.driver_error = result;
            state.error = Error::driver_error;
            return false;
        }
        state.error = Error::none;
        return true;
    }

    bool EsbRadio::stop() noexcept
    {
        if (!state.started)
        {
            state.error = Error::not_started;
            return false;
        }
        int result = esb_suspend();
        if (result == -EALREADY)
        {
            result = 0;
        }
        if (result == 0 && !waitForIdle(state.configuration.stop_timeout_ms))
        {
            state.driver_error = -ETIMEDOUT;
            state.error = Error::stop_timeout;
            return false;
        }
        if (result != 0)
        {
            state.driver_error = result;
            state.error = Error::driver_error;
            return false;
        }
        esb_disable();
        state.started = false;
        state.tx_busy = false;
        k_msgq_purge(&rx_queue);
        ++state.statistics.stops;
        state.error = Error::none;
        return true;
    }

    bool EsbRadio::busy() const noexcept
    {
        return state.tx_busy;
    }

    Statistics EsbRadio::statistics() const noexcept
    {
        const unsigned int key = irq_lock();
        const Statistics snapshot = state.statistics;
        irq_unlock(key);
        return snapshot;
    }

    Error EsbRadio::lastError() const noexcept
    {
        return state.error;
    }

    int EsbRadio::lastDriverError() const noexcept
    {
        return state.driver_error;
    }
}

nucode::esb::EsbRadio NUCODEEsb;

#endif
