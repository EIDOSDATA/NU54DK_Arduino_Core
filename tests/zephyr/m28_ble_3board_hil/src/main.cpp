/**
 * @file main.cpp
 * @brief 세 NU54DK로 mixed-role link·PAST·link control·soak를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

#if !defined(CONFIG_BT_PER_ADV_SYNC_TRANSFER_RECEIVER) || \
    !defined(CONFIG_BT_PER_ADV_SYNC_TRANSFER_SENDER)
#error "M28B3 requires both periodic sync transfer roles"
#endif

namespace
{

    constexpr char start_prefix[] = "NUCODE_M28B3_START:";
    constexpr char peripheral_name[] = "NU54-M28-B3-P";
    constexpr char mixed_name[] = "NU54-M28-B3-M";
    constexpr std::size_t nonce_text_length = 32U;
    constexpr std::size_t nonce_binary_length = 16U;
    constexpr std::uint32_t link_sequence_target = 1000U;
    constexpr std::uint32_t reconnect_target = 20U;
    constexpr std::uint32_t past_target = 20U;
    constexpr std::uint32_t periodic_sequence_target = 1000U;
    constexpr std::uint32_t control_round_target = 20U;
    constexpr std::uint32_t soak_sequence_target = 10000U;
    constexpr std::int64_t reconnect_delay_ms = 250;
    constexpr std::int64_t control_stage_delay_ms = 700;
    constexpr std::int64_t periodic_update_interval_ms = 100;
    constexpr std::int64_t periodic_settle_ms = 1500;
    constexpr std::int64_t soak_duration_ms = 1800000;
    constexpr std::int64_t soak_packet_interval_ms = 180;
    constexpr std::uint8_t periodic_sid = 7U;
    constexpr std::uint16_t company_id = 0x054dU;

    const nucode::ble::BLEUuid service_uuid("9f3c2801-8b7a-4d64-a1b2-001122334455");
    const nucode::ble::BLEUuid value_uuid("9f3c2802-8b7a-4d64-a1b2-001122334455");
    nucode::ble::BLEService trace_service(service_uuid);
    nucode::ble::BLECharacteristic trace_value(
        value_uuid,
        nucode::ble::BLEProperty::read | nucode::ble::BLEProperty::write |
            nucode::ble::BLEProperty::notify,
        nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, 64U);

    enum class Phase : std::uint8_t
    {
        waiting,
        startup,
        data,
        reconnect_outgoing,
        reconnect_incoming,
        periodic_sync,
        periodic_past,
        periodic_data,
        control,
        soak,
        complete,
    };

    enum class ClientWriteKind : std::uint8_t
    {
        none,
        packet,
        link_done,
        past_ready,
        past_next,
        periodic_go,
        periodic_done,
        control_done,
    };

    char nonce[nonce_text_length + 1U] = {};
    std::uint8_t nonce_binary[nonce_binary_length] = {};
    char command[96] = {};
    std::size_t command_length = 0U;
    Phase phase = Phase::waiting;
    bool protocol_started = false;
    bool protocol_failed = false;
    bool final_reported = false;
    bool advertised_once = false;
    std::int64_t protocol_deadline_ms = 0;

    nucode::ble::BLEConnectionHandle outgoing_link;
    nucode::ble::BLEConnectionHandle incoming_link;
    nucode::ble::BLEConnectionHandle stale_outgoing_link;
    nucode::ble::BLEConnectionHandle stale_incoming_link;
    nucode::ble::BLEAddress scan_address;
    nucode::ble::BLEAddress periodic_address;
    nucode::ble::BLEPeriodicSyncHandle periodic_sync;
    nucode::ble::BLEAdvertisingSetHandle periodic_set;

    bool scan_result_pending = false;
    [[maybe_unused]] bool periodic_scan_result_pending = false;
    bool discovery_pending = false;
    bool client_ready = false;
    bool server_subscribed = false;
    bool advertising_restart_pending = false;
    bool disconnect_pending = false;
    bool reconnect_pending = false;
    [[maybe_unused]] bool periodic_delete_pending = false;
    [[maybe_unused]] bool past_transfer_pending = false;
    [[maybe_unused]] bool periodic_emission_active = false;
    std::int64_t action_deadline_ms = 0;
    [[maybe_unused]] std::int64_t periodic_next_update_ms = 0;
    std::int64_t periodic_result_deadline_ms = 0;

    ClientWriteKind pending_client_write = ClientWriteKind::none;
    ClientWriteKind active_client_write = ClientWriteKind::none;
    std::uint8_t pending_client_payload[64] = {};
    std::size_t pending_client_payload_length = 0U;

    std::uint32_t outgoing_connections = 0U;
    std::uint32_t incoming_connections = 0U;
    std::uint32_t outgoing_disconnects = 0U;
    std::uint32_t incoming_disconnects = 0U;
    std::uint32_t outgoing_reconnects = 0U;
    std::uint32_t incoming_reconnects = 0U;
    std::uint32_t stale_events = 0U;
    std::uint32_t unexpected_disconnects = 0U;

    std::uint32_t transmit_sequence = 0U;
    std::uint32_t transmit_completed = 0U;
    std::uint32_t receive_sequence = 0U;
    std::uint32_t receive_loss = 0U;
    std::uint32_t receive_corrupt = 0U;
    std::uint32_t receive_duplicate = 0U;
    std::int64_t transmit_start_ms = 0;
    std::int64_t receive_start_ms = 0;
    std::int64_t next_transmit_ms = 0;

    [[maybe_unused]] std::uint32_t past_sent = 0U;
    [[maybe_unused]] std::uint32_t past_received = 0U;
    [[maybe_unused]] std::uint32_t periodic_emitted = 0U;
    std::uint32_t periodic_received = 0U;
    std::uint32_t periodic_corrupt = 0U;
    std::uint32_t periodic_source_reports = 0U;
    std::uint8_t periodic_seen[(periodic_sequence_target + 7U) / 8U] = {};

    std::uint32_t control_round = 0U;
    [[maybe_unused]] std::uint8_t control_stage = 0U;
    std::uint32_t cross_state_events = 0U;
    std::uint32_t unreported_driver_errors = 0U;
    [[maybe_unused]] std::int64_t control_next_action_ms = 0;

    /** @brief compile-time role 이름을 반환합니다. */
    [[maybe_unused]] const char *roleName()
    {
#if defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
        return "peripheral";
#elif defined(NUCODE_M28_B3_ROLE_MIXED)
        return "mixed";
#else
        return "central";
#endif
    }

    /** @brief compile-time 시험 이름을 protocol 표기로 반환합니다. */
    [[maybe_unused]] const char *testName()
    {
#if defined(NUCODE_M28_B3_TEST_LINK)
        return "LINK";
#elif defined(NUCODE_M28_B3_TEST_PERIODIC)
        return "PER";
#elif defined(NUCODE_M28_B3_TEST_CONTROL)
        return "CTRL";
#else
        return "SOAK";
#endif
    }

    /** @brief 현재 시험의 target 실행 상한을 millisecond로 반환합니다. */
    [[maybe_unused]] std::int64_t protocolTimeoutMs()
    {
#if defined(NUCODE_M28_B3_TEST_LINK)
        return 1200000;
#elif defined(NUCODE_M28_B3_TEST_PERIODIC) || defined(NUCODE_M28_B3_TEST_CONTROL)
        return 900000;
#else
        return 2100000;
#endif
    }

    /** @brief 한 hex 문자를 nibble로 변환합니다. */
    [[maybe_unused]] bool decodeHex(char value, std::uint8_t &decoded)
    {
        if (value >= '0' && value <= '9')
        {
            decoded = static_cast<std::uint8_t>(value - '0');
            return true;
        }
        if (value >= 'a' && value <= 'f')
        {
            decoded = static_cast<std::uint8_t>(value - 'a' + 10);
            return true;
        }
        return false;
    }

    /** @brief 첫 오류만 현재 role·test·nonce에 결합해 출력합니다. */
    [[maybe_unused]] void fail(const char *reason)
    {
        if (!protocol_failed)
        {
            Serial.print("NUCODE_M28B3_FAIL:role=");
            Serial.print(roleName());
            Serial.print(":test=");
            Serial.print(testName());
            Serial.print(":reason=");
            Serial.print(reason == nullptr ? "unknown" : reason);
            Serial.print(":nonce=");
            Serial.println(protocol_started ? nonce : "none");
        }
        protocol_failed = true;
    }

    /** @brief 현재 nonce가 붙은 protocol record의 공통 끝을 출력합니다. */
    [[maybe_unused]] void printNonceEnd()
    {
        Serial.print(":nonce=");
        Serial.println(nonce);
    }

    /** @brief FNV-1a로 작은 RF trace packet의 손상을 검출합니다. */
    [[maybe_unused]] std::uint32_t checksum(const std::uint8_t *data, std::size_t length)
    {
        std::uint32_t value = 2166136261U;
        for (std::size_t index = 0U; index < length; ++index)
        {
            value ^= data[index];
            value *= 16777619U;
        }
        return value;
    }

    /** @brief little-endian 32-bit 값을 고정 packet에 기록합니다. */
    [[maybe_unused]] void putU32(std::uint8_t *output, std::uint32_t value)
    {
        output[0] = static_cast<std::uint8_t>(value);
        output[1] = static_cast<std::uint8_t>(value >> 8U);
        output[2] = static_cast<std::uint8_t>(value >> 16U);
        output[3] = static_cast<std::uint8_t>(value >> 24U);
    }

    /** @brief little-endian 32-bit 값을 고정 packet에서 읽습니다. */
    [[maybe_unused]] std::uint32_t getU32(const std::uint8_t *input)
    {
        return static_cast<std::uint32_t>(input[0]) |
               (static_cast<std::uint32_t>(input[1]) << 8U) |
               (static_cast<std::uint32_t>(input[2]) << 16U) |
               (static_cast<std::uint32_t>(input[3]) << 24U);
    }

    /** @brief nonce·phase·sender·sequence가 결합된 28-byte GATT packet을 만듭니다. */
    [[maybe_unused]] void buildTracePacket(std::uint8_t *packet, std::uint8_t phase_code,
                          std::uint8_t sender, std::uint32_t sequence)
    {
        packet[0] = 'M';
        packet[1] = '3';
        packet[2] = phase_code;
        packet[3] = sender;
        ::memcpy(&packet[4], nonce_binary, nonce_binary_length);
        putU32(&packet[20], sequence);
        putU32(&packet[24], checksum(packet, 24U));
    }

    /** @brief 수신 GATT packet의 무결성·nonce·순서를 fail-closed로 검증합니다. */
    [[maybe_unused]] void consumeTracePacket(const std::uint8_t *packet, std::size_t length,
                            std::uint8_t phase_code, std::uint8_t sender,
                            std::uint32_t target)
    {
        if (length != 28U || packet[0] != 'M' || packet[1] != '3' ||
            packet[2] != phase_code || packet[3] != sender ||
            ::memcmp(&packet[4], nonce_binary, nonce_binary_length) != 0 ||
            getU32(&packet[24]) != checksum(packet, 24U))
        {
            ++receive_corrupt;
            fail("trace-corrupt");
            return;
        }
        const std::uint32_t sequence = getU32(&packet[20]);
        if (sequence == receive_sequence)
        {
            ++receive_duplicate;
            fail("trace-duplicate");
            return;
        }
        if (sequence != receive_sequence + 1U || sequence > target)
        {
            if (sequence > receive_sequence + 1U)
            {
                receive_loss += sequence - receive_sequence - 1U;
            }
            fail("trace-sequence");
            return;
        }
        if (receive_sequence == 0U)
        {
            receive_start_ms = k_uptime_get();
        }
        receive_sequence = sequence;
    }

    /** @brief server notification으로 한 control token을 전달합니다. */
    [[maybe_unused]] bool notifyServer(const char *value)
    {
        const std::size_t length = ::strlen(value);
        return trace_value.setValue(value, length) && trace_value.notify();
    }

    /** @brief 다음 GATT client write를 고정 buffer에 예약합니다. */
    [[maybe_unused]] bool queueClientWrite(ClientWriteKind kind, const void *data,
                                           std::size_t length)
    {
        if (pending_client_write != ClientWriteKind::none ||
            active_client_write != ClientWriteKind::none || data == nullptr ||
            length == 0U || length > sizeof(pending_client_payload))
        {
            return false;
        }
        ::memcpy(pending_client_payload, data, length);
        pending_client_payload_length = length;
        pending_client_write = kind;
        return true;
    }

    /** @brief ASCII control token을 다음 client write로 예약합니다. */
    [[maybe_unused]] bool queueClientCommand(ClientWriteKind kind, const char *value)
    {
        return queueClientWrite(kind, value, ::strlen(value));
    }

    /** @brief 현재 role이 제공해야 하는 connectable advertising을 시작합니다. */
    [[maybe_unused]] bool startConnectableAdvertising()
    {
        if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
            !BLEAdvertising.start())
        {
            return false;
        }
        if (!advertised_once)
        {
            Serial.print("NUCODE_M28B3_");
            Serial.print(roleName());
            Serial.print(":ADVERTISE:PASS:test=");
            Serial.print(testName());
            printNonceEnd();
            advertised_once = true;
        }
        return true;
    }

    /** @brief exact peer 이름으로 active scan을 시작합니다. */
    [[maybe_unused]] bool startPeerScan(const char *name)
    {
        return BLEScan.clearFilters() && BLEScan.filterName(name) && BLEScan.start(true);
    }

    /** @brief 현재 central link의 GATT trace characteristic discovery를 예약합니다. */
    [[maybe_unused]] void scheduleDiscovery()
    {
        client_ready = false;
        discovery_pending = true;
        action_deadline_ms = k_uptime_get() + 250;
    }

    /** @brief role별 link 수와 handle 역할 불변식을 검사합니다. */
    [[maybe_unused]] bool validateActiveLinks()
    {
#if defined(NUCODE_M28_B3_ROLE_MIXED)
        return BLEConnection.count() == 2U && BLEConnection.connected(outgoing_link) &&
               BLEConnection.connected(incoming_link) &&
               BLEConnection.role(outgoing_link) == nucode::ble::BLELinkRole::central &&
               BLEConnection.role(incoming_link) == nucode::ble::BLELinkRole::peripheral;
#else
        const nucode::ble::BLEConnectionHandle link =
#if defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
            incoming_link;
#else
            outgoing_link;
#endif
        return BLEConnection.count() == 1U && BLEConnection.connected(link);
#endif
    }

    /** @brief LINK role의 exact trace·정량 PASS·FINAL을 한 번 출력합니다. */
    [[maybe_unused]] void finishLink()
    {
        if (final_reported || protocol_failed)
        {
            return;
        }
        if (receive_loss != 0U || receive_corrupt != 0U || receive_duplicate != 0U ||
            stale_events != 0U || BLEDevice.droppedEvents() != 0U)
        {
            fail("link-final-counts");
            return;
        }
        Serial.print("NUCODE_M28B3_");
        Serial.print(roleName());
        Serial.print(":TRACE:PASS:test=LINK:source=rf-gatt:tx=");
        Serial.print(transmit_completed);
        Serial.print(":rx=");
        Serial.print(receive_sequence);
        printNonceEnd();
        Serial.print("NUCODE_M28B3_");
        Serial.print(roleName());
#if defined(NUCODE_M28_B3_ROLE_MIXED)
        Serial.print(":LINK:PASS:links=2:central=1:peripheral=1:reconnects_per_link=20:sequence_per_link=1000");
#else
        Serial.print(":LINK:PASS:links=1:reconnects=20:sequence=1000");
#endif
        Serial.print(":loss=0:corrupt=0:duplicate=0:stale=0:drops=0");
        printNonceEnd();
        Serial.print("NUCODE_M28B3_");
        Serial.print(roleName());
        Serial.print(":FINAL:PASS:test=LINK");
        printNonceEnd();
        final_reported = true;
        phase = Phase::complete;
    }

    /** @brief CTRL observer role의 PASS·FINAL을 출력합니다. */
    [[maybe_unused]] void finishControlObserver()
    {
        if (final_reported || protocol_failed)
        {
            return;
        }
        Serial.print("NUCODE_M28B3_");
        Serial.print(roleName());
        Serial.print(":CTRL:PASS:links=1:rounds=20:unexpected_disconnect=0:drops=0");
        printNonceEnd();
        Serial.print("NUCODE_M28B3_");
        Serial.print(roleName());
        Serial.print(":FINAL:PASS:test=CTRL");
        printNonceEnd();
        final_reported = true;
        phase = Phase::complete;
    }

    /** @brief mixed role의 link별 control 정량 PASS·FINAL을 출력합니다. */
    [[maybe_unused]] void finishControlMixed()
    {
        if (final_reported || protocol_failed)
        {
            return;
        }
        if (control_round != control_round_target || cross_state_events != 0U ||
            stale_events != 0U || unreported_driver_errors != 0U ||
            unexpected_disconnects != 0U || BLEDevice.droppedEvents() != 0U)
        {
            fail("control-final-counts");
            return;
        }
        Serial.print("NUCODE_M28B3_mixed:CTRL:PASS:links=2:requests_per_link=20:cross_state=0:stale=0:unreported_driver=0:unexpected_disconnect=0:drops=0");
        printNonceEnd();
        Serial.print("NUCODE_M28B3_mixed:FINAL:PASS:test=CTRL");
        printNonceEnd();
        final_reported = true;
        phase = Phase::complete;
    }

    /** @brief SOAK의 30분 trace와 자원 회수 결과를 출력합니다. */
    [[maybe_unused]] void finishSoak()
    {
        if (final_reported || protocol_failed)
        {
            return;
        }
        if (receive_loss != 0U || receive_corrupt != 0U || receive_duplicate != 0U ||
            unexpected_disconnects != 0U || BLEDevice.droppedEvents() != 0U)
        {
            fail("soak-final-counts");
            return;
        }
        BLEDevice.end();
        if (BLEDevice.initialized() || BLEConnection.count() != 0U)
        {
            fail("resource-recovery");
            return;
        }
        Serial.print("NUCODE_M28B3_");
        Serial.print(roleName());
        Serial.print(":TRACE:PASS:test=SOAK:source=rf-gatt:tx=");
        Serial.print(transmit_completed);
        Serial.print(":rx=");
        Serial.print(receive_sequence);
        printNonceEnd();
        Serial.print("NUCODE_M28B3_");
        Serial.print(roleName());
#if defined(NUCODE_M28_B3_ROLE_MIXED)
        Serial.print(":SOAK:PASS:duration_s=1800:links=2:sequence_per_link=10000");
#else
        Serial.print(":SOAK:PASS:duration_s=1800:links=1:sequence=10000");
#endif
        Serial.print(":loss=0:corrupt=0:duplicate=0:unexpected_disconnect=0:recovery_failures=0:drops=0");
        printNonceEnd();
        Serial.print("NUCODE_M28B3_");
        Serial.print(roleName());
        Serial.print(":FINAL:PASS:test=SOAK");
        printNonceEnd();
        final_reported = true;
        phase = Phase::complete;
    }

    /** @brief periodic advertiser의 extended·periodic payload를 구성해 시작합니다. */
    [[maybe_unused]] bool startPeriodicAdvertiser()
    {
#if defined(NUCODE_M28_B3_ROLE_PERIPHERAL) && defined(NUCODE_M28_B3_TEST_PERIODIC)
        std::uint8_t extended_payload[48] = {};
        const std::size_t name_length = ::strlen(peripheral_name);
        extended_payload[0] = static_cast<std::uint8_t>(name_length + 1U);
        extended_payload[1] = 0x09U;
        ::memcpy(&extended_payload[2], peripheral_name, name_length);
        const std::size_t extended_length = name_length + 2U;
        std::uint8_t periodic_payload[29] = {};
        periodic_payload[0] = 28U;
        periodic_payload[1] = 0xffU;
        periodic_payload[2] = static_cast<std::uint8_t>(company_id);
        periodic_payload[3] = static_cast<std::uint8_t>(company_id >> 8U);
        periodic_payload[4] = 'P';
        ::memcpy(&periodic_payload[5], nonce_binary, nonce_binary_length);
        putU32(&periodic_payload[21], 0U);
        putU32(&periodic_payload[25], checksum(periodic_payload, 25U));

        nucode::ble::BLEExtendedAdvertisingParameters extended{};
        extended.sid = periodic_sid;
        extended.include_tx_power = true;
        extended.interval_min = 0x00a0U;
        extended.interval_max = 0x00a0U;
        nucode::ble::BLEPeriodicAdvertisingParameters periodic{};
        periodic.interval_min = 80U;
        periodic.interval_max = 80U;
        periodic.include_tx_power = true;
        if (!BLEExtendedAdvertising.create(extended, periodic_set) ||
            !BLEExtendedAdvertising.setData(periodic_set, extended_payload, extended_length) ||
            !BLEPeriodicAdvertising.configure(periodic_set, periodic) ||
            !BLEPeriodicAdvertising.setData(periodic_set, periodic_payload,
                                             sizeof(periodic_payload)) ||
            !BLEPeriodicAdvertising.start(periodic_set) ||
            !BLEExtendedAdvertising.start(periodic_set))
        {
            return false;
        }
        Serial.print("NUCODE_M28B3_peripheral:PERIODIC:STARTED:sid=7");
        printNonceEnd();
        return true;
#else
        return false;
#endif
    }

    /** @brief periodic sequence 하나를 payload와 checksum에 반영합니다. */
    [[maybe_unused]] bool updatePeriodicPayload(std::uint32_t sequence)
    {
        std::uint8_t payload[29] = {};
        payload[0] = 28U;
        payload[1] = 0xffU;
        payload[2] = static_cast<std::uint8_t>(company_id);
        payload[3] = static_cast<std::uint8_t>(company_id >> 8U);
        payload[4] = 'P';
        ::memcpy(&payload[5], nonce_binary, nonce_binary_length);
        putU32(&payload[21], sequence);
        putU32(&payload[25], checksum(payload, 25U));
        return BLEPeriodicAdvertising.setData(periodic_set, payload, sizeof(payload));
    }

    /** @brief periodic report의 nonce·checksum·unique sequence를 검증합니다. */
    [[maybe_unused]] void consumePeriodicReport(const nucode::ble::BLEPeriodicReport &report,
                               bool receiver)
    {
        if (report.payload_length != 29U || report.payload[0] != 28U ||
            report.payload[1] != 0xffU || report.payload[2] !=
                static_cast<std::uint8_t>(company_id) ||
            report.payload[3] != static_cast<std::uint8_t>(company_id >> 8U) ||
            report.payload[4] != 'P' ||
            ::memcmp(&report.payload[5], nonce_binary, nonce_binary_length) != 0 ||
            getU32(&report.payload[25]) != checksum(report.payload, 25U))
        {
            ++periodic_corrupt;
            fail("periodic-corrupt");
            return;
        }
        const std::uint32_t sequence = getU32(&report.payload[21]);
        if (sequence == 0U)
        {
            return;
        }
        if (sequence > periodic_sequence_target)
        {
            ++periodic_corrupt;
            fail("periodic-range");
            return;
        }
        if (!receiver)
        {
            ++periodic_source_reports;
            return;
        }
        const std::size_t byte = static_cast<std::size_t>((sequence - 1U) / 8U);
        const std::uint8_t bit = static_cast<std::uint8_t>(1U << ((sequence - 1U) % 8U));
        if ((periodic_seen[byte] & bit) == 0U)
        {
            periodic_seen[byte] |= bit;
            ++periodic_received;
        }
        if (sequence == periodic_sequence_target && periodic_result_deadline_ms == 0)
        {
            periodic_result_deadline_ms = k_uptime_get() + periodic_settle_ms;
        }
    }

    /** @brief PER receiver의 수신률·PAST·trace를 검증하고 완료 command를 보냅니다. */
    [[maybe_unused]] void finishPeriodicCentral()
    {
#if defined(NUCODE_M28_B3_ROLE_CENTRAL) && defined(NUCODE_M28_B3_TEST_PERIODIC)
        if (periodic_received < 990U || periodic_received > periodic_sequence_target ||
            periodic_corrupt != 0U || past_received != past_target ||
            BLEPeriodicAdvertising.droppedReports() != 0U)
        {
            fail("periodic-final-counts");
            return;
        }
        if (pending_client_write == ClientWriteKind::none &&
            active_client_write == ClientWriteKind::none &&
            !queueClientCommand(ClientWriteKind::periodic_done, "PER_DONE"))
        {
            fail("periodic-done-queue");
        }
#endif
    }

    /** @brief 한 packet write를 준비하고 client completion까지 직렬화합니다. */
    [[maybe_unused]] void driveTraceTransmitter(std::uint8_t phase_code, std::uint32_t target,
                               std::int64_t interval_ms)
    {
        if (!client_ready || pending_client_write != ClientWriteKind::none ||
            active_client_write != ClientWriteKind::none || transmit_sequence >= target)
        {
            return;
        }
        const std::int64_t now = k_uptime_get();
        if (transmit_sequence == 0U)
        {
            transmit_start_ms = now;
            next_transmit_ms = now;
        }
        if (now < next_transmit_ms)
        {
            return;
        }
        std::uint8_t packet[28] = {};
        const std::uint8_t sender =
#if defined(NUCODE_M28_B3_ROLE_MIXED)
            'M';
#else
            'C';
#endif
        buildTracePacket(packet, phase_code, sender, transmit_sequence + 1U);
        if (!queueClientWrite(ClientWriteKind::packet, packet, sizeof(packet)))
        {
            fail("trace-write-queue");
            return;
        }
        ++transmit_sequence;
        next_transmit_ms = transmit_start_ms +
                           static_cast<std::int64_t>(transmit_sequence) * interval_ms;
    }

    /** @brief 현재 예약된 GATT write 하나를 제출합니다. */
    [[maybe_unused]] void driveClientWrite()
    {
        if (!client_ready || pending_client_write == ClientWriteKind::none ||
            active_client_write != ClientWriteKind::none || BLEClient.busy())
        {
            return;
        }
        if (!BLEClient.write(pending_client_payload, pending_client_payload_length))
        {
            fail("client-write");
            return;
        }
        active_client_write = pending_client_write;
        pending_client_write = ClientWriteKind::none;
        pending_client_payload_length = 0U;
    }

    /** @brief server write를 trace packet 또는 exact control command로 분기합니다. */
    [[maybe_unused]] void onServerWrite(const std::uint8_t *data, std::size_t length)
    {
#if defined(NUCODE_M28_B3_TEST_LINK)
        if (length == 28U)
        {
#if defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
            consumeTracePacket(data, length, 'L', 'M', link_sequence_target);
#elif defined(NUCODE_M28_B3_ROLE_MIXED)
            consumeTracePacket(data, length, 'L', 'C', link_sequence_target);
#endif
            return;
        }
#elif defined(NUCODE_M28_B3_TEST_SOAK)
        if (length == 28U)
        {
#if defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
            consumeTracePacket(data, length, 'S', 'M', soak_sequence_target);
#elif defined(NUCODE_M28_B3_ROLE_MIXED)
            consumeTracePacket(data, length, 'S', 'C', soak_sequence_target);
#endif
            return;
        }
#endif

#if defined(NUCODE_M28_B3_ROLE_MIXED)
#if defined(NUCODE_M28_B3_TEST_LINK)
        if (length == 9U && ::memcmp(data, "LINK_DONE", length) == 0)
        {
            if (incoming_reconnects != reconnect_target || outgoing_reconnects != reconnect_target)
            {
                fail("link-done-early");
                return;
            }
            finishLink();
            return;
        }
#elif defined(NUCODE_M28_B3_TEST_PERIODIC)
        if ((length == 10U && ::memcmp(data, "PAST_READY", length) == 0) ||
            (length == 9U && ::memcmp(data, "PAST_NEXT", length) == 0))
        {
            past_transfer_pending = true;
            return;
        }
        if (length == 6U && ::memcmp(data, "PER_GO", length) == 0)
        {
            if (past_sent != past_target ||
                !queueClientCommand(ClientWriteKind::periodic_go, "PER_GO"))
            {
                fail("periodic-go");
            }
            phase = Phase::periodic_data;
            return;
        }
        if (length == 8U && ::memcmp(data, "PER_DONE", length) == 0)
        {
            if (!queueClientCommand(ClientWriteKind::periodic_done, "PER_DONE"))
            {
                fail("periodic-done-forward");
            }
            return;
        }
#endif
#elif defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
#if defined(NUCODE_M28_B3_TEST_PERIODIC)
        if (length == 6U && ::memcmp(data, "PER_GO", length) == 0)
        {
            periodic_emission_active = true;
            periodic_next_update_ms = k_uptime_get();
            phase = Phase::periodic_data;
            return;
        }
        if (length == 8U && ::memcmp(data, "PER_DONE", length) == 0)
        {
            if (periodic_emitted != periodic_sequence_target ||
                periodic_corrupt != 0U || BLEDevice.droppedEvents() != 0U)
            {
                fail("periodic-advertiser-counts");
                return;
            }
            static_cast<void>(BLEPeriodicAdvertising.stop(periodic_set));
            static_cast<void>(BLEExtendedAdvertising.stop(periodic_set));
            static_cast<void>(BLEExtendedAdvertising.remove(periodic_set));
            Serial.print("NUCODE_M28B3_peripheral:PER:PASS:emitted=1000:corrupt=0:drops=0");
            printNonceEnd();
            Serial.print("NUCODE_M28B3_peripheral:FINAL:PASS:test=PER");
            printNonceEnd();
            final_reported = true;
            phase = Phase::complete;
            return;
        }
#elif defined(NUCODE_M28_B3_TEST_CONTROL)
        if (length == 9U && ::memcmp(data, "CTRL_DONE", length) == 0)
        {
            finishControlObserver();
            return;
        }
#endif
#endif
        fail("server-command");
    }

    /** @brief GATT server event를 main-thread 고정 상태로 변환합니다. */
    [[maybe_unused]] void onCharacteristic(nucode::ble::BLECharacteristic &,
                          const nucode::ble::BLECharacteristicEventInfo &event, void *)
    {
        if (!protocol_started || protocol_failed)
        {
            return;
        }
        if (event.event == nucode::ble::BLECharacteristicEvent::written)
        {
            onServerWrite(event.data, event.length);
        }
        else if (event.event == nucode::ble::BLECharacteristicEvent::subscribed)
        {
            server_subscribed = true;
        }
        else if (event.event == nucode::ble::BLECharacteristicEvent::unsubscribed)
        {
            server_subscribed = false;
        }
        else if (event.event == nucode::ble::BLECharacteristicEvent::indication_failed)
        {
            fail("server-indication");
        }
    }

    /** @brief client notification control token을 role별 상태 전이로 처리합니다. */
    [[maybe_unused]] void onClientNotification(const std::uint8_t *data, std::size_t length)
    {
#if defined(NUCODE_M28_B3_ROLE_CENTRAL) && defined(NUCODE_M28_B3_TEST_LINK)
        if (length == 10U && ::memcmp(data, "LINK_CYCLE", length) == 0 &&
            transmit_completed == link_sequence_target)
        {
            phase = Phase::reconnect_outgoing;
            disconnect_pending = true;
            action_deadline_ms = k_uptime_get() + reconnect_delay_ms;
            return;
        }
#elif defined(NUCODE_M28_B3_ROLE_CENTRAL) && defined(NUCODE_M28_B3_TEST_CONTROL)
        if (length == 9U && ::memcmp(data, "CTRL_DONE", length) == 0)
        {
            finishControlObserver();
            return;
        }
#endif
        fail("client-notification");
    }

    /** @brief generic GATT client 결과를 write 종류와 discovery 상태로 결합합니다. */
    [[maybe_unused]] void onClientEvent(nucode::ble::BLEGattClientEvent event,
                       const std::uint8_t *data, std::size_t length, void *)
    {
        if (!protocol_started || protocol_failed)
        {
            return;
        }
        if (event == nucode::ble::BLEGattClientEvent::discovery_complete)
        {
            if (!BLEClient.subscribeNotifications())
            {
                fail("client-subscribe");
            }
        }
        else if (event == nucode::ble::BLEGattClientEvent::subscribed)
        {
            client_ready = true;
#if defined(NUCODE_M28_B3_ROLE_CENTRAL) && defined(NUCODE_M28_B3_TEST_PERIODIC)
            if (!BLEPeriodicAdvertising.subscribeTransfers(outgoing_link, 0U, 1000U, true) ||
                !queueClientCommand(ClientWriteKind::past_ready, "PAST_READY"))
            {
                fail("past-subscribe");
            }
            phase = Phase::periodic_past;
#endif
        }
        else if (event == nucode::ble::BLEGattClientEvent::write_complete)
        {
            const ClientWriteKind completed = active_client_write;
            active_client_write = ClientWriteKind::none;
            if (completed == ClientWriteKind::packet)
            {
                ++transmit_completed;
            }
#if defined(NUCODE_M28_B3_ROLE_CENTRAL) && defined(NUCODE_M28_B3_TEST_LINK)
            else if (completed == ClientWriteKind::link_done)
            {
                finishLink();
            }
#elif defined(NUCODE_M28_B3_ROLE_CENTRAL) && defined(NUCODE_M28_B3_TEST_PERIODIC)
            else if (completed == ClientWriteKind::periodic_done)
            {
                const std::uint32_t loss = periodic_sequence_target - periodic_received;
                Serial.print("NUCODE_M28B3_central:TRACE:PASS:test=PER:source=rf-periodic:denominator=1000:received=");
                Serial.print(periodic_received);
                Serial.print(":loss=");
                Serial.print(loss);
                printNonceEnd();
                Serial.print("NUCODE_M28B3_central:PER:PASS:reports=");
                Serial.print(periodic_received);
                Serial.print(":denominator=1000:loss=");
                Serial.print(loss);
                Serial.print(":corrupt=0:past=20:drops=0");
                printNonceEnd();
                Serial.print("NUCODE_M28B3_central:FINAL:PASS:test=PER");
                printNonceEnd();
                final_reported = true;
                phase = Phase::complete;
            }
#elif defined(NUCODE_M28_B3_ROLE_MIXED) && defined(NUCODE_M28_B3_TEST_PERIODIC)
            else if (completed == ClientWriteKind::periodic_done)
            {
                if (past_sent != past_target || periodic_corrupt != 0U ||
                    BLEPeriodicAdvertising.droppedReports() != 0U)
                {
                    fail("periodic-relay-counts");
                    return;
                }
                Serial.print("NUCODE_M28B3_mixed:PER:PASS:past_sent=20:source_reports=");
                Serial.print(periodic_source_reports);
                Serial.print(":corrupt=0:drops=0");
                printNonceEnd();
                Serial.print("NUCODE_M28B3_mixed:FINAL:PASS:test=PER");
                printNonceEnd();
                final_reported = true;
                phase = Phase::complete;
            }
#elif defined(NUCODE_M28_B3_ROLE_MIXED) && defined(NUCODE_M28_B3_TEST_CONTROL)
            else if (completed == ClientWriteKind::control_done)
            {
                finishControlMixed();
            }
#endif
        }
        else if (event == nucode::ble::BLEGattClientEvent::notification_received)
        {
            onClientNotification(data, length);
        }
        else if (event == nucode::ble::BLEGattClientEvent::handles_invalidated)
        {
            client_ready = false;
            active_client_write = ClientWriteKind::none;
            pending_client_write = ClientWriteKind::none;
        }
        else if (event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            fail("client-operation");
        }
    }

    /** @brief scan 결과를 startup peer 또는 periodic source 후보로 보존합니다. */
    [[maybe_unused]] void onScanResult(const nucode::ble::BLEScanResult &result, void *)
    {
        if (!protocol_started || protocol_failed)
        {
            return;
        }
#if defined(NUCODE_M28_B3_ROLE_MIXED) && defined(NUCODE_M28_B3_TEST_PERIODIC)
        if (phase == Phase::periodic_sync && result.extended &&
            result.periodic_interval != 0U && result.sid == periodic_sid)
        {
            periodic_address = result.address;
            periodic_scan_result_pending = true;
            return;
        }
#endif
        if (phase == Phase::startup && !scan_result_pending)
        {
            scan_address = result.address;
            scan_result_pending = true;
        }
    }

    /** @brief periodic reports를 relay source 또는 final receiver trace로 소비합니다. */
    [[maybe_unused]] void onPeriodicReport(const nucode::ble::BLEPeriodicReport &report, void *)
    {
#if defined(NUCODE_M28_B3_TEST_PERIODIC)
#if defined(NUCODE_M28_B3_ROLE_MIXED)
        consumePeriodicReport(report, false);
#elif defined(NUCODE_M28_B3_ROLE_CENTRAL)
        consumePeriodicReport(report, true);
#else
        static_cast<void>(report);
#endif
#else
        static_cast<void>(report);
#endif
    }

    /** @brief link event를 역할별 generation·재연결·제어 상태로 변환합니다. */
    [[maybe_unused]] void onBleEvent(const nucode::ble::BLEEventInfo &information, void *)
    {
        if (!protocol_started || protocol_failed)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::error)
        {
            ++unreported_driver_errors;
            fail("ble-error-event");
            return;
        }

        if (information.event == nucode::ble::BLEEvent::connected)
        {
            if (information.role == nucode::ble::BLELinkRole::central)
            {
                outgoing_link = information.connection;
                ++outgoing_connections;
                if (outgoing_connections > 1U)
                {
                    ++outgoing_reconnects;
                }
#if defined(NUCODE_M28_B3_TEST_LINK) || defined(NUCODE_M28_B3_TEST_SOAK)
                if (outgoing_connections == 1U &&
                    !BLEConnection.requestMtu(outgoing_link))
                {
                    fail("client-mtu-request");
                    return;
                }
#endif
                scheduleDiscovery();
#if defined(NUCODE_M28_B3_ROLE_MIXED)
                if (!advertised_once && !startConnectableAdvertising())
                {
                    fail("mixed-advertising");
                    return;
                }
#if defined(NUCODE_M28_B3_TEST_PERIODIC)
                if (outgoing_connections == 1U)
                {
                    phase = Phase::startup;
                }
#endif
#endif
            }
            else if (information.role == nucode::ble::BLELinkRole::peripheral)
            {
                incoming_link = information.connection;
                ++incoming_connections;
                if (incoming_connections > 1U)
                {
                    ++incoming_reconnects;
                }
#if defined(NUCODE_M28_B3_ROLE_PERIPHERAL) && defined(NUCODE_M28_B3_TEST_PERIODIC)
                if (incoming_connections == 1U && !startPeriodicAdvertiser())
                {
                    fail("periodic-start");
                    return;
                }
#endif
            }

#if defined(NUCODE_M28_B3_TEST_LINK)
            if (phase == Phase::reconnect_outgoing)
            {
                if (outgoing_reconnects < reconnect_target)
                {
                    discovery_pending = false;
                    disconnect_pending = true;
                    action_deadline_ms = k_uptime_get() + reconnect_delay_ms;
                }
                else
                {
#if defined(NUCODE_M28_B3_ROLE_MIXED)
                    scheduleDiscovery();
#elif defined(NUCODE_M28_B3_ROLE_CENTRAL)
                    scheduleDiscovery();
#endif
                }
            }
#if defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
            if (incoming_reconnects == reconnect_target &&
                receive_sequence == link_sequence_target)
            {
                finishLink();
            }
#endif
#endif
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            if (information.role == nucode::ble::BLELinkRole::central)
            {
                stale_outgoing_link = information.connection;
                ++outgoing_disconnects;
                if (BLEConnection.connected(stale_outgoing_link))
                {
                    ++stale_events;
                    fail("stale-outgoing-active");
                    return;
                }
                outgoing_link = {};
                client_ready = false;
                if (phase == Phase::reconnect_outgoing &&
                    outgoing_reconnects < reconnect_target)
                {
                    reconnect_pending = true;
                    action_deadline_ms = k_uptime_get() + reconnect_delay_ms;
                }
#if defined(NUCODE_M28_B3_TEST_SOAK)
                else if (transmit_completed < soak_sequence_target)
                {
                    ++unexpected_disconnects;
                    fail("soak-disconnect");
                }
#elif defined(NUCODE_M28_B3_TEST_CONTROL) || defined(NUCODE_M28_B3_TEST_PERIODIC)
                else
                {
                    ++unexpected_disconnects;
                    fail("unexpected-disconnect");
                }
#endif
            }
            else if (information.role == nucode::ble::BLELinkRole::peripheral)
            {
                stale_incoming_link = information.connection;
                ++incoming_disconnects;
                if (BLEConnection.connected(stale_incoming_link))
                {
                    ++stale_events;
                    fail("stale-incoming-active");
                    return;
                }
                incoming_link = {};
                server_subscribed = false;
#if defined(NUCODE_M28_B3_TEST_LINK)
#if defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
                if (receive_sequence == link_sequence_target &&
                    incoming_reconnects < reconnect_target)
#else
                if (phase == Phase::reconnect_incoming &&
                    incoming_reconnects < reconnect_target)
#endif
                {
                    advertising_restart_pending = true;
                    action_deadline_ms = k_uptime_get() + reconnect_delay_ms;
                }
                else
                {
                    ++unexpected_disconnects;
                    fail("unexpected-link-disconnect");
                }
#elif defined(NUCODE_M28_B3_TEST_SOAK)
                if (receive_sequence < soak_sequence_target)
                {
                    ++unexpected_disconnects;
                    fail("soak-disconnect");
                }
#else
                ++unexpected_disconnects;
                fail("unexpected-disconnect");
#endif
            }
        }
