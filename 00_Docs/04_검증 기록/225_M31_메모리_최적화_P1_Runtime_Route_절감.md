# 225 — M31 메모리 최적화 P1 Runtime Route 절감

## 1. 판정

2026-09-22 `RuntimePeripheralRoute`가 peripheral block 하나와 각 GPIO pad 하나의 transaction에
16-entry 범용 `IoResourceLease`를 다섯 개 보존하던 구조를 right-size했다. 최대 16개 batch API와
Peripheral Fabric의 resource slot 계약은 유지하고, 정확히 한 자원만 reserve/transfer하는 경로에
`IoResourceSingleLease`를 추가했다.

단일 lease는 범용 lease와 같은 reserve → commit/rollback → release 단계, manager epoch,
generation, previous owner/state 복구와 stale 판정을 사용한다. count 2 이상 요청은
`invalid_argument`로 fail-closed한다. GPIO handover의 pin alias·interrupt snapshot·mutex와
route의 pinctrl/PM/STOP/faulted 수명은 바꾸지 않았다.

## 2. 정적 RAM 전후 비교

동일 `p0_serial_spi` adaptive clean image에서 직전 UART20 기준과 비교했다.

| 항목 | UART20 변경 뒤 | Route 변경 뒤 | 절감 |
| --- | ---: | ---: | ---: |
| 전체 정적 RAM | 24,613 B | 21,013 B | 3,600 B |
| `spi_route` | 4,224 B | 624 B | 3,600 B |
| RAM 사용률 | 9.3891% | 8.0158% | 1.3733%p |
| RAM headroom | 237,531 B | 241,131 B | +3,600 B |
| FLASH | 59,192 B | 60,332 B | +1,140 B |

P0 50,877 B 대비 P1 누적 정적 RAM 절감은 29,864 B(58.7%)다. FLASH 증가는 동일 검증 로직의
1-entry template specialization과 overload에서 발생하며 RAM과 별도 기록한다. 새 image의 금지
symbol은 0건이고 budget gate는 PASS다. Core SPI clean-example 상한은 26,000 B에서 22,500 B로
낮췄다.

## 3. 회귀 검증

| 검증 | 결과 |
| --- | --- |
| R08 resource/route Host 23 scenario | PASS |
| M23 inventory Host | 9 PASS |
| R10 serial concurrency Host | PASS |
| AC-02B B2/Analog 인접 Host | 6/9 PASS |
| 전체 Host suite | 1,475 PASS, 2 skip |
| AC-02A ownership + AC-02B production route target build-only | 2/2 PASS, warning 0 |
| adaptive Serial-only/include-only/SPI clean + cache reuse | PASS |
| 물리 HIL | NOT RUN — production target semantic/build와 기존 route runtime 계약 범위 |

R08은 activate/deactivate 반복, alias, block conflict, begin/pinctrl/PM/commit 실패,
unwind 실패의 faulted 차단, stale release, batch capacity, DMA overlap과 thread 직렬화를 실행한다.
새 single scenario는 count 초과 거부, commit/release와 stale copy 거부를 추가했다.

## 4. 다음 작업

SPI image의 다음 큰 Core 고정 저장소는 중앙 `IoResourceTable` 2,320 B다. 이는 full profile과
Peripheral Fabric의 128-slot 공개 계약을 그대로 줄일 수 없으므로, adaptive Core 역할에서 실제
동시 자원 상한을 별도 capacity로 생성할 수 있는지 먼저 검증한다. 그 뒤 역할별 GATT event
queue/state와 server/client 저장소를 분리한다.
