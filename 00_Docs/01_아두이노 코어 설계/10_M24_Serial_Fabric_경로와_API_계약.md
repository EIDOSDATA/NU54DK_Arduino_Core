# M24 작업 1~5 — Serial Fabric 전 instance와 EasyDMA

> 이 파일은 `variants/nu54dk/serial-fabric-contract.json`에서 자동 생성합니다. 직접 수정하지 마세요.
> 현재 판정은 **공통 backend와 23개 personality adapter의 source/build/semantic 완료, UART Fixture 101~103과 SPI Fixture 201~203 PASS**입니다. 남은 물리 HIL과 `planned-hil`은 아직 공개 지원이 아닙니다.

| 항목 | 값 |
| --- | --- |
| 문서 ID | `DESIGN-M24-SERIAL-FABRIC-001` |
| 제품선 | `v0.4.0` / M24 |
| SoC / SDK | `nRF54L15` / `v3.4.0` / Zephyr `4.4.0` |
| Board | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` / `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 상태 | 작업 1~5 source/build/semantic 완료 — 온보드 기본·UART 101~103·SPI 201~203 PASS, 나머지 HIL 대기 |
| 갱신일 | 2026-09-06 |

## 1. 이번 작업의 경계

이 계약은 23개 serial personality의 실제 identity, 공유 block, 허용 pin bank, 현재 route,
고급 선택 API와 DMA 수명주기를 고정한다. 작업 2에서 allocation-free typed handle, 원자적
route/DMA lease, bounded stop과 fail-closed handover를 구현했고 작업 3~5에서 UARTE, SPIM/SPIS,
TWIM/TWIS direct nrfx adapter를 연결했다. Kconfig는 기본 off인 v0.4.0 후보이며, 물리 HIL을
통과하기 전에는 stable 공개 지원으로 승격하지 않는다.

M24의 후속 순서는 다음과 같다.

1. **작업 1(완료):** route/API/errata 계약과 자동 drift 검사
2. **작업 2(완료):** 공통 serial-fabric backend, typed handle과 personality handover
3. **작업 3(완료):** UARTE 5개와 async RX/TX DMA source/build/semantic
4. **작업 4(완료):** SPIM/SPIS 각 5개와 sync/async·double buffer source/build/semantic
5. **작업 5(완료):** TWIM/TWIS 각 4개와 repeated-start·target double buffer source/build/semantic
6. **작업 6(진행):** 온보드 UARTE 4개·TWIM 3개, UART Fixture 101~103과 SPI Fixture 201~203 PASS; TWI 301·추가 동시성·성능·soak 대기

현재 온보드 증거는 [41번 기록](<../04_검증 기록/41_M24_M26_온보드_protocol_교정과_실기_재검증.md>),
UART Fixture 101~103은 [44번](<../04_검증 기록/44_M24_Fixture_101_UART_실기_검증.md>)·[45번](<../04_검증 기록/45_M24_Fixture_102_UART_실기_검증.md>)·[46번](<../04_검증 기록/46_M24_Fixture_103_UART_실기_검증.md>),
SPI Fixture 201~203은 [47번](<../04_검증 기록/47_M24_Fixture_201_SPI_실기_검증.md>)·[48번](<../04_검증 기록/48_M24_Fixture_202_SPI_실기_검증.md>)·[49번 기록](<../04_검증 기록/49_M24_Fixture_203_SPI_실기_검증.md>)을 따른다.
부분 PASS는 아래 `planned-hil` profile의 모든 기능·동시성 또는 공개 지원 완료가 아니다.

## 2. 공개 객체와 고급 API

기존 Arduino 객체의 identity는 바꾸지 않는다.

| 공개 객체 | 실제 identity | 호환 계약 |
| --- | --- | --- |
| `Serial` | `uarte20` | `immutable` |
| `Serial1` | `uarte30` | `immutable` |
| `Wire` | `twim22` | `immutable` |
| `SPI` | `spim00` | `immutable` |

독립 hardware처럼 보이는 가짜 별칭 `Serial2`, `SPI_HS`, `Wire1`은 만들지 않는다.

