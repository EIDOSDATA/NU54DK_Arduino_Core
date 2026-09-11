# v0.4.0-rc.1 Troubleshooting — 비공개 후보

## Profile 또는 library 충돌

`NUCODE Peripheral Fabric`이 `standard`/`ble`에서 `E_FEATURE_PROFILE`로 실패하면 의도된
fail-closed 동작입니다. `Tools → Feature set → Peripheral Fabric (DAP UART disconnected)`를
선택하십시오. 반대로 기존 singleton Sketch는 `standard`나 `ble`을 사용하십시오.

## Handle은 있지만 통신이 안 됨

Factory 조회는 hardware를 시작하지 않습니다. 다음을 순서대로 확인하십시오.

1. 올바른 instance와 승인 route를 선택했는지 확인합니다.
2. P0/P1 DAP UART 공유 핀이라면 해당 DAP UART switch가 실제로 꺼져 있는지 확인합니다.
3. 공통 GND, I/O 전압, controller/target 방향과 CS/SDA/SCL 조건을 확인합니다.
4. 같은 block personality·pin·event channel·DMA buffer를 다른 handle이 소유하지 않는지 확인합니다.
5. `configure/acquire/start` 반환값과 `lastResult()/lastDriverError()`를 기록합니다.

## `ownership_conflict`

같은 serial block의 UARTE·SPIM/SPIS·TWIM/TWIS, 같은 PWM instance, 같은 GPIOTE/DPPI/TIMER channel,
겹치는 DMA RAM은 동시에 활성화할 수 없습니다. 이전 handle의 bounded `stop/release`를 완료하고
핀과 buffer 반환을 확인한 뒤 재시도하십시오. 충돌 검사를 우회하는 raw register 접근은 지원하지
않습니다.

## `stop_timeout` 또는 `faulted`

DMA가 실제로 정지했음이 확인되지 않으면 Core는 lease를 유지해 재사용을 막습니다. 같은 명령을
무한 반복하지 말고 peripheral error/event 상태와 nRF54L15 레지스터를 CMSIS-DAP로 확보하십시오.
Reset 뒤에도 재현되면 exact source, profile, instance, route, 반환값과 레지스터 snapshot을 함께
보고하십시오.

## TEMP·Watchdog·System OFF

TEMP/WDT30은 `fabric`, 기존 WDT31/System OFF는 `standard`/`ble`의 BoardSystem 경로를 따릅니다.
Debugger halt 설정은 watchdog 진행을, active SWD debug는 System OFF와 reset cause를 바꿀 수
있습니다. 전원 기능을 진단할 때 debugger 영향 여부를 결과와 함께 기록하십시오.

## QDEC20/21

연속 카운트에는 `QdecConfiguration::report_events=true`와 `takeEvent()`를 사용하십시오. 자동
report와 manual `read()`는 각각 누산기를 비우므로 같은 구간에 혼용하지 않습니다. 동작 중
반복 manual `read()/clear`의 무손실 누산은 보증하지 않습니다.
