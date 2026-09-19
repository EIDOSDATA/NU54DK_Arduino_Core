/**
 * @file NUCODE_BLE_Audio_PublicBroadcast.cpp
 * @brief 공개 오디오 방송의 조합형 C++ API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

namespace nucode::ble::audio
{
    /** @brief 암호화하지 않은 공개 방송을 시작합니다. */
    Error PublicAudioBroadcastSource::begin(
        const PublicBroadcastSourceConfig &config) noexcept
    {
        return initiator_.startPublic(config, nullptr);
    }

    /** @brief Broadcast Code로 암호화한 공개 방송을 시작합니다. */
    Error PublicAudioBroadcastSource::begin(
        const PublicBroadcastSourceConfig &config,
        const BroadcastCode &broadcast_code) noexcept
    {
        return initiator_.startPublic(config, broadcast_code);
    }

    /** @brief 공개 방송 source 자원을 반환합니다. */
    Error PublicAudioBroadcastSource::end() noexcept
    {
        return initiator_.end();
    }

    /** @brief 공개 방송 BIS가 송신 중인지 반환합니다. */
    bool PublicAudioBroadcastSource::streaming() const noexcept
    {
        return initiator_.streaming();
    }

    /** @brief 공개 방송 BIS로 LC3 frame 하나를 전송합니다. */
    Error PublicAudioBroadcastSource::sendFrame(
        const std::uint8_t (&frame)[40]) noexcept
    {
        return initiator_.sendFrame(frame);
    }

    /** @brief 내부 CAP source 단계를 반환합니다. */
    CapStage PublicAudioBroadcastSource::stage() const noexcept
    {
        return initiator_.stage();
    }

    /** @brief controller에 수락된 frame 수를 반환합니다. */
    std::uint32_t PublicAudioBroadcastSource::sentFrames() const noexcept
    {
        return initiator_.sentFrames();
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error PublicAudioBroadcastSource::lastError() const noexcept
    {
        return initiator_.lastError();
    }

    /** @brief 마지막 Host/controller 오류를 반환합니다. */
    int PublicAudioBroadcastSource::nativeCode() const noexcept
    {
        return initiator_.nativeCode();
    }

    /** @brief 암호화하지 않은 공개 방송 검색을 시작합니다. */
    Error PublicAudioBroadcastSink::begin(
        const PublicBroadcastFilter &filter) noexcept
    {
        return start(filter, nullptr);
    }

    /** @brief Broadcast Code가 필요한 공개 방송 검색을 시작합니다. */
    Error PublicAudioBroadcastSink::begin(
        const PublicBroadcastFilter &filter,
        const BroadcastCode &broadcast_code) noexcept
    {
        return start(filter, broadcast_code);
    }

    /** @brief CAP Acceptor와 공개 broadcast sink를 차례로 준비합니다. */
    Error PublicAudioBroadcastSink::start(
        const PublicBroadcastFilter &filter,
        const std::uint8_t *broadcast_code) noexcept
    {
        if (started_)
        {
            last_error_ = Error::already_started;
            native_code_ = 0;
            return last_error_;
        }
        if (filter.required_quality != PublicBroadcastQuality::standard)
        {
            last_error_ = Error::unsupported;
            native_code_ = 0;
            return last_error_;
        }

        Error result = acceptor_.begin();
        if (result != Error::none)
        {
            last_error_ = result;
            native_code_ = acceptor_.nativeCode();
            return result;
        }
        acceptor_started_ = true;

        result = sink_.startPublic(filter, broadcast_code);
        if (result != Error::none)
        {
            last_error_ = result;
            native_code_ = sink_.nativeCode();
            const Error sink_cleanup = sink_.end();
            sink_started_ = (sink_cleanup != Error::none) &&
                            (sink_cleanup != Error::not_started);
            if (!sink_started_)
            {
                const Error acceptor_cleanup = acceptor_.end();
                acceptor_started_ = acceptor_cleanup != Error::none;
                if (acceptor_started_)
                {
                    last_error_ = acceptor_cleanup;
                    native_code_ = acceptor_.nativeCode();
                }
            }
            started_ = sink_started_ || acceptor_started_;
            return last_error_;
        }
        sink_started_ = true;

        started_ = true;
        last_error_ = Error::none;
        native_code_ = 0;
        return Error::none;
    }

    /** @brief callback 결과를 공개 방송 동기화 단계로 진행합니다. */
    void PublicAudioBroadcastSink::poll() noexcept
    {
        if (!started_)
        {
            return;
        }
        sink_.poll();
        if (sink_.lastError() != Error::none)
        {
            last_error_ = sink_.lastError();
            native_code_ = sink_.nativeCode();
        }
    }

    /** @brief 공개 방송 sink와 CAP Acceptor 자원을 반환합니다. */
    Error PublicAudioBroadcastSink::end() noexcept
    {
        if (!started_)
        {
            last_error_ = Error::not_started;
            native_code_ = 0;
            return last_error_;
        }

        if (sink_started_)
        {
            const Error sink_result = sink_.end();
            if (sink_result != Error::none)
            {
                last_error_ = sink_result;
                native_code_ = sink_.nativeCode();
                return last_error_;
            }
            sink_started_ = false;
        }
        if (acceptor_started_)
        {
            const Error acceptor_result = acceptor_.end();
            if (acceptor_result != Error::none)
            {
                last_error_ = acceptor_result;
                native_code_ = acceptor_.nativeCode();
                return last_error_;
            }
            acceptor_started_ = false;
        }
        started_ = false;
        last_error_ = Error::none;
        native_code_ = 0;
        return Error::none;
    }

    /** @brief 선택한 공개 방송 정보를 고정 크기 구조체에 복사합니다. */
    bool PublicAudioBroadcastSink::selected(PublicBroadcastInfo &info) const noexcept
    {
        return sink_.selectedPublic(info);
    }

    /** @brief 공개 방송 BIS가 수신 중인지 반환합니다. */
    bool PublicAudioBroadcastSink::streaming() const noexcept
    {
        return sink_.streaming();
    }

    /** @brief 공개 방송에서 받은 LC3 frame 하나를 반환합니다. */
    bool PublicAudioBroadcastSink::readFrame(
        std::uint8_t (&frame)[40]) noexcept
    {
        return sink_.readFrame(frame);
    }

    /** @brief 내부 broadcast sink 단계를 반환합니다. */
    BroadcastStage PublicAudioBroadcastSink::stage() const noexcept
    {
        return sink_.stage();
    }

    /** @brief 내부 broadcast sink의 마지막 작업을 반환합니다. */
    BroadcastSinkStep PublicAudioBroadcastSink::lastStep() const noexcept
    {
        return sink_.lastStep();
    }

    /** @brief 수신한 LC3 frame 수를 반환합니다. */
    std::uint32_t PublicAudioBroadcastSink::receivedFrames() const noexcept
    {
        return sink_.receivedFrames();
    }

    /** @brief queue 포화로 폐기한 LC3 frame 수를 반환합니다. */
    std::uint32_t PublicAudioBroadcastSink::droppedFrames() const noexcept
    {
        return sink_.droppedFrames();
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error PublicAudioBroadcastSink::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 Host/controller 오류를 반환합니다. */
    int PublicAudioBroadcastSink::nativeCode() const noexcept
    {
        return native_code_;
    }
} // namespace nucode::ble::audio