고급 API는 향후 `<nucode/SerialFabric.h>`의 `nucode::arduino::serialFabric()`에서
allocation 없는 typed handle로 제공한다. Raw base address는 받지 않고 kind+instance로만
선택한다. 계약 단계에서는 header 자체를 공개하지 않는다.

| 선택 함수 | 반환 handle | 허용 instance |
| --- | --- | --- |
| `uarte()` | `UarteHandle` | 0, 20, 21, 22, 30 |
| `spim()` | `SpimHandle` | 0, 20, 21, 22, 30 |
| `spis()` | `SpisHandle` | 0, 20, 21, 22, 30 |
| `twim()` | `TwimHandle` | 20, 21, 22, 30 |
| `twis()` | `TwisHandle` | 20, 21, 22, 30 |

### API 불변 조건

- Raw register base addresses are never accepted by the public factory.
- A selector names exactly one silicon personality identity; aliases never count as another resource.
- Handles are static opaque views and constructors do not enable hardware or allocate memory.
- Route changes are staged only while inactive and are rejected while active or cancelling.
- Activation reserves the shared serial block, pins, IRQ and every DMA memory range atomically.
- A second personality or handle on the same serial block fails with ownership-conflict.
- Different serial blocks may run together only when pin and DMA leases are disjoint.
- Unsupported instance, route, profile or electrical policy fails before any register or pin change.
- Standard Arduino singleton behavior and identity remain unchanged when the advanced API is enabled.
- The advanced header exists only as a Kconfig-disabled source candidate and remains absent from stable releases until driver, build, semantic and required HIL gates pass.

## 3. 물리 block과 가능한 personality

같은 행은 register base와 IRQ를 공유하므로 단 하나의 personality만 active일 수 있다.

| Block | Non-secure base / IRQ | Personality | 현재 identity | 허용 route class |
| --- | --- | --- | --- | --- |
| `serial00` | `0x4004a000` / 74 | `uarte00`, `spim00`, `spis00` | `spim00` | UARTE: p2-dedicated20, p2-dedicated21; SPIM: p2-dedicated20, p2-dedicated21; SPIS: p2-dedicated20, p2-dedicated21 |
| `serial20` | `0x400c6000` / 198 | `uarte20`, `spim20`, `spis20`, `twim20`, `twis20` | `uarte20` | UARTE: p1-flexible, p2-dedicated20; SPIM: p1-flexible, p2-dedicated20; SPIS: p1-flexible, p2-dedicated20; TWIM: p1-flexible; TWIS: p1-flexible |
| `serial21` | `0x400c7000` / 199 | `uarte21`, `spim21`, `spis21`, `twim21`, `twis21` | — | UARTE: p1-flexible, p2-dedicated21; SPIM: p1-flexible, p2-dedicated21; SPIS: p1-flexible, p2-dedicated21; TWIM: p1-flexible; TWIS: p1-flexible |
| `serial22` | `0x400c8000` / 200 | `uarte22`, `spim22`, `spis22`, `twim22`, `twis22` | `twim22` | UARTE: p1-flexible; SPIM: p1-flexible; SPIS: p1-flexible; TWIM: p1-flexible; TWIS: p1-flexible |
| `serial30` | `0x40104000` / 260 | `uarte30`, `spim30`, `spis30`, `twim30`, `twis30` | `uarte30` | UARTE: p0-flexible; SPIM: p0-flexible; SPIS: p0-flexible; TWIM: p0-flexible; TWIS: p0-flexible |

## 4. Pin bank 판정

