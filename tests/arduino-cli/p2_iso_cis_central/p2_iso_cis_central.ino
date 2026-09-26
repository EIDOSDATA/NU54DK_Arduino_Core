/**
 * @file p2_iso_cis_central.ino
 * @brief 공개 CISCentral payload 경로를 20회 반복하고 메모리를 계측합니다.
 */

#include <NUCODE_BLE_ISO.h>
#include <P2MemoryTelemetry.h>

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
    std::uint16_t sequence = 0U;
    std::uint8_t cycles = 0U;
    std::uint32_t lastSendMs = 0U;
    std::uint32_t restartMs = 0U;
    bool running = false;
    bool closing = false;
    bool finished = false;
    bool canceled = false;

    /** @brief 공개 예제와 동일한 8 B sequence payload를 생성합니다. */
    void makeFrame(std::uint16_t number, std::uint8_t payload[8])
    {
        payload[0] = 'N';
        payload[1] = 'U';
        payload[2] = static_cast<std::uint8_t>(number);
        payload[3] = static_cast<std::uint8_t>(number >> 8U);
        payload[4] = static_cast<std::uint8_t>(number ^ 0x5AU);
        payload[5] = static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
        payload[6] = 0xC1U;
        payload[7] = 0x50U;
    }

    /** @brief 정해진 role에서 한 CIS 세션을 시작합니다. */
    void startSession()
    {
        const Error result = cis.begin(Role::cis_central,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("P2_CIS_FAIL begin=");
            Serial.println(static_cast<unsigned>(result));
            finished = true;
            return;
        }
        sequence = 0U;
        lastSendMs = millis();
        running = true;
        closing = false;
    }

    /** @brief 재시도 없이 실패를 기록하고 CIS 자원을 반환합니다. */
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
    Serial.println("P2_READY role=cis-central");
    nucode::test::reportMemory("ready");
    restartMs = millis() + 1000U;
}

/** @brief 100 SDU × 20 세션을 보내고 STOP high-water를 출력합니다. */
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
            Serial.println("P2_STOP role=cis-central canceled=1");
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
    if (!closing && cis.connected() && sequence < targetFrames &&
        millis() - lastSendMs >= 20U)
    {
        std::uint8_t payload[8] = {};
        makeFrame(sequence, payload);
        const Error result = cis.sendFrame(payload, sizeof(payload));
        if (result == Error::none)
        {
            ++sequence;
            lastSendMs = millis();
        }
        else if (result != Error::busy && result != Error::not_ready)
        {
            fail("send");
        }
    }
    if (!closing && sequence == targetFrames && millis() - lastSendMs >= 500U)
    {
        cis.stop();
        closing = true;
    }
    if (closing && cis.stopped())
    {
        running = false;
        if (!canceled && sequence == targetFrames)
        {
            ++cycles;
            Serial.print("P2_CIS_SENT cycle=");
            Serial.print(cycles);
            Serial.print(" frames=");
            Serial.println(sequence);
        }
        else
        {
            canceled = true;
        }
        if (canceled || cycles == targetCycles)
        {
            nucode::test::reportMemory("stopped");
            Serial.print("P2_STOP role=cis-central cycles=");
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
