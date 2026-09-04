#pragma once
#define DT_NODELABEL(node) node
#define DT_NODE_HAS_STATUS_OKAY(node) DT_STATUS_EXPAND(node)
#define DT_STATUS_EXPAND(node) DT_STATUS_##node
#define DT_STATUS_gpio0 1
#define DT_STATUS_gpio1 1
#define DT_STATUS_gpio2 1
#define DT_STATUS_uart20 TEST_UART_STATUS
#define DT_STATUS_uart30 TEST_UART_STATUS
#define IS_ENABLED(value) value