| Route class | Silicon | NU54DK 판정 | Block | 조건·차단 이유 |
| --- | --- | --- | --- | --- |
| `p2-dedicated20` | verified | **approved** | 0, 20 | SPIM00 at 32 MHz uses the required E0/E1 extra-high-drive configuration.<br>Block 20 cross-domain use enters and leaves constant-latency power mode with the lease.<br>Pins already owned by block 00 or block 20 make the route fail before activation. |
| `p2-dedicated21` | verified | **not-approved** | 0, 21 | The standard board profile rejects this bank; no public route may silently select it.<br>A future board-rework profile requires a separate electrical review and HIL approval.<br>P2.7: LED3 and MOD_SWO board nets<br>P2.8: PMIC_PG board net<br>P2.9: LED1 board net<br>P2.10: PMIC_CE system-owned board net |
| `p1-flexible` | verified | **conditional** | 20, 21, 22 | P1.4 through P1.7 are connected to a switched DAP UART; UARTE20, UARTE21 and UARTE22 may use that host path one at a time after the previous owner stops.<br>Non-UARTE use of P1.4 through P1.7 requires the console profile and the DAP UART switch to be disabled.<br>P1.2 and P1.3 remain a pulled-up module and PMIC I2C bus and are approved only for TWI personalities.<br>P1.0 and P1.1 remain wired to the LFXO and are excluded from serial routes without board rework.<br>P1.8, P1.9, P1.11 and P1.13 are input-only board signals and cannot satisfy output signals.<br>P1.10, P1.12 and P1.14 are transferable but their LED or VBAT monitor electrical load is part of HIL.<br>P1.0: LFXO crystal net<br>P1.1: LFXO crystal net<br>P1.8: SW3 input-only board net<br>P1.9: SW2 input-only board net<br>P1.11: PMIC_INT input-only board net<br>P1.13: SW1 input-only board net |
| `p0-flexible` | verified | **conditional** | 30 | The current UARTE30 profile may use the switched DAP virtual COM path.<br>SPIM, SPIS, TWIM, TWIS and connector-directed UARTE require the DAP UART switch to be disabled before activation.<br>P0.4 is SW4 input-only and is excluded from every serial route.<br>P0.4: SW4 input-only board net |

P2의 `dedicated21`은 실리콘 pin matrix에는 존재하지만 P2.7~P2.10이 LED, MOD_SWO와
PMIC_PG/PMIC_CE에 연결돼 기본 보드에서 승인하지 않는다. UARTE/SPIM/SPIS21은 P1 경로를
사용한다. P0의 non-UARTE 경로는 점퍼가 아니라 보드의 DAP UART switch를 끈 상태가 필요하다.
TWIM/TWIS30 fixture에는 외부 pull-up이 필요하다.

## 5. 보드 자체 시험 자원

회로도 9쪽 전수를 다시 대조해 USB와 온보드 회로만으로 자동화할 수 있는 단독 데이터 경로와
외부 fixture가 필요한 경로를 분리했다. `onboard-automatic`은 구현 완료를 뜻하지 않으며,
M24 작업 3~5의 image/runner로 물리 HIL을 자동 실행할 수 있다는 시험 자원 판정이다.

| 자원 | 위치 / 실행 | 단독 HIL의 primary identity | 보드 net | 자동화 범위 | 선행조건 |
| --- | --- | --- | --- | --- | --- |
| `dap-vcom-p1` | onboard / **onboard-automatic** | `uarte20`, `uarte21`, `uarte22` | P1.4, P1.5, P1.6, P1.7 | host-tx-rx, async-dma, timeout-cancel, throughput | Exactly one of UARTE20, UARTE21 and UARTE22 owns the P1 DAP UART pins at a time.<br>The DAP UART switch remains enabled and the host binds the correct virtual COM port.<br>UARTE30 on the independent P0 DAP UART records orchestration results when the uart20 console is stopped. |
| `dap-vcom-p0` | onboard / **onboard-automatic** | `uarte30` | P0.0, P0.1, P0.2, P0.3 | host-tx-rx, async-dma, timeout-cancel, throughput | The DAP UART switch remains enabled and the host binds the correct virtual COM port.<br>UARTE20 on the independent P1 DAP UART records orchestration results. |
| `pmic-bq25186-i2c` | onboard / **onboard-automatic** | `twim20`, `twim21`, `twim22` | P1.2, P1.3 | read-only-transaction, repeated-start, nack, sync-async-dma | Exactly one TWIM personality owns P1.2 and P1.3 at a time.<br>The onboard 2.1 kOhm pull-ups and BQ25186 address 0x6a remain connected.<br>Automatic HIL is read-only unless PMIC writes are separately authorized for that boot. |
| `p2-header-fixture` | connector / **external-fixture** | `uarte00`, `spim00`, `spis00`, `spim20`, `spis20` | P2.0, P2.1, P2.2, P2.4, P2.5 | fixture-data-path, sync-async-dma, error-injection | A loopback or peer endpoint is connected to the exposed P2 header nets.<br>The fixture never selects the stock-board-prohibited P2 dedicated21 bank. |
| `p1-header-fixture` | connector / **external-fixture** | `spim21`, `spis21`, `twis20`, `twis21`, `spim22`, `spis22`, `twis22` | P1.4, P1.5, P1.6, P1.7 | fixture-data-path, sync-async-dma, target-double-buffer, error-injection | The DAP UART switch is disabled before a non-UARTE fixture owns P1.4 through P1.7.<br>An external controller is required and the TWIS target enables internal SDA/SCL pull-ups for isolated data-path HIL.<br>This fixture excludes the PMIC bus, LED outputs and the capacitive VBAT monitor net. |
| `p0-header-fixture` | connector / **external-fixture** | `spim30`, `spis30`, `twim30`, `twis30` | P0.0, P0.1, P0.2, P0.3 | fixture-data-path, sync-async-dma, target-double-buffer, error-injection | Serial1 is inactive and the DAP UART switch is disabled.<br>The paired TWIS target enables internal SDA/SCL pull-ups; external pull-up resistors are not fitted. |

