/** @file @brief 실제 IEEE 802.15.4 backend의 재전송·취소 경계를 실행합니다.
 * SPDX-License-Identifier: MIT
 */
#include "NUCODE_Radio_IEEE802154.h"
#include "nrf_802154_callouts.h"
#include "zephyr/kernel.h"
#include <cstdlib>
#include <initializer_list>
#include <iostream>
#include <string>
#include <vector>

namespace
{
    std::vector<nrf_802154_tx_error_t> submit_results{};
    std::vector<std::vector<std::uint8_t>> frames{};
    std::size_t submit_index = 0U;
    std::uint8_t *submitted_frame = nullptr;
    unsigned int freed_buffers = 0U;

    /** @brief 최적화 설정과 관계없이 조건 위반을 실패로 반환합니다. */
    void require(bool condition, const char *message)
    {
        if (!condition)
        {
            std::cerr << message << '\n';
            std::exit(1);
        }
    }

    /** @brief SDK 반환 순서를 설정하고 실제 공개 API를 시작합니다. */
    void beginCase(std::initializer_list<nrf_802154_tx_error_t> results)
    {
        submit_results = results;
        nucode::radio154::Configuration configuration{};
        configuration.retry_count = 3U;
        configuration.retry_delay_ms = 4U;
        require(NUCODERadio154.begin(nucode::radio154::Role::transmitter, configuration), "begin failed");
    }

    /** @brief 실제 공개 send로 최초 frame을 생성합니다. */
    bool sendFrame()
    {
        const std::uint8_t payload[] = {0x12U, 0x34U, 0x56U};
        return NUCODERadio154.send(42U, payload, sizeof(payload));
    }

    /** @brief SDK의 비동기 실패 callback을 실제 backend로 전달합니다. */
    void rejectInitialTransmission()
    {
        require(submitted_frame != nullptr, "initial frame missing");
        nrf_802154_transmit_failed(submitted_frame, NRF_802154_TX_ERROR_NO_ACK, nullptr);
    }

    /** @brief 예약을 먼저 해제한 뒤 실제 등록 work handler를 한 번 호출합니다. */
    void runPendingWork()
    {
        auto *work = radio154_fixture::pending;
        require(work != nullptr, "retry work missing");
        radio154_fixture::pending = nullptr;
        work->work.handler(&work->work);
    }

    /** @brief 실제 성공 callback과 ACK buffer 반환 경로를 실행합니다. */
    void acknowledgeTransmission()
    {
        std::uint8_t ack[] = {2U, 0U, 0U};
        nrf_802154_transmit_done_metadata_t metadata{};
        metadata.data.transmitted.p_ack = ack;
        nrf_802154_transmitted_raw(submitted_frame, &metadata);
    }

    /** @brief 실제 공개 통계와 예약 횟수를 함께 검사합니다. */
    void expectStatistics(std::uint32_t retried, std::uint32_t failed,
                          std::uint32_t acknowledged, std::size_t submits)
    {
        const auto statistics = NUCODERadio154.statistics();
        require(statistics.tx_requested == 1U, "tx_requested changed");
        require(statistics.tx_retried == retried, "retry budget mismatch");
        require(statistics.tx_failed == failed, "failure count mismatch");
        require(statistics.tx_acknowledged == acknowledged, "acknowledgment count mismatch");
        require(submit_index == submits && frames.size() == submits, "actual submit count mismatch");
        require(radio154_fixture::delays.size() == retried, "scheduled retry count mismatch");
        for (const auto delay : radio154_fixture::delays)
        {
            require(delay == 4, "configured retry delay changed");
        }
    }

    /** @brief 동기 retry 제출 실패 뒤 남은 한도로 성공해야 합니다. */
    void successAfterSynchronousFailure()
    {
        beginCase({NRF_802154_TX_ERROR_NONE, NRF_802154_TX_ERROR_TIMESLOT_DENIED, NRF_802154_TX_ERROR_NONE});
        require(sendFrame(), "initial accepted send failed");
        rejectInitialTransmission();
        expectStatistics(1U, 0U, 0U, 1U);
        runPendingWork();
        require(NUCODERadio154.busy(), "retry failed before budget exhausted");
        require(radio154_fixture::pending != nullptr, "remaining retry budget abandoned");
        expectStatistics(2U, 0U, 0U, 2U);
        runPendingWork();
        require(NUCODERadio154.busy(), "accepted retry completed without callback");
        require(radio154_fixture::pending == nullptr, "accepted retry scheduled another submit");
        acknowledgeTransmission();
        expectStatistics(2U, 0U, 1U, 3U);
        require(!NUCODERadio154.busy(), "success left transmitter busy");
        require(NUCODERadio154.lastError() == nucode::radio154::Error::none &&
                    NUCODERadio154.lastDriverError() == 0, "success did not clear error");
        require(freed_buffers == 1U, "ACK buffer was not returned exactly once");
    }

