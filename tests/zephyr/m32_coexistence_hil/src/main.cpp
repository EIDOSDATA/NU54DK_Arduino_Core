/**
 * @file main.cpp
 * @brief 세 NU54DK에서 M32-W10 BLE와 두 번째 radio의 실제 공존을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>

#if defined(NUCODE_M32_COEX_DUT) || defined(NUCODE_M32_COEX_BLE_PEER)
#include <NUCODE_BLE.h>
#endif
#if defined(NUCODE_M32_COEX_DUT)
#include <NUCODE_Radio_Coexistence.h>
#endif
#if defined(NUCODE_M32_COEX_154) && !defined(NUCODE_M32_COEX_BLE_PEER)
#include <NUCODE_Radio_IEEE802154.h>
#elif defined(NUCODE_M32_COEX_ESB) && !defined(NUCODE_M32_COEX_BLE_PEER)
#include <NUCODE_Radio_ESB.h>
#elif !defined(NUCODE_M32_COEX_BLE_PEER)
#include <NUCODE_BLE_Mesh.h>
#include <zephyr/bluetooth/mesh.h>
#endif

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <string.h>

#ifndef M32_COEX_CORE_REVISION
#error "M32_COEX_CORE_REVISION is required"
#endif

namespace
{
#if defined(NUCODE_M32_COEX_DUT)
    using nucode::coexistence::Protocol;
#endif
#if defined(NUCODE_M32_COEX_MESH) && !defined(NUCODE_M32_COEX_BLE_PEER)
    using namespace nucode::mesh;
#endif

    constexpr char protocol[] = "M32COEX|1";
    constexpr char clear_prefix[] = "M32COEX|1|CLEAR|nonce=";
    constexpr char start_prefix[] = "M32COEX|1|START|nonce=";
    constexpr char finish_prefix[] = "M32COEX|1|FINISH|nonce=";
    constexpr char stop_prefix[] = "M32COEX|1|STOP|nonce=";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::uint32_t iteration_target = 20U;
    constexpr std::uint32_t packets_per_iteration = 200U;
    constexpr std::uint32_t packet_target = iteration_target * packets_per_iteration;
    constexpr std::uint32_t allowed_loss = 80U;
    constexpr std::uint32_t service_gap_limit_ms = 500U;
    constexpr std::int64_t esb_send_interval_ms = 10;
    constexpr std::uint32_t mesh_configuration_retry_limit = 3U;
    constexpr std::int64_t mesh_configuration_retry_delay_ms = 500;
    constexpr std::int64_t mesh_configuration_settle_ms = 1500;
    constexpr std::uint32_t mesh_acknowledgment_retry_limit = 3U;
    constexpr std::int64_t mesh_acknowledgment_timeout_ms = 300;
    constexpr std::int64_t mesh_ble_payload_delay_ms = 30000;
    constexpr std::int64_t session_timeout_ms = 600000;
    constexpr std::uint32_t ble_magic = 0x58454F43U;
    constexpr std::size_t ble_frame_size = 16U;

    char command[192] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool cleared = false;
    bool started = false;
    bool finished = false;
    bool failed = false;
    bool stop_requested = false;
    std::int64_t deadline_ms = 0;
    std::int64_t progress_deadline_ms = 0;

#if defined(NUCODE_M32_COEX_DUT)
    bool ble_started = false;
#if defined(NUCODE_M32_COEX_154) || defined(NUCODE_M32_COEX_ESB)
    bool second_radio_started = false;
    bool double_owner_rejected = false;
    bool radio_sequence_valid = false;
    std::uint32_t last_radio_sequence = UINT32_MAX;
#endif
    bool ble_ready_seen = false;
    bool ble_disconnect_seen = false;
    std::uint32_t ble_restarts = 0U;
    std::uint32_t radio_restarts = 0U;
    std::uint8_t ble_frame[ble_frame_size] = {};
    std::size_t ble_frame_offset = 0U;
    std::uint32_t ble_received = 0U;
    std::uint32_t ble_corrupt = 0U;
    std::uint32_t radio_received = 0U;
    std::uint32_t radio_corrupt = 0U;
#if defined(NUCODE_M32_COEX_MESH)
    std::uint8_t last_mesh_tid = 0U;
    bool mesh_tid_valid = false;
#endif
#elif defined(NUCODE_M32_COEX_BLE_PEER)
    bool ble_started = false;
    bool disconnect_requested = false;
    bool disconnect_seen = false;
    bool reconnect_seen = false;
    std::uint32_t ble_sent = 0U;
    std::int64_t ble_start_not_before_ms = 0;
#elif defined(NUCODE_M32_COEX_RADIO_PEER)
    bool radio_started = false;
    bool invalid_configuration_rejected = false;
    bool invalid_length_rejected = false;
    bool double_owner_rejected = false;
    bool radio_restarted = false;
    std::uint32_t submitted_packets = 0U;
    std::uint32_t completed_packets = 0U;
    std::uint32_t acknowledged_packets = 0U;
    std::uint32_t failed_packets = 0U;
    std::uint32_t observed_acknowledged = 0U;
    std::uint32_t observed_failed = 0U;
    std::int64_t next_send_ms = 0;
#else
    std::uint8_t dut_uuid[16] = {};
    bool dut_discovered = false;
    bool provisioning_pending = false;
    bool dut_added = false;
    bool mesh_configured = false;
    bool mesh_send_pending = false;
    bool mesh_restarted = false;
    std::uint32_t mesh_sent = 0U;
    std::uint32_t mesh_acknowledged = 0U;
    std::uint32_t mesh_configuration_retries = 0U;
    std::uint32_t mesh_acknowledgment_retries = 0U;
    std::uint32_t mesh_current_retries = 0U;
    std::uint8_t mesh_transaction_id = 0U;
    std::int64_t mesh_configuration_not_before_ms = 0;
    std::int64_t next_mesh_configuration_attempt_ms = 0;
    std::int64_t mesh_acknowledgment_deadline_ms = 0;
#endif

    /** @brief compile-time 공존 조합명을 반환합니다. */
    const char *scenarioName()
    {
#if defined(NUCODE_M32_COEX_154)
        return "ble_154";
#elif defined(NUCODE_M32_COEX_ESB)
        return "ble_esb";
#else
        return "ble_mesh";
#endif
    }

    /** @brief compile-time 역할명을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M32_COEX_DUT)
        return "dut";
#elif defined(NUCODE_M32_COEX_BLE_PEER)
        return "ble_peer";
#elif defined(NUCODE_M32_COEX_RADIO_PEER)
        return "radio_peer";
#else
        return "mesh_peer";
#endif
    }

#if defined(NUCODE_M32_COEX_DUT) || defined(NUCODE_M32_COEX_BLE_PEER)
    /** @brief 조합별 NUS peripheral 이름을 반환합니다. */
    const char *blePeerName()
    {
#if defined(NUCODE_M32_COEX_154)
        return "NU54-COEX-154";
#elif defined(NUCODE_M32_COEX_ESB)
        return "NU54-COEX-ESB";
#else
        return "NU54-COEX-MESH";
#endif
    }
