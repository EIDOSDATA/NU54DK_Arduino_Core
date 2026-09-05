/** @file @brief 경로 Host 검사의 고정 장치입니다. */
#pragma once
struct device
{
    bool ready{true};
};
inline bool device_is_ready(const device *value)
{
    return value->ready;
}
