# R10 Serial Fabric 동시 호출과 orchestration 분리

상태: 진행 중. 시작 commit `1c956b7227c381aeaa6043627b9244b7b5d080a3`.
T14의 동시성 수정·구조 회귀이며 current-source T11은 실행하지 않는다.

## 구현 전 책임 대응표

| 기존 책임 | 분리할 위치 | 상태·동기화 |
| --- | --- | --- |
| SerialFabric.cpp factory·handle 조회 | 기존 파일 | 공개 singleton·handle index·enum·factory 경로 유지 |
| 고정 context/adapter/block table·register·IRQ 연결/dispatch | `internal/serial/SerialFabricRegistry.cpp` | table과 mutex 단일 소유, 작은 내부 accessor; IRQ atomic pointer 유지 |
| stage/activate/deactivate·lease·pin/constant-latency 복구 | `internal/serial/SerialFabricLifecycle.cpp` | 공통 mutex 안에서 상태 전환, 긴 STOP 확인은 block 예약 후 잠금 밖에서 대기 |
| 내부 context와 순수 index 변환 | `internal/serial/SerialFabricInternal.h` | private 구현 전용; mutable extern 및 새 public API 없음 |
| Uarte/Spim/Spis/Twim/TwisFabric.cpp | 기존 5개 adapter 유지 | 각각의 queue·DMA·generation·terminal/waiter 계약 보존 |
| `SerialFabricBackend.h`의 operation guard | 기존 계약 유지·필요한 내부 예약 경계만 보완 | ISR 거부, 같은 handle stop/cancel/submit 교차 거부, 다른 block 진행 |
| CMake·package·Host runner | 기존 feature 조건과 진입점 유지 | 분리 source 각각 한 번 등록; 명시적 source 목록도 조사 |

R10-A에서 실제 Host thread로 긴 stop 대기가 전역 mutex를 점유하는 것을 먼저 재현하고
동시 호출 정책을 수정한다. R10-B에서 검증한 동작을 보존하며 파일을 분리한다.
긴 대기를 열어 둘 때 state/adapter/lease가 교체되지 않도록 block 예약과 lifecycle을
함께 검사한다. 실패한 STOP은 필요한 DMA·pin·전원 lease 및 fault를 유지한다.
nrfx adapter의 짧은 IRQ critical section과 실제 장치의 STOP 제한을 약화하지 않는다.

직접 nrfx Serial Fabric과 Arduino device backend의 Kconfig 상호 배제는 그대로 유지한다.
Host mock과 target build는 물리 STOP, 전기적 파형, 실기 동시성 PASS를 뜻하지 않는다.
향후 HIL 결과의 synchronous/asynchronous scope label도 실제 선택한 스타일과 맞춘다.
이미 저장된 역사적 HIL 원시 기록은 수정하지 않는다.

R10-A 검토 중 adapter activate 실패 뒤 rollback도 실패하면 `context.lease`를 먼저
비우는 경로를 확인했다. 이 분기 역시 성공한 rollback 뒤에만 lease/staged 상태를
정리하도록 보완하고 기존 fault/재사용 거부 검사를 확장한다.

## R10-A 잠금 규칙

1. stage/activate/deactivate와 adapter 제출·취소는 기존 fabric mutex에서 상태를 검사한다.
2. deactivate는 cancelling, commit 실패의 복구는 activating 상태를 유지한다.
3. `request_stop`의 짧은 driver critical section 뒤 block에 wait generation을 예약한다.
   adapter pointer와 lease를 고정한 채 fabric mutex를 놓고 STOP predicate만 기다린다.
4. 대기 중 같은 block의 stage/activate/deactivate/recovery는 wrong_state다. 같은 handle의
   adapter 취소도 active 검사에서 거부한다. 다른 block의 별도 lease는 진행할 수 있다.
5. mutex를 다시 얻으면 generation·adapter·phase를 확인한 뒤 reservation을 닫는다.
   STOP 실패는 fault를 고정하고 lease를 보존한다. 성공하면 기존 순서대로 driver 종료,
   IRQ 연결 제거, pin·constant-latency 복구, lease 반환을 수행한다.

lock 순서는 fabric mutex → 자원 manager mutex 또는 driver의 짧은 IRQ/spinlock이다.
긴 STOP 확인 구간에는 fabric/resource mutex가 없다. 정지 확인이 끝나기 전까지 context
재등록·test reset으로 adapter를 교체하지 않는다. SPIM의 기존 100 us raw STOPPED 확인과
IRQ critical section은 유지한다. 그 구간의 IRQ 허용 또는 latency 개선을 주장하지 않는다.

