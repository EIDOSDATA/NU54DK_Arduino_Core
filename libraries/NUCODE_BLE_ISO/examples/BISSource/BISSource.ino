/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) BISSource (source/transmitter); 2) BISReceiver (receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE_ISO/BISSource`, sha256 `3f30f3f1cbbf9c9de377d6c71c4fed726e5faa02cc33e11e23cffc6484c99a8b`
 * @nucode_example_setup_end */

/**
 * @file BISSource.ino
 * @brief 사용자 데이터를 한 Broadcast Isochronous Stream으로 보냅니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::Error;
using nucode::ble::iso::RawBis;
using nucode::ble::iso::Role;

namespace
{
    /** @brief receiver와 공유하는 16-byte 예제 session ID입니다. */
    constexpr char sessionId[] = "NUCODE-RAW-BIS01";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    RawBis bis;
    std::uint16_t sequence = 0U;
    std::uint32_t connected_ms = 0U;
    std::uint32_t last_send_ms = 0U;
    std::uint32_t restart_ms = 0U;
    bool running = false;
    bool closing = false;

    /** @brief 사용자가 편집할 수 있는 8-byte 측정 SDU를 만듭니다. */
    void makeFrame(std::uint16_t number, std::uint8_t payload[8])
    {
        payload[0] = 'B';
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
        const Error result = bis.begin(Role::bis_source,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("BIS start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restart_ms = millis() + 1000U;
            return;
        }
        sequence = 0U;
        connected_ms = 0U;
        last_send_ms = 0U;
        running = true;
        closing = false;
        Serial.println("BIS source advertising");
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

/** @brief receiver 동기화 뒤 사용자 SDU 100개를 보내고 BIG을 해제합니다. */
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
    if (!closing && connected_ms != 0U && millis() - connected_ms >= 2000U &&
        sequence < 100U && millis() - last_send_ms >= 20U)
    {
        std::uint8_t payload[8] = {};
        makeFrame(sequence, payload);
        const Error result = bis.sendFrame(payload, sizeof(payload));
        if (result == Error::none)
        {
            ++sequence;
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
    if (!closing && sequence == 100U && millis() - last_send_ms >= 500U)
    {
        Serial.print("BIS sent frames=");
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
