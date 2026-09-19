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

    /** @brief CAP unicast Initiator의 공개 비동기 단계입니다. */
    enum class CapUnicastStage : std::uint8_t
    {
        idle,
        securing,
        discovering_common_audio_service,
        discovering_audio_streams,
        ready,
        starting,
        streaming,
        stopping,
        cancelled,
        failed,
    };

    /** @brief 마지막 CAP unicast 작업을 나타냅니다. */
    enum class CapUnicastStep : std::uint8_t
    {
        none,
        security,
        common_audio_service,
        audio_streams,
        group,
        start,
        send,
        stop,
        cancel,
        cleanup,
    };

    /**
     * @brief CAP 절차로 한 Acceptor의 mono LC3 unicast stream을 제어합니다.
     *
     * begin()은 연결된 Acceptor의 보안, CAS, PACS/ASCS를 차례로 확인합니다.
     * ready() 뒤 start()를 호출하면 ad-hoc CAP unicast group을 시작합니다.
     * 진행 중인 시작·중단 절차는 cancel()로 취소할 수 있으며, callback이 특정
     * Acceptor 실패를 보고했는지는 failedOnPeer()로 구분합니다.
     */
    class CapUnicastInitiator final
    {
      public:
        CapUnicastInitiator() = default;

        ~CapUnicastInitiator()
        {
            (void)end();
        }

        CapUnicastInitiator(const CapUnicastInitiator &) = delete;
        CapUnicastInitiator &operator=(const CapUnicastInitiator &) = delete;
        CapUnicastInitiator(CapUnicastInitiator &&) = delete;
        CapUnicastInitiator &operator=(CapUnicastInitiator &&) = delete;

        /** @brief 연결된 Acceptor를 참조하고 보안·CAS·PACS/ASCS 검색을 시작합니다. */
        Error begin(const BLEConnectionHandle &connection) noexcept;

        /** @brief callback 결과를 Arduino 문맥에서 다음 단계로 진행합니다. */
        void poll() noexcept;

        /** @brief 준비된 Acceptor에 CAP unicast audio 시작 절차를 요청합니다. */
        Error start() noexcept;

        /** @brief 진행 중인 CAP unicast 시작·중단 절차를 취소합니다. */
        Error cancel() noexcept;

        /** @brief streaming stream을 중단하고 Acceptor ASE를 release합니다. */
        Error stop() noexcept;

        /** @brief group, callback과 연결 참조를 반환합니다. */
        Error end() noexcept;

        /** @brief CAP group 시작을 요청할 준비가 되었는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief CIS가 LC3 frame 전송 가능한 상태인지 반환합니다. */
        [[nodiscard]] bool streaming() const noexcept;

        /** @brief 마지막 완료 callback이 명시적 취소를 확인했는지 반환합니다. */
        [[nodiscard]] bool cancelled() const noexcept;

        /** @brief 마지막 실패 callback이 특정 Acceptor를 지목했는지 반환합니다. */
        [[nodiscard]] bool failedOnPeer() const noexcept;

        /** @brief 현재 CAP unicast 단계를 반환합니다. */
        [[nodiscard]] CapUnicastStage stage() const noexcept;

        /** @brief 마지막 CAP unicast 작업을 반환합니다. */
        [[nodiscard]] CapUnicastStep lastStep() const noexcept;

        /** @brief CIS로 LC3 frame 하나를 비차단 전송합니다. */
        Error sendFrame(const std::uint8_t (&frame)[40]) noexcept;

        /** @brief controller에 수락된 frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t sentFrames() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 CAP/GATT/controller 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        CapUnicastStage stage_ = CapUnicastStage::idle;
        CapUnicastStep last_step_ = CapUnicastStep::none;
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

    /** @brief 공개 방송이 제공하는 오디오 품질 등급입니다. */
    enum class PublicBroadcastQuality : std::uint8_t
    {
        standard,
        high,
    };

    /** @brief 공개 오디오 방송의 게시 설정입니다. */
    struct PublicBroadcastSourceConfig
    {
        const char *broadcast_name = "NU54-PUBLIC-AUDIO";
        const char *program_info = "NUCODE public audio";
        PublicBroadcastQuality quality = PublicBroadcastQuality::standard;
    };

    /** @brief 공개 오디오 방송을 찾을 때 적용할 조건입니다. */
    struct PublicBroadcastFilter
    {
        const char *broadcast_name = nullptr;
        PublicBroadcastQuality required_quality = PublicBroadcastQuality::standard;
    };

    /** @brief 검색으로 선택한 공개 오디오 방송의 고정 크기 정보입니다. */
    struct PublicBroadcastInfo
    {
        char broadcast_name[129] = {};
        char program_info[65] = {};
        std::uint32_t broadcast_id = 0U;
        bool encrypted = false;
        bool standard_quality = false;
        bool high_quality = false;
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
        friend class PublicAudioBroadcastSink;

        Error start(const char *broadcast_name,
                    const std::uint8_t *broadcast_code) noexcept;
        Error startPublic(const PublicBroadcastFilter &filter,
                          const std::uint8_t *broadcast_code) noexcept;
        Error startConfigured(const char *broadcast_name,
                              const std::uint8_t *broadcast_code,
                              bool public_broadcast) noexcept;
        bool selectedPublic(PublicBroadcastInfo &info) const noexcept;
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

    /** @brief 오디오 입력 gain 제어 방식을 나타냅니다. */
    enum class AudioInputMode : std::uint8_t
    {
        manual_only = 0U,
        automatic_only = 1U,
        manual = 2U,
        automatic = 3U,
    };

    /** @brief 오디오 입력의 용도를 나타냅니다. */
    enum class AudioInputType : std::uint8_t
    {
        unspecified = 0U,
        bluetooth = 1U,
        microphone = 2U,
        analog = 3U,
        digital = 4U,
        radio = 5U,
        streaming = 6U,
        ambient = 7U,
    };

    /** @brief 오디오 제어 객체의 공개 비동기 단계입니다. */
    enum class AudioControlStage : std::uint8_t
    {
        idle,
        discovering,
        ready,
        operating,
        failed,
        disconnected,
    };

    /** @brief 마지막 오디오 제어 작업을 나타냅니다. */
    enum class AudioControlStep : std::uint8_t
    {
        none,
        discover,
        read_volume,
        set_volume,
        volume_up,
        volume_down,
        mute_volume,
        unmute_volume,
        read_offset,
        set_offset,
        set_output_location,
        set_output_description,
        read_input,
        set_input_gain,
        mute_input,
        unmute_input,
        set_input_mode,
        set_input_description,
        read_microphone,
        mute_microphone,
        unmute_microphone,
        disable_microphone_mute,
        cleanup,
    };

    /** @brief Volume Renderer의 현재 volume과 mute 상태입니다. */
    struct VolumeState
    {
        std::uint8_t volume = 0U;
        bool muted = false;
        std::uint8_t flags = 0U;
    };

    /** @brief Volume Offset Control Service의 현재 상태입니다. */
    struct VolumeOffsetState
    {
        std::int16_t offset = 0;
        std::uint32_t location = 0U;
    };

    /** @brief Audio Input Control Service의 현재 상태와 허용 범위입니다. */
    struct AudioInputState
    {
        std::int8_t gain = 0;
        std::int8_t minimum_gain = -100;
        std::int8_t maximum_gain = 100;
        std::uint8_t units = 1U;
        AudioInputMode mode = AudioInputMode::manual;
        AudioInputType type = AudioInputType::unspecified;
        bool muted = false;
        bool mute_disabled = false;
        bool active = true;
    };

    /** @brief Microphone Control Service의 현재 mute 상태입니다. */
    struct MicrophoneState
    {
        bool muted = false;
        bool mute_disabled = false;
    };

    /** @brief 포함할 Volume Offset Control Service의 초기 설정입니다. */
    struct VolumeOffsetConfig
    {
        std::int16_t offset = 0;
        std::uint32_t location = 0U;
        bool location_writable = true;
        bool description_writable = true;
        const char *description = "Speaker";
    };

    /** @brief 포함할 Audio Input Control Service의 초기 설정입니다. */
    struct AudioInputConfig
    {
        std::int8_t gain = 0;
        std::int8_t minimum_gain = -100;
        std::int8_t maximum_gain = 100;
        std::uint8_t units = 1U;
        AudioInputMode mode = AudioInputMode::manual;
        AudioInputType type = AudioInputType::unspecified;
        bool muted = false;
        bool active = true;
        bool description_writable = true;
        const char *description = "Input";
    };

    /** @brief Volume Renderer와 포함 service의 초기 설정입니다. */
    struct VolumeRendererConfig
    {
        std::uint8_t volume = 100U;
        std::uint8_t step = 5U;
        bool muted = false;
        VolumeOffsetConfig output = {};
        AudioInputConfig input = {};
    };

    /** @brief Microphone Device와 포함 input의 초기 설정입니다. */
    struct MicrophoneDeviceConfig
    {
        bool muted = false;
        AudioInputConfig input = {};
    };

    /**
     * @brief volume, mute, offset과 audio input을 제공하는 Volume Renderer입니다.
     *
     * BLEDevice.begin() 뒤 광고를 시작하기 전에 begin()을 호출합니다. service는
     * image 수명 동안 유지되며 end()는 공개 객체의 소유권만 반환합니다.
     */
    class VolumeRenderer final
    {
      public:
        VolumeRenderer() = default;

        ~VolumeRenderer()
        {
            (void)end();
        }

        VolumeRenderer(const VolumeRenderer &) = delete;
        VolumeRenderer &operator=(const VolumeRenderer &) = delete;
        VolumeRenderer(VolumeRenderer &&) = delete;
        VolumeRenderer &operator=(VolumeRenderer &&) = delete;

        /** @brief Volume Renderer와 VOCS·AICS 각 한 개를 준비합니다. */
        Error begin(const VolumeRendererConfig &config = {}) noexcept;

        /** @brief 공개 facade 소유권을 반환합니다. */
        Error end() noexcept;

        /** @brief volume을 절대값으로 설정합니다. */
        Error setVolume(std::uint8_t volume) noexcept;

        /** @brief 설정된 step만큼 volume을 올립니다. */
        Error volumeUp() noexcept;

        /** @brief 설정된 step만큼 volume을 내립니다. */
        Error volumeDown() noexcept;

        /** @brief volume 출력을 mute합니다. */
        Error mute() noexcept;

        /** @brief volume 출력을 unmute합니다. */
        Error unmute() noexcept;

        /** @brief 포함된 output의 volume offset을 설정합니다. */
        Error setOffset(std::int16_t offset) noexcept;

        /** @brief 포함된 output의 audio location을 설정합니다. */
        Error setOutputLocation(std::uint32_t location) noexcept;

        /** @brief 포함된 output 설명을 설정합니다. */
        Error setOutputDescription(const char *description) noexcept;

        /** @brief 포함된 input gain을 설정합니다. */
        Error setInputGain(std::int8_t gain) noexcept;

        /** @brief 포함된 input을 mute합니다. */
        Error muteInput() noexcept;

        /** @brief 포함된 input을 unmute합니다. */
        Error unmuteInput() noexcept;

        /** @brief 포함된 input gain mode를 설정합니다. */
        Error setInputMode(AudioInputMode mode) noexcept;

        /** @brief 포함된 input 설명을 설정합니다. */
        Error setInputDescription(const char *description) noexcept;

        /** @brief service와 공개 facade가 준비되었는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief 마지막으로 관찰한 volume 상태를 반환합니다. */
        [[nodiscard]] VolumeState state() const noexcept;

        /** @brief 마지막으로 관찰한 offset 상태를 반환합니다. */
        [[nodiscard]] VolumeOffsetState offsetState() const noexcept;

        /** @brief 마지막으로 관찰한 input 상태를 반환합니다. */
        [[nodiscard]] AudioInputState inputState() const noexcept;

        /** @brief local 또는 remote 상태 변경 callback 수를 반환합니다. */
        [[nodiscard]] std::uint32_t stateUpdates() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 profile 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        std::uint32_t generation_ = 0U;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /** @brief 원격 Volume Renderer의 VCP·VOCS·AICS를 제어합니다. */
    class VolumeController final
    {
      public:
        VolumeController() = default;

        ~VolumeController()
        {
            (void)end();
        }

        VolumeController(const VolumeController &) = delete;
        VolumeController &operator=(const VolumeController &) = delete;
        VolumeController(VolumeController &&) = delete;
        VolumeController &operator=(VolumeController &&) = delete;

        /** @brief 연결된 peer에서 VCP와 포함 VOCS·AICS를 검색합니다. */
        Error begin(const BLEConnectionHandle &connection) noexcept;

        /** @brief 연결 소실과 callback 결과를 공개 상태에 반영합니다. */
        void poll() noexcept;

        /** @brief 연결 참조와 facade 소유권을 반환합니다. */
        Error end() noexcept;

        Error readVolume() noexcept;
        Error setVolume(std::uint8_t volume) noexcept;
        Error volumeUp() noexcept;
        Error volumeDown() noexcept;
        Error mute() noexcept;
        Error unmute() noexcept;
        Error readOffset() noexcept;
        Error setOffset(std::int16_t offset) noexcept;
        Error setOutputLocation(std::uint32_t location) noexcept;
        Error setOutputDescription(const char *description) noexcept;
        Error readInput() noexcept;
        Error setInputGain(std::int8_t gain) noexcept;
        Error muteInput() noexcept;
        Error unmuteInput() noexcept;
        Error setInputMode(AudioInputMode mode) noexcept;
        Error setInputDescription(const char *description) noexcept;

        [[nodiscard]] bool ready() const noexcept;
        [[nodiscard]] bool busy() const noexcept;
        [[nodiscard]] AudioControlStage stage() const noexcept;
        [[nodiscard]] AudioControlStep lastStep() const noexcept;
        [[nodiscard]] VolumeState state() const noexcept;
        [[nodiscard]] VolumeOffsetState offsetState() const noexcept;
        [[nodiscard]] AudioInputState inputState() const noexcept;
        [[nodiscard]] std::uint32_t stateUpdates() const noexcept;
        [[nodiscard]] Error lastError() const noexcept;
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        std::uint32_t generation_ = 0U;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /** @brief microphone mute와 포함 audio input을 제공하는 Microphone Device입니다. */
    class MicrophoneDevice final
    {
      public:
        MicrophoneDevice() = default;

        ~MicrophoneDevice()
        {
            (void)end();
        }

        MicrophoneDevice(const MicrophoneDevice &) = delete;
        MicrophoneDevice &operator=(const MicrophoneDevice &) = delete;
        MicrophoneDevice(MicrophoneDevice &&) = delete;
        MicrophoneDevice &operator=(MicrophoneDevice &&) = delete;

        Error begin(const MicrophoneDeviceConfig &config = {}) noexcept;
        Error end() noexcept;
        Error mute() noexcept;
        Error unmute() noexcept;
        Error disableMute() noexcept;
        Error setInputGain(std::int8_t gain) noexcept;
        Error muteInput() noexcept;
        Error unmuteInput() noexcept;
        Error setInputMode(AudioInputMode mode) noexcept;
        Error setInputDescription(const char *description) noexcept;
        [[nodiscard]] bool ready() const noexcept;
        [[nodiscard]] MicrophoneState state() const noexcept;
        [[nodiscard]] AudioInputState inputState() const noexcept;
        [[nodiscard]] std::uint32_t stateUpdates() const noexcept;
        [[nodiscard]] Error lastError() const noexcept;
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        std::uint32_t generation_ = 0U;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /** @brief 원격 Microphone Device의 MICP와 포함 AICS를 제어합니다. */
    class MicrophoneController final
    {
      public:
        MicrophoneController() = default;

        ~MicrophoneController()
        {
            (void)end();
        }

        MicrophoneController(const MicrophoneController &) = delete;
        MicrophoneController &operator=(const MicrophoneController &) = delete;
        MicrophoneController(MicrophoneController &&) = delete;
        MicrophoneController &operator=(MicrophoneController &&) = delete;

        Error begin(const BLEConnectionHandle &connection) noexcept;
        void poll() noexcept;
        Error end() noexcept;
        Error readMicrophone() noexcept;
        Error mute() noexcept;
        Error unmute() noexcept;
        Error readInput() noexcept;
        Error setInputGain(std::int8_t gain) noexcept;
        Error muteInput() noexcept;
        Error unmuteInput() noexcept;
        Error setInputMode(AudioInputMode mode) noexcept;
        Error setInputDescription(const char *description) noexcept;
        [[nodiscard]] bool ready() const noexcept;
        [[nodiscard]] bool busy() const noexcept;
        [[nodiscard]] AudioControlStage stage() const noexcept;
        [[nodiscard]] AudioControlStep lastStep() const noexcept;
        [[nodiscard]] MicrophoneState state() const noexcept;
        [[nodiscard]] AudioInputState inputState() const noexcept;
        [[nodiscard]] std::uint32_t stateUpdates() const noexcept;
        [[nodiscard]] Error lastError() const noexcept;
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        std::uint32_t generation_ = 0U;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /** @brief Common Audio Profile 객체의 공개 비동기 단계입니다. */
    enum class CapStage : std::uint8_t
    {
        idle,
        discovering,
        ready,
        operating,
        streaming,
        stopping,
        failed,
    };

    /** @brief 마지막 CAP Commander 작업을 나타냅니다. */
    enum class CapCommanderStep : std::uint8_t
    {
        none,
        common_audio_service,
        broadcast_assistant,
        select_source,
        start_reception,
        distribute_code,
        stop_reception,
        remove_source,
        cleanup,
    };

    /**
     * @brief CAP 절차로 mono LC3 broadcast stream을 시작합니다.
     *
     * BLEDevice.begin() 뒤 begin()을 호출합니다. 객체는 Common Audio Profile
     * Initiator 절차로 16 kHz, 10 ms, 40-byte LC3 BIS를 만들고 게시합니다.
     */
    class CapInitiator final
    {
      public:
        CapInitiator() = default;

        ~CapInitiator()
        {
            (void)end();
        }

        CapInitiator(const CapInitiator &) = delete;
        CapInitiator &operator=(const CapInitiator &) = delete;
        CapInitiator(CapInitiator &&) = delete;
        CapInitiator &operator=(CapInitiator &&) = delete;

        /** @brief 주어진 방송 이름으로 CAP broadcast를 시작합니다. */
        Error begin(const char *broadcast_name = "NU54-CAP-BROADCAST") noexcept;

        /** @brief 주어진 16-byte code로 암호화한 CAP broadcast를 시작합니다. */
        Error begin(const char *broadcast_name,
                    const BroadcastCode &broadcast_code) noexcept;

        /** @brief CAP broadcast와 광고를 중단하고 자원을 반환합니다. */
        Error end() noexcept;

        /** @brief BIS가 LC3 frame 전송 가능한 상태인지 반환합니다. */
        [[nodiscard]] bool streaming() const noexcept;

        /** @brief BIS로 LC3 frame 하나를 비차단 전송합니다. */
        Error sendFrame(const std::uint8_t (&frame)[40]) noexcept;

        /** @brief 실행 중인 broadcast의 16-bit audio context metadata를 갱신합니다. */
        Error updateContext(std::uint16_t context) noexcept;

        /** @brief 현재 CAP Initiator 단계를 반환합니다. */
        [[nodiscard]] CapStage stage() const noexcept;

        /** @brief controller에 수락된 frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t sentFrames() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 Host/controller 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        friend class PublicAudioBroadcastSource;

        Error start(const char *broadcast_name,
                    const std::uint8_t *broadcast_code) noexcept;
        Error startPublic(const PublicBroadcastSourceConfig &config,
                          const std::uint8_t *broadcast_code) noexcept;
        Error startConfigured(const char *broadcast_name,
                              const char *program_info,
                              const std::uint8_t *broadcast_code,
                              bool public_broadcast) noexcept;
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        CapStage stage_ = CapStage::idle;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /**
     * @brief 이 장치를 Common Audio Profile Acceptor로 준비합니다.
     *
     * 고정 image에 포함된 Common Audio Service 준비 상태를 공개 API로 확인합니다.
     * 실제 audio 역할은 같은 sketch의 BAP server 또는 broadcast sink가 담당합니다.
     */
    class CapAcceptor final
    {
      public:
        CapAcceptor() = default;

        ~CapAcceptor()
        {
            (void)end();
        }

        CapAcceptor(const CapAcceptor &) = delete;
        CapAcceptor &operator=(const CapAcceptor &) = delete;
        CapAcceptor(CapAcceptor &&) = delete;
        CapAcceptor &operator=(CapAcceptor &&) = delete;

        /** @brief 정적으로 등록된 Common Audio Service를 사용할 준비를 마칩니다. */
        Error begin() noexcept;

        /** @brief 공개 객체의 Acceptor 수명을 종료합니다. */
        Error end() noexcept;

        /** @brief Common Audio Service를 검색할 수 있는 상태인지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief 현재 CAP Acceptor 단계를 반환합니다. */
        [[nodiscard]] CapStage stage() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 Host 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        CapStage stage_ = CapStage::idle;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /** @brief Standard Quality 공개 오디오 방송을 송신합니다. */
    class PublicAudioBroadcastSource final
    {
      public:
        PublicAudioBroadcastSource() = default;

        ~PublicAudioBroadcastSource()
        {
            (void)end();
        }

        PublicAudioBroadcastSource(const PublicAudioBroadcastSource &) = delete;
        PublicAudioBroadcastSource &operator=(const PublicAudioBroadcastSource &) = delete;
        PublicAudioBroadcastSource(PublicAudioBroadcastSource &&) = delete;
        PublicAudioBroadcastSource &operator=(PublicAudioBroadcastSource &&) = delete;

        /** @brief 암호화하지 않은 공개 오디오 방송을 시작합니다. */
        Error begin(const PublicBroadcastSourceConfig &config = {}) noexcept;

        /** @brief 16-byte code로 암호화한 공개 오디오 방송을 시작합니다. */
        Error begin(const PublicBroadcastSourceConfig &config,
                    const BroadcastCode &broadcast_code) noexcept;

        /** @brief 방송과 광고를 중단하고 자원을 반환합니다. */
        Error end() noexcept;

        /** @brief BIS가 LC3 frame 전송 가능한 상태인지 반환합니다. */
        [[nodiscard]] bool streaming() const noexcept;

        /** @brief BIS로 Standard Quality LC3 frame 하나를 전송합니다. */
        Error sendFrame(const std::uint8_t (&frame)[40]) noexcept;

        /** @brief 현재 공개 방송 단계를 반환합니다. */
        [[nodiscard]] CapStage stage() const noexcept;

        /** @brief controller에 수락된 frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t sentFrames() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 Host/controller 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        CapInitiator initiator_;
    };

    /** @brief Standard Quality 공개 오디오 방송을 검색하고 수신합니다. */
    class PublicAudioBroadcastSink final
    {
      public:
        PublicAudioBroadcastSink() = default;

        ~PublicAudioBroadcastSink()
        {
            (void)end();
        }

        PublicAudioBroadcastSink(const PublicAudioBroadcastSink &) = delete;
        PublicAudioBroadcastSink &operator=(const PublicAudioBroadcastSink &) = delete;
        PublicAudioBroadcastSink(PublicAudioBroadcastSink &&) = delete;
        PublicAudioBroadcastSink &operator=(PublicAudioBroadcastSink &&) = delete;

        /** @brief 조건에 맞는 암호화하지 않은 공개 방송 검색을 시작합니다. */
        Error begin(const PublicBroadcastFilter &filter = {}) noexcept;

        /** @brief 조건과 16-byte code로 암호화된 공개 방송 검색을 시작합니다. */
        Error begin(const PublicBroadcastFilter &filter,
                    const BroadcastCode &broadcast_code) noexcept;

        /** @brief callback 결과를 다음 동기화 단계로 진행합니다. */
        void poll() noexcept;

        /** @brief BIS와 periodic advertising 동기화를 끊고 자원을 반환합니다. */
        Error end() noexcept;

        /** @brief 조건에 맞아 선택한 공개 방송 정보를 복사합니다. */
        [[nodiscard]] bool selected(PublicBroadcastInfo &info) const noexcept;

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

        /** @brief queue 포화로 폐기한 LC3 frame 수를 반환합니다. */
        [[nodiscard]] std::uint32_t droppedFrames() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 Host/controller 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error start(const PublicBroadcastFilter &filter,
                    const std::uint8_t *broadcast_code) noexcept;

        CapAcceptor acceptor_;
        BroadcastSink sink_;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
        bool started_ = false;
    };

    /**
     * @brief CAP Acceptor의 broadcast 수신 절차를 제어합니다.
     *
     * 연결된 peer의 Common Audio Service와 Broadcast Audio Scan Service를 검색한 뒤,
     * scan 결과로 선택한 source의 수신 시작·code 배포·수신 중단 절차를 실행합니다.
     */
    class CapCommander final
    {
      public:
        CapCommander() = default;

        ~CapCommander()
        {
            (void)end();
        }

        CapCommander(const CapCommander &) = delete;
        CapCommander &operator=(const CapCommander &) = delete;
        CapCommander(CapCommander &&) = delete;
        CapCommander &operator=(CapCommander &&) = delete;

        /** @brief 연결된 Acceptor의 CAS와 BASS를 차례로 검색합니다. */
        Error begin(const BLEConnectionHandle &connection) noexcept;

        /** @brief Broadcast Audio announcement가 든 scan 결과를 선택합니다. */
        Error selectSource(const BLEScanResult &result) noexcept;

        /** @brief 선택한 source의 PA와 BIS 1 수신 시작을 요청합니다. */
        Error startReception() noexcept;

        /** @brief 현재 source에 16-byte Broadcast Code를 배포합니다. */
        Error distributeBroadcastCode(const BroadcastCode &broadcast_code) noexcept;

        /** @brief 현재 source의 PA와 BIS 수신 중단을 요청합니다. */
        Error stopReception() noexcept;

        /** @brief 중단된 receive state source를 Acceptor에서 제거합니다. */
        Error removeSource() noexcept;

        /** @brief callback과 연결 참조를 반환합니다. */
        Error end() noexcept;

        /** @brief 현재 CAP Commander 단계를 반환합니다. */
        [[nodiscard]] CapStage stage() const noexcept;

        /** @brief 마지막 CAP Commander 작업을 반환합니다. */
        [[nodiscard]] CapCommanderStep lastStep() const noexcept;

        /** @brief CAS와 BASS 검색이 모두 완료되었는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief 유효한 receive state source가 있는지 반환합니다. */
        [[nodiscard]] bool hasSource() const noexcept;

        /** @brief 마지막 receive state source ID를 반환합니다. */
        [[nodiscard]] std::uint8_t sourceId() const noexcept;

        /** @brief 마지막 receive state가 PA synchronized인지 반환합니다. */
        [[nodiscard]] bool periodicSynchronized() const noexcept;

        /** @brief 마지막 receive state가 BIS 1 synchronized인지 반환합니다. */
        [[nodiscard]] bool bisSynchronized() const noexcept;

        /** @brief 수신한 receive state 통지 수를 반환합니다. */
        [[nodiscard]] std::uint32_t stateUpdates() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 CAP/BASS/GATT 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        CapStage stage_ = CapStage::idle;
        CapCommanderStep last_step_ = CapCommanderStep::none;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /** @brief Coordinated Set을 식별하는 16-byte 비밀 키입니다. */
    struct CsipSetKey
    {
        std::uint8_t bytes[16] = {};
    };

    /** @brief Set Member service의 공개 설정입니다. */
    struct CsipMemberConfig
    {
        CsipSetKey key;
        std::uint8_t set_size = 2U;
        std::uint8_t rank = 1U;
        bool lockable = true;
    };

    /** @brief 한 Coordinated Set member에서 확인한 속성입니다. */
    struct CsipMemberInfo
    {
        std::uint8_t set_size = 0U;
        std::uint8_t rank = 0U;
        bool lockable = false;
        bool locked = false;
    };

    /** @brief Set Coordinator 비동기 절차의 현재 단계입니다. */
    enum class CsipStage : std::uint8_t
    {
        idle,
        discovering,
        ready,
        operating,
        locked,
        failed,
    };

    /** @brief 마지막 Set Coordinator 절차입니다. */
    enum class CsipStep : std::uint8_t
    {
        none,
        discover,
        ordered_access,
        lock,
        release,
        cleanup,
    };

    /** @brief CSIS service와 RSI를 제공하는 Coordinated Set Member입니다. */
    class CsipSetMember final
    {
      public:
        CsipSetMember() = default;

        ~CsipSetMember()
        {
            (void)end();
        }

        CsipSetMember(const CsipSetMember &) = delete;
        CsipSetMember &operator=(const CsipSetMember &) = delete;
        CsipSetMember(CsipSetMember &&) = delete;
        CsipSetMember &operator=(CsipSetMember &&) = delete;

        /** @brief CSIS service를 주어진 key·size·rank로 등록합니다. */
        Error begin(const CsipMemberConfig &configuration) noexcept;

        /** @brief 등록한 CSIS service를 해제합니다. */
        Error end() noexcept;

        /** @brief 광고에 넣을 6-byte RSI를 새로 생성합니다. */
        Error generateRsi(std::uint8_t (&rsi)[6]) noexcept;

        /** @brief 등록된 service의 SIRK를 변경합니다. */
        Error setKey(const CsipSetKey &key) noexcept;

        /** @brief size 변경과 함께 rank를 원자적으로 갱신합니다. */
        Error setSizeAndRank(std::uint8_t set_size, std::uint8_t rank) noexcept;

        /** @brief 잠금 소유자와 무관하게 local CSIS 잠금을 해제합니다. */
        Error forceRelease() noexcept;

        /** @brief 현재 service 속성을 caller 복사본으로 반환합니다. */
        Error info(CsipMemberInfo &information) const noexcept;

        /** @brief CSIS service가 등록됐는지 반환합니다. */
        [[nodiscard]] bool active() const noexcept;

        /** @brief 마지막으로 확인한 잠금 상태를 반환합니다. */
        [[nodiscard]] bool locked() const noexcept;

        /** @brief service 수명 동안 관찰한 잠금 변경 수를 반환합니다. */
        [[nodiscard]] std::uint32_t lockChanges() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 CSIS 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;
    };

    /** @brief 최대 두 bonded peer의 Coordinated Set을 검색하고 잠급니다. */
    class CsipSetCoordinator final
    {
      public:
        static constexpr std::size_t maximum_members = 2U;

        CsipSetCoordinator() = default;

        ~CsipSetCoordinator()
        {
            (void)end();
        }

        CsipSetCoordinator(const CsipSetCoordinator &) = delete;
        CsipSetCoordinator &operator=(const CsipSetCoordinator &) = delete;
        CsipSetCoordinator(CsipSetCoordinator &&) = delete;
        CsipSetCoordinator &operator=(CsipSetCoordinator &&) = delete;

        /** @brief 검색할 key와 필요한 member 수를 설정합니다. */
        Error begin(const CsipSetKey &key, std::uint8_t expected_members = 2U) noexcept;

        /** @brief 활성 연결과 검색 결과를 버리고 객체 소유권을 반환합니다. */
        Error end() noexcept;

        /** @brief scan 결과의 RSI가 설정된 key와 일치하는지 확인합니다. */
        [[nodiscard]] bool matches(const BLEScanResult &result) const noexcept;

        /** @brief 지정 연결에서 CSIS service와 set 속성을 비동기 검색합니다. */
        Error discover(const BLEConnectionHandle &connection) noexcept;

        /** @brief 끊긴 exact handle을 제거하고 재검색 가능한 상태로 갱신합니다. */
        void poll() noexcept;

        /** @brief 모든 member의 lock 상태를 읽고 rank 순서를 준비합니다. */
        Error prepareOrderedAccess() noexcept;

        /** @brief bonded member를 낮은 rank부터 잠급니다. */
        Error lock() noexcept;

        /** @brief 잠긴 member를 높은 rank부터 해제합니다. */
        Error release() noexcept;

        /** @brief 현재 발견된 member 수를 반환합니다. */
        [[nodiscard]] std::size_t memberCount() const noexcept;

        /** @brief 발견된 member의 속성을 caller 복사본으로 반환합니다. */
        Error member(std::size_t index, CsipMemberInfo &information) const noexcept;

        /** @brief 마지막 ordered access에서 rank 순으로 정렬된 연결을 반환합니다. */
        [[nodiscard]] BLEConnectionHandle orderedMember(std::size_t index) const noexcept;

        /** @brief 필요한 member를 모두 검색했는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief set 전체 잠금 완료 여부를 반환합니다. */
        [[nodiscard]] bool locked() const noexcept;

        /** @brief 현재 coordinator 단계를 반환합니다. */
        [[nodiscard]] CsipStage stage() const noexcept;

        /** @brief 마지막 coordinator 절차를 반환합니다. */
        [[nodiscard]] CsipStep lastStep() const noexcept;

        /** @brief peer가 보낸 lock 상태 변경 수를 반환합니다. */
        [[nodiscard]] std::uint32_t lockChanges() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 CSIP/GATT 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;
    };
} // namespace nucode::ble::audio

#endif
