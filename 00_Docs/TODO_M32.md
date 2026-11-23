# M32 실행 TODO — v0.6.0 최신 BLE 제어·Mesh 1.1·무선 공존

> **완료·동결 기록 — 2026-10-05:** 완료 결과와 증거를 보존하며 후속 진행 상태를 동기화하거나
> 매 작업마다 전체를 다시 읽지 않는다. 관련 과거 근거가 필요할 때만 참조한다.
> 현행 진행은 [M33 TODO](TODO_M33.md)·[제품 계획](TODO_v0.6.0.md), 재개는
> [M33 인계](M33_HANDOFF.md), Host 요구·진행은 [다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)이 소유한다.

| 항목 | 내용 |
| --- | --- |
| 대상 제품선 | **v0.6.0** — M33과 함께 후속 Bluetooth 확장 제품선 구성 |
| 현재 구현 상태 | **12/12 완료 — W12 정합성 감사와 후속 인계까지 마감** |
| 하위 gate | M32-A Controller/Host·Nordic 확장, M32-B Mesh, M32-C 최소 radio·공존 |
| 선행·후속 인계 | M31의 controller/resource 계약 인계; HOST-W07은 다중 Host 계약의 독립 범위 |
| 고정 기준 | NCS `v3.4.0`, [CI lock](../tools/ci/ncs-3.4.0.lock.json)의 Zephyr·toolchain revision |
| 최종 실기 장비 | NU54DK 3개; W11 preflight 당시 AHB debug 접근 가능. 새 실기 전 mapping·접근 상태 재확인 |
| 최종 갱신일 | 2026-10-03 |

기능·upstream 예제·제공 방식의 상세 원본은
[NCS Bluetooth 전체 기능과 예제 실행 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)이다.
이 문서는 그 범위의 작업별 완료·체크리스트·시험 ID와 실제 증거를 연결한다. 전체 순서·제품선은
[제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>), 앞뒤 인계는
[M31 TODO](TODO_M31.md)와 [M33 TODO](TODO_M33.md)를 따른다.
문서 작성·Host test·build 통과를 실기 완료 수에 포함하지 않는다. 현재 **W01~W12
12/12 완료**이며, 세부 증거는 아래 작업별 항목이 소유한다. W08은 BLOB 10/10회와 signed MDFU
5회·두 target 10/10 배포, negative, confirm/rollback, 세 역할 STOP/cleanup까지 clean exact
PASS했다. W10 세 내부 공존 조합도 protocol별 4,000/4,000 exact PASS했다. W11은 clean source
`94f02544…`에서 12-family 12/12, signed MDFU 10/10과 1,800초 soak를 PASS했다.

사용자의 2026-10-02 재개 지시에 따라 W08부터 W12까지 순차 완료했다. W09 최신 clean HEAD
회귀, W10 공존 exact HIL, W11 전체 closure, W12 정합성 감사를 PASS했다. 차단 진단 뒤 CTRL-AP ERASEALL과 기존
flash 삭제를 명시적으로 승인받았지만 최종 실기 preflight에서는 세 보드 AHB debug가 열려 있어
ERASEALL은 필요하지 않았고 실행하지 않았다. M32는 마감했다. 후속 M33의 진행은
[M33 TODO](TODO_M33.md), 재개 지점은 [M33 인계](M33_HANDOFF.md), HOST-W04~W08 요구·진행은
[다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)이 소유한다.
당시 M32 진행 지시는 별개 Host의 재개 승인으로 해석하지 않았다.

최종 구현 source `49099e74fec60566f8708e8398d6c1def86dd6d6`의
[Software Gates](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/37099299097)는 9/9 성공했다.
시험군은 **23 PASS + `M32-ACL-01` 1 HOLD / 24**다. ACL은 고정 SDK의 Host TX 경로 부재로
`unsupported`이며 M32 기능 PASS에 합산하지 않는다. 문서 정비와 main squash 통합은
[295번 기록](<04_검증 기록/295_M32_문서_전수_정비와_main_Squash_통합.md>)을 따른다.

동결 당시 설치·지원 버전은 v0.5.0이고 M32/M33은 미공개 v0.6.0 제품선이다.
NCS v3.4.0·제품 SDC·board/toolchain pin은 유지한다. [제품 v0.7.0](TODO_v0.7.0.md)은
NCS v3.4.1 전체 전환만 수행하며 [SDK 변경·개발 영향](<00_사전 리서치/03_NCS_3.4.1_변경과_개발_영향.md>)의
조건부 위험과 회귀 항목을 인계한다. 버전 배정은 구현 완료·실물 시험·공개 승인이 아니다.

## 1. 착수 경계

- M28의 여섯 capability 군과 고정 2-link/1-advertising-set 계약으로 완료한 8/8·9/9는 보존한다.
  당시 범위에 없던 power/path-loss·신규 timing·확장 자원은 M32의 신규 구현·검증으로 추적한다.
- M29의 8/8·10/10과 M30의 8/8·10/10 완료를 보존한다. M30-POWER-01의 실제 전원 차단
  **4지점 × 3회, 12/12 PASS**, recovery failure 0, invalid image boot 0은
  [161번 기록](<04_검증 기록/161_M30_W08_실제_전원_HIL과_M30_완료.md>)이 소유한다.
- 목표는 고정 NCS의 nRF54L15 적용 기능과 예제를 Arduino에서 사용하는 것이다. 일반 API는
  wrapper로, 저수준·특수 기능은 direct/profile/template로 제공하고 각 경로를 설치·예제로 검증한다.
- LE Flushable ACL Data와 그 밖의 experimental 기능은 opt-in 상태를 명시한다. 표준 Shorter
  Connection Interval과 Nordic LLPM은 별도 기능으로 구현·판정한다.
- 세 보드의 packet/event/counter/hash와 수명주기로 기능을 검증한다. 정밀 RF 출력·감도·거리·각도·
  전류 교정이나 audio 음질은 필수 완료 조건에 추가하지 않는다. 관측하지 못한 RF threshold 전환은
  Host 주입 시험과 실제 RF 결과를 각각 남긴다.
