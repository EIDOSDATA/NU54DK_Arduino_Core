# M24 작업 1 — Serial Fabric 경로와 API 계약

> 이 파일은 `variants/nu54dk/serial-fabric-contract.json`에서 자동 생성합니다. 직접 수정하지 마세요.
> 현재 판정은 **경로/API 계약 완료**이며, `planned-hil`과 고급 API는 아직 공개 지원이 아닙니다.

| 항목 | 값 |
| --- | --- |
| 문서 ID | `DESIGN-M24-SERIAL-FABRIC-001` |
| 제품선 | `v0.4.0` / M24 |
| SoC / SDK | `nRF54L15` / `v3.4.0` / Zephyr `4.4.0` |
| Board | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` / `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 상태 | 작업 1 완료 — route/API/negative contract 고정, driver·HIL 미착수 |
| 갱신일 | 2026-09-03 |

## 1. 이번 작업의 경계

이 계약은 23개 serial personality의 실제 identity, 공유 block, 허용 pin bank, 현재 route,
고급 선택 API의 형태와 DMA 수명주기를 고정한다. 새 header나 객체를 아직 배포하지 않으며
manifest의 미구현 identity도 `absent`/`not-run`으로 유지한다.

M24의 후속 순서는 다음과 같다.

1. **작업 1(완료):** route/API/errata 계약과 자동 drift 검사
2. **작업 2:** 공통 serial-fabric backend, typed handle과 personality handover
3. **작업 3:** UARTE 5개와 async RX/TX DMA
4. **작업 4:** SPIM/SPIS 각 5개와 sync/async·double buffer
5. **작업 5:** TWIM/TWIS 각 4개와 repeated-start·target double buffer
6. **작업 6:** 23개 단독/충돌/최대동시/복구 HIL과 성능·전력 기록

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
- The advanced header is not public and remains absent from releases until source, build, semantic and required HIL gates pass.

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
| `p1-flexible` | verified | **conditional** | 20, 21, 22 | P1.4 through P1.7 require the console profile to be disabled and the DAP UART path disconnected.<br>P1.2 and P1.3 remain a pulled-up module and PMIC I2C bus and are approved only for TWI personalities.<br>P1.0 and P1.1 remain wired to the LFXO and are excluded from serial routes without board rework.<br>P1.8, P1.9, P1.11 and P1.13 are input-only board signals and cannot satisfy output signals.<br>P1.10, P1.12 and P1.14 are transferable but their LED or VBAT monitor electrical load is part of HIL.<br>P1.0: LFXO crystal net<br>P1.1: LFXO crystal net<br>P1.8: SW3 input-only board net<br>P1.9: SW2 input-only board net<br>P1.11: PMIC_INT input-only board net<br>P1.13: SW1 input-only board net |
| `p0-flexible` | verified | **conditional** | 30 | The current UARTE30 profile may use the switched DAP virtual COM path.<br>SPIM, SPIS, TWIM, TWIS and connector-directed UARTE require the DAP UART switch to be disabled before activation.<br>P0.4 is SW4 input-only and is excluded from every serial route.<br>P0.4: SW4 input-only board net |

P2의 `dedicated21`은 실리콘 pin matrix에는 존재하지만 P2.7~P2.10이 LED, MOD_SWO와
PMIC_PG/PMIC_CE에 연결돼 기본 보드에서 승인하지 않는다. UARTE/SPIM/SPIS21은 P1 경로를
사용한다. P0의 non-UARTE 경로는 점퍼가 아니라 보드의 DAP UART switch를 끈 상태가 필요하다.
TWIM/TWIS30 fixture에는 외부 pull-up이 필요하다.

## 5. 단독 HIL 기준 route

`current-verified`는 기존 v0.3.0 증거가 있는 route이고 `planned-hil`은 M24 구현 뒤 시험할
고정 fixture route다. 계획 route는 지원 선언이 아니다.

