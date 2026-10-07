/** @file @brief 실제 Apple codec의 byte 계약·fragment·session 음성 시험입니다.
 * SPDX-License-Identifier: MIT
 */
#include <NUCODE_BLE_CompanionCodec.h>
#include <assert.h>
#include <string.h>
using namespace nucode::ble::companion;

int main()
{
    Notification note{};
    const uint8_t notification[] = {0, 0x18, 6, 1, 0x78, 0x56, 0x34, 0x12};
    assert(decodeNotification(notification, sizeof(notification), note) == Error::none);
    assert(note.uid == 0x12345678 && note.category == 6);
    for (size_t size = 0; size < sizeof(notification); ++size)
    {
        assert(decodeNotification(notification, size, note) == Error::malformed);
    }
    uint8_t invalid[] = {3, 0x18, 6, 1, 0, 0, 0, 0};
    assert(decodeNotification(invalid, sizeof(invalid), note) == Error::malformed);
    invalid[0] = 0;
    invalid[1] = 0x80;
    assert(decodeNotification(invalid, sizeof(invalid), note) == Error::malformed);
    invalid[1] = 0;
    invalid[2] = 12;
    assert(decodeNotification(invalid, sizeof(invalid), note) == Error::malformed);

    uint8_t output[16] = {};
    size_t length = 0;
    assert(encodeAttributeRequest(0x12345678, 1, 128, output, sizeof(output), length) ==
           Error::none);
    const uint8_t expected[] = {0, 0x78, 0x56, 0x34, 0x12, 1, 128, 0};
    assert(length == sizeof(expected) && memcmp(output, expected, length) == 0);
    assert(encodeAttributeRequest(1, 8, 128, output, sizeof(output), length) ==
           Error::invalid_argument);
    assert(encodeAttributeRequest(1, 1, 129, output, sizeof(output), length) ==
           Error::invalid_argument);
    assert(encodeNotificationAction(note, true, output, sizeof(output)) == Error::none);
    assert(output[0] == 2 && output[5] == 0);
    note.flags = 0;
    assert(encodeNotificationAction(note, true, output, sizeof(output)) == Error::invalid_argument);

    const uint8_t response[] = {0, 0x78, 0x56, 0x34, 0x12, 1, 5, 0, 'h', 'e', 'l', 'l', 'o'};
    for (size_t split = 0; split <= sizeof(response); ++split)
    {
        AttributeAssembler parser;
        assert(parser.begin(0x12345678, 1) == Error::none);
        assert(parser.feed(response, split) == Error::none);
        assert(parser.feed(response + split, sizeof(response) - split) == Error::none);
        assert(parser.complete() && parser.length() == 5);
        assert(memcmp(parser.text(), "hello", 5) == 0);
        const uint8_t extra = 0;
        assert(parser.feed(&extra, 1) == Error::malformed);
        assert(!parser.complete());
    }
    AttributeAssembler parser;
    assert(parser.begin(99, 1) == Error::none);
    assert(parser.feed(response, sizeof(response)) == Error::malformed);
    assert(parser.begin(0x12345678, 2) == Error::none);
    assert(parser.feed(response, sizeof(response)) == Error::malformed);
    assert(parser.begin(0x12345678, 1) == Error::none);
    assert(parser.feed(response, 7) == Error::none);
    parser.reset();
    assert(parser.feed(response + 7, sizeof(response) - 7) == Error::stale_session);
    uint8_t oversized[137] = {};
    assert(parser.begin(1, 1) == Error::none);
    assert(parser.feed(oversized, sizeof(oversized)) == Error::overflow);

    MediaUpdate media{};
    const uint8_t update[] = {2, 2, 1, 'S', 'o', 'n', 'g'};
    assert(decodeMediaUpdate(update, sizeof(update), media) == Error::none);
    assert(media.entity == 2 && media.attribute == 2 && media.truncated && media.length == 4);
    const uint8_t wrong[] = {0, 3, 0};
    assert(decodeMediaUpdate(wrong, sizeof(wrong), media) == Error::malformed);
    const uint8_t flags[] = {2, 2, 2};
    assert(decodeMediaUpdate(flags, sizeof(flags), media) == Error::malformed);
    assert(decodeMediaUpdate(update, 2, media) == Error::malformed);
    const uint8_t commands[] = {0, 2, 3, 13};
    uint16_t mask = 0;
    assert(decodeMediaCommands(commands, sizeof(commands), mask) == Error::none);
    assert(mask == ((1U << 0) | (1U << 2) | (1U << 3) | (1U << 13)));
    const uint8_t duplicate[] = {2, 2};
    assert(decodeMediaCommands(duplicate, sizeof(duplicate), mask) == Error::malformed);
    const uint8_t out_of_range[] = {14};
    assert(decodeMediaCommands(out_of_range, sizeof(out_of_range), mask) == Error::malformed);
    assert(decodeMediaCommands(nullptr, 0, mask) == Error::none && mask == 0);
    return 0;
}
