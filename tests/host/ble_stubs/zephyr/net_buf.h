/** @file @brief BLE Host driver 경계를 공유합니다. */
#pragma once
#include <ble_mock.h>

#include <array>

/** @brief Host 시험에서 고정 pool ownership을 재현하는 최소 net_buf입니다. */
struct net_buf_pool;

struct net_buf
{
    static constexpr std::size_t storage_size = 1024U;
    std::array<std::uint8_t, storage_size> storage{};
    std::uint8_t *data{storage.data()};
    std::size_t len{0U};
    std::size_t capacity{storage_size};
    net_buf_pool *pool{};
    bool in_use{false};
};

struct net_buf_pool
{
    net_buf *buffers;
    std::size_t count;
    std::size_t requested_size;
};

#define NET_BUF_POOL_FIXED_DEFINE(name, count_value, size_value, user_data_size, destroy)          \
    static_assert((size_value) <= net_buf::storage_size);                                           \
    static net_buf name##_buffers[(count_value)]{};                                                 \
    static net_buf_pool name                                                                      \
    {                                                                                              \
        name##_buffers, (count_value), (size_value)                                                 \
    }

inline net_buf *net_buf_alloc(net_buf_pool *pool, int)
{
    for (std::size_t index = 0U; index < pool->count; ++index)
    {
        net_buf &buffer = pool->buffers[index];
        if (!buffer.in_use)
        {
            buffer.in_use = true;
            buffer.data = buffer.storage.data();
            buffer.len = 0U;
            buffer.capacity = buffer.storage.size();
            buffer.pool = pool;
            return &buffer;
        }
    }
    return nullptr;
}

inline void net_buf_reserve(net_buf *buffer, std::size_t reserve)
{
    assert(buffer != nullptr && reserve <= buffer->storage.size());
    buffer->data = buffer->storage.data() + reserve;
    buffer->capacity = buffer->storage.size() - reserve;
}

inline void *net_buf_add_mem(net_buf *buffer, const void *data, std::size_t length)
{
    assert(buffer != nullptr && buffer->len + length <= buffer->capacity);
    std::memcpy(buffer->data + buffer->len, data, length);
    buffer->len += length;
    return buffer->data + buffer->len - length;
}

inline void net_buf_unref(net_buf *buffer)
{
    assert(buffer != nullptr && buffer->in_use);
    buffer->in_use = false;
    buffer->data = buffer->storage.data();
    buffer->len = 0U;
    buffer->capacity = buffer->storage.size();
}
