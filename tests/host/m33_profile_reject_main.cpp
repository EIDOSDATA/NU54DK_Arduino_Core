/** @file @brief 동일 target matcher의 두 callback 순서·중복·세대·timeout을 검사합니다.
 * SPDX-License-Identifier: MIT
 */
#include "ExpectedReject.h"
#include "ExpectedCgms.h"
#include <assert.h>

int main()
{
    uint8_t interval[] = {3U, 1U, 0U, 0U};
    assert(expectedCgmsInterval(interval, 3U));
    assert(!expectedCgmsInterval(nullptr, 3U));
    constexpr size_t invalid_lengths[] = {0U, 1U, 2U, 4U};
    for (size_t length : invalid_lengths)
    {
        assert(!expectedCgmsInterval(interval, length));
    }
    for (size_t offset = 0U; offset < 3U; ++offset)
    {
        ++interval[offset];
        assert(!expectedCgmsInterval(interval, 3U));
        --interval[offset];
    }
    for (unsigned first = 0U; first < 2U; ++first)
    {
        ExpectedReject<unsigned> value;
        assert(value.begin(0x101U, 5U, 1U, -5, 8U));
        assert(!value.begin(0x101U, 6U, 1U, -5, 8U));
        assert(first == 0U ? value.gap(0x101U, 5U, 1U, -5, 8U, 100U)
                           : value.detail(0x101U, 5U, 1U, -8, 8U, 100U));
        assert(!value.matched());
        assert(!value.finish());
        assert(first == 0U ? value.detail(0x101U, 5U, 1U, -8, 8U, 200U)
                           : value.gap(0x101U, 5U, 1U, -5, 8U, 200U));
        assert(value.matched());
        assert(!value.gap(0x101U, 5U, 1U, -5, 8U, 200U));
        assert(!value.detail(0x101U, 5U, 1U, -8, 8U, 200U));
        assert(value.finish());
        assert(!value.active());
        assert(value.begin(0x101U, 6U, 2U, -5, 8U));
        assert(!value.gap(0x201U, 6U, 2U, -5, 8U, 0U));
        assert(!value.gap(0x101U, 5U, 2U, -5, 8U, 0U));
        assert(!value.gap(0x101U, 6U, 1U, -5, 8U, 0U));
        assert(!value.gap(0x101U, 6U, 2U, -12, 8U, 0U));
        assert(!value.detail(0x101U, 6U, 2U, -8, 0U, 0U));
        assert(!value.detail(0x101U, 6U, 2U, -7, 8U, 0U));
        assert(value.detail(0x101U, 6U, 2U, -8, 8U, 0U));
        assert(value.expired(101U));
        assert(!value.gap(0x101U, 6U, 2U, -5, 8U, 101U));
    }
    ExpectedReject<unsigned> wrap;
    assert(wrap.begin(1U, 1U, 1U, -5, 8U));
    assert(wrap.gap(1U, 1U, 1U, -5, 8U, 0xfffffff0U));
    assert(wrap.detail(1U, 1U, 1U, -8, 8U, 0x10U));
    assert(wrap.finish());
    assert(wrap.begin(1U, 6U, 4U, -107, 0U));
    assert(wrap.acknowledge());
    assert(!wrap.acknowledge());
    assert(wrap.begin(1U, 6U, 4U, -107, 0U));
    assert(wrap.detail(1U, 6U, 4U, -107, 0U, 10U));
    assert(!wrap.acknowledge());
    assert(wrap.gap(1U, 6U, 4U, -107, 0U, 11U));
    assert(wrap.finish());
}
