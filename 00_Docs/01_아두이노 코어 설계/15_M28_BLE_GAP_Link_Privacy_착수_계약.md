# M28 — BLE GAP·Link·Privacy 착수 계약

| 항목 | 내용 |
| --- | --- |
| 문서 ID | M28-BLE-READINESS-001 |
| 문서 개정 | 1.5 |
| 대상 제품선 | `v0.5.0` |
| 현재 상태 | **M28-W01~W06 완료 / W07 착수 / 진행률 6/8, 75.0%** |
| 기준 SDK | NCS `v3.4.0`, Zephyr `4.4.0`, SoftDevice Controller multirole |
| 최종 갱신일 | 2026-09-12 |
| 기계 판정 원본 | [`m28-ble-readiness.json`](../../variants/nu54dk/m28-ble-readiness.json) |

## 1. 목표와 완료 경계

M28은 v0.4.1의 단일 링크·legacy advertising 계약을 보존하면서 다음 기능을 추가하는
`v0.5.0` 첫 구현 마일스톤이다.

- central 1개와 peripheral 1개를 동시에 유지하는 **2-link mixed-role**
- link별 handle·event·GATT client·security·MTU/PHY/parameter 상태
- extended advertising/scanning, periodic advertising/sync와 PAST
- PAwR advertiser/scanner
- privacy/RPA와 link별 제어·오류·자원 회수

이 문서와 JSON은 구현 순서·자원 상한·유한 시험 기준을 고정하는 준비 산출물이다. 정적 NCS
source에 API와 controller 후보가 있다는 사실은 NU54DK image의 HCI 지원, Core 구현 또는 RF
PASS가 아니다. 아래 `NOT RUN` 항목을 실행하지 않은 상태에서 M28을 완료로 표시하지 않는다.

## 2. 고정 기준선

