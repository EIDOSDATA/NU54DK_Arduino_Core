/**
 * @file protocol.h
 * @brief DTM UART 프레임과 허용 HCI 명령의 길이·범위 검사.
 * SPDX-License-Identifier: MIT
 */
#ifndef NUCODE_DIAGNOSTIC_PROTOCOL_H
#define NUCODE_DIAGNOSTIC_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/** @brief 단일 command만 보관하는 고정 크기 수신 상태. */
struct diagnostic_parser
{
    uint8_t bytes[259];
    size_t used;
    int64_t last_ms;
};

/** @brief bt_buf_get_tx()가 붙인 H4 command indicator 뒤의 opcode와 길이를 검사합니다. */
static inline bool diagnostic_hci_command_opcode(const uint8_t *bytes, size_t length,
                                                 uint16_t *opcode)
{
    if (bytes == NULL || opcode == NULL || length < 4 || bytes[0] != 0x01 ||
        length != (size_t)bytes[3] + 4)
    {
        return false;
    }
    *opcode = (uint16_t)bytes[1] | ((uint16_t)bytes[2] << 8);
    return true;
}

/** @brief 프레임 간격 초과 입력은 버리고 새 프레임으로 시작한다. */
static inline bool diagnostic_feed(struct diagnostic_parser *parser, bool h4, uint8_t byte,
                                   int64_t now_ms)
{
    if (parser->used > 0 && now_ms - parser->last_ms > (h4 ? 20 : 5))
    {
        parser->used = 0;
    }
    parser->last_ms = now_ms;
    if (h4 && parser->used == 0 && byte != 0x01)
    {
        return false;
    }
    parser->bytes[parser->used++] = byte;
    if ((!h4 && parser->used == 2) ||
        (h4 && parser->used >= 4 && parser->used == (size_t)parser->bytes[3] + 4))
    {
        parser->used = 0;
        return true;
    }
    return false;
}

/** @brief 허용 진단 opcode인지 확인하고 잘못된 parameter에는 0x12를 반환한다. */
static inline uint8_t diagnostic_hci_status(uint16_t opcode, const uint8_t *p, uint8_t length)
{
    switch (opcode)
    {
    case 0x0c03:
    case 0x1001:
    case 0x1003:
    case 0x2003:
    case 0x201f:
        return length == 0 ? 0 : 0x12;
    case 0x201d:
        return length == 1 && p[0] <= 39 ? 0 : 0x12;
    case 0x201e:
        return length == 3 && p[0] <= 39 && p[2] <= 7 ? 0 : 0x12;
    case 0x2033:
        return length == 3 && p[0] <= 39 && p[1] >= 1 && p[1] <= 3 && p[2] <= 1 ? 0 : 0x12;
    case 0x2034:
        return length == 4 && p[0] <= 39 && p[2] <= 7 && p[3] >= 1 && p[3] <= 4 ? 0 : 0x12;
    default:
        return 0x01;
    }
}

/** @brief RADIO를 시작하는 명령을 식별한다. */
static inline bool diagnostic_starts(uint16_t opcode)
{
    return opcode == 0x201d || opcode == 0x201e || opcode == 0x2033 || opcode == 0x2034;
}

#endif
