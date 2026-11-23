#!/usr/bin/env python3
"""! @brief actual reset helper를 최소 SDK seam과 링크해 scheduling·파괴적 호출 경계를 검사합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable

ROOT = Path(__file__).resolve().parents[2]
MOCK = r"""
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define CONFIG_SYSTEM_WORKQUEUE_PRIORITY (-1)
#define BUILD_ASSERT(condition, message) _Static_assert(condition, message)
#define ARG_UNUSED(value) ((void)(value))
#define BT_CONN_TYPE_LE 1
#define BT_ID_DEFAULT 0
struct shell { int unused; };
struct bt_conn { int unused; };
struct k_work { void (*handler)(struct k_work *); };
struct k_work_delayable { int unused; };
typedef int atomic_t;
static inline bool atomic_cas(atomic_t *value, int expected, int next)
{
    if (*value != expected)
    {
        return false;
    }
    *value = next;
    return true;
}
static inline void atomic_clear(atomic_t *value)
{
    *value = 0;
}
#define K_WORK_DEFINE(name, callback) struct k_work name = {callback}
#define SHELL_CMD_ARG_REGISTER(...)
int k_work_submit(struct k_work *);
int k_work_cancel(struct k_work *);
int k_work_cancel_delayable(struct k_work_delayable *);
int bt_adv_helper_adv_stop(void);
bool bt_fast_pair_is_ready(void);
int bt_fast_pair_disable(void);
int bt_fast_pair_factory_reset(void);
int bt_unpair(int, const void *);
void bt_conn_foreach(int, void (*)(struct bt_conn *, void *), void *);
void shell_error(const struct shell *, const char *, ...);
void shell_print(const struct shell *, const char *, ...);
"""


class EcosystemResetTests(unittest.TestCase):
    """! @brief reset의 성공 출력 이전 실제 API·실행 context·승인 단계를 검사합니다. """

    def test_explicit_confirmation_and_cooperative_reset(self):
        """! @brief invalid·busy·not-ready·native 실패에서 storage 변경을 차단합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "mock_sdk.h").write_text(MOCK, encoding="utf-8")
            for name in ("bluetooth/fast_pair/fast_pair.h", "zephyr/bluetooth/bluetooth.h",
                         "zephyr/bluetooth/conn.h", "zephyr/shell/shell.h",
                         "zephyr/kernel.h", "zephyr/sys/atomic.h"):
                header = root / name
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text('#include "mock_sdk.h"\n', encoding="ascii")
            executable = root / "reset-test.exe"
            command = compiler_command("c") + ["-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I", str(root), "-I", str(ROOT / "libraries/NUCODE_BLE_Companion/templates"),
                str(ROOT / "tests/host/m33_ecosystem_reset_main.c"), "-o", str(executable)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = run_executable([str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
