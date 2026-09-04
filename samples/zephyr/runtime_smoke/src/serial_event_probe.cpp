/**
 * @file serial_event_probe.cpp
 * @brief ArduinoCore-API weak 선언과 분리된 강한 serialEventRun 시험 symbol입니다.
 *
 * SPDX-License-Identifier: MIT
 */

extern "C" void nu54M2SerialEventProbe(void);

namespace arduino
{

    /** @brief 각 loop() 반환 뒤 runtime smoke 순서 검증 본체를 호출합니다. */
    void serialEventRun(void)
    {
        nu54M2SerialEventProbe();
    }

} // namespace arduino
