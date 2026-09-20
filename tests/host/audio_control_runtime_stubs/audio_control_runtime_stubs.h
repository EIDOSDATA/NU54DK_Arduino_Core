/**
 * @file audio_control_runtime_stubs.h
 * @brief Audio Control production 구현을 host에서 실행하기 위한 최소 Zephyr stub입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#ifndef NUCODE_AUDIO_CONTROL_RUNTIME_STUBS_H
#define NUCODE_AUDIO_CONTROL_RUNTIME_STUBS_H

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <mutex>

#define CONFIG_BT_VCP_VOL_CTLR 1
#define CONFIG_BT_VCP_VOL_CTLR_VOCS 1
#define CONFIG_BT_VCP_VOL_CTLR_AICS 1
#define CONFIG_BT_VCP_VOL_CTLR_MAX_VOCS_INST 1
#define CONFIG_BT_VCP_VOL_CTLR_MAX_AICS_INST 1
#define CONFIG_BT_VOCS_CLIENT 1
#define CONFIG_BT_AICS_CLIENT 1
#define CONFIG_BT_MICP_MIC_CTLR 1
#define CONFIG_BT_MICP_MIC_CTLR_AICS 1
#define CONFIG_BT_MICP_MIC_CTLR_MAX_AICS_INST 1

#define __packed __attribute__((packed))
#define BT_GATT_ITER_STOP 0U
#define BT_ATT_ERR_UNLIKELY 0x0eU
#define BT_GATT_ERR(value) (-(static_cast<int>(value)))
#define K_FOREVER 0
#define BT_VCP_STATE_MUTED 1U
#define BT_AICS_STATE_MUTED 1U
#define BT_AICS_STATE_MUTE_DISABLED 2U
#define BT_AICS_STATUS_ACTIVE 1U
#define BT_MICP_MUTE_MUTED 1U
#define BT_MICP_MUTE_DISABLED 2U
#define BT_VOCS_MIN_OFFSET (-255)
#define BT_VOCS_MAX_OFFSET 255
#if !defined(ESTALE)
#define ESTALE 116
#endif
#define CONTAINER_OF(pointer, type, member)                                                        \
    reinterpret_cast<type *>(reinterpret_cast<std::uint8_t *>(pointer) - offsetof(type, member))

using atomic_val_t = long;
using atomic_t = long;

#define ATOMIC_INIT(value) (value)

inline atomic_val_t atomic_get(const atomic_t *value) noexcept
{
    return *value;
}

inline void atomic_set(atomic_t *target, atomic_val_t value) noexcept
{
    *target = value;
}

inline bool atomic_cas(atomic_t *target, atomic_val_t old_value, atomic_val_t new_value) noexcept
{
    if (*target != old_value)
    {
        return false;
    }
    *target = new_value;
    return true;
}

inline void atomic_clear_bit(atomic_t *target, unsigned int bit) noexcept
{
    *target &= ~(static_cast<atomic_t>(1U) << bit);
}

struct k_mutex
{
    std::recursive_mutex native;
};

#define K_MUTEX_DEFINE(name) k_mutex name

inline void k_mutex_lock(k_mutex *mutex, int) noexcept
{
    mutex->native.lock();
}

inline void k_mutex_unlock(k_mutex *mutex) noexcept
{
    mutex->native.unlock();
}

namespace audio_control_stub
{
    inline std::uint32_t uptime_ms = 0U;
}

inline std::uint32_t k_uptime_get_32() noexcept
{
    return audio_control_stub::uptime_ms;
}

inline std::uint16_t sys_get_le16(const std::uint8_t *data) noexcept
{
    return static_cast<std::uint16_t>(data[0]) |
           static_cast<std::uint16_t>(static_cast<std::uint16_t>(data[1]) << 8U);
}

inline std::uint32_t sys_get_le32(const std::uint8_t *data) noexcept
{
    return static_cast<std::uint32_t>(data[0]) |
           (static_cast<std::uint32_t>(data[1]) << 8U) |
           (static_cast<std::uint32_t>(data[2]) << 16U) |
           (static_cast<std::uint32_t>(data[3]) << 24U);
}

struct bt_conn
{
    std::uint32_t references = 0U;
    bool active = false;
};

struct bt_conn_cb
{
    void (*disconnected)(bt_conn *, std::uint8_t) = nullptr;
};

#define BT_CONN_CB_DEFINE(name) static bt_conn_cb name

inline bt_conn *bt_conn_ref(bt_conn *connection) noexcept
{
    if (connection != nullptr)
    {
        ++connection->references;
    }
    return connection;
}

inline void bt_conn_unref(bt_conn *connection) noexcept
{
    if ((connection != nullptr) && (connection->references != 0U))
    {
        --connection->references;
    }
}

struct bt_gatt_read_params;
using bt_gatt_read_func_t = std::uint8_t (*)(bt_conn *, std::uint8_t, bt_gatt_read_params *,
                                             const void *, std::uint16_t);

struct bt_gatt_read_params
{
    bt_gatt_read_func_t func;
    std::uint8_t handle_count;
    struct
    {
        std::uint16_t handle;
        std::uint16_t offset;
    } single;
};

struct bt_gatt_subscribe_params
{
};
struct bt_gatt_discover_params
{
};
struct bt_gatt_write_params
{
};
struct bt_uuid_16
{
};
struct sys_snode_t
{
};

struct bt_vocs;
struct bt_aics;
struct bt_vcp_vol_ctlr;
struct bt_micp_mic_ctlr;

struct bt_vocs_cb
{
    void (*state)(bt_vocs *, int, std::int16_t) = nullptr;
    void (*location)(bt_vocs *, int, std::uint32_t) = nullptr;
    void (*description)(bt_vocs *, int, char *) = nullptr;
    void (*discover)(bt_vocs *, int) = nullptr;
    void (*set_offset)(bt_vocs *, int) = nullptr;
};

struct bt_aics_cb
{
    void (*state)(bt_aics *, int, std::int8_t, std::uint8_t, std::uint8_t) = nullptr;
    void (*gain_setting)(bt_aics *, int, std::uint8_t, std::int8_t, std::int8_t) = nullptr;
    void (*type)(bt_aics *, int, std::uint8_t) = nullptr;
    void (*status)(bt_aics *, int, bool) = nullptr;
    void (*description)(bt_aics *, int, char *) = nullptr;
    void (*discover)(bt_aics *, int) = nullptr;
    void (*set_gain)(bt_aics *, int) = nullptr;
    void (*unmute)(bt_aics *, int) = nullptr;
    void (*mute)(bt_aics *, int) = nullptr;
    void (*set_manual_mode)(bt_aics *, int) = nullptr;
    void (*set_auto_mode)(bt_aics *, int) = nullptr;
};

struct bt_vcp_vol_ctlr_cb
{
    void (*state)(bt_vcp_vol_ctlr *, int, std::uint8_t, std::uint8_t) = nullptr;
    void (*flags)(bt_vcp_vol_ctlr *, int, std::uint8_t) = nullptr;
    void (*discover)(bt_vcp_vol_ctlr *, int, std::uint8_t, std::uint8_t) = nullptr;
    void (*vol_down)(bt_vcp_vol_ctlr *, int) = nullptr;
    void (*vol_up)(bt_vcp_vol_ctlr *, int) = nullptr;
    void (*mute)(bt_vcp_vol_ctlr *, int) = nullptr;
    void (*unmute)(bt_vcp_vol_ctlr *, int) = nullptr;
    void (*vol_down_unmute)(bt_vcp_vol_ctlr *, int) = nullptr;
    void (*vol_up_unmute)(bt_vcp_vol_ctlr *, int) = nullptr;
    void (*vol_set)(bt_vcp_vol_ctlr *, int) = nullptr;
    bt_vocs_cb vocs_cb = {};
    bt_aics_cb aics_cb = {};
    sys_snode_t _node = {};
};

struct bt_micp_mic_ctlr_cb
{
    void (*mute)(bt_micp_mic_ctlr *, int, std::uint8_t) = nullptr;
    void (*discover)(bt_micp_mic_ctlr *, int, std::uint8_t) = nullptr;
    void (*mute_written)(bt_micp_mic_ctlr *, int) = nullptr;
    void (*unmute_written)(bt_micp_mic_ctlr *, int) = nullptr;
    bt_aics_cb aics_cb = {};
    sys_snode_t _node = {};
};

struct vcs_state
{
    std::uint8_t volume;
    std::uint8_t mute;
    std::uint8_t change_counter;
} __packed;

struct bt_vocs_state
{
    std::int16_t offset;
    std::uint8_t change_counter;
} __packed;

struct bt_aics_state
{
    std::int8_t gain;
    std::uint8_t mute;
    std::uint8_t gain_mode;
    std::uint8_t change_counter;
} __packed;

struct bt_aics_gain_settings
{
    std::uint8_t units;
    std::int8_t minimum;
    std::int8_t maximum;
} __packed;

struct bt_vocs
{
};

struct bt_vocs_client
{
    bt_vocs vocs = {};
    bt_vocs_state state = {};
    std::uint32_t location = 0U;
    std::uint16_t start_handle = 0U;
    std::uint16_t end_handle = 0U;
    std::uint16_t state_handle = 0U;
    std::uint16_t location_handle = 0U;
    std::uint16_t control_handle = 0U;
    std::uint16_t desc_handle = 0U;
    bt_conn *conn = nullptr;
    atomic_t flags[1] = {};
};

enum bt_vocs_client_flag
{
    BT_VOCS_CLIENT_FLAG_BUSY,
    BT_VOCS_CLIENT_FLAG_CP_RETRIED,
    BT_VOCS_CLIENT_FLAG_DESC_WRITABLE,
    BT_VOCS_CLIENT_FLAG_LOC_WRITABLE,
    BT_VOCS_CLIENT_FLAG_ACTIVE,
};

struct bt_aics_client
{
    std::uint8_t change_counter = 0U;
    std::uint8_t gain_mode = 0U;
    std::uint16_t start_handle = 0U;
    std::uint16_t end_handle = 0U;
    std::uint16_t state_handle = 0U;
    std::uint16_t gain_handle = 0U;
    std::uint16_t type_handle = 0U;
    std::uint16_t status_handle = 0U;
    std::uint16_t control_handle = 0U;
    std::uint16_t desc_handle = 0U;
    bt_conn *conn = nullptr;
};

struct bt_aics
{
    bool client_instance = true;
    bt_aics_client cli = {};
};

struct bt_vcp_vol_ctlr
{
    vcs_state state = {};
    std::uint8_t vol_flags = 0U;
    std::uint16_t start_handle = 0U;
    std::uint16_t end_handle = 0U;
    std::uint16_t state_handle = 0U;
    std::uint16_t control_handle = 0U;
    std::uint16_t vol_flag_handle = 0U;
    bt_conn *conn = nullptr;
    std::uint8_t vocs_inst_cnt = 0U;
    bt_vocs *vocs[1] = {};
    std::uint8_t aics_inst_cnt = 0U;
    bt_aics *aics[1] = {};
};

struct bt_micp_mic_ctlr
{
    std::uint16_t start_handle = 0U;
    std::uint16_t end_handle = 0U;
    std::uint16_t mute_handle = 0U;
    bt_conn *conn = nullptr;
    std::uint8_t aics_inst_cnt = 0U;
    bt_aics *aics[1] = {};
};

struct bt_vcp_included
{
    std::uint8_t vocs_cnt = 0U;
    bt_vocs **vocs = nullptr;
    std::uint8_t aics_cnt = 0U;
    bt_aics **aics = nullptr;
};

struct bt_micp_included
{
    std::uint8_t aics_cnt = 0U;
    bt_aics **aics = nullptr;
};

namespace audio_control_stub
{
    inline bt_conn connection = {};
    inline bt_vocs_client volume_offset = {};
    inline bt_aics volume_input = {};
    inline bt_vcp_vol_ctlr volume_controller = {};
    inline bt_aics microphone_input = {};
    inline bt_micp_mic_ctlr microphone_controller = {};
    inline bt_vcp_vol_ctlr_cb *volume_callbacks = nullptr;
    inline bt_micp_mic_ctlr_cb *microphone_callbacks = nullptr;
    inline bt_gatt_read_params *pending_read = nullptr;
    inline bt_conn *pending_connection = nullptr;
    inline bt_gatt_read_params *delayed_read = nullptr;
    inline bt_conn *delayed_connection = nullptr;
    inline std::uint32_t cancel_callbacks = 0U;
    inline int next_read_result = 0;
    inline bool vocs_reference_held = false;
    inline bool volume_aics_reference_held = false;

    /** @brief 한 connection pool slot에 controller client 포인터를 다시 결합합니다. */
    inline void bindControllerClients() noexcept
    {
        volume_controller.conn = &connection;
        volume_offset.conn = nullptr;
        volume_offset.state_handle = 0x0111U;
        volume_offset.location_handle = 0x0112U;
        volume_input.cli.conn = nullptr;
        microphone_controller.conn = &connection;
        microphone_input.cli.conn = &connection;
        vocs_reference_held = false;
        volume_aics_reference_held = false;
    }

    inline void reset() noexcept
    {
        uptime_ms = 0U;
        connection = {};
        connection.active = true;
        connection.references = 1U;
        volume_offset = {};
        volume_input = {};
        volume_controller = {};
        microphone_input = {};
        microphone_controller = {};
        bindControllerClients();
        volume_controller.state_handle = 0x0101U;
        volume_controller.vol_flag_handle = 0x0102U;
        volume_controller.vocs_inst_cnt = 1U;
        volume_controller.vocs[0] = &volume_offset.vocs;
        volume_controller.aics_inst_cnt = 1U;
        volume_controller.aics[0] = &volume_input;
        volume_offset.state_handle = 0x0111U;
        volume_offset.location_handle = 0x0112U;
        volume_input.cli.state_handle = 0x0121U;
        volume_input.cli.gain_handle = 0x0122U;
        volume_input.cli.type_handle = 0x0123U;
        volume_input.cli.status_handle = 0x0124U;
        microphone_controller.mute_handle = 0x0201U;
        microphone_controller.aics_inst_cnt = 1U;
        microphone_controller.aics[0] = &microphone_input;
        microphone_input.cli.state_handle = 0x0211U;
        microphone_input.cli.gain_handle = 0x0212U;
        microphone_input.cli.type_handle = 0x0213U;
        microphone_input.cli.status_handle = 0x0214U;
        pending_read = nullptr;
        pending_connection = nullptr;
        delayed_read = nullptr;
        delayed_connection = nullptr;
        cancel_callbacks = 0U;
        next_read_result = 0;
    }

    /** @brief top-level VCP callback 전 포함 VOCS/AICS discovery의 conn ref 획득을 재현합니다. */
    inline void reachVolumeIncludedDiscovery() noexcept
    {
        if (!vocs_reference_held && (volume_controller.conn != nullptr))
        {
            volume_offset.conn = volume_controller.conn;
            bt_conn_ref(volume_controller.conn);
            vocs_reference_held = true;
        }
        if (!volume_aics_reference_held && (volume_controller.conn != nullptr))
        {
            volume_input.cli.conn = volume_controller.conn;
            bt_conn_ref(volume_controller.conn);
            volume_aics_reference_held = true;
        }
    }

    /** @brief locked host의 disconnect와 non-sticky profile ref 해제를 재현합니다. */
    inline void disconnectSingleConnection() noexcept
    {
        if (!connection.active)
        {
            return;
        }
        connection.active = false;
        volume_controller.conn = nullptr;
        if (volume_aics_reference_held && (volume_input.cli.conn == &connection))
        {
            volume_input.cli.conn = nullptr;
            volume_aics_reference_held = false;
            bt_conn_unref(&connection);
        }
        else
        {
            volume_input.cli.conn = nullptr;
        }
        microphone_controller.conn = nullptr;
        microphone_input.cli.conn = nullptr;
        bt_conn_unref(&connection);
    }

    /** @brief ref가 0인 경우에만 CONFIG_BT_MAX_CONN=1 slot을 재할당합니다. */
    inline bool allocateSingleConnection() noexcept
    {
        if (connection.references != 0U)
        {
            return false;
        }
        connection.references = 1U;
        connection.active = true;
        bindControllerClients();
        return true;
    }

    inline void completeRead(const void *data, std::uint16_t length,
                             std::uint8_t error = 0U) noexcept
    {
        bt_gatt_read_params *parameters = pending_read;
        bt_conn *read_connection = pending_connection;
        pending_read = nullptr;
        pending_connection = nullptr;
        if ((parameters != nullptr) && (parameters->func != nullptr))
        {
            parameters->func(read_connection, error, parameters, data, length);
        }
    }

    /** @brief cancel lookup이 놓친 callback을 재현하도록 pending read를 분리합니다. */
    inline void detachReadForLateCallback() noexcept
    {
        delayed_read = pending_read;
        delayed_connection = pending_connection;
        pending_read = nullptr;
        pending_connection = nullptr;
    }

    /** @brief 분리한 old read callback을 지정한 시점에 전달합니다. */
    inline void completeLateRead(std::uint8_t error = BT_ATT_ERR_UNLIKELY) noexcept
    {
        bt_gatt_read_params *parameters = delayed_read;
        bt_conn *read_connection = delayed_connection;
        delayed_read = nullptr;
        delayed_connection = nullptr;
        if ((parameters != nullptr) && (parameters->func != nullptr))
        {
            parameters->func(read_connection, error, parameters, nullptr, 0U);
        }
    }
}

