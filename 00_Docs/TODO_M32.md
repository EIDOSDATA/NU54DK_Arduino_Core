# M32 실행 TODO — 최신 BLE 제어·Mesh 1.1·무선 공존

| 항목 | 내용 |
| --- | --- |
| 대상 제품선 | `v0.5.0` |
| 현재 구현 상태 | **계획 — 0/12 작업 묶음** |
| 하위 gate | M32-A Controller/Host·Nordic 확장, M32-B Mesh, M32-C 최소 radio·공존 |
| 선행·병행 | M31의 controller/resource 계약 인계, HOST-W07 자동 검사·최종 사용자 검증 절차 준비 독립 병행 |
| 고정 기준 | NCS `v3.4.0`, [CI lock](../tools/ci/ncs-3.4.0.lock.json)의 Zephyr·toolchain revision |
| 사용자 장비 조건 | NU54DK 3개 연결, 외부 RF·audio 계측 장비 없음; 실행 직전 실제 mapping 재확인 |
| 최종 갱신일 | 2026-09-16 |

기능·upstream 예제·제공 방식의 상세 원본은
[NCS Bluetooth 전체 기능과 예제 실행 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)이다.
이 문서는 그 범위를 구현 순서·체크리스트·예정 시험 ID에 배정한다. 전체 순서는
[제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>), 제품선 상태는
[v0.5.0 TODO](TODO_v0.5.0.md), 앞뒤 인계는 [M31 TODO](TODO_M31.md)와 [M33 TODO](TODO_M33.md)를 따른다.
문서 작성은 구현·build·HIL 완료 수에 포함하지 않는다.

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
  Ubuntu/macOS 실물 설치·USB·serial·debug는 사용자가 최종 릴리스 때 검증하며 중간 작업을 차단하지 않는다.

## 2. 작업 배치

| 작업 | 하위 gate | 구현·검증 범위 | 현재 상태 |
| --- | --- | --- | --- |
| M32-W01 | 공통 | Capability·자원·예제 inventory와 유한 시험 계약 | 미착수 |
| M32-W02 | M32-A | LE Power Control·Path Loss·Tx Power Report | 미착수 |
| M32-W03 | M32-A | Subrating·SCA·Frame Space·Shorter Interval·확장 feature | 미착수 |
| M32-W04 | M32-A | 광고/list/identity·EAD·coding·자원 규모 확장 | 미착수 |
| M32-W05 | M32-A | Nordic LLPM·QoS·시간 동기·event·radio notification·experimental ACL | 미착수 |
| M32-W06 | M32-B | Mesh provisioning·역할·model·settings·security 기반 | 미착수 |
| M32-W07 | M32-B | Mesh 1.1 관리·privacy·bridging 기능 | 미착수 |
| M32-W08 | M32-B | BLOB·Mesh DFU·Firmware Distribution | 미착수 |
| M32-W09 | M32-C | 최소 IEEE 802.15.4·ESB profile와 단독 TX/RX | 미착수 |
| M32-W10 | M32-C | 허용 조합의 BLE/Mesh/802.15.4/ESB 공존 | 미착수 |
| M32-W11 | 공통 | 세 보드 기능 HIL·negative·회귀·유한 soak | 미착수 |
| M32-W12 | 공통 | API·예제·증거 정합화와 M33/M38/M39 인계 | 미착수 |

W02~W05와 W06~W08은 W01 계약 뒤 독립 가능한 범위를 병행한다. W10은 해당 protocol의 W09
단독 TX/RX 증거를 선행조건으로 사용한다. HOST-W07은 별도 분모이며 M32의 12개 묶음에 합산하지 않는다.
HOST-W07의 자동 검사·최종 인계 절차는 준비하되 Ubuntu/macOS PC를 중간에 연결하도록 요구하지 않는다.

## 3. M32-A 세부 구현 TODO

### M32-W01 — Capability와 실행 계약

- [ ] M31-W01에서 만드는 `variants/nu54dk/ncs-v3.4.0-bluetooth-sample-parity.json`의 M32 소유 행을
  고정 SDK와 다시 대조한다. 공식 nRF54L15 target·일반 Host sample·미적용 sample을 모두 추적한다.
