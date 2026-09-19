/**
 * @file pbp_runtime_stubs.h
 * @brief 실제 PBP backend를 Host에서 실행하기 위한 고정 Zephyr API stub입니다.
 *
 * SPDX-License-Identifier: MIT
 */
#pragma once

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <deque>
#include <errno.h>
#include <mutex>
#include <thread>
#include <vector>

#define CONFIG_BT_BAP_BROADCAST_SINK 1
#define CONFIG_BT_BAP_BROADCAST_SOURCE 1
#define CONFIG_BT_CAP_INITIATOR 1
#define CONFIG_BT_PBP 1
#define CONFIG_BT_ISO_TX_MTU 64
#define CONFIG_BT_CONN_TX_USER_DATA_SIZE 0

#define ARRAY_SIZE(value) (sizeof(value) / sizeof((value)[0]))
#define CLAMP(value, low, high) \
    ((value) < (low) ? (low) : ((value) > (high) ? (high) : (value)))
#define K_FOREVER (-1)
#define K_NO_WAIT 0
#define K_SECONDS(value) (value)

using atomic_t = long;
using atomic_val_t = long;
using atomic_ptr_t = void *;

namespace pbp_stub
{
    inline std::mutex atomic_mutex;
    inline std::condition_variable atomic_changed;
    inline const atomic_t *blocked_atomic = nullptr;
    inline bool atomic_entered = false;
    inline bool release_atomic = false;
}

inline atomic_val_t atomic_get(const atomic_t *target)
{
    if (target == pbp_stub::blocked_atomic)
    {
        std::unique_lock<std::mutex> lock(pbp_stub::atomic_mutex);
        pbp_stub::atomic_entered = true;
        pbp_stub::atomic_changed.notify_all();
        pbp_stub::atomic_changed.wait(lock, []()
        {
            return pbp_stub::release_atomic;
        });
    }
    return __atomic_load_n(target, __ATOMIC_SEQ_CST);
}

inline void atomic_set(atomic_t *target, atomic_val_t value)
{
    __atomic_store_n(target, value, __ATOMIC_SEQ_CST);
}

inline atomic_val_t atomic_inc(atomic_t *target)
{
    return __atomic_fetch_add(target, 1, __ATOMIC_SEQ_CST);
}

inline atomic_val_t atomic_dec(atomic_t *target)
{
    return __atomic_fetch_sub(target, 1, __ATOMIC_SEQ_CST);
}