- 보드 수가 세 개를 넘는 topology, 외부 coex 신호 배선, 전원 차단 장치나 다른 vendor peer가 필요한
  행은 필요 조건을 기록한다. 해당 기능 행이 `NOT RUN`이어도 독립적인 구현·build는 계속 진행한다.
- [전체 계약의 최종 사용자 결정](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)에
  따라 외장 장치·Apple/Google 등 제품의 실제 운용·검증은 사용자 후속이며 개발·릴리스 필수 gate에서
  제외한다. 실제 연결해서 사용할 구현·예제·설정/연결 안내·자동 가능한 검사는 반드시 제공한다.
  Ubuntu/macOS 실물 설치·USB·serial·debug는 해당 OS 지원을 추가하는 후속 릴리스 때 사용자가
  검증한다. M31 Windows 릴리스의 gate에는 포함하지 않는다.

## 2. 작업 배치

| 작업 | 하위 gate | 구현·검증 범위 | 현재 상태 |
| --- | --- | --- | --- |
| M32-W01 | 공통 | Capability·자원·예제 inventory와 유한 시험 계약 | **완료** |
| M32-W02 | M32-A | LE Power Control·Path Loss·Tx Power Report | **완료** |
| M32-W03 | M32-A | Subrating·SCA·Frame Space·Shorter Interval·확장 feature | **완료** |
| M32-W04 | M32-A | 광고/list/identity·EAD·coding·자원 규모 확장 | **완료 — ADV·PRIV·EAD exact HIL PASS** |
| M32-W05 | M32-A | Nordic LLPM·QoS·시간 동기·event·radio notification·experimental ACL | **완료 — 세 적용 시험군 exact HIL PASS, Flushable ACL unsupported/HOLD** |
| M32-W06 | M32-B | Mesh provisioning·역할·model·settings·security 기반 | **완료 — 세 보드 구성·500/500 ACK·negative·STOP PASS** |
| M32-W07 | M32-B | Mesh 1.1 관리·privacy·bridging 기능 | **완료 — Remote Provisioning·350/350 관리 operation·negative·STOP PASS** |
| M32-W08 | M32-B | BLOB·Mesh DFU·Firmware Distribution | **완료 — BLOB·signed MDFU exact HIL PASS** |
| M32-W09 | M32-C | 최소 IEEE 802.15.4·ESB profile와 단독 TX/RX | **완료** |
| M32-W10 | M32-C | 허용 조합의 BLE/Mesh/802.15.4/ESB 공존 | **완료 — 세 내부 조합 exact HIL PASS** |
| M32-W11 | 공통 | 세 보드 기능 HIL·negative·회귀·유한 soak | **완료 — exact family 12/12·signed MDFU·M32-REG-01·M32-SOAK-01 PASS** |
| M32-W12 | 공통 | API·예제·증거 정합화와 M33/M38/M39 인계 | **완료 — 원장·문서·지원 gate·후속 인계 정합성 PASS** |

W02~W05와 W06~W08은 W01 계약 뒤 독립 가능한 범위를 병행한다. W10은 해당 protocol의 W09
단독 TX/RX 증거를 선행조건으로 사용한다. HOST-W07은 별도 분모이며 M32의 12개 묶음에 합산하지 않는다.
HOST-W07의 자동 검사·최종 인계 절차는 준비하되 Ubuntu/macOS PC를 중간에 연결하도록 요구하지 않는다.

## 3. M32-A 세부 구현 TODO

### M32-W01 — Capability와 실행 계약

- [x] M31-W01에서 확정한 `variants/nu54dk/ncs-v3.4.0-bluetooth-sample-parity.json`의 M32 소유 행을
  고정 SDK와 다시 대조한다. 공식 nRF54L15 target·일반 Host sample·미적용 sample을 모두 추적한다.
- [x] `variants/nu54dk/m32-ble-readiness.json`과 M32 착수 계약을 구현한다. 기능별 controller/Host
  Kconfig·API·upstream sample·Arduino 제공 경로·resource profile·예정 test ID를 연결한다.
- [x] Source candidate, NU54DK native build, Arduino build, runtime capability, 기능 HIL, 외부 peer
  interop 상태를 독립 필드로 정의하고 unknown·누락·중복·revision mismatch를 거부한다.
- [x] Master 원장의 case별 검증 책임·시점·개발/릴리스 blocker 필드를 연결한다. 사용자 후속 외장 실물
  case와 필수 구현/자동 검사를 분리하고 외장 실물 `NOT_RUN`을 PASS 또는 릴리스 차단으로 바꾸지 않는다.
  Ubuntu/macOS 실제 Host는 해당 OS를 지원할 후속 릴리스의 사용자 gate로 연결하며 중간 개발
  blocker 또는 M31 Windows 릴리스 blocker로 사용하지 않는다.
- [x] Capability parser, 정상/negative Host test, capability target image와 build matrix를 구현한다.
- [x] 기능별 연결·광고 set·identity·sync·Mesh node·buffer·RAM/RRAM 상한과 profile 충돌표를 고정한다.
- [x] 이 문서의 예정 test ID별 board role·반복/packet 분모·timeout·허용 손실·복구 상한·유한 재검증
  횟수를 시험 전에 readiness에 고정한다. 미확정 수치는 제품 보증이나 시험 PASS로 채우지 않는다.
- [x] SHA-256 probe identity·serial 경로·role·firmware revision을 대조한 한 보드 capability HIL을
  수행한다. Mapping이 불명확하면 target build까지 수행하고 실제 HIL을 `NOT RUN`으로 기록한다.

