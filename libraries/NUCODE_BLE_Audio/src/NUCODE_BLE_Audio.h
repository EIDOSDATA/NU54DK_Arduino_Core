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
    struct BLEScanResult;
}

namespace nucode::ble::audio
{
    /** @brief 암호화 broadcast stream에 사용하는 16-byte 코드입니다. */
    using BroadcastCode = std::uint8_t[16];

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

    /** @brief unicast client가 사용할 LC3 stream 방향입니다. */
    enum class UnicastClientMode : std::uint8_t
    {
        transmit_only,
        duplex,
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
     * @brief PACS/ASCS ASE를 찾고 mono LC3 frame을 CIS로 송수신합니다.
     *
     * BLEDevice가 연결한 하나의 peer에만 결합합니다. poll()은 보안, PACS 검색,
     * ASE codec/QoS·enable·CIS 시작을 비동기로 진행합니다. 기본 begin()은
     * 송신 전용이고 duplex mode는 상대 source ASE의 수신도 시작합니다.
     * 40-byte LC3 frame encode/decode와 전송 간격 선택은 Sketch가 수행합니다.
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

        /** @brief 요청한 방향의 ASE를 사용할 unicast 연결을 시작합니다. */
        Error begin(const BLEConnectionHandle &connection, UnicastClientMode mode) noexcept;

        /** @brief callback 결과를 Arduino 문맥에서 다음 단계로 진행합니다. */
        void poll() noexcept;

        /** @brief streaming 상태에서 한 LC3 frame을 비차단 전송합니다. */
        Error sendFrame(const std::uint8_t (&frame)[40]) noexcept;

        /** @brief 양방향 연결에서 수신한 LC3 frame 하나를 가져옵니다. */
        [[nodiscard]] bool readFrame(std::uint8_t (&frame)[40]) noexcept;

        /** @brief 소유한 ASE를 비동기로 disable한 뒤 release합니다. */
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

        /** @brief 유효하게 수신한 LC3 frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t receivedFrames() const noexcept;

        /** @brief 수신 queue가 가득 차서 버린 frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedFrames() const noexcept;

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

    /** @brief broadcast audio 객체의 공개 비동기 단계입니다. */
    enum class BroadcastStage : std::uint8_t
    {
        idle,
        scanning,
        synchronizing,
        streaming,
        stopping,
        failed,
    };

    /** @brief 마지막 broadcast sink 작업을 나타냅니다. */
    enum class BroadcastSinkStep : std::uint8_t
    {
        none,
        pacs,
        capability,
        location,
        supported_contexts,
        available_contexts,
        scan_delegator,
        callbacks,
        scan,
        periodic_sync,
        sink_create,
        bis_sync,
        cleanup,
        cleanup_sink_stop,
        cleanup_sink_delete,
        cleanup_periodic_sync,
        cleanup_callbacks,
        cleanup_scan_delegator,
        cleanup_capability,
        cleanup_pacs,
    };

    /** @brief Broadcast Assistant의 공개 비동기 단계입니다. */
    enum class BroadcastAssistantStage : std::uint8_t
    {
        idle,
        discovering,
        ready,
        operating,
        failed,
    };

    /** @brief 마지막 Broadcast Assistant 작업을 나타냅니다. */
    enum class BroadcastAssistantStep : std::uint8_t
    {
        none,
        discover,
        select_source,
        add_source,
        modify_source,
        broadcast_code,
        remove_source,
        read_state,
        cleanup,
    };

    /**
     * @brief mono LC3 frame을 BAP broadcast stream으로 송신합니다.
     *
     * BLEDevice.begin() 뒤 begin()을 호출합니다. 객체는 16 kHz, 10 ms,
     * 40-byte LC3 frame 한 개를 담는 BIS를 만들고 extended/periodic 광고와
     * BASE를 함께 게시합니다. PCM 변환은 공개 Lc3Codec으로 수행합니다.
     */
    class BroadcastSource final
    {
      public:
        BroadcastSource() = default;

        ~BroadcastSource()
        {
            (void)end();
        }

