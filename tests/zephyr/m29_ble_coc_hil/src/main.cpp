/**
 * @file main.cpp
 * @brief 두 NU54DK로 M29-W06 LE CoC와 고정 자원 오류 회수를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/att.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <string.h>

#ifndef M29_COC_CORE_REVISION
#error "M29_COC_CORE_REVISION is required"
#endif

static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_L2CAP_DYNAMIC_CHANNEL == 1);
static_assert(CONFIG_BT_L2CAP_TX_MTU == 512);
static_assert(CONFIG_BT_L2CAP_TX_BUF_COUNT == 4);
static_assert(nucode::ble::L2capCoc::maximum_channels == 2U);
static_assert(nucode::ble::L2capCoc::maximum_sdu_length == 512U);
static_assert(nucode::ble::L2capCoc::receive_records_per_channel == 4U);
static_assert(nucode::ble::L2capCoc::transmit_buffers == 4U);

namespace nucode::ble::internal::gatt
{

    /** @brief W06 target negative가 production GATT write 경계를 직접 검증합니다. */
    ssize_t serverWrite(struct bt_conn *connection,
                        const struct bt_gatt_attr *attribute,
                        const void *buffer, std::uint16_t length,
                        std::uint16_t offset, std::uint8_t flags) noexcept;

} // namespace nucode::ble::internal::gatt

namespace
{

    constexpr char protocol[] = "M29W06|1";
    constexpr char ready_query[] = "M29W06|1|READY?";
    constexpr char start_prefix[] = "M29W06|1|START|nonce=";
    constexpr char core_suffix[] = "|core=" M29_COC_CORE_REVISION;
    constexpr char service_text[] = "90bf2a20-14f5-4d3d-92c7-299334932a20";
    constexpr char characteristic_text[] = "90bf2a21-14f5-4d3d-92c7-299334932a20";
    constexpr std::uint16_t coc_psm = 0x0080U;
    constexpr std::uint16_t invalid_psm = 0x007fU;
    constexpr std::size_t channel_count = 2U;
    constexpr std::size_t sdu_length = 512U;
    constexpr std::uint32_t required_iterations = 1000U;
    constexpr std::uint32_t required_negative_iterations = 20U;
    constexpr std::int64_t protocol_timeout_ms = 600000;
    constexpr std::size_t nonce_length = 32U;
    constexpr std::uint8_t normal_marker = 0xa6U;
    constexpr std::uint8_t credit_marker = 0xc1U;
    constexpr std::uint8_t recovery_marker = 0xb6U;

    const nucode::ble::BLEUuid service_uuid(service_text);
    const nucode::ble::BLEUuid characteristic_uuid(characteristic_text);
    nucode::ble::BLEService negative_service(service_uuid);
    nucode::ble::BLECharacteristic negative_characteristic(
        characteristic_uuid, nucode::ble::BLEProperty::write,
        nucode::ble::BLEPermission::write, sdu_length);

    char nonce[nonce_length + 1U] = {};
    char command[128] = {};
    std::size_t command_length = 0U;
    bool protocol_started = false;
    bool protocol_finished = false;
    bool callback_context_valid = true;
    std::int64_t protocol_deadline = 0;
    struct k_thread *setup_thread = nullptr;
    nucode::ble::BLEConnectionHandle connection_handle;

#if defined(NUCODE_M29_COC_CENTRAL)
    std::uint8_t payload[sdu_length] = {};
    nucode::ble::BLEL2capChannelHandle channels[channel_count];
    enum class Phase : std::uint8_t
    {
        idle,
        scanning,
        connecting,
        malformed,
        psm,
        credit_issue,
        credit_wait,
        traffic,
        disconnecting,
        recovery_wait,
        recovery_connecting,
        recovery_traffic,
        finished,
    };