완료 근거는 [277번 기록](<04_검증 기록/277_M32_W01_capability_자원_시험_계약_완료.md>)과
[`w01-closure-audit.json`](<04_검증 기록/evidence/m32-w01-exact-35aabc84/w01-closure-audit.json>)이다.
Baseline/extended 2/2 build와 2/2 HCI query가 PASS했고 RAM/RRAM은 각각
61,364/199,564 B와 66,396/217,196 B다. 이는 W02 이후 기능별 연결 HIL PASS가 아니다.

### M32-W02 — LE Power Control와 Path Loss

- [x] Per-link LE Power Control request·local/remote Tx power read/report와 callback 수명주기를 구현한다.
- [x] Path Loss Monitoring의 threshold·hysteresis·minimum time·enable/disable·zone event를 구현한다.
- [x] RSSI 기반 application power-control 예제와 표준 LE Power Control 절차를 서로 다른 예제로 제공한다.
- [x] Unsupported peer, 범위 밖 power/threshold, stale handle, 종료 후 callback, 반복 enable/disable을 검증한다.
- [x] `path_loss_monitoring` central/peripheral와 `rssi_power_control` central/peripheral의 Arduino 역할
  예제를 제공한다. RF에서 관측한 event 값·범위와 Host synthetic zone event 검증을 따로 기록한다.
- [x] `M32-PWR-01`, `M32-PATH-01`에 실제 negotiated state·event·per-link 격리·복구 근거를 남긴다.

완료 근거는 [278번 기록](<04_검증 기록/278_M32_W02_LE_Power_Control_Path_Loss_완료.md>)과
[`w02-closure-audit.json`](<04_검증 기록/evidence/m32-w02-exact-9a7d0351/w02-closure-audit.json>)이다.
Exact `9a7d0351…`에서 v0.6.0 target 5/5와 공개 Arduino 예제 6/6을 빌드했고, 두 보드에서
remote Tx power report 40/40, Path Loss zone event 60/60, loss 0과 STOP 2/2를 확인했다.
외부 제품 peer 상호운용은 별도 `NOT_RUN`이며 W02 개발 PASS로 확대하지 않는다.

### M32-W03 — 최신 연결 timing와 feature 교환

- [x] Connection Subrating의 default/request·continuation·latency·timeout·change event를 구현한다.
- [x] Sleep Clock Accuracy Update의 controller 지원성과 고정 Host 요청·report API 부재를 분리해 제공한다.
- [x] Frame Space Update의 요청·협상 결과·지원 PHY/조합과 미지원 peer fallback을 구현한다.
- [x] 표준 Shorter Connection Interval의 요청·실제 interval·controller 조건과 상한을 노출한다.
- [x] LL Extended Feature Set의 local/remote 조회·분류·미지원 feature 거부를 구현한다.
- [x] Connection parameter·supervision·channel map/classification·event length 관련 적용 API를 조사하고
  제공 경로를 확정한다. 기존 PHY/DLE/MTU 요청과 결합한 지원 조합을 matrix에 넣는다.
- [x] `subrating`, `shorter_conn_intervals`, `throughput`의 Arduino 예제와 결과 단위·측정 방법을 제공한다.
- [x] 협상 거부·잘못된 조합·disconnect 중 request·다중 link 오귀속·controller 자원 부족을 검증한다.
- [x] `M32-SUB-01`, `M32-SCA-01`, `M32-TIME-01`, `M32-FEAT-01`을 역할별로 실행한다.

구현 commit `30258a57…`의 API·예제와 software 검증에 이어 exact `9b3badc4…`에서 central/peripheral
target 2/2와 두 보드 HIL을 완료했다. Packet 2,000/2,000·loss 0, Subrating·Shorter Interval 역할별
20/20, Frame Space central 20회·peripheral 2회, feature 40 sample, channel classification 20회,
최대 packet/procedure gap 9/907 ms와 STOP 2/2가 PASS했다. SCA controller procedure는 20 sample로
확인했지만 고정 Host 요청·report API는 없으므로 `unsupported_host_initiator_api`로 닫아 stable 지원
catalog에서 제외한다. 완료 근거는 [288번 기록](<04_검증 기록/288_M32_W03_연결_timing_feature_exact_HIL_완료.md>)과
[`w03-closure-audit.json`](<04_검증 기록/evidence/m32-w03-exact-9b3badc4/w03-closure-audit.json>)이다.

### M32-W04 — 광고·identity·privacy와 자원 규모

- [x] Multiple Advertising Sets의 생성·개별 payload/PHY/SID·시작·중지·삭제와 generation handle을 구현한다.
- [x] Legacy/extended, active/passive scanning, duplicate filtering, scan과 initiating의 동시 실행을 검증한다.
- [x] Directed Advertising의 peer identity·timeout·privacy·재연결을 구현한다.
- [x] Filter Accept List, resolving list, periodic advertiser list의 용량·추가/삭제·활성 중 변경 제약을 구현한다.
- [x] Multiple Identities의 생성·선택·reset/delete·identity별 광고·bond/RPA 격리를 구현한다.
- [x] Advertising Coding Selection의 controller 지원성·coded PHY 옵션·상호 배타 조건을 구현한다.
- [x] Encrypted Advertising Data의 encrypt/decrypt·session key/IV·randomizer/RPA 연계와 무결성 실패를
  검증한다. 단순 source 존재를 nRF54L15 전용 sample PASS로 바꾸지 않는다.
- [x] Connection·advertising set·periodic sync·identity의 기본/확장 profile를 만들고 RAM/RRAM 사용량과
  실제 검증 상한을 공개한다. Kconfig 최대값 또는 upstream 예제의 set 수를 runtime 실적으로 복사하지 않는다.
- [x] ARF-01의 BLE role-budget(C1P1/C2P0/C0P2)을 이 작업의 resource preset으로 통합한다. 기존
  기본 2-link/1-advertising-set 계약을 보존하고 확장 preset의 실제 상한을 W01에서 고정한다.
  자원이 부족하면 fail-closed로 거부하며 ARF-01을 별도 후속 구현 분모로 중복 계산하지 않는다.
