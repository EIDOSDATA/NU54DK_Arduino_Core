# M15 NU54DK Board/System 기준선

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VALIDATION-M15-001 |
| 문서 개정 | 1.0 |
| 상태 | **진행 중** — 구현과 검증 진행 중, SW0/P1.13 System OFF wake 물리 HIL NOT RUN |
| 적용 제품 버전 | `v0.2.0` |
| 기준일 | 2026-08-30 |
| 최종 갱신일 | 2026-08-30 |
| 작성자 | Quantum / NUCODE |
| 시작 기준 Core | `336e83871635398b0433ebe3bb27fa67cde2c0e6` — M14 완료 commit |
| M15 기준 Core | 미확정 — 작업 tree 검증과 commit 전 |
| 기준 board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` — 변경 없음 |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 기준 target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |

---

## 1. 목적과 현재 판정

M15는 `NUCODE_NU54DK` library에 board identity, reset, watchdog, GRTC, settings/ZMS,
System OFF와 제한된 BQ25186 API를 추가한다. 이 문서는 구현이 존재한다는 사실과 실제 검증
결과를 분리한다.

2026-08-30 현재 상태는 **진행 중**이다. 신규 API, 예제와 시험 harness는 구현 중이며 자동
시험·target build·자동 HIL의 최종 결과는 아직 이 문서에 반영하지 않았다. SW0/P1.13을 눌러
System OFF에서 깨우는 물리 HIL은 **NOT RUN**이다. 따라서 M15 완료나 M16 착수를 선언하지 않는다.

## 2. 구현 범위

| 영역 | 구현 범위 | 검증 판정 |
| --- | --- | --- |
| Board identity | 모델, target, SoC, NCS/Zephyr/Core, raw device ID | 결과 반영 전 |
| Reset/uptime | reset cause·지원 mask·clear, 64-bit uptime | 결과 반영 전 |
| Watchdog | WDT31 begin/feed/지원 시 stop | 결과 반영 전 |
| GRTC | absolute counter, one-shot alarm/cancel, work queue callback | 결과 반영 전 |
| Settings/ZMS | `nucode/` key-value put/get/remove | 결과 반영 전 |
| System OFF | SW0~SW3 button wake, GRTC timed wake 준비 | 결과 반영 전 |
| PMIC read | ID/status/충전 설정/SYS regulation/register watchdog | 결과 반영 전 |
| PMIC write | 충전 전압·전류·enable·recharge·SYS_REG·watchdog·shutdown/ship 요청 | software 계약 구현, battery electrical HIL NOT RUN |
| 배터리 온도 | 실제 NTC 없음 | **미지원** |

## 3. 구성과 보드 소유권

- board package gitlink는 M14 기준 `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`을 유지한다.
- `board-system.overlay`는 `wdt31`만 활성화한다.
- BQ25186 Devicetree child node는 계속 disabled이며 Zephyr charger driver를 자동 시작하지 않는다.
- feature manifest가 `board-system.conf`, `board-system.overlay`와 `wire` 의존성을 병합한다.
- 일반 Arduino 예제에는 사용자 편집용 `prj.conf`나 `app.overlay`가 없다.

## 4. 시험 자산

| 계층 | 자산 | 현재 상태 |
| --- | --- | --- |
| Host contract | `tests/host/test_m15_board_system_contract.py` | 구현됨, 최종 실행 결과 반영 전 |
| Arduino CLI | `run_smoke.py --tests m15 examples` | 연결됨, 최종 실행 결과 반영 전 |
| NU54DK target | `tests/zephyr/m15_board` | 구현됨, 최종 build 결과 반영 전 |
| 비버튼 자동 HIL image | `tests/zephyr/m15_hil` | 구현됨, 최종 build/HIL 결과 반영 전 |
| 비버튼 자동 HIL runner | `tests/hil/nu54dk/m15_auto.py` | 구현됨, 실제 보드 결과 반영 전 |
| 자동 HIL parser | `tests/hil/nu54dk/test_m15_auto.py` | 구현됨, 최종 실행 결과 반영 전 |
| System OFF image | `tests/zephyr/m15_wake` | 구현됨, 최종 build/HIL 결과 반영 전 |
| HIL parser | `tests/hil/nu54dk/test_m15_system_off.py` | 구현됨, 최종 실행 결과 반영 전 |
| 물리 HIL runner | `tests/hil/nu54dk/m15_system_off.py` | 준비됨, SW0 wake NOT RUN |

검증 결과가 확정되면 실행 명령, testcase 수, build 크기, warning/error 수와 evidence 경로를
이 표에 추가한다. 결과를 확인하기 전에 `PASS`로 기록하지 않는다.

## 5. PMIC 검증 경계

### 5.1 구현한 안전 계약

- `pmicBegin()`은 BQ25186 `MASK_ID`를 읽을 뿐 register를 쓰지 않는다.
- PMIC write 승인은 RAM에만 보관하며 reset 또는 `pmicBegin()` 뒤 자동 해제된다.
- 승인·watchdog 정책 확인과 read-modify-write는 같은 mutex 임계구역에서 처리한다.
- 매 승인마다 register watchdog 정책을 먼저 설정하지 않으면 충전·SYS write를 거부한다.
- 공개 raw register API를 제공하지 않는다.
- 변경 가능한 field를 제한하고 read-modify-write로 reserved bit를 보존한다.
- 허용 범위 밖 전압·전류·재충전 문턱과 열거값을 거부한다.
- NU54DK에 실제 NTC가 없음을 API에서 `false`로 보고한다.

### 5.2 실제 전기 검증

| 항목 | 현재 판정 | 완료 증거로 사용하는가 |
| --- | --- | --- |
| M7의 BQ25186 ID read-only I2C HIL | 역사적 PASS | Wire와 PMIC 응답의 회귀 참고만 사용 |
| M15 `pmicBegin()`과 상태 read | 결과 반영 전 | 실제 실행 뒤 별도 판정 |
| 충전 전압·전류·enable | **NOT RUN** | 아니요 |
| 충전 완료·재충전 | **NOT RUN** | 아니요 |
| `SYS_REG` rail 전압 | **NOT RUN** | 아니요 |
| 입력 제거 후 shutdown/ship 실제 전원 상태와 복구 | **NOT RUN** | 아니요 |
| 실제 배터리 온도 보호 | **미지원** | 아니요 |

배터리가 연결되지 않은 현재 fixture에서 PMIC write electrical HIL을 실행하지 않는다. API 사용자는
자신의 배터리, 전원과 온도 조건에서 직접 검증해야 한다. Software test나 register 변환 시험을
충전 안전성 또는 전기 동작 PASS로 확대하지 않는다.

## 6. System OFF 버튼 HIL 준비 상태

HIL image는 UART `ARM` 명령 전에는 wake source를 준비하거나 System OFF에 들어가지 않는다.
Runner는 exact CMSIS-DAP UID, source/build digest와 `--acknowledge-button-wake`를 요구한다.
예정 protocol은 다음 순서다.

```text
NUCODE_M15_SYSTEM_OFF_READY
  → host ARM
