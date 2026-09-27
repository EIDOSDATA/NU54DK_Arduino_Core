/** @file @brief CSIP Member 수명주기 Host 시험용 최소 driver 경계입니다. */
#pragma once

#include <zephyr/bluetooth/conn.h>

#include <cstddef>
#include <cstdint>

#define BT_CSIP_SIRK_SIZE 16
#define BT_CSIP_RSI_SIZE 6
#define BT_CSIP_READ_SIRK_REQ_RSP_REJECT 0U
#define BT_CSIP_READ_SIRK_REQ_RSP_ACCEPT_ENC 1U
#define BT_DATA_CSIS_RSI 0x2EU

struct bt_csip_set_member_svc_inst
{
    int marker;
};

struct bt_csip_set_member_set_info
{
    std::uint8_t sirk[BT_CSIP_SIRK_SIZE];
    std::uint8_t set_size;
    std::uint8_t rank;
    bool lockable;
    bool locked;
};

struct bt_csip_set_member_cb
{
    void (*lock_changed)(bt_conn *, bt_csip_set_member_svc_inst *, bool);
    std::uint8_t (*sirk_read_req)(bt_conn *, bt_csip_set_member_svc_inst *);
};

struct bt_csip_set_member_register_param
{
    std::uint8_t set_size;
    bool lockable;
    std::uint8_t rank;
    bt_csip_set_member_cb *cb;
    std::uint8_t sirk[BT_CSIP_SIRK_SIZE];
};

int bt_csip_set_member_register(const bt_csip_set_member_register_param *parameters,
                                bt_csip_set_member_svc_inst **instance);
int bt_csip_set_member_unregister(bt_csip_set_member_svc_inst *instance);
int bt_csip_set_member_generate_rsi(bt_csip_set_member_svc_inst *instance,
                                    std::uint8_t rsi[BT_CSIP_RSI_SIZE]);
int bt_csip_set_member_sirk(bt_csip_set_member_svc_inst *instance,
                            const std::uint8_t sirk[BT_CSIP_SIRK_SIZE]);
int bt_csip_set_member_set_size_and_rank(bt_csip_set_member_svc_inst *instance,
                                         std::uint8_t size, std::uint8_t rank);
int bt_csip_set_member_get_info(const bt_csip_set_member_svc_inst *instance,
                                bt_csip_set_member_set_info *information);
int bt_csip_set_member_lock(bt_csip_set_member_svc_inst *instance, bool lock, bool force);

struct bt_csip_set_coordinator_set_info
{
    std::uint8_t sirk[BT_CSIP_SIRK_SIZE];
    std::uint8_t set_size;
    std::uint8_t rank;
    bool lockable;
};

struct bt_csip_set_coordinator_csis_inst
{
    bt_csip_set_coordinator_set_info info;
    void *svc_inst;
};

struct bt_csip_set_coordinator_set_member
{
    bt_csip_set_coordinator_csis_inst insts[1];
};

using bt_csip_set_coordinator_ordered_access_t =
    bool (*)(const bt_csip_set_coordinator_set_info *,
             bt_csip_set_coordinator_set_member *[], std::size_t);

struct bt_csip_set_coordinator_cb
{
    void (*discover)(bt_conn *, const bt_csip_set_coordinator_set_member *, int, std::size_t);
    void (*lock_set)(int);
    void (*release_set)(int);
    void (*lock_changed)(bt_csip_set_coordinator_csis_inst *, bool);
    void (*sirk_changed)(bt_csip_set_coordinator_csis_inst *);
    void (*size_changed)(bt_conn *, const bt_csip_set_coordinator_csis_inst *);
    void (*ordered_access)(const bt_csip_set_coordinator_set_info *, int, bool,
                           bt_csip_set_coordinator_set_member *);
};

int bt_csip_set_coordinator_register_cb(bt_csip_set_coordinator_cb *callbacks);
bool bt_csip_set_coordinator_is_set_member(const std::uint8_t sirk[BT_CSIP_SIRK_SIZE],
                                           const bt_data *data);
int bt_csip_set_coordinator_discover(bt_conn *connection);
bt_csip_set_coordinator_set_member *
bt_csip_set_coordinator_set_member_by_conn(const bt_conn *connection);
int bt_csip_set_coordinator_ordered_access(
    const bt_csip_set_coordinator_set_member *members[], std::uint8_t count,
    const bt_csip_set_coordinator_set_info *set_info,
    bt_csip_set_coordinator_ordered_access_t callback);
int bt_csip_set_coordinator_lock(const bt_csip_set_coordinator_set_member *members[],
                                 std::uint8_t count,
                                 const bt_csip_set_coordinator_set_info *set_info);
int bt_csip_set_coordinator_release(const bt_csip_set_coordinator_set_member *members[],
                                    std::uint8_t count,
                                    const bt_csip_set_coordinator_set_info *set_info);
