# 개발 인계 — M30 완료, M31 착수 대기

현재 설치·지원 배포는 **v0.4.1 하나**이고 개발 소스는 **0.4.1-dev**입니다.
M28과 M29는 각각 W01~W08을 완료했지만 v0.5.0 공개·Bluetooth qualification 또는 모든
OS/adapter 상호운용 완료를 뜻하지 않습니다. M30-W01 capability, W02 link별 security·pairing,
W03 유선 OOB·bond/privacy, W04 일곱 BLE profile, W05 MCUboot layout·서명과 W06 secure BLE
DFU·negative·rollback과 W07 세 보드 secure multi-link를 완료했습니다. W08은 exact
`ae5186f7…`에서 `M30-POWER-01` 네 지점 × 3회 실제 전원 차단 **12/12**를 통과했고 M30을 완료했습니다.
병행한 **HOST-W01~HOST-W03 inventory·Host resolver·launcher**도 완료했습니다.
다음 개발 요청은 [M31 TODO](TODO_M31.md)에 따라 착수 계약과 RF/audio 장비 gate를 먼저 확정해야 합니다.

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
| M30 | W01~W08 **8/8**, test ID **10/10 PASS** |
| M30 W01 | exact `6254398c…`, parser 13/13·target 1/1·실제 capability 7/7 PASS |
| M30 W02 | exact `4f91e347…`, target 10/10·IO capability 5종 × 10회 = 50/50 PASS |
| M30 W03 | OOB exact `284254c7…` 20/20·MITM 20/20, BOND exact `83a4d11a…` reconnect 20/20·RPA 3·migration 1·stale accept 0 |
| M30 W04 | exact `d2a0b968…`, profile 7/7·서비스별 100 operation·payload/driver 오류 0 |
| M30 W05 | exact `b16b44f4…`, signed boot 20/20·unsigned/wrong-key accept 0·power cut 0 |
| M30 W06 | exact `df9ea2a3…`, authenticated BLE update 10/10·negative 5×20·invalid/rollback accept 0·power cut 0 |
| M30 W07 | exact `d94f5ec3…`, target 3/3·동시 link 2·handle별 보안 연산 총 400회·cross-link/security/key-size 오류 0 |
| M30 W08 준비 | exact `05b639b4…`, target 3/3·두 보드 저장영역 초기화·DFU retry preflight PASS·실제 전원 차단 0회 |
| M30 W08 실제 전원 HIL | exact `ae5186f7…`, 네 지점 × 3회·실제 차단 12/12·recovery failure/invalid boot 0 |
| M30 계약 | [`17_M30_BLE_Security_Profile_DFU_착수_계약.md`](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>) |
| M30 기계 원장 | [`m30-ble-readiness.json`](../variants/nu54dk/m30-ble-readiness.json) |
| M31 실행 순서 | [M31 TODO](TODO_M31.md) |
| 현재 개발 지점 | M30 완료. M31 범위·장비 gate 확인 뒤 착수 |
| v0.5.0 Host 목표 | Windows 10/11 x64 + Ubuntu 24.04 이상 AMD64 + macOS 26 이상 Apple Silicon |
| Host 구현 상태 | HOST-W01~HOST-W03 완료, HOST-W04~HOST-W08 미착수 |

## 2. 고정 환경