23개 identity 중 7개는 USB와 온보드 회로만으로 단독 data-path HIL을 자동화할 수 있고,
나머지 16개는 외부 loopback, controller/target 또는 pull-up fixture가 필요하다.
모든 23개 identity의 build, activation, ownership-conflict와 fail-closed semantic 검사는
fixture 없이 자동화한다. P1 DAP UART를 시험할 때 P0 DAP UART를 제어·결과 채널로 사용하고
반대로 UARTE30을 시험할 때는 UARTE20을 제어·결과 채널로 사용한다.

## 6. 단독 HIL 기준 route

`current-verified`는 기존 v0.3.0 증거가 있는 route이고 `planned-hil`은 M24 adapter로 시험할
고정 fixture route다. 계획 route는 지원 선언이 아니다.

| Identity | Route | 핀 | 실행 분류 / 자원 | 상태 | 선행조건 |
| --- | --- | --- | --- | --- | --- |
| `uarte20` | `p1-flexible` | TXD P1.4, RXD P1.5, RTS P1.6, CTS P1.7 | **onboard-automatic** / `dap-vcom-p1` | **current-verified** | The system console remains the owner and the advanced handle is non-owning.<br>The DAP UART switch is enabled and the host binds the P1 virtual COM port. |
| `uarte30` | `p0-flexible` | TXD P0.0, RXD P0.1, RTS P0.2, CTS P0.3 | **onboard-automatic** / `dap-vcom-p0` | **current-verified** | The DAP UART switch is enabled for virtual COM use. |
| `spim00` | `p2-dedicated20` | SCK P2.1, MOSI P2.2, MISO P2.4 | **external-fixture** / `p2-header-fixture` | **current-verified** | Chip select remains sketch-owned. |
| `twim22` | `p1-flexible` | SDA P1.2, SCL P1.3 | **onboard-automatic** / `pmic-bq25186-i2c` | **current-verified** | The onboard pull-ups and PMIC bus electrical contract remain active.<br>Automatic HIL reads the BQ25186 at address 0x6a without changing PMIC state. |
| `uarte00` | `p2-dedicated20` | RXD P2.0, TXD P2.2, CTS P2.4, RTS P2.5 | **external-fixture** / `p2-header-fixture` | **planned-hil** | serial00 and all listed pins are free. |
| `spis00` | `p2-dedicated20` | SCK P2.1, MISO P2.2, MOSI P2.4, CSN P2.5 | **external-fixture** / `p2-header-fixture` | **planned-hil** | serial00 and all listed pins are free. |
| `spim20` | `p2-dedicated20` | SCK P2.1, MOSI P2.2, MISO P2.4, CSN P2.5 | **external-fixture** / `p2-header-fixture` | **planned-hil** | The console is disabled.<br>Constant-latency power mode is leased.<br>serial00 is inactive. |
| `spis20` | `p2-dedicated20` | SCK P2.1, MISO P2.2, MOSI P2.4, CSN P2.5 | **external-fixture** / `p2-header-fixture` | **planned-hil** | The console is disabled.<br>Constant-latency power mode is leased.<br>serial00 is inactive. |
| `twim20` | `p1-flexible` | SDA P1.2, SCL P1.3 | **onboard-automatic** / `pmic-bq25186-i2c` | **planned-hil** | The console is disabled.<br>serial22 is inactive.<br>Automatic HIL reads the onboard BQ25186 at address 0x6a without changing PMIC state. |
| `twis20` | `p1-flexible` | SDA P1.4, SCL P1.5 | **external-fixture** / `p1-header-fixture` | **planned-hil** | The console is disabled.<br>The DAP UART switch is disabled.<br>TwisConfiguration.internal_pullups is enabled on the isolated fixture; external pull-up resistors are not fitted. |
| `uarte21` | `p1-flexible` | TXD P1.4, RXD P1.5, RTS P1.6, CTS P1.7 | **onboard-automatic** / `dap-vcom-p1` | **planned-hil** | The uart20 console and every other P1 DAP UART owner are inactive.<br>The DAP UART switch is enabled and the host binds the P1 virtual COM port.<br>UARTE30 reports orchestration results through the independent P0 DAP UART. |
| `spim21` | `p1-flexible` | SCK P1.4, MOSI P1.5, MISO P1.6, CSN P1.7 | **external-fixture** / `p1-header-fixture` | **planned-hil** | The console is disabled.<br>The DAP UART switch is disabled.<br>The SPI fixture excludes VBAT monitor and LED loads. |
| `spis21` | `p1-flexible` | SCK P1.4, MOSI P1.5, MISO P1.6, CSN P1.7 | **external-fixture** / `p1-header-fixture` | **planned-hil** | The console is disabled.<br>The DAP UART switch is disabled. |
| `twim21` | `p1-flexible` | SDA P1.2, SCL P1.3 | **onboard-automatic** / `pmic-bq25186-i2c` | **planned-hil** | serial22 is inactive.<br>Automatic HIL reads the onboard BQ25186 at address 0x6a without changing PMIC state. |
| `twis21` | `p1-flexible` | SDA P1.4, SCL P1.5 | **external-fixture** / `p1-header-fixture` | **planned-hil** | The console is disabled.<br>The DAP UART switch is disabled.<br>TwisConfiguration.internal_pullups is enabled on the isolated fixture; external pull-up resistors are not fitted. |
| `uarte22` | `p1-flexible` | TXD P1.4, RXD P1.5, RTS P1.6, CTS P1.7 | **onboard-automatic** / `dap-vcom-p1` | **planned-hil** | The uart20 console, Wire and every other P1 DAP UART owner are inactive.<br>The DAP UART switch is enabled and the host binds the P1 virtual COM port.<br>UARTE30 reports orchestration results through the independent P0 DAP UART. |
| `spim22` | `p1-flexible` | SCK P1.4, MOSI P1.5, MISO P1.6, CSN P1.7 | **external-fixture** / `p1-header-fixture` | **planned-hil** | Wire and the console are disabled.<br>The DAP UART switch is disabled.<br>The SPI fixture excludes VBAT monitor and LED loads. |
| `spis22` | `p1-flexible` | SCK P1.4, MOSI P1.5, MISO P1.6, CSN P1.7 | **external-fixture** / `p1-header-fixture` | **planned-hil** | Wire and the console are disabled.<br>The DAP UART switch is disabled. |
| `twis22` | `p1-flexible` | SDA P1.4, SCL P1.5 | **external-fixture** / `p1-header-fixture` | **planned-hil** | Wire and the console are disabled.<br>The DAP UART switch is disabled.<br>TwisConfiguration.internal_pullups is enabled on the isolated fixture; external pull-up resistors are not fitted. |
| `spim30` | `p0-flexible` | SCK P0.0, MOSI P0.1, MISO P0.2 | **external-fixture** / `p0-header-fixture` | **planned-hil** | Serial1 is inactive.<br>The DAP UART switch is disabled.<br>Chip select remains sketch-owned. |
| `spis30` | `p0-flexible` | SCK P0.0, MOSI P0.1, MISO P0.2, CSN P0.3 | **external-fixture** / `p0-header-fixture` | **planned-hil** | Serial1 is inactive.<br>The DAP UART switch is disabled. |
| `twim30` | `p0-flexible` | SDA P0.0, SCL P0.1 | **external-fixture** / `p0-header-fixture` | **planned-hil** | Serial1 is inactive.<br>The DAP UART switch is disabled.<br>The paired TWIS target enables internal SDA/SCL pull-ups; external pull-up resistors are not fitted. |
| `twis30` | `p0-flexible` | SDA P0.0, SCL P0.1 | **external-fixture** / `p0-header-fixture` | **planned-hil** | Serial1 is inactive.<br>The DAP UART switch is disabled.<br>TwisConfiguration.internal_pullups is enabled; external pull-up resistors are not fitted. |