- [x] `multiple_adv_sets`, `peripheral_with_multiple_identities`, `scanning_while_connecting`, directed/list,
  encrypted advertising의 Arduino 예제를 제공한다.
- [x] Over-capacity·잘못된 identity/SID·동일 resource 재사용·변조 EAD·잘못된 key/IV·stale callback을 Host에서 검증한다.
- [x] `M32-ADV-01`, `M32-PRIV-01`, `M32-EAD-01`을 실행하고 scale별 수신 증거를 남긴다.

구현 commit `b8d0c0c1…`에서 W04 공개 예제 12/12, Host 회귀 21 test, 광고·동시 scan/initiate와
C1P1/C2P0/C0P2 target build 5/5가 PASS했다. 세 자원 preset의 RAM/RRAM은 각각
65,280/226,048 B, 60,344/218,716 B, 61,248/207,276 B로 고정 상한 안이다. 후속 exact
`4af5b15a…`에서 EAD 인증 20/20·raw report 400/400, `3829f144…`에서 ADV packet 600/600,
`386bc379…`에서 PRIV packet 200/200과 각 negative·STOP을 CMSIS-DAP v2로 완료했다. 첫 PRIV
timeout FAIL은 원본 증거로 보존하고 peer RPA/FAL 경계를 수정한 뒤 재시험했다. software/build 경계는
[279번](<04_검증 기록/279_M32_W03_W04_software와_HIL_blocker.md>), EAD 진척은
[289번](<04_검증 기록/289_M32_W04_EAD_exact_HIL_진척.md>), 최종 완료는
[290번](<04_검증 기록/290_M32_W04_광고_identity_privacy_exact_HIL_완료.md>)이 소유한다.

### M32-W05 — Nordic 확장과 진단

- [x] Nordic LLPM 요청·negotiation·fallback과 표준 shorter interval의 다른 설정 경로를 제공한다.
- [x] QoS Connection Event Reports와 QoS Channel Survey의 enable/disable·report·channel별 결과를 제공한다.
- [x] `conn_time_sync`의 역할·timestamp·clock 도메인·오차 관측을 Arduino 예제로 옮긴다.
- [x] Event Trigger의 예약·cancel·resource/DPPI ownership과 callback 맥락을 명시한다.
- [x] Radio Notification callback의 등록·해제·제한된 callback 작업과 link 종료 경계를 구현한다.
- [x] LE Flushable ACL Data의 고정 SDK experimental 지원성을 판정하고 기본 OFF profile을 유지한다.
  Host TX 경로가 없으면 buffer 수명주기·flush/drop을 가장하지 않고 명시적 unsupported 경계를 제공한다.
- [x] `llpm`, `event_trigger`, `radio_notification_cb`, QoS·sync 예제에 profile와 Nordic peer 요구를 명시한다.
- [x] Overflow·취소 뒤 event·중복 예약·부족한 radio slot·미지원 vendor feature·종료 후 buffer 접근을 검증한다.
- [x] `M32-NORDIC-01`, `M32-SYNC-01`, `M32-EVENT-01`의 적용 행을 두 보드에서 실행한다.
- [x] `M32-ACL-01`은 controller experimental=true와 Host TX=false를 실측하고 기능 실행 불가
  `HOLD`로 닫는다. 지원 기능 PASS나 packet 전송 PASS로 계산하지 않는다.

구현 commit `85da6122…`에서 W05 공개 예제 8/8, 관련 Host 회귀 21 test, Nordic target contract가
PASS했다. Exact revision `f813356c…`에서는 LLPM mode와 vendor interval 정규화 결함을 교정하고
CMSIS-DAP v2 두 보드 HIL을 완료했다. 역할별 QoS 200, survey 20, anchor 1,000, event 200,
radio prepare 200, LLPM 1,000 us를 확인했으며 최대 anchor gap 3,999 us·event gap 1 ms와
overflow/negative/disable 뒤 callback 0·STOP을 PASS했다. Flushable ACL은 controller experimental,
Host TX=false, usable=false로 `unsupported/HOLD`다. 상세 결과는
[280번 기록](<04_검증 기록/280_M32_W05_Nordic_확장_software와_HIL_blocker.md>)과
[`w05-closure-audit.json`](<04_검증 기록/evidence/m32-w05-exact-f813356c/w05-closure-audit.json>)이 소유한다.

## 4. M32-B Mesh 세부 구현 TODO

### M32-W06 — Mesh 기반

- [x] PB-ADV/PB-GATT, provisioner/node, provisioning 완료·취소·실패 복구를 구현한다.
- [x] Relay, Friend, Low Power Node, GATT Proxy 역할과 역할별 memory·message queue·지원 조합을 제공한다.
- [x] Foundation/configuration/health와 generic·sensor·light 등 고정 NCS 적용 model catalog를 작성하고
  client/server 역할별 예제를 배정한다. Model마다 구현·build·runtime 상태를 남긴다.
- [x] Publication/subscription, acknowledged/unacknowledged message, segmented transport, TTL·retransmit,
  replay protection·sequence·IV Update·Key Refresh·settings 복원을 구현·검증한다.
- [x] 세 보드를 provisioner+두 node의 순차 topology로 사용해 두 node 구성과 역할별 payload를 확인한다.
- [x] wrong AppKey·invalid destination·unprovisioned access와 ACK/Configuration timeout 유한 재시도를
  실기 검증하고, stack 내부 replay/settings·API 범위 밖 model/opcode는 Zephyr 설정과 Host 검사가 소유한다.
- [x] `M32-MESH-01`, `M32-MESHSEC-01`에 실제 provisioning·300+200 message·복구·STOP 결과를 연결한다.

