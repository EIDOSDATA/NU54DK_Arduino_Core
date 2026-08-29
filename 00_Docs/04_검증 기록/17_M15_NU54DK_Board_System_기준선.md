# M15 NU54DK Board/System 기준선

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VALIDATION-M15-001 |
| 문서 개정 | 1.1 |
| 상태 | **진행 중** — 비-System-OFF 자동 HIL 2/2 PASS, SWD 격리 timed GRTC→사용자 SW0 결합 HIL NOT RUN |
| 적용 제품 버전 | `v0.2.0` |
| 기준일 | 2026-08-30 |
| 최종 갱신일 | 2026-08-30 |
| 작성자 | Quantum / NUCODE |
| 시작 기준 Core | `336e83871635398b0433ebe3bb27fa67cde2c0e6` — M14 완료 commit |
| 자동 HIL 기준 Core | `6898f7917348fab3c5cf54eec0756523e2c27d69` |
| 현재 System OFF 준비 Core | `8244e572f526329905fcff6e2a640616e36dc5c0` |
| 기준 board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` — 변경 없음 |
| 기준 SDK | nRF Connect SDK v3.4.0 / Zephyr 4.4.0 |
| 기준 target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 자동 HIL artifact | GitHub Actions run `33272544277`, artifact `9720630620` |
| 현재 준비 검증 | Software Gates run `33273425011`, Reproducible Builds run `33273424875` |

---

## 1. 목적과 현재 판정

M15는 `NUCODE_NU54DK` library에 board identity, reset, watchdog, GRTC, settings/ZMS,
System OFF와 제한된 BQ25186 API를 추가한다. 이 문서는 구현이 존재한다는 사실, 자동 HIL과
후속 수동 결합 HIL을 분리한다.

Core `6898f7917348fab3c5cf54eec0756523e2c27d69`과 board package
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`에서 같은 공식 CI HEX를 두 NU54DK에 기록했다.
두 보드 모두 identity, 64-bit uptime, GRTC callback, Settings/ZMS, watchdog stop과 watchdog
expiry reset의 비-System-OFF 자동 HIL을 통과했다.

이후 Core `8244e572f526329905fcff6e2a640616e36dc5c0`에서 System OFF 결합 HIL의 실패 상태
정리, bounded nonce 검사, UART 단절 transcript 보존과 기존 PASS evidence 보호를 보강했다.
이 보강은 Software Gates run `33273425011`과 Reproducible Builds run `33273424875`에서
모두 성공했으며 자동 HIL의 production API나 `m15_auto` 시험 범위는 변경하지 않았다.

M15 상태는 계속 **진행 중**이다. 자동 HIL은 의도적으로 System OFF에 진입하지 않았으며
`timed_system_off_wake`와 `button_system_off_wake`는 모두 **NOT RUN**이다. 완료하려면 한 번의
SWD-only 격리 세션에서 timed GRTC wake의 exact reset cause `2048`과 사용자 SW0/P1.13 wake의
exact reset cause `128`을 이 순서로 모두 확인해야 한다.

## 2. 구현 범위

| 영역 | 구현 범위 | 검증 판정 |
| --- | --- | --- |
| Board identity | 모델, target, SoC, NCS/Zephyr/Core, raw device ID | 자동 HIL 2/2 PASS |
| Reset/uptime | reset cause·지원 mask·clear, 64-bit uptime | 자동 HIL 2/2 PASS |
| Watchdog | WDT31 begin/feed/지원 시 stop | stop·expiry reset 자동 HIL 2/2 PASS |
| GRTC | absolute counter, one-shot alarm/cancel, work queue callback | callback 자동 HIL 2/2 PASS; timed System OFF wake NOT RUN |
| Settings/ZMS | `nucode/` key-value put/get/remove | reset persistence 자동 HIL 2/2 PASS |
| System OFF | SW0~SW3 button wake, GRTC timed wake 준비 | timed GRTC·사용자 SW0 결합 HIL 모두 NOT RUN |
| PMIC read | ID/status/충전 설정/SYS regulation/register watchdog | M7 ID read 역사적 PASS; M15 자동 HIL 범위 아님 |
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
| Host contract와 parser | GitHub Actions Software Gates run `33273425011` | 현재 준비 Core 전체 workflow SUCCESS |
| Arduino 예제 discovery | GitHub Actions Software Gates run `33273425011` | 현재 준비 Core SUCCESS |
| NU54DK target build | `tests/zephyr/m15_board` | 현재 준비 Core 재현 빌드 run `33273424875`의 Zephyr job SUCCESS |
| 비-System-OFF 자동 HIL image | `tests/zephyr/m15_hil` | 재현 빌드 성공, 두 보드 HIL 2/2 PASS |
| 비-System-OFF 자동 HIL runner | `tests/hil/nu54dk/m15_auto.py` | 두 보드 HIL 2/2 PASS |
| System OFF image | `tests/zephyr/m15_wake` | 현재 준비 Core 재현 build SUCCESS; 물리 wake HIL NOT RUN |
| System OFF parser·runner | `tests/hil/nu54dk/test_m15_system_off.py`, `m15_system_off.py` | 현재 준비 Core software gate PASS; 물리 wake HIL NOT RUN |
| Windows Arduino compile | 현재 준비 Core 재현 빌드 run `33273424875` | SUCCESS |