inline int bt_gatt_read(bt_conn *connection, bt_gatt_read_params *parameters) noexcept
{
    if (audio_control_stub::next_read_result != 0)
    {
        const int result = audio_control_stub::next_read_result;
        audio_control_stub::next_read_result = 0;
        return result;
    }
    if (audio_control_stub::pending_read != nullptr)
    {
        return -16;
    }
    audio_control_stub::pending_read = parameters;
    audio_control_stub::pending_connection = connection;
    return 0;
}

inline void bt_gatt_cancel(bt_conn *connection, bt_gatt_read_params *parameters) noexcept
{
    if ((audio_control_stub::pending_read == parameters) &&
        (audio_control_stub::pending_connection == connection))
    {
        audio_control_stub::pending_read = nullptr;
        audio_control_stub::pending_connection = nullptr;
        ++audio_control_stub::cancel_callbacks;
        parameters->func(connection, BT_ATT_ERR_UNLIKELY, parameters, nullptr, 0U);
    }
}

inline int bt_vcp_vol_ctlr_cb_register(bt_vcp_vol_ctlr_cb *callbacks) noexcept
{
    audio_control_stub::volume_callbacks = callbacks;
    return 0;
}

inline int bt_micp_mic_ctlr_cb_register(bt_micp_mic_ctlr_cb *callbacks) noexcept
{
    audio_control_stub::microphone_callbacks = callbacks;
    return 0;
}

