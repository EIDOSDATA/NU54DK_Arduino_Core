#pragma once
struct device { int id; };
extern device mock_gpio0, mock_gpio1, mock_gpio2;
inline bool device_is_ready(const device *) { return true; }
#define DEVICE_DT_GET(node) DEVICE_DT_EXPAND(node)
#define DEVICE_DT_EXPAND(node) (&mock_##node)
