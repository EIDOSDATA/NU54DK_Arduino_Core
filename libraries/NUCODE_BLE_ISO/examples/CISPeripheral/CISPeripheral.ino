/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: Adaptive capabilities (experimental) (adaptive, 실험적 대안)
 * @par 보드와 역할
 * 2대 — 1) CISCentral (central/client); 2) CISPeripheral (peripheral/server)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * nucode-build.json, prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_BLE_ISO/CISPeripheral`, sha256 `18ee2189f3b320ee1e36c28e4c281d3ceddf84e00e8c6ad11fe3537e5dbf65ca`
 * @nucode_example_setup_end */

/**
 * @file CISPeripheral.ino
 * @brief CIS 사용자 SDU의 내용과 순서를 Arduino 코드에서 검사합니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::CisFrame;
using nucode::ble::iso::Error;
using nucode::ble::iso::RawCis;
using nucode::ble::iso::Role;

namespace
{
    /** @brief central 예제와 같은 16-byte 연결 식별자입니다. */
    constexpr char sessionId[] = "NUCODE-RAW-CIS01";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    RawCis cis;
    std::uint16_t received = 0U;
    std::uint16_t errors = 0U;
    std::uint32_t restart_ms = 0U;
    bool running = false;
    bool saw_connection = false;
    bool closing = false;

    /** @brief Arduino 애플리케이션이 받은 payload·sequence를 검사합니다. */
    bool validFrame(const CisFrame &frame)
    {
        if (frame.length != 8U || frame.data[0] != 'N' || frame.data[1] != 'U' ||
            frame.data[6] != 0xC1U || frame.data[7] != 0x50U)
        {
            return false;
        }
        const std::uint16_t number = static_cast<std::uint16_t>(frame.data[2]) |
                                     (static_cast<std::uint16_t>(frame.data[3]) << 8U);
        return number == received &&
               frame.data[4] == static_cast<std::uint8_t>(number ^ 0x5AU) &&
               frame.data[5] == static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
    }

    /** @brief 공개 ISO API로 다음 광고 세션을 시작합니다. */
    void startSession()
    {
        const Error result = cis.begin(Role::cis_peripheral,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("CIS start failed: ");
            Serial.println(static_cast<unsigned>(result));
            restart_ms = millis() + 1000U;
            return;
        }
        received = 0U;
        errors = 0U;
        saw_connection = false;
        closing = false;
        running = true;
        Serial.println("CIS peripheral advertising");
    }
}

/** @brief Serial과 사용자 CIS 수신 세션을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.print("CIS core revision=");
    Serial.println(RawCis::buildRevision());
    startSession();
}

/** @brief 받은 SDU를 처리하고 연결 해제 뒤 다음 세션을 준비합니다. */
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
        Serial.print("CIS error: ");
        Serial.println(cis.nativeError());
        cis.stop();
        closing = true;
    }
    if (cis.connected())
    {
        saw_connection = true;
    }
    CisFrame frame = {};
    while (!closing && cis.readFrame(frame))
    {
        if (!validFrame(frame))
        {
            ++errors;
        }
        ++received;
    }
    if (!closing && saw_connection && !cis.connected())
    {
        Serial.print("CIS received frames=");
        Serial.print(received);
        Serial.print(" errors=");
        Serial.println(errors);
        cis.stop();
        closing = true;
    }
    if (closing && cis.stopped())
    {
        running = false;
        restart_ms = millis() + 1000U;
    }
    delay(1);
}
