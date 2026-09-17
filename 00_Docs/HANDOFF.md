# 개발 인계 — M30 완료, M31-W01·W02 완료·W03~W05 진행 중

현재 설치·지원 배포는 **v0.4.1 하나**이고 개발 소스는 **0.4.1-dev**입니다.
M28과 M29는 각각 W01~W08을 완료했지만 v0.5.0 공개·Bluetooth qualification 또는 모든
OS/adapter 상호운용 완료를 뜻하지 않습니다. M30-W01 capability, W02 link별 security·pairing,
W03 유선 OOB·bond/privacy, W04 일곱 BLE profile, W05 MCUboot layout·서명과 W06 secure BLE
DFU·negative·rollback과 W07 세 보드 secure multi-link를 완료했습니다. W08은 exact
`ae5186f7…`에서 `M30-POWER-01` 네 지점 × 3회 실제 전원 차단 **12/12**를 통과했고 M30을 완료했습니다.
병행한 **HOST-W01~HOST-W03 inventory·Host resolver·launcher**도 완료했습니다.
현재 [M31 TODO](TODO_M31.md)의 전체 Bluetooth sample 원장·capability 계약 W01을
703행 parity·20/20 negative·clean HCI query 5/5로 완료했습니다. W02 CIS와 BIS
positive·negative 두 종류, time sync를 실제 두 보드에서 통과했습니다. combined와 설치
Arduino sketch 11개도 [W02 완료 기록](<04_검증 기록/167_M31_W02_설치_Arduino_ISO_예제_완료.md>)의
clean package/image로 다시 통과했습니다. 다만 공개 ISO 예제의 사용자 payload API가 없어
[W02 재점검](<04_검증 기록/191_M31_W02_공개_ISO_예제_재점검.md>)에 따라 W02 완료를 취소했습니다.
공개 `RawCis` 두 역할과 `RawBis` 두 역할은 각각
[192번](<04_검증 기록/192_M31_W02_공개_CIS_사용자_SDU_실기.md>)·
[193번](<04_검증 기록/193_M31_W02_공개_BIS_사용자_SDU_실기.md>)의 clean image로
20회 실기를 통과했습니다. 암호화 BIS 두 역할도
[194번](<04_검증 기록/194_M31_W02_공개_암호화_BIS_사용자_SDU_실기.md>)에서
20회·2,000/2,000과 잘못된 Code 거부를 확인했습니다. 시각 동기 BIS 두 역할도
[195번](<04_검증 기록/195_M31_W02_공개_BIS_시각동기_사용자_SDU_실기.md>)에서
20회·2,000/2,000과 HCI·수신 시각 단조성을 확인했습니다. CIS→BIS 공개 세 역할도
[196번](<04_검증 기록/196_M31_W02_공개_CIS_BIS_세_보드_사용자_SDU_실기.md>)에서
각 20회·2,000/2,000 전달·수신과 종료를 확인했습니다. 공개 API의 암호화 오류 후
같은 image 복구도 [197번](<04_검증 기록/197_M31_W02_공개_API_암호화_BIS_오류_후_복구.md>)에서
100/100 SDU로 확인했습니다. 일반 BIS의 강제 sync loss 뒤 새 session 복구도
[198번](<04_검증 기록/198_M31_W02_공개_BIS_sync_loss_재시작_복구.md>)에서
100/100 SDU로 확인했습니다. 공개 ISO 예제 감사는 82개 중 0건이며,
독립 개발 package에서 ISO 11개를 전수 빌드하고 같은 revision의 11역할을
두·세 보드에서 다시 20회씩 실행했습니다. [199번 최종 기록](<04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>)에
따라 **W02를 완료**했습니다.
Audio·DF·CS, HOST-W04도 잔여입니다.
2026-09-16에 [전체 기능·예제 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)으로
M31~M33 계획을 재배치했습니다. 목표는 고정 NCS의 nRF54L15 예제를 Arduino에서 사용하는 것이며,
보드 기반 기능 검증을 수행하고 정밀 RF·음질·거리/각도 보정은 필수 gate에서 제외합니다.