NUCODE_M15_SYSTEM_OFF_REQUEST:command=ARM:wake=SW0:gpio=P1.13:active=LOW
NUCODE_M15_SYSTEM_OFF_ACTION
NUCODE_M15_SYSTEM_OFF_ENTERING
  → 2초 이상의 UART 무응답
  → 사용자가 SW0(P1.13)을 눌러 wake
NUCODE_M15_SYSTEM_OFF_BOOT:phase=WAKE:reset=LOW_POWER_WAKE
NUCODE_M15_SYSTEM_OFF_WAKE:PASS
NUCODE_M15_SYSTEM_OFF_PASS
```

현재는 image와 parser 준비 상태이며 실제 보드의 System OFF 무응답 구간, SW0 wake와
`LOW_POWER_WAKE` reset cause는 확인하지 않았다.

## 7. 비버튼 자동 HIL 준비 상태

`m15_auto.py`와 `m15_hil` image는 사람의 버튼 동작 없이 다음 상태를 실제 reset 경계로
검증하도록 준비했다.

- board identity, raw device ID와 uptime 단조성
- GRTC one-shot alarm과 callback 1회
- Settings/ZMS save, software reset 뒤 load와 delete
- watchdog feed·stop 뒤 생존
- watchdog expiry 뒤 watchdog reset cause
- 2초 timed System OFF와 clock wake reset cause

Host는 실행마다 128-bit nonce를 만들고 재부팅 단계마다 정확한 `CONTINUE` 명령을 보낸다.
장치 UID를 필수로 요구하고 실패 시 mass erase/recover 없이 UID에 제한된 reset 또는 승인된
안전 image reflash만 수행한다. 2026-08-30 현재 runner·parser·image는 구현 상태이며 실제
보드 실행 결과와 evidence는 아직 이 문서에 반영하지 않았다.

## 8. 미확정 증거

다음 항목은 자동 실행이 끝난 뒤 실제 값으로 채운다.

- host contract와 parser testcase 수
- Arduino CLI 신규 예제 5개 compile 및 전체 예제 discovery 결과
- `m15_board`, `m15_wake` target build 결과와 image 크기
- `m15_hil` target build와 비버튼 자동 HIL 결과
- exact M15 commit, build record와 source SHA-256
- SW0 wake transcript, HEX와 evidence SHA-256

## 9. 완료 조건과 다음 단계

M15 완료에는 자동 software/target gate 결과, 승인된 비파괴 실기 결과와 SW0/P1.13 System OFF
wake 물리 HIL이 필요하다. PMIC battery electrical HIL은 프로젝트 소유자가 승인한 범위
제외이므로 완료를 차단하지 않지만 계속 `NOT RUN`과 사용자 책임으로 표시한다.

현재 다음 작업은 자동 검증 결과를 이 문서에 반영하고, 이후 사용자가 SW0 버튼 wake HIL을
수행하는 것이다. 버튼 PASS 증거가 기록된 뒤에만 이 문서와 M15 상태를 `완료`로 변경한다.
