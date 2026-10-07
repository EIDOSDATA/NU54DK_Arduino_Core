/**
 * @file main.cpp
 * @brief 두 NU54DK에서 W03 timing·feature·packet 경로를 유한 반복 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

#ifndef M32_TIMING_CORE_REVISION
#error "M32_TIMING_CORE_REVISION is required"
#endif

namespace
{

    constexpr char protocol[] = "M32TIM|1";
    constexpr char start_prefix[] = "M32TIM|1|START|nonce=";
    constexpr char stop_prefix[] = "M32TIM|1|STOP|nonce=";
    constexpr char peer_name[] = "NU54-M32-TIM";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::uint32_t procedure_target = 20U;
    constexpr std::uint32_t packet_target = 2000U;
    constexpr std::uint32_t boundary_packet_mask = 0x80000000U;
    constexpr std::uint32_t feature_target = 20U;
    constexpr std::uint32_t sca_target = 10U;
    constexpr std::int64_t session_timeout_ms = 240000;
    constexpr std::int64_t channel_interval_ms = 1050;

    const nucode::ble::BLEUuid service_uuid("bc7a0001-46dd-4a69-9b9b-102030405060");
    const nucode::ble::BLEUuid packet_uuid("bc7a0002-46dd-4a69-9b9b-102030405060");
    nucode::ble::BLEService packet_service(service_uuid);
    nucode::ble::BLECharacteristic packet_value(
        packet_uuid,
        nucode::ble::BLEProperty::write_without_response,
        nucode::ble::BLEPermission::write,
        8U);

    enum class ProcedurePhase : std::uint8_t
    {
        idle,
        subrate,
        frame_space,
        connection_rate,
        channel_map,
        complete,
    };

    char command[128] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool started = false;
    bool session_complete = false;
    bool failed = false;
    bool stop_requested = false;
    bool callback_context_valid = true;
    bool feature_ready = false;
#if defined(NUCODE_M32_TIMING_CENTRAL)
    bool discovery_pending = false;
    bool procedures_started = false;
    bool initial_parameters_ready = false;
    bool subrate_ack_pending = false;
    bool subrate_ack_received = false;
    bool boundary_write_pending = false;
    bool boundary_write_complete = false;
#endif
    std::uint32_t transmitted_packets = 0U;
    std::uint32_t received_packets = 0U;
    std::uint32_t subrate_changes = 0U;
    std::uint32_t subrate_acknowledgements = 0U;
    std::uint32_t subrate_increase_acknowledgements = 0U;
    std::uint32_t boundary_packets = 0U;
    std::uint32_t frame_space_changes = 0U;
    std::uint32_t connection_rate_changes = 0U;
    std::uint32_t channel_updates = 0U;
    std::uint32_t feature_samples = 0U;
    std::uint32_t sca_samples = 0U;
    std::uint16_t minimum_interval_us = 0U;
    std::uint32_t maximum_packet_gap_ms = 0U;
    std::uint32_t maximum_procedure_gap_ms = 0U;
    std::int64_t deadline_ms = 0;
#if defined(NUCODE_M32_TIMING_CENTRAL)
    std::int64_t next_channel_update_ms = 0;
#endif
    std::int64_t last_packet_ms = 0;
    std::int64_t last_procedure_ms = 0;
    struct k_thread *main_thread = nullptr;
    nucode::ble::BLEConnectionHandle connection_handle;
#if defined(NUCODE_M32_TIMING_CENTRAL)
    ProcedurePhase procedure_phase = ProcedurePhase::idle;
#endif
    std::uint8_t packet[8] = {};

    /** @brief 현재 image의 고정 역할 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M32_TIMING_CENTRAL)
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief 모든 결과 record에 nonce와 exact Core revision을 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M32_TIMING_CORE_REVISION);
    }

    /** @brief 첫 오류를 bounded protocol로 출력합니다. */
    void fail(const char *stage, int code = 0)
    {
        if (failed)
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
        failed = true;
    }

    /** @brief callback이 Arduino main thread에서 dispatch됐는지 확인합니다. */
    void checkCallbackContext()
    {
        if (k_current_get() != main_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
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
                     M32_TIMING_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

    /** @brief 반복 번호별 Subrate factor·latency·timeout 경계를 고정합니다. */
    void subrateParameters(std::uint32_t iteration,
                           nucode::ble::BLESubrateParameters &parameters)
    {
        const bool increased = (iteration & 1U) != 0U;
        const std::uint16_t factor = increased ? 4U : 2U;
        parameters.minimum_factor = factor;
        parameters.maximum_factor = factor;
        parameters.maximum_peripheral_latency = increased ? 3U : 0U;
        parameters.continuation_number = 0U;
        parameters.supervision_timeout_10ms = increased ? 800U : 400U;
    }

    /** @brief controller ACK가 factor·latency 범위·timeout 계약을 만족하는지 검사합니다. */
    bool validSubrateAck(std::uint32_t iteration,
                         const nucode::ble::BLESubrateInfo &result)
    {
        nucode::ble::BLESubrateParameters expected;
        subrateParameters(iteration, expected);
        return result.status == 0U &&
               result.factor == expected.minimum_factor &&
               result.continuation_number == expected.continuation_number &&
               result.peripheral_latency <= expected.maximum_peripheral_latency &&
               result.supervision_timeout_10ms ==
                   expected.supervision_timeout_10ms;
    }

#if defined(NUCODE_M32_TIMING_CENTRAL)
    /** @brief packet sequence와 역상 값을 little-endian payload에 기록합니다. */
    void encodePacket(std::uint32_t sequence)
    {
        const std::uint32_t inverse = ~sequence;
        for (std::size_t index = 0U; index < 4U; ++index)
        {
            packet[index] = static_cast<std::uint8_t>(sequence >> (index * 8U));
            packet[index + 4U] = static_cast<std::uint8_t>(inverse >> (index * 8U));
        }
    }
#else

    /** @brief 고정 길이 packet의 sequence와 역상을 복호화합니다. */
    bool decodePacket(const std::uint8_t *data, std::size_t length,
                      std::uint32_t &sequence)
    {
        if (data == nullptr || length != sizeof(packet))
        {
            return false;
        }
        sequence = 0U;
        std::uint32_t inverse = 0U;
        for (std::size_t index = 0U; index < 4U; ++index)
        {
            sequence |= static_cast<std::uint32_t>(data[index]) << (index * 8U);
            inverse |= static_cast<std::uint32_t>(data[index + 4U]) << (index * 8U);
        }
        return inverse == ~sequence;
    }
#endif

    /** @brief 연속 event의 최대 간격을 overflow 없이 갱신합니다. */
    void recordGap(std::int64_t &previous, std::uint32_t &maximum)
    {
        const std::int64_t now = k_uptime_get();
        if (previous != 0)
        {
            const std::int64_t gap = now - previous;
            if (gap > static_cast<std::int64_t>(maximum))
            {
                maximum = static_cast<std::uint32_t>(gap);
            }
        }
        previous = now;
    }

#if defined(NUCODE_M32_TIMING_CENTRAL)
    /** @brief 다음 GATT packet 한 개를 response write로 제출합니다. */
    bool sendPacket()
    {
        if (transmitted_packets >= packet_target)
        {
            return true;
        }
        encodePacket(transmitted_packets);
        return BLEClient.writeWithoutResponse(connection_handle, packet, sizeof(packet));
    }

    /** @brief 다음 Frame Space 요청 함수의 Subrate 경계용 전방 선언입니다. */
    bool requestFrameSpaceIteration();

    /** @brief Subrate 요청 직후 기존 link로 ACK 경계 payload를 제출합니다. */
    bool sendBoundaryPacket()
    {
        encodePacket(boundary_packet_mask | subrate_changes);
        boundary_write_pending = true;
        boundary_write_complete = false;
        if (!BLEClient.writeWithoutResponse(connection_handle, packet, sizeof(packet)))
        {
            boundary_write_pending = false;
            return false;
        }
        return true;
    }

    /** @brief Subrate ACK와 경계 payload 완료가 모두 관측된 뒤 다음 절차로 이동합니다. */
    void advanceSubrateBoundary()
    {
        if (!subrate_ack_received || !boundary_write_complete || failed)
        {
            return;
        }
        subrate_ack_received = false;
        boundary_write_complete = false;
        if (!requestFrameSpaceIteration())
        {
            fail("frame_request", BLEDevice.lastDriverError());
        }
    }

    /** @brief 다음 Subrating 절차를 exact factor로 시작합니다. */
    bool requestSubrateIteration()
    {
        nucode::ble::BLESubrateParameters parameters;
        subrateParameters(subrate_changes, parameters);
        procedure_phase = ProcedurePhase::subrate;
        subrate_ack_pending = true;
        subrate_ack_received = false;
        if (!BLEConnection.requestSubrate(connection_handle, parameters))
        {
            subrate_ack_pending = false;
            return false;
        }
        if (!sendBoundaryPacket())
        {
            return false;
        }
        return true;
    }

    /** @brief 다음 Frame Space 절차를 controller가 고를 수 있는 2M ACL 범위로 제출합니다. */
    bool requestFrameSpaceIteration()
    {
        nucode::ble::BLEFrameSpaceParameters parameters;
        parameters.phy_mask = (frame_space_changes % 2U) == 0U
                                  ? nucode::ble::BLEFrameSpaceParameters::phy_le_2m
                                  : nucode::ble::BLEFrameSpaceParameters::phy_le_1m;
        parameters.minimum_us = 0U;
        parameters.maximum_us = 150U;
        procedure_phase = ProcedurePhase::frame_space;
        return BLEConnection.requestFrameSpace(connection_handle, parameters);
    }

    /** @brief 다음 표준 Shorter Connection Interval 절차를 제출합니다. */
    bool requestConnectionRateIteration()
    {
        nucode::ble::BLEConnectionRateParameters parameters;
        const std::uint16_t interval =
            static_cast<std::uint16_t>((connection_rate_changes % 2U) == 0U ? 6U : 8U);
        parameters.interval_minimum_125us = interval;
        parameters.interval_maximum_125us = interval;
        procedure_phase = ProcedurePhase::connection_rate;
        return BLEConnection.requestConnectionRate(connection_handle, parameters);
    }

    /** @brief 1초 간격을 지킨 Host channel classification을 적용합니다. */
    bool applyChannelMapIteration()
    {
        const std::uint8_t full_map[5] = {0xffU, 0xffU, 0xffU, 0xffU, 0x1fU};
        const std::uint8_t classified_map[5] = {0xfeU, 0xffU, 0xffU, 0xffU, 0x1fU};
        const std::uint8_t *selected =
            (channel_updates % 2U) == 0U ? full_map : classified_map;
        if (!BLEConnection.setChannelClassification(selected))
        {
            return false;
        }
        ++channel_updates;
        next_channel_update_ms = k_uptime_get() + channel_interval_ms;
        if (channel_updates < procedure_target)
        {
            return requestSubrateIteration();
        }
        procedure_phase = ProcedurePhase::complete;
        return true;
    }

    /** @brief exact-name scan 결과 하나를 연결합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (failed || (!result.connectable && !result.scan_response))
        {
            return;
        }
        if (!BLEScan.stop() ||
            !BLEConnection.connect(result.address, connection_handle))
        {
            fail("connect_start", BLEDevice.lastDriverError());
        }
    }

    /** @brief GATT discovery와 2,000개 response write를 직렬화합니다. */
    void onClientEvent(nucode::ble::BLEGattClientEvent event,
                       const std::uint8_t *data, std::size_t length,
                       void *context)
    {
        static_cast<void>(data);
        static_cast<void>(length);
        static_cast<void>(context);
        checkCallbackContext();
        if (event == nucode::ble::BLEGattClientEvent::discovery_complete)
        {
            if (!sendPacket())
            {
                fail("packet_start", BLEDevice.lastDriverError());
            }
        }
        else if (event == nucode::ble::BLEGattClientEvent::write_without_response_complete)
        {
            if (boundary_write_pending)
            {
                boundary_write_pending = false;
                boundary_write_complete = true;
                ++boundary_packets;
                advanceSubrateBoundary();
                return;
            }
            if (transmitted_packets == 100U)
            {
                last_packet_ms = 0;
            }
            if (transmitted_packets >= 100U)
            {
                recordGap(last_packet_ms, maximum_packet_gap_ms);
            }
            ++transmitted_packets;
            if (transmitted_packets < packet_target)
            {
                if (!sendPacket())
                {
                    fail("packet_write", BLEDevice.lastDriverError());
                }
            }
            else
            {
                procedures_started = true;
                if (!requestSubrateIteration())
                {
                    fail("subrate_request", BLEDevice.lastDriverError());
                }
            }
        }
        else if (event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            fail("gatt_operation", BLEDevice.lastDriverError());
        }
    }
#else
    /** @brief GATT write payload의 순서·역상 값을 검증합니다. */
    void onPacket(nucode::ble::BLECharacteristic &characteristic,
                  const nucode::ble::BLECharacteristicEventInfo &event,
                  void *context)
    {
        static_cast<void>(characteristic);
        static_cast<void>(context);
        checkCallbackContext();
        if (event.event == nucode::ble::BLECharacteristicEvent::written)
        {
            std::uint32_t sequence = 0U;
            if (!decodePacket(event.data, event.length, sequence))
            {
                fail("payload_corruption", static_cast<int>(received_packets));
                return;
            }
            if ((sequence & boundary_packet_mask) != 0U)
            {
                const std::uint32_t boundary_sequence =
                    sequence & ~boundary_packet_mask;
                if (boundary_sequence != boundary_packets)
                {
                    fail("subrate_boundary_order",
                         static_cast<int>(boundary_sequence));
                    return;
                }
                ++boundary_packets;
                return;
            }
            if (sequence != received_packets)
            {
                fail("payload_sequence", static_cast<int>(sequence));
                return;
            }
            if (received_packets == 100U)
            {
                last_packet_ms = 0;
            }
            if (received_packets >= 100U)
            {
                recordGap(last_packet_ms, maximum_packet_gap_ms);
            }
            ++received_packets;
        }
    }
#endif

    /** @brief timeout 원인 분석용 현재 분모를 UID 없이 출력합니다. */
    void printDiagnostic()
    {
        Serial.print(protocol);
        Serial.print("|DIAG|role=");
        Serial.print(roleName());
        Serial.print("|tx=");
        Serial.print(transmitted_packets);
        Serial.print("|rx=");
        Serial.print(received_packets);
        Serial.print("|subrate=");
        Serial.print(subrate_changes);
        Serial.print("|subrate_ack=");
        Serial.print(subrate_acknowledgements);
        Serial.print("|boundary=");
        Serial.print(boundary_packets);
        Serial.print("|frame=");
        Serial.print(frame_space_changes);
        Serial.print("|rate=");
        Serial.print(connection_rate_changes);
        Serial.print("|feature=");
        Serial.print(feature_samples);
        Serial.print("|sca=");
        Serial.print(sca_samples);
        printSuffix();
        Serial.println();
    }

    /** @brief 연결·timing·feature callback을 exact link에 귀속합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (failed)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            connection_handle = information.connection;
            nucode::ble::BLEExtendedFeatureSet local_features;
            if (!BLEConnection.localExtendedFeatures(local_features) ||
                local_features.maximum_valid_page < 1U ||
                !BLEConnection.requestRemoteExtendedFeatures(connection_handle))
            {
                fail("feature_setup", BLEDevice.lastDriverError());
                return;
            }
#if defined(NUCODE_M32_TIMING_CENTRAL)
            nucode::ble::BLESubrateParameters invalid_subrate;
            invalid_subrate.minimum_factor = 0U;
            nucode::ble::BLEFrameSpaceParameters invalid_frame;
            invalid_frame.phy_mask = 0U;
            nucode::ble::BLEConnectionRateParameters invalid_rate;
            invalid_rate.interval_minimum_125us = 2U;
            const std::uint8_t invalid_map[5] = {1U, 0U, 0U, 0U, 0U};
            if (BLEConnection.requestSubrate(connection_handle, invalid_subrate) ||
                BLEConnection.requestFrameSpace(connection_handle, invalid_frame) ||
                BLEConnection.requestConnectionRate(connection_handle, invalid_rate) ||
                BLEConnection.requestRemoteExtendedFeatures(connection_handle, 11U) ||
                BLEConnection.setChannelClassification(invalid_map))
            {
                fail("negative_accept");
                return;
            }
            if (!BLEConnection.minimumConnectionInterval(minimum_interval_us) ||
                minimum_interval_us > 750U ||
                !BLEConnection.requestParameters(connection_handle, 6U, 6U, 0U, 400U))
            {
                fail("link_setup", BLEDevice.lastDriverError());
                return;
            }
#endif
        }
#if defined(NUCODE_M32_TIMING_CENTRAL)
        else if (information.event == nucode::ble::BLEEvent::parameters_changed &&
                 information.connection == connection_handle &&
                 !initial_parameters_ready)
        {
            initial_parameters_ready = true;
            if (!BLEConnection.requestPhy(connection_handle, true) ||
                !BLEConnection.requestDataLength(connection_handle))
            {
                fail("throughput_setup", BLEDevice.lastDriverError());
                return;
            }
            discovery_pending = true;
        }
#endif
        else if (information.event == nucode::ble::BLEEvent::remote_features_available &&
                 information.connection == connection_handle)
        {
            nucode::ble::BLEExtendedFeatureSet remote_features;
            if (!BLEConnection.remoteExtendedFeatures(connection_handle, remote_features) ||
                remote_features.status != 0U || remote_features.maximum_valid_page < 1U)
            {
                fail("remote_features", remote_features.status);
                return;
            }
            feature_ready = true;
        }
        else if (information.event == nucode::ble::BLEEvent::subrate_changed &&
                 information.connection == connection_handle)
        {
            nucode::ble::BLESubrateInfo result;
            if (!BLEConnection.subrate(connection_handle, result) ||
                !validSubrateAck(subrate_changes, result))
            {
                fail("subrate_result", result.status);
                return;
            }
            recordGap(last_procedure_ms, maximum_procedure_gap_ms);
            ++subrate_acknowledgements;
            if ((subrate_changes & 1U) != 0U)
            {
                ++subrate_increase_acknowledgements;
            }
            ++subrate_changes;
#if defined(NUCODE_M32_TIMING_CENTRAL)
            if (procedure_phase != ProcedurePhase::subrate ||
                !subrate_ack_pending)
            {
                fail("subrate_ack_order");
                return;
            }
            subrate_ack_pending = false;
            subrate_ack_received = true;
            advanceSubrateBoundary();
#endif
        }
        else if (information.event == nucode::ble::BLEEvent::frame_space_changed &&
                 information.connection == connection_handle)
        {
            nucode::ble::BLEFrameSpaceInfo result;
            if (!BLEConnection.frameSpace(connection_handle, result) || result.status != 0U)
            {
                fail("frame_result", result.status);
                return;
            }
            recordGap(last_procedure_ms, maximum_procedure_gap_ms);
            ++frame_space_changes;
#if defined(NUCODE_M32_TIMING_CENTRAL)
            if (procedure_phase != ProcedurePhase::frame_space ||
                !requestConnectionRateIteration())
            {
                fail("rate_request", BLEDevice.lastDriverError());
            }
#endif
        }
        else if (information.event == nucode::ble::BLEEvent::connection_rate_changed &&
                 information.connection == connection_handle)
        {
            nucode::ble::BLEConnectionRateInfo result;
            if (!BLEConnection.connectionRate(connection_handle, result) ||
                result.status != 0U || result.interval_us > 1000U)
            {
                fail("rate_result", result.status);
                return;
            }
            recordGap(last_procedure_ms, maximum_procedure_gap_ms);
            ++connection_rate_changes;
#if defined(NUCODE_M32_TIMING_CENTRAL)
            if (procedure_phase != ProcedurePhase::connection_rate)
            {
                fail("rate_order");
                return;
            }
            procedure_phase = ProcedurePhase::channel_map;
#endif
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected &&
                 stop_requested)
        {
            nucode::ble::BLESubrateParameters parameters;
            if (BLEConnection.requestSubrate(connection_handle, parameters))
            {
                fail("stale_link_accept");
                return;
            }
            Serial.print(protocol);
            Serial.print("|STOPPED|role=");
            Serial.print(roleName());
            printSuffix();
            Serial.println();
            stop_requested = false;
        }
    }

    /** @brief 모든 역할별 분모가 끝나면 RESULT와 END를 한 번 출력합니다. */
    void finishIfComplete()
    {
        if (session_complete || failed || !started ||
            feature_samples != feature_target || sca_samples != sca_target ||
            subrate_acknowledgements != procedure_target ||
            subrate_increase_acknowledgements != procedure_target / 2U ||
            boundary_packets != procedure_target)
        {
            return;
        }
#if defined(NUCODE_M32_TIMING_CENTRAL)
        if (transmitted_packets != packet_target ||
            subrate_changes != procedure_target ||
            frame_space_changes != procedure_target ||
            connection_rate_changes != procedure_target ||
            channel_updates != procedure_target ||
            procedure_phase != ProcedurePhase::complete)
        {
            return;
        }
#else
        if (received_packets != packet_target ||
            subrate_changes != procedure_target ||
            frame_space_changes != 2U ||
            connection_rate_changes != procedure_target)
        {
            return;
        }
#endif
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
        Serial.print("|tx=");
        Serial.print(transmitted_packets);
        Serial.print("|rx=");
        Serial.print(received_packets);
        Serial.print("|subrate=");
        Serial.print(subrate_changes);
        Serial.print("|subrate_ack=");
        Serial.print(subrate_acknowledgements);
        Serial.print("|subrate_increase_ack=");
        Serial.print(subrate_increase_acknowledgements);
        Serial.print("|boundary=");
        Serial.print(boundary_packets);
        Serial.print("|frame=");
        Serial.print(frame_space_changes);
        Serial.print("|rate=");
        Serial.print(connection_rate_changes);
        Serial.print("|channel=");
        Serial.print(channel_updates);
        Serial.print("|feature=");
        Serial.print(feature_samples);
        Serial.print("|sca=");
        Serial.print(sca_samples);
        Serial.print("|min_interval_us=");
        Serial.print(minimum_interval_us);
        Serial.print("|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        Serial.print("|packet_gap_ms=");
        Serial.print(maximum_packet_gap_ms);
        Serial.print("|procedure_gap_ms=");
        Serial.print(maximum_procedure_gap_ms);
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        session_complete = true;
    }

    /** @brief PROBE·START·STOP command를 최대 고정 길이로 해석합니다. */
    void processCommand()
    {
        if (::strcmp(command, "M32TIM|1|PROBE") == 0)
        {
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|core=");
            Serial.println(M32_TIMING_CORE_REVISION);
            return;
        }
        if (!started && acceptStart())
        {
            started = true;
            deadline_ms = k_uptime_get() + session_timeout_ms;
            Serial.print(protocol);
            Serial.print("|BEGIN|role=");
            Serial.print(roleName());
            printSuffix();
            Serial.println();
#if defined(NUCODE_M32_TIMING_CENTRAL)
            if (!BLEScan.clearFilters() || !BLEScan.filterName(peer_name) ||
                !BLEScan.start(true))
#else
            if (!BLEAdvertising.clear() ||
                !BLEAdvertising.addServiceUuid(service_uuid) ||
                !BLEAdvertising.setConnectable(true) ||
                !BLEAdvertising.setScanResponseName(true) ||
                !BLEAdvertising.start())
#endif
            {
                fail("radio_start", BLEDevice.lastDriverError());
            }
            return;
        }
        if (session_complete &&
            ::strncmp(command, stop_prefix, sizeof(stop_prefix) - 1U) == 0 &&
            ::strcmp(command + sizeof(stop_prefix) - 1U, nonce) == 0)
        {
            stop_requested = true;
            if (!connection_handle.valid() ||
                !BLEConnection.connected(connection_handle))
            {
                nucode::ble::BLESubrateParameters parameters;
                if (BLEConnection.requestSubrate(connection_handle, parameters))
                {
                    fail("stale_link_accept");
                    return;
                }
                Serial.print(protocol);
                Serial.print("|STOPPED|role=");
                Serial.print(roleName());
                printSuffix();
                Serial.println();
                stop_requested = false;
            }
            else if (!BLEConnection.disconnect(connection_handle))
            {
                fail("disconnect", BLEDevice.lastDriverError());
            }
            return;
        }
        fail("command");
    }

    /** @brief 한 줄 command를 overflow 없이 수집합니다. */
    void pollSerial()
    {
        while (Serial.available() > 0)
        {
            const int incoming = Serial.read();
            if (incoming == '\r')
            {
                continue;
            }
            if (incoming == '\n')
            {
                command[command_length] = '\0';
                processCommand();
                command_length = 0U;
                continue;
            }
            if (incoming < 0 || command_length + 1U >= sizeof(command))
            {
                fail("command_length");
                command_length = 0U;
                continue;
            }
            command[command_length++] = static_cast<char>(incoming);
        }
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    main_thread = k_current_get();
    BLEDevice.onEventInfo(onBleEvent);
#if defined(NUCODE_M32_TIMING_CENTRAL)
    BLEScan.onResult(onScanResult);
    BLEClient.onEvent(onClientEvent);
#else
    packet_value.onEvent(onPacket);
    if (!packet_service.addCharacteristic(packet_value) ||
        !BLEDevice.addService(packet_service))
    {
        fail("gatt_register", BLEDevice.lastDriverError());
    }
#endif
    if (!BLEDevice.begin(peer_name))
    {
        fail("ble_begin", BLEDevice.lastDriverError());
    }
}

void loop()
{
    BLEDevice.poll();
    pollSerial();
    if (failed)
    {
        return;
    }
    if (started && sca_samples < sca_target)
    {
        const nucode::ble::BLESleepClockAccuracySupport support =
            BLEConnection.sleepClockAccuracySupport();
        if (!support.controller_procedure || support.host_request_and_report)
        {
            fail("sca_boundary");
            return;
        }
        ++sca_samples;
    }
    if (feature_ready && feature_samples < feature_target)
    {
        nucode::ble::BLEExtendedFeatureSet features;
        if (!BLEConnection.remoteExtendedFeatures(connection_handle, features) ||
            features.status != 0U)
        {
            fail("feature_copy");
            return;
        }
        ++feature_samples;
    }
#if defined(NUCODE_M32_TIMING_CENTRAL)
    if (discovery_pending && BLEConnection.connected(connection_handle))
    {
        discovery_pending = false;
        if (!BLEClient.discover(connection_handle, service_uuid, packet_uuid))
        {
            fail("gatt_discovery", BLEDevice.lastDriverError());
            return;
        }
    }
    if (procedures_started && procedure_phase == ProcedurePhase::channel_map &&
        k_uptime_get() >= next_channel_update_ms)
    {
        if (!applyChannelMapIteration())
        {
            fail("channel_update", BLEDevice.lastDriverError());
            return;
        }
    }
#endif
    finishIfComplete();
    if (started && !session_complete && k_uptime_get() > deadline_ms)
    {
        printDiagnostic();
        fail("timeout");
    }
}
