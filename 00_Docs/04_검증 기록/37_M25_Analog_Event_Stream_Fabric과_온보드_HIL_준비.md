# M25 Analog·Event·Stream Fabric과 온보드 HIL 준비 기록

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VERIFY-M25-PERIPHERAL-FABRIC-001 |
| 기록일 | 2026-09-04 |
| 제품선 | `v0.4.0` M25 |
| Core 구현 commit | `d00e90a`, `4baaf6e`, `6299c9e` |
| 온보드 gate commit | `3c71511` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 판정 | **source/build/semantic PASS / physical HOLD** |
| 작성자 | Quantum / NUCODE |

## 1. 판정

M25의 SAADC·PWM, timer/event routing, PDM·I2S·QDEC 후보 adapter와 공통 자원 계약을 구현했다.
모든 새 경로는 Kconfig 기본값이 off인 내부 후보이며, 기존 `v0.3.0` 공개 API와 release asset은
변경하지 않았다. Exact NCS v3.4.0 target build와 host 계약은 통과했다.

배선 없는 통합 image는 EGU20→DPPIC20→TIMER20 event 경로, 내부 VDD SAADC 변환과 PDM20/21,
I2S20, QDEC20/21 handle identity를 한 번에 확인한다. 그러나 실제 flash가 SWD `No ACK`에서
중단됐으므로 runtime PASS로 승격하지 않는다.

## 2. 구현 범위

| 기능군 | 구현한 후보 경로 |
| --- | --- |
| SAADC | 8채널 scan, single-ended/differential/internal input, calibration·oversampling, 연속 EasyDMA buffer |
| PWM | PWM20/21/22, 채널 allocator, 동적 resolution/frequency, sequence EasyDMA |
| Event | TIMER00/10/20~24, GPIOTE20/30, EGU10/20, DPPIC00/10/20/30, PPIB bridge와 GRTC endpoint |
| PDM | PDM20/21 연속 capture와 double buffer |
| I2S | I2S20 TX/RX/full-duplex double buffer |
| QDEC | QDEC20/21 accumulator와 bounded event queue |

DMA buffer, peripheral block, event channel과 pin은 공통 `IoResourceManager` lease로 예약하고
commit하거나 rollback한다. ISR은 고정 크기 event만 적재하며 사용자 callback을 직접 실행하지
않는다. 여러 DMA consumer가 동시에 동작해도 서로 다른 RAM 범위와 hardware resource를 소유해야
하며, 동일 범위·block·channel 충돌은 fail-closed 처리한다.

## 3. 자동 gate 결과

| Gate | 결과 |
| --- | --- |
| `nucode.m25.analog` | PASS |
| `nucode.m25.event` | PASS |
| `nucode.m25.stream` | PASS |
| `nucode.m25.onboard_hil` build | PASS |
| commit `3c71511` exact `v0.4.0` group | 16/16 PASS, warning 0 |
| Host regression | `M12_GATE_PASS=host` |
| 온보드 image RAM | 256 KiB 경계 안에서 link PASS |

## 4. 물리 실행 결과와 남은 gate

| 항목 | 결과 |
| --- | --- |
| Probe·VCOM 열거 | 1개 probe, COM5/COM6 확인 |
| pyOCD target | `nrf54l`, SWD 1 MHz, mass erase/recover 금지 |
| Flash | **FAIL — SWD/JTAG No ACK** |
| EGU→DPPI→TIMER runtime | NOT RUN |
| 내부 VDD SAADC runtime | NOT RUN |
| SAADC 외부 정확도·PWM jitter | 외부 source/계측 fixture 필요 |
| PDM·I2S·QDEC 신호·overflow/underrun | 외부 source/sink fixture 필요 |
| 최대 동시성·장시간 soak·CPU·전력 | 외부 fixture와 계측 필요 |

재연결 뒤 먼저 배선 없는 M25 runner를 실행한다. 그 PASS는 내부 event와 VDD 경로에만 적용한다.
외부 신호 품질, 모든 instance 단독·동시 실행과 장시간 수치는 별도 fixture evidence 없이는 PASS로
표시하지 않는다.
