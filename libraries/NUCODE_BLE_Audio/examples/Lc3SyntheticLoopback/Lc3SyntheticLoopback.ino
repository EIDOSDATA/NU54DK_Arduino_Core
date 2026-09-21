/**
 * @file Lc3SyntheticLoopback.ino
 * @brief 합성 PCM을 공개 LC3 API로 encode/decode하고 결과를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_Audio.h>

#include <cstdint>
#include <string.h>

using nucode::ble::audio::Error;
using nucode::ble::audio::Lc3Codec;
using nucode::ble::audio::Lc3Config;

namespace
{
    constexpr std::size_t frameSamples = 160U;
    constexpr std::size_t frameOctets = 40U;
    constexpr unsigned int frameCount = 100U;
    constexpr std::size_t nonceLength = 32U;
    constexpr char startPrefix[] = "NUCODE_AUDIO|1|START|nonce=";
    constexpr char startSuffix[] = "|scenario=lc3-loopback|iterations=100";
    constexpr char negativePrefix[] = "NUCODE_AUDIO|1|CHECK_INVALID|nonce=";
    constexpr char negativeSuffix[] = "|scenario=lc3-loopback";
    constexpr char stopPrefix[] = "NUCODE_AUDIO|1|STOP|nonce=";
    Lc3Codec codec;
    std::int16_t inputPcm[frameSamples] = {};
    std::int16_t outputPcm[frameSamples] = {};
    std::uint8_t encodedFrame[frameOctets] = {};
    char command[144] = {};
    char nonce[nonceLength + 1U] = {};
    std::size_t commandLength = 0U;
    bool codecReady = false;
    bool sessionActive = false;

    /** @brief 한 행의 실패를 bounded 진단 형식으로 출력합니다. */
    void fail(const char *stage, int code)
    {
        Serial.print("NUCODE_AUDIO|1|FAIL|nonce=");
        Serial.print(nonce[0] == '\0' ? "none" : nonce);
        Serial.print("|scenario=lc3-loopback|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.println(code);
    }

    /** @brief nonce가 소문자 128-bit hex인지 확인합니다. */
    bool validNonce(const char *value)
    {
        for (std::size_t index = 0U; index < nonceLength; ++index)
        {
            const char character = value[index];
            if (!((character >= '0' && character <= '9') ||
                  (character >= 'a' && character <= 'f')))
            {
                return false;
            }
        }
        return true;
    }

    /** @brief 고정 prefix와 suffix 사이의 session nonce를 읽습니다. */
    bool parseSession(const char *prefix, const char *suffix)
    {
        const std::size_t prefixLength = strlen(prefix);
        const std::size_t suffixLength = strlen(suffix);
        if ((commandLength != prefixLength + nonceLength + suffixLength) ||
            (memcmp(command, prefix, prefixLength) != 0) ||
            (memcmp(command + prefixLength + nonceLength, suffix, suffixLength) != 0))
        {
            return false;
        }
        memcpy(nonce, command + prefixLength, nonceLength);
        nonce[nonceLength] = '\0';
        return validNonce(nonce);
    }

    /** @brief frame 번호가 다른 유계 삼각파 PCM을 생성합니다. */
    void generatePcm(unsigned int frame)
    {
        for (std::size_t index = 0U; index < frameSamples; ++index)
        {
            const unsigned int phase =
                (frame * 17U + static_cast<unsigned int>(index)) % 64U;
            const int triangle = phase < 32U ? static_cast<int>(phase)
                                             : 63 - static_cast<int>(phase);
            inputPcm[index] = static_cast<std::int16_t>((triangle - 16) * 1200);
        }
    }

    /** @brief 공개 API로 합성 PCM 100 frame을 실제 LC3 경로에 통과시킵니다. */
    void runLoopback()
    {
        Serial.print("NUCODE_AUDIO|1|BEGIN|nonce=");
        Serial.print(nonce);
        Serial.println("|scenario=lc3-loopback|role=codec");
        Serial.print("NUCODE_AUDIO|1|IDENTITY|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(NUCODE_CORE_REVISION);
        Serial.print("|board=");
        Serial.print(NUCODE_BOARD_REVISION);
        Serial.print("|ncs=");
        Serial.print(NUCODE_NCS_REVISION);
        Serial.print("|zephyr=");
        Serial.println(NUCODE_ZEPHYR_REVISION);

        std::uint32_t encodedChecksum = 2166136261U;
        std::uint64_t decodedEnergy = 0U;
        unsigned int decodedFrames = 0U;
        for (unsigned int frame = 0U; frame < frameCount; ++frame)
        {
            generatePcm(frame);
            if (codec.encode(inputPcm, frameSamples, encodedFrame,
                             sizeof(encodedFrame)) != Error::none)
            {
                fail("encode", static_cast<int>(codec.lastError()));
                return;
            }
            for (std::size_t index = 0U; index < frameOctets; ++index)
            {
                encodedChecksum ^= encodedFrame[index];
                encodedChecksum *= 16777619U;
            }
            if (codec.decode(encodedFrame, frameOctets, outputPcm,
                             frameSamples) != Error::none)
            {
                fail("decode", static_cast<int>(codec.lastError()));
                return;
            }
            for (std::size_t index = 0U; index < frameSamples; ++index)
            {
                const std::int32_t sample = outputPcm[index];
                decodedEnergy += static_cast<std::uint64_t>(sample < 0 ? -sample : sample);
            }
            ++decodedFrames;
        }
        if ((encodedChecksum == 2166136261U) || (decodedEnergy == 0U))
        {
            fail("codec_output", -1);
            return;
        }

        Serial.print("NUCODE_AUDIO|1|END|nonce=");
        Serial.print(nonce);
        Serial.print("|scenario=lc3-loopback|encoded=");
        Serial.print(frameCount);
        Serial.print("|decoded=");
        Serial.print(decodedFrames);
        Serial.print("|frame_samples=");
        Serial.print(codec.frameSamples());
        Serial.print("|frame_octets=");
        Serial.print(codec.frameOctets());
        Serial.print("|checksum=");
        Serial.print(encodedChecksum);
        Serial.print("|energy=");
        Serial.print(static_cast<unsigned long>(decodedEnergy & 0xffffffffU));
        Serial.println("|plc=0|errors=0");
        sessionActive = true;
    }

    /** @brief 공개 API가 두 잘못된 LC3 구성을 거부하는지 확인합니다. */
    void runNegative()
    {
        Lc3Codec invalidCodec;
        Lc3Config invalidConfig = {};
        unsigned int rejected = 0U;
        invalidConfig.frame_duration_us = 1234U;
        if (invalidCodec.begin(invalidConfig) == Error::invalid_argument)
        {
            ++rejected;
        }
        invalidConfig.frame_duration_us = 10000U;
        invalidConfig.sample_rate_hz = 12345U;
        if (invalidCodec.begin(invalidConfig) == Error::invalid_argument)
        {
            ++rejected;
        }
        if (rejected != 2U)
        {
            fail("invalid_accept", -1);
            return;
        }
        Serial.print("NUCODE_AUDIO|1|NEG_END|nonce=");
        Serial.print(nonce);
        Serial.println("|scenario=lc3-loopback|rejected=2|invalid_accept=0");
    }

    /** @brief 완성된 bounded 명령 하나를 실행합니다. */
    void executeCommand()
    {
        if (strcmp(command, "NUCODE_AUDIO|1|PROBE") == 0)
        {
            Serial.println("NUCODE_AUDIO|1|READY|scenario=lc3-loopback|role=codec");
        }
        else if (parseSession(startPrefix, startSuffix))
        {
            runLoopback();
        }
        else if (parseSession(negativePrefix, negativeSuffix))
        {
            runNegative();
        }
        else if (sessionActive &&
                 (commandLength == strlen(stopPrefix) + nonceLength) &&
                 (memcmp(command, stopPrefix, strlen(stopPrefix)) == 0) &&
                 (memcmp(command + strlen(stopPrefix), nonce, nonceLength) == 0))
        {
            Serial.print("NUCODE_AUDIO|1|STOPPED|nonce=");
            Serial.print(nonce);
            Serial.println("|scenario=lc3-loopback");
            sessionActive = false;
            memset(nonce, 0, sizeof(nonce));
        }
        else
        {
            fail("command", -1);
        }
    }

    /** @brief UART 한 행을 모아 완성된 명령만 실행합니다. */
    void pollSerial()
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
                command[commandLength] = '\0';
                executeCommand();
                commandLength = 0U;
                return;
            }
            if (commandLength + 1U >= sizeof(command))
            {
                commandLength = 0U;
                fail("command_length", -1);
                return;
            }
            command[commandLength++] = value;
        }
    }
}

/** @brief Serial과 16 kHz, 10 ms, 40-byte LC3 codec을 시작합니다. */
void setup()
{
    Serial.begin(115200);
    Lc3Config config = {};
    config.sample_rate_hz = 16000U;
    config.frame_duration_us = 10000U;
    config.frame_octets = frameOctets;
    codecReady = codec.begin(config) == Error::none;
    if (!codecReady)
    {
        fail("begin", static_cast<int>(codec.lastError()));
    }
}

/** @brief 검증 명령을 받고 공개 codec API 실행을 Arduino main thread에서 진행합니다. */
void loop()
{
    if (codecReady)
    {
        pollSerial();
    }
    delay(1);
}
