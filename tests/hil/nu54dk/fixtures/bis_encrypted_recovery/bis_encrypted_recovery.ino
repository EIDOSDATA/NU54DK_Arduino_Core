/**
 * @file bis_encrypted_recovery.ino
 * @brief 잘못된 Code의 MIC 거부 후 같은 image에서 정상 BIS를 다시 수신합니다.
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_ISO.h>

using nucode::ble::iso::BisFrame;
using nucode::ble::iso::Error;
using nucode::ble::iso::RawBis;
using nucode::ble::iso::Role;

namespace
{
    constexpr char sessionId[] = "NUCODE-ENC-BIS01";
    constexpr char wrongCode[] = "MUCODE-BIS-CODE1";
    constexpr char correctCode[] = "NUCODE-BIS-CODE1";
    static_assert(sizeof(sessionId) == 17U, "session ID must be 16 bytes");
    static_assert(sizeof(wrongCode) == 17U, "wrong code must be 16 bytes");
    static_assert(sizeof(correctCode) == 17U, "correct code must be 16 bytes");

    enum class Phase : std::uint8_t
    {
        wrong,
        stopping_wrong,
        waiting_correct,
        correct,
        stopping_retry,
        stopping_success,
        stopping_failure,
        finished,
    };

    RawBis receiver;
    Phase phase = Phase::wrong;
    std::uint16_t leaked = 0U;
    std::uint16_t received = 0U;
    std::uint16_t missing = 0U;
    std::uint16_t errors = 0U;
    std::uint16_t last_sequence = 0U;
    std::uint8_t recovery_attempts = 0U;
    std::uint32_t phase_ms = 0U;
    std::uint32_t recovery_ms = 0U;
    std::uint32_t restart_ms = 0U;
    bool have_frame = false;

    /** @brief 공개 API에 16-byte session ID와 선택한 Code를 전달합니다. */
    Error beginWith(const char code[17])
    {
        return receiver.begin(Role::bis_encrypted_receiver,
                              reinterpret_cast<const std::uint8_t *>(sessionId),
                              reinterpret_cast<const std::uint8_t *>(code));
    }

    /** @brief 수신 payload의 사용자 sequence와 검사 byte를 확인합니다. */
    bool validFrame(const BisFrame &frame, std::uint16_t &number)
    {
        if (frame.length != 8U || frame.data[0] != 'B' || frame.data[1] != 'I' ||
            frame.data[6] != 0xB1U || frame.data[7] != 0x50U)
        {
            return false;
        }
        number = static_cast<std::uint16_t>(frame.data[2]) |
                 (static_cast<std::uint16_t>(frame.data[3]) << 8U);
        return number < 100U &&
               frame.data[4] == static_cast<std::uint8_t>(number ^ 0x5AU) &&
               frame.data[5] == static_cast<std::uint8_t>((number >> 8U) ^ 0xA5U);
    }

    /** @brief 이전 BIG 해제가 끝난 뒤 올바른 Code로 재동기화합니다. */
    void startCorrect()
    {
        if (recovery_attempts >= 3U || millis() - recovery_ms >= 30000U)
        {
            Serial.println("BIS recovery exhausted");
            phase = Phase::finished;
            return;
        }
        const Error result = beginWith(correctCode);
        if (result != Error::none)
        {
            Serial.print("BIS recovery begin failed: ");
            Serial.println(static_cast<unsigned>(result));
            phase = Phase::finished;
            return;
        }
        ++recovery_attempts;
        received = 0U;
        missing = 0U;
        errors = 0U;
        last_sequence = 0U;
        have_frame = false;
        phase_ms = millis();
        phase = Phase::correct;
        Serial.print("BIS recovery scanning attempt=");
        Serial.println(recovery_attempts);
    }

    /** @brief 정상 Code에서 99개 이상을 받으면 payload 결과를 출력합니다. */
    void reportCorrect()
    {
        if (have_frame)
        {
            missing += static_cast<std::uint16_t>(99U - last_sequence);
        }
        Serial.print("BIS wrong code recovered frames=");
        Serial.print(received);
        Serial.print(" missing=");
        Serial.print(missing);
        Serial.print(" errors=");
        Serial.println(errors);
        receiver.stop();
        phase = Phase::stopping_success;
    }
}