software·NU54DK native target·12개 Arduino 예제 build는 exact
`ab3f682547836afd33d6c09612f027266b144f90`에서 완료했다. Generic OnOff는
client/server를 모두 제공하고 나머지 SIG model은 client와 peer server 역할 경계를
명시한다. `cb73cb08…`에서 provisioner+두 node의 500-message HIL image·V2 runner와
provisioner CDB reset lifecycle을 추가했다. 이후 stack 증설, 두 beacon 선행 수집, 비동기
provisioning 재시도 계측을 반영한 `6af305d3187f…`에서 세 역할 image 3/3은 PASS했다. 두 번째
node 실패는 CDB node slot 2개가 local provisioner와 첫 remote node로 소진된 것이 원인이었고,
`70a687698bdd…`에서 3으로 교정한 image 3/3과 짧은 세 보드 시험에서 두 remote node 모두
provisioning됐다. `2b9dfce2d06d…`에서는 W06 최소 `3/1/2` profile과 Arduino provisioner 확장
`33/4/8` profile, CDB/local/model key 용량 계약을 분리했다. 이어 PB-ADV 종료 순서와 유한
Configuration/ACK 재시도를 교정한 `45715e42…` exact 실행에서 두 node 구성, 300+200 message,
500/500 ACK, 최대 지연 121 ms, negative·STOP을 PASS했다. 상태와 closure는
[281번 기록](<04_검증 기록/281_M32_W06_Mesh_기반_software와_HIL_blocker.md>)이 소유하며,
[291번 기록](<04_검증 기록/291_M32_W06_second_node_provisioning_FAIL과_재부팅_인계.md>)은 과거
재부팅 인계 기록으로 보존한다.

### M32-W07 — Mesh 1.1 기능

- [x] Remote Provisioning client/server의 scan·link·provision 절차와 timeout을 구현한다.
- [x] SAR Configuration client/server의 segmented RX/TX 조건·한계·잘못된 parameter를 검증한다.
- [x] Opcodes Aggregator client/server의 sequence·길이·부분 오류·응답 귀속을 검증한다.
- [x] Large Composition Data client/server의 page·offset·분할·크기 상한을 검증한다.
- [x] Private Beacon과 On-Demand Private Proxy의 설정·수명주기·privacy 관측을 구현한다.
- [x] Solicitation PDU와 solicitation replay protection list 관련 설정·재사용/재생 거부를 검증한다.
- [x] Subnet Bridging의 table·forwarding·key·허용 subnet·삭제/재설정 경계를 검증한다.
- [x] 고정 SDK의 나머지 Mesh Kconfig·model·sample을 전수 대조해 신규 항목마다 구현 또는 미적용 사유를
  원장에 등록한다. 다른 버전 문서의 Mesh 기능을 v3.4.0 지원으로 자동 포함하지 않는다.
- [x] 기능마다 client/server 또는 source/destination 역할 예제·negative를 제공하고 `M32-MESH11-01`의
  하위 case ID를 고정한다. 세 보드로 검증하지 못하는 topology는 요구 보드 수를 기록한다.

구현 commit `8da1ff4e…`에서 일곱 기능군의 bounded 공개 API·client/server composition과
Arduino 예제 13/13, Host·native target build가 PASS했다. Target RAM/RRAM은
71,265/283,300 B다. 고정 SDK W07 선택 기능은 모두 소유 행에 연결했고 Directed Forwarding은
고정 source 부재로 지원 승격하지 않는다. `c499aa89…`에서 PB-ADV server 선행 추가 →
PB-Remote target 추가, 일곱 기능군 350 operations·네 negative·STOP의 세 역할 image와
V2 exact runner를 추가했다. CDB capacity·link close 순서·SRPL AppKey bind·Aggregator·
Proxy Solicitation을 교정한 `f95cca6c…` exact 실행에서 Remote Provisioning,
350/350 operation, 네 negative class와 세 역할 STOP을 모두 PASS했다. 두 subnet
end-to-end forwarding과 외부 peer interop는 현재 3보드 완료 분자에 포함하지 않고
`NOT_RUN`으로 보존한다. 상세 경계는
[282번 기록](<04_검증 기록/282_M32_W07_Mesh_1.1_software와_HIL_blocker.md>)이 소유한다.

### M32-W08 — BLOB와 Mesh DFU

- [x] BLOB Transfer client/server, block/chunk, pull/push 적용성·분할·중단/재개·digest 확인을 구현한다.
- [x] Mesh DFU target, initiator, distributor/Firmware Distribution의 역할별 profile와 예제를 제공한다.
- [x] NU54DK 외장 flash 미탑재 조건에서 object 크기·RRAM/partition·image 저장·settings 예산을 판정한다.
  외장 저장소가 필요한 variant도 사용 가능한 template·설정·연결 안내·자동 검사를 제공한다.
  그 variant의 실제 외장 저장소 운용·검증만 사용자 후속·릴리스 비차단 `NOT_RUN`으로 인계한다.
- [x] M30의 서명·image/key·rollback 계약을 재사용하고 Mesh transport의 인증·배포 권한·metadata·version·
  hash 검증·부분 image·잘못된 target/키·미확인 image 복귀를 추가 검증한다.
- [x] Transport cancel·peer loss·다시 시작·정상 재부팅 복구를 자동화한다. 새로운 실제 전원 차단 확장은
  v0.8.0의 M36으로 인계하며 M32/v0.6.0이나 SDK 전용 v0.7.0의 추가 기능으로 넣지 않는다. 별도 정책·장치·사용자
  요청 없이 실행하지 않고, reset 시험으로 전원 차단 PASS를 기록하지 않는다.
- [x] `M32-BLOB-01`, `M32-MDFU-01`의 role image·object/image hash·분모·negative 결과를 보존한다.
- [x] M36으로 partition·배포 transport·복구 경계·남은 외장 storage variant를 인계한다.