    Phase phase = Phase::idle;
    nucode::ble::BLEAddress peer_address;
    nucode::ble::BLEL2capChannelHandle old_channels[channel_count];
    bool peer_found = false;
    bool disconnect_started = false;
    std::uint8_t connected_channels = 0U;
    std::uint8_t disconnected_channels = 0U;
    std::uint8_t intentional_gap_errors = 0U;
    std::uint32_t malformed_rejected = 0U;
    std::uint32_t psm_rejected = 0U;
    std::uint32_t credit_rejected = 0U;
    std::uint32_t credit_iteration = 0U;
    std::uint32_t credit_sent_events = 0U;
    std::uint32_t credit_sent_target = 0U;
    std::uint32_t normal_sent[channel_count] = {};
    std::uint32_t normal_received[channel_count] = {};
    bool normal_awaiting[channel_count] = {};
    bool recovery_sent[channel_count] = {};
    bool recovery_received[channel_count] = {};
    std::int64_t recovery_due = 0;
#else
    nucode::ble::BLEL2capChannelHandle server_channels[channel_count];
    std::uint8_t pending_echo[channel_count] = {};
    std::uint32_t normal_sent[channel_count] = {};
    std::uint32_t normal_received[channel_count] = {};
    std::uint32_t offset_rejected = 0U;
    std::uint32_t execute_rejected = 0U;
    std::uint8_t connected_channels = 0U;
    std::uint8_t recovery_received = 0U;
    std::uint8_t recovery_sent = 0U;
    bool negative_finished = false;
    bool initial_channels_reported = false;
    bool coc_reported = false;
#endif

    /** @brief 현재 image의 고정 role 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M29_COC_CENTRAL)
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief 모든 session record에 nonce와 exact Core revision을 붙입니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M29_COC_CORE_REVISION);
    }

    /** @brief 첫 실패를 고정 protocol로 출력하고 추가 동작을 중단합니다. */
    void fail(const char *stage, int code = 0, int ble_error = -1)
    {
        if (protocol_finished)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(stage == nullptr ? "unknown" : stage);
        if (ble_error >= 0)
        {
            Serial.print("|ble_error=");
            Serial.print(ble_error);
        }
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.println();
        protocol_finished = true;
    }

