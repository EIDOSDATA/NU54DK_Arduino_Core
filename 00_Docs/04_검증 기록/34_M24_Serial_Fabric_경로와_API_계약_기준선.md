# M24 Serial Fabric 경로와 API 계약 기준선

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VERIFY-M24-SERIAL-FABRIC-001 |
| 기록일 | 2026-09-03 |
| 제품선 | `v0.4.0` M24 작업 1 |
| Core 구현 commit | `aff666411a3d80bcf1008c74ff4f4a989d9dd351` |
| 최초 계약 commit | `bf5d129603d8c7da8060f8ee7ba04af641f6f6f2` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 판정 | **M24 작업 1 PASS / 작업 2 착수 가능** |
| 작성자 | Quantum / NUCODE |

## 1. 판정

M24 작업 1은 nRF54L15의 5개 serial block과 23개 UARTE/SPIM/SPIS/TWIM/TWIS
personality를 실제 register base, IRQ, 공유 관계와 pin route에 연결했다. 기존 Arduino singleton의
identity, 향후 고급 API 형태, DMA buffer 수명주기와 errata 의무를 machine-readable 계약으로
고정하고 local·CI drift 검사를 연결했다.

이 판정은 **경로와 API 계약만 완료**됐다는 뜻이다. 새 driver, `<nucode/SerialFabric.h>`, async
DMA, 신규 personality와 신규 HIL은 아직 구현하거나 공개하지 않았다. M23 manifest의 미구현
identity는 계속 `absent`/`none`/`not_run`이며 `v0.3.0` 공개 지원 범위와 기존 Release 자산도
변경하지 않았다.

## 2. 고정 identity와 공유 관계

| Block | Non-secure base | IRQ | Personality | 현재 공개 identity |
| --- | --- | --- | --- | --- |
| `serial00` | `0x4004a000` | 74 | UARTE00, SPIM00, SPIS00 | SPIM00 |
| `serial20` | `0x400c6000` | 198 | UARTE20, SPIM20, SPIS20, TWIM20, TWIS20 | UARTE20 |
| `serial21` | `0x400c7000` | 199 | UARTE21, SPIM21, SPIS21, TWIM21, TWIS21 | 없음 |
| `serial22` | `0x400c8000` | 200 | UARTE22, SPIM22, SPIS22, TWIM22, TWIS22 | TWIM22 |
| `serial30` | `0x40104000` | 260 | UARTE30, SPIM30, SPIS30, TWIM30, TWIS30 | UARTE30 |

같은 block의 personality는 register와 IRQ를 공유하므로 동시에 활성화할 수 없다. 다른 block은
핀, IRQ, 전력 조건과 DMA RAM range를 하나의 lease로 충돌 없이 예약한 경우에만 동시에 쓸 수 있다.

## 3. Board route 판정

| Route class | 판정 | 적용 block | 근거와 조건 |
| --- | --- | --- | --- |
| `p2-dedicated20` | 승인 | 00, 20 | Nordic dedicated pin bank이며 NU54DK header에서 사용 가능 |
| `p2-dedicated21` | 미승인 | 00, 21 | P2.7~P2.10이 LED3/MOD_SWO, PMIC_PG, LED1, PMIC_CE에 연결됨 |
| `p1-flexible` | 조건부 | 20, 21, 22 | console, DAP UART, LED, VBAT monitor, PMIC I2C 소유권을 route별로 인계해야 함 |
| `p0-flexible` | 조건부 | 30 | `Serial1`을 종료하고 보드 DAP UART switch를 꺼야 함 |

P2 dedicated21 bank는 실리콘에서 제공되더라도 기본 NU54DK에서 자동 선택하지 않는다. 별도 보드
개조 profile을 만들려면 전기 검토와 독립 HIL 승인이 새로 필요하다. TWIM/TWIS30 시험 fixture에는
외부 pull-up이 필요하다.

## 4. 공개 API 경계

기존 객체는 `Serial=UARTE20`, `Serial1=UARTE30`, `Wire=TWIM22`, `SPI=SPIM00`으로 유지한다.
`Serial2`, `SPI_HS`, `Wire1`처럼 독립 hardware로 오해할 alias는 만들지 않는다.

