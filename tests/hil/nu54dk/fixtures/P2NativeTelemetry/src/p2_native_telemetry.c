/**
 * @file p2_native_telemetry.c
 * @brief Nordic native 비교 image에 P2 stack/heap 계측 비용을 포함합니다.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include <stddef.h>
#include <sys_malloc.h>

#include <zephyr/kernel.h>
#include <zephyr/debug/thread_analyzer.h>
#include <zephyr/init.h>
#include <zephyr/sys/printk.h>

/** @brief 각 native thread의 예약량과 최고 사용량을 출력합니다. */
static void report_thread(struct thread_analyzer_info *info)
{
    printk("P2_STACK name=%s reserved=%zu used=%zu\n",
           info->name, info->stack_size, info->stack_used);
}

/** @brief 비교 image의 stack 및 libc/kernel heap 계측 경로를 link합니다. */
static int report_native_memory(void)
{
    struct sys_memory_stats stats = {0};
    struct k_heap *heaps = NULL;
    int count;

    printk("P2_PHASE name=native-ready\n");
    thread_analyzer_run(report_thread, 0U);
    if (malloc_runtime_stats_get(&stats) == 0)
    {
        printk("P2_MALLOC free=%zu allocated=%zu peak=%zu\n",
               stats.free_bytes, stats.allocated_bytes, stats.max_allocated_bytes);
    }
    count = k_heap_array_get(&heaps);
    for (int index = 0; index < count; ++index)
    {
        if (sys_heap_runtime_stats_get(&heaps[index].heap, &stats) == 0)
        {
            printk("P2_KHEAP index=%d free=%zu allocated=%zu peak=%zu\n",
                   index, stats.free_bytes, stats.allocated_bytes,
                   stats.max_allocated_bytes);
        }
    }
    return 0;
}

SYS_INIT(report_native_memory, APPLICATION, CONFIG_APPLICATION_INIT_PRIORITY);
