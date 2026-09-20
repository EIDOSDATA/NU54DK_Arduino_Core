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
} // namespace nucode::ble

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
        Error start(const char *broadcast_name, const std::uint8_t *broadcast_code) noexcept;
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /**
     * @brief BAP broadcast source를 찾고 mono LC3 frame을 수신합니다.
     *
     * BLEDevice.begin() 뒤 begin()을 호출하고 loop()에서 poll()을 반복합니다.
     * 광고 이름이 일치하는 source의 periodic advertising과 지원 codec BIS에 동기화하며,
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

        Error start(const char *broadcast_name, const std::uint8_t *broadcast_code) noexcept;
        Error startPublic(const PublicBroadcastFilter &filter,
                          const std::uint8_t *broadcast_code) noexcept;
        Error startConfigured(const char *broadcast_name, const std::uint8_t *broadcast_code,
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

    /** @brief 포함할 Volume Offset Control Service의 초기 설정입니다. 설명은 UTF-8 31바이트 이하입니다. */
    struct VolumeOffsetConfig
    {
        std::int16_t offset = 0;
        std::uint32_t location = 0U;
        bool location_writable = true;
        bool description_writable = true;
        const char *description = "Speaker";
    };

    /** @brief 포함할 Audio Input Control Service의 초기 설정입니다. 설명은 UTF-8 31바이트 이하입니다. */
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
     * 다시 begin()할 때 instance 수·gain 범위·쓰기 권한 같은 immutable 설정은 최초값과
     * 같아야 하며, mutable 설정은 실제 service에 다시 적용됩니다.
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

        /** @brief 포함된 output 설명을 UTF-8 31바이트 이하로 설정합니다. */
        Error setOutputDescription(const char *description) noexcept;

        /** @brief 포함된 input gain을 설정합니다. */
        Error setInputGain(std::int8_t gain) noexcept;

        /** @brief 포함된 input을 mute합니다. */
        Error muteInput() noexcept;

        /** @brief 포함된 input을 unmute합니다. */
        Error unmuteInput() noexcept;

        /** @brief 포함된 input gain mode를 설정합니다. */
        Error setInputMode(AudioInputMode mode) noexcept;

        /** @brief 포함된 input 설명을 UTF-8 31바이트 이하로 설정합니다. */
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

    /**
     * @brief 원격 Volume Renderer의 VCP·VOCS·AICS를 제어합니다.
     *
     * snapshot getter의 값은 ready()가 true가 된 뒤 유효합니다. begin()은 discovery 뒤
     * 원격 VCS·VOCS·AICS의 실제 상태와 설정을 모두 읽은 다음 ready 상태가 됩니다.
     */
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

        /** @brief 원격 volume과 mute 상태를 다시 읽습니다. */
        Error readVolume() noexcept;

        /** @brief 원격 volume을 절대값으로 설정합니다. */
        Error setVolume(std::uint8_t volume) noexcept;

        /** @brief 원격 volume을 한 step 올립니다. */
        Error volumeUp() noexcept;

        /** @brief 원격 volume을 한 step 내립니다. */
        Error volumeDown() noexcept;

        /** @brief 원격 volume 출력을 mute합니다. */
        Error mute() noexcept;

        /** @brief 원격 volume 출력을 unmute합니다. */
        Error unmute() noexcept;

        /** @brief 원격 output offset을 다시 읽습니다. */
        Error readOffset() noexcept;

        /** @brief 원격 output offset을 설정합니다. */
        Error setOffset(std::int16_t offset) noexcept;

        /** @brief 원격 output audio location을 설정합니다. */
        Error setOutputLocation(std::uint32_t location) noexcept;

        /** @brief 원격 output 설명을 UTF-8 31바이트 이하로 설정합니다. */
        Error setOutputDescription(const char *description) noexcept;

        /** @brief 원격 input gain·mute·mode를 다시 읽습니다. */
        Error readInput() noexcept;

        /** @brief 원격 input gain을 검색된 범위 안에서 설정합니다. */
        Error setInputGain(std::int8_t gain) noexcept;

        /** @brief 원격 input을 mute합니다. */
        Error muteInput() noexcept;

        /** @brief 원격 input을 unmute합니다. */
        Error unmuteInput() noexcept;

        /** @brief 원격 input gain mode를 manual 또는 automatic으로 설정합니다. */
        Error setInputMode(AudioInputMode mode) noexcept;

        /**
         * @brief 잠긴 SDK가 AICS client busy를 복구하지 못하므로 unsupported를 반환합니다.
         */
        Error setInputDescription(const char *description) noexcept;

        /** @brief discovery와 실제 상태 bootstrap read가 모두 끝났는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief discovery 또는 한 비동기 요청이 진행 중인지 반환합니다. */
        [[nodiscard]] bool busy() const noexcept;

        /** @brief 현재 discovery·ready·operation·failure 단계를 반환합니다. */
        [[nodiscard]] AudioControlStage stage() const noexcept;

        /** @brief 마지막으로 시작한 공개 작업을 반환합니다. */
        [[nodiscard]] AudioControlStep lastStep() const noexcept;

        /** @brief 마지막으로 읽거나 통지받은 원격 volume 상태를 반환합니다. */
        [[nodiscard]] VolumeState state() const noexcept;

        /** @brief 마지막으로 읽거나 통지받은 원격 output 상태를 반환합니다. */
        [[nodiscard]] VolumeOffsetState offsetState() const noexcept;

        /** @brief 마지막으로 읽거나 통지받은 원격 input 상태를 반환합니다. */
        [[nodiscard]] AudioInputState inputState() const noexcept;

        /** @brief 현재 session에서 수락한 상태 callback 수를 반환합니다. */
        [[nodiscard]] std::uint32_t stateUpdates() const noexcept;

        /** @brief 마지막 공개 오류 또는 비동기 profile 오류를 반환합니다. */
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

    /**
     * @brief microphone mute와 포함 audio input을 제공하는 Microphone Device입니다.
     *
     * service는 image 수명 동안 유지됩니다. 다시 begin()할 때 gain 범위·입력 형식·쓰기
     * 권한은 최초값과 같아야 하며, mutable 설정은 실제 service에 다시 적용됩니다.
     */
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

        /** @brief Microphone Device와 포함 AICS 한 개를 준비합니다. */
        Error begin(const MicrophoneDeviceConfig &config = {}) noexcept;

        /** @brief image-lifetime service를 유지하고 facade 소유권만 반환합니다. */
        Error end() noexcept;

        /** @brief microphone을 mute합니다. */
        Error mute() noexcept;

        /** @brief microphone을 unmute합니다. */
        Error unmute() noexcept;

        /** @brief 이 image 수명 동안 microphone mute 변경을 비활성화합니다. */
        Error disableMute() noexcept;

        /** @brief 포함된 input gain을 설정합니다. */
        Error setInputGain(std::int8_t gain) noexcept;

        /** @brief 포함된 input을 mute합니다. */
        Error muteInput() noexcept;

        /** @brief 포함된 input을 unmute합니다. */
        Error unmuteInput() noexcept;

        /** @brief 포함된 input gain mode를 설정합니다. */
        Error setInputMode(AudioInputMode mode) noexcept;

        /** @brief 포함된 input 설명을 UTF-8 31바이트 이하로 설정합니다. */
        Error setInputDescription(const char *description) noexcept;

        /** @brief service와 facade가 준비되었는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief 마지막으로 관찰한 microphone 상태를 반환합니다. */
        [[nodiscard]] MicrophoneState state() const noexcept;

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

    /**
     * @brief 원격 Microphone Device의 MICP와 포함 AICS를 제어합니다.
     *
     * snapshot getter의 값은 ready()가 true가 된 뒤 유효합니다. begin()은 discovery 뒤
     * 원격 MICS·AICS의 실제 상태와 설정을 모두 읽은 다음 ready 상태가 됩니다.
     */
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

        /** @brief 연결된 peer에서 MICP와 포함 AICS를 검색합니다. */
        Error begin(const BLEConnectionHandle &connection) noexcept;

        /** @brief 연결 소실과 callback 결과를 공개 상태에 반영합니다. */
        void poll() noexcept;

        /** @brief 연결 참조와 facade 소유권을 반환합니다. */
        Error end() noexcept;

        /** @brief 원격 microphone mute 상태를 다시 읽습니다. */
        Error readMicrophone() noexcept;

        /** @brief 원격 microphone을 mute합니다. */
        Error mute() noexcept;

        /** @brief 원격 microphone을 unmute합니다. */
        Error unmute() noexcept;

        /** @brief 원격 input gain·mute·mode를 다시 읽습니다. */
        Error readInput() noexcept;

        /** @brief 원격 input gain을 검색된 범위 안에서 설정합니다. */
        Error setInputGain(std::int8_t gain) noexcept;

        /** @brief 원격 input을 mute합니다. */
        Error muteInput() noexcept;

        /** @brief 원격 input을 unmute합니다. */
        Error unmuteInput() noexcept;

        /** @brief 원격 input gain mode를 manual 또는 automatic으로 설정합니다. */
        Error setInputMode(AudioInputMode mode) noexcept;

        /**
         * @brief 잠긴 SDK가 AICS client busy를 복구하지 못하므로 unsupported를 반환합니다.
         */
        Error setInputDescription(const char *description) noexcept;

        /** @brief discovery와 실제 상태 bootstrap read가 모두 끝났는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief discovery 또는 한 비동기 요청이 진행 중인지 반환합니다. */
        [[nodiscard]] bool busy() const noexcept;

        /** @brief 현재 discovery·ready·operation·failure 단계를 반환합니다. */
        [[nodiscard]] AudioControlStage stage() const noexcept;

        /** @brief 마지막으로 시작한 공개 작업을 반환합니다. */
        [[nodiscard]] AudioControlStep lastStep() const noexcept;

        /** @brief 마지막으로 읽거나 통지받은 원격 microphone 상태를 반환합니다. */
        [[nodiscard]] MicrophoneState state() const noexcept;

        /** @brief 마지막으로 읽거나 통지받은 원격 input 상태를 반환합니다. */
        [[nodiscard]] AudioInputState inputState() const noexcept;

        /** @brief 현재 session에서 수락한 상태 callback 수를 반환합니다. */
        [[nodiscard]] std::uint32_t stateUpdates() const noexcept;

        /** @brief 마지막 공개 오류 또는 비동기 profile 오류를 반환합니다. */
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
        Error begin(const char *broadcast_name, const BroadcastCode &broadcast_code) noexcept;

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

        Error start(const char *broadcast_name, const std::uint8_t *broadcast_code) noexcept;
        Error startPublic(const PublicBroadcastSourceConfig &config,
                          const std::uint8_t *broadcast_code) noexcept;
        Error startConfigured(const char *broadcast_name, const char *program_info,
                              const std::uint8_t *broadcast_code, bool public_broadcast) noexcept;
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
        bool acceptor_started_ = false;
        bool sink_started_ = false;
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
            if (end() != Error::none)
            {
                abandon();
            }
        }

        CsipSetMember(const CsipSetMember &) = delete;
        CsipSetMember &operator=(const CsipSetMember &) = delete;
        CsipSetMember(CsipSetMember &&) = delete;
        CsipSetMember &operator=(CsipSetMember &&) = delete;

        /**
         * @brief CSIS service를 주어진 key·size·rank로 등록합니다.
         * @note lockable service는 rank 1..size, non-lockable service는 rank 0만 허용합니다.
         * @note 첫 등록 뒤 service instance는 image 수명 동안 유지됩니다.
         * @note end 뒤 재시작은 이전 lock timeout과의 경합을 막기 위해 재부팅 전까지 unsupported입니다.
         */
        Error begin(const CsipMemberConfig &configuration) noexcept;

        /** @brief 공개 소유권과 승인을 영구 해제하고 image-lifetime service를 휴면 상태로 둡니다. */
        Error end() noexcept;

        /** @brief 광고에 넣을 6-byte RSI를 새로 생성합니다. */
        Error generateRsi(std::uint8_t (&rsi)[6]) noexcept;

        /** @brief 연결에서 확인한 bonded identity의 encrypted SIRK 읽기 권한을 설정합니다. */
        Error authorizeSirkRead(const BLEConnectionHandle &connection,
                                bool authorized = true) noexcept;

        /** @brief 등록된 service의 SIRK를 변경합니다. */
        Error setKey(const CsipSetKey &key) noexcept;

        /**
         * @brief size 변경과 함께 rank를 원자적으로 갱신합니다.
         * @note 고정 SDK 제약으로 size가 같은 rank-only 변경은 unsupported입니다.
         * @note 현재 service가 non-lockable이면 rank는 0이어야 합니다.
         */
        Error setSizeAndRank(std::uint8_t set_size, std::uint8_t rank) noexcept;

        /** @brief 잠금 소유자와 무관하게 local CSIS 잠금을 해제합니다. */
        Error forceRelease() noexcept;

        /** @brief 현재 service 속성을 caller 복사본으로 반환합니다. */
        Error info(CsipMemberInfo &information) const noexcept;

        /** @brief 현재 facade가 image-lifetime CSIS service를 소유하는지 반환합니다. */
        [[nodiscard]] bool active() const noexcept;

        /** @brief 마지막으로 확인한 잠금 상태를 반환합니다. */
        [[nodiscard]] bool locked() const noexcept;

        /** @brief service 수명 동안 관찰한 잠금 변경 수를 반환합니다. */
        [[nodiscard]] std::uint32_t lockChanges() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 CSIS 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        /** @brief end 실패 시 callback owner를 안전하게 격리합니다. */
        void abandon() noexcept;
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

        /**
         * @brief 활성 연결과 검색 결과를 버리고 객체 소유권을 반환합니다.
         * @return 잠금 해제 또는 cleanup이 진행 중이면 busy이며 poll 뒤 다시 호출해야 합니다.
         * @note cleanup은 시작 뒤 최대 120초로 제한되며 객체는 end 성공까지 살아 있어야 합니다.
         */
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

    /** @brief Hearing Access Service가 게시하는 보청기 형식입니다. */
    enum class HearingAidType : std::uint8_t
    {
        binaural,
        monaural,
        banded,
    };

    /** @brief Hearing Access client 비동기 절차의 현재 단계입니다. */
    enum class HearingAccessStage : std::uint8_t
    {
        idle,
        discovering,
        ready,
        operating,
        disconnected,
        failed,
    };

    /** @brief 마지막 Hearing Access client 절차입니다. */
    enum class HearingAccessStep : std::uint8_t
    {
        none,
        discover,
        read_presets,
        set_active,
        next,
        previous,
        cleanup,
    };

    /** @brief 하나의 Hearing Access preset을 caller 소유 메모리로 표현합니다. */
    struct HearingPreset
    {
        static constexpr std::size_t maximum_name_bytes = 40U;

        std::uint8_t index = 0U;
        bool available = false;
        bool writable = false;
        char name[maximum_name_bytes + 1U] = {};
    };

    /** @brief Hearing Access server의 고정 service 설정입니다. */
    struct HearingAccessServerConfig
    {
        HearingAidType type = HearingAidType::monaural;
        bool preset_synchronization = false;
        bool independent_presets = false;
    };

    /** @brief HAS와 preset database를 제공하는 Hearing Access server입니다. */
    class HearingAccessServer final
    {
      public:
        HearingAccessServer() = default;

        ~HearingAccessServer()
        {
            (void)end();
        }

        HearingAccessServer(const HearingAccessServer &) = delete;
        HearingAccessServer &operator=(const HearingAccessServer &) = delete;
        HearingAccessServer(HearingAccessServer &&) = delete;
        HearingAccessServer &operator=(HearingAccessServer &&) = delete;

        /** @brief 광고 전에 HAS service를 등록하고 이 객체가 소유하게 합니다. */
        Error begin(const HearingAccessServerConfig &config = {}) noexcept;

        /** @brief 등록한 preset을 해제하고 공개 소유권을 반환합니다. */
        Error end() noexcept;

        /** @brief 고유 index와 이름을 가진 preset을 추가합니다. */
        Error addPreset(std::uint8_t index, const char *name, bool writable = true,
                        bool available = true) noexcept;

        /** @brief local preset을 활성화하고 연결된 client에 알립니다. */
        Error setActivePreset(std::uint8_t index) noexcept;

        /** @brief preset 선택 가능 상태를 변경하고 연결된 client에 알립니다. */
        Error setPresetAvailable(std::uint8_t index, bool available) noexcept;

        /** @brief writable preset의 이름을 변경하고 연결된 client에 알립니다. */
        Error renamePreset(std::uint8_t index, const char *name) noexcept;

        /** @brief 현재 활성 preset index를 반환하며 없으면 0을 반환합니다. */
        [[nodiscard]] std::uint8_t activePreset() const noexcept;

        /** @brief 현재 등록된 preset 수를 반환합니다. */
        [[nodiscard]] std::size_t presetCount() const noexcept;

        /** @brief 위치 순서의 preset을 caller 복사본으로 반환합니다. */
        Error preset(std::size_t position, HearingPreset &value) const noexcept;

        /** @brief local 또는 원격 선택 요청으로 바뀐 횟수를 반환합니다. */
        [[nodiscard]] std::uint32_t selectionChanges() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 HAS 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /** @brief 원격 HAS를 검색하고 preset을 읽고 선택하는 Hearing Access client입니다. */
    class HearingAccessClient final
    {
      public:
        HearingAccessClient() = default;

        ~HearingAccessClient()
        {
            (void)end();
        }

        HearingAccessClient(const HearingAccessClient &) = delete;
        HearingAccessClient &operator=(const HearingAccessClient &) = delete;
        HearingAccessClient(HearingAccessClient &&) = delete;
        HearingAccessClient &operator=(HearingAccessClient &&) = delete;

        /** @brief 암호화된 연결에서 HAS 검색을 시작합니다. */
        Error begin(const BLEConnectionHandle &connection) noexcept;

        /** @brief 연결 해제와 callback 결과를 Arduino 문맥에서 반영합니다. */
        void poll() noexcept;

        /** @brief 연결 참조와 검색 결과를 반환합니다. */
        Error end() noexcept;

        /** @brief 지정 index부터 bounded preset 목록을 비동기로 읽습니다. */
        Error readPresets(std::uint8_t start_index = 1U,
                          std::uint8_t maximum_count = 0xffU) noexcept;

        /** @brief 지정 preset을 활성화하도록 요청합니다. */
        Error setActivePreset(std::uint8_t index, bool synchronize = false) noexcept;

        /** @brief 다음 사용 가능한 preset을 활성화하도록 요청합니다. */
        Error nextPreset(bool synchronize = false) noexcept;

        /** @brief 이전 사용 가능한 preset을 활성화하도록 요청합니다. */
        Error previousPreset(bool synchronize = false) noexcept;

        /** @brief HAS 검색과 subscription이 완료됐는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief 비동기 요청이 callback을 기다리는지 반환합니다. */
        [[nodiscard]] bool busy() const noexcept;

        /** @brief 현재 client 단계를 반환합니다. */
        [[nodiscard]] HearingAccessStage stage() const noexcept;

        /** @brief 마지막 client 절차를 반환합니다. */
        [[nodiscard]] HearingAccessStep lastStep() const noexcept;

        /** @brief 원격 장치가 보고한 활성 preset index를 반환합니다. */
        [[nodiscard]] std::uint8_t activePreset() const noexcept;

        /** @brief 마지막 read에서 복사한 preset 수를 반환합니다. */
        [[nodiscard]] std::size_t presetCount() const noexcept;

        /** @brief 위치 순서의 원격 preset을 caller 복사본으로 반환합니다. */
        Error preset(std::size_t position, HearingPreset &value) const noexcept;

        /** @brief discovery·preset 알림으로 갱신된 횟수를 반환합니다. */
        [[nodiscard]] std::uint32_t stateUpdates() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 HAS/GATT 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        std::uint32_t generation_ = 0U;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };
    /** @brief Media Control Service가 보고하는 재생 상태입니다. */
    enum class MediaState : std::uint8_t
    {
        inactive,
        playing,
        paused,
        seeking,
    };

    /** @brief Media Control Point에 전달할 사용자 명령입니다. */
    enum class MediaCommand : std::uint8_t
    {
        play,
        pause,
        fast_rewind,
        fast_forward,
        stop,
        previous_track,
        next_track,
    };

    /** @brief media/call client가 공유하는 비동기 검색 단계입니다. */
    enum class RemoteControlStage : std::uint8_t
    {
        idle,
        discovering,
        reading,
        ready,
        operating,
        failed,
    };

    /** @brief 원격 Media Control Service에서 읽은 고정 크기 snapshot입니다. */
    struct MediaSnapshot
    {
        char player_name[32] = {};
        char track_title[48] = {};
        std::int32_t track_duration = 0;
        std::int32_t track_position = 0;
        std::uint64_t current_track_id = 0U;
        std::uint32_t supported_commands = 0U;
        std::uint32_t updates = 0U;
        std::uint32_t state_notifications = 0U;
        std::uint8_t content_control_id = 0U;
        MediaState state = MediaState::inactive;
    };

    /**
     * @brief 고정 SDK의 합성 media player와 Media Control Service를 제공합니다.
     *
     * @note player와 service는 image 수명 자원입니다. end() 뒤 같은 image에서 재등록하지 않습니다.
     */
    class MediaControlPlayer final
    {
      public:
        MediaControlPlayer() = default;

        ~MediaControlPlayer()
        {
            (void)end();
        }

        MediaControlPlayer(const MediaControlPlayer &) = delete;
        MediaControlPlayer &operator=(const MediaControlPlayer &) = delete;

        /** @brief 합성 track/object와 MCS를 등록합니다. */
        Error begin() noexcept;

        /** @brief 공개 소유권을 해제하고 image-lifetime service를 휴면 상태로 둡니다. */
        Error end() noexcept;

        /** @brief MCS가 원격 controller 요청을 받을 준비가 되었는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 Media Proxy 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /** @brief 원격 Media Control Service를 검색하고 track과 재생 상태를 제어합니다. */
    class MediaControlClient final
    {
      public:
        MediaControlClient() = default;

        ~MediaControlClient()
        {
            (void)end();
        }

        MediaControlClient(const MediaControlClient &) = delete;
        MediaControlClient &operator=(const MediaControlClient &) = delete;

        /** @brief 암호화된 연결에서 MCS 검색과 상태 구독을 시작합니다. */
        Error begin(const BLEConnectionHandle &connection) noexcept;

        /** @brief callback 결과에 따라 다음 특성 읽기를 진행합니다. */
        void poll() noexcept;

        /** @brief 원격 player 상태를 처음부터 다시 읽습니다. */
        Error refresh() noexcept;

        /** @brief 지원되는 Media Control Point 명령을 보냅니다. */
        Error command(MediaCommand command) noexcept;

        /** @brief 확장 또는 negative 검증용 Media Control Point opcode를 보냅니다. */
        Error commandOpcode(std::uint8_t opcode) noexcept;

        /** @brief 현재 track 안에서 상대 위치 이동 명령을 보냅니다. */
        Error moveRelative(std::int32_t hundredths) noexcept;

        /** @brief 현재 track 위치를 1/100초 단위로 설정합니다. */
        Error setTrackPosition(std::int32_t hundredths) noexcept;

        /**
         * @brief 가장 최근 원격 읽기·통지로 관찰한 48-bit track object를 선택합니다.
         *
         * @note 고정 SDK가 존재하지 않는 object도 성공으로 응답하므로 미관찰 ID는 전송 전에
         *       거부합니다.
         */
        Error selectTrack(std::uint64_t object_id) noexcept;

        /** @brief 연결 참조와 비동기 작업을 반환합니다. */
        Error end() noexcept;

        /** @brief 검색과 초기 snapshot 읽기가 완료되었는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief 현재 비동기 단계를 반환합니다. */
        [[nodiscard]] RemoteControlStage stage() const noexcept;

        /** @brief 마지막 원격 snapshot 복사본을 반환합니다. */
        [[nodiscard]] MediaSnapshot snapshot() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 MCC/GATT 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        std::uint32_t generation_ = 0U;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /** @brief Telephone Bearer Service가 보고하는 통화 상태입니다. */
    enum class CallState : std::uint8_t
    {
        none,
        incoming,
        dialing,
        alerting,
        active,
        locally_held,
        remotely_held,
        locally_and_remotely_held,
    };

    /** @brief 마지막으로 관찰한 합성 통화 상태입니다. */
    struct CallSnapshot
    {
        std::uint32_t updates = 0U;
        std::uint32_t state_notifications = 0U;
        std::uint8_t call_index = 0U;
        std::uint8_t result_code = 0U;
        CallState state = CallState::none;
    };

    /** @brief 합성 통화와 Generic Telephone Bearer Service를 제공합니다. */
    class CallControlServer final
    {
      public:
        CallControlServer() = default;

        ~CallControlServer()
        {
            (void)end();
        }

        CallControlServer(const CallControlServer &) = delete;
        CallControlServer &operator=(const CallControlServer &) = delete;

        /** @brief GTBS를 등록합니다. */
        Error begin(const char *provider_name = "NUCODE Call",
                    const char *uri_schemes = "tel") noexcept;

        /** @brief 원격 caller가 시작한 합성 incoming call을 게시합니다. */
        Error incoming(const char *to, const char *from, const char *friendly_name) noexcept;

        /** @brief 현재 outgoing call이 원격에서 응답됐음을 게시합니다. */
        Error remoteAnswer(std::uint8_t call_index) noexcept;

        /** @brief 원격 party의 hold 상태를 게시합니다. */
        Error remoteHold(std::uint8_t call_index) noexcept;

        /** @brief 원격 party가 hold를 해제했음을 게시합니다. */
        Error remoteRetrieve(std::uint8_t call_index) noexcept;

        /** @brief 원격 party가 통화를 끝냈음을 게시합니다. */
        Error remoteTerminate(std::uint8_t call_index) noexcept;

        /** @brief GTBS service를 등록 해제하고 자원을 반환합니다. */
        Error end() noexcept;

        /** @brief GTBS가 등록됐는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief 마지막 server 통화 상태를 반환합니다. */
        [[nodiscard]] CallSnapshot snapshot() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 TBS 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };

    /** @brief 원격 Generic Telephone Bearer Service를 검색하고 통화를 제어합니다. */
    class CallControlClient final
    {
      public:
        CallControlClient() = default;

        ~CallControlClient()
        {
            (void)end();
        }

        CallControlClient(const CallControlClient &) = delete;
        CallControlClient &operator=(const CallControlClient &) = delete;

        /** @brief 암호화된 연결에서 GTBS/TBS 검색과 상태 구독을 시작합니다. */
        Error begin(const BLEConnectionHandle &connection) noexcept;

        /** @brief 완료 callback 뒤 필요한 상태 재읽기를 진행합니다. */
        void poll() noexcept;

        /** @brief 원격 call-state characteristic를 다시 읽습니다. */
        Error refresh() noexcept;

        /** @brief 새 outgoing call을 요청합니다. */
        Error originate(const char *uri) noexcept;

        /** @brief incoming call 수락을 요청합니다. */
        Error accept(std::uint8_t call_index) noexcept;

        /** @brief active call hold를 요청합니다. */
        Error hold(std::uint8_t call_index) noexcept;

        /** @brief held call 복귀를 요청합니다. */
        Error retrieve(std::uint8_t call_index) noexcept;

        /** @brief 지정 call 종료를 요청합니다. */
        Error terminate(std::uint8_t call_index) noexcept;

        /** @brief 연결 참조와 비동기 작업을 반환합니다. */
        Error end() noexcept;

        /** @brief GTBS discovery가 완료됐는지 반환합니다. */
        [[nodiscard]] bool ready() const noexcept;

        /** @brief 현재 비동기 단계를 반환합니다. */
        [[nodiscard]] RemoteControlStage stage() const noexcept;

        /** @brief 마지막 client 통화 상태를 반환합니다. */
        [[nodiscard]] CallSnapshot snapshot() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 TBS client/GATT 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;

      private:
        Error record(Error error, int native_code = 0) noexcept;

        bool started_ = false;
        std::uint32_t generation_ = 0U;
        Error last_error_ = Error::not_started;
        int native_code_ = 0;
    };
    /** @brief TMAP Role characteristic의 공개 역할 bit입니다. */
    enum class TelephonyMediaRole : std::uint16_t
    {
        call_gateway = 1U << 0U,
        call_terminal = 1U << 1U,
        unicast_media_sender = 1U << 2U,
        unicast_media_receiver = 1U << 3U,
        broadcast_media_sender = 1U << 4U,
        broadcast_media_receiver = 1U << 5U,
    };

    /** @brief 여러 TMAP 역할을 하나의 안전한 bit set으로 결합합니다. */
    constexpr TelephonyMediaRole operator|(TelephonyMediaRole left,
                                           TelephonyMediaRole right) noexcept
    {
        return static_cast<TelephonyMediaRole>(static_cast<std::uint16_t>(left) |
                                               static_cast<std::uint16_t>(right));
    }

    /** @brief TMAP service 등록과 peer 역할 검색 단계를 나타냅니다. */
    enum class TelephonyMediaStage : std::uint8_t
    {
        idle,
        ready,
        discovering,
        discovered,
        failed,
    };

    /**
     * @brief TMAP 역할을 게시하고 연결된 peer의 역할 조합을 검색합니다.
     *
     * 역할별 PACS/ASCS, VCP, MCP 또는 CCP service는 선택한 Arduino profile의
     * Kconfig와 해당 공개 facade가 소유합니다. 이 객체는 실제 TMAS Role
     * characteristic만 등록·검색하며 지원되지 않는 역할 조합을 fail-closed로 거부합니다.
     */
    class TelephonyMediaRoles final
    {
      public:
        TelephonyMediaRoles() = default;

        ~TelephonyMediaRoles()
        {
            (void)end();
        }

        TelephonyMediaRoles(const TelephonyMediaRoles &) = delete;
        TelephonyMediaRoles &operator=(const TelephonyMediaRoles &) = delete;
        TelephonyMediaRoles(TelephonyMediaRoles &&) = delete;
        TelephonyMediaRoles &operator=(TelephonyMediaRoles &&) = delete;

        /** @brief image가 제공하는 TMAP 역할 bit를 등록합니다. */
        Error begin(TelephonyMediaRole roles) noexcept;

        /** @brief 지정 연결에서 TMAS와 TMAP Role characteristic을 검색합니다. */
        Error discover(const BLEConnectionHandle &connection) noexcept;

        /** @brief 연결 소실을 확인하고 stale 검색 결과를 폐기합니다. */
        void poll() noexcept;

        /** @brief 현재 객체의 검색 session 소유권을 반환합니다. */
        Error end() noexcept;

        /** @brief local image가 게시하는 역할 bit를 반환합니다. */
        [[nodiscard]] std::uint16_t localRoles() const noexcept;

        /** @brief 마지막으로 검색한 peer 역할 bit를 반환합니다. */
        [[nodiscard]] std::uint16_t peerRoles() const noexcept;

        /** @brief peer가 요청한 역할을 모두 게시했는지 확인합니다. */
        [[nodiscard]] bool peerSupports(TelephonyMediaRole roles) const noexcept;

        /** @brief 현재 비동기 검색 단계를 반환합니다. */
        [[nodiscard]] TelephonyMediaStage stage() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 TMAP/GATT 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;
    };

    /** @brief GMAP service가 게시하는 역할 bit입니다. */
    enum class GamingAudioRole : std::uint8_t
    {
        unicast_game_gateway = 1U << 0U,
        unicast_game_terminal = 1U << 1U,
        broadcast_game_sender = 1U << 2U,
        broadcast_game_receiver = 1U << 3U,
    };

    /** @brief 여러 GMAP 역할을 하나의 안전한 bit set으로 결합합니다. */
    constexpr GamingAudioRole operator|(GamingAudioRole left, GamingAudioRole right) noexcept
    {
        return static_cast<GamingAudioRole>(static_cast<std::uint8_t>(left) |
                                            static_cast<std::uint8_t>(right));
    }

    /** @brief Unicast Game Gateway가 게시할 수 있는 feature bit입니다. */
    enum class GamingGatewayFeature : std::uint8_t
    {
        multiplex = 1U << 0U,
        source_96_kbps = 1U << 1U,
        multiple_sinks = 1U << 2U,
    };

    /** @brief Unicast Game Terminal이 게시할 수 있는 feature bit입니다. */
    enum class GamingTerminalFeature : std::uint8_t
    {
        source = 1U << 0U,
        source_80_kbps = 1U << 1U,
        sink = 1U << 2U,
        sink_64_kbps = 1U << 3U,
        multiplex = 1U << 4U,
        multiple_sinks = 1U << 5U,
        multiple_sources = 1U << 6U,
    };

    /** @brief Broadcast Game Sender가 게시할 수 있는 feature bit입니다. */
    enum class GamingBroadcastSenderFeature : std::uint8_t
    {
        source_96_kbps = 1U << 0U,
    };

    /** @brief Broadcast Game Receiver가 게시할 수 있는 feature bit입니다. */
    enum class GamingBroadcastReceiverFeature : std::uint8_t
    {
        multiple_sinks = 1U << 0U,
        multiplex = 1U << 1U,
    };

    /** @brief GMAP 역할별 feature characteristic 값을 지정합니다. */
    struct GamingAudioFeatures
    {
        std::uint8_t unicast_gateway = 0U;
        std::uint8_t unicast_terminal = 0U;
        std::uint8_t broadcast_sender = 0U;
        std::uint8_t broadcast_receiver = 0U;
    };

    /** @brief 원격 GMAP 역할과 역할별 feature 검색 결과입니다. */
    struct GamingAudioPeer
    {
        std::uint8_t roles = 0U;
        GamingAudioFeatures features;
    };

    /** @brief GMAP service 등록과 peer 역할 검색 단계를 나타냅니다. */
    enum class GamingAudioStage : std::uint8_t
    {
        idle,
        ready,
        discovering,
        discovered,
        failed,
    };

    /**
     * @brief GMAP 역할·feature를 게시하고 연결된 peer의 GMAS를 검색합니다.
     *
     * 실제 unicast/broadcast stream은 BAP/CAP 공개 facade가 소유합니다. begin()은
     * 선택한 역할의 필수 service와 stream 자원이 Kconfig에 없으면 등록을 거부합니다.
     */
    class GamingAudioRoles final
    {
      public:
        GamingAudioRoles() = default;

        ~GamingAudioRoles()
        {
            (void)end();
        }

        GamingAudioRoles(const GamingAudioRoles &) = delete;
        GamingAudioRoles &operator=(const GamingAudioRoles &) = delete;
        GamingAudioRoles(GamingAudioRoles &&) = delete;
        GamingAudioRoles &operator=(GamingAudioRoles &&) = delete;

        /** @brief image가 제공하는 GMAP 역할과 feature를 등록합니다. */
        Error begin(GamingAudioRole roles, const GamingAudioFeatures &features = {}) noexcept;

        /** @brief 지정 연결에서 GMAS 역할과 feature characteristic을 검색합니다. */
        Error discover(const BLEConnectionHandle &connection) noexcept;

        /** @brief 연결 소실을 확인하고 stale 검색 결과를 폐기합니다. */
        void poll() noexcept;

        /** @brief 현재 객체의 검색 session 소유권을 반환합니다. */
        Error end() noexcept;

        /** @brief local image가 게시하는 역할 bit를 반환합니다. */
        [[nodiscard]] std::uint8_t localRoles() const noexcept;

        /** @brief 마지막 원격 역할·feature 검색 결과를 복사합니다. */
        Error peer(GamingAudioPeer &information) const noexcept;

        /** @brief peer가 요청한 역할을 모두 게시했는지 확인합니다. */
        [[nodiscard]] bool peerSupports(GamingAudioRole roles) const noexcept;

        /** @brief 현재 비동기 검색 단계를 반환합니다. */
        [[nodiscard]] GamingAudioStage stage() const noexcept;

        /** @brief 마지막 공개 오류를 반환합니다. */
        [[nodiscard]] Error lastError() const noexcept;

        /** @brief 마지막 GMAP/GATT 원본 오류를 반환합니다. */
        [[nodiscard]] int nativeCode() const noexcept;
    };
} // namespace nucode::ble::audio

#endif
