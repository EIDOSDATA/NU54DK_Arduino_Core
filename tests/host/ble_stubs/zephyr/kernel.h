/** @file @brief BLE Host의 실제 mutex와 고정 크기 message queue입니다. */
#pragma once
#include "../../serial_driver_stubs/zephyr/kernel.h"
#include <cstring>
#include <cerrno>
#define K_NO_WAIT 0
struct k_msgq
{
    unsigned char *data;
    std::size_t item_size;
    std::size_t capacity;
    std::size_t read{0};
    std::size_t write{0};
    std::size_t count{0};
    std::mutex mutex{};
};
#define K_MSGQ_DEFINE(name, size, count, alignment)                                                \
    static unsigned char name##_storage[(size) * (count)]{};                                       \
    static k_msgq name                                                                             \
    {                                                                                              \
        name##_storage, size, count                                                                \
    }
inline int k_msgq_put(k_msgq *queue, const void *data, int)
{
    std::lock_guard<std::mutex> lock(queue->mutex);
    if (queue->count == queue->capacity)
    {
        return -ENOMSG;
    }
    std::memcpy(queue->data + queue->write * queue->item_size, data, queue->item_size);
    queue->write = (queue->write + 1) % queue->capacity;
    ++queue->count;
    return 0;
}
inline int k_msgq_get(k_msgq *queue, void *data, int)
{
    std::lock_guard<std::mutex> lock(queue->mutex);
    if (queue->count == 0)
    {
        return -ENOMSG;
    }
    std::memcpy(data, queue->data + queue->read * queue->item_size, queue->item_size);
    queue->read = (queue->read + 1) % queue->capacity;
    --queue->count;
    return 0;
}
inline void k_msgq_purge(k_msgq *queue)
{
    std::lock_guard<std::mutex> lock(queue->mutex);
    queue->count = queue->read = queue->write = 0;
}
inline std::size_t k_msgq_num_used_get(k_msgq *queue)
{
    std::lock_guard<std::mutex> lock(queue->mutex);
    return queue->count;
}
inline std::int64_t k_uptime_get()
{
    return static_cast<std::int64_t>(waited_us.load() / 1000);
}