구현 commit `1a57eaae…`에서 내부 inactive slot 기반 BLOB Client/Server, Mesh DFU Target,
Firmware Distributor와 SHA-256·metadata·MCUboot test-upgrade 경계를 제공했다. Signed Arduino 예제
4/4, Host 5/5, exact native target build가 PASS했고 RAM/RRAM은 72,460/277,712 B다. 외장 flash는
비활성 template와 적용 안내만 제공하며 실제 운용은 사용자 후속 `NOT_RUN`이다. CMSIS-DAP DP/AP
접근 중단으로 당시 실제 transfer·배포·rollback·negative는 `NOT_RUN`이었고 W08은 완료로 계산하지 않았다.
`b6d1630c…`에서 BLOB·DFU·Distributor model의 foundation binding 경로를 공개했고,
`19c390ba…`에서 32 KiB object × 10회 × 두 target, target별 2,560 chunk, suspend/resume,
wrong AppKey·bad digest와 STOP을 고정한 세 역할 BLOB HIL image·CMSIS-DAP v2 runner를 추가했다.
세 image build, M32 Host 77/77과 contract check는 PASS했다. 이어 `bceb1817…`에서 ECDSA P-256
MCUboot·security counter 1→2, Distributor→두 target 5회/10 target, wrong key·wrong image·partial
image·rollback, 마지막 target A confirm/target B rollback을 검증하는 `M32-MDFU-01:primary` image와
V2 전용 runner를 추가했다. Clean exact source의 네 sysbuild와 공통 public key·candidate hash/size
고정 검사는 PASS했고 당시 M32 Host 94/94와 contract check도 PASS했다. Build 감사 원본은
[`build-audit.json`](<04_검증 기록/evidence/m32-w08-mdfu-preparation-bceb1817/build-audit.json>)에 남긴다.
W06·W07 완료 뒤 `8dcb033e…` exact BLOB 실행에서 client·target A와 target B 내부 상태 모두
10/10회, client 5,120/target별 2,560 chunk와 digest를 완료했다. 다만 target B의 마지막
`RESULT/END`를 수집하지 못해 runner는 `serial progress timeout` FAIL을 기록했고 session STOP
증거도 남기지 못했다. VCOM 재개방 경합은 원인 후보이며 정확한 유실 위치는 미확정이다.
target B의 `session_complete=1`, `failed=0`, CFSR·HFSR 0을 CMSIS-DAP v2 attach로 확인했다.
STOP 전 최종 결과를 5초마다 반복하고 동일 중복 RESULT를 허용하도록 보강했다.

2026-10-02 새 PC의 clean source `40e4c46b…`에서 BLOB 10/10회, client 5,120 chunk,
target별 2,560 chunk, suspend/resume·wrong AppKey·bad digest·세 역할 STOP/cleanup을 exact PASS했다.
같은 source의 첫 signed MDFU는 343,511-byte 전체 Mesh candidate와 343,495-byte partial negative
때문에 iteration 1이 1,800초 안에 끝나지 못해 FAIL했다. 세 probe의 DP/AP·APPROTECT는 정상이었다.
Candidate를 최소 MCUboot/settings oracle로 분리해 55,040-byte signed image로 줄이고 partial
negative를 4,096 byte로 제한했다. Apply 재부팅·rollback 뒤 persisted state 복구와 10,800초 유한
세션 상한을 보강한 clean source `e0a1b7fd…`에서 5회·두 target 10/10 배포, candidate 부팅 10회,
rollback 9회, 마지막 target A confirm·target B rollback, wrong image/key·partial image 거부와
세 역할 STOP/cleanup을 모두 exact PASS했다. W08 closure audit은
[`w08-closure-audit.json`](<04_검증 기록/evidence/m32-w08-mdfu-e0a1b7fd-exact/w08-closure-audit.json>)이다.
과거 FAIL은 소급 변경하지 않는다.
상세 과거 경계는 [283번 기록](<04_검증 기록/283_M32_W08_BLOB_Mesh_DFU_software와_HIL_blocker.md>),
현재 PASS·timeout 진단은 [294번 기록](<04_검증 기록/294_M32_W08_BLOB_PASS와_MDFU_timeout_진단.md>)이 소유한다.

## 5. M32-C와 통합 TODO

### M32-W09 — 최소 802.15.4/ESB 단독 radio

- [x] IEEE 802.15.4 최소 TX/RX peer와 ESB PTX/PRX·ACK·재전송·payload 경로를 검증용 profile로 구현한다.
- [x] RADIO·clock·timer·DPPI·MPSL 소유권, profile 전환·cancel·STOP·buffer 반환을 명시한다.
- [x] Packet sequence/hash, ACK·손실·중복·오류·채널/rate 경계와 bounded recovery를 검증한다.
- [x] `M32-154-01`, `M32-ESB-01`의 두 보드 단독 실기부터 완료한다.
- [x] M38/M39 공개 API·일반 예제 확장에 재사용할 최소 backend와 검증 전용 예제를 연결한다.

구현 revision `82361413bc0377871fffd74f4a23eca5a98a2abb`에서 두 전용 profile과 공개 library,
IEEE 802.15.4 TX/RX·ESB PTX/PRX 예제 4/4, 두 native target와 Host 계약이 PASS했다. Arduino
최대 footprint는 IEEE 802.15.4 RAM/RRAM 38,748/97,166 B, ESB 27,876/66,640 B다. direct
radio owner를 분리하고 같은 image의 두 protocol 조합은 fail-closed했다. Exact revision
`c817a27ed765641bdf41e4e386664a8aa8c173f9`의 CMSIS-DAP v2 두 보드 HIL에서 protocol별
2,000/2,000 ACK·unique, loss/corrupt/drop 0, negative와 네 역할 STOP을 PASS했다. 상세 결과는
[284번 기록](<04_검증 기록/284_M32_W09_802154_ESB_software와_HIL_blocker.md>)과
[`w09-closure-audit.json`](<04_검증 기록/evidence/m32-w09-exact-c817a27e/w09-closure-audit.json>)이 소유한다.

### M32-W10 — 공존