        BroadcastSource(const BroadcastSource &) = delete;
        BroadcastSource &operator=(const BroadcastSource &) = delete;
        BroadcastSource(BroadcastSource &&) = delete;
        BroadcastSource &operator=(BroadcastSource &&) = delete;

        /** @brief 주어진 방송 이름으로 BASE와 BIS 광고를 시작합니다. */
        Error begin(const char *broadcast_name = "NU54-AUDIO-BROADCAST") noexcept;

        /** @brief 주어진 16-byte code로 암호화한 BASE와 BIS 광고를 시작합니다. */
        Error begin(const char *broadcast_name, const BroadcastCode &broadcast_code) noexcept;

        /** @brief 방송을 중단하고 광고와 고정 자원을 반환합니다. */
        Error end() noexcept;

        /** @brief BIS가 LC3 frame 전송 가능한 상태인지 반환합니다. */
        [[nodiscard]] bool streaming() const noexcept;

        /** @brief BIS로 LC3 frame 하나를 비차단 전송합니다. */
        Error sendFrame(const std::uint8_t (&frame)[40]) noexcept;

        /** @brief controller에 수락된 frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t sentFrames() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 Host/controller 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error start(const char *broadcast_name,
                    const std::uint8_t *broadcast_code) noexcept;
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /**
     * @brief BAP broadcast source를 찾고 mono LC3 frame을 수신합니다.
     *
     * BLEDevice.begin() 뒤 begin()을 호출하고 loop()에서 poll()을 반복합니다.
     * 광고 이름이 일치하는 source의 periodic advertising과 BIS 1에 동기화하며,
     * 수신 frame의 복호화는 공개 Lc3Codec으로 Arduino loop에서 수행합니다.
     */
    class BroadcastSink final
    {
      public:
        BroadcastSink() = default;

        ~BroadcastSink()
        {
            (void)end();
        }

        BroadcastSink(const BroadcastSink &) = delete;
        BroadcastSink &operator=(const BroadcastSink &) = delete;
        BroadcastSink(BroadcastSink &&) = delete;
        BroadcastSink &operator=(BroadcastSink &&) = delete;

        /** @brief 방송 이름을 선택하고 extended advertising 검색을 시작합니다. */
        Error begin(const char *broadcast_name = "NU54-AUDIO-BROADCAST") noexcept;

        /** @brief 방송 이름과 16-byte code로 암호화된 BIS 검색을 시작합니다. */
        Error begin(const char *broadcast_name, const BroadcastCode &broadcast_code) noexcept;

        /** @brief Broadcast Assistant가 지정할 source를 기다리는 Scan Delegator를 시작합니다. */
        Error beginDelegated() noexcept;

        /** @brief callback 결과를 Arduino 문맥에서 다음 동기화 단계로 진행합니다. */
        void poll() noexcept;

        /** @brief BIS와 periodic advertising 동기화를 끊고 자원을 반환합니다. */
        Error end() noexcept;

        /** @brief BIS가 LC3 frame 수신 가능한 상태인지 반환합니다. */
        [[nodiscard]] bool streaming() const noexcept;

        /** @brief 수신한 LC3 frame 하나를 복사하고 queue에서 제거합니다. */
        [[nodiscard]] bool readFrame(std::uint8_t (&frame)[40]) noexcept;

        /** @brief 현재 검색 또는 동기화 단계를 반환합니다. */
        [[nodiscard]] BroadcastStage stage() const noexcept;

        /** @brief 마지막 Host 요청 또는 오류가 발생한 작업을 반환합니다. */
        [[nodiscard]] BroadcastSinkStep lastStep() const noexcept;

        /** @brief 유효하게 수신한 LC3 frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t receivedFrames() const noexcept;

        /** @brief queue가 가득 차서 버린 frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedFrames() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 Host/controller 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

        /** @brief Assistant가 수락시킨 source add 요청 수를 반환합니다. */
        [[nodiscard]] std::uint32_t delegatedAdds() const noexcept;

