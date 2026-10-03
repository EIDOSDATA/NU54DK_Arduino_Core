/**
 * @file NUCODE_Radio_IEEE802154.cpp
 * @brief nRF 802.15.4 단독 radio backend입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_Radio_IEEE802154.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

extern "C"
{
#include <nrf_802154_callouts.h>
}
#include <nrf_802154.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>

#include <string.h>

namespace
{
    constexpr std::uint8_t minimum_channel = 11U;
    constexpr std::uint8_t maximum_channel = 26U;
    constexpr std::uint8_t maximum_retry_count = 8U;
    constexpr std::size_t mac_header_size = 9U;
    constexpr std::size_t application_header_size = 7U;
    constexpr std::size_t hash_size = 4U;
    constexpr std::size_t fcs_size = 2U;
    constexpr std::size_t raw_frame_capacity = 128U;
    constexpr std::uint8_t magic0 = 0x4EU;
    constexpr std::uint8_t magic1 = 0x55U;

    struct BackendState
    {
        nucode::radio154::Configuration configuration{};
        nucode::radio154::Statistics statistics{};
        nucode::radio154::Role role = nucode::radio154::Role::receiver;
        nucode::radio154::Error error = nucode::radio154::Error::none;
        int driver_error = 0;
        std::uint32_t last_sequence = UINT32_MAX;
        std::uint8_t tx_frame[raw_frame_capacity]{};
        std::uint8_t tx_attempt = 0U;
        bool started = false;
        bool tx_busy = false;
        bool cancel_requested = false;
    };

    BackendState state{};
    bool driver_initialized = false;
    K_MSGQ_DEFINE(rx_queue, sizeof(nucode::radio154::Packet), 8, alignof(nucode::radio154::Packet));

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

    /** @brief 16-bit 값을 little-endian으로 기록합니다. */
    void write16(std::uint8_t *destination, std::uint16_t value) noexcept
    {
        destination[0] = static_cast<std::uint8_t>(value);
        destination[1] = static_cast<std::uint8_t>(value >> 8U);
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

    /** @brief 현재 frame을 driver에 한 번 제출합니다. */
    bool submitTransmit() noexcept
    {
        const nrf_802154_transmit_metadata_t metadata = {
            .frame_props = NRF_802154_TRANSMITTED_FRAME_PROPS_DEFAULT_INIT,
            .cca = state.configuration.clear_channel_assessment,
        };
        const nrf_802154_tx_error_t result = nrf_802154_transmit_raw(state.tx_frame, &metadata);
        if (result != NRF_802154_TX_ERROR_NONE)
        {
            state.driver_error = static_cast<int>(result);
            state.error = nucode::radio154::Error::driver_error;
            return false;
        }
        return true;
    }

    /** @brief ACK 손실 뒤 bounded 재전송을 수행합니다. */
    void retryWorkHandler(k_work *work) noexcept
    {
        ARG_UNUSED(work);
        if (!state.started || state.cancel_requested)
        {
            state.tx_busy = false;
            return;
        }
        if (!submitTransmit())
        {
            state.tx_busy = false;
            ++state.statistics.tx_failed;
        }
    }

    K_WORK_DELAYABLE_DEFINE(retry_work, retryWorkHandler);

    /** @brief 실패를 기록하거나 남은 재전송을 예약합니다. */
    void handleTransmitFailure(int driver_error) noexcept
    {
        state.driver_error = driver_error;
        if (state.started && !state.cancel_requested &&
            state.tx_attempt < state.configuration.retry_count)
        {
            ++state.tx_attempt;
            ++state.statistics.tx_retried;
            static_cast<void>(k_work_reschedule(&retry_work,
                                                K_MSEC(state.configuration.retry_delay_ms)));
            return;
        }
        state.error = nucode::radio154::Error::driver_error;
        state.tx_busy = false;
        ++state.statistics.tx_failed;
    }

    /** @brief raw frame을 검증하고 고정 queue로 복사합니다. */
    void receiveFrame(std::uint8_t *data, std::int8_t power, std::uint8_t lqi) noexcept
    {
        if (data == nullptr)
        {
            return;
        }

        const std::size_t psdu_length = data[0];
        const std::size_t minimum_length = mac_header_size + application_header_size +
                                           hash_size + fcs_size;
        if (!state.started || state.role != nucode::radio154::Role::receiver ||
            psdu_length < minimum_length)
        {
            nrf_802154_buffer_free_raw(data);
            return;
        }

        const std::uint8_t *application = &data[1U + mac_header_size];
        const std::size_t payload_length = application[6];
        const std::size_t expected_length = mac_header_size + application_header_size +
                                            payload_length + hash_size + fcs_size;
        nucode::radio154::Packet packet{};
        if (application[0] != magic0 || application[1] != magic1 ||
            payload_length > nucode::radio154::Packet::payload_capacity ||
            psdu_length != expected_length)
        {
            ++state.statistics.rx_hash_failures;
            nrf_802154_buffer_free_raw(data);
            static_cast<void>(nrf_802154_receive());
            return;
        }

        packet.sequence = read32(&application[2]);
        packet.length = payload_length;
        packet.rssi_dbm = power;
        packet.link_quality = lqi;
        packet.duplicate = packet.sequence == state.last_sequence;
        const std::uint32_t expected_hash = read32(&application[application_header_size +
                                                                  payload_length]);
        packet.hash_valid = packetHash(application, application_header_size + payload_length) ==
                            expected_hash;
        memcpy(packet.payload, &application[application_header_size], payload_length);
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
            state.error = nucode::radio154::Error::queue_full;
        }
        nrf_802154_buffer_free_raw(data);
        static_cast<void>(nrf_802154_receive());
    }
}