- [ ] `variants/nu54dk/m32-ble-readiness.json`과 M32 착수 계약을 구현한다. 기능별 controller/Host
  Kconfig·API·upstream sample·Arduino 제공 경로·resource profile·예정 test ID를 연결한다.
- [ ] Source candidate, NU54DK native build, Arduino build, runtime capability, 기능 HIL, 외부 peer
  interop 상태를 독립 필드로 정의하고 unknown·누락·중복·revision mismatch를 거부한다.
- [ ] Master 원장의 case별 검증 책임·시점·개발/릴리스 blocker 필드를 연결한다. 사용자 후속 외장 실물
  case와 필수 구현/자동 검사를 분리하고 외장 실물 `NOT_RUN`을 PASS 또는 릴리스 차단으로 바꾸지 않는다.
  Ubuntu/macOS 실제 Host는 사용자 최종 릴리스 gate로 연결하며 중간 개발 blocker로 사용하지 않는다.
- [ ] Capability parser, 정상/negative Host test, capability target image와 build matrix를 구현한다.
- [ ] 기능별 연결·광고 set·identity·sync·Mesh node·buffer·RAM/RRAM 상한과 profile 충돌표를 고정한다.
- [ ] 이 문서의 예정 test ID별 board role·반복/packet 분모·timeout·허용 손실·복구 상한·유한 재검증
  횟수를 시험 전에 readiness에 고정한다. 미확정 수치는 제품 보증이나 시험 PASS로 채우지 않는다.
- [ ] SHA-256 probe identity·serial 경로·role·firmware revision을 대조한 한 보드 capability HIL을
  수행한다. Mapping이 불명확하면 target build까지 수행하고 실제 HIL을 `NOT RUN`으로 기록한다.

### M32-W02 — LE Power Control와 Path Loss

- [ ] Per-link LE Power Control request·local/remote Tx power read/report와 callback 수명주기를 구현한다.
- [ ] Path Loss Monitoring의 threshold·hysteresis·minimum time·enable/disable·zone event를 구현한다.
- [ ] RSSI 기반 application power-control 예제와 표준 LE Power Control 절차를 서로 다른 예제로 제공한다.
- [ ] Unsupported peer, 범위 밖 power/threshold, stale handle, 종료 후 callback, 반복 enable/disable을 검증한다.
- [ ] `path_loss_monitoring` central/peripheral와 `rssi_power_control` central/peripheral의 Arduino 역할
  예제를 제공한다. RF에서 관측한 event 값·범위와 Host synthetic zone event 검증을 따로 기록한다.
- [ ] `M32-PWR-01`, `M32-PATH-01`에 실제 negotiated state·event·per-link 격리·복구 근거를 남긴다.

### M32-W03 — 최신 연결 timing와 feature 교환

- [ ] Connection Subrating의 default/request·continuation·latency·timeout·change event를 구현한다.
- [ ] Sleep Clock Accuracy Update의 요청/보고·지원성·link별 상태를 제공한다.
- [ ] Frame Space Update의 요청·협상 결과·지원 PHY/조합과 미지원 peer fallback을 구현한다.
- [ ] 표준 Shorter Connection Interval의 요청·실제 interval·controller 조건과 상한을 노출한다.
- [ ] LL Extended Feature Set의 local/remote 조회·분류·미지원 feature 거부를 구현한다.
- [ ] Connection parameter·supervision·channel map/classification·event length 관련 적용 API를 조사하고
  제공 경로를 확정한다. 기존 PHY/DLE/MTU 요청과 결합한 지원 조합을 matrix에 넣는다.
- [ ] `subrating`, `shorter_conn_intervals`, `throughput`의 Arduino 예제와 결과 단위·측정 방법을 제공한다.
- [ ] 협상 거부·잘못된 조합·disconnect 중 request·다중 link 오귀속·controller 자원 부족을 검증한다.
- [ ] `M32-SUB-01`, `M32-SCA-01`, `M32-TIME-01`, `M32-FEAT-01`을 역할별로 실행한다.

### M32-W04 — 광고·identity·privacy와 자원 규모

