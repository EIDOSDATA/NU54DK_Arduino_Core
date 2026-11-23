#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <deque>
#include <vector>

using atomic_val_t = long;

struct atomic_t
{
    atomic_val_t value;
};

struct atomic_ptr_t
{
    void *value;
};

inline atomic_val_t atomic_set(atomic_t *target, atomic_val_t value)
{
    const atomic_val_t previous = target->value;
    target->value = value;
    return previous;
}

inline atomic_val_t atomic_get(const atomic_t *target)
{
    return target->value;
}

inline void atomic_clear(atomic_t *target)
{
    target->value = 0;
}

inline bool atomic_cas(atomic_t *target, atomic_val_t old_value, atomic_val_t new_value)
{
    if (target->value != old_value)
    {
        return false;
    }
    target->value = new_value;
    return true;
}

inline void atomic_set_bit(atomic_t *target, unsigned bit)
{
    target->value |= static_cast<atomic_val_t>(1UL << bit);
}

inline void *atomic_ptr_get(const atomic_ptr_t *target)
{
    return target->value;
}

inline void atomic_ptr_set(atomic_ptr_t *target, void *value)
{
    target->value = value;
}

struct k_msgq
{
    explicit k_msgq(std::size_t size) : message_size(size)
    {
    }

    std::size_t message_size;
    std::deque<std::vector<std::uint8_t>> entries;
};

#define K_MSGQ_DEFINE(name, size, count, alignment) k_msgq name(size)
#define K_NO_WAIT 0

inline int k_msgq_put(k_msgq *queue, const void *message, int)
{
    const auto *bytes = static_cast<const std::uint8_t *>(message);
    queue->entries.emplace_back(bytes, bytes + queue->message_size);
    return 0;
}

inline int k_msgq_get(k_msgq *queue, void *message, int)
{
    if (queue->entries.empty())
    {
        return -1;
    }
    std::memcpy(message, queue->entries.front().data(), queue->message_size);
    queue->entries.pop_front();
    return 0;
}

inline void k_msgq_purge(k_msgq *queue)
{
    queue->entries.clear();
}

inline std::int64_t companion_stub_uptime;

inline std::int64_t k_uptime_get()
{
    return companion_stub_uptime;
}

struct bt_conn
{
    int marker;
};

using bt_security_t = std::uint8_t;

enum bt_security_err
{
    BT_SECURITY_ERR_SUCCESS,
    BT_SECURITY_ERR_AUTH_FAIL,
    BT_SECURITY_ERR_PIN_OR_KEY_MISSING,
    BT_SECURITY_ERR_OOB_NOT_AVAILABLE,
    BT_SECURITY_ERR_AUTH_REQUIREMENT,
    BT_SECURITY_ERR_PAIR_NOT_SUPPORTED,
    BT_SECURITY_ERR_PAIR_NOT_ALLOWED,
    BT_SECURITY_ERR_INVALID_PARAM,
    BT_SECURITY_ERR_KEY_REJECTED,
    BT_SECURITY_ERR_UNSPECIFIED,
};

constexpr bt_security_t BT_SECURITY_L1 = 1U;
constexpr bt_security_t BT_SECURITY_L2 = 2U;
constexpr std::uint8_t BT_HCI_ERR_REMOTE_USER_TERM_CONN = 0x13U;

struct bt_conn_cb
{
    void (*connected)(bt_conn *, std::uint8_t) = nullptr;
    void (*disconnected)(bt_conn *, std::uint8_t) = nullptr;
    void (*security_changed)(bt_conn *, bt_security_t, bt_security_err) = nullptr;
};

#define BT_CONN_CB_DEFINE(name) bt_conn_cb name

inline int companion_stub_security_result;
inline bt_security_t companion_stub_security_level = BT_SECURITY_L1;
inline unsigned companion_stub_disconnects;
inline unsigned companion_stub_unref_count;

inline int bt_conn_set_security(bt_conn *, bt_security_t)
{
    return companion_stub_security_result;
}

inline bt_security_t bt_conn_get_security(const bt_conn *)
{
    return companion_stub_security_level;
}

inline int bt_conn_disconnect(bt_conn *, std::uint8_t)
{
    ++companion_stub_disconnects;
    return 0;
}

inline void bt_conn_unref(bt_conn *)
{
    ++companion_stub_unref_count;
}

struct bt_uuid
{
    std::uint8_t type;
};

struct bt_uuid_128
{
    bt_uuid uuid;
    std::uint8_t val[16];
};

#define BT_UUID_128_ENCODE(a, b, c, d, e)                                                          \
    0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U
#define BT_UUID_INIT_128(...)                                                                      \
    {                                                                                              \
        {0U},                                                                                      \
        {                                                                                          \
            __VA_ARGS__                                                                            \
        }                                                                                          \
    }

inline const bt_uuid companion_stub_ccc_uuid{};
#define BT_UUID_GATT_CCC (&companion_stub_ccc_uuid)