        /** @brief Assistant가 수락시킨 source modify 요청 수를 반환합니다. */
        [[nodiscard]] std::uint32_t delegatedModifications() const noexcept;

        /** @brief Assistant가 수락시킨 source remove 요청 수를 반환합니다. */
        [[nodiscard]] std::uint32_t delegatedRemovals() const noexcept;

      private:
        Error start(const char *broadcast_name,
                    const std::uint8_t *broadcast_code) noexcept;
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        BroadcastStage stage_ = BroadcastStage::idle;
        BroadcastSinkStep last_step_ = BroadcastSinkStep::none;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /**
     * @brief BASS server를 제어해 Broadcast Source를 위임하는 Assistant입니다.
     *
     * BLEConnection이 만든 Scan Delegator 연결로 BASS를 검색합니다. Sketch가
     * BLEScanResult에서 source를 선택하면 add/modify/code/remove control point를
     * 비동기로 실행하고 receive state 통지를 고정 크기 상태로 보존합니다.
     */
    class BroadcastAssistant final
    {
      public:
        BroadcastAssistant() = default;

        ~BroadcastAssistant()
        {
            (void)end();
        }

        BroadcastAssistant(const BroadcastAssistant &) = delete;
        BroadcastAssistant &operator=(const BroadcastAssistant &) = delete;
        BroadcastAssistant(BroadcastAssistant &&) = delete;
        BroadcastAssistant &operator=(BroadcastAssistant &&) = delete;

        /** @brief 연결된 Scan Delegator의 BASS와 receive state를 검색합니다. */
        Error begin(const BLEConnectionHandle &connection) noexcept;

        /** @brief Broadcast Audio announcement가 든 scan 결과를 위임 대상으로 선택합니다. */
        Error selectSource(const BLEScanResult &result) noexcept;

        /** @brief 선택한 source의 PA와 BIS 1 동기화를 Scan Delegator에 요청합니다. */
        Error addSource() noexcept;

        /** @brief 기존 source의 PA와 BIS 1 동기화 요청을 갱신합니다. */
        Error modifySource(bool synchronize = true) noexcept;

        /** @brief 암호화 source에 사용할 16-byte Broadcast Code를 전달합니다. */
        Error setBroadcastCode(const BroadcastCode &broadcast_code) noexcept;

        /** @brief 현재 receive state source를 Scan Delegator에서 제거합니다. */
        Error removeSource() noexcept;

        /** @brief 첫 receive state를 다시 읽어 통지 상태와 대조합니다. */
        Error readState() noexcept;

        /** @brief callback과 연결 참조를 반환합니다. */
        Error end() noexcept;

        /** @brief 현재 비동기 단계를 반환합니다. */
        [[nodiscard]] BroadcastAssistantStage stage() const noexcept;

        /** @brief 마지막 요청 작업을 반환합니다. */
        [[nodiscard]] BroadcastAssistantStep lastStep() const noexcept;

        /** @brief BASS 검색에서 확인한 receive state 개수를 반환합니다. */
        [[nodiscard]] std::uint8_t receiveStateCount() const noexcept;

        /** @brief 통지에서 확인한 source ID가 있는지 반환합니다. */
        [[nodiscard]] bool hasSource() const noexcept;

        /** @brief 마지막 receive state의 source ID를 반환합니다. */
        [[nodiscard]] std::uint8_t sourceId() const noexcept;

        /** @brief 마지막 receive state가 PA synchronized인지 반환합니다. */
        [[nodiscard]] bool periodicSynchronized() const noexcept;

        /** @brief 마지막 receive state가 BIS 1 synchronized인지 반환합니다. */
        [[nodiscard]] bool bisSynchronized() const noexcept;

        /** @brief 수신한 receive state 통지 수를 반환합니다. */
        [[nodiscard]] std::uint32_t stateUpdates() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 BASS/GATT 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        BroadcastAssistantStage stage_ = BroadcastAssistantStage::idle;
        BroadcastAssistantStep last_step_ = BroadcastAssistantStep::none;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };
} // namespace nucode::ble::audio

#endif