| Identity | Route | 핀 | 상태 | 선행조건 |
| --- | --- | --- | --- | --- |
| `uarte20` | `p1-flexible` | TXD P1.4, RXD P1.5, RTS P1.6, CTS P1.7 | **current-verified** | The system console remains the owner and the advanced handle is non-owning. |
| `uarte30` | `p0-flexible` | TXD P0.0, RXD P0.1, RTS P0.2, CTS P0.3 | **current-verified** | The DAP UART switch is enabled for virtual COM use. |
| `spim00` | `p2-dedicated20` | SCK P2.1, MOSI P2.2, MISO P2.4 | **current-verified** | Chip select remains sketch-owned. |
| `twim22` | `p1-flexible` | SDA P1.2, SCL P1.3 | **current-verified** | The onboard pull-ups and PMIC bus electrical contract remain active. |
| `uarte00` | `p2-dedicated20` | RXD P2.0, TXD P2.2, CTS P2.4, RTS P2.5 | **planned-hil** | serial00 and all listed pins are free. |
| `spis00` | `p2-dedicated20` | SCK P2.1, MISO P2.2, MOSI P2.4, CSN P2.5 | **planned-hil** | serial00 and all listed pins are free. |
| `spim20` | `p2-dedicated20` | SCK P2.1, MOSI P2.2, MISO P2.4, CSN P2.5 | **planned-hil** | The console is disabled.<br>Constant-latency power mode is leased.<br>serial00 is inactive. |
| `spis20` | `p2-dedicated20` | SCK P2.1, MISO P2.2, MOSI P2.4, CSN P2.5 | **planned-hil** | The console is disabled.<br>Constant-latency power mode is leased.<br>serial00 is inactive. |
| `twim20` | `p1-flexible` | SDA P1.2, SCL P1.3 | **planned-hil** | The console is disabled.<br>serial22 is inactive. |
| `twis20` | `p1-flexible` | SDA P1.2, SCL P1.3 | **planned-hil** | The console is disabled.<br>serial22 is inactive. |
| `uarte21` | `p1-flexible` | TXD P1.10, RXD P1.14 | **planned-hil** | LED2 and LED4 are transferred to the serial owner. |
| `spim21` | `p1-flexible` | SCK P1.10, MOSI P1.12, MISO P1.14 | **planned-hil** | Chip select remains sketch-owned.<br>LED and VBAT monitor loading is included in HIL. |
| `spis21` | `p1-flexible` | SCK P1.4, MOSI P1.5, MISO P1.6, CSN P1.7 | **planned-hil** | The console is disabled.<br>The DAP UART switch is disabled. |
| `twim21` | `p1-flexible` | SDA P1.2, SCL P1.3 | **planned-hil** | serial22 is inactive. |
| `twis21` | `p1-flexible` | SDA P1.2, SCL P1.3 | **planned-hil** | serial22 is inactive. |
| `uarte22` | `p1-flexible` | TXD P1.10, RXD P1.14 | **planned-hil** | Wire is inactive.<br>LED2 and LED4 are transferred to the serial owner. |
| `spim22` | `p1-flexible` | SCK P1.10, MOSI P1.12, MISO P1.14 | **planned-hil** | Wire is inactive.<br>Chip select remains sketch-owned. |
| `spis22` | `p1-flexible` | SCK P1.4, MOSI P1.5, MISO P1.6, CSN P1.7 | **planned-hil** | Wire and the console are disabled.<br>The DAP UART switch is disabled. |
| `twis22` | `p1-flexible` | SDA P1.2, SCL P1.3 | **planned-hil** | Wire controller mode is inactive. |
| `spim30` | `p0-flexible` | SCK P0.0, MOSI P0.1, MISO P0.2 | **planned-hil** | Serial1 is inactive.<br>The DAP UART switch is disabled.<br>Chip select remains sketch-owned. |
| `spis30` | `p0-flexible` | SCK P0.0, MOSI P0.1, MISO P0.2, CSN P0.3 | **planned-hil** | Serial1 is inactive.<br>The DAP UART switch is disabled. |
| `twim30` | `p0-flexible` | SDA P0.0, SCL P0.1 | **planned-hil** | Serial1 is inactive.<br>The DAP UART switch is disabled.<br>External pull-ups are fitted by the fixture. |
| `twis30` | `p0-flexible` | SDA P0.0, SCL P0.1 | **planned-hil** | Serial1 is inactive.<br>The DAP UART switch is disabled.<br>External pull-ups are fitted by the fixture. |

## 6. DMA와 lifecycle

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

## 7. M24에 적용할 errata

| ID | Peripheral | 구현·시험 의무 |
| --- | --- | --- |
| 7 | UARTE | RX flush and empty FIFO accounting must not trust a stale RXD.AMOUNT value. |
| 8 | SPIM | MOSI corruption conditions and the pinned nrfx workaround state are covered by targeted transfer tests. |
| 21 | SPIM | The final MOSI transition condition is recorded and checked with a logic analyzer where applicable. |
| 54 | SPIS | SDO receives a known idle state so the erratum cannot leave it floating. |
| 105 | TWIM | Cancellation never disables TWIM during clock stretching; an unprovable stop requires reset before reuse. |

## 8. M24 완료 gate

- Every one of the 23 personality identities has a build, semantic and standalone HIL result.
- Every same-block personality pair fails atomically while one personality owns the block.
- Begin-end and cross-personality handover repeat without stale pins, events, IRQs, DMA or power leases.
- A five-block maximum-concurrency topology runs with disjoint pins and DMA buffers.
- Timeout, cancel, bus error, overflow, underrun and System OFF recovery are verified.
- Throughput, CPU load, latency, data loss and power are recorded for synchronous and asynchronous paths.
- No planned profile or contract-only API is described as public support before all required states pass.

최대 동시성은 이름 개수가 아니라 충돌 없는 실제 topology로 판정한다. 기준 topology는
`SPIM00 + UARTE20 console + UARTE21(P1.10/P1.14) + TWIM22 + UARTE30`의 다섯 block이다.
각 handle의 DMA buffer는 겹치지 않아야 하며 LED/PMIC/DAP 전기 상태도 함께 기록한다.

## 9. 단일 원본과 검사

- Contract: [`variants/nu54dk/serial-fabric-contract.json`](../../variants/nu54dk/serial-fabric-contract.json)
- Schema: [`tools/peripheral/serial-fabric-contract.schema.json`](../../tools/peripheral/serial-fabric-contract.schema.json)
- 검증·생성기: [`tools/peripheral/verify_m24_serial_contract.py`](../../tools/peripheral/verify_m24_serial_contract.py)
- M23 inventory: [`variants/nu54dk/peripheral-manifest.json`](../../variants/nu54dk/peripheral-manifest.json)

검증기는 exact block/base/IRQ/personality, 23개 HIL route, P2 dedicated pin map, 보드 source
checksum, stable singleton, 가짜 alias, lifecycle·errata, manifest의 미승격 상태와 생성 문서 drift를
검사한다. `--ncs-root`를 주면 고정 NCS DTS의 checksum, node base와 IRQ도 대조한다.

## 10. 근거

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