extern "C" void nrf_802154_received_raw(std::uint8_t *data,
                                         std::int8_t power,
                                         std::uint8_t lqi)
{
    receiveFrame(data, power, lqi);
}

extern "C" void nrf_802154_receive_failed(nrf_802154_rx_error_t error, std::uint32_t id)
{
    ARG_UNUSED(id);
    state.driver_error = static_cast<int>(error);
    state.error = nucode::radio154::Error::driver_error;
    if (state.started && state.role == nucode::radio154::Role::receiver)
    {
        static_cast<void>(nrf_802154_receive());
    }
}

extern "C" void nrf_802154_transmitted_raw(
    std::uint8_t *frame,
    const nrf_802154_transmit_done_metadata_t *metadata)
{
    ARG_UNUSED(frame);
    if (metadata != nullptr && metadata->data.transmitted.p_ack != nullptr)
    {
        nrf_802154_buffer_free_raw(metadata->data.transmitted.p_ack);
        ++state.statistics.tx_acknowledged;
        state.error = nucode::radio154::Error::none;
        state.driver_error = 0;
        state.tx_busy = false;
        return;
    }
    handleTransmitFailure(static_cast<int>(NRF_802154_TX_ERROR_NO_ACK));
}

extern "C" void nrf_802154_transmit_failed(
    std::uint8_t *frame,
    nrf_802154_tx_error_t error,
    const nrf_802154_transmit_done_metadata_t *metadata)
{
    ARG_UNUSED(frame);
    ARG_UNUSED(metadata);
    handleTransmitFailure(static_cast<int>(error));
}

namespace nucode::radio154
{
    bool Radio154::begin(Role role, const Configuration &configuration) noexcept
    {
        if (state.started || configuration.channel < minimum_channel ||
            configuration.channel > maximum_channel ||
            configuration.local_address == 0xFFFFU ||
            configuration.peer_address == 0xFFFFU ||
            configuration.retry_count > maximum_retry_count ||
            configuration.retry_delay_ms == 0U || configuration.stop_timeout_ms == 0U)
        {
            state.error = state.started ? Error::busy : Error::invalid_argument;
            return false;
        }

        k_msgq_purge(&rx_queue);
        state = {};
        state.configuration = configuration;
        state.role = role;
        state.last_sequence = UINT32_MAX;
        if (!driver_initialized)
        {
            nrf_802154_init();
            driver_initialized = true;
        }
        else if (!nrf_802154_reinit())
        {
            state.driver_error = -1;
            state.error = Error::driver_error;
            return false;
        }
        const std::uint8_t pan_id[2] = {
            static_cast<std::uint8_t>(configuration.pan_id),
            static_cast<std::uint8_t>(configuration.pan_id >> 8U),
        };
        const std::uint8_t short_address[2] = {
            static_cast<std::uint8_t>(configuration.local_address),
            static_cast<std::uint8_t>(configuration.local_address >> 8U),
        };
        nrf_802154_pan_id_set(pan_id);
        nrf_802154_short_address_set(short_address);
        nrf_802154_channel_set(configuration.channel);
        nrf_802154_tx_power_set(configuration.tx_power_dbm);
        nrf_802154_promiscuous_set(false);
        nrf_802154_auto_ack_set(true);
        state.started = true;
        if (role == Role::receiver && !nrf_802154_receive())
        {
            state.driver_error = -1;
            state.error = Error::driver_error;
            state.started = false;
            static_cast<void>(nrf_802154_reinit());
            return false;
        }
        return true;
    }