/** @brief 잘못된 Code로 첫 BIG 동기화를 요청합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.print("BIS core revision=");
    Serial.println(RawBis::buildRevision());
    const Error result = beginWith(wrongCode);
    if (result != Error::none)
    {
        Serial.print("BIS wrong code begin failed: ");
        Serial.println(static_cast<unsigned>(result));
        phase = Phase::finished;
        return;
    }
    phase_ms = millis();
    Serial.println("BIS wrong code scanning");
}

/** @brief MIC 거부·자원 반환·올바른 Code의 사용자 SDU 복구를 순서대로 확인합니다. */
void loop()
{
    if (phase == Phase::finished)
    {
        delay(10);
        return;
    }
    const Error progress = receiver.poll();
    if (phase == Phase::wrong)
    {
        BisFrame frame = {};
        while (receiver.readFrame(frame))
        {
            ++leaked;
        }
        if (progress == Error::transport_failure)
        {
            const int native = receiver.nativeError();
            if (native == -61 && leaked == 0U)
            {
                Serial.println("BIS wrong code rejected native=-61 leaked=0");
                recovery_ms = millis();
                phase = Phase::stopping_wrong;
            }
            else
            {
                Serial.print("BIS wrong code failed native=");
                Serial.print(native);
                Serial.print(" leaked=");
                Serial.println(leaked);
                phase = Phase::stopping_failure;
            }
            receiver.stop();
        }
        else if (millis() - phase_ms >= 12000U)
        {
            Serial.print("BIS wrong code timeout leaked=");
            Serial.println(leaked);
            receiver.stop();
            phase = Phase::stopping_failure;
        }
    }
    else if (phase == Phase::stopping_wrong && receiver.stopped())
    {
        Serial.println("BIS wrong code stopped");
        restart_ms = millis() + 500U;
        phase = Phase::waiting_correct;
    }
    else if (phase == Phase::waiting_correct &&
             static_cast<std::int32_t>(millis() - restart_ms) >= 0)
    {
        startCorrect();
    }
    else if (phase == Phase::correct)
    {
        BisFrame frame = {};
        while (receiver.readFrame(frame))
        {
            std::uint16_t number = 0U;
            if (!validFrame(frame, number))
            {
                ++errors;
                continue;
            }
            if (!have_frame)
            {
                missing = number;
                have_frame = true;
            }
            else if (number <= last_sequence)
            {
                ++errors;
                continue;
            }
            else
            {
                missing += static_cast<std::uint16_t>(number - last_sequence - 1U);
            }
            last_sequence = number;
            ++received;
        }
        if (received == 100U ||
            (progress == Error::peer_stopped && received >= 99U &&
             missing + (99U - last_sequence) <= 1U && errors == 0U))
        {
            reportCorrect();
        }
        else if (progress == Error::transport_failure ||
                 progress == Error::peer_stopped ||
                 millis() - phase_ms >= 12000U)
        {
            Serial.print("BIS recovery retry native=");
            Serial.print(receiver.nativeError());
            Serial.print(" frames=");
            Serial.println(received);
            receiver.stop();
            phase = Phase::stopping_retry;
        }
    }
    else if (phase == Phase::stopping_retry && receiver.stopped())
    {
        restart_ms = millis() + 500U;
        phase = Phase::waiting_correct;
    }
    else if (phase == Phase::stopping_success && receiver.stopped())
    {
        Serial.println("BIS wrong code recovery stopped");
        phase = Phase::finished;
    }
    else if (phase == Phase::stopping_failure && receiver.stopped())
    {
        phase = Phase::finished;
    }
    delay(1);
}
