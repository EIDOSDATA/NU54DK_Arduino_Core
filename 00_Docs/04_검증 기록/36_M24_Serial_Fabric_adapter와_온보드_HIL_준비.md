# M24 Serial Fabric adapter와 온보드 HIL 준비 기록

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VERIFY-M24-SERIAL-FABRIC-003 |
| 기록일 | 2026-09-04 |
| 제품선 | `v0.4.0` M24 작업 3~6 |
| Core 구현 commit | `b59aee4` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 판정 | **작업 3~5 source/build/semantic PASS / 작업 6 physical HOLD** |
| 작성자 | Quantum / NUCODE |

## 1. 판정

M24 작업 3~5의 23개 serial personality에 실제 direct nrfx adapter를 연결했다. 새 API는
`<nucode/SerialFabric.h>`에서 instance별 typed handle로 선택하며 Kconfig 기본값은 계속 off다.
이 판정은 source, exact NCS `v3.4.0` compile/link와 fail-closed semantic 계약에 한정한다.
기존 `Serial`, `Serial1`, `SPI`, `Wire`와 공개 `v0.3.0` 자산은 변경하지 않았다.

새 물리 지원 판정은 아직 내리지 않는다. 온보드 7개 image와 자동 runner는 준비됐지만 연결된
프로브가 플래시 시 SWD `No ACK`를 반환했다. 외부 fixture가 필요한 16개 identity, 최대 동시성,
오류 주입, 처리량·CPU·전력도 물리 gate로 남아 있다.

## 2. 구현 범위

| Personality | Instance | 구현 |
| --- | --- | --- |
| UARTE | 00, 20, 21, 22, 30 | async TX, double-buffer RX, cancel, 고정 event queue |
| SPIM | 00, 20, 21, 22, 30 | sync/async full-duplex EasyDMA, cancel, 고정 event queue |
| SPIS | 00, 20, 21, 22, 30 | current/next buffer pair, ISR turnover, cancel/reinit |
| TWIM | 20, 21, 22, 30 | sync/async TX/RX, write-read repeated-start, bounded STOP, bus recovery |
| TWIS | 20, 21, 22, 30 | dual address, 방향별 current/next buffer, request/done/error event |

모든 DMA buffer는 `stage()`에서 선언한 application RAM lease 안에 있어야 한다. 같은 serial block의
personality는 공통 IRQ와 register를 상호배타로 소유한다. 정지 확인이 timeout되면 해당 block은
reset 전까지 fault 상태로 고정한다. PMIC P1.2/P1.3의 `pmic_read_only` profile은 TWIM만 허용하고
TWIS target 구동은 거부한다.

## 3. 자동 gate 결과

| Gate | 결과 |
| --- | --- |
| `nucode.m24.fabric` | PASS |
| `nucode.m24.uarte` | PASS |
| `nucode.m24.spi` | PASS |
| `nucode.m24.twi` | PASS |
| `nucode.m24.uarte20/21/22/30_hil` build | 4/4 PASS |
| `nucode.m24.twim20/21/22_hil` build | 3/3 PASS |
| commit `cec32fb` exact `v0.4.0` group | 9/9 PASS, warning 0 |
| commit `b59aee4` exact TWIM onboard images | 3/3 PASS, warning 0 |
| Host protocol/CI unit | 47/47 PASS |

## 4. 물리 실행 결과와 HOLD

| 항목 | 결과 |
| --- | --- |
| Probe UID | SHA-256로만 evidence에 기록하도록 runner 고정 |
| VCOM | COM5/COM6 두 포트 열거 확인 |
| pyOCD target | `nrf54l`, SWD 1 MHz, mass erase/recover 금지 |
| Flash | **FAIL — SWD/JTAG No ACK** |
| UARTE data path | NOT RUN |
| TWIM20/21/22 BQ25186 `0x6A/0x0C` read-only | NOT RUN |

내일 USB 전원을 완전히 분리·재연결한 뒤 다음 순서로 재실행한다.

1. `pyocd list`에서 probe와 COM 두 포트를 확인한다.
2. exact clean build의 UARTE runner를 실행해 4개 READY/32-byte reverse를 확인한다.
3. TWIM runner를 실행해 20/21/22가 모두 BQ25186 MASK_ID `0x41`을 반환하는지 확인한다.
4. 외부 fixture 16개와 최대 동시성·복구·성능·전력 gate를 수행한다.

물리 evidence JSON이 생성되기 전에는 M24 작업 6, M25 착수 gate 또는 `v0.4.0` 공개 지원을
PASS로 표시하지 않는다.
