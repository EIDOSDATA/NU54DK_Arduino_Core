/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) RadioEventTrigger scanner
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * EGU10 task와 interrupt는 application 소유이며 다른 DPPI·peripheral 사용과 충돌하지 않아야 합니다.
 * @par Metadata
 * identity `NUCODE_BLE/RadioEventTrigger`, sha256 `74f3fbbaa9b09cea7726126a15c813aadacae0f63eba377f7f77023941e3f2cb`
 * @nucode_example_setup_end */

/**
 * @file RadioEventTrigger.ino
 * @brief scanner radio event 시작에 caller 소유 EGU task를 결합합니다.
 */

#include <NUCODE_BLE.h>

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
#include <hal/nrf_egu.h>
#include <zephyr/devicetree.h>
#include <zephyr/irq.h>

#define NUCODE_EGU_NODE DT_NODELABEL(egu10)
#define NUCODE_EGU ((NRF_EGU_Type *)DT_REG_ADDR(NUCODE_EGU_NODE))

volatile std::uint32_t triggerCount = 0U;

/** @brief EGU event를 지우고 ISR-safe counter만 증가시킵니다. */
void onEguEvent(const void *context)
{
    static_cast<void>(context);
    nrf_egu_event_clear(NUCODE_EGU, NRF_EGU_EVENT_TRIGGERED0);
    ++triggerCount;
}

void setup()
{
    Serial.begin(115200);
    IRQ_CONNECT(DT_IRQN(NUCODE_EGU_NODE), 5, onEguEvent, nullptr, 0);
    nrf_egu_int_enable(NUCODE_EGU, NRF_EGU_INT_TRIGGERED0);
    irq_enable(DT_IRQN(NUCODE_EGU_NODE));
    const std::uint32_t taskAddress =
        nrf_egu_task_address_get(NUCODE_EGU, NRF_EGU_TASK_TRIGGER0);
    if (!BLEDevice.begin("NU54-EVENT") || !BLEScan.start(false) ||
        !BLENordic.setScannerEventTrigger(taskAddress))
    {
        Serial.println("Radio event trigger start failed");
    }
}

void loop()
{
    BLEDevice.poll();
    static std::uint32_t reported = 0U;
    const std::uint32_t current = triggerCount;
    if (current != reported)
    {
        reported = current;
        Serial.print("Scanner event triggers: ");
        Serial.println(reported);
    }
}

#endif // !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)
