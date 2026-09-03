# M23 Peripheral inventory와 공통 소유권 기준선

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VERIFY-M23-PERIPHERAL-001 |
| 기록일 | 2026-09-03 |
| 제품선 | `v0.4.0` M23 |
| Core 구현 commit | `e329733d4152d0d9e45461ac5392888bf95de112` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 판정 | **M23 PASS / M24 착수 가능** |
| 작성자 | Quantum / NUCODE |

## 1. 판정

M23은 nRF54L15/NU54DK 경쟁 범위의 75개 hardware identity를 machine-readable manifest로
고정하고, 실제 공개 객체 identity와 독립 상태 축을 allocation 없이 조회하는 API를 추가했다.
같은 serial block의 personality 상호배타, 서로 다른 block의 동시 예약, GPIOTE·DPPI·timer·IRQ·
clock과 DMA RAM range를 하나의 공통 lease 계약으로 확장했다.

이 판정은 **inventory와 공통 계약의 완료**다. Manifest에서 `absent`, `candidate`, `not-run`인
M24~M26 대상의 driver, 공개 객체, async DMA 또는 HIL이 완료됐다는 뜻이 아니다. 현재 `v0.3.0`
공개 지원 범위와 기존 Release 자산은 변경하지 않았다.

## 2. 고정 identity

| 항목 | 값 |
| --- | --- |
| SoC | nRF54L15 |
| Board target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| nRF Connect SDK | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Nordic Toolchain | `dcbdc366a1` |
| Board source | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Host Python | CPython `3.14.7` |
| Nordic Toolchain Python | CPython `3.12.4` |
| Host C++ | WinLibs POSIX UCRT GCC `16.1.0` |

Manifest는 exact NCS의 다음 두 파일 SHA-256을 고정한다.

| NCS DTS source | SHA-256 |
| --- | --- |
| `zephyr/dts/vendor/nordic/nrf54l_05_10_15.dtsi` | `f8a9385898adc53a39b653dc2df4d913589ed034060558adedb2d3a745c7a2fb` |
| `zephyr/dts/vendor/nordic/nrf54l15.dtsi` | `f24c1fc5f65356ebc95627b28014cfb662c81d5a8e6544cafb268a73f17ea5e7` |

## 3. 작업 결과

### 3.1 Inventory와 생성물

- `variants/nu54dk/peripheral-manifest.json`: M24 23개, M25 36개, M26 16개로 총 75개 identity
- `tools/peripheral/peripheral-manifest.schema.json`: strict field·enum·state 계약
- `tools/peripheral/verify_m23_inventory.py`: 중복 JSON key, exact set, serial personality group,
  공개 객체 alias, source evidence, lock/DTS hash·node와 generated drift 검사
- `cores/arduino/generated/PeripheralInventory.inc`: compile-time descriptor table
- [M23 Peripheral instance matrix](<../01_아두이노 코어 설계/09_M23_Peripheral_인스턴스_매트릭스.md>):
  사람이 읽는 동일 상태표

Silicon, board route, source, exposure, build, semantic, HIL과 concurrent HIL은 서로 독립된 축이다.
한 축의 PASS를 다른 축으로 확대하지 않는다.

### 3.2 공개 identity API

`<nucode/PeripheralInventory.h>`는 index, kind+instance와 공개 객체 이름 조회, 안정 token과
`NU54:PERIPHERAL:...` ASCII 진단 형식을 제공한다. 현재 객체는 다음 실제 identity에만 매핑된다.

| 공개 객체 | 실제 identity |
| --- | --- |
| `Serial` | UARTE20 |
| `Serial1` | UARTE30 |
| `Wire` | TWIM22 |
| `SPI` | SPIM00 |

독립 hardware를 가장하는 `Serial2` alias는 존재하지 않으며 verifier와 host/target test가 이를
거부한다.

### 3.3 M23 작업 3 — 공통 ownership

기존 AC-02A manager를 다음 자원까지 확장했다.

- GPIOTE channel, DPPI channel/group와 timer channel
- interrupt line과 clock domain
- DMA가 접근하는 RAM byte range
- timer/event/audio/radio/security/application owner 종류
- 한 트랜잭션의 고정 lease 용량 8개에서 16개로 확대

같은 `serial_block + instance`를 UARTE와 SPI/I2C personality가 동시에 얻을 수 없다. 서로 다른
block은 각자의 event·timer와 비중첩 DMA buffer를 묶어 동시에 commit할 수 있다. DMA byte range가
조금이라도 겹치면 다른 owner뿐 아니라 같은 owner의 별도 lease도 거부한다. Null, 0 byte와
비정규 offset range도 fail-closed한다.

## 4. 실행한 gate

| Gate | 결과 |
| --- | --- |
| `python tools/peripheral/verify_m23_inventory.py --write --ncs-root C:\ncs\v3.4.0` | PASS, 75개 / generated 2개 일치 |
| `python -m unittest -v tests.host.test_m23_peripheral_inventory` | 8/8 PASS |
| `python tools/ci/run_m12_gate.py contract` | 40/40 PASS |
| `python tools/ci/run_m12_gate.py host` | PASS |
| `python tools/ci/run_m12_gate.py docs` | PASS |
| `python tools/ci/run_m12_gate.py package` | 20/20 PASS |
| `python tools/ci/run_m12_gate.py examples --arduino-cli ...` | PASS |
| M23 target contract 단독 build-only | 1/1 PASS, warning 0 |
| 고정 NCS 대표 Zephyr 전체 build-only | 30/30 PASS, warning 0 |
| 전체 build 반복 중 Windows 공용 `%TEMP%` 이상 | 29/30 build, `nucode.m6.core_api`의 GCC 임시 `.s` 파일 소실 1건 |
| 위 `nucode.m6.core_api` 전용 임시 폴더 격리 재실행 | 1/1 PASS, warning 0 |

M23 target contract는 공개 identity 75개, 가짜 alias 부재, 같은 block 충돌, 서로 다른 block의
block+DPPI+timer+DMA bundle 동시 commit, 겹치는 DMA range와 잘못된 range 거부를 compile/link한다.
반복 build의 1건은 서로 다른 C source 세 개에서 assembler 입력 임시 파일을 찾지 못한 host 환경
오류였고, 동일 source와 toolchain을 전용 임시 폴더에서 단독 재실행해 통과했다. Source compile
diagnostic이나 warning으로 판정하지 않았다.
M23에는 새 peripheral의 물리 HIL이 없다. 기존 기능의 HIL 상태는 각 과거 exact-commit 기록을
manifest evidence로 연결했으며 새 기능의 `not-run`을 임의로 PASS로 바꾸지 않았다.

## 5. CI fail-closed 연결

- Software workflow의 `peripheral-inventory` job이 schema, 누락, alias, source와 generated drift를
  Ubuntu에서 검사한다.
- Reproducible-build workflow는 exact NCS workspace 준비 직후 pinned DTS hash·node를 검사하고
  그 뒤 대표 Zephyr suite를 빌드한다.
- `m23_inventory_contract` target suite가 전체 대표 build 집합에 포함된다.

## 6. 다음 단계

M24는 이 기준선 위에서 UARTE00/20/21/22/30, SPIM/SPIS00/20/21/22/30,
TWIM/TWIS20/21/22/30의 실제 선택 API와 sync/async DMA 수명주기를 구현한다. 같은 block 충돌,
다른 block 동시 실행, timeout/cancel/error/System OFF 복구와 실제 NU54DK HIL을 통과하기 전에는
manifest의 해당 상태를 지원으로 승격하지 않는다.
