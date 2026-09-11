# v0.3.0에서 v0.4.0 후보로 이동

v0.3.0 Sketch는 기본적으로 `standard` 또는 `ble` profile을 계속 사용합니다. 기존 singleton API를
직접 Fabric API로 바꿀 필요는 없습니다. 전 peripheral instance나 비동기 DMA가 필요한 Sketch만
새 `fabric` profile로 분리하십시오.

## Profile 선택

| 목적 | Feature set |
| --- | --- |
| 기존 GPIO·Serial·Wire·SPI·ADC·PWM·Storage | `Standard peripherals` |
| BLE와 해당 library | `BLE NUS` |
| 직접 Serial/Analog/Event/Stream/System Fabric | `Peripheral Fabric (DAP UART disconnected)` |

`fabric`은 기존 `Serial`, `Serial1`, `Wire`, `SPI`, ADC/PWM singleton backend를 끄고 직접 IRQ·DMA
소유권을 사용합니다. 한 Sketch에서 profile을 섞거나 raw Kconfig로 양쪽을 강제 활성화하지 마십시오.

## Sketch 변경

```cpp
#include <NUCODE_Peripheral_Fabric.h>

using namespace nucode::arduino;

void setup()
{
    auto *uart = serialFabric().uarte(21U);
    if (uart == nullptr)
    {
        return;
    }
}

void loop()
{
}
```

Factory가 handle을 반환하는 것만으로 hardware나 pin이 활성화되지는 않습니다. 각 API의
`configure/acquire/start` 순서, DMA buffer 수명과 `stop/release` 결과를 확인하십시오. 같은 serial
block의 personality, 같은 pin, event channel 또는 겹치는 DMA RAM은 동시에 소유할 수 없습니다.

## 하드웨어 전환 주의

P0.0~P0.3 또는 P1.4~P1.7을 DAP UART가 아닌 직접 peripheral route로 사용할 때는 보드의 해당
DAP UART switch를 끄고 공통 GND·I/O 전압을 확인해야 합니다. SWD debug 연결은 유지할 수 있지만
active debugger는 watchdog halt·System OFF·reset cause 관측에 영향을 줄 수 있습니다.

QDEC20/21 capability는 `supported`입니다. 연속 카운트에는 기본 `report_events=true`와
`takeEvent()`를 사용하십시오. 동작 중 반복 manual `read()`는 누산기를 read/clear하므로 무손실
누산을 보증하지 않으며 자동 report와 같은 구간에 혼용하지 마십시오.