Host의 1초 관찰창은 throughput 측정이 아니라, 제어된 STOP 미완료 구간에 다른 호출이
끝나는지를 판별하는 watchdog이다. 27 us timeout은 fake busy-wait budget의 검증이다.
초기 6개 중 5개가 막혔고 수정 뒤 6개 모두 완료됐다. 실제 hardware elapsed time은 측정하지 않았다.

## R10-A 결과

| 검사 | 결과 |
| --- | --- |
| production lifecycle·manager 동시성 6개 | 이전 5 FAIL/1 PASS → 수정 뒤 6 PASS |
| 기존 SPIM/TWIM production nrfx mock | 24개 시나리오 PASS |
| 기존 lifecycle/route/fixture Host | 3/3 PASS; activate/rollback 동시 실패의 fault 거부 추가 |
| 전체 Host | 621개 중 619 PASS·2 조건부 SKIP |
| contract / inventory / style | 45/45 / PASS / C/C++/ino 294개 PASS |
| target | Serial lifecycle·UARTE·SPI·TWI·DUT/peer 6/6 build-only PASS(214.14초) |

실제 Host thread의 교차 호출은 STOP 미완료 상태에서 IRQ dispatch·lease 보존, 같은
handle/block 거부, 다른 block 활성화, timeout·driver 실패 뒤 fault 유지까지 확인했다.
취소 함수의 active guard를 다섯 adapter에 적용했다. SPIM 100 us raw STOPPED critical
section은 유지하며 긴 lifecycle STOP 확인에서만 전역 mutex를 해제한다.

[software·source](evidence/r10a-1c956b7/software-and-source.json),
[target](evidence/r10a-1c956b7/target-build.json),
[기준선 실패](evidence/r10a-1c956b7/before.txt),
[수정 후](evidence/r10a-1c956b7/after-initial.txt)에 연결한다.
R10-A 완료는 R10 전체 완료가 아니다. 다음 R10-B에서 registry·IRQ·lifecycle을 분리하고
동일 Host 및 선택/비선택 target를 재검증한다. 공개 header·Kconfig 상호 배제는 유지한다.

## R10-B 구조 분리 결과

factory, 단일 registry·IRQ, lifecycle·복구를 책임 대응표대로 분리했다. 긴 STOP 대기의
예약·mutex 해제/재획득 순서를 포함한 38개 본문은 accessor 치환과 정렬 외 동일하다.
공개 `SerialFabric.h`, 내부 backend 계약 및 5개 adapter의 byte도 동일하다.
Host 명시적 source 목록과 M24 계약 검사기의 backend 경로를 갱신했다.
처음 전체 Host는 옛 단일 파일에서만 lease 함수를 찾는 검사기로 실패했고, 분리된 필수
파일을 모두 요구하도록 수정한 뒤 전체 Host가 619 PASS/2 SKIP다.

| 검사 | 결과 |
| --- | --- |
| 동시성 / SPIM·TWIM production | 6 / 24개 PASS |
| contract / inventory / style | 45/45 / PASS / 297개 PASS |
| 선택/비선택 조합·DUT/peer | 9/9 build-only PASS, 326.84초 |
| source 소속 | 공통 3개 각 1회, 각 personality의 미선택 adapter 0회 |
| pair DUT flash / RAM | 184,016 → 183,824 B / 161,496 B 동일 |
| 정적 객체 / 공개 method symbol | context 27,416 B·block 80 B·adapter 552 B·등록 23 B·mutex 20 B 동일, 제거 없음 |

`r01.none`은 공통 Serial Fabric은 켜고 5개 personality만 끈 구성이다. 따라서 공통
3개 source는 포함되며 adapter가 0개다. 실제 함수 분리의 flash 변화만 기록하며
실기 성능·IRQ latency 개선은 주장하지 않는다. 모든 Host와 target은 물리 I/O 없이 실행했다.

[software·source](evidence/r10b-7be9f71/software-and-source.json),
[본문·header](evidence/r10b-7be9f71/comparison.json),
[target](evidence/r10b-7be9f71/target-build.json),
[메모리·symbol·소속](evidence/r10b-7be9f71/target-comparison.json)에 증거를 둔다.
다음 R10-C는 향후 HIL 결과의 synchronous scope metadata만 교정한다. 역사적 raw evidence는 유지한다.
