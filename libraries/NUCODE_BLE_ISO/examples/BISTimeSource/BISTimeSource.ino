/**
 * @file BISTimeSource.ino
 * @brief HCI 기준시각을 붙인 사용자 BIS SDU를 보냅니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::BisTxSync;
using nucode::ble::iso::Error;
using nucode::ble::iso::RawBis;
using nucode::ble::iso::Role;

namespace
{
    /** @brief receiver와 공유하는 16-byte 예제 session ID입니다. */
    constexpr char sessionId[] = "NUCODE-TIME-BIS1";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    RawBis bis;
    std::uint16_t sequence = 0U;
    std::uint16_t timestamped = 0U;
    std::uint32_t connected_ms = 0U;
    std::uint32_t last_send_ms = 0U;
    std::uint32_t session_ms = 0U;
    std::uint32_t restart_ms = 0U;
    std::uint32_t next_timestamp_us = 0U;
    std::uint32_t first_hci_timestamp_us = 0U;
    std::uint32_t last_hci_timestamp_us = 0U;
    std::uint16_t last_hci_sequence = 0U;
    bool running = false;
    bool closing = false;
    bool timestamp_pending = false;
    bool hci_sync_seen = false;

    /** @brief 사용자가 편집할 수 있는 8-byte 측정 SDU를 만듭니다. */
    void makeFrame(std::uint16_t number, std::uint8_t payload[8])
    {
        payload[0] = 'T';
        payload[1] = 'I';
        payload[2] = static_cast<std::uint8_t>(number);
        payload[3] = static_cast<std::uint8_t>(number >> 8U);
        payload[4] = static_cast<std::uint8_t>(number ^ 0x5AU);
        payload[5] = static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
        payload[6] = 0xB1U;
        payload[7] = 0x50U;
    }

    /** @brief 사용자 ID로 periodic 광고와 BIG을 시작합니다. */
    void startSession()
    {
        const Error result = bis.begin(Role::bis_time_source,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("BIS start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restart_ms = millis() + 1000U;
            return;
        }
        sequence = 0U;
        timestamped = 0U;
        connected_ms = 0U;
        last_send_ms = 0U;
        session_ms = millis();
        next_timestamp_us = 0U;
        first_hci_timestamp_us = 0U;
        last_hci_timestamp_us = 0U;
        last_hci_sequence = 0U;
        running = true;
        closing = false;
        timestamp_pending = false;
        hci_sync_seen = false;
        Serial.println("BIS time source advertising");
    }
}

/** @brief 공개 API와 Core image revision을 Serial에 표시합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.print("BIS core revision=");
    Serial.println(RawBis::buildRevision());
    startSession();
}

/** @brief 첫 SDU의 HCI 시각을 기준으로 다음 99개에 timestamp를 붙입니다. */
void loop()
{
    if (!running)
    {
        if (static_cast<std::int32_t>(millis() - restart_ms) >= 0)
        {
            startSession();
        }
        delay(1);
        return;
    }
    const Error progress = bis.poll();
    if (progress == Error::transport_failure && !closing)
    {
        Serial.print("BIS error: ");
        Serial.println(bis.nativeError());
        bis.stop();
        closing = true;
    }
    if (!closing && bis.connected() && connected_ms == 0U)
    {
        connected_ms = millis();
    }
    if (!closing && connected_ms != 0U && millis() - connected_ms >= 3000U &&
        sequence == 0U)
    {
        std::uint8_t payload[8] = {};
        makeFrame(0U, payload);
        const Error result = bis.sendFrame(payload, sizeof(payload));
        if (result == Error::none)
        {
            sequence = 1U;
            last_send_ms = millis();
        }
        else if (result != Error::busy && result != Error::not_ready)
        {
            Serial.print("BIS send failed: ");
            Serial.println(static_cast<unsigned>(result));
            bis.stop();
            closing = true;
        }
    }
    if (!closing && sequence > 0U && sequence < 100U && !timestamp_pending)
    {
        BisTxSync sync = {};
        if (bis.takeTxSync(sync))
        {
            if (hci_sync_seen &&
                static_cast<std::int16_t>(sync.sequence - last_hci_sequence) <= 0)
            {
                Serial.println("BIS time TX sync sequence regressed");
                bis.stop();
                closing = true;
            }
            else
            {
                if (sequence == 1U)
                {
                    first_hci_timestamp_us = sync.timestamp_us;
                }
                last_hci_timestamp_us = sync.timestamp_us;
                last_hci_sequence = sync.sequence;
                hci_sync_seen = true;
                next_timestamp_us = sync.timestamp_us + 10000U;
                timestamp_pending = true;
            }
        }
    }
    if (!closing && timestamp_pending && sequence < 100U)
    {
        std::uint8_t payload[8] = {};
        makeFrame(sequence, payload);
        const Error result = bis.sendFrameAt(payload, sizeof(payload), next_timestamp_us);
        if (result == Error::none)
        {
            ++sequence;
            ++timestamped;
            last_send_ms = millis();
            timestamp_pending = false;
        }
        else if (result != Error::busy && result != Error::not_ready)
        {
            Serial.print("BIS time send failed: ");
            Serial.println(static_cast<unsigned>(result));
            bis.stop();
            closing = true;
        }
    }
    if (!closing && sequence == 100U && millis() - last_send_ms >= 500U)
    {
        Serial.print("BIS time sent frames=");
        Serial.print(sequence);
        Serial.print(" timestamped=");
        Serial.print(timestamped);
        Serial.print(" first_hci_ts=");
        Serial.print(first_hci_timestamp_us);
        Serial.print(" last_hci_ts=");
        Serial.println(last_hci_timestamp_us);
        bis.stop();
        closing = true;
    }
    if (!closing && millis() - session_ms >= 15000U)
    {
        Serial.print("BIS time source timeout frames=");
        Serial.println(sequence);
        bis.stop();
        closing = true;
    }
    if (closing && bis.stopped())
    {
        running = false;
        restart_ms = millis() + 1000U;
    }
    delay(1);
}