- [x] BLE connection/Mesh/802.15.4/ESB 조합별 controller·MPSL 지원성, role·peer 수·RAM·radio budget을 판정한다.
- [x] 허용 조합의 traffic·priority·scheduler·slot 거부·starvation·지연·drop·복구 상한을 고정한다.
- [x] 세 보드에서 실행 가능한 조합을 선택하고 protocol별 sequence/hash·서비스 간격·오류를 동시에 기록한다.
- [x] 미지원 controller 조합·double ownership·slot 부족·다른 protocol 종료/재시작·주요 BLE 기능 회귀를 검증한다.
- [x] 1-wire 등 외부 coexistence 신호도 실제 연결용 구현·예제·설정/연결 안내·자동 검사를 제공한다.
  외부 peer와 결선의 실물 운용·검증은 사용자 후속·릴리스 비차단 개별 행으로 관리한다.
  내부 MPSL 공존 결과를 외부 arbitration 실기 PASS로 확대하지 않는다.
- [x] `M32-COEX-01`에 각 조합의 개별 결과를 연결한다. 모든 protocol의 동시 실행을 하나의 PASS로 선언하지 않는다.

구현 revision `7e756311d3ada2907820732ebec0a7b7a14b0e0c`에서 BLE+Mesh, BLE+IEEE 802.15.4,
BLE+ESB candidate와 외부 1-wire 전용 profile·공개 telemetry API·예제 4개·native target·Host 계약이
PASS했다. protocol별 sequence/hash·drop·timeslot failure·starvation·service gap을 bounded 통계로
분리하고 direct radio double ownership은 fail-closed했다. 외부 template은 P1.10(P4-8) output과
P1.14(P4-12) grant input을 사용하며 DAP UART pin을 피한다. 당시 W09 단독 HIL 뒤 조합별
packet·복구·STOP 실기는 `NOT_RUN`이었고, 아래 clean exact 실행에서 별도로 완료했다.
Revision `042cfb32de7d…`에서 BLE+IEEE 802.15.4, BLE+ESB, BLE+Mesh의 DUT·radio/Mesh peer·
BLE peer 아홉 image와 CMSIS-DAP v2 전용 순차 runner를 준비했다. 조합별 protocol당 4,000 frame,
중간 BLE reconnect·상대 radio/Mesh restart, negative·STOP을 고정했고 아홉 target build와 M32 Host
81/81은 PASS했다. 당시 CMSIS-DAP v2 DP/AP preflight를 통과하고 W06~W08 뒤 실행하도록 준비했다.
Clean `512b027a…`의 아홉 image build와 세 내부 조합 exact HIL은 protocol별 4,000/4,000,
loss·corrupt·starvation 0, reconnect·restart 각 1, 최대 gap 151/124 ms 이하와 아홉 역할 STOP을
PASS했다. 외부 1-wire 실제 결선·외부 peer 상호운용은 사용자 후속 `NOT_RUN`이다. 상세 경계는
[285번 기록](<04_검증 기록/285_M32_W10_무선_공존_software와_HIL_blocker.md>)과
[`w10-closure-audit.json`](<04_검증 기록/evidence/m32-w10-exact-512b027a/w10-closure-audit.json>)이 소유한다.

### M32-W11 — 회귀·세 보드 HIL

- [x] M19~M31 GAP/GATT/security/DFU/ISO/audio/DF/CS의 영향받는 profile·자원 조합을 회귀한다.
- [x] W02~W10의 각 target와 Arduino 예제를 build하고 역할별 기능 HIL·negative·cancel/reconnect를 실행한다.
- [x] 제한 시간·요청/실제 실행 시간·기대/수신 packet·실패 원본을 가진 대표 유한 soak를 실행한다.
- [x] `M32-REG-01`, `M32-SOAK-01`에서 cross-link/resource/security 오귀속·payload corruption·cleanup
  failure 0을 확인하고 손실/지연은 W01에서 고정한 기능별 한계로 판정한다.
- [x] W02~W10 native target 62/62와 Arduino 예제 74/74 build를 고정 source에서 회귀했다.
- [x] 전체 Host regression 1,689/1,689·관련 unit/negative를 수행했다.
- [x] 세 역할 유한 soak image·CMSIS-DAP v2 runner와 12-family exact evidence closure를 준비했다.
- [x] 문서 gate·JSON schema/drift를 최종 갱신 source에서 다시 수행한다.

Build·Host software 회귀와 exact HIL closure는
[286번 기록](<04_검증 기록/286_M32_W11_software_회귀와_HIL_soak_blocker.md>)이 소유한다.
Clean `94f02544…`에서 native 62/62, exact SHA CI 8 job, 12-family **12/12**, BLOB 10회,
signed MDFU 5회×두 target 10/10과 1,800초 soak를 PASS했다. Privacy 첫 실행의 identity_b
`session_timeout` 원본은 보존했고 같은 clean SHA·image의 허용된 1회 재실행은 A/B 20/20과 peer
200/200을 PASS했다. 세 보드 access preflight는 모두 AHB debug enabled였으므로 승인받은
ERASEALL은 이번 exact 실행에서 필요하지 않았고 실행하지 않았다. W11은 완료다.

### M32-W12 — 마감·인계

- [x] 12개 작업 묶음과 기능별 필수 test case의 구현·build·HIL·지원 제한을 대조한다.
- [x] 예제 catalog·README·API/profile·resource matrix·기계 원장·실행 기록의 상태/수치/링크를 맞춘다.
- [x] Source candidate 또는 build-only 행이 지원 catalog로 잘못 승격되는 것을 gate에서 차단한다.
- [x] M33에 설치용 예제·profile·known limitation·cross-vendor NOT RUN 목록을 인계한다.
- [x] M36에 Mesh update/storage, M38/M39에 최소 radio/public 확장, M40/M42에 적용 공존 조합을 인계한다.
- [x] HOST-W07 자동 검사 결과와 사용자용 최종 실물 검증 절차를 별도 표로 연결한다. Ubuntu/macOS
  설치·USB·serial·debug 실기는 해당 OS를 포함할 후속 릴리스 때 사용자가 수행한다. 그때까지 `NOT_RUN`으로 유지하되
  중간 PC 연결을 요구하거나 M32 완료를 차단하지 않는다. 해당 OS 최종 지원 gate는 유지한다.

