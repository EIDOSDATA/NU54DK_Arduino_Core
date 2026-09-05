# R02 — Serial 완료·timeout·DMA 수명주기

2026-09-06, 시작 source `eed0b6c`. 종료 commit은 이 문서의 최초 commit으로 식별한다.
Host/fault injection과 target 회귀를 완료했다. 다음 작업은 R03 Analog/Stream의 ISR·stop 동기화다.

## 교정한 계약

동기 SPIM/TWIM은 자신의 제출 generation의 terminal 기록을 기다린다. 공개 `takeEvent()` queue는
사용자가 소비하며 동기 함수와 경쟁하지 않는다. 이전 완료, 같은 buffer 주소, queue overflow,
다른 소비자의 dequeue는 현재 제출을 완료시키지 않는다. callback 완료 뒤에도 동기 waiter가 결과를
읽을 때까지 다음 제출은 `wrong_state`로 거부한다. generation wrap은 진행 중인 waiter 예약과
terminal 유효 상태로 구분한다. 공개 enum·event layout·함수 signature는 유지한다.

| 공유 항목 | writer / reader | 동기화 |
| --- | --- | --- |
| lifecycle state·route·adapter 설정 | thread lifecycle / thread 제출 | 기존 fabric mutex와 내부 operation guard |
| 제출 descriptor·활성 예약 | 제출 thread / nrfx IRQ | thread guard → 짧은 IRQ 금지 → context spinlock |
| buffer 상태·완료 generation·terminal 결과 | callback/취소 / waiter·조회 | 같은 context spinlock |
| 공개 event queue | callback·취소 / 사용자 | 같은 context spinlock, 기존 용량 8·overflow 우선 보고 |
| 동기 waiter 예약 | 동기 thread / 제출·activation | context spinlock, 완료 대기에는 fabric mutex를 보유하지 않음 |

UARTE/SPIS/TWIS의 configure·submit·cancel에도 같은 thread guard를 적용해 state 확인과 driver 호출
사이에 lifecycle이 route를 반환하지 못하게 한다. IRQ는 fabric mutex를 획득하지 않는다.
전역 lifecycle의 stop 대기 범위는 R10에서 별도 축소·검증할 항목이다.

시간은 최대 10 us씩 남은 예산을 차감한다. 마지막 1~9 us와 `UINT32_MAX`도 wrap 없이 처리하며
마지막 대기 직후 terminal을 다시 확인한다. 이는 요청한 busy-wait 예산이며 스케줄러 선점 시간까지
포함한 정밀 wall-clock SLA는 아니다.

timeout 반환만으로 buffer를 재사용하면 안 된다. `bufferState()`의 반환과 정지/해제 성공을 확인한다.
TWIM 취소는 STOP 요청이며, pinned nrfx가 STOP과 pending IRQ 처리를 마친 terminal callback 뒤에
buffer를 반환한다. 정지하지 않으면 `dma_owned`와 lease를 유지하고 재제출을 거부한다.

SPIM의 pinned `nrfx_spim_abort()`는 최대 100 us의 STOP 확인 실패에도 내부 진행 플래그를 지운다.
따라서 먼저 IRQ를 막고 STOPPED를 최대 100 us 확인한 뒤에만 nrfx 정리와 buffer 반환을 수행한다.
실패 시 driver 진행·DMA 소유권을 그대로 유지한다. 성공한 경계와 새 제출 전에 이전 END 및 pending
IRQ를 제거한다. 주소 비교나 현재 generation을 무조건 callback에 붙이는 것만으로 지연 IRQ를
구분한다고 주장하지 않는다. 이 경계는 고정 NCS의 단일 CPU nrfx IRQ 모델에 의존한다.

## 실패 재현과 회귀

