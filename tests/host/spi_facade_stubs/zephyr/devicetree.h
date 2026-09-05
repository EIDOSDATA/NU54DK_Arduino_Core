/** @file @brief SPI00 chosen과 UART00 비선택을 고정한 Host DTS 경계입니다. */
#pragma once
#define DT_HAS_CHOSEN(name) 1
#define DT_CHOSEN(name) 1
#define DT_NODELABEL(name) DT_NODE_##name
#define DT_NODE_spi00 1
#define DT_NODE_uart00 2
#define DT_NODE_EXISTS(node) 1
#define DT_SAME_NODE(lhs, rhs) ((lhs) == (rhs))
#define DT_NODE_HAS_STATUS_OKAY(node) ((node) == 1)
#define DT_PROP_OR(node, property, fallback) 32000000U
extern const struct device mock_spi_device;
#define DEVICE_DT_GET(node) (&mock_spi_device)