자동 정합성 감사·지원 승격 gate·후속 인계는
[287번 기록](<04_검증 기록/287_M32_W12_정합성_감사와_후속_인계.md>)이 소유한다. HOST-W07은
별도 분모로 인계했고 M32를 차단하지 않았다. 현재 진행은 다중 Host 계약을 따른다. W11 exact software·12-family HIL·
signed MDFU·soak는 PASS했다. W12의 문서·원장·예제·지원 후보·후속 인계 최종 정합성 감사도
PASS했으며 M32는 **12/12 완료**다.

## 6. 시험 ID와 판정 입력

아래 ID는 구현 전 예약하고 W01에서 하위 case·정량 입력을 확정한 시험 그룹이다.
실제 결과는 [기계 원장](../variants/nu54dk/m32-ble-readiness.json)에서 관리하며,
문서 행 수를 HIL test 완료 수로 계산하지 않는다.

| 시험 ID | 최소 구성 | 필수 관측·negative |
| --- | --- | --- |
| M32-CAP-01 | 1보드 | Source/HCI·revision·profile 대조, 누락/중복/미지원 판정 |
| M32-PWR-01 / M32-PATH-01 | 2보드 | Link별 요청/report/zone·enable/disable, 잘못된 threshold·unsupported peer |
| M32-SUB-01 / M32-SCA-01 | 2보드 | Negotiated 상태·event·fallback, stale link·범위 밖 값 |
| M32-TIME-01 / M32-FEAT-01 | 2보드 | Frame space/interval/PHY/DLE·확장 feature·channel control, 금지 조합 |
| M32-ADV-01 / M32-PRIV-01 | 2~3보드 | Set/identity/list별 수신·RPA·용량·동시 scan/initiate, cross-identity 오귀속 |
| M32-EAD-01 | 2보드 | Payload/무결성·randomizer, 변조·wrong key/IV·잘못된 길이 |
| M32-NORDIC-01 / M32-SYNC-01 | 2~3보드 | LLPM·QoS·timestamp·관측 오차, 미지원 peer·overflow |
| M32-EVENT-01 / M32-ACL-01 | 1~2보드, 경로별 결선 가능 | Trigger/notification·flush/drop·buffer, cancel 뒤 접근·default-off |
| M32-MESH-01 / M32-MESHSEC-01 | 3보드 순차 topology | Provisioning/model/security/settings, malformed·replay·wrong key |
| M32-MESH11-01 | 기능별 2~3보드, 초과 topology 별도 | 일곱 기능군별 case·관리 변경·거부·복구 |
| M32-BLOB-01 / M32-MDFU-01 | 역할별 2~3보드 | Object/image hash·분할/재개·서명·rollback, 잘못된 object/image |
| M32-154-01 / M32-ESB-01 | 2보드 | 각 radio 단독 TX/RX·ACK·hash·STOP, 채널/길이 경계 |
| M32-COEX-01 | 조합별 2~3보드 | Protocol별 서비스 간격·손실·복구, starvation·double ownership |
| M32-REG-01 / M32-SOAK-01 | 최대 3보드 | 이전 기능 회귀·유한 부하·자원 회수·실패 원본 |

각 case는 최소한 `iterations`, `timeout_s`, payload/packet 분모, 허용 loss/latency,
`recovery_timeout_s`, 즉시 중단 오류와 유한 재검증 정책을 가진다. 누락되면 실행을 차단한다.
실제 power cut을 수행하는 새로운 case는 M36 후속 범위다. M31 v0.5.0 및 M32 후속 개발·릴리스는 그
새 시험의 사용자 실행을 기다리지 않는다. 후속 실행 시 별도 정책·fixture를 기록하고
M30-POWER-01의 고정 4지점 × 3회 완료 이력과 합치지 않는다.

## 7. 증거·완료 규칙

- Probe UID 원문은 채팅·문서·로그에 노출하거나 저장하지 않는다. 실행기는 메모리 내 선택값만 사용하고
  SHA-256 identity, serial 경로, role, exact Core/board/NCS/Zephyr/toolchain와 image hash를 기록한다.
- 여러 probe 중 임의 선택을 금지한다. 실제 시험 직전에 identity/serial/role/firmware를 대조하고
  배타 lock·watchdog·유한 command lease·STOP/자원 반환을 확인한다.
- 자동 mass erase/recover·전체 flash 초기화·임의 GPIO·전원 차단을 수행하지 않는다. 필요한 결선·장치가
  없으면 그 case를 `NOT RUN`으로 기록하고 독립 작업을 진행한다.
- 실패 시도별 원본 log·nonce·명령·판정·hash를 보존하고 후속 성공으로 덮어쓰지 않는다.
- `unresolved`, `applicable`, `experimental`, `unsupported`, `not_applicable`은 master의
  target 적용성 값이다. SDK maturity 근거와 실행 결과 `PASS`, `FAIL`, `NOT_RUN`은 별도 필드다.
  `unsupported`는 성공한 RF 기능 수에 포함하지 않는다.
- M32 구현 완료는 12/12 작업, 적용 필수 기능/예제의 실제 증거와 명시적 제한·인계가 모두 갖춰질 때
  판정한다. 필수 구현·예제·자동 검증과 사용자 후속 외장 실물 행의 분모를 분리한다. 사용자 후속
  실물 미검증은 PASS가 아니지만 M32 개발·릴리스 blocker도 아니다. SDK 제약·미지원은 근거 없이
  사용자 후속으로 넘기지 않는다. Ubuntu/macOS 실물은 최종 사용자 Host 지원 gate이며,
  각 후속 버전의 공개 승인·qualification은 자동화 장비 조건과 독립된 절차다.
