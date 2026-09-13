/**
 * @file main.cpp
 * @brief 두 NU54DK로 Signed Write 재부팅·replay와 EATT 두 bearer를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_EATT.h>
#include <NUCODE_BLE_LegacySigning.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/att.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/reboot.h>

extern "C"
{
#include "att_internal.h"
#include "conn_internal.h"
#include "l2cap_internal.h"
#include "smp.h"
}

#include <cstddef>
#include <cstdint>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#ifndef M29_ADVANCED_CORE_REVISION
#error "M29_ADVANCED_CORE_REVISION is required"
#endif

static_assert(CONFIG_BT_SIGNING == 1);
static_assert(CONFIG_BT_EATT == 1);
static_assert(CONFIG_BT_EATT_MAX == 2);
static_assert(nucode::ble::BLELegacySigningProfile::deprecated);
static_assert(!nucode::ble::BLELegacySigningProfile::default_enabled);
static_assert(nucode::ble::BLEEattProfile::experimental);
static_assert(!nucode::ble::BLEEattProfile::default_enabled);
static_assert(nucode::ble::Eatt::maximum_bearers_per_connection == 2U);

extern "C" int nucode_ble_signing_persist(struct bt_conn *connection);
extern "C" int nucode_ble_signing_counters(struct bt_conn *connection,
                                            std::uint32_t *local_counter,
                                            std::uint32_t *remote_counter);

namespace
{

    constexpr char protocol[] = "M29W07|1";
    constexpr char ready_query[] = "M29W07|1|READY?";
    constexpr char start_prefix[] = "M29W07|1|START|mode=";
    constexpr char clear_prefix[] = "M29W07|1|CLEAR|nonce=";
    constexpr char reboot_prefix[] = "M29W07|1|REBOOT|nonce=";
    constexpr char core_suffix[] = "|core=" M29_ADVANCED_CORE_REVISION;
    constexpr char service_text[] = "90bf2a30-14f5-4d3d-92c7-299334932a20";
    constexpr char characteristic_text[] = "90bf2a31-14f5-4d3d-92c7-299334932a20";
    constexpr std::uint16_t company_id = 0x29a7U;
    constexpr std::size_t nonce_text_length = 32U;
    constexpr std::size_t nonce_binary_length = 16U;
    constexpr std::size_t legacy_flags_serialized_length = 3U;
    constexpr std::size_t legacy_manufacturer_serialized_length =
        2U + 2U + nonce_binary_length;
    constexpr std::uint32_t eatt_operations_per_bearer = 1000U;
    constexpr std::int64_t session_timeout_ms = 900000;
    constexpr std::int64_t replay_observation_ms = 1500;
    constexpr std::int64_t disconnect_settle_ms = 250;
    constexpr std::uint8_t signed_marker = 0x51U;
    constexpr std::uint8_t replay_marker = 0x52U;
    constexpr std::uint8_t eatt_production_marker = 0xe6U;
    constexpr std::uint8_t eatt_raw_marker = 0xe7U;
    constexpr std::size_t eatt_tx_buffer_count = 4U;

    static_assert(legacy_flags_serialized_length +
                      legacy_manufacturer_serialized_length <=
                  nucode::ble::Advertising::maximum_payload_length);

    enum class Mode : std::uint8_t
    {
        idle,
        pair,
        sign,
        replay,
        eatt,
    };

    enum class Phase : std::uint8_t
    {
        idle,
        scanning,
        connecting,
        discovering,
        securing,
        signing,
        eatt_connecting,
        eatt_reading,
        eatt_writing,
        eatt_traffic,
        replay_observation,
        disconnect_delay,
        disconnecting,
        complete,
    };

    const nucode::ble::BLEUuid service_uuid(service_text);
    const nucode::ble::BLEUuid characteristic_uuid(characteristic_text);
    nucode::ble::BLEService test_service(service_uuid);
    nucode::ble::BLECharacteristic test_characteristic(
        characteristic_uuid,
        nucode::ble::BLEProperty::read |
            nucode::ble::BLEProperty::write |
            nucode::ble::BLEProperty::write_without_response |
            nucode::ble::BLEProperty::authenticated_signed_write,
        nucode::ble::BLEPermission::read | nucode::ble::BLEPermission::write, 32U);

    char command[192] = {};
    std::size_t command_length = 0U;
    char nonce[nonce_text_length + 1U] = {};
    std::uint8_t nonce_binary[nonce_binary_length] = {};
    Mode mode = Mode::idle;
    Phase phase = Phase::idle;
    std::uint32_t iteration = 0U;
    bool session_active = false;
    bool session_finished = false;
    bool callback_context_valid = true;
    bool security_changed = false;
    bool pairing_seen = false;
    bool production_read_passed = false;
    bool production_write_passed = false;
    bool eatt_unencrypted_rejected = false;
    bool eatt_over_limit_rejected = false;
    std::int64_t session_deadline = 0;
    std::int64_t replay_deadline = 0;
    std::int64_t disconnect_at = 0;
    std::uint32_t expected_ble_errors = 0U;
    std::uint32_t server_signed_writes = 0U;
    std::uint32_t server_replay_writes = 0U;
    std::uint32_t server_eatt_production_writes = 0U;
    std::uint32_t server_eatt_received[2] = {};
    std::uint32_t server_eatt_next_sequence[2] = {};
    nucode::ble::BLEConnectionHandle connection_handle;
    struct k_thread *setup_thread = nullptr;
    atomic_t disconnect_reason = ATOMIC_INIT(-1);

    /** @brief Zephyr callback에서 실제 HCI disconnect reason을 진단용으로 보존합니다. */
    void onConnectionDisconnected(struct bt_conn *connection, std::uint8_t reason)
    {
        ARG_UNUSED(connection);
        atomic_set(&disconnect_reason, static_cast<atomic_val_t>(reason));
    }

    BT_CONN_CB_DEFINE(m29_advanced_connection_callbacks) = {
        .disconnected = onConnectionDisconnected,
    };