최종 사용자 결정에서 Apple/Google 등 외부 ecosystem와 마이크·스피커·외장 장치는 **구현·예제·
설정/연결 안내·자동 가능한 검사까지 필수**, 실제 운용·실물 검증은 **사용자 후속·v0.5.0 개발/공개
비차단**으로 확정했습니다. Ubuntu/macOS 실물 설치·USB·serial·debug는 **최종 릴리스 단계에서
사용자가 검증**합니다. 이 두 종류의 NOT RUN을 같은 release blocker로 취급하지 않습니다.
DF 원시 IQ는 배열 확보를 기다리지 않고 수신 구성의 코드·build·가능한 보드 시험부터 판정합니다.
상세 근거와 인계 개정은 [164번 기록](<04_검증 기록/164_사용자_후속_검증_범위와_DF_IQ_인계.md>)을 따릅니다.

## 1. 현재 체크포인트

| 항목 | 상태 |
| --- | --- |
| Branch | `m31-w01` — M30 인계 `10f16eaa913f9b1d1906239fbe6ff98c53c73cd1` 포함; 현행 M31 작업은 이 브랜치에서 진행 |
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
| M31 / M32 / M33 구현 진도 | **2/8 · 0/12 · 0/8**; M31-W01·W02 완료·W03~W05 진행, [M32 TODO](TODO_M32.md)·[M33 TODO](TODO_M33.md) 미착수 |
| 현재 개발 지점 | M30 완료. [W02 독립 package·11역할 실기 완료](<04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>) 후 W03 전체 LE Audio·W04 DF·W05 CS 구현 진행 |
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

1. [200번 다른 PC 인계](<04_검증 기록/200_M31_다른_PC_작업_인계.md>)를 먼저 읽습니다. 실제 C drive
   저장소의 `AGENTS.md`, branch·HEAD·미커밋 변경 소유권을 확인하고 `git fetch origin` 뒤
   **기존 `m31-w01`을 이어받아** `git pull --ff-only`로 갱신합니다. 로컬 branch가 없을 때만
   `git switch --track origin/m31-w01`로 만듭니다. Dirty/diverged 상태를 덮어쓰거나 강제 push하지 않습니다.
2. 이 문서, [M31 TODO](TODO_M31.md), [전체 기능 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>),
   [W02 최종 기록](<04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>)과
   [M31 readiness](../variants/nu54dk/m31-ble-readiness.json)을 대조합니다. Board submodule을
   초기화하고 §2의 고정 revision 및 SDK/toolchain lock을 확인합니다.
3. 현재 기준선은 **M31-W01·W02 완료 2/8**입니다. W01 원장과 W02 공개 ISO 11역할을 재구현하거나
   기존 PC의 임시 package·HEX 경로를 결과물로 가정하지 않습니다. 신규 변경은 새 PC에서 clean source,
   설치 예제 build, 보드 역할별 runtime을 같은 revision으로 결합해 검증합니다.
4. 다음 우선순위는 W03의 미완료 LC3/LE Audio profile 행입니다. W03-02 BAP unicast는 완료 근거를
   보존하고 §3의 W03-01 잔여와 W03-03~W03-11을 차례로 판정합니다. W04 raw IQ RX와 W05 CS의
   미해결 오류는 실제 register/log 근거로 조사하며 W06~W08은 아직 미착수입니다.
5. 실제 보드 시험 직전에 현재 CMSIS-DAP V2 probe SHA-256 identity·COM/serial·role·firmware를
   다시 확인합니다. 이전 PC mapping을 자동 재사용하지 않습니다. 공개 `.ino`는 의미 있는 사용자
   C++/NUCODE API 흐름을 두고 Zephyr 직접 호출과 개발 마일스톤 이름을 노출하지 않습니다.