    /** @brief 모든 retry 제출이 실패해도 기존 한도까지만 실행해야 합니다. */
    void exactBudgetExhaustion()
    {
        beginCase({NRF_802154_TX_ERROR_NONE, NRF_802154_TX_ERROR_TIMESLOT_DENIED,
                   NRF_802154_TX_ERROR_TIMESLOT_DENIED, NRF_802154_TX_ERROR_TIMESLOT_DENIED});
        require(sendFrame(), "initial accepted send failed");
        rejectInitialTransmission();
        for (unsigned int retry = 0U; retry < 3U; ++retry)
        {
            runPendingWork();
        }
        expectStatistics(3U, 1U, 0U, 4U);
        require(radio154_fixture::pending == nullptr, "retry remained after exact budget");
        require(!NUCODERadio154.busy(), "exhaustion left transmitter busy");
        require(NUCODERadio154.lastError() == nucode::radio154::Error::driver_error &&
                    NUCODERadio154.lastDriverError() == NRF_802154_TX_ERROR_TIMESLOT_DENIED,
                "exhaustion lost final SDK error");
    }

    /** @brief 취소된 예약과 늦게 진입한 handler 모두 재제출하지 않아야 합니다. */
    void cancelWithoutResubmit()
    {
        beginCase({NRF_802154_TX_ERROR_NONE});
        require(sendFrame(), "initial accepted send failed");
        rejectInitialTransmission();
        auto *late_work = radio154_fixture::pending;
        require(late_work != nullptr, "retry was not scheduled");
        require(NUCODERadio154.cancel(), "cancel failed");
        require(radio154_fixture::pending == nullptr, "cancel left queued work");
        require(radio154_fixture::cancellations == 1U, "cancel did not call delayed-work cancellation");
        /** @brief 이미 dequeue된 handler의 취소 이후 진입을 모사합니다. */
        late_work->work.handler(&late_work->work);
        expectStatistics(1U, 0U, 0U, 1U);
        require(radio154_fixture::pending == nullptr, "cancelled handler scheduled work");
        require(!NUCODERadio154.busy(), "cancel left transmitter busy");
    }

    /** @brief 최초 동기 거절은 기존 false 계약과 무재시도를 유지합니다. */
    void initialSynchronousFailure()
    {
        beginCase({NRF_802154_TX_ERROR_TIMESLOT_DENIED});
        require(!sendFrame(), "initial rejected send became accepted");
        expectStatistics(0U, 1U, 0U, 1U);
        require(radio154_fixture::pending == nullptr, "initial rejected send scheduled retry");
        require(!NUCODERadio154.busy(), "initial rejection left busy");
        require(NUCODERadio154.lastError() == nucode::radio154::Error::driver_error &&
                    NUCODERadio154.lastDriverError() == NRF_802154_TX_ERROR_TIMESLOT_DENIED,
                "initial rejection lost SDK error");
    }
}

extern "C"
{
    void nrf_802154_init(void)
    {
    }
    bool nrf_802154_reinit(void)
    {
        return true;
    }
    void nrf_802154_pan_id_set(const std::uint8_t *value)
    {
        static_cast<void>(value);
    }
    void nrf_802154_short_address_set(const std::uint8_t *value)
    {
        static_cast<void>(value);
    }
    void nrf_802154_channel_set(std::uint8_t value)
    {
        static_cast<void>(value);
    }
    void nrf_802154_tx_power_set(std::int8_t value)
    {
        static_cast<void>(value);
    }
    void nrf_802154_promiscuous_set(bool value)
    {
        static_cast<void>(value);
    }
    void nrf_802154_auto_ack_set(bool value)
    {
        require(value, "automatic ACK disabled");
    }
    bool nrf_802154_receive(void)
    {
        return true;
    }
    bool nrf_802154_sleep(void)
    {
        return true;
    }
    void nrf_802154_buffer_free_raw(std::uint8_t *buffer)
    {
        require(buffer != nullptr, "null ACK buffer");
        ++freed_buffers;
    }
    nrf_802154_tx_error_t nrf_802154_transmit_raw(
        std::uint8_t *frame, const nrf_802154_transmit_metadata_t *metadata)
    {
        require(frame != nullptr && metadata != nullptr, "missing submit input");
        require(submit_index < submit_results.size(), "unexpected extra submit");
        require(frame[0] < 128U, "invalid frame length");
        require(metadata->cca, "configured CCA changed");
        submitted_frame = frame;
        frames.emplace_back(frame, frame + static_cast<std::size_t>(frame[0]) + 1U);
        require(frames.back() == frames.front(), "retry mutated original frame");
        return submit_results[submit_index++];
    }
}

/** @brief 각 시나리오는 독립 프로세스에서 실제 backend 정적 상태로 시작합니다. */
int main(int argc, char **argv)
{
    require(argc == 2, "one scenario required");
    const std::string scenario(argv[1]);
    if (scenario == "success")
    {
        successAfterSynchronousFailure();
    }
    else if (scenario == "exhaustion")
    {
        exactBudgetExhaustion();
    }
    else if (scenario == "cancel")
    {
        cancelWithoutResubmit();
    }
    else if (scenario == "initial")
    {
        initialSynchronousFailure();
    }
    else
    {
        require(false, "unknown scenario");
    }
    const std::size_t submits_before_stop = submit_index;
    require(NUCODERadio154.stop(), "final stop failed");
    require(submit_index == submits_before_stop && radio154_fixture::pending == nullptr,
            "stop caused another submit");
    return 0;
}