#if defined(NUCODE_M29_ADVANCED_CENTRAL)
    struct bt_l2cap_chan *eatt_channels[2] = {};
    std::uint32_t eatt_sent[2] = {};
    std::uint32_t eatt_next_bearer = 0U;
    atomic_t eatt_buffers_completed = ATOMIC_INIT(0);

    /** @brief EATT 전송 buffer가 controller 완료 뒤 pool로 돌아온 횟수를 셉니다. */
    void eattBufferDestroyed(struct net_buf *buffer)
    {
        atomic_inc(&eatt_buffers_completed);
        net_buf_destroy(buffer);
    }

    NET_BUF_POOL_FIXED_DEFINE(eatt_tx_pool, eatt_tx_buffer_count, 32U,
                              CONFIG_BT_CONN_TX_USER_DATA_SIZE, eattBufferDestroyed);
#endif

    /** @brief 현재 image의 고정 role 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M29_ADVANCED_CENTRAL)
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief 현재 검증 mode의 고정 이름을 반환합니다. */
    const char *modeName()
    {
        switch (mode)
        {
        case Mode::pair:
            return "pair";
        case Mode::sign:
            return "sign";
        case Mode::replay:
            return "replay";
        case Mode::eatt:
            return "eatt";
        default:
            return "idle";
        }
    }

    /** @brief 모든 session record에 iteration·nonce·exact revision을 붙입니다. */
    void printSuffix()
    {
        Serial.print("|iteration=");
        Serial.print(iteration);
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M29_ADVANCED_CORE_REVISION);
    }

    /** @brief 첫 실패를 고정 protocol로 출력하고 현재 session을 닫습니다. */
    void fail(const char *stage, int code = 0)
    {
        if (session_finished)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|mode=");
        Serial.print(modeName());
        Serial.print("|stage=");
        Serial.print(stage == nullptr ? "unknown" : stage);
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.println();
        session_finished = true;
        phase = Phase::complete;
    }

    /** @brief 공개 callback이 Arduino main thread에서 실행됐는지 검증합니다. */
    void checkCallbackContext()
    {
        if (k_current_get() != setup_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
    }

    /** @brief READY record를 현재 bond 수와 full revision으로 출력합니다. */
    void printReady()
    {
        Serial.print(protocol);
        Serial.print("|READY|role=");
        Serial.print(roleName());
        Serial.print("|bond_count=");
        Serial.print(BLESecurity.bondCount());
        Serial.print("|core=");
        Serial.println(M29_ADVANCED_CORE_REVISION);
    }

    /** @brief 현재 session BEGIN record를 고정 순서로 출력합니다. */
    void printBegin()
    {
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        Serial.print("|mode=");
        Serial.print(modeName());
        printSuffix();
        Serial.println();
    }

    /** @brief PASS END record를 출력하고 추가 시험 동작을 막습니다. */
    void printEnd()
    {
        Serial.print(protocol);
        Serial.print("|END|role=");
        Serial.print(roleName());
        Serial.print("|mode=");
        Serial.print(modeName());
        Serial.print("|status=pass|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        printSuffix();
        Serial.println();
        session_finished = true;
        phase = Phase::complete;
    }

    /** @brief 성공 record 뒤 central의 정상 disconnect가 끝날 때까지 END를 보류합니다. */
    void requestSessionEnd()
    {
        if (phase == Phase::disconnect_delay || phase == Phase::disconnecting)
        {
            return;
        }
        phase = Phase::disconnect_delay;
        disconnect_at = k_uptime_get() + disconnect_settle_ms;
    }

    /** @brief lowercase hexadecimal nibble을 binary 값으로 변환합니다. */
    std::uint8_t hexNibble(char value)
    {
        return static_cast<std::uint8_t>(value <= '9' ? value - '0' : value - 'a' + 10);
    }

    /** @brief 검증된 nonce 문자열을 RF payload용 16 byte로 변환합니다. */
    void buildNonceBinary()
    {
        for (std::size_t index = 0U; index < nonce_binary_length; ++index)
        {
            nonce_binary[index] = static_cast<std::uint8_t>(
                (hexNibble(nonce[index * 2U]) << 4U) |
                hexNibble(nonce[index * 2U + 1U]));
        }
    }

    /** @brief fixed suffix가 붙은 exact nonce command인지 검증합니다. */
    bool acceptNonceCommand(const char *prefix)
    {
        const std::size_t prefix_length = ::strlen(prefix);
        if (::strncmp(command, prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *nonce_start = command + prefix_length;
        for (std::size_t index = 0U; index < nonce_text_length; ++index)
        {
            const char value = nonce_start[index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        if (::strcmp(nonce_start + nonce_text_length, core_suffix) != 0)
        {
            return false;
        }
        ::memcpy(nonce, nonce_start, nonce_text_length);
        nonce[nonce_text_length] = '\0';
        buildNonceBinary();
        return true;
    }

    /** @brief START의 mode·iteration·nonce·revision을 고정 문법으로 해석합니다. */
    bool acceptStartCommand()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        if (::strncmp(command, start_prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *cursor = command + prefix_length;
        const char *iteration_field = nullptr;
        if (::strncmp(cursor, "pair|iteration=", 15U) == 0)
        {
            mode = Mode::pair;
            iteration_field = cursor + 15U;
        }
        else if (::strncmp(cursor, "sign|iteration=", 15U) == 0)
        {
            mode = Mode::sign;
            iteration_field = cursor + 15U;
        }
        else if (::strncmp(cursor, "replay|iteration=", 17U) == 0)
        {
            mode = Mode::replay;
            iteration_field = cursor + 17U;
        }
        else if (::strncmp(cursor, "eatt|iteration=", 15U) == 0)
        {
            mode = Mode::eatt;
            iteration_field = cursor + 15U;
        }
        else
        {
            return false;
        }
        char *end = nullptr;
        const unsigned long parsed = ::strtoul(iteration_field, &end, 10);
        if (end == iteration_field || parsed > UINT32_MAX ||
            ::strncmp(end, "|nonce=", 7U) != 0)
        {
            return false;
        }
        const char *nonce_start = end + 7U;
        for (std::size_t index = 0U; index < nonce_text_length; ++index)
        {
            const char value = nonce_start[index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        if (::strcmp(nonce_start + nonce_text_length, core_suffix) != 0)
        {
            return false;
        }
        iteration = static_cast<std::uint32_t>(parsed);
        if ((mode == Mode::pair && iteration != 0U) ||
            (mode == Mode::sign && (iteration == 0U || iteration > 20U)) ||
            (mode == Mode::replay && iteration != 21U) ||
            (mode == Mode::eatt && iteration != 22U))
        {
            return false;
        }
        ::memcpy(nonce, nonce_start, nonce_text_length);
        nonce[nonce_text_length] = '\0';
        buildNonceBinary();
        return true;
    }

    /** @brief generation link가 가진 CSRK 송수신 counter를 안전하게 복사합니다. */
    bool readSigningCounters(std::uint32_t &local_counter,
                             std::uint32_t &remote_counter)
    {
        struct bt_conn *connection =
            nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            return false;
        }
        const int result =
            nucode_ble_signing_counters(connection, &local_counter, &remote_counter);
        bt_conn_unref(connection);
        return result == 0;
    }

#if defined(NUCODE_M29_ADVANCED_CENTRAL)
    /** @brief advertising data 안의 exact 128-bit nonce를 확인합니다. */
    bool validRfNonce(const nucode::ble::BLEScanResult &result)
    {
        std::size_t cursor = 0U;
        while (cursor < result.payload_length)
        {
            const std::uint8_t field_length = result.payload[cursor];
            if (field_length == 0U || cursor + field_length >= result.payload_length)
            {
                break;
            }
            const std::uint8_t type = result.payload[cursor + 1U];
            if (type == BT_DATA_MANUFACTURER_DATA &&
                field_length == nonce_binary_length + 3U)
            {
                const std::uint8_t *value = &result.payload[cursor + 2U];
                return value[0] == static_cast<std::uint8_t>(company_id & 0xffU) &&
                       value[1] == static_cast<std::uint8_t>(company_id >> 8U) &&
                       ::memcmp(&value[2], nonce_binary, nonce_binary_length) == 0;
            }
            cursor += field_length + 1U;
        }
        return false;
    }

    /** @brief scan callback에서 exact nonce의 connectable peer만 선택합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        ARG_UNUSED(context);
        checkCallbackContext();
        if (session_finished || phase != Phase::scanning || !result.connectable ||
            result.scan_response || !validRfNonce(result))
        {
            return;
        }
        if (!BLEScan.stop())
        {
            fail("scan_stop");
            return;
        }
        Serial.print(protocol);
        Serial.print("|SCAN|role=central|mode=");
        Serial.print(modeName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        phase = Phase::connecting;
        if (!BLEConnection.connect(result.address, connection_handle))
        {
            fail("connect_start", BLEDevice.lastDriverError());
        }
    }

    /** @brief replay 시험용 signed ATT PDU 하나와 같은 byte의 재전송을 실제 RF로 보냅니다. */
    bool sendSignedOriginalAndReplay(std::uint16_t attribute_handle)
    {
        struct bt_conn *connection =
            nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr || bt_conn_get_security(connection) != BT_SECURITY_L1)
        {
            if (connection != nullptr)
            {
                bt_conn_unref(connection);
            }
            return false;
        }
        const std::uint8_t payload[8] = {replay_marker, nonce_binary[0], nonce_binary[1],
                                         nonce_binary[2], 0x29U, 0x07U, 0x01U, 0x00U};
        struct net_buf *original = bt_l2cap_create_pdu(nullptr, 0U);
        if (original == nullptr)
        {
            bt_conn_unref(connection);
            return false;
        }
        net_buf_add_u8(original, BT_ATT_OP_SIGNED_WRITE_CMD);
        net_buf_add_le16(original, attribute_handle);
        net_buf_add_mem(original, payload, sizeof(payload));
        if (bt_smp_sign(connection, original) < 0 || original->len > 64U)
        {
            net_buf_unref(original);
            bt_conn_unref(connection);
            return false;
        }
        std::uint8_t captured[64] = {};
        const std::size_t captured_length = original->len;
        ::memcpy(captured, original->data, captured_length);
        struct bt_l2cap_chan *fixed =
            bt_l2cap_le_lookup_tx_cid(connection, BT_L2CAP_CID_ATT);
        if (fixed == nullptr ||
            bt_l2cap_send_pdu(BT_L2CAP_LE_CHAN(fixed), original, nullptr, nullptr) < 0)
        {
            net_buf_unref(original);
            bt_conn_unref(connection);
            return false;
        }
        if (nucode_ble_signing_persist(connection) < 0)
        {
            bt_conn_unref(connection);
            return false;
        }
        struct net_buf *replay = bt_l2cap_create_pdu(nullptr, 0U);
        if (replay == nullptr)
        {
            bt_conn_unref(connection);
            return false;
        }
        net_buf_add_mem(replay, captured, captured_length);
        const int replay_result =
            bt_l2cap_send_pdu(BT_L2CAP_LE_CHAN(fixed), replay, nullptr, nullptr);
        if (replay_result < 0)
        {
            net_buf_unref(replay);
            bt_conn_unref(connection);
            return false;
        }
        bt_conn_unref(connection);
        return true;
    }

    /** @brief 현재 link의 동적 EATT channel 두 개를 CID 순서로 고정합니다. */
    bool captureEattChannels()
    {
        struct bt_conn *connection =
            nucode::ble::internal::referenceConnection(connection_handle);
        if (connection == nullptr)
        {
            return false;
        }
        eatt_channels[0] = nullptr;
        eatt_channels[1] = nullptr;
        std::size_t count = 0U;
        struct bt_l2cap_chan *channel = nullptr;
        SYS_SLIST_FOR_EACH_CONTAINER(&connection->channels, channel, node)
        {
            struct bt_l2cap_le_chan *le_channel = BT_L2CAP_LE_CHAN(channel);
            if (le_channel->state != BT_L2CAP_CONNECTED || le_channel->tx.cid < 0x0040U ||
                le_channel->rx.cid < 0x0040U)
            {
                continue;
            }
            if (count >= 2U)
            {
                bt_conn_unref(connection);
                return false;
            }
            eatt_channels[count++] = channel;
        }
        bt_conn_unref(connection);
        if (count != 2U)
        {
            return false;
        }
        if (BT_L2CAP_LE_CHAN(eatt_channels[0])->tx.cid >
            BT_L2CAP_LE_CHAN(eatt_channels[1])->tx.cid)
        {
            struct bt_l2cap_chan *temporary = eatt_channels[0];
            eatt_channels[0] = eatt_channels[1];
            eatt_channels[1] = temporary;
        }
        return true;
    }

    /** @brief 지정 EATT bearer에 sequence가 결합된 실제 ATT Write Command를 보냅니다. */
    int sendEattWrite(std::size_t bearer_index, std::uint32_t sequence)
    {
        struct net_buf *buffer = net_buf_alloc(&eatt_tx_pool, K_NO_WAIT);
        if (buffer == nullptr)
        {
            return 0;
        }
        const nucode::ble::BLERemoteCharacteristic characteristic =
            BLEClient.remoteCharacteristic(connection_handle);
        if (!characteristic.valid())
        {
            net_buf_unref(buffer);
            return -EINVAL;
        }
        std::uint8_t payload[8] = {};
        payload[0] = eatt_raw_marker;
        payload[1] = static_cast<std::uint8_t>(bearer_index);
        sys_put_le32(sequence, &payload[2]);
        payload[6] = nonce_binary[sequence % nonce_binary_length];
        payload[7] = static_cast<std::uint8_t>(payload[0] ^ payload[1] ^ payload[2] ^
                                               payload[3] ^ payload[4] ^ payload[5] ^
                                               payload[6]);
        net_buf_reserve(buffer, BT_L2CAP_SDU_CHAN_SEND_RESERVE);
        net_buf_add_u8(buffer, BT_ATT_OP_WRITE_CMD);
        net_buf_add_le16(buffer, characteristic.valueHandle());
        net_buf_add_mem(buffer, payload, sizeof(payload));
        const int result = bt_l2cap_chan_send(eatt_channels[bearer_index], buffer);
        if (result < 0)
        {
            net_buf_unref(buffer);
            return result;
        }
        return 1;
    }
#endif

    /** @brief server callback에서 signed/replay/EATT payload를 정량 검증합니다. */
    void onCharacteristicEvent(
        nucode::ble::BLECharacteristic &characteristic,
        const nucode::ble::BLECharacteristicEventInfo &information, void *context)
    {
        ARG_UNUSED(characteristic);
        ARG_UNUSED(context);
        checkCallbackContext();
        if (session_finished || information.event != nucode::ble::BLECharacteristicEvent::written ||
            information.connection != connection_handle || information.data == nullptr)
        {
            return;
        }
        if (mode == Mode::sign)
        {
            if (information.length != 8U || information.data[0] != signed_marker ||
                sys_get_le32(&information.data[1]) != iteration ||
                information.data[5] != nonce_binary[0])
            {
                fail("signed_payload");
                return;
            }
            ++server_signed_writes;
            std::uint32_t local_counter = 0U;
            std::uint32_t remote_counter = 0U;
            if (server_signed_writes != 1U ||
                !readSigningCounters(local_counter, remote_counter))
            {
                fail("signed_counter");
                return;
            }
            Serial.print(protocol);
            Serial.print("|SIGN|role=peripheral|writes=1|local_counter=");
            Serial.print(local_counter);
            Serial.print("|remote_counter=");
            Serial.print(remote_counter);
            printSuffix();
            Serial.println();
            requestSessionEnd();
            return;
        }
        if (mode == Mode::replay)
        {
            if (information.length != 8U || information.data[0] != replay_marker)
            {
                fail("replay_payload");
                return;
            }
            ++server_replay_writes;
            if (server_replay_writes == 1U)
            {
                phase = Phase::replay_observation;
                replay_deadline = k_uptime_get() + replay_observation_ms;
            }
            return;
        }
        if (mode != Mode::eatt)
        {
            fail("unexpected_server_write");
            return;
        }
        if (information.length == 4U && information.data[0] == eatt_production_marker)
        {
            ++server_eatt_production_writes;
            return;
        }
        if (information.length != 8U || information.data[0] != eatt_raw_marker ||
            information.data[1] > 1U)
        {
            fail("eatt_payload_shape");
            return;
        }
        const std::size_t bearer = information.data[1];
        const std::uint32_t sequence = sys_get_le32(&information.data[2]);
        const std::uint8_t checksum = static_cast<std::uint8_t>(
            information.data[0] ^ information.data[1] ^ information.data[2] ^
            information.data[3] ^ information.data[4] ^ information.data[5] ^
            information.data[6]);
        if (sequence != server_eatt_next_sequence[bearer] ||
            information.data[6] != nonce_binary[sequence % nonce_binary_length] ||
            information.data[7] != checksum)
        {
            fail("eatt_payload_sequence", static_cast<int>(bearer));
            return;
        }
        ++server_eatt_next_sequence[bearer];
        ++server_eatt_received[bearer];
    }

#if defined(NUCODE_M29_ADVANCED_CENTRAL)
    /** @brief production GATT completion을 Signed Write와 EATT phase에 연결합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information,
                       void *context)
    {
        ARG_UNUSED(context);
        checkCallbackContext();
        if (session_finished || information.connection != connection_handle)
        {
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            fail("gatt_operation", information.status);
            return;
        }
        if (phase == Phase::discovering)
        {
            if (information.event != nucode::ble::BLEGattClientEvent::discovery_complete)
            {
                fail("discovery_event", static_cast<int>(information.event));
                return;
            }
            if (!BLEClient.discovered(connection_handle))
            {
                fail("discovery_state");
                return;
            }
            if (mode == Mode::sign)
            {
                std::uint32_t local_counter = 0U;
                std::uint32_t remote_counter = 0U;
                if (BLESecurity.currentLevel() != nucode::ble::SecurityLevel::none ||
                    !readSigningCounters(local_counter, remote_counter))
                {
                    fail("signing_link_state");
                    return;
                }
                std::uint8_t payload[8] = {signed_marker, 0U, 0U, 0U,
                                           0U, nonce_binary[0], 0x29U, 0x07U};
                sys_put_le32(iteration, &payload[1]);
                phase = Phase::signing;
                if (!BLEClient.writeSigned(connection_handle, payload, sizeof(payload)))
                {
                    fail("signed_write_start", BLEDevice.lastDriverError());
                }
                return;
            }
            if (mode == Mode::replay)
            {
                if (!sendSignedOriginalAndReplay(
                        BLEClient.remoteCharacteristic(connection_handle).valueHandle()))
                {
                    fail("replay_send");
                    return;
                }
                phase = Phase::replay_observation;
                replay_deadline = k_uptime_get() + replay_observation_ms;
                return;
            }
            if (mode == Mode::pair)
            {
                phase = Phase::securing;
                if (!BLESecurity.requestSecurity())
                {
                    fail("pair_security_request", BLESecurity.lastDriverError());
                }
                return;
            }
            if (mode == Mode::eatt)
            {
                ++expected_ble_errors;
                if (BLEEatt.connect(connection_handle, 2U))
                {
                    --expected_ble_errors;
                    fail("eatt_unencrypted_accept");
                    return;
                }
                eatt_unencrypted_rejected = true;
                phase = Phase::securing;
                if (!BLESecurity.requestSecurity())
                {
                    fail("eatt_security_request", BLESecurity.lastDriverError());
                }
            }
            return;
        }
        if (mode == Mode::sign && phase == Phase::signing &&
            information.event == nucode::ble::BLEGattClientEvent::signed_write_complete)
        {
            std::uint32_t local_counter = 0U;
            std::uint32_t remote_counter = 0U;
            if (!readSigningCounters(local_counter, remote_counter))
            {
                fail("signed_counter");
                return;
            }
            Serial.print(protocol);
            Serial.print("|SIGN|role=central|writes=1|local_counter=");
            Serial.print(local_counter);
            Serial.print("|remote_counter=");
            Serial.print(remote_counter);
            printSuffix();
            Serial.println();
            requestSessionEnd();
            return;
        }
        if (mode == Mode::eatt && phase == Phase::eatt_reading)
        {
            if (information.event != nucode::ble::BLEGattClientEvent::read_complete ||
                information.bearer != nucode::ble::BLEGattBearer::enhanced)
            {
                fail("eatt_read_result");
                return;
            }
            production_read_passed = true;
            const std::uint8_t payload[4] = {eatt_production_marker, nonce_binary[0],
                                             0x29U, 0x07U};
            phase = Phase::eatt_writing;
            if (!BLEClient.write(connection_handle, payload, sizeof(payload),
                                 nucode::ble::BLEGattBearer::enhanced))
            {
                fail("eatt_write_start", BLEDevice.lastDriverError());
            }
            return;
        }
        if (mode == Mode::eatt && phase == Phase::eatt_writing)
        {
            if (information.event != nucode::ble::BLEGattClientEvent::write_complete ||
                information.bearer != nucode::ble::BLEGattBearer::enhanced)
            {
                fail("eatt_write_result");
                return;
            }
            production_write_passed = true;
            if (!captureEattChannels())
            {
                fail("eatt_channel_capture");
                return;
            }
            phase = Phase::eatt_traffic;
        }
    }
#endif

    /** @brief pairing callback을 auto-accept하고 실제 security 전환만 기록합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *context)
    {
        ARG_UNUSED(context);
        checkCallbackContext();
        if (session_finished)
        {
            return;
        }
        switch (event.event)
        {
        case nucode::ble::SecurityEvent::pairing_requested:
            if (!BLESecurity.acceptPairing(true))
            {
                fail("pairing_accept");
            }
            break;
        case nucode::ble::SecurityEvent::passkey_confirmation_requested:
            if (!BLESecurity.confirmPasskey(true))
            {
                fail("passkey_confirm");
            }
            break;
        case nucode::ble::SecurityEvent::paired:
            pairing_seen = true;
            break;
        case nucode::ble::SecurityEvent::security_changed:
            if (event.level >= nucode::ble::SecurityLevel::encrypted)
            {
                security_changed = true;
            }
            break;
        case nucode::ble::SecurityEvent::pairing_failed:
        case nucode::ble::SecurityEvent::timeout:
        case nucode::ble::SecurityEvent::error:
            fail("security_event", event.reason);
            break;
        default:
            break;
        }
    }

    /** @brief GAP event를 generation handle·role·고정 GATT phase에 연결합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        ARG_UNUSED(context);
        checkCallbackContext();
        if (!session_active || session_finished)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::error)
        {
            if (expected_ble_errors > 0U)
            {
                --expected_ble_errors;
                return;
            }
            const int driver_error = BLEDevice.lastDriverError();
#if defined(NUCODE_M29_ADVANCED_CENTRAL)
            /** @brief Discovery 오류는 뒤따르는 link별 GATT event에서 정확한 stage로 판정합니다. */
            if (phase == Phase::discovering && driver_error == -ENOENT)
            {
                return;
            }
#endif
            fail("gap_error", driver_error);
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
#if defined(NUCODE_M29_ADVANCED_CENTRAL)
            if (information.role != nucode::ble::BLELinkRole::central)
            {
                fail("connection_role");
                return;
            }
            phase = Phase::discovering;
            if (!BLEClient.discover(connection_handle, service_uuid, characteristic_uuid))
            {
                fail("discovery_start");
            }
#else
            if (information.role != nucode::ble::BLELinkRole::peripheral)
            {
                fail("connection_role");
            }
#endif
            return;
        }
        if (information.event == nucode::ble::BLEEvent::disconnected &&
            information.connection == connection_handle)
        {
            if (phase == Phase::disconnect_delay || phase == Phase::disconnecting)
            {
                printEnd();
                return;
            }
            fail("unexpected_disconnect", static_cast<int>(atomic_get(&disconnect_reason)));
        }
    }

    /** @brief 검증된 START에서 role별 scan 또는 connectable advertising을 시작합니다. */
    void startSession()
    {
        if (!acceptStartCommand())
        {
            fail("start_record");
            return;
        }
        if (mode != Mode::pair && BLESecurity.bondCount() != 1U)
        {
            fail("bond_count", static_cast<int>(BLESecurity.bondCount()));
            return;
        }
        session_active = true;
        session_finished = false;
        callback_context_valid = true;
        security_changed = false;
        pairing_seen = false;
        production_read_passed = false;
        production_write_passed = false;
        eatt_unencrypted_rejected = false;
        eatt_over_limit_rejected = false;
        expected_ble_errors = 0U;
        server_signed_writes = 0U;
        server_replay_writes = 0U;
        server_eatt_production_writes = 0U;
        server_eatt_received[0] = 0U;
        server_eatt_received[1] = 0U;
        server_eatt_next_sequence[0] = 0U;
        server_eatt_next_sequence[1] = 0U;
        atomic_set(&disconnect_reason, -1);
        connection_handle = {};
        session_deadline = k_uptime_get() + session_timeout_ms;
        disconnect_at = 0;
#if defined(NUCODE_M29_ADVANCED_CENTRAL)
        eatt_channels[0] = nullptr;
        eatt_channels[1] = nullptr;
        eatt_sent[0] = 0U;
        eatt_sent[1] = 0U;
        eatt_next_bearer = 0U;
        atomic_set(&eatt_buffers_completed, 0);
#endif
        printBegin();
#if defined(NUCODE_M29_ADVANCED_CENTRAL)
        phase = Phase::scanning;
        if (!BLEScan.clearFilters())
        {
            fail("scan_clear", BLEDevice.lastDriverError());
            return;
        }
        if (!BLEScan.start(true))
        {
            fail("scan_start", BLEDevice.lastDriverError());
        }
#else
        phase = Phase::connecting;
        if (!BLEAdvertising.clear())
        {
            fail("advertising_clear", BLEDevice.lastDriverError());
            return;
        }
        if (!BLEAdvertising.setConnectable(true))
        {
            fail("advertising_connectable", BLEDevice.lastDriverError());
            return;
        }
        if (!BLEAdvertising.setManufacturerData(company_id, nonce_binary,
                                                 sizeof(nonce_binary)))
        {
            fail("advertising_nonce", BLEDevice.lastDriverError());
            return;
        }
        if (!BLEAdvertising.setScanResponseName(true))
        {
            fail("advertising_name", BLEDevice.lastDriverError());
            return;
        }
        if (!BLEAdvertising.start())
        {
            fail("advertising_start", BLEDevice.lastDriverError());
            return;
        }
        Serial.print(protocol);
        Serial.print("|ADVERTISE|role=peripheral|mode=");
        Serial.print(modeName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
#endif
    }

    /** @brief 전체 bond를 지우고 고정 확인 record를 출력합니다. */
    void clearBonds()
    {
        if (!acceptNonceCommand(clear_prefix) || !BLESecurity.eraseAllBonds())
        {
            fail("clear_bonds", BLESecurity.lastDriverError());
            return;
        }
        Serial.print(protocol);
        Serial.print("|CLEAR|role=");
        Serial.print(roleName());
        Serial.print("|bond_count=");
        Serial.print(BLESecurity.bondCount());
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.println(M29_ADVANCED_CORE_REVISION);
    }

    /** @brief exact reboot command만 warm reset으로 연결합니다. */
    void rebootTarget()
    {
        if (!acceptNonceCommand(reboot_prefix))
        {
            fail("reboot_record");
            return;
        }
        Serial.print(protocol);
        Serial.print("|REBOOTING|role=");
        Serial.print(roleName());
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.println(M29_ADVANCED_CORE_REVISION);
        delay(100U);
        sys_reboot(SYS_REBOOT_WARM);
    }

    /** @brief 완전한 UART command 한 줄만 고정 dispatcher에 전달합니다. */
    void executeCommand()
    {
        if (::strcmp(command, ready_query) == 0)
        {
            printReady();
        }
        else if (::strncmp(command, clear_prefix, ::strlen(clear_prefix)) == 0)
        {
            clearBonds();
        }
        else if (::strncmp(command, reboot_prefix, ::strlen(reboot_prefix)) == 0)
        {
            rebootTarget();
        }
        else if (!session_active)
        {
            startSession();
        }
        else
        {
            fail("unexpected_command");
        }
    }

    /** @brief UART의 newline command를 fixed buffer로 조립합니다. */
    void pollHostCommand()
    {
        while (Serial.available() > 0)
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
                executeCommand();
                command_length = 0U;
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                command_length = 0U;
                fail("command_overflow");
                return;
            }
            command[command_length++] = value;
        }
    }

    /** @brief pair 완료 뒤 CSRK 존재와 bond 저장 상태를 role별로 보고합니다. */
    void drivePairCompletion()
    {
        if (mode != Mode::pair || !security_changed || !pairing_seen ||
            BLESecurity.bondCount() != 1U || phase == Phase::disconnect_delay ||
            phase == Phase::disconnecting)
        {
            return;
        }
        std::uint32_t local_counter = 0U;
        std::uint32_t remote_counter = 0U;
        if (!readSigningCounters(local_counter, remote_counter))
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|PAIR|role=");
        Serial.print(roleName());
        Serial.print("|bond_count=1|local_counter=");
        Serial.print(local_counter);
        Serial.print("|remote_counter=");
        Serial.print(remote_counter);
        printSuffix();
        Serial.println();
        requestSessionEnd();
    }

    /** @brief replay observation window 뒤 server write가 한 번뿐인지 판정합니다. */
    void driveReplayCompletion()
    {
        if (mode != Mode::replay || phase != Phase::replay_observation ||
            k_uptime_get() < replay_deadline)
        {
            return;
        }
#if defined(NUCODE_M29_ADVANCED_CENTRAL)
        std::uint32_t local_counter = 0U;
        std::uint32_t remote_counter = 0U;
        if (!readSigningCounters(local_counter, remote_counter))
        {
            fail("replay_counter");
            return;
        }
        Serial.print(protocol);
        Serial.print("|REPLAY|role=central|sent=2|signed_originals=1|replays=1|");
        Serial.print("local_counter=");
        Serial.print(local_counter);
        Serial.print("|remote_counter=");
        Serial.print(remote_counter);
#else
        if (server_replay_writes != 1U)
        {
            fail("replay_accept_count", static_cast<int>(server_replay_writes));
            return;
        }
        std::uint32_t local_counter = 0U;
        std::uint32_t remote_counter = 0U;
        if (!readSigningCounters(local_counter, remote_counter))
        {
            fail("replay_counter");
            return;
        }
        Serial.print(protocol);
        Serial.print("|REPLAY|role=peripheral|writes=1|replay_accepts=0|");
        Serial.print("local_counter=");
        Serial.print(local_counter);
        Serial.print("|remote_counter=");
        Serial.print(remote_counter);
#endif
        printSuffix();
        Serial.println();
        requestSessionEnd();
    }

    /** @brief encrypted link에서 EATT 연결·production API·bearer별 raw 부하를 진행합니다. */
    void driveEatt()
    {
        if (mode != Mode::eatt || !security_changed ||
            phase == Phase::disconnect_delay || phase == Phase::disconnecting)
        {
            return;
        }
#if defined(NUCODE_M29_ADVANCED_CENTRAL)
        if (phase == Phase::securing)
        {
            phase = Phase::eatt_connecting;
            if (!BLEEatt.connect(connection_handle, 2U))
            {
                fail("eatt_connect", BLEDevice.lastDriverError());
            }
            return;
        }
        if (phase == Phase::eatt_connecting && BLEEatt.count(connection_handle) == 2U)
        {
            ++expected_ble_errors;
            if (BLEEatt.connect(connection_handle, 1U))
            {
                --expected_ble_errors;
                fail("eatt_over_limit_accept");
                return;
            }
            eatt_over_limit_rejected = true;
            phase = Phase::eatt_reading;
            if (!BLEClient.read(connection_handle, nucode::ble::BLEGattBearer::enhanced))
            {
                fail("eatt_read_start");
            }
            return;
        }
        if (phase != Phase::eatt_traffic)
        {
            return;
        }
        for (std::size_t attempt = 0U; attempt < eatt_tx_buffer_count; ++attempt)
        {
            const std::size_t bearer = eatt_next_bearer % 2U;
            eatt_next_bearer = static_cast<std::uint32_t>((eatt_next_bearer + 1U) % 2U);
            if (eatt_sent[bearer] >= eatt_operations_per_bearer)
            {
                continue;
            }
            const int send_result = sendEattWrite(bearer, eatt_sent[bearer]);
            if (send_result < 0)
            {
                fail("eatt_raw_send", send_result);
                return;
            }
            if (send_result > 0)
            {
                ++eatt_sent[bearer];
            }
        }
        if (eatt_sent[0] == eatt_operations_per_bearer &&
            eatt_sent[1] == eatt_operations_per_bearer &&
            atomic_get(&eatt_buffers_completed) ==
                static_cast<atomic_val_t>(eatt_operations_per_bearer * 2U))
        {
            Serial.print(protocol);
            Serial.print("|EATT|role=central|bearers=2|ops_bearer0=1000|");
            Serial.print("ops_bearer1=1000|unencrypted_rejected=");
            Serial.print(eatt_unencrypted_rejected ? 1 : 0);
            Serial.print("|over_limit_rejected=");
            Serial.print(eatt_over_limit_rejected ? 1 : 0);
            Serial.print("|production_read=");
            Serial.print(production_read_passed ? 1 : 0);
            Serial.print("|production_write=");
            Serial.print(production_write_passed ? 1 : 0);
            Serial.print("|deadlocks=0|starvation=0");
            printSuffix();
            Serial.println();
            requestSessionEnd();
        }
#else
        if (BLEEatt.count(connection_handle) != 2U ||
            server_eatt_received[0] != eatt_operations_per_bearer ||
            server_eatt_received[1] != eatt_operations_per_bearer)
        {
            return;
        }
        if (server_eatt_production_writes != 1U)
        {
            fail("eatt_production_write_count",
                 static_cast<int>(server_eatt_production_writes));
            return;
        }
        Serial.print(protocol);
        Serial.print("|EATT|role=peripheral|bearers=2|ops_bearer0=1000|");
        Serial.print("ops_bearer1=1000|production_writes=1|payload_errors=0|");
        Serial.print("deadlocks=0|starvation=0");
        printSuffix();
        Serial.println();
        requestSessionEnd();
#endif
    }

    /** @brief 성공 결과 정착 뒤 central만 정상 disconnect를 시작합니다. */
    void driveSessionDisconnect()
    {
#if defined(NUCODE_M29_ADVANCED_CENTRAL)
        if (phase != Phase::disconnect_delay || k_uptime_get() < disconnect_at)
        {
            return;
        }
        phase = Phase::disconnecting;
        if (!BLEConnection.disconnect(connection_handle))
        {
            fail("disconnect_start", BLEDevice.lastDriverError());
        }
#endif
    }

} // namespace

/** @brief BLE/GATT/security callback과 strict W07 target protocol을 초기화합니다. */
void setup()
{
    setup_thread = k_current_get();
    Serial.begin(115200);
    const std::int64_t serial_deadline = k_uptime_get() + 5000;
    while (!Serial && k_uptime_get() < serial_deadline)
    {
        delay(10);
    }
    const std::uint8_t initial_value[4] = {0x29U, 0x07U, 0x00U, 0x01U};
    if (!test_characteristic.setValue(initial_value, sizeof(initial_value)) ||
        !test_service.addCharacteristic(test_characteristic) ||
        !BLEDevice.addService(test_service))
    {
        fail("gatt_schema");
        return;
    }
    test_characteristic.onEvent(onCharacteristicEvent);
    BLESecurity.onEvent(onSecurityEvent);
    const nucode::ble::SecurityConfig security = {
        nucode::ble::SecurityLevel::encrypted, true, 30000U,
        nucode::ble::SecurityIoCapability::no_input_output};
    if (!BLESecurity.begin(security))
    {
        fail("security_begin", BLESecurity.lastDriverError());
        return;
    }
    BLEDevice.onEventInfo(onBleEvent);
#if defined(NUCODE_M29_ADVANCED_CENTRAL)
    BLEScan.onResult(onScanResult);
    BLEClient.onDetailedEvent(onClientEvent);
#endif
    if (!BLEDevice.begin(roleName()))
    {
        fail("device_begin", BLEDevice.lastDriverError());
        return;
    }
    printReady();
}

/** @brief Host command, BLE main-thread event와 bounded W07 상태 기계를 진행합니다. */
void loop()
{
    pollHostCommand();
    BLEDevice.poll();
    BLESecurity.poll();
    if (!session_active || session_finished)
    {
        delay(1);
        return;
    }
    drivePairCompletion();
    driveReplayCompletion();
    driveEatt();
    driveSessionDisconnect();
    if (!session_finished && k_uptime_get() >= session_deadline)
    {
        fail("timeout");
    }
    delay(1);
}
