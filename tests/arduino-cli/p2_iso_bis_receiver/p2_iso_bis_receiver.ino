/**
 * @file p2_iso_bis_receiver.ino
 * @brief 공개 BISReceiver의 수신·누락 경로를 20회 계측합니다.
 */

#include <NUCODE_BLE_ISO.h>
#include <P2MemoryTelemetry.h>

using nucode::ble::iso::BisFrame;
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
    std::uint16_t received = 0U;
    std::uint16_t errors = 0U;
    std::uint16_t missing = 0U;
    std::uint16_t lastSequence = 0U;
    std::uint8_t cycles = 0U;
    std::uint32_t sessionMs = 0U;
    std::uint32_t restartMs = 0U;
    bool running = false;
    bool closing = false;
    bool haveFrame = false;
    bool finished = false;
    bool canceled = false;

    /** @brief 공개 예제의 8 B SDU와 sequence를 검증합니다. */
    bool validFrame(const BisFrame &frame, std::uint16_t &number)
    {
        if (frame.length != 8U || frame.data[0] != 'B' || frame.data[1] != 'I' ||
            frame.data[6] != 0xB1U || frame.data[7] != 0x50U)
        {
            return false;
        }
        number = static_cast<std::uint16_t>(frame.data[2]) |
                 (static_cast<std::uint16_t>(frame.data[3]) << 8U);
        return number < targetFrames &&
               frame.data[4] == static_cast<std::uint8_t>(number ^ 0x5AU) &&
               frame.data[5] == static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
    }

    /** @brief session ID가 일치하는 BIG 수신을 시작합니다. */
    void startSession()
    {
        const Error result = bis.begin(Role::bis_receiver,
                                       reinterpret_cast<const std::uint8_t *>(sessionId));
        if (result != Error::none)
        {
            Serial.print("P2_BIS_FAIL begin=");
            Serial.println(static_cast<unsigned>(result));
            finished = true;
            return;
        }
        received = 0U;
        errors = 0U;
        missing = 0U;
        lastSequence = 0U;
        haveFrame = false;
        sessionMs = millis();
        running = true;
        closing = false;
    }

    /** @brief 실패 원인을 기록하고 BIS 자원을 반환합니다. */
    void fail(const char *reason)
    {
        Serial.print("P2_BIS_FAIL ");
        Serial.println(reason);
        bis.stop();
        closing = true;
        canceled = true;
    }

    /** @brief 마지막 sequence까지 누락을 계산하고 session을 닫습니다. */
    void finishSession()
    {
        if (haveFrame)
        {
            missing += static_cast<std::uint16_t>(99U - lastSequence);
        }
        if (received < 99U || received + missing != targetFrames ||
            missing > 1U || errors != 0U)
        {
            fail("payload");
        }
        else
        {
            bis.stop();
            closing = true;
        }
    }
}

/** @brief 공개 BIS API와 계측기를 초기화합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("P2_READY role=bis-receiver");
    nucode::test::reportMemory("ready");
    restartMs = millis() + 500U;
}

/** @brief 20개 BIG 세션의 SDU 순서·누락·오류를 검사합니다. */
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
            Serial.println("P2_STOP role=bis-receiver canceled=1");
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
    BisFrame frame = {};
    while (!closing && bis.readFrame(frame))
    {
        std::uint16_t number = 0U;
        if (!validFrame(frame, number))
        {
            ++errors;
            continue;
        }
        if (!haveFrame)
        {
            missing = number;
            haveFrame = true;
        }
        else if (number <= lastSequence)
        {
            ++errors;
            continue;
        }
        else
        {
            missing += static_cast<std::uint16_t>(number - lastSequence - 1U);
        }
        lastSequence = number;
        ++received;
    }
    if (!closing && received == targetFrames)
    {
        finishSession();
    }
    if (!closing && progress == Error::peer_stopped)
    {
        finishSession();
    }
    if (!closing && progress == Error::transport_failure)
    {
        fail("transport");
    }
    if (!closing && millis() - sessionMs >= 15000U)
    {
        fail("timeout");
    }
    if (closing && bis.stopped())
    {
        running = false;
        if (!canceled)
        {
            ++cycles;
            Serial.print("P2_BIS_RECV cycle=");
            Serial.print(cycles);
            Serial.print(" frames=");
            Serial.print(received);
            Serial.print(" missing=");
            Serial.print(missing);
            Serial.print(" errors=");
            Serial.println(errors);
        }
        if (canceled || cycles == targetCycles)
        {
            nucode::test::reportMemory("stopped");
            Serial.print("P2_STOP role=bis-receiver cycles=");
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