inline bool atomic_cas(atomic_t *target, atomic_val_t old_value,
                       atomic_val_t new_value)
{
    return __atomic_compare_exchange_n(target, &old_value, new_value, false,
                                       __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}

inline void *atomic_ptr_get(const atomic_ptr_t *target)
{
    return __atomic_load_n(target, __ATOMIC_SEQ_CST);
}

inline void atomic_ptr_set(atomic_ptr_t *target, void *value)
{
    __atomic_store_n(target, value, __ATOMIC_SEQ_CST);
}

inline void atomic_ptr_clear(atomic_ptr_t *target)
{
    atomic_ptr_set(target, nullptr);
}

inline bool atomic_ptr_cas(atomic_ptr_t *target, void *old_value, void *new_value)
{
    return __atomic_compare_exchange_n(target, &old_value, new_value, false,
                                       __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}

struct k_sem
{
    std::mutex mutex;
    std::condition_variable changed;
    unsigned int count = 0U;
    unsigned int limit = 1U;
};

inline void k_sem_reset(k_sem *semaphore)
{
    const std::lock_guard<std::mutex> lock(semaphore->mutex);
    semaphore->count = 0U;
}

inline void k_sem_give(k_sem *semaphore)
{
    {
        const std::lock_guard<std::mutex> lock(semaphore->mutex);
        semaphore->count = std::min(semaphore->count + 1U, semaphore->limit);
    }
    semaphore->changed.notify_all();
}

inline int k_sem_take(k_sem *semaphore, int timeout_seconds)
{
    std::unique_lock<std::mutex> lock(semaphore->mutex);
    const auto ready = [&]()
    {
        return semaphore->count != 0U;
    };
    if (timeout_seconds == K_NO_WAIT)
    {
        if (!ready())
        {
            return -11;
        }
    }
    else if (timeout_seconds == K_FOREVER)
    {
        semaphore->changed.wait(lock, ready);
    }
    else if (!semaphore->changed.wait_for(lock, std::chrono::seconds(timeout_seconds), ready))
    {
        return -11;
    }
    semaphore->count--;
    return 0;
}

#define K_SEM_DEFINE(name, initial, maximum) \
    k_sem name = {std::mutex(), std::condition_variable(), initial, maximum}

using k_mutex = std::recursive_mutex;
#define K_MUTEX_DEFINE(name) k_mutex name

inline int k_mutex_lock(k_mutex *mutex, int)
{
    mutex->lock();
    return 0;
}

inline int k_mutex_unlock(k_mutex *mutex)
{
    mutex->unlock();
    return 0;
}

inline std::int32_t k_msleep(std::int32_t milliseconds)
{
    std::this_thread::sleep_for(std::chrono::milliseconds(milliseconds));
    return 0;
}

inline std::uint32_t k_uptime_get_32()
{
    static const auto started = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - started);
    return static_cast<std::uint32_t>(elapsed.count());
}

struct k_msgq
{
    std::mutex mutex;
    std::size_t element_size = 0U;
    std::size_t capacity = 0U;
    std::deque<std::vector<std::uint8_t>> elements;
};

#define K_MSGQ_DEFINE(name, element_size_value, capacity_value, alignment) \
    k_msgq name = {std::mutex(), element_size_value, capacity_value, {}}

inline int k_msgq_put(k_msgq *queue, const void *data, int)
{
    const std::lock_guard<std::mutex> lock(queue->mutex);
    if (queue->elements.size() == queue->capacity)
    {
        return -11;
    }
    const auto *bytes = static_cast<const std::uint8_t *>(data);
    queue->elements.emplace_back(bytes, bytes + queue->element_size);
    return 0;
}

inline int k_msgq_get(k_msgq *queue, void *data, int)
{
    const std::lock_guard<std::mutex> lock(queue->mutex);
    if (queue->elements.empty())
    {
        return -11;
    }
    memcpy(data, queue->elements.front().data(), queue->element_size);
    queue->elements.pop_front();
    return 0;
}

inline void k_msgq_purge(k_msgq *queue)
{
    const std::lock_guard<std::mutex> lock(queue->mutex);
    queue->elements.clear();
}

struct net_buf
{
    std::size_t len = 0U;
    std::uint8_t storage[128] = {};
    std::uint8_t *data = storage;
};

struct net_buf_simple
{
    std::size_t len = 0U;
    std::size_t size = 0U;
    std::uint8_t *data = nullptr;
};

#define NET_BUF_SIMPLE_DEFINE(name, capacity) \
    std::uint8_t name##_storage[capacity] = {}; \
    net_buf_simple name = {0U, capacity, name##_storage}
#define NET_BUF_POOL_FIXED_DEFINE(name, count, size, user_size, destroy) int name = 0
#define BT_ISO_SDU_BUF_SIZE(value) (value)

inline void net_buf_simple_add_le16(net_buf_simple *buffer, std::uint16_t value)
{
    buffer->data[buffer->len++] = static_cast<std::uint8_t>(value);
    buffer->data[buffer->len++] = static_cast<std::uint8_t>(value >> 8U);
}

inline void net_buf_simple_add_le24(net_buf_simple *buffer, std::uint32_t value)
{
    for (unsigned int index = 0U; index < 3U; index++)
    {
        buffer->data[buffer->len++] = static_cast<std::uint8_t>(value >> (index * 8U));
    }
}

inline void net_buf_simple_clone(const net_buf_simple *source, net_buf_simple *target)
{
    *target = *source;
}

inline net_buf *net_buf_alloc(int *, int)
{
    return new net_buf();
}

inline void net_buf_reserve(net_buf *, std::size_t)
{
}

inline void net_buf_add_mem(net_buf *buffer, const void *data, std::size_t length)
{
    memcpy(buffer->data + buffer->len, data, length);
    buffer->len += length;
}

inline void net_buf_unref(net_buf *buffer)
{
    delete buffer;
}

struct bt_addr_le_t
{
    std::uint8_t type = 0U;
    std::uint8_t address[6] = {};
};

inline int bt_addr_le_cmp(const bt_addr_le_t *left, const bt_addr_le_t *right)
{
    return memcmp(left, right, sizeof(*left));
}

struct bt_conn
{
};

struct bt_data
{
    std::uint8_t type = 0U;
    std::uint8_t data_len = 0U;
    const std::uint8_t *data = nullptr;
};

using bt_data_func_t = bool (*)(bt_data *, void *);

inline void bt_data_parse(net_buf_simple *, bt_data_func_t, void *)
{
}

using bt_audio_location = std::uint32_t;
using bt_audio_context = std::uint16_t;
using bt_audio_codec_cfg_type = std::uint8_t;

struct bt_audio_codec_cfg
{
    std::uint8_t id = 0U;
    int frequency = 0;
    int duration = 0;
    int octets = 0;
    int blocks = 0;
    bt_audio_location location = 0U;
};

struct bt_audio_codec_cap
{
};

constexpr std::uint8_t BT_HCI_CODING_FORMAT_LC3 = 0x06U;
constexpr int BT_AUDIO_CODEC_CFG_FREQ_16KHZ = 3;
constexpr int BT_AUDIO_CODEC_CFG_DURATION_10 = 1;
constexpr bt_audio_location BT_AUDIO_LOCATION_FRONT_LEFT = 1U;
constexpr bt_audio_location BT_AUDIO_LOCATION_MONO_AUDIO = 1U;
constexpr bt_audio_context BT_AUDIO_CONTEXT_TYPE_MEDIA = 4U;
constexpr std::uint8_t BT_AUDIO_METADATA_TYPE_PROGRAM_INFO = 3U;
constexpr std::uint8_t BT_AUDIO_METADATA_TYPE_STREAM_CONTEXT = 2U;

#define BT_AUDIO_CODEC_CAP_FREQ_16KHZ 1
#define BT_AUDIO_CODEC_CAP_DURATION_10 1
#define BT_AUDIO_CODEC_CAP_CHAN_COUNT_SUPPORT(value) (value)
#define BT_AUDIO_CODEC_CAP_LC3(...) bt_audio_codec_cap{}
#define BT_AUDIO_CODEC_LC3_CONFIG(freq, duration, location, octets, blocks, context) \
    bt_audio_codec_cfg{BT_HCI_CODING_FORMAT_LC3, freq, duration, octets, blocks, location}

inline int bt_audio_codec_cfg_get_freq(const bt_audio_codec_cfg *codec)
{
    return codec->frequency;
}

inline int bt_audio_codec_cfg_get_frame_dur(const bt_audio_codec_cfg *codec)
{
    return codec->duration;
}

inline int bt_audio_codec_cfg_get_octets_per_frame(const bt_audio_codec_cfg *codec)
{
    return codec->octets;
}

inline int bt_audio_codec_cfg_get_frame_blocks_per_sdu(const bt_audio_codec_cfg *codec, bool)
{
    return codec->blocks;
}

inline int bt_audio_codec_cfg_get_chan_allocation(const bt_audio_codec_cfg *codec,
                                                   bt_audio_location *location, bool)
{
    *location = codec->location;
    return 0;
}

inline std::uint8_t bt_audio_get_chan_count(bt_audio_location location)
{
    return static_cast<std::uint8_t>(__builtin_popcount(location));
}

inline int bt_audio_codec_cfg_set_val(bt_audio_codec_cfg *codec,
                                      bt_audio_codec_cfg_type type,
                                      const std::uint8_t *data, std::size_t length)
{
    if ((data == nullptr) || (length != 1U))
    {
        return -EBADMSG;
    }
    switch (type)
    {
        case 1U:
            codec->frequency = data[0];
            break;
        case 2U:
            codec->duration = data[0];
            break;
        case 3U:
            codec->octets = data[0];
            break;
        case 4U:
            codec->blocks = data[0];
            break;
        case 5U:
            codec->location = data[0];
            break;
        default:
            return -ENOTSUP;
    }
    return 0;
}

inline int bt_audio_data_parse(const std::uint8_t *bytes, std::size_t length,
                               bt_data_func_t callback, void *user_data)
{
    std::size_t offset = 0U;
    while (offset < length)
    {
        const std::size_t field_length = bytes[offset];
        if ((field_length < 2U) || ((offset + field_length + 1U) > length))
        {
            return -EBADMSG;
        }
        bt_data field = {
            .type = bytes[offset + 1U],
            .data_len = static_cast<std::uint8_t>(field_length - 1U),
            .data = &bytes[offset + 2U],
        };
        if (!callback(&field, user_data))
        {
            return 0;
        }
        offset += field_length + 1U;
    }
    return 0;
}

struct bt_bap_base_subgroup_bis
{
    std::uint8_t index = 0U;
    const std::uint8_t *data = nullptr;
    std::size_t data_len = 0U;
};

struct bt_bap_base_subgroup
{
    bt_audio_codec_cfg codec = {};
    std::vector<bt_bap_base_subgroup_bis> bis;
};

struct bt_bap_base
{
    int encoded_size = 1;
    std::vector<bt_bap_base_subgroup> subgroups;
};

namespace pbp_stub
{
    inline std::mutex base_mutex;
    inline std::condition_variable base_changed;
    inline bool block_base = false;
    inline bool base_entered = false;
    inline bool release_base = false;
}

inline int bt_bap_base_get_size(const bt_bap_base *base)
{
    return base->encoded_size;
}

inline int bt_bap_base_subgroup_codec_to_codec_cfg(const bt_bap_base_subgroup *subgroup,
                                                    bt_audio_codec_cfg *codec)
{
    *codec = subgroup->codec;
    return 0;
}

inline int bt_bap_base_subgroup_foreach_bis(
    const bt_bap_base_subgroup *subgroup,
    bool (*callback)(const bt_bap_base_subgroup_bis *, void *), void *user_data)
{
    for (const auto &bis : subgroup->bis)
    {
        if (!callback(&bis, user_data))
        {
            break;
        }
    }
    return 0;
}

inline int bt_bap_base_foreach_subgroup(
    const bt_bap_base *base,
    bool (*callback)(const bt_bap_base_subgroup *, void *), void *user_data)
{
    if (pbp_stub::block_base)
    {
        std::unique_lock<std::mutex> lock(pbp_stub::base_mutex);
        pbp_stub::base_entered = true;
        pbp_stub::base_changed.notify_all();
        pbp_stub::base_changed.wait(lock, []()
        {
            return pbp_stub::release_base;
        });
    }
    for (const auto &subgroup : base->subgroups)
    {
        if (!callback(&subgroup, user_data))
        {
            break;
        }
    }
    return 0;
}

struct bt_bap_stream;
struct bt_iso_recv_info;

struct bt_bap_stream_ops
{
    void (*started)(bt_bap_stream *) = nullptr;
    void (*stopped)(bt_bap_stream *, std::uint8_t) = nullptr;
    void (*recv)(bt_bap_stream *, const bt_iso_recv_info *, net_buf *) = nullptr;
};

struct bt_bap_stream
{
    const bt_bap_stream_ops *callbacks = nullptr;
};

inline void bt_bap_stream_cb_register(bt_bap_stream *stream,
                                      const bt_bap_stream_ops *callbacks)
{
    stream->callbacks = callbacks;
}

struct bt_bap_broadcast_sink
{
    int id = 0;
};

struct bt_iso_biginfo
{
    bool encryption = false;
};

struct bt_iso_recv_info
{
    std::uint8_t flags = 0U;
};

struct bt_bap_broadcast_sink_cb
{
    void (*base_recv)(bt_bap_broadcast_sink *, const bt_bap_base *, std::size_t) = nullptr;
    void (*syncable)(bt_bap_broadcast_sink *, const bt_iso_biginfo *) = nullptr;
    void (*started)(bt_bap_broadcast_sink *) = nullptr;
    void (*stopped)(bt_bap_broadcast_sink *, std::uint8_t) = nullptr;
};

struct bt_le_per_adv_sync
{
    int id = 0;
};

struct bt_le_per_adv_sync_synced_info
{
    const bt_addr_le_t *addr = nullptr;
    std::uint8_t sid = 0U;
};

struct bt_le_per_adv_sync_term_info
{
    const bt_addr_le_t *addr = nullptr;
    std::uint8_t sid = 0U;
    std::uint8_t reason = 0U;
};

struct bt_le_per_adv_sync_cb
{
    void (*synced)(bt_le_per_adv_sync *, bt_le_per_adv_sync_synced_info *) = nullptr;
    void (*term)(bt_le_per_adv_sync *, const bt_le_per_adv_sync_term_info *) = nullptr;
};

namespace pbp_stub
{
    /** @brief PA 취소와 explicit scan 종료의 호출 순서를 기록합니다. */
    enum class CleanupEvent : std::uint8_t
    {
        periodic_delete,
        periodic_released,
        scan_stop,
    };

    enum class PeriodicDeleteMode : std::uint8_t
    {
        pending,
        pending_stalled,
        synchronous,
        late,
    };

    enum class PeriodicCreateMode : std::uint8_t
    {
        normal,
        synced_before_return,
        terminated_before_return,
    };

    inline std::deque<int> scan_stop_results;
    inline std::deque<int> periodic_delete_results;
    inline int scan_stop_default_result = 0;
    inline int periodic_delete_default_result = 0;
    inline unsigned int scan_stop_calls = 0U;
    inline unsigned int periodic_delete_calls = 0U;
    inline unsigned int periodic_lookup_calls = 0U;
    inline unsigned int foreign_periodic_delete_calls = 0U;
    inline unsigned int periodic_callback_register_calls = 0U;
    inline unsigned int periodic_callback_unregister_calls = 0U;
    inline std::atomic<bool> periodic_present{false};
    inline std::atomic<unsigned int> periodic_cancel_polls{0U};
    inline bool reuse_after_transient_delete = false;
    inline bool reuse_same_identity_before_term = false;
    inline bool reuse_same_identity_during_lookup = false;
    inline bool foreign_periodic = false;
    inline PeriodicCreateMode periodic_create_mode = PeriodicCreateMode::normal;
    inline PeriodicDeleteMode periodic_delete_mode = PeriodicDeleteMode::pending;
    inline bt_le_per_adv_sync *periodic_instance = nullptr;
    inline bt_le_per_adv_sync_cb *periodic_callbacks = nullptr;
    inline bt_addr_le_t periodic_address = {};
    inline std::uint8_t periodic_sid = 0U;
    inline std::vector<CleanupEvent> cleanup_events;

    /** @brief scan·PA cleanup stub 상태를 다음 시나리오 전에 초기화합니다. */
    inline void resetCleanupState()
    {
        scan_stop_results.clear();
        periodic_delete_results.clear();
        scan_stop_default_result = 0;
        periodic_delete_default_result = 0;
        scan_stop_calls = 0U;
        periodic_delete_calls = 0U;
        periodic_lookup_calls = 0U;
        foreign_periodic_delete_calls = 0U;
        periodic_present.store(false);
        periodic_cancel_polls.store(0U);
        reuse_after_transient_delete = false;
        reuse_same_identity_before_term = false;
        reuse_same_identity_during_lookup = false;
        foreign_periodic = false;
        periodic_create_mode = PeriodicCreateMode::normal;
        periodic_delete_mode = PeriodicDeleteMode::pending;
        periodic_instance = nullptr;
        cleanup_events.clear();
    }

    /** @brief 취소된 slot을 다른 주소·SID의 외부 PA sync로 재사용합니다. */
    inline void reusePeriodicSlot(const bt_addr_le_t &address, std::uint8_t sid)
    {
        periodic_cancel_polls.store(0U);
        periodic_address = address;
        periodic_sid = sid;
        foreign_periodic = true;
        periodic_present.store(true);
    }
}

struct bt_le_scan_recv_info
{
    const bt_addr_le_t *addr = nullptr;
    std::uint16_t interval = 0U;
    std::uint16_t adv_props = 0U;
    std::uint8_t sid = 0U;
};

struct bt_le_scan_cb
{
    void (*recv)(const bt_le_scan_recv_info *, net_buf_simple *) = nullptr;
};

struct bt_le_per_adv_sync_param
{
    bt_addr_le_t addr = {};
    std::uint8_t sid = 0U;
    std::uint8_t options = 0U;
    std::uint16_t skip = 0U;
    std::uint16_t timeout = 0U;
};

struct bt_bap_scan_delegator_recv_state
{
    bt_addr_le_t addr = {};
    std::uint32_t broadcast_id = 0U;
    std::uint8_t src_id = 0U;
    std::uint8_t adv_sid = 0U;
    std::uint8_t num_subgroups = 0U;
};

struct bt_bap_scan_delegator_cb
{
    void *recv_state_updated = nullptr;
    int (*pa_sync_req)(bt_conn *, const bt_bap_scan_delegator_recv_state *, bool,
                       std::uint16_t) = nullptr;
    int (*pa_sync_term_req)(bt_conn *, const bt_bap_scan_delegator_recv_state *) = nullptr;
    void (*broadcast_code)(bt_conn *, const bt_bap_scan_delegator_recv_state *,
                           const std::uint8_t *) = nullptr;
    int (*bis_sync_req)(bt_conn *, const bt_bap_scan_delegator_recv_state *,
                        const std::uint32_t *) = nullptr;
    void *scanning_state = nullptr;
    int (*add_source)(bt_conn *, const bt_bap_scan_delegator_recv_state *) = nullptr;
    int (*modify_source)(bt_conn *, const bt_bap_scan_delegator_recv_state *) = nullptr;
    int (*remove_source)(bt_conn *, std::uint8_t) = nullptr;
};

struct bt_pacs_register_param
{
    bool snk_pac = false;
    bool snk_loc = false;
};

struct bt_pacs_cap
{
    const bt_audio_codec_cap *codec_cap = nullptr;
};

using bt_pbp_announcement_feature = std::uint8_t;

constexpr std::uint8_t BT_PBP_ANNOUNCEMENT_FEATURE_STANDARD_QUALITY = 0x01U;
constexpr std::uint8_t BT_PBP_ANNOUNCEMENT_FEATURE_HIGH_QUALITY = 0x02U;
constexpr std::uint8_t BT_PBP_ANNOUNCEMENT_FEATURE_ENCRYPTION = 0x04U;
constexpr std::uint8_t BT_DATA_SVC_DATA16 = 0x16U;
constexpr std::uint8_t BT_DATA_BROADCAST_NAME = 0x30U;
constexpr std::uint8_t BT_DATA_GAP_APPEARANCE = 0x19U;
constexpr std::uint16_t BT_UUID_BROADCAST_AUDIO_VAL = 0x1852U;
constexpr std::uint16_t BT_UUID_PBA_VAL = 0x1856U;
constexpr std::size_t BT_UUID_SIZE_16 = 2U;
constexpr std::size_t BT_AUDIO_BROADCAST_ID_SIZE = 3U;
constexpr std::size_t BT_AUDIO_BROADCAST_NAME_LEN_MIN = 4U;
constexpr std::size_t BT_AUDIO_BROADCAST_NAME_LEN_MAX = 128U;
constexpr std::size_t BT_ISO_BROADCAST_CODE_SIZE = 16U;
constexpr std::uint8_t BT_ISO_BIS_INDEX_MAX = 31U;
constexpr std::uint8_t BT_ISO_FLAGS_VALID = 1U;
constexpr std::uint8_t BT_HCI_ERR_LOCALHOST_TERM_CONN = 0x16U;
constexpr std::uint8_t BT_GAP_ADV_PROP_CONNECTABLE = 0x01U;
constexpr std::uint16_t BT_GAP_PER_ADV_MIN_TIMEOUT = 10U;
constexpr std::uint16_t BT_GAP_PER_ADV_MAX_TIMEOUT = 16384U;
constexpr std::uint32_t BT_BAP_BIS_SYNC_NO_PREF = 0xffffffffU;
constexpr std::size_t BT_BAP_BASS_MAX_SUBGROUPS = 1U;
constexpr std::uint8_t BT_BAP_PA_STATE_NOT_SYNCED = 0U;
constexpr int BT_AUDIO_DIR_SINK = 0;
constexpr int BT_LE_SCAN_ACTIVE = 0;
constexpr int BT_LE_PER_ADV_SYNC_OPT_NONE = 0;

#define BT_ISO_BIS_INDEX_BIT(index) (std::uint32_t{1U} << ((index) - 1U))

inline std::uint16_t sys_get_le16(const std::uint8_t *data)
{
    return static_cast<std::uint16_t>(data[0] | (data[1] << 8U));
}

inline std::uint32_t sys_get_le24(const std::uint8_t *data)
{
    return static_cast<std::uint32_t>(data[0] | (data[1] << 8U) | (data[2] << 16U));
}

inline int utf8_count_chars(const char *text)
{
    return static_cast<int>(strlen(text));
}

inline int bt_pbp_parse_announcement(bt_data *, bt_pbp_announcement_feature *,
                                     std::uint8_t **)
{
    return -ENOTSUP;
}

inline int bt_pbp_get_announcement(const std::uint8_t *, std::size_t,
                                   bt_pbp_announcement_feature, net_buf_simple *)
{
    return 0;
}

inline int bt_bap_broadcast_sink_register_cb(bt_bap_broadcast_sink_cb *)
{
    return 0;
}

inline int bt_bap_broadcast_sink_create(bt_le_per_adv_sync *, std::uint32_t,
                                        bt_bap_broadcast_sink **sink)
{
    static bt_bap_broadcast_sink instance;
    *sink = &instance;
    return 0;
}

inline int bt_bap_broadcast_sink_sync(bt_bap_broadcast_sink *, std::uint32_t,
                                      bt_bap_stream **, const std::uint8_t *)
{
    return 0;
}

inline int bt_bap_broadcast_sink_stop(bt_bap_broadcast_sink *)
{
    return -EALREADY;
}

inline int bt_bap_broadcast_sink_delete(bt_bap_broadcast_sink *)
{
    return 0;
}

inline int bt_bap_scan_delegator_register(bt_bap_scan_delegator_cb *)
{
    return 0;
}

inline int bt_bap_scan_delegator_unregister()
{
    return 0;
}

inline int bt_bap_scan_delegator_set_pa_state(std::uint8_t, std::uint8_t)
{
    return 0;
}

inline int bt_bap_scan_delegator_rem_src(std::uint8_t)
{
    return 0;
}

inline int bt_pacs_register(const bt_pacs_register_param *)
{
    return 0;
}

inline int bt_pacs_unregister()
{
    return 0;
}

inline int bt_pacs_cap_register(int, bt_pacs_cap *)
{
    return 0;
}

inline int bt_pacs_cap_unregister(int, bt_pacs_cap *)
{
    return 0;
}

inline int bt_pacs_set_location(int, bt_audio_location)
{
    return 0;
}

inline int bt_pacs_set_supported_contexts(int, bt_audio_context)
{
    return 0;
}

inline int bt_pacs_set_available_contexts(int, bt_audio_context)
{
    return 0;
}

inline int bt_le_scan_start(int, void *)
{
    return 0;
}

inline int bt_le_scan_stop()
{
    ++pbp_stub::scan_stop_calls;
    pbp_stub::cleanup_events.push_back(pbp_stub::CleanupEvent::scan_stop);
    if (pbp_stub::scan_stop_results.empty())
    {
        return pbp_stub::scan_stop_default_result;
    }
    const int result = pbp_stub::scan_stop_results.front();
    pbp_stub::scan_stop_results.pop_front();
    return result;
}

inline int bt_le_scan_cb_register(bt_le_scan_cb *)
{
    return 0;
}

inline void bt_le_scan_cb_unregister(bt_le_scan_cb *)
{
}

inline int bt_le_per_adv_sync_cb_register(bt_le_per_adv_sync_cb *callbacks)
{
    ++pbp_stub::periodic_callback_register_calls;
    pbp_stub::periodic_callbacks = callbacks;
    return 0;
}

inline int bt_le_per_adv_sync_cb_unregister(bt_le_per_adv_sync_cb *)
{
    ++pbp_stub::periodic_callback_unregister_calls;
    return 0;
}

inline int bt_le_per_adv_sync_create(const bt_le_per_adv_sync_param *parameters,
                                     bt_le_per_adv_sync **sync)
{
    static bt_le_per_adv_sync instance;
    *sync = &instance;
    pbp_stub::periodic_instance = &instance;
    pbp_stub::periodic_address = parameters->addr;
    pbp_stub::periodic_sid = parameters->sid;
    pbp_stub::foreign_periodic = false;
    pbp_stub::periodic_present.store(true);
    if ((pbp_stub::periodic_callbacks != nullptr) &&
        (pbp_stub::periodic_create_mode ==
         pbp_stub::PeriodicCreateMode::synced_before_return) &&
        (pbp_stub::periodic_callbacks->synced != nullptr))
    {
        bt_le_per_adv_sync_synced_info information = {
            .addr = &pbp_stub::periodic_address,
            .sid = pbp_stub::periodic_sid,
        };
        pbp_stub::periodic_callbacks->synced(*sync, &information);
    }
    else if ((pbp_stub::periodic_callbacks != nullptr) &&
             (pbp_stub::periodic_create_mode ==
              pbp_stub::PeriodicCreateMode::terminated_before_return) &&
             (pbp_stub::periodic_callbacks->term != nullptr))
    {
        const bt_le_per_adv_sync_term_info information = {
            .addr = &pbp_stub::periodic_address,
            .sid = pbp_stub::periodic_sid,
            .reason = 0x08U,
        };
        pbp_stub::periodic_present.store(false);
        pbp_stub::periodic_callbacks->term(*sync, &information);
    }
    return 0;
}

inline int bt_le_per_adv_sync_delete(bt_le_per_adv_sync *sync)
{
    ++pbp_stub::periodic_delete_calls;
    if (pbp_stub::foreign_periodic)
    {
        ++pbp_stub::foreign_periodic_delete_calls;
    }
    pbp_stub::cleanup_events.push_back(pbp_stub::CleanupEvent::periodic_delete);
    if (!pbp_stub::periodic_delete_results.empty())
    {
        const int result = pbp_stub::periodic_delete_results.front();
        pbp_stub::periodic_delete_results.pop_front();
        if (result != 0)
        {
            if (pbp_stub::reuse_same_identity_before_term)
            {
                pbp_stub::reuse_same_identity_before_term = false;
                const bt_addr_le_t terminated_address =
                    pbp_stub::periodic_address;
                const std::uint8_t terminated_sid = pbp_stub::periodic_sid;
                pbp_stub::periodic_present.store(false);
                pbp_stub::reusePeriodicSlot(terminated_address, terminated_sid);
                if ((pbp_stub::periodic_callbacks != nullptr) &&
                    (pbp_stub::periodic_callbacks->term != nullptr))
                {
                    const bt_le_per_adv_sync_term_info information = {
                        .addr = &pbp_stub::periodic_address,
                        .sid = pbp_stub::periodic_sid,
                        .reason = BT_HCI_ERR_LOCALHOST_TERM_CONN,
                    };
                    pbp_stub::periodic_callbacks->term(sync, &information);
                }
            }
            else if (pbp_stub::reuse_after_transient_delete)
            {
                pbp_stub::reuse_after_transient_delete = false;
                const bt_addr_le_t terminated_address =
                    pbp_stub::periodic_address;
                const std::uint8_t terminated_sid = pbp_stub::periodic_sid;
                pbp_stub::periodic_present.store(false);
                if ((pbp_stub::periodic_callbacks != nullptr) &&
                    (pbp_stub::periodic_callbacks->term != nullptr))
                {
                    const bt_le_per_adv_sync_term_info information = {
                        .addr = &terminated_address,
                        .sid = terminated_sid,
                        .reason = BT_HCI_ERR_LOCALHOST_TERM_CONN,
                    };
                    pbp_stub::periodic_callbacks->term(sync, &information);
                }
                bt_addr_le_t foreign_address = {};
                foreign_address.address[0] = 0xa5U;
                pbp_stub::reusePeriodicSlot(foreign_address, 0x0eU);
            }
            return result;
        }
    }
    else if (pbp_stub::periodic_delete_default_result != 0)
    {
        return pbp_stub::periodic_delete_default_result;
    }
    if (pbp_stub::periodic_delete_mode ==
        pbp_stub::PeriodicDeleteMode::pending)
    {
        pbp_stub::periodic_cancel_polls.store(2U);
        return 0;
    }
    if (pbp_stub::periodic_delete_mode ==
        pbp_stub::PeriodicDeleteMode::pending_stalled)
    {
        return 0;
    }
    if (pbp_stub::periodic_delete_mode ==
        pbp_stub::PeriodicDeleteMode::synchronous)
    {
        pbp_stub::periodic_present.store(false);
        if ((pbp_stub::periodic_callbacks != nullptr) &&
            (pbp_stub::periodic_callbacks->term != nullptr))
        {
            const bt_le_per_adv_sync_term_info information = {
                .addr = &pbp_stub::periodic_address,
                .sid = pbp_stub::periodic_sid,
                .reason = BT_HCI_ERR_LOCALHOST_TERM_CONN,
            };
            pbp_stub::periodic_callbacks->term(sync, &information);
        }
        return 0;
    }
    const bt_addr_le_t terminated_address = pbp_stub::periodic_address;
    const std::uint8_t terminated_sid = pbp_stub::periodic_sid;
    std::thread([sync, terminated_address, terminated_sid]()
    {
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        pbp_stub::periodic_present.store(false);
        if ((pbp_stub::periodic_callbacks != nullptr) &&
            (pbp_stub::periodic_callbacks->term != nullptr))
        {
            const bt_le_per_adv_sync_term_info information = {
                .addr = &terminated_address,
                .sid = terminated_sid,
                .reason = BT_HCI_ERR_LOCALHOST_TERM_CONN,
            };
            pbp_stub::periodic_callbacks->term(sync, &information);
        }
    }).detach();
    return 0;
}

inline bt_le_per_adv_sync *bt_le_per_adv_sync_lookup_addr(
    const bt_addr_le_t *address, std::uint8_t sid)
{
    ++pbp_stub::periodic_lookup_calls;
    if (pbp_stub::reuse_same_identity_during_lookup &&
        pbp_stub::periodic_present.load() &&
        (bt_addr_le_cmp(address, &pbp_stub::periodic_address) == 0) &&
        (sid == pbp_stub::periodic_sid))
    {
        pbp_stub::reuse_same_identity_during_lookup = false;
        const bt_addr_le_t terminated_address = pbp_stub::periodic_address;
        const std::uint8_t terminated_sid = pbp_stub::periodic_sid;
        pbp_stub::periodic_present.store(false);
        if ((pbp_stub::periodic_callbacks != nullptr) &&
            (pbp_stub::periodic_callbacks->term != nullptr))
        {
            const bt_le_per_adv_sync_term_info information = {
                .addr = &terminated_address,
                .sid = terminated_sid,
                .reason = BT_HCI_ERR_LOCALHOST_TERM_CONN,
            };
            pbp_stub::periodic_callbacks->term(
                pbp_stub::periodic_instance, &information);
        }
        pbp_stub::reusePeriodicSlot(terminated_address, terminated_sid);
    }
    unsigned int polls = pbp_stub::periodic_cancel_polls.load();
    if (polls != 0U)
    {
        polls = pbp_stub::periodic_cancel_polls.fetch_sub(1U);
        if (polls == 1U)
        {
            pbp_stub::periodic_present.store(false);
            pbp_stub::cleanup_events.push_back(
                pbp_stub::CleanupEvent::periodic_released);
        }
    }
    if (!pbp_stub::periodic_present.load() ||
        (bt_addr_le_cmp(address, &pbp_stub::periodic_address) != 0) ||
        (sid != pbp_stub::periodic_sid))
    {
        return nullptr;
    }
    return pbp_stub::periodic_instance;
}

struct bt_le_ext_adv
{
};

struct bt_bap_qos_cfg
{
    std::uint32_t pd = 0U;
    int framing = 0;
    int phy = 0;
    std::uint8_t rtn = 0U;
    std::uint16_t sdu = 0U;
    std::uint16_t latency = 0U;
    std::uint32_t interval = 0U;
};

struct bt_bap_lc3_preset
{
    bt_audio_codec_cfg codec_cfg = {};
    bt_bap_qos_cfg qos = {};
};

struct bt_cap_stream
{
    bt_bap_stream bap_stream = {};
};

struct bt_cap_broadcast_source
{
    int id = 0;
};

struct bt_cap_initiator_broadcast_stream_param
{
    bt_cap_stream *stream = nullptr;
    std::size_t data_len = 0U;
    const std::uint8_t *data = nullptr;
};

struct bt_cap_initiator_broadcast_subgroup_param
{
    std::size_t stream_count = 0U;
    bt_cap_initiator_broadcast_stream_param *stream_params = nullptr;
    bt_audio_codec_cfg *codec_cfg = nullptr;
};

struct bt_cap_initiator_broadcast_create_param
{
    std::size_t subgroup_count = 0U;
    bt_cap_initiator_broadcast_subgroup_param *subgroup_params = nullptr;
    bt_bap_qos_cfg *qos = nullptr;
    int packing = 0;
    bool encryption = false;
    std::uint8_t broadcast_code[16] = {};
};

struct bt_cap_initiator_cb
{
    void (*broadcast_started)(bt_cap_broadcast_source *) = nullptr;
    void (*broadcast_stopped)(bt_cap_broadcast_source *, std::uint8_t) = nullptr;
};

constexpr int BT_BAP_QOS_CFG_FRAMING_UNFRAMED = 0;
constexpr int BT_BAP_QOS_CFG_2M = 2;
constexpr int BT_ISO_PACKING_SEQUENTIAL = 0;
constexpr int BT_ISO_CHAN_SEND_RESERVE = 0;
constexpr int BT_APPEARANCE_AUDIO_SOURCE_BROADCASTING_DEVICE = 0x0840;
constexpr int BT_PBP_MIN_PBA_SIZE = 3;
constexpr int BT_LE_EXT_ADV_START_DEFAULT = 0;
#define BT_BAP_ADV_PARAM_BROADCAST_FAST nullptr
#define BT_BAP_PER_ADV_PARAM_BROADCAST_FAST nullptr
#define BT_BYTES_LIST_LE16(value) \
    static_cast<std::uint8_t>((value) & 0xffU), \
        static_cast<std::uint8_t>(((value) >> 8U) & 0xffU)

inline void bt_cap_stream_ops_register(bt_cap_stream *stream,
                                       const bt_bap_stream_ops *callbacks)
{
    stream->bap_stream.callbacks = callbacks;
}

inline int bt_cap_initiator_register_cb(bt_cap_initiator_cb *)
{
    return 0;
}

inline int bt_cap_initiator_unregister_cb(bt_cap_initiator_cb *)
{
    return 0;
}

inline int bt_cap_initiator_broadcast_audio_create(
    const bt_cap_initiator_broadcast_create_param *, bt_cap_broadcast_source **source)
{
    static bt_cap_broadcast_source instance;
    *source = &instance;
    return 0;
}

inline int bt_cap_initiator_broadcast_audio_start(bt_cap_broadcast_source *, bt_le_ext_adv *)
{
    return 0;
}

inline int bt_cap_initiator_broadcast_audio_stop(bt_cap_broadcast_source *)
{
    return -EALREADY;
}

inline int bt_cap_initiator_broadcast_audio_delete(bt_cap_broadcast_source *)
{
    return 0;
}

inline int bt_cap_initiator_broadcast_audio_update(bt_cap_broadcast_source *,
                                                   const std::uint8_t *, std::size_t)
{
    return 0;
}

inline int bt_cap_initiator_broadcast_get_base(bt_cap_broadcast_source *, net_buf_simple *)
{
    return 0;
}

inline int bt_cap_stream_send(bt_cap_stream *, net_buf *, std::uint16_t)
{
    return 0;
}

inline int bt_le_ext_adv_create(const void *, void *, bt_le_ext_adv **advertising)
{
    static bt_le_ext_adv instance;
    *advertising = &instance;
    return 0;
}

inline int bt_le_ext_adv_set_data(bt_le_ext_adv *, const bt_data *, std::size_t,
                                  const bt_data *, std::size_t)
{
    return 0;
}

inline int bt_le_ext_adv_start(bt_le_ext_adv *, int)
{
    return 0;
}

inline int bt_le_ext_adv_stop(bt_le_ext_adv *)
{
    return 0;
}

inline int bt_le_ext_adv_delete(bt_le_ext_adv *)
{
    return 0;
}

inline int bt_le_per_adv_set_param(bt_le_ext_adv *, const void *)
{
    return 0;
}

inline int bt_le_per_adv_set_data(bt_le_ext_adv *, const bt_data *, std::size_t)
{
    return 0;
}

inline int bt_le_per_adv_start(bt_le_ext_adv *)
{
    return 0;
}

inline int bt_le_per_adv_stop(bt_le_ext_adv *)
{
    return 0;
}

inline int bt_rand(void *data, std::size_t length)
{
    memset(data, 0x5a, length);
    return 0;
}

class BleDeviceStub
{
public:
    bool initialized() const noexcept
    {
        return true;
    }
};

inline BleDeviceStub BLEDevice;