- [ ] Multiple Advertising Sets의 생성·개별 payload/PHY/SID·시작·중지·삭제와 generation handle을 구현한다.
- [ ] Legacy/extended, active/passive scanning, duplicate filtering, scan과 initiating의 동시 실행을 검증한다.
- [ ] Directed Advertising의 peer identity·timeout·privacy·재연결을 구현한다.
- [ ] Filter Accept List, resolving list, periodic advertiser list의 용량·추가/삭제·활성 중 변경 제약을 구현한다.
- [ ] Multiple Identities의 생성·선택·reset/delete·identity별 광고·bond/RPA 격리를 구현한다.
- [ ] Advertising Coding Selection의 controller 지원성·coded PHY 옵션·상호 배타 조건을 구현한다.
- [ ] Encrypted Advertising Data의 encrypt/decrypt·session key/IV·randomizer/RPA 연계와 무결성 실패를
  검증한다. 단순 source 존재를 nRF54L15 전용 sample PASS로 바꾸지 않는다.
- [ ] Connection·advertising set·periodic sync·identity의 기본/확장 profile를 만들고 RAM/RRAM 사용량과
  실제 검증 상한을 공개한다. Kconfig 최대값 또는 upstream 예제의 set 수를 runtime 실적으로 복사하지 않는다.
- [ ] ARF-01의 BLE role-budget(C1P1/C2P0/C0P2)을 이 작업의 resource preset으로 통합한다. 기존
  기본 2-link/1-advertising-set 계약을 보존하고 확장 preset의 실제 상한을 W01에서 고정한다.
  자원이 부족하면 fail-closed로 거부하며 ARF-01을 별도 후속 구현 분모로 중복 계산하지 않는다.
- [ ] `multiple_adv_sets`, `peripheral_with_multiple_identities`, `scanning_while_connecting`, directed/list,
  encrypted advertising의 Arduino 예제를 제공한다.
- [ ] Over-capacity·잘못된 identity/SID·동일 resource 재사용·변조 EAD·잘못된 key/IV·stale callback을 검증한다.
- [ ] `M32-ADV-01`, `M32-PRIV-01`, `M32-EAD-01`을 실행하고 scale별 수신 증거를 남긴다.

### M32-W05 — Nordic 확장과 진단

- [ ] Nordic LLPM 요청·negotiation·fallback과 표준 shorter interval의 다른 설정 경로를 제공한다.
- [ ] QoS Connection Event Reports와 QoS Channel Survey의 enable/disable·report·channel별 결과를 제공한다.
- [ ] `conn_time_sync`의 역할·timestamp·clock 도메인·오차 관측을 Arduino 예제로 옮긴다.
- [ ] Event Trigger의 예약·cancel·resource/DPPI ownership과 callback 맥락을 명시한다.
- [ ] Radio Notification callback의 등록·해제·제한된 callback 작업과 link 종료 경계를 구현한다.
- [ ] LE Flushable ACL Data의 고정 SDK experimental 지원성을 판정하고 기본 OFF profile, buffer 수명주기,
  flush 조건·drop counter·미지원 peer 오류를 구현한다.
- [ ] `llpm`, `event_trigger`, `radio_notification_cb`, QoS·sync 예제에 profile와 Nordic peer 요구를 명시한다.
- [ ] Overflow·취소 뒤 event·중복 예약·부족한 radio slot·미지원 vendor feature·종료 후 buffer 접근을 검증한다.
- [ ] `M32-NORDIC-01`, `M32-SYNC-01`, `M32-EVENT-01`, `M32-ACL-01`의 적용 행을 실행한다.
  외부 GPIO 결선이 필요한 upstream 동작은 route를 먼저 확정하고 해당 물리 경로만 별도 `NOT RUN`으로 남긴다.

## 4. M32-B Mesh 세부 구현 TODO

### M32-W06 — Mesh 기반

- [ ] PB-ADV/PB-GATT, provisioner/node, provisioning 완료·취소·실패 복구를 구현한다.
- [ ] Relay, Friend, Low Power Node, GATT Proxy 역할과 역할별 memory·message queue·지원 조합을 제공한다.
- [ ] Foundation/configuration/health와 generic·sensor·light 등 고정 NCS 적용 model catalog를 작성하고
  client/server 역할별 예제를 배정한다. Model마다 구현·build·runtime 상태를 남긴다.