#endif

    /** @brief bounded record에 nonce·Core·조합을 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M32_COEX_CORE_REVISION);
        Serial.print("|scenario=");
        Serial.print(scenarioName());
    }

    /** @brief 첫 오류만 bounded protocol로 출력합니다. */
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

    /** @brief nonce와 exact revision이 포함된 명령을 검증합니다. */
    bool acceptRevisionCommand(const char *prefix)
    {
        const std::size_t prefix_length = ::strlen(prefix);
        if (::strncmp(command, prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *cursor = command + prefix_length;
        for (std::size_t index = 0U; index < nonce_length; ++index)
        {
            const char value = cursor[index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        constexpr char core_prefix[] = "|core=";
        if (::strncmp(cursor + nonce_length, core_prefix, sizeof(core_prefix) - 1U) != 0 ||
            ::strcmp(cursor + nonce_length + sizeof(core_prefix) - 1U, M32_COEX_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

#if defined(NUCODE_M32_COEX_DUT)
    /** @brief little-endian 32-bit 값을 읽습니다. */
    std::uint32_t read32(const std::uint8_t *source)
    {
        return static_cast<std::uint32_t>(source[0]) |
               (static_cast<std::uint32_t>(source[1]) << 8U) |
               (static_cast<std::uint32_t>(source[2]) << 16U) |
               (static_cast<std::uint32_t>(source[3]) << 24U);
    }
#endif

#if defined(NUCODE_M32_COEX_BLE_PEER)
    /** @brief little-endian 32-bit 값을 기록합니다. */
    void write32(std::uint8_t *destination, std::uint32_t value)
    {
        destination[0] = static_cast<std::uint8_t>(value);
        destination[1] = static_cast<std::uint8_t>(value >> 8U);
        destination[2] = static_cast<std::uint8_t>(value >> 16U);
        destination[3] = static_cast<std::uint8_t>(value >> 24U);
    }

    /** @brief BLE sequence와 inverse를 포함한 고정 frame을 만듭니다. */
    void encodeBleFrame(std::uint32_t sequence, std::uint8_t *frame)
    {
        write32(&frame[0], ble_magic);
        write32(&frame[4], sequence);
        write32(&frame[8], ~sequence);
        write32(&frame[12], sequence ^ 0xB1E0C0DEU);
    }
#endif

#if (defined(NUCODE_M32_COEX_154) || defined(NUCODE_M32_COEX_ESB)) &&                              \
    !defined(NUCODE_M32_COEX_BLE_PEER)
    /** @brief second-radio payload를 재현 가능한 sequence pattern으로 만듭니다. */
    void encodeRadioPayload(std::uint32_t sequence, std::uint8_t *payload, std::size_t length)
    {
        for (std::size_t index = 0U; index < length; ++index)
        {
            payload[index] =
                static_cast<std::uint8_t>((sequence * 17U + index * 29U + 0x32U) & 0xFFU);
        }
    }
#endif

#if defined(NUCODE_M32_COEX_DUT) || defined(NUCODE_M32_COEX_BLE_PEER)
    /** @brief BLE 연결·재연결 상태를 bounded counter로 복사합니다. */
    void onBleEvent(nucode::ble::Event event, void *)
    {
#if defined(NUCODE_M32_COEX_DUT)
        if (event == nucode::ble::Event::ready)
        {
            if (ble_disconnect_seen && ble_ready_seen)
            {
                ++ble_restarts;
                NUCODECoexistence.recordRestart(Protocol::ble);
            }
            ble_ready_seen = true;
            NUCODECoexistence.setActive(Protocol::ble, true);
        }
        else if (event == nucode::ble::Event::disconnected)
        {
            ble_disconnect_seen = true;
            NUCODECoexistence.setActive(Protocol::ble, false);
        }
        else if (event == nucode::ble::Event::error)
        {
            fail("ble_event", BLESerial.lastDriverError());
        }
#else
        if (event == nucode::ble::Event::disconnected)
        {
            disconnect_seen = true;
        }
        else if (event == nucode::ble::Event::ready && disconnect_seen)
        {
            reconnect_seen = true;
        }
        else if (event == nucode::ble::Event::error)
        {
            fail("ble_event", BLESerial.lastDriverError());
        }
#endif
    }
#endif

#if defined(NUCODE_M32_COEX_MESH) && !defined(NUCODE_M32_COEX_BLE_PEER)
    /** @brief provisioning과 Generic OnOff status를 역할별 counter로 복사합니다. */
    void onMeshEvent(const EventRecord &record, void *)
    {
#if defined(NUCODE_M32_COEX_DUT)
        if (record.event == Event::model_status && record.model == Model::generic_on_off_server)
        {
            if (record.payload_size >= 2U && mesh_tid_valid && record.payload[1] == last_mesh_tid)
            {
                return;
            }
            const bool valid = record.payload_size >= 2U &&
                               record.payload[0] == static_cast<std::uint8_t>(radio_received & 1U);
            if (record.payload_size >= 2U)
            {
                last_mesh_tid = record.payload[1];
                mesh_tid_valid = true;
            }
            ++radio_received;
            if (!valid)
            {
                ++radio_corrupt;
            }
            NUCODECoexistence.recordRequested(Protocol::mesh);
            NUCODECoexistence.recordDelivered(Protocol::mesh, radio_received - 1U,
                                              (radio_received - 1U) ^ 0x4D455348U, valid);
            if (radio_received == packet_target / 2U)
            {
                NUCODECoexistence.setActive(Protocol::mesh, false);
            }
            else if (radio_received == packet_target / 2U + 1U)
            {
                ++radio_restarts;
                NUCODECoexistence.recordRestart(Protocol::mesh);
            }
        }
#else
        if (record.event == Event::unprovisioned_device && record.uuid[15] == 0xD0U && !dut_added)
        {
            ::memcpy(dut_uuid, record.uuid, sizeof(dut_uuid));
            dut_discovered = true;
        }
        else if (record.event == Event::node_added && record.address == 0x0100U)
        {
            provisioning_pending = false;
            dut_added = true;
        }
        else if (record.event == Event::provisioning_link_closed)
        {
            provisioning_pending = false;
            mesh_configuration_not_before_ms =
                k_uptime_get() + mesh_configuration_settle_ms;
        }
        else if (record.event == Event::model_status && record.model == Model::generic_on_off)
        {
            const std::uint8_t expected_state =
                static_cast<std::uint8_t>((mesh_acknowledged & 1U) != 0U ? 1U : 0U);
            if (mesh_send_pending && record.payload_size >= 1U &&
                record.payload[0] == expected_state)
            {
                mesh_send_pending = false;
                ++mesh_acknowledged;
                ++mesh_transaction_id;
                mesh_current_retries = 0U;
            }
        }
#endif
    }
#endif

#if defined(NUCODE_M32_COEX_154) && !defined(NUCODE_M32_COEX_BLE_PEER)
    /** @brief 고정 IEEE 802.15.4 역할을 시작합니다. */
    bool beginSecondRadio(bool transmitter)
    {
        nucode::radio154::Configuration configuration{};
        configuration.channel = 20U;
        configuration.local_address = transmitter ? 0x0001U : 0x0002U;
        configuration.peer_address = transmitter ? 0x0002U : 0x0001U;
        return NUCODERadio154.begin(transmitter ? nucode::radio154::Role::transmitter
                                                : nucode::radio154::Role::receiver,
                                    configuration);
    }

    /** @brief IEEE 802.15.4 radio를 취소하고 정지합니다. */
    bool stopSecondRadio()
    {
        return NUCODERadio154.cancel() && NUCODERadio154.stop();
    }
#elif defined(NUCODE_M32_COEX_ESB) && !defined(NUCODE_M32_COEX_BLE_PEER)
    /** @brief 고정 ESB 역할을 시작합니다. */
    bool beginSecondRadio(bool transmitter)
    {
        nucode::esb::Configuration configuration{};
        configuration.channel = 40U;
        configuration.bitrate = nucode::esb::Bitrate::mbps2;
        configuration.retransmit_delay_us = 1000U;
        configuration.retransmit_count = 15U;
        return NUCODEEsb.begin(transmitter ? nucode::esb::Role::primary_transmitter
                                           : nucode::esb::Role::primary_receiver,
                               configuration);
    }

    /** @brief ESB FIFO와 radio를 취소하고 정지합니다. */
    bool stopSecondRadio()
    {
        return NUCODEEsb.cancel() && NUCODEEsb.stop();
    }
#endif

    /** @brief 역할 counter를 지우고 persistent Mesh 상태를 초기화합니다. */
    void clearState()
    {
#if defined(NUCODE_M32_COEX_MESH) && !defined(NUCODE_M32_COEX_BLE_PEER)
        if (!NUCODEMesh.reset())
        {
            fail("mesh_clear", NUCODEMesh.lastDriverError());
            return;
        }
#endif
        started = false;
        finished = false;
        failed = false;
        stop_requested = false;
#if defined(NUCODE_M32_COEX_DUT)
        ble_ready_seen = false;
        ble_disconnect_seen = false;
#if defined(NUCODE_M32_COEX_154) || defined(NUCODE_M32_COEX_ESB)
        double_owner_rejected = false;
        radio_sequence_valid = false;
        last_radio_sequence = UINT32_MAX;
#endif
        ble_restarts = 0U;
        radio_restarts = 0U;
        ble_frame_offset = 0U;
        ble_received = 0U;
        ble_corrupt = 0U;
        radio_received = 0U;
        radio_corrupt = 0U;
#if defined(NUCODE_M32_COEX_MESH)
        mesh_tid_valid = false;
#endif
#elif defined(NUCODE_M32_COEX_BLE_PEER)
        disconnect_requested = false;
        disconnect_seen = false;
        reconnect_seen = false;
        ble_sent = 0U;
        ble_start_not_before_ms = 0;
#elif defined(NUCODE_M32_COEX_RADIO_PEER)
        invalid_configuration_rejected = false;
        invalid_length_rejected = false;
        double_owner_rejected = false;
        radio_restarted = false;
        submitted_packets = 0U;
        completed_packets = 0U;
        acknowledged_packets = 0U;
        failed_packets = 0U;
        observed_acknowledged = 0U;
        observed_failed = 0U;
        next_send_ms = 0;
#else
        dut_discovered = false;
        provisioning_pending = false;
        dut_added = false;
        mesh_configured = false;
        mesh_send_pending = false;
        mesh_restarted = false;
        mesh_sent = 0U;
        mesh_acknowledged = 0U;
        mesh_configuration_retries = 0U;
        mesh_acknowledgment_retries = 0U;
        mesh_current_retries = 0U;
        mesh_transaction_id = 0U;
        mesh_configuration_not_before_ms = 0;
        next_mesh_configuration_attempt_ms = 0;
        mesh_acknowledgment_deadline_ms = 0;
#endif
        cleared = true;
        Serial.print(protocol);
        Serial.print("|CLEARED|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
    }

#if defined(NUCODE_M32_COEX_DUT)
    /** @brief 공존 DUT의 NUS peripheral과 두 번째 radio를 시작합니다. */
    bool startDut()
    {
        if (!NUCODECoexistence.begin(service_gap_limit_ms))
        {
            return false;
        }
#if defined(NUCODE_M32_COEX_MESH)
        NUCODECoexistence.setActive(Protocol::mesh, true);
#else
        BLESerial.onEvent(onBleEvent);
        if (!BLESerial.beginPeripheral(blePeerName()) || !BLESerial.startAdvertising())
        {
            return false;
        }
        ble_started = true;
        if (!beginSecondRadio(false))
        {
            return false;
        }
        second_radio_started = true;
        double_owner_rejected = !beginSecondRadio(false);
        if (!double_owner_rejected)
        {
            return false;
        }
#endif
        return true;
    }
#elif defined(NUCODE_M32_COEX_BLE_PEER)
    /** @brief NUS central을 시작해 공존 DUT를 검색합니다. */
    bool startBlePeer()
    {
#if defined(NUCODE_M32_COEX_MESH)
        ble_start_not_before_ms = k_uptime_get() + mesh_ble_payload_delay_ms;
        return true;
#else
        BLESerial.onEvent(onBleEvent);
        if (!BLESerial.beginCentral() || !BLESerial.scanForNus(blePeerName()))
        {
            return false;
        }
        ble_started = true;
        return true;
#endif
    }
#elif defined(NUCODE_M32_COEX_RADIO_PEER)
    /** @brief second-radio negative와 transmitter를 시작합니다. */
    bool startRadioPeer()
    {
#if defined(NUCODE_M32_COEX_154)
        nucode::radio154::Configuration invalid{};
        invalid.channel = 10U;
        invalid_configuration_rejected =
            !NUCODERadio154.begin(nucode::radio154::Role::transmitter, invalid);
#else
        nucode::esb::Configuration invalid{};
        invalid.bitrate = static_cast<nucode::esb::Bitrate>(0xffU);
        invalid_configuration_rejected =
            !NUCODEEsb.begin(nucode::esb::Role::primary_transmitter, invalid);
#endif
        if (!invalid_configuration_rejected || !beginSecondRadio(true))
        {
            return false;
        }
        radio_started = true;
        double_owner_rejected = !beginSecondRadio(true);
#if defined(NUCODE_M32_COEX_154)
        std::uint8_t oversized[nucode::radio154::Packet::payload_capacity + 1U] = {};
        invalid_length_rejected = !NUCODERadio154.send(0U, oversized, sizeof(oversized));
#else
        std::uint8_t oversized[nucode::esb::Packet::payload_capacity + 1U] = {};
        invalid_length_rejected = !NUCODEEsb.send(0U, oversized, sizeof(oversized));
#endif
        return double_owner_rejected && invalid_length_rejected;
    }
#endif

    /** @brief 역할 runtime을 시작하고 BEGIN record를 출력합니다. */
    void startSession()
    {
        if (!cleared)
        {
            fail("start_without_clear");
            return;
        }
        bool success = true;
#if defined(NUCODE_M32_COEX_DUT)
        success = startDut();
#elif defined(NUCODE_M32_COEX_BLE_PEER)
        success = startBlePeer();
#elif defined(NUCODE_M32_COEX_RADIO_PEER)
        success = startRadioPeer();
#endif
        if (!success)
        {
            fail("start");
            return;
        }
        started = true;
        deadline_ms = k_uptime_get() + session_timeout_ms;
        progress_deadline_ms = k_uptime_get() + 5000;
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
    }

#if defined(NUCODE_M32_COEX_DUT)
    /** @brief NUS byte stream을 16-byte sequence frame으로 판정합니다. */
    void driveBleReceiver()
    {
#if defined(NUCODE_M32_COEX_MESH)
        if (!ble_started)
        {
            if (!mesh_tid_valid)
            {
                return;
            }
            BLESerial.onEvent(onBleEvent);
            if (!BLESerial.beginPeripheral(blePeerName()) || !BLESerial.startAdvertising())
            {
                fail("ble_start", BLESerial.lastDriverError());
                return;
            }
            ble_started = true;
        }
#endif
        while (BLESerial.available() > 0)
        {
            const int value = BLESerial.read();
            if (value < 0)
            {
                break;
            }
            ble_frame[ble_frame_offset++] = static_cast<std::uint8_t>(value);
            if (ble_frame_offset != sizeof(ble_frame))
            {
                continue;
            }
            const std::uint32_t sequence = read32(&ble_frame[4]);
            const bool valid =
                read32(&ble_frame[0]) == ble_magic && read32(&ble_frame[8]) == ~sequence &&
                read32(&ble_frame[12]) == (sequence ^ 0xB1E0C0DEU) && sequence < packet_target;
            NUCODECoexistence.recordRequested(Protocol::ble);
            NUCODECoexistence.recordDelivered(Protocol::ble, sequence, sequence ^ 0xB1E0C0DEU,
                                              valid);
            ++ble_received;
            if (!valid)
            {
                ++ble_corrupt;
            }
            ble_frame_offset = 0U;
        }
    }

#if defined(NUCODE_M32_COEX_154)
    /** @brief driver 재시작 경계의 최종 ACK payload 재수신을 한 번만 제외합니다. */
    bool isDuplicateRadioSequence(std::uint32_t sequence, bool driver_duplicate)
    {
        if (driver_duplicate ||
            (radio_sequence_valid && sequence == last_radio_sequence))
        {
            return true;
        }
        last_radio_sequence = sequence;
        radio_sequence_valid = true;
        return false;
    }

    /** @brief IEEE 802.15.4 수신 payload와 중간 restart를 판정합니다. */
    void driveSecondRadioReceiver()
    {
        nucode::radio154::Packet packet{};
        while (NUCODERadio154.read(packet))
        {
            if (isDuplicateRadioSequence(packet.sequence, packet.duplicate))
            {
                continue;
            }
            std::uint8_t expected[12] = {};
            encodeRadioPayload(packet.sequence, expected, sizeof(expected));
            const bool valid = packet.hash_valid && packet.length == sizeof(expected) &&
                               ::memcmp(packet.payload, expected, sizeof(expected)) == 0;
            NUCODECoexistence.recordRequested(Protocol::ieee802154);
            NUCODECoexistence.recordDelivered(Protocol::ieee802154, packet.sequence,
                                              packet.sequence ^ 0x00001540U, valid);
            ++radio_received;
            if (!valid)
            {
                ++radio_corrupt;
            }
            if (radio_received == packet_target / 2U)
            {
                if (!stopSecondRadio() || !beginSecondRadio(false))
                {
                    fail("radio_restart", NUCODERadio154.lastDriverError());
                    return;
                }
                ++radio_restarts;
                NUCODECoexistence.recordRestart(Protocol::ieee802154);
            }
        }
    }
#elif defined(NUCODE_M32_COEX_ESB)
    /** @brief driver 재시작 경계의 최종 ACK payload 재수신을 한 번만 제외합니다. */
    bool isDuplicateRadioSequence(std::uint32_t sequence, bool driver_duplicate)
    {
        if (driver_duplicate ||
            (radio_sequence_valid && sequence == last_radio_sequence))
        {
            return true;
        }
        last_radio_sequence = sequence;
        radio_sequence_valid = true;
        return false;
    }

    /** @brief ESB 수신 payload와 중간 restart를 판정합니다. */
    void driveSecondRadioReceiver()
    {
        nucode::esb::Packet packet{};
        while (NUCODEEsb.read(packet))
        {
            if (isDuplicateRadioSequence(packet.sequence, packet.duplicate))
            {
                continue;
            }
            std::uint8_t expected[8] = {};
            encodeRadioPayload(packet.sequence, expected, sizeof(expected));
            const bool valid = packet.hash_valid && packet.length == sizeof(expected) &&
                               ::memcmp(packet.payload, expected, sizeof(expected)) == 0;
            NUCODECoexistence.recordRequested(Protocol::esb);
            NUCODECoexistence.recordDelivered(Protocol::esb, packet.sequence,
                                              packet.sequence ^ 0x0000E5B0U, valid);
            ++radio_received;
            if (!valid)
            {
                ++radio_corrupt;
            }
            if (radio_received == packet_target / 2U)
            {
                if (!stopSecondRadio() || !beginSecondRadio(false))
                {
                    fail("radio_restart", NUCODEEsb.lastDriverError());
                    return;
                }
                ++radio_restarts;
                NUCODECoexistence.recordRestart(Protocol::esb);
            }
        }
    }
#endif

    /** @brief 공존 DUT의 두 protocol 결과를 출력합니다. */
    void finishDut()
    {
        if (finished)
        {
            return;
        }
#if defined(NUCODE_M32_COEX_154)
        const Protocol second = Protocol::ieee802154;
#elif defined(NUCODE_M32_COEX_ESB)
        const Protocol second = Protocol::esb;
#else
        const Protocol second = Protocol::mesh;
#endif
        const auto ble = NUCODECoexistence.statistics(Protocol::ble);
        const auto radio = NUCODECoexistence.statistics(second);
#if defined(NUCODE_M32_COEX_154) || defined(NUCODE_M32_COEX_ESB)
        const bool ownership_ok = double_owner_rejected;
#else
        const bool ownership_ok = true;
#endif
        if (ble_received + allowed_loss < packet_target ||
            radio_received + allowed_loss < packet_target || ble_corrupt != 0U ||
            radio_corrupt != 0U || BLESerial.droppedRxBytes() != 0U || ble_restarts != 1U ||
            radio_restarts != 1U || !ownership_ok || ble.hash_errors != 0U ||
            radio.hash_errors != 0U || ble.sequence_errors != 0U || radio.sequence_errors != 0U ||
            ble.maximum_service_gap_ms > service_gap_limit_ms ||
            radio.maximum_service_gap_ms > service_gap_limit_ms)
        {
            fail("result_boundary");
            return;
        }
        Serial.print(protocol);
        Serial.print("|RESULT|role=dut|iterations=20|ble_received=");
        Serial.print(ble_received);
        Serial.print("|radio_received=");
        Serial.print(radio_received);
        Serial.print("|ble_loss=");
        Serial.print(ble_received < packet_target ? packet_target - ble_received : 0U);
        Serial.print("|radio_loss=");
        Serial.print(radio_received < packet_target ? packet_target - radio_received : 0U);
        Serial.print("|ble_corrupt=0|radio_corrupt=0|ble_restarts=");
        Serial.print(ble_restarts);
        Serial.print("|radio_restarts=");
        Serial.print(radio_restarts);
        Serial.print("|ble_gap_ms=");
        Serial.print(ble.maximum_service_gap_ms);
        Serial.print("|radio_gap_ms=");
        Serial.print(radio.maximum_service_gap_ms);
        Serial.print("|starvation=");
        Serial.print(ble.starvation_events + radio.starvation_events);
#if defined(NUCODE_M32_COEX_154) || defined(NUCODE_M32_COEX_ESB)
        Serial.print("|double_owner_rejected=");
        Serial.print(double_owner_rejected ? 1 : 0);
#endif
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=dut|status=pass");
        printSuffix();
        Serial.println();
        finished = true;
    }
#elif defined(NUCODE_M32_COEX_BLE_PEER)
    /** @brief BLE NUS 4,000 frame과 중간 disconnect/reconnect를 실행합니다. */
    void driveBlePeer()
    {
#if defined(NUCODE_M32_COEX_MESH)
        if (!ble_started)
        {
            if (k_uptime_get() < ble_start_not_before_ms)
            {
                return;
            }
            BLESerial.onEvent(onBleEvent);
            if (!BLESerial.beginCentral() || !BLESerial.scanForNus(blePeerName()))
            {
                fail("ble_start", BLESerial.lastDriverError());
                return;
            }
            ble_started = true;
            return;
        }
#endif
        if (!BLESerial.ready())
        {
            return;
        }
        if (ble_sent == packet_target / 2U && !disconnect_requested)
        {
            if (!BLESerial.disconnect())
            {
                fail("ble_disconnect", BLESerial.lastDriverError());
                return;
            }
            disconnect_requested = true;
            return;
        }
        if (disconnect_requested && !reconnect_seen)
        {
            return;
        }
        if (ble_sent >= packet_target)
        {
            if (!finished)
            {
                Serial.print(protocol);
                Serial.print("|RESULT|role=ble_peer|iterations=20|sent=4000");
                Serial.print("|reconnects=1|write_failures=0");
                printSuffix();
                Serial.println();
                Serial.print(protocol);
                Serial.print("|END|role=ble_peer|status=pass");
                printSuffix();
                Serial.println();
                finished = true;
            }
            return;
        }
        std::uint8_t frame[ble_frame_size] = {};
        encodeBleFrame(ble_sent, frame);
        if (BLESerial.write(frame, sizeof(frame)) != sizeof(frame))
        {
            fail("ble_write", BLESerial.lastDriverError());
            return;
        }
        ++ble_sent;
    }
#elif defined(NUCODE_M32_COEX_RADIO_PEER)
    /** @brief 현재 second-radio ACK counter를 반환합니다. */
    std::uint32_t radioAcknowledged()
    {
#if defined(NUCODE_M32_COEX_154)
        return NUCODERadio154.statistics().tx_acknowledged;
#else
        return NUCODEEsb.statistics().tx_acknowledged;
#endif
    }

    /** @brief 현재 second-radio 최종 전송 실패 counter를 반환합니다. */
    std::uint32_t radioFailed()
    {
#if defined(NUCODE_M32_COEX_154)
        return NUCODERadio154.statistics().tx_failed;
#else
        return NUCODEEsb.statistics().tx_failed;
#endif
    }

    /** @brief second-radio 4,000 packet과 중간 stop/restart를 실행합니다. */
    void driveRadioPeer()
    {
#if defined(NUCODE_M32_COEX_154)
        const bool busy = NUCODERadio154.busy();
#else
        const bool busy = NUCODEEsb.busy();
#endif
        if (busy)
        {
            return;
        }
        if (submitted_packets != completed_packets)
        {
            const std::uint32_t acknowledged = radioAcknowledged();
            const std::uint32_t transmission_failed = radioFailed();
            if (acknowledged > observed_acknowledged)
            {
                ++acknowledged_packets;
            }
            else if (transmission_failed > observed_failed)
            {
                ++failed_packets;
            }
            else
            {
                fail("radio_completion");
                return;
            }
            observed_acknowledged = acknowledged;
            observed_failed = transmission_failed;
            ++completed_packets;
        }
        if (completed_packets == packet_target / 2U && !radio_restarted)
        {
            if (!stopSecondRadio() || !beginSecondRadio(true))
            {
                fail("radio_restart");
                return;
            }
            observed_acknowledged = 0U;
            observed_failed = 0U;
            radio_restarted = true;
            next_send_ms = k_uptime_get() + 300;
            return;
        }
        if (completed_packets >= packet_target)
        {
            if (acknowledged_packets + allowed_loss < packet_target ||
                failed_packets > allowed_loss)
            {
                fail("radio_loss_boundary");
                return;
            }
            if (!finished)
            {
                Serial.print(protocol);
                Serial.print("|RESULT|role=radio_peer|iterations=20|sent=4000");
                Serial.print("|acknowledged=");
                Serial.print(acknowledged_packets);
                Serial.print("|failures=");
                Serial.print(failed_packets);
                Serial.print("|restarts=1|invalid_configuration_rejected=1");
                Serial.print("|invalid_length_rejected=1|double_owner_rejected=1");
                printSuffix();
                Serial.println();
                Serial.print(protocol);
                Serial.print("|END|role=radio_peer|status=pass");
                printSuffix();
                Serial.println();
                finished = true;
            }
            return;
        }
        if (k_uptime_get() < next_send_ms)
        {
            return;
        }
#if defined(NUCODE_M32_COEX_154)
        std::uint8_t payload[12] = {};
#else
        std::uint8_t payload[8] = {};
#endif
        encodeRadioPayload(submitted_packets, payload, sizeof(payload));
#if defined(NUCODE_M32_COEX_154)
        const bool sent = NUCODERadio154.send(submitted_packets, payload, sizeof(payload));
#else
        const bool sent = NUCODEEsb.send(submitted_packets, payload, sizeof(payload));
#endif
        if (!sent)
        {
            fail("radio_send");
            return;
        }
        ++submitted_packets;
#if defined(NUCODE_M32_COEX_ESB)
        next_send_ms = k_uptime_get() + esb_send_interval_ms;
#endif
    }
#else
    /** @brief 손실된 Mesh Configuration 응답을 유한 횟수만 다시 요청합니다. */
    bool retryMeshConfiguration(const char *stage)
    {
        const int error = NUCODEMesh.lastDriverError();
        if (error == -ETIMEDOUT &&
            mesh_configuration_retries < mesh_configuration_retry_limit)
        {
            ++mesh_configuration_retries;
            next_mesh_configuration_attempt_ms =
                k_uptime_get() + mesh_configuration_retry_delay_ms;
            return true;
        }
        fail(stage, error);
        return false;
    }

    /** @brief Mesh node provisioning·binding·4,000 acknowledged set을 진행합니다. */
    void driveMeshPeer()
    {
        if (!dut_added)
        {
            if (dut_discovered && !provisioning_pending)
            {
                provisioning_pending = NUCODEMesh.provision(dut_uuid, Bearer::advertising, 0x0100U);
                if (!provisioning_pending)
                {
                    fail("mesh_provision", NUCODEMesh.lastDriverError());
                }
            }
            return;
        }
        if (!mesh_configured)
        {
            if (k_uptime_get() < mesh_configuration_not_before_ms ||
                k_uptime_get() < next_mesh_configuration_attempt_ms)
            {
                return;
            }
            constexpr std::uint8_t app_key[16] = {
                0x32U, 0x10U, 0x54U, 0x15U, 0x11U, 0x22U, 0x33U, 0x44U,
                0x55U, 0x66U, 0x77U, 0x88U, 0x99U, 0xAAU, 0xBBU, 0xCCU,
            };
            if (!NUCODEMesh.configureAppKey(0x0100U, app_key))
            {
                retryMeshConfiguration("mesh_configure_remote_key");
                return;
            }
            if (!NUCODEMesh.bindModel(0x0100U, 0x0100U,
                                      Model::generic_on_off_server))
            {
                retryMeshConfiguration("mesh_configure_remote_bind");
                return;
            }
            if (!NUCODEMesh.configureAppKey(0x0001U, app_key))
            {
                retryMeshConfiguration("mesh_configure_local_key");
                return;
            }
            if (!NUCODEMesh.bindModel(0x0001U, 0x0001U, Model::generic_on_off))
            {
                retryMeshConfiguration("mesh_configure_local_bind");
                return;
            }
            mesh_configured = true;
            return;
        }
        if (mesh_send_pending)
        {
            if (k_uptime_get() < mesh_acknowledgment_deadline_ms)
            {
                return;
            }
            if (mesh_current_retries >= mesh_acknowledgment_retry_limit)
            {
                fail("mesh_acknowledgment_timeout", -ETIMEDOUT);
                return;
            }
            Destination destination{};
            destination.address = 0x0100U;
            const bool enabled = (mesh_acknowledged & 1U) != 0U;
            if (!NUCODEMesh.sendOnOff(destination, enabled, true,
                                      mesh_transaction_id))
            {
                fail("mesh_retry", NUCODEMesh.lastDriverError());
                return;
            }
            ++mesh_current_retries;
            ++mesh_acknowledgment_retries;
            mesh_acknowledgment_deadline_ms =
                k_uptime_get() + mesh_acknowledgment_timeout_ms;
            return;
        }
        if (mesh_acknowledged == packet_target / 2U && !mesh_restarted)
        {
            const int suspend_error = bt_mesh_suspend();
            const int resume_error = suspend_error == 0 ? bt_mesh_resume() : suspend_error;
            if (suspend_error != 0 || resume_error != 0)
            {
                fail("mesh_restart", resume_error);
                return;
            }
            mesh_restarted = true;
        }
        if (mesh_acknowledged >= packet_target)
        {
            if (!finished)
            {
                Serial.print(protocol);
                Serial.print("|RESULT|role=mesh_peer|iterations=20|sent=4000");
                Serial.print("|acknowledged=4000|restarts=1|failures=0");
                Serial.print("|configuration_retries=");
                Serial.print(mesh_configuration_retries);
                Serial.print("|acknowledgment_retries=");
                Serial.print(mesh_acknowledgment_retries);
                printSuffix();
                Serial.println();
                Serial.print(protocol);
                Serial.print("|END|role=mesh_peer|status=pass");
                printSuffix();
                Serial.println();
                finished = true;
            }
            return;
        }
        Destination destination{};
        destination.address = 0x0100U;
        if (!NUCODEMesh.sendOnOff(destination, (mesh_sent & 1U) != 0U, true,
                                  mesh_transaction_id))
        {
            fail("mesh_send", NUCODEMesh.lastDriverError());
            return;
        }
        ++mesh_sent;
        mesh_send_pending = true;
        mesh_acknowledgment_deadline_ms =
            k_uptime_get() + mesh_acknowledgment_timeout_ms;
    }
#endif

    /** @brief 5초 간격으로 역할별 진행률을 출력합니다. */
    void printProgress()
    {
        Serial.print(protocol);
        Serial.print("|PROGRESS|role=");
        Serial.print(roleName());
#if defined(NUCODE_M32_COEX_DUT)
        Serial.print("|ble=");
        Serial.print(ble_received);
        Serial.print("|radio=");
        Serial.print(radio_received);
#elif defined(NUCODE_M32_COEX_BLE_PEER)
        Serial.print("|sent=");
        Serial.print(ble_sent);
#elif defined(NUCODE_M32_COEX_RADIO_PEER)
        Serial.print("|sent=");
        Serial.print(completed_packets);
#else
        Serial.print("|sent=");
        Serial.print(mesh_acknowledged);
#endif
        printSuffix();
        Serial.println();
    }

    /** @brief BLE·Mesh·radio를 정지하고 자원 반환을 기록합니다. */
    void stopSession()
    {
        bool cleanup = true;
#if defined(NUCODE_M32_COEX_DUT)
#if defined(NUCODE_M32_COEX_154) || defined(NUCODE_M32_COEX_ESB)
        if (second_radio_started)
        {
            cleanup = stopSecondRadio() && cleanup;
            second_radio_started = false;
        }
#endif
        if (ble_started)
        {
            BLESerial.end();
            ble_started = false;
        }
#if !defined(NUCODE_M32_COEX_154) && !defined(NUCODE_M32_COEX_ESB)
        cleanup = bt_mesh_suspend() == 0 && cleanup;
#endif
        NUCODECoexistence.stop();
#elif defined(NUCODE_M32_COEX_BLE_PEER)
        if (ble_started)
        {
            BLESerial.end();
            ble_started = false;
        }
#elif defined(NUCODE_M32_COEX_RADIO_PEER)
        if (radio_started)
        {
            cleanup = stopSecondRadio() && cleanup;
            radio_started = false;
        }
#else
        cleanup = bt_mesh_suspend() == 0 && cleanup;
#endif
        Serial.print(protocol);
        Serial.print("|STOPPED|role=");
        Serial.print(roleName());
        Serial.print("|cleanup=");
        Serial.print(cleanup ? "pass" : "fail");
        printSuffix();
        Serial.println();
        stop_requested = false;
    }

    /** @brief PROBE·CLEAR·START·FINISH·STOP 명령을 처리합니다. */
    void processCommand()
    {
        if (::strcmp(command, "M32COEX|1|PROBE") == 0)
        {
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|core=");
            Serial.print(M32_COEX_CORE_REVISION);
            Serial.print("|scenario=");
            Serial.println(scenarioName());
            return;
        }
        if (acceptRevisionCommand(clear_prefix))
        {
            clearState();
            return;
        }
        if (!started && acceptRevisionCommand(start_prefix))
        {
            startSession();
            return;
        }
#if defined(NUCODE_M32_COEX_DUT)
        if (started && !finished &&
            ::strncmp(command, finish_prefix, ::strlen(finish_prefix)) == 0 &&
            ::strcmp(command + ::strlen(finish_prefix), nonce) == 0)
        {
            finishDut();
            return;
        }
#endif
        if ((finished || failed) && ::strncmp(command, stop_prefix, ::strlen(stop_prefix)) == 0 &&
            ::strcmp(command + ::strlen(stop_prefix), nonce) == 0)
        {
            stop_requested = true;
            return;
        }
        fail("command");
    }

    /** @brief CR/LF serial command를 overflow 없이 수집합니다. */
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
                command_length = 0U;
                fail("command_length");
                continue;
            }
            command[command_length++] = static_cast<char>(incoming);
        }
    }
} // namespace

void setup()
{
    Serial.begin(115200);
#if defined(NUCODE_M32_COEX_MESH) && !defined(NUCODE_M32_COEX_BLE_PEER)
    Configuration configuration{};
#if defined(NUCODE_M32_COEX_DUT)
    configuration.role = Role::node;
    configuration.local_address = 0x0100U;
    configuration.uuid[15] = 0xD0U;
#else
    configuration.role = Role::provisioner;
    configuration.local_address = 0x0001U;
    configuration.uuid[15] = 0xE0U;
#endif
    configuration.bearers = Bearer::advertising;
    configuration.uuid[0] = 0x32U;
    configuration.uuid[1] = 0x10U;
    configuration.uuid[2] = 0x54U;
    configuration.uuid[3] = 0x15U;
    NUCODEMesh.onEvent(onMeshEvent);
    if (!NUCODEMesh.begin(configuration))
    {
        fail("mesh_begin", NUCODEMesh.lastDriverError());
    }
#endif
}

void loop()
{
#if defined(NUCODE_M32_COEX_MESH) && !defined(NUCODE_M32_COEX_BLE_PEER)
    NUCODEMesh.poll();
#endif
#if defined(NUCODE_M32_COEX_DUT) || defined(NUCODE_M32_COEX_BLE_PEER)
    BLESerial.poll();
#endif
    pollSerial();
    if (stop_requested)
    {
        stopSession();
    }
    if (failed)
    {
        return;
    }
    if (started && !finished)
    {
#if defined(NUCODE_M32_COEX_DUT)
        driveBleReceiver();
#if defined(NUCODE_M32_COEX_154) || defined(NUCODE_M32_COEX_ESB)
        driveSecondRadioReceiver();
#endif
#elif defined(NUCODE_M32_COEX_BLE_PEER)
        driveBlePeer();
#elif defined(NUCODE_M32_COEX_RADIO_PEER)
        driveRadioPeer();
#else
        driveMeshPeer();
#endif
        if (k_uptime_get() >= progress_deadline_ms)
        {
            printProgress();
            progress_deadline_ms = k_uptime_get() + 5000;
        }
        if (k_uptime_get() >= deadline_ms)
        {
            fail("timeout");
        }
    }
    delay(1);
}