## 7. DMA와 lifecycle

### 활성화

1. Validate identity, profile, pin direction and electrical policy without changing hardware.
2. Reserve serial block, pins, IRQ, power requirement and every DMA memory range in one lease.
3. Snapshot GPIO state and transfer pins to the selected route.
4. Apply runtime power and pinctrl, clear stale events and initialize the selected personality.
5. Commit the lease and only then publish the active state.

### 종료·취소

1. Reject new work and request a bounded cancel or stop.
2. Wait for the documented terminal event and prove DMA no longer owns application memory.
3. Disable shortcuts, publish-subscribe links, interrupts and the peripheral personality.
4. Disconnect PSEL, release power mode, restore GPIO state and release the complete lease.
5. Latch fail-closed if bounded shutdown or restoration cannot be proven.

Buffer 상태 집합은 `application-owned`, `queued`, `dma-owned`, `completed`, `cancelled`, `error`다. 완료·취소·오류 event 전에는 application이 buffer를
재사용할 수 없다. ISR은 bounded event만 기록하고 사용자 callback은 thread 문맥으로 넘긴다.
Bounded stop으로 DMA 정지를 증명하지 못하면 해당 block을 fail-closed로 latch하고 reset 전
재사용을 금지한다.

## 8. M24에 적용할 errata