    bool Radio154::send(std::uint32_t sequence,
                        const std::uint8_t *payload,
                        std::size_t length) noexcept
    {
        if (!state.started)
        {
            state.error = Error::not_started;
            return false;
        }
        if (state.role != Role::transmitter || payload == nullptr || length == 0U ||
            length > Packet::payload_capacity)
        {
            state.error = Error::invalid_argument;
            return false;
        }
        if (state.tx_busy)
        {
            state.error = Error::busy;
            return false;
        }

        const std::size_t application_size = application_header_size + length + hash_size;
        const std::size_t psdu_size = mac_header_size + application_size + fcs_size;
        std::uint8_t *mac = &state.tx_frame[1];
        state.tx_frame[0] = static_cast<std::uint8_t>(psdu_size);
        mac[0] = 0x61U;
        mac[1] = 0x98U;
        mac[2] = static_cast<std::uint8_t>(sequence);
        write16(&mac[3], state.configuration.pan_id);
        write16(&mac[5], state.configuration.peer_address);
        write16(&mac[7], state.configuration.local_address);

        std::uint8_t *application = &mac[mac_header_size];
        application[0] = magic0;
        application[1] = magic1;
        write32(&application[2], sequence);
        application[6] = static_cast<std::uint8_t>(length);
        memcpy(&application[application_header_size], payload, length);
        write32(&application[application_header_size + length],
                packetHash(application, application_header_size + length));

        state.tx_attempt = 0U;
        state.cancel_requested = false;
        state.tx_busy = true;
        ++state.statistics.tx_requested;
        if (!submitTransmit())
        {
            state.tx_busy = false;
            ++state.statistics.tx_failed;
            return false;
        }
        return true;
    }

    bool Radio154::available() const noexcept
    {
        return k_msgq_num_used_get(&rx_queue) != 0U;
    }

    bool Radio154::read(Packet &packet) noexcept
    {
        return k_msgq_get(&rx_queue, &packet, K_NO_WAIT) == 0;
    }

    bool Radio154::cancel() noexcept
    {
        if (!state.started)
        {
            state.error = Error::not_started;
            return false;
        }
        state.cancel_requested = true;
        static_cast<void>(k_work_cancel_delayable(&retry_work));
        state.tx_busy = false;
        k_msgq_purge(&rx_queue);
        if (state.role == Role::receiver && !nrf_802154_receive())
        {
            state.driver_error = -1;
            state.error = Error::driver_error;
            return false;
        }
        state.error = Error::none;
        return true;
    }

    bool Radio154::stop() noexcept
    {
        if (!state.started)
        {
            state.error = Error::not_started;
            return false;
        }
        state.cancel_requested = true;
        static_cast<void>(k_work_cancel_delayable(&retry_work));
        const std::int64_t deadline = k_uptime_get() + state.configuration.stop_timeout_ms;
        while (!nrf_802154_sleep())
        {
            if (k_uptime_get() >= deadline)
            {
                state.error = Error::stop_timeout;
                return false;
            }
            k_sleep(K_MSEC(1));
        }
        if (!nrf_802154_reinit())
        {
            state.error = Error::stop_timeout;
            return false;
        }
        state.started = false;
        state.tx_busy = false;
        k_msgq_purge(&rx_queue);
        ++state.statistics.stops;
        state.error = Error::none;
        return true;
    }

    bool Radio154::busy() const noexcept
    {
        return state.tx_busy;
    }

    Statistics Radio154::statistics() const noexcept
    {
        const unsigned int key = irq_lock();
        const Statistics snapshot = state.statistics;
        irq_unlock(key);
        return snapshot;
    }

    Error Radio154::lastError() const noexcept
    {
        return state.error;
    }

    int Radio154::lastDriverError() const noexcept
    {
        return state.driver_error;
    }
}

nucode::radio154::Radio154 NUCODERadio154;

#endif
