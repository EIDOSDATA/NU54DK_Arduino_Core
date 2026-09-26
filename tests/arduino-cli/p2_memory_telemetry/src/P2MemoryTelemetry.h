/**
 * @file P2MemoryTelemetry.h
 * @brief P2 시험 image의 thread stack과 heap 사용량을 보고합니다.
 * @note 공개 Arduino library가 아닌 tests 전용 헤더입니다.
 */

#ifndef NUCODE_P2_MEMORY_TELEMETRY_H
#define NUCODE_P2_MEMORY_TELEMETRY_H

#include <Arduino.h>

#if !defined(NUCODE_CAPABILITY_PROBE) && !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include <zephyr/kernel.h>
#include <zephyr/debug/thread_analyzer.h>
#include <sys_malloc.h>

namespace nucode::test
{
    /** @brief 각 Zephyr thread와 ISR stack의 최대 관찰 사용량을 출력합니다. */
    inline void reportThread(struct thread_analyzer_info *info)
    {
        Serial.print("P2_STACK name=");
        Serial.print(info->name);
        Serial.print(" reserved=");
        Serial.print(static_cast<unsigned long>(info->stack_size));
        Serial.print(" used=");
        Serial.println(static_cast<unsigned long>(info->stack_used));
    }

    /** @brief 현재 phase의 stack 및 libc/kernel heap 누적 통계를 출력합니다. */
    inline void reportMemory(const char *phase)
    {
        Serial.print("P2_PHASE name=");
        Serial.println(phase);
        thread_analyzer_run(reportThread, 0U);

        struct sys_memory_stats stats = {};
        if (malloc_runtime_stats_get(&stats) == 0)
        {
            Serial.print("P2_MALLOC free=");
            Serial.print(static_cast<unsigned long>(stats.free_bytes));
            Serial.print(" allocated=");
            Serial.print(static_cast<unsigned long>(stats.allocated_bytes));
            Serial.print(" peak=");
            Serial.println(static_cast<unsigned long>(stats.max_allocated_bytes));
        }

        struct k_heap *heaps = nullptr;
        const int count = k_heap_array_get(&heaps);
        for (int index = 0; index < count; ++index)
        {
            if (sys_heap_runtime_stats_get(&heaps[index].heap, &stats) == 0)
            {
                Serial.print("P2_KHEAP index=");
                Serial.print(index);
                Serial.print(" free=");
                Serial.print(static_cast<unsigned long>(stats.free_bytes));
                Serial.print(" allocated=");
                Serial.print(static_cast<unsigned long>(stats.allocated_bytes));
                Serial.print(" peak=");
                Serial.println(static_cast<unsigned long>(stats.max_allocated_bytes));
            }
        }
    }
}

#else
namespace nucode::test
{
    /** @brief Capability probe에서는 Zephyr-only 계측을 제외합니다. */
    inline void reportMemory(const char *phase)
    {
        static_cast<void>(phase);
    }
}
#endif

#endif
