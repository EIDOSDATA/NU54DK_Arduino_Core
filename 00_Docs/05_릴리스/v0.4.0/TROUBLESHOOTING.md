# v0.4.0 Troubleshooting

## Boards Manager 설치는 끝났지만 prerequisite가 실패함

Arduino CLI가 platform을 목록에 등록한 뒤 post-install 실패를 warning으로만 표시할 수 있습니다.
설치 version만 확인하지 말고 로그의 `Nordic prerequisite installation PASS`와 prerequisite
`ready.json`을 함께 확인하십시오.

공식 nRF Util byte가 pin과 다르면 같은 명령을 반복하지 마십시오. binary version, SHA-256과
Authenticode 서명을 확보하고 릴리스에서 고정한 hash와 비교하십시오. 검토 없이 pin을 완화하거나
hash 검사를 끄지 않습니다.

## Profile 또는 library 충돌

`NUCODE Peripheral Fabric`이 `standard`/`ble`에서 `E_FEATURE_PROFILE`로 실패하면 의도된
fail-closed 동작입니다. `Tools → Feature set → Peripheral Fabric (DAP UART disconnected)`을
선택하십시오. 기존 singleton Sketch는 `standard`나 `ble`을 사용합니다.

## Handle은 있지만 통신이 안 됨

1. 올바른 instance와 승인 route를 선택했는지 확인합니다.
2. 공유 pin을 사용하면 해당 DAP UART switch 상태를 확인합니다.
3. 공통 GND, I/O 전압, controller/target 방향과 CS/SDA/SCL 조건을 확인합니다.
4. 같은 block personality·pin·event channel·DMA buffer의 다른 owner가 없는지 확인합니다.
5. `configure/acquire/start` 반환값과 `lastResult()/lastDriverError()`를 기록합니다.

## `stop_timeout` 또는 `faulted`

DMA 정지가 확인되지 않으면 Core는 lease를 유지해 재사용을 막습니다. 무한 재시도하지 말고
CMSIS-DAP로 peripheral event/error, DMA와 GPIO 레지스터를 확보하십시오. Reset 뒤에도 재현되면
exact source, profile, instance, route, 반환값과 snapshot을 함께 보고하십시오.

## TEMP·Watchdog·System OFF

TEMP/WDT30은 `fabric`, 기존 WDT31/System OFF는 `standard`/`ble`의 BoardSystem 경로를
사용합니다. Debugger halt는 watchdog 진행을, active SWD는 System OFF와 reset cause를 바꿀 수
있습니다. 전원 기능의 결과에는 debugger 상태를 함께 기록하십시오.

## QDEC20/21

연속 카운트에는 `QdecConfiguration::report_events=true`와 `takeEvent()`를 사용하십시오. 자동
report와 manual `read()`는 각각 누산기를 비우므로 같은 구간에 혼용하지 않습니다. 동작 중
반복 manual `read()/clear`의 무손실 누산은 보증하지 않습니다.
