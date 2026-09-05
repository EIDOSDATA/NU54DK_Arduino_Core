/** @file @brief 고정 AC-03 filesystem partition의 Host compile 표면입니다. */
#pragma once
#define DT_NODELABEL(name) 1
#define DT_NODE_EXISTS(node) 1
#define DT_REG_ADDR(node) 0x16c000
#define DT_REG_SIZE(node) 0x8000
#define DT_FIXED_PARTITION_ID(node) 1