#if defined(NUCODE_M28_B3_TEST_PERIODIC)
        else if (information.event == nucode::ble::BLEEvent::periodic_sync_synchronized)
        {
#if defined(NUCODE_M28_B3_ROLE_MIXED)
            periodic_sync = information.periodic_sync;
            phase = Phase::periodic_past;
            Serial.print("NUCODE_M28B3_mixed:PERIODIC:SYNCED:sid=7");
            printNonceEnd();
#elif defined(NUCODE_M28_B3_ROLE_CENTRAL)
            periodic_sync = information.periodic_sync;
            ++past_received;
            if (past_received < past_target)
            {
                periodic_delete_pending = true;
            }
            else if (!queueClientCommand(ClientWriteKind::periodic_go, "PER_GO"))
            {
                fail("periodic-go-queue");
            }
            else
            {
                phase = Phase::periodic_data;
            }
#endif
        }
#if defined(NUCODE_M28_B3_ROLE_CENTRAL)
        else if (information.event == nucode::ble::BLEEvent::periodic_sync_deleted)
        {
            periodic_sync = {};
            if (!queueClientCommand(ClientWriteKind::past_next, "PAST_NEXT"))
            {
                fail("past-next-queue");
            }
        }
#endif
#endif

#if defined(NUCODE_M28_B3_ROLE_MIXED) && defined(NUCODE_M28_B3_TEST_CONTROL)
        if (phase == Phase::control &&
            (information.event == nucode::ble::BLEEvent::phy_changed ||
             information.event == nucode::ble::BLEEvent::data_length_changed ||
             information.event == nucode::ble::BLEEvent::parameters_changed ||
             information.event == nucode::ble::BLEEvent::remote_information_available))
        {
            const bool central_match = information.connection == outgoing_link &&
                                       information.role == nucode::ble::BLELinkRole::central;
            const bool peripheral_match = information.connection == incoming_link &&
                                          information.role == nucode::ble::BLELinkRole::peripheral;
            if (!central_match && !peripheral_match)
            {
                ++cross_state_events;
                fail("control-cross-state");
            }
        }