- [ ] Publication/subscription, acknowledged/unacknowledged message, segmented transport, TTL·retransmit,
  replay protection·sequence·IV Update·Key Refresh·settings 복원을 구현·검증한다.
- [ ] 세 보드를 provisioner+두 node, Friend+LPN+peer 등 순차 topology로 사용해 역할별 payload를 확인한다.
- [ ] 잘못된 key/model/opcode·재전송/중복·unprovisioned access·stale address·settings 손상을 검증한다.
- [ ] `M32-MESH-01`, `M32-MESHSEC-01`에 실제 provisioning·message·재시작·복구 결과를 연결한다.

### M32-W07 — Mesh 1.1 기능

- [ ] Remote Provisioning client/server의 scan·link·provision 절차와 timeout을 구현한다.
- [ ] SAR Configuration client/server의 segmented RX/TX 조건·한계·잘못된 parameter를 검증한다.
- [ ] Opcodes Aggregator client/server의 sequence·길이·부분 오류·응답 귀속을 검증한다.
- [ ] Large Composition Data client/server의 page·offset·분할·크기 상한을 검증한다.
- [ ] Private Beacon과 On-Demand Private Proxy의 설정·수명주기·privacy 관측을 구현한다.
- [ ] Solicitation PDU와 solicitation replay protection list 관련 설정·재사용/재생 거부를 검증한다.
- [ ] Subnet Bridging의 table·forwarding·key·허용 subnet·삭제/재설정 경계를 검증한다.
- [ ] 고정 SDK의 나머지 Mesh Kconfig·model·sample을 전수 대조해 신규 항목마다 구현 또는 미적용 사유를
  원장에 등록한다. 다른 버전 문서의 Mesh 기능을 v3.4.0 지원으로 자동 포함하지 않는다.
- [ ] 기능마다 client/server 또는 source/destination 역할 예제·negative를 제공하고 `M32-MESH11-01`의
  하위 case ID를 고정한다. 세 보드로 검증하지 못하는 topology는 요구 보드 수를 기록한다.

### M32-W08 — BLOB와 Mesh DFU

- [ ] BLOB Transfer client/server, block/chunk, pull/push 적용성·분할·중단/재개·digest 확인을 구현한다.
- [ ] Mesh DFU target, initiator, distributor/Firmware Distribution의 역할별 profile와 예제를 제공한다.
- [ ] NU54DK 외장 flash 미탑재 조건에서 object 크기·RRAM/partition·image 저장·settings 예산을 판정한다.
  외장 저장소가 필요한 variant도 사용 가능한 template·설정·연결 안내·자동 검사를 제공한다.
  그 variant의 실제 외장 저장소 운용·검증만 사용자 후속·릴리스 비차단 `NOT_RUN`으로 인계한다.
- [ ] M30의 서명·image/key·rollback 계약을 재사용하고 Mesh transport의 인증·배포 권한·metadata·version·
  hash 검증·부분 image·잘못된 target/키·미확인 image 복귀를 추가 검증한다.
- [ ] Transport cancel·peer loss·다시 시작·정상 재부팅 복구를 자동화한다. 새로운 실제 전원 차단 확장은
  M36 후속으로 인계하며 M32/v0.5.0의 추가 필수 사용자 gate로 만들지 않는다. 별도 정책·장치·사용자
  요청 없이 실행하지 않고, reset 시험으로 전원 차단 PASS를 기록하지 않는다.
- [ ] `M32-BLOB-01`, `M32-MDFU-01`의 role image·object/image hash·분모·negative 결과를 보존한다.
- [ ] M36으로 partition·배포 transport·복구 경계·남은 외장 storage variant를 인계한다.

## 5. M32-C와 통합 TODO

### M32-W09 — 최소 802.15.4/ESB 단독 radio

- [ ] IEEE 802.15.4 최소 TX/RX peer와 ESB PTX/PRX·ACK·재전송·payload 경로를 검증용 profile로 구현한다.
- [ ] RADIO·clock·timer·DPPI·MPSL 소유권, profile 전환·cancel·STOP·buffer 반환을 명시한다.
- [ ] Packet sequence/hash, ACK·손실·중복·오류·채널/rate 경계와 bounded recovery를 검증한다.
- [ ] `M32-154-01`, `M32-ESB-01`의 두 보드 단독 실기부터 완료한다.
- [ ] M38/M39 공개 API·일반 예제 확장에 재사용할 최소 backend와 검증 전용 예제를 연결한다.

