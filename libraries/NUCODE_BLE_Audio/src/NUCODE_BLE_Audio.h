/**
 * @file NUCODE_BLE_Audio.h
 * @brief NU54DK Bluetooth LE Audio codec 공개 API를 정의합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_BLE_AUDIO_H
#define NUCODE_BLE_AUDIO_H

#include <Arduino.h>

#include <cstddef>
#include <cstdint>

namespace nucode::ble
{
    class BLEConnectionHandle;
}

namespace nucode::ble::audio
{
    /** @brief LC3 codec API의 안정된 오류 분류입니다. */
    enum class Error : std::uint8_t
    {
        none = 0U,
        invalid_argument,
        already_started,
        busy,
        not_started,
        buffer_too_small,
        codec_error,
        stack_error,
        not_ready,
        not_connected,
        unsupported,
    };

    /** @brief 한 LC3 stream의 frame 구성을 지정합니다. */
    struct Lc3Config
    {
        std::uint32_t sample_rate_hz = 16000U;
        std::uint32_t frame_duration_us = 10000U;
        std::size_t frame_octets = 40U;
    };

    /** @brief unicast server가 제공할 Audio 방향입니다. */
    enum class UnicastServerMode : std::uint8_t
    {
        sink_only,
        duplex,
    };

    /**
     * @brief 16 kHz 이하 PCM과 LC3 frame을 변환합니다.
     *
     * 고정 메모리 backend는 한 번에 한 객체만 활성화합니다. encode()/decode()는 동적 메모리를
     * 할당하지 않으며 Arduino main thread에서 호출합니다.
     */
    class Lc3Codec final
    {
      public:
        /** @brief 시작 전 codec 객체를 만듭니다. */
        Lc3Codec() = default;

        /** @brief 객체 수명 종료 시 소유한 codec 자원을 반환합니다. */
        ~Lc3Codec()
        {
            end();
        }

        Lc3Codec(const Lc3Codec &) = delete;
        Lc3Codec &operator=(const Lc3Codec &) = delete;
        Lc3Codec(Lc3Codec &&) = delete;
        Lc3Codec &operator=(Lc3Codec &&) = delete;

        /** @brief 주어진 frame 구성으로 encoder와 decoder를 만듭니다. */
        Error begin(const Lc3Config &config = {}) noexcept;

        /** @brief codec 소유권과 내부 frame 상태를 반환합니다. */
        void end() noexcept;

        /** @brief PCM 한 frame을 LC3 byte frame으로 encode합니다. */
        Error encode(const std::int16_t *pcm, std::size_t sample_count, std::uint8_t *frame,
                     std::size_t frame_capacity) noexcept;

        /** @brief LC3 byte frame 하나를 PCM으로 decode합니다. */
        Error decode(const std::uint8_t *frame, std::size_t frame_size, std::int16_t *pcm,
                     std::size_t sample_capacity) noexcept;

        /** @brief 현재 구성의 PCM sample/frame 수를 반환합니다. */
        [[nodiscard]] std::size_t frameSamples() const noexcept;

        /** @brief 현재 구성의 LC3 byte/frame 수를 반환합니다. */
        [[nodiscard]] std::size_t frameOctets() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

      private:
        Error record(Error error) noexcept;

        void *state_ = nullptr;
        Error last_error_ = Error::not_started;
    };

    /**
     * @brief PACS와 ASCS의 unicast sink를 제공하고 LC3 frame을 수신합니다.
     *
     * BLEDevice.begin() 뒤, 광고 시작 전에 begin()을 호출합니다. 하나의
     * 16 kHz·10 ms·40-byte mono LC3 stream과 고정 크기 수신 queue를 사용합니다.
     * 수신 frame의 복호화는 공개 Lc3Codec으로 Arduino loop에서 수행합니다.
     */
    class UnicastServer final
    {
      public:
        UnicastServer() = default;

        ~UnicastServer()
        {
            (void)end();
        }

        UnicastServer(const UnicastServer &) = delete;
        UnicastServer &operator=(const UnicastServer &) = delete;
        UnicastServer(UnicastServer &&) = delete;
        UnicastServer &operator=(UnicastServer &&) = delete;

        /** @brief 기존 단방향 PACS/ASCS sink를 등록합니다. */
        Error begin() noexcept;

        /** @brief 요청한 방향의 PACS/ASCS와 LC3 capability를 등록합니다. */
        Error begin(UnicastServerMode mode) noexcept;

        /** @brief 연결이 해제된 뒤 서비스와 고정 자원을 반환합니다. */
        Error end() noexcept;

        /** @brief 현재 ASE가 streaming 상태인지 반환합니다. */
        [[nodiscard]] bool streaming() const noexcept;

        /** @brief 수신한 LC3 frame 하나를 복사하고 queue에서 제거합니다. */
        [[nodiscard]] bool readFrame(std::uint8_t (&frame)[40]) noexcept;

        /** @brief duplex source ASE가 streaming 상태인지 반환합니다. */
        [[nodiscard]] bool sourceStreaming() const noexcept;

        /** @brief duplex source ASE로 LC3 frame 하나를 보냅니다. */
        Error sendFrame(const std::uint8_t (&frame)[40]) noexcept;

        /** @brief controller가 수락한 duplex source frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t sentFrames() const noexcept;

        /** @brief 유효하게 수신한 LC3 frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t receivedFrames() const noexcept;

        /** @brief queue가 가득 차서 버린 frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedFrames() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 stack 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /** @brief unicast client의 공개 비동기 단계입니다. */
    enum class UnicastClientStage : std::uint8_t
    {
        idle,
        securing,
        discovering,
        configuring,
        streaming,
        failed,
        stopping,
        released,
    };

    /** @brief 마지막 unicast client 작업을 나타냅니다. */
    enum class UnicastClientStep : std::uint8_t
    {
        none,
        security,
        discover,
        configure,
        group,
        qos,
        enable,
        connect,
        send,
        cleanup,
        disable,
        release,
    };

    /**
     * @brief PACS/ASCS sink를 찾고 mono LC3 frame을 CIS로 보냅니다.
     *
     * BLEDevice가 연결한 하나의 peer에만 결합합니다. poll()은 보안, PACS 검색,
     * ASE codec/QoS·enable·CIS 시작을 비동기로 진행합니다. 40-byte LC3 frame
     * encode와 전송 간격 선택은 Arduino sketch가 공개 API로 수행합니다.
     */
    class UnicastClient final
    {
      public:
        UnicastClient() = default;

        ~UnicastClient()
        {
            (void)end();
        }

        UnicastClient(const UnicastClient &) = delete;
        UnicastClient &operator=(const UnicastClient &) = delete;
        UnicastClient(UnicastClient &&) = delete;
        UnicastClient &operator=(UnicastClient &&) = delete;

        /** @brief 연결된 peer를 참조하고 L2 보안 절차를 시작합니다. */
        Error begin(const BLEConnectionHandle &connection) noexcept;

        /** @brief callback 결과를 Arduino 문맥에서 다음 단계로 진행합니다. */
        void poll() noexcept;

        /** @brief streaming 상태에서 한 LC3 frame을 비차단 전송합니다. */
        Error sendFrame(const std::uint8_t (&frame)[40]) noexcept;

        /** @brief sink ASE를 비동기로 disable한 뒤 release합니다. */
        Error stop() noexcept;

        /** @brief peer 연결 해제 뒤 그룹과 callback 자원을 반환합니다. */
        Error end() noexcept;

        /** @brief 현재 비동기 단계를 반환합니다. */
        [[nodiscard]] UnicastClientStage stage() const noexcept;

        /** @brief 마지막 실패가 발생한 단계를 반환합니다. */
        [[nodiscard]] UnicastClientStage failedAt() const noexcept;

        /** @brief 마지막 Host 요청 또는 오류 callback의 작업을 반환합니다. */
        [[nodiscard]] UnicastClientStep lastStep() const noexcept;

        /** @brief controller에 수락된 frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t sentFrames() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 Host/controller 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        UnicastClientStage stage_ = UnicastClientStage::idle;
        UnicastClientStage failure_stage_ = UnicastClientStage::idle;
        UnicastClientStep last_step_ = UnicastClientStep::none;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };
} // namespace nucode::ble::audio

#endif