6. HOST-W04 이후는 독립 트랙으로 유지합니다. 사용자 후속 외장 audio·Apple/Google 실물 검증과
   최종 릴리스 단계 Ubuntu/macOS 실기를 M31 기능 구현 완료로 잘못 승격하지 않습니다.

사용자가 NU54DK 세 대 연결과 보드만 보유한 상태를 확인했습니다. 이는 영구 probe mapping이 아닙니다.
M31-W01 capability/CTE TX 제어는 한 대, ISO·합성 Audio·CS는 두 대, broadcast/assistant·통합은
세 대 구성을 기본으로 합니다. 적용 가능한 실제 기능 경로는 반복 실행·증거 수집을 자동화합니다.
Apple/Google·외장 audio 등 실제 운용은 사용자 후속으로 남기되 사용 가능한 구현과 예제는 제공합니다.
Ubuntu/macOS 실기는 최종 릴리스 때 인계합니다. 정밀 RF·음질·거리/각도 보정은 필수 밖입니다.

DF 원시 IQ 수신과 각도 산출을 혼동하지 않습니다. 고정 SDC는 DF TX만 제공하고 Zephyr LL에는
RX 코드가 있으나 NU54DK target build/runtime은 아직 미검증입니다. 고정 Zephyr 수신 예제의
안테나 배열은 선택 사항입니다. W01에서 기본 안테나 수신 구성을 조사·build하고 W04에서 적용
가능한 2보드 수신·buffer·callback·복구를 검증합니다. 아직 실행하지 않은 것을 PASS로 쓰거나,
배열이 없다는 이유로 RX를 기술적 미지원으로 분류하지 않습니다. 실제 각도/안테나 전환은 별도
외장 경로입니다. CS의 `A1_B1` 기본 두 보드 시험은 DF RX의 판정과 독립적으로 진행합니다.

### CI/CD와 이번 인계의 종료 범위

최신 사용자 지시는 **C drive의 실제 저장소에서 M31 전체 구현·보드 HIL·문서·커밋·푸시**입니다.
CI/CD 실행 요청·조회·대기는 생략합니다. PR 생성·main 병합·tag/Release 게시도 요청 범위가 아닙니다. 이전 CI 상태는
[163번 기록](<04_검증 기록/163_Bluetooth_전체_기능_예제와_마일스톤_재배치.md>)에 당시 이력으로 남아 있으며
재감시 지시가 아닙니다. 다음 PC도 최신 사용자가 변경하지 않는 한 CI/CD 확인을 요구하지 않습니다.

2026-09-16 당시에는 M31/M32/M33을 2/8·0/12·0/8로 기록했으나,
2026-09-17 공개 Arduino 데이터 예제 재점검으로 W02 완료 판정을 철회했다.
이후 공개 사용자 SDU 11역할, 오류 후 복구와 독립 개발 package 실기를 완료했다.
현행 분자는 **2/8·0/12·0/8**이다. W03 이후 작업과 HOST-W04가 남아 있다.

## 5. 재검증 규칙

- raw evidence는 원본 byte를 Base64 archive로 저장하고 manifest의 크기·SHA-256을 Host 시험으로
  검증합니다. reset noise를 삭제하거나 성공 문자열로 정규화하지 않습니다.
- 실제 장치 실패는 DAP/UART identity와 전원·필요한 GPIO부터 확인합니다. 연결이 정상이면
  CMSIS-DAP으로 fault, SRAM, queue/buffer/credit와 peripheral 오류 register를 확보합니다.
- 원인 분류 → 단일 수정 → 동일 조건 재검증을 지키고 무한 재시도로 PASS를 만들지 않습니다.
- 과거 기록의 당시 판정과 원시 증거는 소급 수정하거나 삭제하지 않습니다.
- 공개 v0.4.1 package와 개발 `m31-w01` branch의 API·예제·지원 상태를 항상 구분합니다.