`tests/host/test_r02_serial_drivers.py`는 production `SpimFabric.cpp` 또는 `TwimFabric.cpp`와
`SerialFabric.cpp`를 함께 컴파일한다. 복사한 전송 알고리즘을 시험하지 않는다. Host fake는 descriptor,
STOP 누락·지연, callback, 오류를 제어하며 mutex/spinlock/atomic은 실제 thread 동기화를 사용한다.
수정 전 첫 12개 scenario 중 11개 실패를 보존했다. TWIM의 STOP 실패 시 lease 유지 한 건은 기존에도
통과했다. 수정 후 두 personality × 12 scenario, 총 24개를 검증한다.

- 같은 주소의 오래된 완료, 공개 소비자와 경합, queue overflow, 완료 누락.
- timeout 0·1·최댓값과 마지막 경계, generation wrap, callback 뒤 waiter 예약.
- driver 오류·TWIM NACK 뒤 재시작, STOP 실패·지연·중복 callback, DMA/lease 보유와 fault.
- 실제 thread의 submit/deactivate 교차, 동기 대기 중 다른 thread의 fabric 조회, 대기 중 deactivate.

첫 target 빌드에서는 `NRFY_IRQ_PENDING_CLEAR`의 C++ `IRQn_Type` 변환 누락을 발견해 중단했다.
SDK 타입으로 명시 변환하고 Host fake도 동일한 typed 함수로 강화했다. 실패 output `C:/r02`는 보존하며
수정 후 전체 R02 선택은 별도 `C:/r02a`에서 다시 빌드해 통과했다.

공개 완료 event가 동기 호출 뒤에도 남으므로 pair HIL의 동기 성공 분기를 event 소비로 바꿨다.
기존 수동 count 합산을 제거해 완료를 두 번 세지 않는다. 독립적인 RX pattern/byte oracle, fixture
목록·JSON schema·역사 evidence는 유지한다.

## 호환성·최종 실기

| 검사 | 최종 결과 |
| --- | --- |
| production adapter fault injection | SPIM/TWIM 24/24 PASS |
| Host 전체 | 602개 중 600 PASS·2 조건부 SKIP; 설치 discovery opt-in / dirty checkout 조건 |
| contract / inventory | 45/45 PASS / identity 75·serial 23·system 16·readiness blocker 8 유지 |
| target | 7개 personality 조합 + DUT/Peer + M24 UART/SPI/TWI, 12/12 build-only, fail/error/warning 0 |
| 문서 / 스타일 | Markdown 161개 및 first-party C/C++/ino 234개 PASS |
| package / 전체 target / 설치 예제 | R02에서는 별도 재실행하지 않음; 전체 최종 gate는 R13 |
| flash / HIL | NOT RUN |

근거는 [software·source·SDK hash](evidence/r02-eed0b6c/software-and-source.json),
[target 설정·source 소속·ELF](evidence/r02-eed0b6c/target-build.json),
[DUT/Peer 전후 비교](evidence/r02-eed0b6c/pair-comparison.json)에 보존했다.
공개 header 25개의 normalized source는 R00과 같고 SDK·board·공개 자산·역사 evidence 변경은 없다.
R01과 resolved config가 같은 DUT/Peer의 RAM(data+bss)은 각각 161,342 byte로 108 byte 증가했다.
Flash(text+data)는 DUT 182,128(+1,036), Peer 182,140(+1,028) byte다.
이는 정확성 상태와 동기화 비용이며 성능 개선 수치로 해석하지 않는다.

API·CLI·builder schema·저장 형식·partition migration은 없다. 동기 호출 후 공개 완료가 관측되고,
진행 중 재제출은 `wrong_state`로 거부되며, SPIM STOP 실패는 성공 취소로 보고하지 않는 동작 교정이다.
Runtime byte가 달라지므로 과거 exact T11 PASS를 새 source에 적용하지 않는다.

R13 뒤 최종 source에서 Fixture 101~103 UART, 201~203 SPI, 301 TWI의 sync/async·같은 주소 재사용·
cancel/NACK/정상 재시작을 검증해야 한다. 현재 작업은 flash/HIL 없이 current-source T11 직전까지다.
되돌림 단위는 내부 guard, SPIM/TWIM 완료·정지 수정, 나머지 adapter guard, pair count 집계와 새 Host 시험이다.