    /** @brief 공개 callback이 Arduino main thread에서 실행됐는지 확인합니다. */
    void checkCallbackContext()
    {
        if (k_current_get() != setup_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
    }

    /** @brief READY record를 full revision과 함께 출력합니다. */
    void printReady()
    {
        Serial.print(protocol);
        Serial.print("|READY|role=");
        Serial.print(roleName());
        Serial.print("|core=");
        Serial.println(M29_COC_CORE_REVISION);
    }

    /** @brief BEGIN record를 session identity와 함께 출력합니다. */
    void printBegin()
    {
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
    }

    /** @brief 128-bit lowercase nonce와 exact revision start record만 허용합니다. */
    bool acceptStartCommand()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        if (::strncmp(command, start_prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *nonce_start = command + prefix_length;
        for (std::size_t index = 0U; index < nonce_length; ++index)
        {
            const char value = nonce_start[index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        if (::strcmp(nonce_start + nonce_length, core_suffix) != 0)
        {
            return false;
        }
        ::memcpy(nonce, nonce_start, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

    /** @brief little-endian 32-bit sequence를 읽습니다. */
    std::uint32_t getLe32(const std::uint8_t *input)
    {
        return static_cast<std::uint32_t>(input[0]) |
               (static_cast<std::uint32_t>(input[1]) << 8U) |
               (static_cast<std::uint32_t>(input[2]) << 16U) |
               (static_cast<std::uint32_t>(input[3]) << 24U);
    }

#if defined(NUCODE_M29_COC_CENTRAL)
    /** @brief 32-bit sequence를 little-endian으로 기록합니다. */
    void putLe32(std::uint8_t *output, std::uint32_t value)
    {
        output[0] = static_cast<std::uint8_t>(value & 0xffU);
        output[1] = static_cast<std::uint8_t>((value >> 8U) & 0xffU);
        output[2] = static_cast<std::uint8_t>((value >> 16U) & 0xffU);
        output[3] = static_cast<std::uint8_t>((value >> 24U) & 0xffU);
    }

    /** @brief channel·sequence·offset으로 검증 가능한 고정 512-byte SDU를 만듭니다. */
    void buildPayload(std::uint8_t marker, std::size_t channel_index,
                      std::uint32_t sequence)
    {
        payload[0] = marker;
        payload[1] = static_cast<std::uint8_t>(channel_index);
        putLe32(payload + 2U, sequence);
        for (std::size_t index = 6U; index < sizeof(payload); ++index)
        {
            payload[index] = static_cast<std::uint8_t>(
                (channel_index * 37U + sequence * 13U + index * 7U) & 0xffU);
        }
    }
#endif

    /** @brief 수신 SDU가 기대 marker·channel·sequence와 byte 단위로 일치하는지 확인합니다. */
    bool validPayload(const nucode::ble::BLEL2capEventInfo &information,
                      std::uint8_t marker, std::size_t channel_index,
                      std::uint32_t sequence)
    {
        if (information.data == nullptr || information.length != sdu_length ||
            information.data[0] != marker ||
            information.data[1] != static_cast<std::uint8_t>(channel_index) ||
            getLe32(information.data + 2U) != sequence)
        {
            return false;
        }
        for (std::size_t index = 6U; index < information.length; ++index)
        {
            const std::uint8_t expected = static_cast<std::uint8_t>(
                (channel_index * 37U + sequence * 13U + index * 7U) & 0xffU);
            if (information.data[index] != expected)
            {
                return false;
            }
        }
        return true;
    }

    /** @brief 지정 handle이 들어 있는 두 channel 배열 위치를 반환합니다. */
    int channelIndex(nucode::ble::BLEL2capChannelHandle handle,
                     const nucode::ble::BLEL2capChannelHandle *values)
    {
        for (std::size_t index = 0U; index < channel_count; ++index)
        {
            if (values[index].valid() && values[index] == handle)
            {
                return static_cast<int>(index);
            }
        }
        return -1;
    }

    /** @brief role별 고정 2-channel·512-byte·1,000회 결과를 출력합니다. */
    void printCocResult()
    {
        Serial.print(protocol);
        Serial.print("|COC|role=");
        Serial.print(roleName());
        Serial.print("|channels=2|sdu=512|tx_per_channel=1000|rx_per_channel=1000");
        Serial.print("|payload_errors=0");
        printSuffix();
        Serial.println();
    }

#if defined(NUCODE_M29_COC_CENTRAL)
    /** @brief 예상된 공개 오류 event 한 개를 fail-closed 허용 목록에서 소비합니다. */
    void consumeExpectedGapError()
    {
        if (intentional_gap_errors == 0U)
        {
            fail("unexpected_gap_error", BLEDevice.lastDriverError(),
                 static_cast<int>(BLEDevice.lastError()));
            return;
        }
        --intentional_gap_errors;
    }

    /** @brief 한 credit 고갈 회차에서 TX buffer 4개와 다섯 번째 busy를 검증합니다. */
    void issueCreditIteration()
    {
        if (BLEL2cap.availableForWrite() != nucode::ble::L2capCoc::transmit_buffers)
        {
            return;
        }
        buildPayload(credit_marker, 0U, credit_iteration);
        for (std::size_t index = 0U; index < nucode::ble::L2capCoc::transmit_buffers;
             ++index)
        {
            if (!BLEL2cap.send(channels[0], payload, sizeof(payload)))
            {
                fail("credit_early", static_cast<int>(index),
                     static_cast<int>(BLEDevice.lastError()));
                return;
            }
        }
        ++intentional_gap_errors;
        if (BLEL2cap.send(channels[0], payload, sizeof(payload)))
        {
            --intentional_gap_errors;
            fail("credit_unexpected_accept");
            return;
        }
        if (BLEDevice.lastError() != nucode::ble::BLEError::busy)
        {
            fail("credit_error", BLEDevice.lastDriverError(),
                 static_cast<int>(BLEDevice.lastError()));
            return;
        }
        ++credit_rejected;
        ++credit_iteration;
        credit_sent_target = credit_sent_events +
                             nucode::ble::L2capCoc::transmit_buffers;
        phase = Phase::credit_wait;
    }

    /** @brief 모든 정상 echo 뒤 두 기존 channel을 bounded 방식으로 종료합니다. */
    void beginRecovery()
    {
        if (disconnect_started)
        {
            return;
        }
        disconnect_started = true;
        for (std::size_t index = 0U; index < channel_count; ++index)
        {
            old_channels[index] = channels[index];
            if (!BLEL2cap.disconnect(channels[index]))
            {
                fail("recovery_disconnect", static_cast<int>(index),
                     static_cast<int>(BLEDevice.lastError()));
                return;
            }
        }
    }

    /** @brief 해제된 generation을 거부하고 같은 link에 두 새 channel을 만듭니다. */
    void connectRecoveryChannels()
    {
        std::uint8_t marker = recovery_marker;
        for (std::size_t index = 0U; index < channel_count; ++index)
        {
            ++intentional_gap_errors;
            if (BLEL2cap.send(old_channels[index], &marker, 1U))
            {
                --intentional_gap_errors;
                fail("stale_handle_accept", static_cast<int>(index));
                return;
            }
            if (BLEDevice.lastError() != nucode::ble::BLEError::not_connected)
            {
                fail("stale_handle_error", BLEDevice.lastDriverError(),
                     static_cast<int>(BLEDevice.lastError()));
                return;
            }
        }
        connected_channels = 0U;
        for (std::size_t index = 0U; index < channel_count; ++index)
        {
            nucode::ble::BLEL2capChannelHandle replacement;
            if (!BLEL2cap.connect(connection_handle, coc_psm, replacement) ||
                !replacement.valid() || replacement == old_channels[index])
            {
                fail("recovery_connect", static_cast<int>(index),
                     static_cast<int>(BLEDevice.lastError()));
                return;
            }
            channels[index] = replacement;
        }
        phase = Phase::recovery_connecting;
    }

    /** @brief 두 새 generation channel에서 각각 한 SDU echo 회수를 시작합니다. */
    void issueRecoveryTraffic()
    {
        for (std::size_t index = 0U; index < channel_count; ++index)
        {
            if (!recovery_sent[index])
            {
                buildPayload(recovery_marker, index, 0U);
                if (!BLEL2cap.send(channels[index], payload, sizeof(payload)))
                {
                    fail("recovery_send", static_cast<int>(index),
                         static_cast<int>(BLEDevice.lastError()));
                    return;
                }
                recovery_sent[index] = true;
            }
        }
    }

    /** @brief central의 strict 정량 결과와 END를 출력합니다. */
    void finishCentral()
    {
        const nucode::ble::BLEL2capStatistics statistics = BLEL2cap.statistics();
        if (statistics.backpressure != required_negative_iterations)
        {
            fail("backpressure_counter", static_cast<int>(statistics.backpressure));
            return;
        }
        if (statistics.connected != 4U || statistics.disconnected != 2U ||
            statistics.received != 2002U || statistics.sent != 2082U ||
            statistics.dropped_events != 0U)
        {
            fail("central_statistics");
            return;
        }
        Serial.print(protocol);
        Serial.print("|RECOVERY|role=central|old_rejected=2|new_channels=2|echoes=2");
        Serial.print("|failures=0");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|RESULT|role=central|malformed=20|psm=20|credit=20");
        Serial.print("|unexpected=0|recovery_failures=0|stale=0|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=central|status=pass");
        printSuffix();
        Serial.println();
        phase = Phase::finished;
        protocol_finished = true;
    }
#else
    /** @brief production GATT write 경계에서 invalid offset과 execute-without-prepare를 검증합니다. */
    void runGattNegative()
    {
        struct bt_conn *connection =
            nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            fail("negative_connection");
            return;
        }
        struct bt_gatt_attr attribute = {};
        attribute.user_data = &negative_characteristic;
        const std::uint8_t value = 0x5aU;
        const ssize_t expected = BT_GATT_ERR(BT_ATT_ERR_INVALID_OFFSET);
        for (std::uint32_t iteration = 0U;
             iteration < required_negative_iterations; ++iteration)
        {
            const ssize_t result = nucode::ble::internal::gatt::serverWrite(
                connection, &attribute, &value, 1U, 1U, BT_GATT_WRITE_FLAG_PREPARE);
            if (result != expected)
            {
                bt_conn_unref(connection);
                fail("offset_accept", static_cast<int>(result));
                return;
            }
            ++offset_rejected;
        }
        for (std::uint32_t iteration = 0U;
             iteration < required_negative_iterations; ++iteration)
        {
            const ssize_t result = nucode::ble::internal::gatt::serverWrite(
                connection, &attribute, &value, 1U, 0U, BT_GATT_WRITE_FLAG_EXECUTE);
            if (result != expected)
            {
                bt_conn_unref(connection);
                fail("execute_accept", static_cast<int>(result));
                return;
            }
            ++execute_rejected;
        }
        bt_conn_unref(connection);
        Serial.print(protocol);
        Serial.print("|NEG|role=peripheral|class=offset|attempts=20|rejected=20");
        Serial.print("|unexpected=0");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|NEG|role=peripheral|class=execute|attempts=20|rejected=20");
        Serial.print("|unexpected=0");
        printSuffix();
        Serial.println();
        negative_finished = true;
    }

    /** @brief server의 두 정상 channel에서 전송·수신 1,000회가 끝나면 결과를 출력합니다. */
    void maybePrintPeripheralCoc()
    {
        if (!coc_reported && normal_sent[0] == required_iterations &&
            normal_sent[1] == required_iterations &&
            normal_received[0] == required_iterations &&
            normal_received[1] == required_iterations)
        {
            coc_reported = true;
            printCocResult();
        }
    }

    /** @brief peripheral의 회수·negative 정량 결과와 END를 출력합니다. */
    void finishPeripheral()
    {
        if (protocol_finished || !coc_reported || recovery_received != channel_count ||
            recovery_sent != channel_count)
        {
            return;
        }
        const nucode::ble::BLEL2capStatistics statistics = BLEL2cap.statistics();
        if (statistics.accepted != 4U || statistics.connected != 4U ||
            statistics.disconnected != 2U || statistics.received != 2082U ||
            statistics.sent != 2002U || statistics.backpressure != 0U ||
            statistics.rejected != 0U || statistics.dropped_events != 0U)
        {
            fail("peripheral_statistics");
            return;
        }
        Serial.print(protocol);
        Serial.print("|RECOVERY|role=peripheral|new_channels=2|echoes=2|failures=0");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|RESULT|role=peripheral|offset=20|execute=20|unexpected=0");
        Serial.print("|recovery_failures=0|cross_channel=0|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=peripheral|status=pass");
        printSuffix();
        Serial.println();
        protocol_finished = true;
    }
#endif

#if defined(NUCODE_M29_COC_CENTRAL)
    /** @brief scan 결과의 검증된 peer 주소를 main-thread storage에 보존합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (protocol_started && !protocol_finished && !peer_found)
        {
            peer_address = result.address;
            peer_found = true;
        }
    }
#endif

    /** @brief GAP connection과 예상된 오류 event를 role별 상태기에 전달합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!protocol_started || protocol_finished)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::error)
        {
#if defined(NUCODE_M29_COC_CENTRAL)
            consumeExpectedGapError();
#else
            fail("gap_error", BLEDevice.lastDriverError(),
                 static_cast<int>(BLEDevice.lastError()));
#endif
            return;
        }
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            connection_handle = information.connection;
            if (!connection_handle.valid())
            {
                fail("connection_handle");
                return;
            }
#if defined(NUCODE_M29_COC_CENTRAL)
            if (information.role != nucode::ble::BLELinkRole::central)
            {
                fail("connection_role");
                return;
            }
            phase = Phase::connecting;
            for (std::size_t index = 0U; index < channel_count; ++index)
            {
                if (!BLEL2cap.connect(connection_handle, coc_psm, channels[index]))
                {
                    fail("channel_connect", static_cast<int>(index),
                         static_cast<int>(BLEDevice.lastError()));
                    return;
                }
            }
#else
            if (information.role != nucode::ble::BLELinkRole::peripheral)
            {
                fail("connection_role");
            }
#endif
            return;
        }
        if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            fail("early_gap_disconnect");
        }
    }

    /** @brief CoC state와 복사된 SDU를 main thread에서 검증하고 다음 전송을 예약합니다. */
    void onL2capEvent(const nucode::ble::BLEL2capEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!protocol_started || protocol_finished)
        {
            return;
        }
#if defined(NUCODE_M29_COC_CENTRAL)
        if (information.event == nucode::ble::BLEL2capEvent::connected)
        {
            if (channelIndex(information.channel, channels) < 0 ||
                information.local_mtu != sdu_length ||
                information.remote_mtu != sdu_length)
            {
                fail("channel_connected_value", information.status);
                return;
            }
            ++connected_channels;
            if (connected_channels == channel_count && phase == Phase::connecting)
            {
                Serial.print(protocol);
                Serial.print("|CHANNELS|role=central|connected=2|local_mtu=512");
                Serial.print("|remote_mtu=512");
                printSuffix();
                Serial.println();
                phase = Phase::malformed;
            }
            else if (connected_channels == channel_count &&
                     phase == Phase::recovery_connecting)
            {
                phase = Phase::recovery_traffic;
            }
            return;
        }
        if (information.event == nucode::ble::BLEL2capEvent::sent)
        {
            if (phase == Phase::credit_wait || phase == Phase::credit_issue)
            {
                ++credit_sent_events;
            }
            return;
        }
        if (information.event == nucode::ble::BLEL2capEvent::disconnected)
        {
            if (phase != Phase::disconnecting)
            {
                fail("unexpected_channel_disconnect", information.status);
                return;
            }
            ++disconnected_channels;
            if (disconnected_channels == channel_count)
            {
                recovery_due = k_uptime_get() + 250;
                phase = Phase::recovery_wait;
            }
            return;
        }
        if (information.event != nucode::ble::BLEL2capEvent::received)
        {
            return;
        }
        const int index = channelIndex(information.channel, channels);
        if (index < 0)
        {
            fail("rx_channel");
            return;
        }
        const std::size_t channel_index = static_cast<std::size_t>(index);
        if (phase == Phase::traffic)
        {
            const std::uint32_t sequence = normal_received[channel_index];
            if (!normal_awaiting[channel_index] ||
                !validPayload(information, normal_marker, channel_index, sequence))
            {
                fail("normal_payload", static_cast<int>(channel_index));
                return;
            }
            normal_awaiting[channel_index] = false;
            ++normal_received[channel_index];
            if (normal_received[0] == required_iterations &&
                normal_received[1] == required_iterations)
            {
                printCocResult();
                phase = Phase::disconnecting;
            }
            return;
        }
        if (phase == Phase::recovery_traffic)
        {
            if (!validPayload(information, recovery_marker, channel_index, 0U) ||
                recovery_received[channel_index])
            {
                fail("recovery_payload", static_cast<int>(channel_index));
                return;
            }
            recovery_received[channel_index] = true;
            if (recovery_received[0] && recovery_received[1])
            {
                finishCentral();
            }
        }
#else
        if (information.event == nucode::ble::BLEL2capEvent::connected)
        {
            if (information.local_mtu != sdu_length ||
                information.remote_mtu != sdu_length || connected_channels >= channel_count)
            {
                fail("channel_connected_value", information.status);
                return;
            }
            server_channels[connected_channels] = information.channel;
            ++connected_channels;
            if (connected_channels == channel_count && !initial_channels_reported)
            {
                initial_channels_reported = true;
                Serial.print(protocol);
                Serial.print("|CHANNELS|role=peripheral|connected=2|local_mtu=512");
                Serial.print("|remote_mtu=512");
                printSuffix();
                Serial.println();
            }
            return;
        }
        if (information.event == nucode::ble::BLEL2capEvent::disconnected)
        {
            const int index = channelIndex(information.channel, server_channels);
            if (index < 0)
            {
                fail("disconnect_channel");
                return;
            }
            server_channels[static_cast<std::size_t>(index)] =
                nucode::ble::BLEL2capChannelHandle{};
            pending_echo[static_cast<std::size_t>(index)] = 0U;
            --connected_channels;
            return;
        }
        const int index = channelIndex(information.channel, server_channels);
        if (index < 0)
        {
            fail("event_channel");
            return;
        }
        const std::size_t channel_index = static_cast<std::size_t>(index);
        if (information.event == nucode::ble::BLEL2capEvent::sent)
        {
            if (pending_echo[channel_index] == normal_marker)
            {
                ++normal_sent[channel_index];
                pending_echo[channel_index] = 0U;
                maybePrintPeripheralCoc();
            }
            else if (pending_echo[channel_index] == recovery_marker)
            {
                ++recovery_sent;
                pending_echo[channel_index] = 0U;
                finishPeripheral();
            }
            else
            {
                fail("unexpected_sent", static_cast<int>(channel_index));
            }
            return;
        }
        if (information.event != nucode::ble::BLEL2capEvent::received)
        {
            return;
        }
        if (information.data == nullptr || information.length == 0U)
        {
            fail("empty_receive");
            return;
        }
        const std::uint8_t marker = information.data[0];
        if (marker == credit_marker)
        {
            return;
        }
        if (marker != normal_marker && marker != recovery_marker)
        {
            fail("unknown_marker", marker);
            return;
        }
        const std::size_t payload_channel = information.data[1];
        const std::uint32_t sequence = getLe32(information.data + 2U);
        if (payload_channel >= channel_count || payload_channel != channel_index ||
            pending_echo[channel_index] != 0U ||
            !validPayload(information, marker, payload_channel, sequence))
        {
            fail("server_payload", static_cast<int>(payload_channel));
            return;
        }
        if (marker == normal_marker)
        {
            if (sequence != normal_received[channel_index] ||
                sequence >= required_iterations)
            {
                fail("server_sequence", static_cast<int>(sequence));
                return;
            }
            ++normal_received[channel_index];
        }
        else
        {
            if (sequence != 0U)
            {
                fail("recovery_sequence", static_cast<int>(sequence));
                return;
            }
            ++recovery_received;
        }
        pending_echo[channel_index] = marker;
        if (!BLEL2cap.send(information.channel, information.data, information.length))
        {
            pending_echo[channel_index] = 0U;
            fail("echo_send", BLEDevice.lastDriverError(),
                 static_cast<int>(BLEDevice.lastError()));
        }
#endif
    }

    /** @brief 검증된 START 뒤 role별 advertising 또는 scan을 시작합니다. */
    void startProtocol()
    {
        if (!acceptStartCommand())
        {
            fail("start_record");
            return;
        }
        protocol_started = true;
        protocol_deadline = k_uptime_get() + protocol_timeout_ms;
        printBegin();
#if defined(NUCODE_M29_COC_CENTRAL)
        phase = Phase::scanning;
        if (!BLEScan.clearFilters() || !BLEScan.filterServiceUuid(service_uuid) ||
            !BLEScan.start(true))
        {
            fail("scan_start", BLEDevice.lastDriverError(),
                 static_cast<int>(BLEDevice.lastError()));
            return;
        }
        Serial.print(protocol);
        Serial.print("|SCAN|role=central|status=pass");
#else
        if (!BLEL2cap.startServer(coc_psm) || !BLEAdvertising.clear() ||
            !BLEAdvertising.setConnectable(true) ||
            !BLEAdvertising.addServiceUuid(service_uuid) ||
            !BLEAdvertising.setScanResponseName(true) || !BLEAdvertising.start())
        {
            fail("advertising_start", BLEDevice.lastDriverError(),
                 static_cast<int>(BLEDevice.lastError()));
            return;
        }
        Serial.print(protocol);
        Serial.print("|ADVERTISE|role=peripheral|psm=128|status=pass");
#endif
        printSuffix();
        Serial.println();
    }

    /** @brief Host의 bounded 한 줄 command만 수집합니다. */
    void pollHostCommand()
    {
        while (Serial.available() > 0 && !protocol_started && !protocol_finished)
        {
            const int incoming = Serial.read();
            if (incoming < 0)
            {
                return;
            }
            const char value = static_cast<char>(incoming);
            if (value == '\r')
            {
                continue;
            }
            if (value == '\n')
            {
                command[command_length] = '\0';
                if (::strcmp(command, ready_query) == 0)
                {
                    command_length = 0U;
                    printReady();
                    return;
                }
                startProtocol();
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                fail("command_overflow");
                return;
            }
            command[command_length++] = value;
        }
    }

} // namespace

void setup()
{
    setup_thread = k_current_get();
    Serial.begin(115200);
    const std::int64_t deadline = k_uptime_get() + 5000;
    while (!Serial && k_uptime_get() < deadline)
    {
        delay(10);
    }
#if !defined(NUCODE_M29_COC_CENTRAL)
    if (!negative_service.addCharacteristic(negative_characteristic) ||
        !BLEDevice.addService(negative_service))
    {
        fail("schema");
        return;
    }
#endif
    BLEDevice.onEventInfo(onBleEvent);
    BLEL2cap.onEvent(onL2capEvent);
#if defined(NUCODE_M29_COC_CENTRAL)
    BLEScan.onResult(onScanResult);
#endif
    if (!BLEDevice.begin(roleName()))
    {
        fail("device_begin", BLEDevice.lastDriverError(),
             static_cast<int>(BLEDevice.lastError()));
        return;
    }
    printReady();
}

void loop()
{
    pollHostCommand();
    BLEDevice.poll();
    if (!protocol_started || protocol_finished)
    {
        delay(1);
        return;
    }
#if defined(NUCODE_M29_COC_CENTRAL)
    if (peer_found && phase == Phase::scanning)
    {
        peer_found = false;
        static_cast<void>(BLEScan.stop());
        if (!BLEConnection.connect(peer_address))
        {
            fail("gap_connect", BLEDevice.lastDriverError(),
                 static_cast<int>(BLEDevice.lastError()));
        }
    }
    else if (phase == Phase::malformed)
    {
        ++intentional_gap_errors;
        if (BLEL2cap.send(channels[0], nullptr, 1U))
        {
            --intentional_gap_errors;
            fail("malformed_accept");
        }
        else if (BLEDevice.lastError() != nucode::ble::BLEError::invalid_argument)
        {
            fail("malformed_error", BLEDevice.lastDriverError(),
                 static_cast<int>(BLEDevice.lastError()));
        }
        else
        {
            ++malformed_rejected;
            if (malformed_rejected == required_negative_iterations)
            {
                Serial.print(protocol);
                Serial.print("|NEG|role=central|class=malformed|attempts=20|rejected=20");
                Serial.print("|unexpected=0");
                printSuffix();
                Serial.println();
                phase = Phase::psm;
            }
        }
    }
    else if (phase == Phase::psm)
    {
        nucode::ble::BLEL2capChannelHandle rejected_channel;
        ++intentional_gap_errors;
        if (BLEL2cap.connect(connection_handle, invalid_psm, rejected_channel))
        {
            --intentional_gap_errors;
            fail("psm_accept");
        }
        else if (rejected_channel.valid() ||
                 BLEDevice.lastError() != nucode::ble::BLEError::invalid_argument)
        {
            fail("psm_error", BLEDevice.lastDriverError(),
                 static_cast<int>(BLEDevice.lastError()));
        }
        else
        {
            ++psm_rejected;
            if (psm_rejected == required_negative_iterations)
            {
                Serial.print(protocol);
                Serial.print("|NEG|role=central|class=psm|attempts=20|rejected=20");
                Serial.print("|unexpected=0");
                printSuffix();
                Serial.println();
                phase = Phase::credit_issue;
            }
        }
    }
    else if (phase == Phase::credit_issue)
    {
        issueCreditIteration();
    }
    else if (phase == Phase::credit_wait &&
             credit_sent_events >= credit_sent_target &&
             BLEL2cap.availableForWrite() == nucode::ble::L2capCoc::transmit_buffers)
    {
        if (credit_iteration == required_negative_iterations)
        {
            Serial.print(protocol);
            Serial.print("|NEG|role=central|class=credit|attempts=20|rejected=20");
            Serial.print("|unexpected=0");
            printSuffix();
            Serial.println();
            phase = Phase::traffic;
        }
        else
        {
            phase = Phase::credit_issue;
        }
    }
    else if (phase == Phase::traffic)
    {
        for (std::size_t index = 0U; index < channel_count; ++index)
        {
            if (!normal_awaiting[index] && normal_sent[index] < required_iterations)
            {
                buildPayload(normal_marker, index, normal_sent[index]);
                if (!BLEL2cap.send(channels[index], payload, sizeof(payload)))
                {
                    fail("normal_send", static_cast<int>(index),
                         static_cast<int>(BLEDevice.lastError()));
                    break;
                }
                normal_awaiting[index] = true;
                ++normal_sent[index];
            }
        }
    }
    else if (phase == Phase::disconnecting)
    {
        beginRecovery();
    }
    else if (phase == Phase::recovery_wait && k_uptime_get() >= recovery_due)
    {
        connectRecoveryChannels();
    }
    else if (phase == Phase::recovery_traffic)
    {
        issueRecoveryTraffic();
    }
#else
    if (!negative_finished && connection_handle.valid())
    {
        runGattNegative();
    }
#endif
    if (!protocol_finished && k_uptime_get() >= protocol_deadline)
    {
        fail("timeout");
    }
    delay(1);
}