계획된 고급 API는 `<nucode/SerialFabric.h>`의 `nucode::arduino::serialFabric()` 아래에서
kind+instance를 받는 allocation-free typed handle로 제공한다. Raw register address와 임의 pin
우회는 허용하지 않는다. 이 header와 handle은 작업 2 이후 실제 구현·시험을 통과하기 전에는
공개 API가 아니다.

## 5. DMA와 errata 계약

활성화는 검증, 전체 자원 예약, GPIO snapshot과 route 인계, peripheral 초기화, lease commit
순서로 원자적으로 수행한다. 종료는 새 작업 차단, bounded stop/cancel, DMA memory 소유권 반환,
PSEL·IRQ·event·power 해제, GPIO 복원 순서다. 정지를 증명할 수 없으면 reset 전 재사용을 금지한다.

Buffer 상태는 `application-owned`, `queued`, `dma-owned`, `completed`, `cancelled`, `error`로
고정했다. 사용자 callback은 ISR에서 직접 실행하지 않고 bounded event를 thread 문맥으로 넘긴다.
Engineering B errata 7(UARTE), 8·21(SPIM), 54(SPIS), 105(TWIM)를 구현과 시험의 필수 gate로
등록했다.

## 6. 실행한 gate

| Gate | 결과 |
| --- | --- |
| `python tools/peripheral/verify_m24_serial_contract.py --write --ncs-root C:\ncs\v3.4.0` | PASS, 5 block / 23 identity / 23 profile |
| `python -m unittest -v tests.host.test_m24_serial_contract` | 9/9 PASS |
| `python tools/ci/run_m12_gate.py inventory` | M23 75 identity + M24 계약 PASS |
| `python tools/ci/run_m12_gate.py contract` | 41/41 PASS |
| `python tools/ci/run_m12_gate.py host` | PASS |
| `python tools/ci/run_m12_gate.py docs` | 127 Markdown 파일 PASS |
| `python tools/ci/run_m12_gate.py package` | 20/20 PASS |
| M24 JSON 2개 `python -m json.tool` | PASS |
| M24 verifier와 host test `python -m py_compile` | PASS |
| 신규 driver target build | **NOT RUN — 작업 1에는 firmware source 변경 없음** |
| 신규 personality NU54DK HIL | **NOT RUN — 작업 2~6 구현 전** |

검증기는 exact NCS v3.4.0/Zephyr 4.4.0 DTS source hash와 node base/IRQ, Board pinctrl와
회로도 source hash, 23개 profile 전수, 미승인 route, singleton·alias, manifest 미승격 상태와
생성 문서 일치를 fail-closed로 검사한다. 텍스트 source는 checkout OS에 무관한 LF 정규화
SHA-256, PDF는 raw byte SHA-256을 사용한다.

검증 환경은 Host CPython `3.14.7`, Nordic Toolchain Python `3.12.4`, WinLibs POSIX UCRT GCC
`16.1.0`이다.

### 6.1 원격 CI 교정 이력

최초 계약이 포함된 `d5bc5f0`의 Software Gates #87에서는 Windows checkout의 CRLF 바이트로
기록한 DTS hash가 Ubuntu checkout의 LF 바이트와 달라 inventory job이 실패했다. 다른 6개
software job은 통과했다. `aff6664`에서 source별 `raw`/`lf-normalized` hash mode를 명시하고
checkout EOL 불변 host test를 추가했다. 이 실패는 peripheral 계약이나 driver 결함이 아니라
근거 파일의 교차 OS byte canonicalization 결함이며, 기록에서 삭제하지 않는다.

## 7. CI fail-closed 연결

- Software workflow의 `peripheral-inventory` job이 M23 inventory 뒤 M24 계약을 검사한다.
- Reproducible-build workflow는 exact NCS workspace에서 M24 DTS hash·base·IRQ 검사를 마친 뒤
  대표 Zephyr build를 시작한다.
- 계약 또는 생성 문서가 drift하거나 신규 identity가 HIL 없이 공개 상태로 승격되면 gate가 실패한다.

## 8. 다음 단계

M24 작업 2에서 공통 serial-fabric backend, allocation-free typed handle과 같은 block의 안전한
personality handover를 구현한다. 이 단계에서도 신규 공개 지원을 선언하지 않으며, 이후 UARTE,
SPIM/SPIS, TWIM/TWIS 구현과 작업 6의 NU54DK HIL까지 순차적으로 상태를 승격한다.
