/**
 * @file p2_iso_bis_source.ino
 * @brief 공개 BISSource의 100 SDU 경로를 20회 반복해 메모리를 계측합니다.
 */

#include <NUCODE_BLE_ISO.h>
#include <P2MemoryTelemetry.h>

using nucode::ble::iso::Error;
using nucode::ble::iso::RawBis;
using nucode::ble::iso::Role;

namespace
{
    constexpr char sessionId[] = "NUCODE-RAW-BIS01";
    constexpr std::uint16_t targetFrames = 100U;
    constexpr std::uint8_t targetCycles = 20U;
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");

    RawBis bis;
    std::uint16_t sequence = 0U;
    std::uint8_t cycles = 0U;
    std::uint32_t connectedMs = 0U;
    std::uint32_t lastSendMs = 0U;
    std::uint32_t restartMs = 0U;
    bool running = false;
    bool closing = false;
    bool finished = false;
    bool canceled = false;

    /** @brief 공개 예제의 8 B sequence payload를 만듭니다. */
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

    /** @brief periodic 광고와 BIG을 시작합니다. */
    void startSession()
    {
        const Error result = bis.begin(Role::bis_source,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("P2_BIS_FAIL begin=");
            Serial.println(static_cast<unsigned>(result));
            finished = true;
            return;
        }
        sequence = 0U;
        connectedMs = 0U;
        lastSendMs = 0U;
        running = true;
        closing = false;
    }

    /** @brief 전송 실패를 기록하고 BIG을 정리합니다. */
    void fail(const char *reason)
    {
        Serial.print("P2_BIS_FAIL ");
        Serial.println(reason);
        bis.stop();
        closing = true;
        canceled = true;
    }
}

/** @brief 공개 BIS API와 계측기를 초기화합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("P2_READY role=bis-source");
    nucode::test::reportMemory("ready");
    restartMs = millis() + 1000U;
}

/** @brief 수신 동기화 시간을 둔 뒤 100 SDU × 20세션을 송신합니다. */
void loop()
{
    if (Serial.available() > 0 && Serial.read() == 's' && !finished)
    {
        canceled = true;
        if (running && !closing)
        {
            bis.stop();
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
            Serial.println("P2_STOP role=bis-source canceled=1");
            finished = true;
        }
        else if (static_cast<std::int32_t>(millis() - restartMs) >= 0)
        {
            startSession();
        }
        delay(1);
        return;
    }

    const Error progress = bis.poll();
    if (progress == Error::transport_failure && !closing)
    {
        fail("transport");
    }
    if (!closing && bis.connected() && connectedMs == 0U)
    {
        connectedMs = millis();
    }
    if (!closing && connectedMs != 0U && millis() - connectedMs >= 2000U &&
        sequence < targetFrames && millis() - lastSendMs >= 20U)
    {
        std::uint8_t payload[8] = {};
        makeFrame(sequence, payload);
        const Error result = bis.sendFrame(payload, sizeof(payload));
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
        bis.stop();
        closing = true;
    }
    if (closing && bis.stopped())
    {
        running = false;
        if (!canceled && sequence == targetFrames)
        {
            ++cycles;
            Serial.print("P2_BIS_SENT cycle=");
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
            Serial.print("P2_STOP role=bis-source cycles=");
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