GitHub Actions의 상태는 계층별로 기록한다. 자동 HIL image를 만든 Software Gates run
`33272543102`와 Reproducible Builds run `33272544277`은 모두 `success`다. 이후 준비 보강
Core의 Software Gates run `33273425011`과 Reproducible Builds run `33273424875`도 Zephyr
build와 Windows Arduino compile을 포함해 모두 `success`로 완료됐다. 이 CI 성공은
build·software gate이며 System OFF 물리 wake PASS로 확대하지 않는다.

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
| M15 `pmicBegin()`과 상태 read | 자동 HIL 범위 아님 | 별도 실기 없이는 M15 read PASS로 확대하지 않음 |
| 충전 전압·전류·enable | **NOT RUN** | 아니요 |
| 충전 완료·재충전 | **NOT RUN** | 아니요 |
| `SYS_REG` rail 전압 | **NOT RUN** | 아니요 |
| 입력 제거 후 shutdown/ship 실제 전원 상태와 복구 | **NOT RUN** | 아니요 |
| 실제 배터리 온도 보호 | **미지원** | 아니요 |

배터리가 연결되지 않은 현재 fixture에서 PMIC write electrical HIL을 실행하지 않는다. API 사용자는
자신의 배터리, 전원과 온도 조건에서 직접 검증해야 한다. Software test나 register 변환 시험을
충전 안전성 또는 전기 동작 PASS로 확대하지 않는다. 이 범위는 **NOT RUN·사용자 책임·M15
비차단**으로 유지한다.

## 6. 비-System-OFF 자동 HIL 결과

### 6.1 공식 image provenance

| 항목 | 값 |
| --- | --- |
| GitHub Actions run | `33272544277` |
| Artifact 이름 | `m12-zephyr-build-6898f7917348fab3c5cf54eec0756523e2c27d69` |
| Artifact ID | `9720630620` |
| Artifact digest | `sha256:0704b55f6e2a939265e9c9c31995a53a82955a8ba711c14fa064ef975910fa0a` |
| HEX 이름 | `zephyr.hex` |
| HEX 크기 | `173441` bytes |
| HEX SHA-256 | `aad3089a9c26115990f1957a6b5b84571609c91b7904d7a066899512ef604950` |
| Core revision | `6898f7917348fab3c5cf54eec0756523e2c27d69` |
| Board revision | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |

Artifact digest는 GitHub Actions API가 반환한 64자리 SHA-256을 기록했다. 같은 HEX digest와
크기를 두 보드 evidence가 모두 확인했다.

### 6.2 두 보드 실기 결과

| 보드 | CMSIS-DAP UID | UART | Device ID | WDT expiry 관측 | 판정 |
| --- | --- | --- | --- | --- | --- |
| 보드 1 | `5415360300052840fcd47678fd7d106d` | `COM13` | `d7548c79f065439b` | `1.953 s` | PASS |
| 보드 2 | `5415360300052840d9e1e32cc887aaf1` | `COM14` | `fe68a78c3a5d743d` | `1.937 s` | PASS |

두 실행은 다음 scope를 정확히 검증했다.

- `identity`
- `uptime_64`
- `grtc_callback`
- `settings_zms`
- `watchdog_stop`
- `watchdog_expiry_reset`

두 evidence의 `timed_wake_executed`와 `button_wake_executed`는 모두 `false`다. 따라서 GRTC
callback PASS를 timed System OFF wake PASS로 확대하지 않는다. Evidence는 다음 경로에 있다.

- `build/m15/hil/m15_auto_6898f79_board1.json`
- `build/m15/hil/m15_auto_6898f79_board1.transcript.log`
- `build/m15/hil/m15_auto_6898f79_board2.json`
- `build/m15/hil/m15_auto_6898f79_board2.transcript.log`

| 보드 | Evidence JSON SHA-256 | Transcript SHA-256 |
| --- | --- | --- |
| 보드 1 | `2b52eb9a8bc61ff801b009fc483bca3efab0ec368081960ac6140934cf44b759` | `8e7d89d2824a9af6e35a6d428d160e1d6008edf9b621db60442a24eb70eed4d5` |
| 보드 2 | `b67245f7ce7664f8f748e934a9a3cb80d6892aab674decf38fd51af71c3086f1` | `60c24aafeaef939fc91518467bb0e378ad89bb69fc7f0f3ea138f582df87746d` |

## 7. SWD 격리 System OFF 결합 HIL 준비 상태

온보드 DAPLink SWD가 연결된 상태에서 관측한 reset cause `32` (`RESET_DEBUG`)는 fixture
contamination 진단이다. 이는 timed GRTC 또는 GPIO wake의 PASS도 FAIL도 아니며 M15 완료 증거로
사용하지 않는다.

