/** @file @brief Fast Pair input template의 명시적 사용자 account-key 삭제 명령입니다.
 * SPDX-License-Identifier: MIT
 */
#include <bluetooth/fast_pair/fast_pair.h>
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/shell/shell.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>
#include <string.h>
#include <errno.h>

BUILD_ASSERT(CONFIG_SYSTEM_WORKQUEUE_PRIORITY < 0,
             "Fast Pair reset requires cooperative workqueue");
static atomic_t reset_pending;
static const struct shell *reset_shell;
/** @brief 생성된 main이 광고·timeout·버튼 재시작을 닫는 내부 함수입니다. */
extern int companion_reset_prepare(void);

/** @brief 연결이 남아 있으면 factory reset을 거부하기 위한 callback입니다. */
static void count_connection(struct bt_conn *connection, void *context)
{
    unsigned int *count = context;
    ARG_UNUSED(connection);
    ++(*count);
}

/** @brief 사용자의 정확한 확인 문자열을 받고 account key·bond만 초기화합니다. */
static void reset_work_handler(struct k_work *work)
{
    ARG_UNUSED(work);
    const struct shell *shell = reset_shell;
    unsigned int connections = 0;
    bt_conn_foreach(BT_CONN_TYPE_LE, count_connection, &connections);
    if (connections != 0 || !bt_fast_pair_is_ready())
    {
        shell_error(shell, "Reset rejected: disconnect all peers and wait for Fast Pair ready");
        atomic_clear(&reset_pending);
        return;
    }
    int result = companion_reset_prepare();
    if (result == 0)
    {
        result = bt_fast_pair_disable();
    }
    if (result == 0)
    {
        result = bt_fast_pair_factory_reset();
    }
    if (result == 0)
    {
        result = bt_unpair(BT_ID_DEFAULT, NULL);
    }
    if (result != 0)
    {
        shell_error(shell, "Reset failed: %d; check radio state and restart explicitly", result);
    }
    else
    {
        shell_print(shell, "Account keys and bonds cleared; restart explicitly");
    }
    atomic_clear(&reset_pending);
}

K_WORK_DEFINE(reset_work, reset_work_handler);

/** @brief 정확한 사용자 확인 후 cooperative context에 요청만 전달합니다. */
static int reset_keys(const struct shell *shell, size_t argc, char **argv)
{
    if (argc != 2 || strcmp(argv[1], "CONFIRM") != 0)
    {
        shell_error(shell, "Use: companion_keys_reset CONFIRM (deletes account keys and bonds)");
        return -EINVAL;
    }
    if (!atomic_cas(&reset_pending, 0, 1))
    {
        return -EBUSY;
    }
    reset_shell = shell;
    const int result = k_work_submit(&reset_work);
    if (result < 0)
    {
        atomic_clear(&reset_pending);
        return result;
    }
    shell_print(shell, "Reset queued; wait for explicit result");
    return 0;
}

SHELL_CMD_ARG_REGISTER(companion_keys_reset, NULL,
                       "Delete Fast Pair account keys and bonds after explicit confirmation",
                       reset_keys, 2, 0);