| ID | Peripheral | 구현·시험 의무 |
| --- | --- | --- |
| 7 | UARTE | RX flush and empty FIFO accounting must not trust a stale RXD.AMOUNT value. |
| 8 | SPIM | MOSI corruption conditions and the pinned nrfx workaround state are covered by targeted transfer tests. |
| 21 | SPIM | The final MOSI transition condition and pinned workaround are reviewed and exercised by targeted peer transfers; unmeasured waveform quality is not guaranteed. |
| 54 | SPIS | SDO receives a known idle state so the erratum cannot leave it floating. |
| 105 | TWIM | Cancellation never disables TWIM during clock stretching; an unprovable stop requires reset before reuse. |

## 9. M24 완료 gate

- Every one of the 23 personality identities has a build, semantic and standalone HIL result.
- Every same-block personality pair fails atomically while one personality owns the block.
- Begin-end and cross-personality handover repeat without stale pins, events, IRQs, DMA or power leases.
- A five-block maximum-concurrency topology runs with disjoint pins and DMA buffers.
- Timeout, cancel, bus error, overflow, underrun and System OFF recovery are verified.
- Software-observed throughput, CPU load, latency and data loss plus power-mode lease state are recorded for synchronous and asynchronous paths; precision timing and power metrology are outside the v0.4.0 release scope.
- Owner-approved v0.4.0 functional HIL uses onboard resources and safe NU54DK peer/loopback wiring; external measurement equipment and third-party device qualification are not required, but unexecuted core functions remain HOLD.
- No planned profile or contract-only API is described as public support before all required states pass.

