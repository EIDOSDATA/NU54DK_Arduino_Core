# 개발 인계 — M30-W04 진행·HOST-W01~W03 완료

현재 설치·지원 배포는 **v0.4.1 하나**이고 개발 소스는 **0.4.1-dev**입니다.
M28과 M29는 각각 W01~W08을 완료했지만 v0.5.0 공개·Bluetooth qualification 또는 모든
OS/adapter 상호운용 완료를 뜻하지 않습니다. M30-W01 capability, W02 link별 security·pairing과
W03 유선 OOB·bond/privacy는 완료했고 현재 구현 지점은 **M30-W04 HID mouse/consumer·HRS·ESS catalog**입니다.
병행한 **HOST-W01~W03 inventory·Host resolver·launcher**도 완료했습니다.
M30은 `M30-POWER-01` 실제 전원 차단 직전까지 자동 진행하고 그 시험에서만 사람 개입을 요청합니다.

## 1. 현재 체크포인트

| 항목 | 상태 |
| --- | --- |
| Branch | `main` |
| 공개 배포 | v0.4.1 단독 지원 |
| 개발 소스 | 0.4.1-dev |
| M28 | W01~W08 **8/8**, test ID 9/9 PASS |
| M29 | W01~W08 **8/8**, test ID 10/10 PASS |
| M29 W07-C | 두 보드 Signed Write·EATT PASS — exact `c71ef4a2…` |
| M29 W07-D/E | 세 보드 MULTI·M19/M20/M21/M28 회귀 PASS — exact `16eb8fce…` |
| M29 상호운용 | Windows 11·Intel Bluetooth·WinRT 기본 GATT PASS — exact `a964ae20…` |
| M29 W08 최종 재검증 | 분할 후 세 role build·3보드 MULTI PASS — exact `ab3f85d3…` |
| M30 | W01~W03 완료·W04 진행, 작업 묶음 3/8·test ID 4/10 PASS |
| M30 W01 | exact `6254398c…`, parser 13/13·target 1/1·실제 capability 7/7 PASS |
| M30 W02 | exact `4f91e347…`, target 10/10·IO capability 5종 × 10회 = 50/50 PASS |
| M30 W03 | OOB exact `284254c7…` 20/20·MITM 20/20, BOND exact `83a4d11a…` reconnect 20/20·RPA 3·migration 1·stale accept 0 |
| M30 계약 | [`17_M30_BLE_Security_Profile_DFU_착수_계약.md`](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>) |
| M30 기계 원장 | [`m30-ble-readiness.json`](../variants/nu54dk/m30-ble-readiness.json) |
| M30 자동 중단점 | `M30-POWER-01` 실제 target USB 전원 차단 직전 |
| v0.5.0 Host 목표 | Windows 10/11 x64 + Ubuntu 24.04 이상 AMD64 + macOS 26 이상 Apple Silicon |
| Host 구현 상태 | HOST-W01~W03 완료, HOST-W04~W08 미착수 |

## 2. 고정 환경

