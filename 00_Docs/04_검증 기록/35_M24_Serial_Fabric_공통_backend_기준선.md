# M24 Serial Fabric 공통 backend 기준선

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VERIFY-M24-SERIAL-FABRIC-002 |
| 기록일 | 2026-09-03 |
| 제품선 | `v0.4.0` M24 작업 2 |
| Core 구현 commit | `9680a56de3ffa8a56a4ff7f39894bd93e5f343af` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 판정 | **M24 작업 2 PASS / 작업 3 착수 가능** |
| 작성자 | Quantum / NUCODE |

## 1. 판정

M24 작업 2는 작업 1의 5개 serial block·23개 personality 계약을 소비하는 공통 실행 기반을
구현했다. `<nucode/SerialFabric.h>`는 UARTE/SPIM/SPIS 00·20·21·22·30과 TWIM/TWIS
20·21·22·30을 실제 identity별 typed handle로 선택한다. 생성자와 selector는 hardware를 켜거나
동적 메모리를 할당하지 않는다.

이 판정은 **공통 lifecycle과 의미 검증 완료**다. 실제 UARTE/SPIM/SPIS/TWIM/TWIS adapter와
데이터 전송 API, 물리 data-path HIL은 작업 3~6의 범위다. Kconfig 기본값은 off이며 이 header를
`v0.3.0` stable 또는 `v0.4.0` 공개 지원으로 승격하지 않았다.

## 2. 구현한 계약

- `stage()`는 inactive/staged에서만 route, 전기 profile, pin과 DMA workspace를 검증한다.
- `activate()`는 serial block, IRQ, pin, 필요한 power domain과 모든 DMA RAM range를 하나의
  lease로 reserve하고 driver 성공 뒤 commit한다.
- 같은 block의 다른 personality와 겹치는 DMA range는 register 변경 전에 거부한다.
- Driver 활성화 실패는 전체 lease를 rollback하며 부분 owner를 남기지 않는다.
- `deactivate()`는 bounded stop을 확인한 뒤 driver와 자원을 해제한다.
- 정지 또는 복원을 증명하지 못하면 해당 physical block 전체를 reset 전까지 fail-closed로 latch한다.
- NU54DK validator는 P2 dedicated20, P1/P0 flexible route, DAP UART와 PMIC I2C의 전기 정책,
  미승인 pin과 P2 dedicated21 경로를 실행 시점에 검사한다.

## 3. 실행한 gate

| Gate | 결과 |
| --- | --- |
| `python tools/peripheral/verify_m24_serial_contract.py --ncs-root C:\\ncs\\v3.4.0` | PASS, 5 block / 23 identity / 23 profile |
| `python -m unittest -v tests.host.test_m24_serial_contract` | 11/11 PASS |
| `python tools/ci/run_m12_gate.py contract` | 42/42 PASS |
| `python tools/ci/run_m12_gate.py host` | PASS |
| `west twister ... tests/zephyr/m24_serial_fabric_contract --build-only` | 1/1 PASS, warning 0 |
| M24 semantic image link | PASS, FLASH 98,844 B / RAM 52,600 B |
| 신규 physical data-path HIL | **NOT RUN — 작업 3~5 driver 구현 전** |

Target semantic suite는 exact factory identity, adapter 미등록 거부, route/electrical negative,
같은 block 충돌과 순차 handover, 다른 block 동시 활성, DMA range overlap, driver 실패 rollback과
bounded-stop fault latch를 실제 nRF54L15 target configuration으로 compile·link한다.

## 4. CI와 공개 경계

`v0.4.0` Zephyr build group에 `nucode.m24.fabric`을 추가해 Linux/Windows 재현 build가 공통
backend를 계속 검사한다. Contract verifier는 header, backend, route validator의 필수 source와
소유권 lifecycle primitive를 fail-closed로 확인한다.

기존 `Serial`, `Serial1`, `Wire`, `SPI` identity와 `v0.3.0` package/Release 자산은 변경하지 않았다.
M23 manifest의 신규 19개 personality는 driver와 물리 gate 전까지 `absent`/`none`/`not_run`을
유지한다.

## 5. 다음 단계

작업 3은 다섯 UARTE identity의 실제 adapter, async RX/TX DMA buffer 상태, backpressure,
cancel·restart와 errata 7을 구현한다. 이후 SPIM/SPIS, TWIM/TWIS adapter와 보드 자체 HIL을
순서대로 연결한다.