constexpr std::uint8_t BT_GATT_CHRC_READ = 1U << 1U;
constexpr std::uint8_t BT_GATT_CHRC_WRITE = 1U << 3U;
constexpr std::uint8_t BT_GATT_CHRC_NOTIFY = 1U << 4U;
constexpr std::uint16_t BT_GATT_CCC_NOTIFY = 1U;
constexpr unsigned BT_GATT_SUBSCRIBE_FLAG_VOLATILE = 0U;
constexpr std::uint8_t BT_GATT_ITER_STOP = 0U;
constexpr std::uint8_t BT_GATT_ITER_CONTINUE = 1U;

struct bt_gatt_subscribe_params
{
    std::uint8_t (*notify)(bt_conn *, bt_gatt_subscribe_params *, const void *, std::uint16_t);
    void (*subscribe)(bt_conn *, std::uint8_t, bt_gatt_subscribe_params *);
    std::uint16_t value_handle;
    std::uint16_t ccc_handle;
    std::uint16_t value;
    atomic_t flags[1];
};

struct bt_gatt_write_params
{
    void (*func)(bt_conn *, std::uint8_t, bt_gatt_write_params *);
    std::uint16_t handle;
    const void *data;
    std::uint16_t length;
};

struct bt_gatt_read_params
{
    std::uint8_t (*func)(bt_conn *, std::uint8_t, bt_gatt_read_params *, const void *,
                         std::uint16_t);
    std::uint8_t handle_count;
    struct
    {
        std::uint16_t handle;
    } single;
};

inline int bt_gatt_subscribe(bt_conn *, bt_gatt_subscribe_params *)
{
    return 0;
}

inline int bt_gatt_write(bt_conn *, bt_gatt_write_params *)
{
    return 0;
}

inline int bt_gatt_read(bt_conn *, bt_gatt_read_params *)
{
    return 0;
}

struct bt_gatt_dm
{
};

struct bt_gatt_dm_attr
{
    std::uint16_t handle;
};

struct bt_gatt_chrc
{
    std::uint8_t properties;
};

struct bt_gatt_dm_cb
{
    void (*completed)(bt_gatt_dm *, void *);
    void (*service_not_found)(bt_conn *, void *);
    void (*error_found)(bt_conn *, int, void *);
};

inline const bt_gatt_dm_attr *bt_gatt_dm_char_by_uuid(bt_gatt_dm *, const bt_uuid *)
{
    return nullptr;
}

inline const bt_gatt_chrc *bt_gatt_dm_attr_chrc_val(const bt_gatt_dm_attr *)
{
    return nullptr;
}

inline const bt_gatt_dm_attr *bt_gatt_dm_desc_by_uuid(bt_gatt_dm *, const bt_gatt_dm_attr *,
                                                      const bt_uuid *)
{
    return nullptr;
}

inline bt_conn *bt_gatt_dm_conn_get(bt_gatt_dm *)
{
    return nullptr;
}

inline int bt_gatt_dm_data_release(bt_gatt_dm *)
{
    return 0;
}

inline int bt_gatt_dm_start(bt_conn *, const bt_uuid *, const bt_gatt_dm_cb *, void *)
{
    return 0;
}

struct bt_data
{
    std::uint8_t type;
    std::uint8_t data_len;
    const std::uint8_t *data;
};

constexpr std::uint8_t BT_LE_AD_GENERAL = 1U << 1U;
constexpr std::uint8_t BT_LE_AD_NO_BREDR = 1U << 2U;
constexpr std::uint8_t BT_DATA_FLAGS = 1U;
constexpr std::uint8_t BT_DATA_SOLICIT128 = 2U;
constexpr std::uint8_t BT_DATA_NAME_COMPLETE = 3U;
inline const void *BT_LE_ADV_CONN_FAST_2 = nullptr;

inline int bt_le_adv_start(const void *, const bt_data *, std::size_t, const bt_data *, std::size_t)
{
    return 0;
}

inline int bt_le_adv_stop()
{
    return 0;
}

namespace nucode::ble
{
    inline bool companion_stub_advertising_running;

    struct BLEConnectionHandle
    {
        int value = 0;
    };

    class StubAdvertising
    {
      public:
        bool running() const noexcept
        {
            return companion_stub_advertising_running;
        }
    };

    class StubDevice
    {
      public:
        bool initialized_value = false;
        unsigned begin_calls = 0U;

        bool begin(const char *) noexcept
        {
            ++begin_calls;
            initialized_value = true;
            return true;
        }

        bool initialized() const noexcept
        {
            return initialized_value;
        }
    };

    inline StubAdvertising BLEAdvertising;
    inline StubDevice BLEDevice;
    inline bt_conn *companion_stub_connection;

    namespace internal
    {
        inline bt_conn *referenceConnection(BLEConnectionHandle connection) noexcept
        {
            return connection.value == 0 ? nullptr : companion_stub_connection;
        }
    } // namespace internal
} // namespace nucode::ble
