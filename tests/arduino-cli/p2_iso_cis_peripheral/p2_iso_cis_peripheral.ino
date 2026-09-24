/**
 * @file p2_iso_cis_peripheral.ino
 * @brief 공개 CISPeripheral 수신 경로를 20회 반복하고 메모리를 계측합니다.
 */

#include <NUCODE_BLE_ISO.h>
#include <P2MemoryTelemetry.h>

using nucode::ble::iso::CisFrame;
using nucode::ble::iso::Error;
using nucode::ble::iso::RawCis;
using nucode::ble::iso::Role;

namespace
{
    constexpr char sessionId[] = "NUCODE-RAW-CIS01";
    constexpr std::uint16_t targetFrames = 100U;
    constexpr std::uint8_t targetCycles = 20U;
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    RawCis cis;
    std::uint16_t received = 0U;
    std::uint16_t errors = 0U;
    std::uint8_t cycles = 0U;
    std::uint32_t restartMs = 0U;
    bool running = false;
    bool closing = false;
    bool sawConnection = false;
    bool finished = false;
    bool canceled = false;

    /** @brief 공개 예제와 같은 SDU 내용·순서 계약을 검증합니다. */
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

    /** @brief 다음 수신 광고 세션을 시작합니다. */
    void startSession()
    {
        const Error result = cis.begin(Role::cis_peripheral,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("P2_CIS_FAIL begin=");
            Serial.println(static_cast<unsigned>(result));
            finished = true;
            return;
        }
        received = 0U;
        errors = 0U;
        sawConnection = false;
        closing = false;
        running = true;
    }

    /** @brief 오류를 기록하고 CIS 수명을 정리합니다. */
    void fail(const char *reason)
    {
        Serial.print("P2_CIS_FAIL ");
        Serial.println(reason);
        cis.stop();
        closing = true;
        canceled = true;
    }
}

/** @brief Serial과 계측기를 초기화합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("P2_READY role=cis-peripheral");
    nucode::test::reportMemory("ready");
    restartMs = millis() + 500U;
}

/** @brief 100 SDU × 20 세션을 검증하고 STOP high-water를 출력합니다. */
void loop()
{
    if (Serial.available() > 0 && Serial.read() == 's' && !finished)
    {
        canceled = true;
        if (running && !closing)
        {
            cis.stop();
            closing = true;
        }
    }
    if (finished)
    {
        delay(10);
        return;
    }
    if (!running)
    {
        if (canceled)
        {
            nucode::test::reportMemory("stopped");
            Serial.println("P2_STOP role=cis-peripheral canceled=1");
            finished = true;
        }
        else if (static_cast<std::int32_t>(millis() - restartMs) >= 0)
        {
            startSession();
        }
        delay(1);
        return;
    }

    const Error progress = cis.poll();
    if (progress == Error::transport_failure && !closing)
    {
        fail("transport");
    }
    if (cis.connected())
    {
        sawConnection = true;
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
    if (!closing && sawConnection && !cis.connected())
    {
        if (received != targetFrames || errors != 0U)
        {
            fail("payload");
        }
        else
        {
            cis.stop();
            closing = true;
        }
    }
    if (closing && cis.stopped())
    {
        running = false;
        if (!canceled && received == targetFrames && errors == 0U)
        {
            ++cycles;
            Serial.print("P2_CIS_RECV cycle=");
            Serial.print(cycles);
            Serial.print(" frames=");
            Serial.print(received);
            Serial.print(" errors=");
            Serial.println(errors);
        }
        else
        {
            canceled = true;
        }
        if (canceled || cycles == targetCycles)
        {
            nucode::test::reportMemory("stopped");
            Serial.print("P2_STOP role=cis-peripheral cycles=");
            Serial.println(cycles);
            finished = true;
        }
        else
        {
            restartMs = millis() + 1000U;
        }
    }
    delay(1);
}