| 항목 | 값 |
| --- | --- |
| Target | nRF54L15 CPUAPP / `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| NCS | v3.4.0 / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Board submodule | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Windows toolchain | bundle `dcbdc366a1` |
| M29 고정 자원 | connection 2, central 1 + peripheral 1, GATT client context 2, LE CoC channel 2 |

## 3. M29 완료 근거

- M29-W01 capability부터 W06 long/reliable GATT·descriptor·authorization·cache·LE CoC까지 각
  Host parser, target build와 한/두 보드 HIL을 분리해 통과했습니다.
- W07-C는 Signed Write 20회 warm reboot에서 CSRK/counter rollback 0·replay accept 0을,
  EATT는 암호화 뒤 bearer 2개 × operation 1,000회와 deadlock/starvation 0을 확인했습니다.
- W07-D는 mixed DUT가 central 1-link와 peripheral 1-link를 동시에 유지한 상태에서 link별 GATT와
  CoC 각 1,000회, cross-link/payload/drop 오류 0을 확인했습니다.
- W07-E는 세 보드를 순환 사용해 M19 GAP, M20 GATT, M21 security, M28 extended
  advertising·PAwR·RPA·bond reconnect 4/4 회귀군을 통과했습니다.
- Windows/Intel peer는 광고 UUID, service·characteristic·property, nonce read, response write,
  write command, notify 2회, indicate 1회와 connect/disconnect 2회를 확인했습니다.
- W08은 `MixedGattCocLinks` 예제를 추가하고 896줄 target을 protocol·RF·traffic·event·command로
  분할했습니다. 세 role target 재빌드는 분할 전과 같은 FLASH/RAM 수치로 PASS했고 exact
  `ab3f85d3…`을 세 보드에서 다시 실행해 2-link GATT·CoC와 오류 0을 재확인했습니다.

사람이 읽는 단일 완료 기록은
[149번](<04_검증 기록/149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>), 기계 원장은
[`m29-ble-readiness.json`](../variants/nu54dk/m29-ble-readiness.json)입니다. W01~W07-C의 단계별
계약은 [M29 착수 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>)에,
실패·수정·재검증은 [141~147번](<04_검증 기록/README.md>)에 그대로 보존합니다.

## 4. 지원 경계

- Signed Write는 기본 OFF의 deprecated `NUCODE_BLE_LegacySigning` opt-in입니다.
- EATT는 기본 OFF의 experimental `NUCODE_BLE_EATT` opt-in이며 안정 API로 승격하지 않았습니다.
- Windows 결과는 Intel Bluetooth/WinRT의 기본 M20 GATT 범위입니다. Android/iOS/Linux,
  Windows EATT·robust caching과 다른 adapter를 PASS로 추정하지 않습니다.
- 외부 packet sniffer는 사용하지 않았습니다. MULTI packet 분모는 같은 128-bit nonce와 세 UART,
  수신측 link별 sequence·payload 검증으로 묶었습니다.
- 반복 Serial personality handover, 모든 주변장치 임의 동시 조합, 정밀 ADC·jitter·음질·신호
  무결성은 계속 보증 범위 밖입니다. QDEC20/21은 지원 범위입니다.

## 5. M30 재개 순서

1. [v0.5.0 계획](TODO_v0.5.0.md),
   [다중 Host 지원 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)과
   [경쟁 마일스톤](<01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>)의 M30 절을 읽습니다.
2. 완료된 HOST-W01~W03 inventory·공통 backend·OS descriptor·`.cmd`/`.sh` 경계를 보존합니다.
3. exact `4f91e347…` M30-W02의 IO capability 5종·50/50과 exact `284254c7…`/`83a4d11a…`
   M30-W03 OOB·bond/privacy 증거를 보존합니다. NFC RF는 `NOT RUN` 상태를 유지합니다.
4. W04는 기존 BAS/DIS/HID keyboard 회귀와 HID mouse/consumer, HRS, ESS catalog를 구현하고
   서비스별 100 operation을 두 보드에서 검사합니다.
5. 최소 BLE DFU의 MCUboot 사용 여부, 고정 memory layout, 신뢰키·서명, 초기 설치, BLE update,
   rollback·corruption·power-loss recovery와 Arduino 제공 형태를 코드 전에 계약합니다. 새 도구는
   Windows 전용 진입점을 추가하지 않고 세 Host에서 같은 backend를 사용합니다.
6. M30 test ID별 보드/peer 수, 반복 수, timeout, negative 입력과 증거 protocol을 고정한 뒤
   Host → target build → 실제 HIL 순서로 진행합니다.

고정 결과는 [M30 착수 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>)과
[`m30-ble-readiness.json`](../variants/nu54dk/m30-ble-readiness.json)에 있다. 실제 OOB carrier는
wired USB/DAPLink VCOM이며 NFC adapter는 구현·build만 하고 RF는 `NOT RUN`이다. 마지막
`M30-POWER-01`은 네 주입 지점마다 3회 실제 target USB 전원 차단이 필요하며 reset은 대체 증거가
아니다.

## 6. 재검증 규칙

- raw evidence는 원본 byte를 Base64 archive로 저장하고 manifest의 크기·SHA-256을 Host 시험으로
  검증합니다. reset noise를 삭제하거나 성공 문자열로 정규화하지 않습니다.
- 실제 장치 실패는 DAP/UART identity와 전원·필요한 GPIO부터 확인합니다. 연결이 정상이면
  CMSIS-DAP으로 fault, SRAM, queue/buffer/credit와 peripheral 오류 register를 확보합니다.
- 원인 분류 → 단일 수정 → 동일 조건 재검증을 지키고 무한 재시도로 PASS를 만들지 않습니다.
- 과거 기록의 당시 판정과 원시 증거는 소급 수정하거나 삭제하지 않습니다.
- 공개 v0.4.1 package와 개발 main의 API·예제·지원 상태를 항상 구분합니다.
