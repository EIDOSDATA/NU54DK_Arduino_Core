/**
 * @file api_compat.cpp
 * @brief ArduinoCore-API 공통 구현에 필요한 libc 호환 함수를 제공합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <api/itoa.h>

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

namespace
{

    /** @brief 지원하는 정수 문자열 변환 진법의 최솟값입니다. */
    constexpr int minimum_radix = 2;

    /** @brief 지원하는 정수 문자열 변환 진법의 최댓값입니다. */
    constexpr int maximum_radix = 36;

    /**
     * @brief 부호 없는 정수를 지정한 진법의 문자열로 변환합니다.
     *
     * @tparam UnsignedValue 부호 없는 정수 형식입니다.
     * @param value 변환할 값입니다.
     * @param output 결과를 기록할 버퍼입니다.
     * @param radix 사용할 진법입니다.
     * @return 입력 output 주소입니다.
     */
    template <typename UnsignedValue>
    char *unsignedToString(UnsignedValue value, char *output, int radix) noexcept
    {
        if (output == nullptr)
        {
            return nullptr;
        }

        if ((radix < minimum_radix) || (radix > maximum_radix))
        {
            output[0] = '\0';
            return output;
        }

        char reversed[(sizeof(UnsignedValue) * 8U) + 1U] = {};
        size_t length = 0U;

        do
        {
            const auto digit = static_cast<unsigned int>(value % static_cast<UnsignedValue>(radix));
            reversed[length++] =
                static_cast<char>((digit < 10U) ? ('0' + digit) : ('a' + digit - 10U));
            value /= static_cast<UnsignedValue>(radix);
        } while (value != 0U);

        for (size_t index = 0U; index < length; ++index)
        {
            output[index] = reversed[length - index - 1U];
        }
        output[length] = '\0';
        return output;
    }

    /**
     * @brief 부호 있는 정수를 Arduino 규칙에 따라 문자열로 변환합니다.
     *
     * 10진수의 음수만 부호를 표시하며 다른 진법은 같은 폭의 부호 없는 값으로
     * 해석합니다.
     *
     * @tparam SignedValue 부호 있는 정수 형식입니다.
     * @param value 변환할 값입니다.
     * @param output 결과를 기록할 버퍼입니다.
     * @param radix 사용할 진법입니다.
     * @return 입력 output 주소입니다.
     */
    template <typename SignedValue, typename UnsignedValue>
    char *signedToString(SignedValue value, char *output, int radix) noexcept
    {
        if (output == nullptr)
        {
            return nullptr;
        }

        if ((radix == 10) && (value < 0))
        {
            output[0] = '-';
            const UnsignedValue magnitude =
                static_cast<UnsignedValue>(0U) - static_cast<UnsignedValue>(value);
            static_cast<void>(unsignedToString(magnitude, output + 1, radix));
            return output;
        }

        return unsignedToString(static_cast<UnsignedValue>(value), output, radix);
    }

} // namespace

extern "C" char *itoa(int value, char *string, int radix)
{
    return signedToString<int, unsigned int>(value, string, radix);
}

extern "C" char *ltoa(long value, char *string, int radix)
{
    return signedToString<long, unsigned long>(value, string, radix);
}

extern "C" char *utoa(unsigned int value, char *string, int radix)
{
    return unsignedToString(value, string, radix);
}

extern "C" char *ultoa(unsigned long value, char *string, int radix)
{
    return unsignedToString(value, string, radix);
}

/**
 * @brief 부동소수 값을 avr-libc 호환 폭과 정밀도로 문자열에 기록합니다.
 *
 * @param value 변환할 값입니다.
 * @param width 최소 출력 폭이며 음수이면 왼쪽 정렬합니다.
 * @param precision 소수점 이하 자릿수입니다.
 * @param output 결과를 기록할 버퍼입니다.
 * @return 입력 output 주소입니다.
 */
extern "C" char *dtostrf(double value, signed char width, unsigned char precision, char *output)
{
    if (output == nullptr)
    {
        return nullptr;
    }

    char format[20] = {};
    static_cast<void>(snprintf(format, sizeof(format), "%%%d.%df", static_cast<int>(width),
                               static_cast<int>(precision)));
    static_cast<void>(sprintf(output, format, value));
    return output;
}
