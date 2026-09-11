# v0.3.0에서 v0.4.0으로 이동

기존 Sketch는 `standard` 또는 `ble` profile을 계속 사용하면 됩니다. 기존 singleton API를 직접
Fabric API로 바꾸지 않아도 됩니다.

## 직접 instance API 사용

전 peripheral instance나 비동기 DMA가 필요한 Sketch만
`Peripheral Fabric (DAP UART disconnected)`을 선택하고 다음 header를 포함합니다.

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

Factory가 handle을 반환해도 hardware나 pin은 자동으로 활성화되지 않습니다.
`configure/acquire/start` 순서, DMA buffer 수명과 `stop/release` 결과를 확인하십시오. 같은 serial
block의 다른 personality, 같은 pin·event channel 또는 겹치는 DMA RAM은 동시에 소유할 수
없습니다.

## 보드 조건

P0.0~P0.3 또는 P1.4~P1.7을 직접 peripheral route로 사용할 때는 공유 DAP UART switch를
끄고 공통 GND·I/O 전압을 확인하십시오. SWD debug는 유지할 수 있지만 active debugger는
watchdog halt, System OFF와 reset cause 관측에 영향을 줄 수 있습니다.

QDEC20/21 capability는 `supported`입니다. 연속 카운트에는 기본 `report_events=true`와
`takeEvent()`를 사용하십시오. 동작 중 반복 manual `read()`는 누산기를 read/clear하므로 무손실
누산을 보증하지 않으며 자동 report와 같은 구간에 혼용하지 마십시오.
