# M33-W04 DTM/HCI 진단 application template 완료

## 1. 판정

M33-W04는 기능 source `e3a663d629bcc22fb3222b99c456fda6c8e2c312`에서 **완료**다.
NCS v3.4.0과 board submodule `fe65f2f…`를 유지했고, 독립 진단 route 10개, Host negative,
DTM two-wire와 H4의 실제 두 보드 RF runtime을 검증했다.

이 완료는 정밀 RF 출력·감도·주파수 측정이나 외부 HCI Host/adapter의 실제 상호운용 PASS가 아니다.
RF tester와 UART/async UART/H5/LPUART/SPI 외부 adapter 실기는 사용자 후속 `NOT_RUN`이며 개발·릴리스
비차단이다. Native USB가 없는 HCI USB, nRF5340 cpunet 배치인 IPC/RPC는 이유와 함께 제외했다.

## 2. 구현 결과

### 2.1 DTM

- DAPLink VCOM 전용 two-wire 19200과 H4 115200의 독립 application template를 제공한다.
- 실제 SDC raw controller command complete/status만 opcode와 길이로 대조하며 H4 indicator를 포함한
  `bt_buf_get_tx()` buffer 경계를 검사한다.
- 허용 command, PHY·channel·length range, malformed/busy lease, 1초 controller timeout과 3초 RF lease를
  fail-closed로 처리한다. 오류 시 무기한 송신하지 않고 유한 STOP 또는 reset 대기 상태로 돌아간다.
- console, printk, log와 Bluetooth Host를 진단 UART에서 제외해 binary wire에 debug byte를 섞지 않는다.

### 2.2 HCI와 특수 진단 route

- HCI UART, async UART, H5, LPUART, SPI의 고정 SDK 원본을 NU54DK loaderless target으로 build하는
  독립 controller template를 제공한다.
- 외부 Host 결선·flow control·REQ/RDY·IRQ 요구사항과 종료/재시작, watchdog, 소유권 제한을 문서화했다.
- Dynamic TX power, SDC extended scan-request callback, bounded power-profiling route도 같은 원장에서
  build하며 실제 peer·계측기 runtime과 build 결과를 분리한다.
- RADIO·clock·UART 동시 소유와 transport 누락, debug UART 혼입, malformed frame, stale opcode를 Host
  검사에서 거부한다.

### 2.3 실기 안전 경계

- 세 보드의 비식별 probe/port mapping, DP/AP identity, APPROTECT, exact image SHA를 실행 직전에 대조했다.
- TX/RX는 500 kHz sector-only program, `auto_unlock=false`, no-reset 뒤 전체 load range readback을 수행했다.
  실행 시작은 software SYSRESETREQ로만 제한했다.
- 세 번째 보드는 W02 native final의 미시작 standard-watcher exact fixture와 RAM symbol을 대조하고,
  program/reset/resume 없이 계속 HALTED·RADIO disabled로 유지했다.
- 모든 command와 대기 구간에서 RADIO/DPPI/WDT와 watcher RAM을 반복 audit했다. 자동 mass erase·unlock·
  recover·hardware reset fallback은 실행하지 않았다.

## 3. exact 검증

| 항목 | 결과 |
| --- | --- |
| 전체 독립 route target build | 10/10 PASS |
| 필수 HCI controller route | UART/async UART/H5/LPUART/SPI 5/5 PASS |
| DTM two-wire runtime | 역할 교대 × 1M/2M × 채널 0/19/39, 12/12 PASS |
| DTM H4 runtime | 역할 교대 × 1M/2M × 채널 0/19/39, 12/12 PASS |
| 최소 실제 RX count | two-wire 1,590; H4 1,884 |
| Negative·cleanup | transport별 두 역할 negative 2/2, STOP 2/2 PASS |
| 세 번째 보드 격리 audit | two-wire 1,018회, H4 457회 PASS |
| Host diagnostics | 46/46 PASS |
| Readiness 계약 | 15/15 PASS, contract check PASS |
| C/C++ formatting | clang-format PASS |

상세 manifest·preflight·fixture·result와 hash는
[`m33-w04-exact-e3a663d6`](<evidence/m33-w04-exact-e3a663d6>)에 있다. 원격 CI는 조회하거나
기다리지 않았다.

## 4. 실패 진단과 SDK 위험

후속 성공을 실패 원본에 덮어쓰지 않았다. 후보 runtime에서 첫 RX command timeout을 디버거·UART transcript와
고정 SDK source로 좁혀, H4 indicator 뒤 opcode를 읽어야 하는 buffer offset 오류를 수정했다. 시작 직후 stale
UART byte는 1초 settle과 input flush로 차단했다. W02 STOP 뒤 남는 `PHYEND→DISABLE` bit 19는 Nordic MDK의
SHORTS reset/bit 정의를 근거로 TX/RX 전환에서만 허용했고 active/unknown shortcut은 계속 실패시킨다.

Exact 준비 중 pyOCD `FlashFailure`는 read-only audit와 target-only readback으로 진단했다. 1 MHz에서 RX 실패가
반복되고 500 kHz에서 program/readback이 통과해 기본 SWD를 낮췄다. 500 kHz H4 TX에서도 한 번의 transient
실패가 있었으므로 SDK 결함이나 SWD 주파수를 단일 원인으로 단정하지 않았다. 매 실패 뒤 세 보드 safe-idle과
세 번째 보드 불변을 확인한 뒤 새 output에서만 재실행했고 최종 exact 결과는 모두 PASS다.

NCS 3.4.0의 DRGN-29228 noisy DTM RX assert 조건은 현재 짧은 보드 간 시험에서 재현되지 않았다. 이를
위험 해소나 SDK 결함 부재로 확대하지 않으며, 정밀 noise/RF tester 행은 `NOT_RUN`으로 유지한다.

## 5. `M33-DIAG-01`과 남은 범위

Readiness의 필수 자동 case는 `dtm_twowire`, `dtm_h4`, `hci_automatic` 세 행으로 분리해 모두 exact PASS로
고정했다. 외부 adapter 실기는 UART, async UART, H5, LPUART, SPI의 다섯 사용자 후속 행으로 분리했고
`NOT_RUN`을 PASS로 처리하지 않았다.

M33 다음 작업은 W05 예제 품질·설치 경로다. W06까지 완료하기 전에는 HOST-W04를 시작하지 않는다.
