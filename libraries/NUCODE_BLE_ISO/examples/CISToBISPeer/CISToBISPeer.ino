/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 3대 — 1) CISToBISPeer (peer); 2) CISToBISBridge (bridge); 3) CISToBISReceiver (receiver)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE_ISO/CISToBISPeer`, sha256 `899c0ae9af02b2c94193f05fce2df50ea095542824a3296a1de5dc88ede58787`
 * @nucode_example_setup_end */

/**
 * @file CISToBISPeer.ino
 * @brief bridge로 보낼 사용자 payload를 CIS에 싣고 세션을 반복합니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::Error;
using nucode::ble::iso::RawCis;
using nucode::ble::iso::Role;

namespace
{
    /** @brief bridge와 공유하는 16-byte 연결 식별자입니다. */
    constexpr char sessionId[] = "NUCODE-C2B-CIS01";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    RawCis cis;
    std::uint16_t sequence = 0U;
    std::uint32_t last_send_ms = 0U;
    std::uint32_t connected_ms = 0U;
    std::uint32_t session_ms = 0U;
    std::uint32_t restart_ms = 0U;
    bool running = false;
    bool closing = false;

    /** @brief 사용자가 바꿀 수 있는 8-byte 데모 측정값을 만듭니다. */
    void makeFrame(std::uint16_t number, std::uint8_t payload[8])
    {
        payload[0] = 'C';
        payload[1] = 'B';
        payload[2] = static_cast<std::uint8_t>(number);
        payload[3] = static_cast<std::uint8_t>(number >> 8U);
        payload[4] = static_cast<std::uint8_t>(number ^ 0x5AU);
        payload[5] = static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
        payload[6] = 0xC1U;
        payload[7] = 0x52U;
    }

    /** @brief 공개 ISO API로 새 연결을 시작합니다. */
    void startSession()
    {
        const Error result = cis.begin(Role::cis_to_bis_peer,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("CIS peer start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restart_ms = millis() + 1000U;
            return;
        }
        sequence = 0U;
        last_send_ms = millis();
        connected_ms = 0U;
        session_ms = millis();
        running = true;
        closing = false;
        Serial.println("CIS peer scanning");
    }
}

/** @brief Serial과 사용자 CIS 세션을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.print("CIS peer core revision=");
    Serial.println(RawCis::buildRevision());
    startSession();
}

/** @brief 사용자가 만든 100개 SDU를 보내고 연결 자원을 반환합니다. */
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

    const Error progress = cis.poll();
    if (progress == Error::transport_failure && !closing)
    {
        Serial.print("CIS peer error: ");
        Serial.println(cis.nativeError());
        cis.stop();
        closing = true;
    }
    if (!closing && cis.connected() && connected_ms == 0U)
    {
        connected_ms = millis();
    }
    if (!closing && connected_ms != 0U &&
        millis() - connected_ms >= 2500U && sequence < 100U &&
        millis() - last_send_ms >= 18U)
    {
        std::uint8_t payload[8] = {};
        makeFrame(sequence, payload);
        const Error result = cis.sendFrame(payload, sizeof(payload));
        if (result == Error::none)
        {
            ++sequence;
            last_send_ms = millis();
        }
        else if (result != Error::busy && result != Error::not_ready)
        {
            Serial.print("CIS peer send failed: ");
            Serial.println(static_cast<unsigned>(result));
            cis.stop();
            closing = true;
        }
    }
    if (!closing && sequence == 100U && millis() - last_send_ms >= 1000U)
    {
        Serial.print("CIS peer sent frames=");
        Serial.println(sequence);
        cis.stop();
        closing = true;
    }
    if (!closing && millis() - session_ms >= 15000U)
    {
        Serial.print("CIS peer timeout frames=");
        Serial.println(sequence);
        cis.stop();
        closing = true;
    }
    if (closing && cis.stopped())
    {
        Serial.println("CIS peer stopped");
        running = false;
        restart_ms = millis() + 1000U;
    }
    delay(1);
}