inline int bt_vcp_vol_ctlr_discover(bt_conn *, bt_vcp_vol_ctlr **controller) noexcept
{
    *controller = &audio_control_stub::volume_controller;
    return 0;
}

inline int bt_micp_mic_ctlr_discover(bt_conn *, bt_micp_mic_ctlr **controller) noexcept
{
    *controller = &audio_control_stub::microphone_controller;
    return 0;
}

inline int bt_vcp_vol_ctlr_included_get(bt_vcp_vol_ctlr *controller,
                                         bt_vcp_included *included) noexcept
{
    audio_control_stub::reachVolumeIncludedDiscovery();
    included->vocs_cnt = controller->vocs_inst_cnt;
    included->vocs = controller->vocs;
    included->aics_cnt = controller->aics_inst_cnt;
    included->aics = controller->aics;
    return 0;
}

inline int bt_micp_mic_ctlr_included_get(bt_micp_mic_ctlr *controller,
                                         bt_micp_included *included) noexcept
{
    included->aics_cnt = controller->aics_inst_cnt;
    included->aics = controller->aics;
    return 0;
}

inline int bt_vcp_vol_ctlr_conn_get(const bt_vcp_vol_ctlr *controller, bt_conn **connection) noexcept
{
    *connection = controller->conn;
    return *connection == nullptr ? -107 : 0;
}

