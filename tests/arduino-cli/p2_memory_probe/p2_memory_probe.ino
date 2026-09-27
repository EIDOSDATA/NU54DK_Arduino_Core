/**
 * @file p2_memory_probe.ino
 * @brief P2 Arduino 계측 이미지의 stack/heap API 빌드 가능성을 확인합니다.
 */

#include <Arduino.h>

#if !defined(NUCODE_CAPABILITY_PROBE) && !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include <zephyr/kernel.h>
#include <zephyr/debug/thread_analyzer.h>
#include <sys_malloc.h>

/** @brief Thread analyzer의 stack high-water를 직렬 출력으로 전달합니다. */
void reportThread(struct thread_analyzer_info *info)
{
    Serial.print("P2_STACK name=");
    Serial.print(info->name);
    Serial.print(" reserved=");
    Serial.print(static_cast<unsigned long>(info->stack_size));
    Serial.print(" used=");
    Serial.println(static_cast<unsigned long>(info->stack_used));
}
#endif

/** @brief 계측 구성을 초기화합니다. */
void setup()
{
    Serial.begin(115200);
    Serial.println("P2_BASE_READY");
}

/** @brief 5초 간격으로 thread stack과 malloc heap을 계측합니다. */
void loop()
{
#if !defined(NUCODE_CAPABILITY_PROBE) && !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
    struct sys_memory_stats stats = {};
    thread_analyzer_run(reportThread, 0U);
    if (malloc_runtime_stats_get(&stats) == 0)
    {
        Serial.print("P2_MALLOC free=");
        Serial.print(static_cast<unsigned long>(stats.free_bytes));
        Serial.print(" allocated=");
        Serial.print(static_cast<unsigned long>(stats.allocated_bytes));
        Serial.print(" peak=");
        Serial.println(static_cast<unsigned long>(stats.max_allocated_bytes));
    }
#endif
    delay(5000);
}