후속 HIL은 image 기록과 UART 준비를 끝낸 뒤 한 번의 SWD-only 격리 세션으로 실행한다. NU54DK의
온보드 debug-control 2연 `SW1`에서 `DISABLE_SWD` 쪽만 격리 위치로 전환하고
`DISABLE_UART` 쪽은 그대로 두어 UART를 유지한다. 이 debug-control `SW1`은 Arduino 사용자
버튼 `SW1`/P1.09와 이름만 같을 뿐 다른 물리 부품이다. 실제 button wake에는 사용자
`SW0`/P1.13을 사용한다.

현재 준비 Core `8244e572f526329905fcff6e2a640616e36dc5c0`은 실패나 UART 단절이 발생해도
partial transcript를 보존하고 다음 재시도를 위해 target 영구 상태를 정리한다. 새 실행은
고유 transcript를 사용하며 모든 단계가 PASS한 뒤에만 기존 evidence를 원자적으로 교체한다.

Runner는 exact CMSIS-DAP UID와 source/build digest 외에 다음 두 승인을 모두 요구한다.

- `--acknowledge-interface-switch`
- `--acknowledge-button-wake`

예정 protocol은 다음 순서다.

```text
NUCODE_M15_SYSTEM_OFF_READY:schema=2:phase=TIMED:command=ARM_TIMED:duration_us=2000000
  → host가 DISABLE_SWD_ONLY 확인
  → host ARM_TIMED:<nonce>
NUCODE_M15_SYSTEM_OFF_REQUEST:schema=2:phase=TIMED:nonce=<nonce>:duration_us=2000000
NUCODE_M15_SYSTEM_OFF_ENTERING:schema=2:phase=TIMED:nonce=<nonce>:mode=GRTC_WAKE
  → UART 무응답 구간
NUCODE_M15_SYSTEM_OFF_BOOT:schema=2:phase=TIMED_WAKE:nonce=<nonce>:cause=2048:supported=<mask>
NUCODE_M15_SYSTEM_OFF_WAKE:PASS:phase=TIMED:nonce=<nonce>:source=GRTC:cause=2048
NUCODE_M15_SYSTEM_OFF_READY:schema=2:phase=BUTTON:command=ARM_BUTTON:nonce=<nonce>:wake=SW0:gpio=P1.13:active=LOW
  → host가 SW0_RELEASED 확인
  → host ARM_BUTTON:<nonce>
NUCODE_M15_SYSTEM_OFF_REQUEST:schema=2:phase=BUTTON:nonce=<nonce>:wake=SW0:gpio=P1.13:active=LOW
NUCODE_M15_SYSTEM_OFF_ACTION:schema=2:phase=BUTTON:nonce=<nonce>:expected=PRESS_LOW:host_wait_ms=2000
NUCODE_M15_SYSTEM_OFF_ENTERING:schema=2:phase=BUTTON:nonce=<nonce>:mode=GPIO_WAKE
  → UART 무응답 구간
  → 사용자가 SW0/P1.13을 누름
NUCODE_M15_SYSTEM_OFF_BOOT:schema=2:phase=BUTTON_WAKE:nonce=<nonce>:cause=128:supported=<mask>
NUCODE_M15_SYSTEM_OFF_WAKE:PASS:phase=BUTTON:nonce=<nonce>:source=SW0:gpio=P1.13:active=LOW:cause=128
NUCODE_M15_SYSTEM_OFF_PASS:schema=2:nonce=<nonce>:timed=PASS:button=PASS
```

판정은 token 이름만으로 하지 않는다. Timed 단계는 exact reset cause `2048`, button 단계는 exact
reset cause `128`을 요구한다. 2026-08-30 현재 두 단계 모두 **NOT RUN**이다.

## 8. 남은 증거

- SWD-only 격리 상태의 timed GRTC System OFF 무응답 구간과 exact reset cause `2048`
- 같은 격리 세션에서 사용자 SW0/P1.13 System OFF 무응답 구간과 exact reset cause `128`
- 결합 HIL transcript와 evidence SHA-256

## 9. 완료 조건과 다음 단계

M15 자동 비-System-OFF HIL은 두 보드에서 PASS했다. 남은 차단 gate는 한 번의 SWD-only 격리
세션에서 timed GRTC wake와 사용자 SW0/P1.13 wake를 순서대로 모두 통과하는 결합 HIL이다.
버튼 단계만 통과해서는 M15를 완료로 변경하지 않는다.

PMIC battery electrical HIL은 프로젝트 소유자가 승인한 범위 제외이므로 완료를 차단하지 않는다.
계속 `NOT RUN`과 사용자 책임으로 표시하며 전기적으로 검증된 완전 지원으로 확대하지 않는다.
두 System OFF 단계의 PASS 증거가 기록된 뒤에만 이 문서와 M15 상태를 `완료`로 변경한다.