| 대상 | 고정 값 | 현재 의미 |
| --- | --- | --- |
| 설치·지원 release | `v0.4.1` | M28 개발 중에도 기존 사용자 지원 기준 유지 |
| 개발 source version | `0.4.1-dev` | `platform.txt`의 source 식별자 |
| NCS | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` | lock과 설치 source 일치 확인 |
| Zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` | lock과 설치 source 일치 확인 |
| Windows Toolchain | bundle `dcbdc366a1` | lock과 로컬 manifest 일치 확인 |
| 보드 submodule | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` | 임의 수정 금지 |
| 현재 BLE 연결 상한 | 2 | `CONFIG_BT_MAX_CONN=2`, central/peripheral 역할 고정 slot 각 1개 |
| 현재 광고 형식 | legacy 31 byte + extended 255 byte | periodic set은 미구현 |

`BLEDevice`, `BLEAdvertising`, `BLEScan`, `BLEConnection`은 v0.4.1 호환 symbol로 유지한다.
W02에서 `maximumConnections()==2`와 역할 고정 connection slot을 구현했으며 Kconfig 숫자만
늘린 구현이 아니다. W01 이전 단일 connection 기준선은 130~133번 역사 기록에 보존한다.

## 3. 고정 SDK 지원 후보 원장

아래 source 판정은 로컬 NCS v3.4.0 source와 CI lock을 대조한 **정적 후보 판정**이다. W01 exact
image의 실제 HCI 결과는 별도 열에 두며, 어느 쪽도 production API·RF HIL 완료를 뜻하지 않는다.

| 기능군 | 정적 근거 | W01 실제 HCI | 남은 production 판정 |
| --- | --- | --- | --- |
| Multi-role/link | `BT_MAX_CONN`, SDC peripheral count, multirole controller 변형 | **PASS** | 동시 2-link 구현·실기 NOT RUN |
| Extended advertising/scanning | `BT_EXT_ADV`, `bt_le_ext_adv_*`, SDC Advertising Extensions | **PASS** | public API·Host·target PASS, 255-byte RF 실기 NOT RUN |
| Periodic advertising/sync·PAST | `BT_PER_ADV*`, sync-transfer sender/receiver API | **PASS** | public API·Host·target PASS, report·PAST 3보드 실기 NOT RUN |
| PAwR | `BT_PER_ADV_RSP`, `BT_PER_ADV_SYNC_RSP`, SDC PAwR advertiser/scanner | **PASS** | buffer·subevent/slot RF 실기 NOT RUN |
| Privacy/RPA | Zephyr host `BT_PRIVACY`, controller privacy | **PASS** | bond identity·RPA 회전·재연결 NOT RUN |
| Per-link control | 기존 MTU/PHY/parameter/tx-power + DLE/remote-info API | **PASS** | 두 링크 격리·DLE·remote-info 실기 NOT RUN |

정적 근거 경로와 필요한 Kconfig의 단일 기계 원본은
[`m28-ble-readiness.json`](../../variants/nu54dk/m28-ble-readiness.json)에 둔다. 고정 SDK를
바꾸면 원장과 전 회귀 범위를 먼저 다시 판정한다.

## 4. 공개 API·자원 계약

### 4.1 호환성

기존 네 singleton symbol과 기존 callback은 source 호환을 유지한다. 새 multi-link API는 다음
규칙을 따른다.

1. Link는 slot 번호만이 아니라 **generation을 포함한 불투명 handle**로 식별한다.
2. 새 상세 event는 link handle을 포함한다. 기존 callback은 호환 view로 남긴다.
3. GATT discovery/subscription, security/bond 관측, MTU/PHY/DLE/parameter 상태는 link별로 둔다.
4. `struct bt_conn *`와 Zephyr type은 공개 Arduino 헤더에 노출하지 않는다.
5. Disconnect/end 뒤 이전 generation의 callback은 새 link로 전달하지 않는다.

기존 handle 없는 `BLEConnection` link 제어는 active central을 우선하고, central이 없을 때
peripheral을 선택하는 결정적 호환 view로 W02 Host 시험에 고정했다. `connected()`는 active link가
하나 이상인지 반환하고 `connecting()`은 유일한 central pending slot을 나타낸다.

### 4.2 자원 상한

첫 공개 목표는 `CONFIG_BT_MAX_CONN=2`, SDC peripheral slot 1개, central slot 1개다. 따라서
보증 topology는 DUT 기준 central 1 + peripheral 1의 동시 2-link다. Connection, advertising set,
periodic sync, queue와 payload buffer는 compile-time 상한을 가진 고정 storage로 구현한다.

다음 구현은 금지한다.

- `CONFIG_BT_MAX_CONN`만 늘리고 singleton GATT/security/connection 상태를 공유
- Bluetooth callback에서 사용자 callback 직접 호출 또는 heap 할당
- Disconnect 직후 slot을 generation 변경 없이 재사용
- HCI 미조회 기능이나 peer 미지원 결과를 PASS·지원으로 표기

## 5. 구현 묶음

| 순서 | 작업 | 종료 조건 |
| --- | --- | --- |
| M28-W01 | Capability image와 HCI 원장 | `M28-CAP-01`, source 후보와 실제 feature/command/자원 상한 대조 |
| M28-W02 | Per-link slot·handle·event 기반 | 두 link ref/unref, generation, end/disconnect/reconnect와 stale event Host 계약 |
| M28-W03 | Extended advertising·scanning | Set lifecycle, 255-byte payload, SID/PHY와 scan result 경계 |
| M28-W04 | Periodic advertising·sync·PAST | Advertiser/sync lifecycle, report fragmentation, transfer sender/receiver 경계 |
| M28-W05 | PAwR advertiser·scanner | Subevent/slot buffer, response window, overflow·취소·회수 계약 |
| M28-W06 | Privacy·RPA·per-link control | Identity/bond 연결, RPA 회전, DLE/PHY/parameter/remote-info link 격리 |
| M28-W07 | Host·target·두/세 보드 HIL | 아래 9개 test ID와 기존 M19~M21 회귀 |
| M28-W08 | 문서·지원표·M29 인계 | 지원/조건부/미지원 원장, 자원/interop 제약, exact evidence 연결 |

각 작업은 Host 계약 → target build → 필요한 실기의 순서로 판정한다. 실패 시 원인과 수정 source를
연결해 동일 조건으로 재검증하며, timeout 안의 이유 없는 반복으로 통과를 만들지 않는다.

### 5.1 M28-W01 고정 protocol과 현재 결과

`M28CAP/1`은 임의 로그 문장이 아니다. Host가 flash/reset 구간의 UART byte를 버린 뒤 exact
`PROBE` command로 세션을 arm하고, firmware는 다음 15개 record를 고정 순서로 출력한다.

1. `READY`, nonce가 결합된 `BEGIN`
2. Core·board·NCS·Zephyr full revision과 Host Kconfig
3. HCI version, 64-byte Supported Commands, 8-byte LE Local Supported Features
4. 최대 advertising data·advertising set·periodic advertiser list·resolving list 자원
5. 6개 기능군의 Host/controller 판정과 record 수를 고정한 `END`

Firmware는 잘못된 PROBE·START·nonce·HCI status·응답 크기를 즉시 `FAIL`로 닫는다. Host parser는 전체
transcript가 정확히 15줄인지 확인하고 noise·중복·누락·순서 변경·stale nonce·wrong revision·
timeout과 raw HCI bit/resource에 맞지 않는 PASS 문자열을 거부한다. exact `78078a42…`에서 신규
parser 시험 12개, 고정 SDK target 1/1 build와 실제 HCI 6/6이 PASS했다. 정적
`source_status=candidate`는 유지하고 기능군의 별도 `runtime_hci_status`만 `passed`다.
[132번 기록](<../04_검증 기록/132_M28_W01_실제_HCI_capability_완료.md>)이 image·raw 증거 hash와
실패 분류를 보존한다.

### 5.2 M28-W02 2-slot·generation 결과

Production profile은 `CONFIG_BT_MAX_CONN=2`, `CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=1`을 사용한다.
Connection storage는 central과 peripheral 역할이 고정된 두 slot이고, 각 할당은 image 수명 동안
증가하는 generation을 불투명 `BLEConnectionHandle`에 결합한다. 상세 `BLEEventInfo`는 기존
`BLEEventCallback`을 제거하지 않고 handle·local 역할을 추가한다.

Disconnect와 `Device::end()`는 public 상태보다 먼저 slot을 무효화하고 소유 reference를 회수한다.
MTU 요청은 고정 4개 context에 generation handle을 보존하여 이전 link의 늦은 callback을 새 slot에
전달하지 않는다. 실제 production GAP source를 사용한 Host lifecycle 13개 시나리오와 W02 source
계약 5개, `nucode.m28.ble_link_contract` target 1/1 build가 PASS했다. `MixedRoleLinks` 예제는
central 연결 뒤 peripheral 광고를 시작하고 상세 event로 두 handle을 분리한다. 실제 mixed-role RF
PASS는 W07의 `M28-LINK-01`에서만 판정한다.

### 5.3 M28-W03 확장 광고·스캔 결과

Production profile은 extended advertising set 1개와 controller 광고 payload 255 byte를 고정
상한으로 사용한다. `BLEAdvertisingSetHandle`은 generation을 포함하고, 삭제 후 같은 storage를
재사용해도 이전 callback을 새 set event로 전달하지 않는다. Raw AD payload는 구조 수 16개와 전체
길이 255 byte를 넘거나 TLV가 잘리면 시작 전에 거부한다.

확장 스캔 결과는 callback buffer를 보존하지 않고 최대 255 byte를 queue value로 복사하며 SID,
TX power, periodic interval과 primary/secondary PHY를 함께 전달한다. Production source Host 수명
시나리오 4개와 정적 경계 검사, 고정 NCS의 `nucode.m28.ble_extended_contract` target 1/1 build가
warning 없이 PASS했다. `ExtendedAdvertising`·`ExtendedScanner` 예제를 함께 추가했다. 실제
255-byte RF report 100개 판정은 W07의 `M28-ADV-01` 전까지 `NOT RUN`이다.

### 5.4 M28-W04 periodic sync·PAST 결과

Periodic advertiser는 W03 extended set 하나에 결합하고, periodic sync는 generation 기반 고정 slot
한 개를 사용한다. Report callback은 최대 255 byte와 주소·SID·TX power·RSSI를 고정 8-entry queue로
복사한다. 삭제·end 뒤 이전 sync pointer의 callback은 새 generation으로 전달하지 않는다.

PAST sender의 sync/set transfer와 receiver subscribe/unsubscribe는 현재 `BLEConnectionHandle`을
요구한다. Receiver는 구독된 현재 link에서 전달된 sync만 고정 slot에 할당한다. Production Host
수명 시나리오 4개와 정적 계약, 고정 NCS의 `nucode.m28.ble_periodic_contract` target 1/1 build가
warning 없이 PASS했고 `PeriodicAdvertiser`·`PeriodicScanner` 예제를 추가했다. 3-node PAST와
periodic report RF 판정은 W07의 `M28-PER-01`까지 `NOT RUN`이다.

### 5.5 M28-W05 PAwR advertiser·scanner 결과

PAwR advertiser는 4 subevent × 4 response slot을 고정 상한으로 사용하며 subevent data와 response
payload는 각각 249 byte를 넘지 않는다. Scanner response는 현재 periodic sync generation에만
결합하고, 잘못된 subevent·slot·offset·길이는 controller 호출 전에 거부한다.

Controller callback data는 고정 storage와 8-entry response queue에 값으로 복사한다. Stop·delete·
`Device::end()`는 callback보다 먼저 context를 무효화하여 이전 request/response가 새 set·sync로
전달되지 않게 한다. Production Host 시나리오 4개와 정적 계약, 고정 NCS의
`nucode.m28.ble_pawr_contract` target 1/1 build가 warning 없이 PASS했고 `PawrAdvertiser`와
`PawrScanner` 예제를 추가했다. 실제 PAwR RF 판정은 W07의 `M28-PAWR-01`까지 `NOT RUN`이다.

### 5.6 M28-W06 privacy·RPA·per-link control 결과

`BLEPrivacy`는 production profile의 privacy 지원 여부, 1~3600초 runtime RPA timeout과 현재 Device
session의 extended advertising RPA 만료 횟수를 노출한다. RPA 만료 callback은 현재 advertising set
generation에만 event를 전달하고 실제 주소 회전을 허용한다.

각 connection slot은 연결 설정에 사용한 remote 주소와 해석된 peer identity를 분리한다. Identity,
DLE와 remote-info callback은 stack pointer가 현재 active slot과 일치할 때만 generation event로
변환한다. Public API는 handle별 actual parameter, DLE 송수신 값, remote LL version·manufacturer·
subversion·8-byte LE feature를 값으로 복사한다. Host 수명 시나리오 5개와 정적 계약, 고정 NCS의
`nucode.m28.privacy_control` target 1/1 build가 warning 없이 PASS했고 `PrivacyPeripheral`·
`PerLinkControl` 예제를 추가했다. 실제 RPA/bond와 동시 2-link control은 W07까지 `NOT RUN`이다.

### 5.7 M28-W07 2보드 자동화 준비

두 role image는 한 실행에서 255-byte extended advertising, 4 subevent × 4 response slot PAwR,
초기 RPA와 세 번 회전한 주소, Just Works bond와 20회 재연결을 순서대로 수행한다. `M28B2`
protocol은 128-bit nonce와 role별 고정 record를 사용하며 Host parser가 누락·중복·순서·수치·
stale·FAIL을 닫는다. Parser 10/10과 고정 NCS peripheral/central build 2/2가 warning 없이 PASS했다.

이 결과는 2보드 RF PASS가 아니다. Exact clean commit image로 `M28-ADV-01`, `M28-PAWR-01`,
`M28-PRIV-01`을 실행하고 기존 M19~M21로 `M28-REG-01`을 채우기 전까지 네 test ID는 `NOT RUN`이다.
3보드에서는 이 기능을 반복하지 않고 두 link 동시 조건 네 개만 실행한다.

## 6. 유한 시험 계약

정확한 수치와 구조화 필드의 단일 원본은 readiness JSON이다. 아래 요약과 JSON이 다르면 자동
Host 검사를 실패시켜 함께 수정하게 한다.

| Test ID | 장비 | 핵심 합격 기준 | 상한 |
| --- | --- | --- | --- |
| `M28-CAP-01` | NU54DK 1 | 6개 기능군 HCI 근거, 필수 누락·stale nonce 0 | 180초 |
| `M28-REG-01` | NU54DK 2 | 기존 M19 GAP·M20 GATT·M21 security 3 suite 실패 0 | 900초 |
| `M28-LINK-01` | NU54DK 3 | mixed-role 2-link, link당 재연결 20회·sequence 1,000개, loss/corrupt/duplicate/stale 0 | 1,200초 |
| `M28-ADV-01` | NU54DK 2 | 255-byte extended payload report 100개, corrupt/stale set event 0 | 600초 |
| `M28-PER-01` | NU54DK 3 | periodic report 1,000개 중 99% 이상, corrupt 0, PAST 20/20 | 900초 |
| `M28-PAWR-01` | NU54DK 2 | 4 subevent × 4 slot, 100 event, valid response 99% 이상, corrupt/out-of-window 0 | 900초 |
| `M28-PRIV-01` | NU54DK 2 | RPA 회전 3회, bonded reconnect 20/20, identity 오판 0 | 900초 |
| `M28-CTRL-01` | NU54DK 3 | 2-link 각 제어 20회, 교차 상태·stale event·누락 driver error 0 | 900초 |
| `M28-SOAK-01` | NU54DK 3 | 1,800초, link당 sequence 10,000개, loss/corrupt/unexpected disconnect/회수 실패 0 | 2,100초 |

Periodic/PAwR 수신률은 통제된 bench 조건과 packet trace로 분모를 기록한다. 허용 손실을 payload
손상이나 구현 queue overflow 허용으로 바꾸지 않는다. Peer가 기능을 지원하지 않으면 해당 peer
칸은 비적용으로 남기고 NU54DK끼리의 필수 시험을 대체하지 않는다.

## 7. 장비와 실행 전 확인

필수 구성은 NU54DK 3개, 독립 USB/DAP/UART 경로 3개와 packet trace 수단 1개다. Android,
iOS, Windows와 Linux peer는 각 OS/version과 adapter를 기록해 상호운용 표를 채운다. W01에서
보드·DAP/UART 2경로를 확인했으며 **3번째 경로와 packet trace는 미확인**이다. 장비가 없으면
관련 시험은 `NOT RUN`이다.

실기 전에는 다음을 확인한다.

1. 세 보드의 exact UID·image SHA-256·Core/board revision
2. DAP/UART endpoint와 역할의 일대일 결합, 실행별 128-bit nonce
3. Packet trace 시간축과 세 UART transcript의 동일 실행 결합
4. Test별 timeout·오류 중단 조건, 종료 후 advertising/scan/link/queue 자원 회수

M28 BLE 시험에는 GPIO 점퍼가 필요하지 않다. Flash 전에는 대상 UID를 확인하고 자동
unlock·recover·mass erase를 사용하지 않는다.

## 8. 현재 준비 판정과 다음 실행

| 준비 항목 | 상태 |
| --- | --- |
| P01 Core/board/SDK/toolchain 기준선 | **완료** |
| P02 M28 정적 capability 원장 | **완료** |
| P02 실제 HCI capability | **exact `78078a42…` 실기 6/6 PASS** |
| P03 공개 API·profile 경계 | **준비 계약 완료** |
| P04 시험 구성 | **계획 고정 / 보드·DAP/UART 2/3 확인, packet trace 미확인** |
| P05 수치 합격 기준 | **M28 9개 test ID 고정** |
| P06 실행 목록 | **M28-W01~W08 고정** |

따라서 M28 진행률은 **6/8 작업 묶음, 75.0%**다. 다음 작업은 `M28-W07`이다. 2보드에서
`M28-REG-01`, `M28-ADV-01`, `M28-PAWR-01`, `M28-PRIV-01`을 먼저 실행하고, 3보드에서는 중복
기능시험 없이 `M28-LINK-01`, `M28-PER-01`, `M28-CTRL-01`, `M28-SOAK-01`의 동시 조건만
실행한다. W01~W06 PASS는 W07~W08이나 전체 M28 PASS가 아니다.

준비 계약 검사는 다음으로 실행한다.

```powershell
python -B -m unittest discover -s tests/host -p "test_m28_readiness.py" -v
python -B tools/ci/run_m12_gate.py host
python -B tools/ci/run_m12_gate.py docs
```