| 항목 | 값 |
| --- | --- |
| Target | nRF54L15 CPUAPP / `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| NCS | v3.4.0 / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Board submodule | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Windows toolchain | bundle `dcbdc366a1` |
| M29 고정 자원 | connection 2, central 1 + peripheral 1, GATT client context 2, LE CoC channel 2 |
| M30 secure DFU layout | boot 63,488·slot 0/1 각 729,088·storage 36,864 bytes |
| M30 signing | 외부 ECDSA P-256 PEM만 허용, 저장소에는 private key 금지 |

## 3. 완료 근거와 지원 경계

- M28과 M29의 상세 결과는 각각 [140번](<04_검증 기록/140_M28_W07_3보드_HIL과_W08_완료.md>)과
  [149번](<04_검증 기록/149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>)에 보존합니다.
- M29의 단계 계약은 [M29 착수 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>),
  기계 상태는 [`m29-ble-readiness.json`](../variants/nu54dk/m29-ble-readiness.json)이 소유합니다.
  M29-W01~M29-W08은 8/8 완료 상태입니다.
- M30 단계별 계약은 [M30 착수 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>),
  기계 상태는 [`m30-ble-readiness.json`](../variants/nu54dk/m30-ble-readiness.json)이 소유합니다.
- W08 최종 근거는 [161번 기록](<04_검증 기록/161_M30_W08_실제_전원_HIL과_M30_완료.md>)의 exact
  `ae5186f7…`, 실제 전원 차단 4지점 × 3회(12/12), recovery failure·invalid boot 0입니다.
  Reset 대체와 mass erase는 없었습니다.
- [159번](<04_검증 기록/159_M30_W08_전원_HIL_주입_직전_준비.md>)과
  [160번](<04_검증 기록/160_전체_문서_검토와_마일스톤_개정.md>)은 준비·재개 당시의 역사적 상태로
  보존하며 최종 판정에는 161번 기록을 사용합니다.
- 실제 OOB carrier는 wired USB/DAPLink VCOM입니다. NFC adapter는 구현·Host/target build만 완료했고
  RF는 사용자 결정대로 `NOT RUN`·지원 제외입니다.
- Signed Write와 EATT는 각각 기본 OFF의 deprecated legacy·experimental opt-in입니다. Windows 결과는
  Intel Bluetooth/WinRT 기본 GATT 범위이며 다른 OS·adapter·profile의 PASS를 뜻하지 않습니다.
- M28~M30 개발 완료는 공개 v0.4.1 기능 추가, v0.5.0 공개 또는 Bluetooth qualification 완료가 아닙니다.

## 4. 다른 컴퓨터에서 바로 할 일

1. `main`을 fetch/pull한 뒤 branch, HEAD, 작업 트리, board submodule, NCS/Zephyr/toolchain lock을 확인합니다.
2. 이 문서와 [M31 TODO](TODO_M31.md), [v0.5.0 계획](TODO_v0.5.0.md),
   [다중 Host 지원 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)을 읽습니다.
3. 전체 Host regression을 먼저 실행해 인계 source의 기준선을 확인합니다.
4. M31-W01 착수 계약, `m31-ble-readiness.json`, capability parser와 negative Host test를 만듭니다.
5. 고정 SDK의 ISO/Audio·DF·CS source candidate와 실제 NU54DK runtime capability를 분리합니다.
6. HOST-W04 prerequisite manifest·검증기는 M31 RF/audio 장비 대기와 독립적으로 병행합니다.
7. 실제 보드 시험 전에는 현재 probe UID·COM·role·firmware revision을 다시 확인하며 과거 mapping을
   자동 재사용하지 않습니다.

M31-W01 capability는 NU54DK 한 대부터 시작할 수 있습니다. Raw ISO는 최소 두 대가 필요하고,
LE Audio·Direction Finding·정량 Channel Sounding은 승인된 peer와 audio/antenna/IQ/거리 fixture가
확정돼야 실기 판정할 수 있습니다. 장비가 없는 필수 행은 `NOT RUN`으로 유지합니다.

## 5. 재검증 규칙

- raw evidence는 원본 byte를 Base64 archive로 저장하고 manifest의 크기·SHA-256을 Host 시험으로
  검증합니다. reset noise를 삭제하거나 성공 문자열로 정규화하지 않습니다.
- 실제 장치 실패는 DAP/UART identity와 전원·필요한 GPIO부터 확인합니다. 연결이 정상이면
  CMSIS-DAP으로 fault, SRAM, queue/buffer/credit와 peripheral 오류 register를 확보합니다.
- 원인 분류 → 단일 수정 → 동일 조건 재검증을 지키고 무한 재시도로 PASS를 만들지 않습니다.
- 과거 기록의 당시 판정과 원시 증거는 소급 수정하거나 삭제하지 않습니다.
- 공개 v0.4.1 package와 개발 main의 API·예제·지원 상태를 항상 구분합니다.