### M32-W10 — 공존

- [ ] BLE connection/Mesh/802.15.4/ESB 조합별 controller·MPSL 지원성, role·peer 수·RAM·radio budget을 판정한다.
- [ ] 허용 조합의 traffic·priority·scheduler·slot 거부·starvation·지연·drop·복구 상한을 고정한다.
- [ ] 세 보드에서 실행 가능한 조합을 선택하고 protocol별 sequence/hash·서비스 간격·오류를 동시에 기록한다.
- [ ] 미지원 controller 조합·double ownership·slot 부족·다른 protocol 종료/재시작·주요 BLE 기능 회귀를 검증한다.
- [ ] 1-wire 등 외부 coexistence 신호도 실제 연결용 구현·예제·설정/연결 안내·자동 검사를 제공한다.
  외부 peer와 결선의 실물 운용·검증은 사용자 후속·릴리스 비차단 개별 행으로 관리한다.
  내부 MPSL 공존 결과를 외부 arbitration 실기 PASS로 확대하지 않는다.
- [ ] `M32-COEX-01`에 각 조합의 개별 결과를 연결한다. 모든 protocol의 동시 실행을 하나의 PASS로 선언하지 않는다.

### M32-W11 — 회귀·세 보드 HIL

- [ ] M19~M31 GAP/GATT/security/DFU/ISO/audio/DF/CS의 영향받는 profile·자원 조합을 회귀한다.
- [ ] W02~W10의 각 target와 Arduino 예제를 build하고 역할별 기능 HIL·negative·cancel/reconnect를 실행한다.
- [ ] 제한 시간·요청/실제 실행 시간·기대/수신 packet·실패 원본을 가진 대표 유한 soak를 실행한다.
- [ ] `M32-REG-01`, `M32-SOAK-01`에서 cross-link/resource/security 오귀속·payload corruption·cleanup
  failure 0을 확인하고 손실/지연은 W01에서 고정한 기능별 한계로 판정한다.
- [ ] 전체 Host regression·관련 unit/negative·문서 gate·JSON schema/drift·`git diff --check`를 수행한다.

### M32-W12 — 마감·인계

- [ ] 12개 작업 묶음과 기능별 필수 test case의 구현·build·HIL·지원 제한을 대조한다.
- [ ] 예제 catalog·README·API/profile·resource matrix·기계 원장·실행 기록의 상태/수치/링크를 맞춘다.
- [ ] Source candidate 또는 build-only 행이 지원 catalog로 잘못 승격되는 것을 gate에서 차단한다.
- [ ] M33에 설치용 예제·profile·known limitation·cross-vendor NOT RUN 목록을 인계한다.
- [ ] M36에 Mesh update/storage, M38/M39에 최소 radio/public 확장, M40/M42에 적용 공존 조합을 인계한다.
- [ ] HOST-W07 자동 검사 결과와 사용자용 최종 실물 검증 절차를 별도 표로 연결한다. Ubuntu/macOS
  설치·USB·serial·debug 실기는 사용자가 최종 릴리스 때 수행한다. 그때까지 `NOT_RUN`으로 유지하되
  중간 PC 연결을 요구하거나 M32 완료를 차단하지 않는다. 해당 OS 최종 지원 gate는 유지한다.

## 6. 예정 test ID와 판정 입력

아래 ID는 구현 전 예약한 시험 그룹이다. W01에서 하위 case·정량 입력을 고정한 뒤 실행 분모를
기계 원장에 등록한다. 문서 행 수를 HIL test 완료 수로 계산하지 않는다.

| 예정 ID | 최소 구성 | 필수 관측·negative |
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
실제 power cut을 수행하는 새로운 case는 M36 후속 범위다. 현재 M32/v0.5.0 개발·릴리스는 그
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
  v0.5.0 공개 승인·qualification은 자동화 장비 조건과 독립된 절차다.