최대 동시성은 이름 개수가 아니라 충돌 없는 실제 topology로 판정한다. 기준 topology는
`SPIM00 + UARTE20 console + UARTE21(P1.10/P1.14) + TWIM22 + UARTE30`의 다섯 block이다.
UARTE21 단독 시험은 P1 DAP UART를 재사용하지만 이 최대 동시 topology에서는
UARTE20과 핀이 겹치지 않는 P1.10/P1.14 connector fixture route를 사용한다.
각 handle의 DMA buffer는 겹치지 않아야 하며 LED/PMIC/DAP 전기 상태도 함께 기록한다.

[42번 범위 합의](<../04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>)에 따라 두 NU54DK의
실제 통신·기대 데이터·DMA·복구·허용 동시성·soak를 검증한다. 외부 계측기는 필수가 아니며
정밀 파형·전력·부품별 호환성을 보증하지 않는다. Errata 대응과 안전한 배선 조건은 유지하고
기능 시험이 성립하지 않은 항목은 HOLD로 남긴다.

## 10. 단일 원본과 검사

- Contract: [`variants/nu54dk/serial-fabric-contract.json`](../../variants/nu54dk/serial-fabric-contract.json)
- Schema: [`tools/peripheral/serial-fabric-contract.schema.json`](../../tools/peripheral/serial-fabric-contract.schema.json)
- 검증·생성기: [`tools/peripheral/verify_m24_serial_contract.py`](../../tools/peripheral/verify_m24_serial_contract.py)
- M23 inventory: [`variants/nu54dk/peripheral-manifest.json`](../../variants/nu54dk/peripheral-manifest.json)

검증기는 exact block/base/IRQ/personality, 6개 보드 시험 자원, 23개 HIL route, P2 dedicated pin map, 보드 source
checksum, stable singleton, 가짜 alias, lifecycle·errata, candidate/stable 경계와 생성 문서 drift를
검사한다. `--ncs-root`를 주면 고정 NCS DTS의 checksum, node base와 IRQ도 대조한다.

## 11. 근거

- [board-schematic](../../board_package/NU54DK_Zephyr_DTS/NU54-DK%20Schematic.pdf) — SHA-256 `7e959be6d8db5d31c55366bd118093727062588770772b226117dd3826798466` (`raw`)
- [board-pinctrl](../../board_package/NU54DK_Zephyr_DTS/boards/nucode/nu54dk/nu54dk-pinctrl.dtsi) — SHA-256 `5ec7648319b0941753486e6895f2615c4a9728cd5256b0a27086a793cffc48e7` (`lf-normalized`)
- [board-common-dts](../../board_package/NU54DK_Zephyr_DTS/boards/nucode/nu54dk/nu54dk_cpuapp_common.dtsi) — SHA-256 `bfb90dd8dad909a3e30d57043aa03b1aa9d4b1d7cf064430af1b542b6743c9c2` (`lf-normalized`)
- [variant-pin-policy](../../dts/nucode/nu54dk-arduino-pins.dtsi) — SHA-256 `2f2b6add061b0c9c51c75e7790784155110ce5e9c88ababdd0fbd807a2b29a35` (`lf-normalized`)
- [runtime-dts](../../dts/nucode/nu54dk-arduino-runtime.dtsi) — SHA-256 `77fc0a2e9cb99cb630f82950b3b7bbfceee57c68023dd0cf19ee5f9c92d9620e` (`lf-normalized`)
- [nordic-uarte](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/uarte.html-topic)
- [nordic-spim](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/spim.html-topic)
- [nordic-spis](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/spis.html-topic)
- [nordic-twim](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/twim.html-topic)
- [nordic-twis](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/twis.html-topic)
- [nordic-dedicated-pins](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/chapters/pin.html-dedicated_pins)
- [nordic-csp47-pins](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/chapters/pin.html-csp47)
- [nordic-errata-engineering-b](https://docs.nordicsemi.com/r/bundle/errata_nrf54l15_engb/page/ERR/nrf54l15/EngineeringB/latest/err_l15_new.html)
- [competitor-v1-0-17](https://github.com/lolren/nrf54-arduino-core/tree/a6bb99879aa14cbff362a5478d5f1189848b4200)