inline int bt_micp_mic_ctlr_conn_get(const bt_micp_mic_ctlr *controller,
                                     bt_conn **connection) noexcept
{
    *connection = controller->conn;
    return *connection == nullptr ? -107 : 0;
}

inline int bt_vocs_client_conn_get(const bt_vocs *instance, bt_conn **connection) noexcept
{
    const auto *client = reinterpret_cast<const bt_vocs_client *>(instance);
    *connection = client->conn;
    return *connection == nullptr ? -107 : 0;
}

inline int bt_aics_client_conn_get(const bt_aics *instance, bt_conn **connection) noexcept
{
    *connection = instance->cli.conn;
    return *connection == nullptr ? -107 : 0;
}

#define NUCODE_STUB_OPERATION(name, signature)                                                     \
    inline int name signature noexcept                                                             \
    {                                                                                              \
        return 0;                                                                                  \
    }

NUCODE_STUB_OPERATION(bt_vcp_vol_ctlr_vol_down, (bt_vcp_vol_ctlr *))
NUCODE_STUB_OPERATION(bt_vcp_vol_ctlr_vol_up, (bt_vcp_vol_ctlr *))
NUCODE_STUB_OPERATION(bt_vcp_vol_ctlr_mute, (bt_vcp_vol_ctlr *))
NUCODE_STUB_OPERATION(bt_vcp_vol_ctlr_unmute, (bt_vcp_vol_ctlr *))
NUCODE_STUB_OPERATION(bt_vcp_vol_ctlr_set_vol, (bt_vcp_vol_ctlr *, std::uint8_t))
NUCODE_STUB_OPERATION(bt_vocs_state_set, (bt_vocs *, std::int16_t))
NUCODE_STUB_OPERATION(bt_vocs_location_set, (bt_vocs *, std::uint32_t))
NUCODE_STUB_OPERATION(bt_vocs_description_set, (bt_vocs *, const char *))
NUCODE_STUB_OPERATION(bt_aics_gain_set, (bt_aics *, std::int8_t))
NUCODE_STUB_OPERATION(bt_aics_mute, (bt_aics *))
NUCODE_STUB_OPERATION(bt_aics_unmute, (bt_aics *))
NUCODE_STUB_OPERATION(bt_aics_manual_gain_set, (bt_aics *))
NUCODE_STUB_OPERATION(bt_aics_automatic_gain_set, (bt_aics *))
NUCODE_STUB_OPERATION(bt_micp_mic_ctlr_mute, (bt_micp_mic_ctlr *))
NUCODE_STUB_OPERATION(bt_micp_mic_ctlr_unmute, (bt_micp_mic_ctlr *))

#undef NUCODE_STUB_OPERATION

namespace nucode::ble
{
    class BLEConnectionHandle final
    {
      public:
        BLEConnectionHandle() noexcept = default;
        explicit BLEConnectionHandle(std::uint16_t value) noexcept : value_(value)
        {
        }

        [[nodiscard]] bool valid() const noexcept
        {
            return value_ != 0U;
        }

        friend bool operator==(const BLEConnectionHandle &left,
                               const BLEConnectionHandle &right) noexcept
        {
            return left.value_ == right.value_;
        }

      private:
        std::uint16_t value_ = 0U;
    };

    namespace internal
    {
        inline bt_conn *referenceConnection(const BLEConnectionHandle &handle) noexcept
        {
            if (!handle.valid() || !audio_control_stub::connection.active)
            {
                return nullptr;
            }
            return bt_conn_ref(&audio_control_stub::connection);
        }

        inline bool activeConnection(const BLEConnectionHandle &handle) noexcept
        {
            return handle.valid() && audio_control_stub::connection.active;
        }

        inline bool activeConnection(const bt_conn *connection) noexcept
        {
            return (connection != nullptr) && connection->active;
        }
    }
}

#endif
