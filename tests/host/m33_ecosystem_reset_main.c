/** @file @brief 실제 Fast Pair reset helper의 명시 승인·cooperative 실행·실패 경계를 검증합니다.
 * SPDX-License-Identifier: MIT
 */
#include "mock_sdk.h"
#include <assert.h>
#include <errno.h>
#include <string.h>

static bool companion_reset_locked;
static struct k_work bt_adv_restart;
static struct k_work_delayable fp_adv_mode_status_led_handle;
static struct k_work_delayable fp_disc_adv_timeout;
static struct k_work *queued;
static int cooperative;
static int live_connections;
static int fast_pair_ready = 1;
static int disable_error;
static int stop_error;
static int submit_error;
static unsigned stopped;
static unsigned cancelled;
static unsigned disabled;
static unsigned resets;
static unsigned unpairs;
static unsigned errors;

/** @brief 원본 main의 광고 정지와 work 취소를 관측합니다. */
int bt_adv_helper_adv_stop(void)
{
    assert(cooperative == 1);
    ++stopped;
    return stop_error;
}

#include "fast_pair_reset_guard.h"
#include "fast_pair_reset.c"

/** @brief shell에서 호출한 work는 바로 실행하지 않고 queue에 넣습니다. */
int k_work_submit(struct k_work *work)
{
    assert(cooperative == 0);
    if (submit_error != 0)
    {
        return submit_error;
    }
    queued = work;
    return 1;
}

int k_work_cancel(struct k_work *work)
{
    assert(work == &bt_adv_restart && cooperative == 1);
    ++cancelled;
    return 0;
}

int k_work_cancel_delayable(struct k_work_delayable *work)
{
    assert((work == &fp_adv_mode_status_led_handle || work == &fp_disc_adv_timeout) &&
           cooperative == 1);
    ++cancelled;
    return 0;
}

bool bt_fast_pair_is_ready(void)
{
    return fast_pair_ready != 0;
}

int bt_fast_pair_disable(void)
{
    assert(cooperative == 1 && companion_reset_locked && stopped != 0 && cancelled == 3);
    ++disabled;
    return disable_error;
}

int bt_fast_pair_factory_reset(void)
{
    assert(cooperative == 1 && disabled != 0);
    ++resets;
    return 0;
}

int bt_unpair(int identity, const void *address)
{
    assert(cooperative == 1 && identity == BT_ID_DEFAULT && address == NULL && resets != 0);
    ++unpairs;
    return 0;
}

void bt_conn_foreach(int type, void (*callback)(struct bt_conn *, void *), void *context)
{
    assert(type == BT_CONN_TYPE_LE && cooperative == 1);
    for (int index = 0; index < live_connections; ++index)
    {
        struct bt_conn connection = {0};
        callback(&connection, context);
    }
}

void shell_error(const struct shell *shell, const char *format, ...)
{
    assert(shell != NULL && format != NULL);
    ++errors;
}

void shell_print(const struct shell *shell, const char *format, ...)
{
    assert(shell != NULL && format != NULL);
}

/** @brief test가 cooperative scheduler를 명시적으로 전진시킵니다. */
static void run_queued(void)
{
    assert(queued != NULL);
    struct k_work *work = queued;
    queued = NULL;
    cooperative = 1;
    work->handler(work);
    cooperative = 0;
}

int main(void)
{
    struct shell terminal = {0};
    char command[] = "companion_keys_reset";
    char confirmation[] = "CONFIRM";
    char invalid[] = "confirm";
    char *valid[] = {command, confirmation};
    char *wrong[] = {command, invalid};
    assert(reset_keys(&terminal, 1, valid) == -EINVAL);
    assert(reset_keys(&terminal, 2, wrong) == -EINVAL);
    assert(queued == NULL && resets == 0 && errors == 2);

    live_connections = 1;
    assert(reset_keys(&terminal, 2, valid) == 0);
    assert(reset_keys(&terminal, 2, valid) == -EBUSY);
    assert(resets == 0 && disabled == 0);
    run_queued();
    assert(resets == 0 && disabled == 0 && errors == 3);

    live_connections = 0;
    fast_pair_ready = 0;
    assert(reset_keys(&terminal, 2, valid) == 0);
    run_queued();
    assert(resets == 0 && errors == 4);

    fast_pair_ready = 1;
    assert(reset_keys(&terminal, 2, valid) == 0);
    run_queued();
    assert(resets == 1 && unpairs == 1 && disabled == 1 && errors == 4);
    assert(companion_reset_locked && stopped == 1 && cancelled == 3);

    cancelled = 0;
    disable_error = -EIO;
    assert(reset_keys(&terminal, 2, valid) == 0);
    run_queued();
    assert(resets == 1 && unpairs == 1 && errors == 5);

    stop_error = -EIO;
    assert(reset_keys(&terminal, 2, valid) == 0);
    run_queued();
    assert(resets == 1 && unpairs == 1 && disabled == 2 && errors == 6);

    submit_error = -EIO;
    assert(reset_keys(&terminal, 2, valid) == -EIO);
    assert(reset_pending == 0 && queued == NULL && resets == 1);
    return 0;
}