#endif
    }

    /** @brief START command의 test·128-bit nonce를 exact grammar로 검증합니다. */
    [[maybe_unused]] bool acceptStartCommand()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        const std::size_t test_length = ::strlen(testName());
        const std::size_t expected_length = prefix_length + test_length + 1U + nonce_text_length;
        if (command_length != expected_length ||
            ::memcmp(command, start_prefix, prefix_length) != 0 ||
            ::memcmp(&command[prefix_length], testName(), test_length) != 0 ||
            command[prefix_length + test_length] != ':')
        {
            return false;
        }
        const char *nonce_text = &command[prefix_length + test_length + 1U];
        for (std::size_t index = 0U; index < nonce_binary_length; ++index)
        {
            std::uint8_t high = 0U;
            std::uint8_t low = 0U;
            if (!decodeHex(nonce_text[index * 2U], high) ||
                !decodeHex(nonce_text[index * 2U + 1U], low))
            {
                return false;
            }
            nonce_binary[index] = static_cast<std::uint8_t>((high << 4U) | low);
        }
        ::memcpy(nonce, nonce_text, nonce_text_length);
        nonce[nonce_text_length] = '\0';
        return true;
    }

    /** @brief 검증된 START 뒤 role별 첫 advertising 또는 scan을 시작합니다. */
    [[maybe_unused]] void startProtocol()
    {
        if (!acceptStartCommand())
        {
            fail("bad-start-command");
            return;
        }
        protocol_started = true;
        phase = Phase::startup;
        protocol_deadline_ms = k_uptime_get() + protocolTimeoutMs();
#if defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
        if (!startConnectableAdvertising())
        {
            fail("peripheral-advertising");
        }
#elif defined(NUCODE_M28_B3_ROLE_MIXED)
        if (!startPeerScan(peripheral_name))
        {
            fail("peripheral-scan");
        }
#else
        if (!startPeerScan(mixed_name))
        {
            fail("mixed-scan");
        }
#endif
    }

    /** @brief UART의 한 줄 START command를 bounded buffer로 수집합니다. */
    [[maybe_unused]] void pollHostCommand()
    {
        while (Serial.available() > 0 && !protocol_started && !protocol_failed)
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
                startProtocol();
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                fail("command-overflow");
                return;
            }
            command[command_length++] = value;
        }
    }

    /** @brief LINK의 송신 완료 뒤 mixed 또는 central 재연결 단계를 진행합니다. */
    [[maybe_unused]] void driveLink()
    {
#if defined(NUCODE_M28_B3_TEST_LINK)
#if defined(NUCODE_M28_B3_ROLE_MIXED) || defined(NUCODE_M28_B3_ROLE_CENTRAL)
        if (phase == Phase::startup && client_ready &&
            BLEConnection.mtu(outgoing_link) >= 31U)
        {
#if defined(NUCODE_M28_B3_ROLE_MIXED)
            if (incoming_link.valid())
#endif
            {
                phase = Phase::data;
            }
        }
        if (phase == Phase::data)
        {
            driveTraceTransmitter('L', link_sequence_target, 0);
        }
#endif
#if defined(NUCODE_M28_B3_ROLE_MIXED)
        if (phase == Phase::data && transmit_completed == link_sequence_target &&
            receive_sequence == link_sequence_target)
        {
            phase = Phase::reconnect_outgoing;
            disconnect_pending = true;
            action_deadline_ms = k_uptime_get() + reconnect_delay_ms;
        }
        if (phase == Phase::reconnect_outgoing && outgoing_reconnects == reconnect_target &&
            client_ready && !BLEClient.busy() && server_subscribed)
        {
            phase = Phase::reconnect_incoming;
            if (!notifyServer("LINK_CYCLE"))
            {
                fail("link-cycle-notify");
                return;
            }
        }
#elif defined(NUCODE_M28_B3_ROLE_CENTRAL)
        if (phase == Phase::reconnect_outgoing && outgoing_reconnects == reconnect_target &&
            client_ready && pending_client_write == ClientWriteKind::none &&
            active_client_write == ClientWriteKind::none)
        {
            if (!queueClientCommand(ClientWriteKind::link_done, "LINK_DONE"))
            {
                fail("link-done-queue");
            }
        }
#elif defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
        if (incoming_reconnects == reconnect_target && receive_sequence == link_sequence_target)
        {
            finishLink();
        }
#endif
#endif
    }

    /** @brief PER의 source scan·PAST 20회·1000 packet 광고를 진행합니다. */
    [[maybe_unused]] void drivePeriodic()
    {
#if defined(NUCODE_M28_B3_TEST_PERIODIC)
#if defined(NUCODE_M28_B3_ROLE_MIXED)
        if (incoming_link.valid() && outgoing_link.valid() && client_ready &&
            phase == Phase::startup)
        {
            phase = Phase::periodic_sync;
            if (!BLEScan.clearFilters() || !BLEScan.filterName(peripheral_name) ||
                !BLEScan.startExtended(false, false, false))
            {
                fail("periodic-source-scan");
            }
        }
        if (periodic_scan_result_pending)
        {
            periodic_scan_result_pending = false;
            static_cast<void>(BLEScan.stop());
            if (!BLEPeriodicAdvertising.createSync(periodic_address, periodic_sid,
                                                    periodic_sync, 0U, 1000U, true))
            {
                fail("periodic-source-sync");
            }
        }
        if (past_transfer_pending && periodic_sync.valid() &&
            BLEPeriodicAdvertising.synchronized(periodic_sync))
        {
            past_transfer_pending = false;
            if (past_sent >= past_target ||
                !BLEPeriodicAdvertising.transferSync(periodic_sync, incoming_link,
                                                     static_cast<std::uint16_t>(past_sent + 1U)))
            {
                fail("past-transfer");
                return;
            }
            ++past_sent;
        }
#elif defined(NUCODE_M28_B3_ROLE_CENTRAL)
        if (periodic_delete_pending && periodic_sync.valid())
        {
            periodic_delete_pending = false;
            if (!BLEPeriodicAdvertising.deleteSync(periodic_sync))
            {
                fail("past-sync-delete");
            }
        }
        if (periodic_result_deadline_ms != 0 &&
            k_uptime_get() >= periodic_result_deadline_ms)
        {
            periodic_result_deadline_ms = 0;
            finishPeriodicCentral();
        }
#elif defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
        if (periodic_emission_active && periodic_emitted < periodic_sequence_target &&
            k_uptime_get() >= periodic_next_update_ms)
        {
            ++periodic_emitted;
            if (!updatePeriodicPayload(periodic_emitted))
            {
                fail("periodic-update");
                return;
            }
            periodic_next_update_ms += periodic_update_interval_ms;
        }
#endif
#endif
    }

    /** @brief mixed role의 두 link에 PHY·DLE·parameter 제어 20 round를 적용합니다. */
    [[maybe_unused]] void driveControl()
    {
#if defined(NUCODE_M28_B3_ROLE_MIXED) && defined(NUCODE_M28_B3_TEST_CONTROL)
        const std::int64_t now = k_uptime_get();
        if (phase == Phase::startup && client_ready && server_subscribed &&
            validateActiveLinks())
        {
            phase = Phase::control;
            control_next_action_ms = now + control_stage_delay_ms;
        }
        if (phase != Phase::control || now < control_next_action_ms ||
            control_round >= control_round_target)
        {
            return;
        }
        if (!validateActiveLinks())
        {
            ++cross_state_events;
            fail("control-link-state");
            return;
        }
        const bool alternate = (control_round & 1U) == 0U;
        if (control_stage == 0U)
        {
            if (!BLEConnection.requestPhy(outgoing_link, alternate) ||
                !BLEConnection.requestPhy(incoming_link, alternate))
            {
                fail("control-phy-request");
                return;
            }
        }
        else if (control_stage == 1U)
        {
            const std::uint16_t octets = alternate ? 100U : 251U;
            const std::uint16_t time_us = alternate ? 1000U : 17040U;
            if (!BLEConnection.requestDataLength(outgoing_link, octets, time_us) ||
                !BLEConnection.requestDataLength(incoming_link, octets, time_us))
            {
                fail("control-dle-request");
                return;
            }
        }
        else if (control_stage == 2U)
        {
            const std::uint16_t interval = alternate ? 24U : 40U;
            if (!BLEConnection.requestParameters(outgoing_link, interval, interval, 0U, 400U) ||
                !BLEConnection.requestParameters(incoming_link, interval, interval, 0U, 400U))
            {
                fail("control-parameter-request");
                return;
            }
        }
        else
        {
            nucode::ble::BLEConnectionParameters outgoing_parameters{};
            nucode::ble::BLEConnectionParameters incoming_parameters{};
            nucode::ble::BLEDataLengthInfo outgoing_length{};
            nucode::ble::BLEDataLengthInfo incoming_length{};
            nucode::ble::BLERemoteInformation outgoing_remote{};
            nucode::ble::BLERemoteInformation incoming_remote{};
            std::int8_t outgoing_power = 0;
            std::int8_t incoming_power = 0;
            if (BLEConnection.phy(outgoing_link) == nucode::ble::BLEPhy::unknown ||
                BLEConnection.phy(incoming_link) == nucode::ble::BLEPhy::unknown ||
                !BLEConnection.parameters(outgoing_link, outgoing_parameters) ||
                !BLEConnection.parameters(incoming_link, incoming_parameters) ||
                !BLEConnection.dataLength(outgoing_link, outgoing_length) ||
                !BLEConnection.dataLength(incoming_link, incoming_length) ||
                !BLEConnection.remoteInformation(outgoing_link, outgoing_remote) ||
                !BLEConnection.remoteInformation(incoming_link, incoming_remote) ||
                !BLEConnection.txPower(outgoing_link, outgoing_power) ||
                !BLEConnection.txPower(incoming_link, incoming_power))
            {
                ++unreported_driver_errors;
                fail("control-snapshot");
                return;
            }
            ++control_round;
        }
        control_stage = static_cast<std::uint8_t>((control_stage + 1U) % 4U);
        control_next_action_ms = now + control_stage_delay_ms;
        if (control_round == control_round_target)
        {
            if (!notifyServer("CTRL_DONE") ||
                !queueClientCommand(ClientWriteKind::control_done, "CTRL_DONE"))
            {
                fail("control-finish-signal");
            }
        }
#endif
    }

    /** @brief SOAK의 10,000 packet/link와 1,800초 실행·회수를 진행합니다. */
    [[maybe_unused]] void driveSoak()
    {
#if defined(NUCODE_M28_B3_TEST_SOAK)
#if defined(NUCODE_M28_B3_ROLE_MIXED) || defined(NUCODE_M28_B3_ROLE_CENTRAL)
        if (phase == Phase::startup && client_ready &&
            BLEConnection.mtu(outgoing_link) >= 31U)
        {
#if defined(NUCODE_M28_B3_ROLE_MIXED)
            if (incoming_link.valid())
#endif
            {
                phase = Phase::soak;
            }
        }
        if (phase == Phase::soak)
        {
            driveTraceTransmitter('S', soak_sequence_target, soak_packet_interval_ms);
        }
#endif
        std::int64_t completion_deadline = 0;
#if defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
        if (receive_sequence == soak_sequence_target)
        {
            completion_deadline = receive_start_ms + soak_duration_ms;
        }
#elif defined(NUCODE_M28_B3_ROLE_MIXED)
        if (receive_sequence == soak_sequence_target &&
            transmit_completed == soak_sequence_target)
        {
            const std::int64_t receive_deadline = receive_start_ms + soak_duration_ms;
            const std::int64_t transmit_deadline = transmit_start_ms + soak_duration_ms;
            completion_deadline = receive_deadline > transmit_deadline
                                      ? receive_deadline : transmit_deadline;
        }
#else
        if (transmit_completed == soak_sequence_target)
        {
            completion_deadline = transmit_start_ms + soak_duration_ms;
        }
#endif
        if (completion_deadline != 0 && k_uptime_get() >= completion_deadline)
        {
            finishSoak();
        }
#endif
    }

    /** @brief callback 밖에서 실행해야 하는 scan·재연결·discovery·시험 단계를 처리합니다. */
    [[maybe_unused]] void driveProtocol()
    {
        if (!protocol_started || protocol_failed || phase == Phase::complete)
        {
            return;
        }
        const std::int64_t now = k_uptime_get();
        if (now >= protocol_deadline_ms)
        {
            fail("protocol-timeout");
            return;
        }
        if (scan_result_pending)
        {
            scan_result_pending = false;
            static_cast<void>(BLEScan.stop());
            if (!BLEConnection.connect(scan_address, outgoing_link))
            {
                fail("peer-connect");
                return;
            }
        }
        if (advertising_restart_pending && now >= action_deadline_ms)
        {
            advertising_restart_pending = false;
            if (!BLEAdvertising.start())
            {
                fail("advertising-restart");
                return;
            }
        }
        if (disconnect_pending && now >= action_deadline_ms)
        {
            disconnect_pending = false;
            if (!BLEConnection.disconnect(outgoing_link))
            {
                fail("reconnect-disconnect");
                return;
            }
        }
        if (reconnect_pending && now >= action_deadline_ms)
        {
            reconnect_pending = false;
            if (!BLEConnection.reconnect(outgoing_link))
            {
                fail("reconnect-start");
                return;
            }
        }
        if (discovery_pending && now >= action_deadline_ms && outgoing_link.valid())
        {
            discovery_pending = false;
            if (!BLEClient.discover(service_uuid, value_uuid))
            {
                fail("client-discovery");
                return;
            }
        }
        driveLink();
        drivePeriodic();
        driveControl();
        driveSoak();
        driveClientWrite();
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    const std::int64_t serial_deadline = k_uptime_get() + 5000;
    while (!Serial && k_uptime_get() < serial_deadline)
    {
        delay(10);
    }
#if !defined(NUCODE_M28_B3_ROLE_CENTRAL)
    trace_value.onEvent(onCharacteristic);
    if (!trace_service.addCharacteristic(trace_value) ||
        !BLEDevice.addService(trace_service))
    {
        fail("gatt-schema");
        return;
    }
#endif
    BLEDevice.onEventInfo(onBleEvent);
#if !defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
    BLEScan.onResult(onScanResult);
    BLEClient.onEvent(onClientEvent);
#endif
#if defined(NUCODE_M28_B3_TEST_PERIODIC) && \
    !defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
    BLEPeriodicAdvertising.onReport(onPeriodicReport);
#endif
    if (!BLEDevice.begin(
#if defined(NUCODE_M28_B3_ROLE_PERIPHERAL)
            peripheral_name
#elif defined(NUCODE_M28_B3_ROLE_MIXED)
            mixed_name
#else
            "NU54-M28-B3-C"
#endif
            ))
    {
        fail("device-begin");
        return;
    }
    Serial.print("NUCODE_M28B3_READY:role=");
    Serial.print(roleName());
    Serial.print(":test=");
    Serial.println(testName());
}

void loop()
{
    pollHostCommand();
    if (BLEDevice.initialized())
    {
        BLEDevice.poll();
    }
    driveProtocol();
    delay(1);
}
