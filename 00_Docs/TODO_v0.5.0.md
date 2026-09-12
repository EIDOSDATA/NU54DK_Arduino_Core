# v0.5.0 착수 계획 — BLE 확장과 지원 범위 판정

현재 설치·지원 배포는 **v0.4.1 하나**이며 v0.4.0 M27까지의 기능 기준선과 v0.4.1 설치기
유지보수는 완료했다. 이 문서는 다음 제품선의 착수 순서와 판정 산출물을 정의한다.
**M28은 진행 중이며 M28-W01의 Host·target·실제 HCI 6/6을 완료했다. 현재 작업은
M28-W02이고 M29~M33은 계획·구현 미착수**다. W01 capability PASS를 production BLE 구현이나
전체 M28 물리 PASS로 확대하지 않는다. 현재 v0.4.1 사용자 지원과 후속 개발은 별개다.

| 정보 | 단일 원본 |
| --- | --- |
| M28~M45 순서·전체 상태 | [제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>) |
| BLE 기능군별 목표·완료 조건 | [경쟁 마일스톤](<01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>) |
| v0.5.0 착수 체크·결정 상태 | 이 문서 |
| M28 API·자원·시험 계약 | [M28 착수 계약](<01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>) |
| M28 기계 판정 원본 | [`m28-ble-readiness.json`](../variants/nu54dk/m28-ble-readiness.json) |
| v0.4.0 완료·보존할 지원 계약 | [v0.4.0 완료 TODO](TODO_v0.4.0.md) |
| W01 실제 HCI·실패 분류·증거 | [132번 기록](<04_검증 기록/132_M28_W01_실제_HCI_capability_완료.md>) |

## 1. 다음 착수 순서

M28 준비는 P01 기준선과 정적 지원 원장부터 시작했으며, API·자원·유한 시험 계약까지 고정했다.
**M28-W01 capability image·고정 protocol·Host parser·target build와 실물 `M28-CAP-01` 6/6을
완료했고, 다음 구현은 M28-W02 per-link 기반**이다. P01~P06은 별도 전역
마일스톤이 아닌 준비 체크다. 코드 작성 전에는 영향을 받는 P02/P03 결정이, 각 물리 시험 전에는
해당 P04/P05 조건이 확정되어야 한다.
M31 전용 장비가 미확보라는 이유로 독립적인 M28 문서·Host 작업까지 차단하지 않는다.

| 체크 | 상태 | 산출물·완료 조건 |
| --- | --- | --- |
| P01 기준선 확인 | **M28 완료** | v0.4.1, Core/board/NCS/Zephyr lock과 현재 단일 링크 source 계약 대조 완료 |
| P02 기능 지원 원장 | **M28 정적 완료 / W01 HCI 6/6 PASS** | 정적 `candidate`는 유지하고 실제 runtime HCI 판정만 별도 PASS |
| P03 공개 API·profile 경계 | **M28 완료** | 기존 singleton symbol 호환, generation handle, 역할별 1개·총 2-link 고정 자원 계약 확정 |
| P04 장비·상호운용 matrix | **M28 계획 완료 / 2보드·2 DAP/UART 확인** | 필수 3개 중 1개 부족, packet trace와 OS peer 적용성은 미확인 |
| P05 수치 합격 기준 | **M28 완료** | `M28-CAP-01`~`M28-SOAK-01`의 반복·분모·timeout·오류 기준 고정 |
| P06 실행 목록 고정 | **M28 완료** | `M28-W01`~`M28-W08`의 구현·검증 순서와 증거 경계 확정 |

P02의 정적 SDK 조사와 실제 HCI 조회는 다른 증거다. `M28-CAP-01`은 exact `78078a42…`에서
6개 기능군을 확인했지만, source 후보 자체와 W02~W08 implementation/RF HIL은 별도 상태다.
미지원 판정에 controller 한계와 칩 자체 비적용을 혼동하지 않고 미판정 항목을 자동 승격하지 않는다.

M28의 상세 상태·Kconfig·시험 수치는
[`m28-ble-readiness.json`](../variants/nu54dk/m28-ble-readiness.json)을 기계 원본으로 사용하고,
[M28 착수 계약](<01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>)에서 사람이
읽는 설계와 실행 순서를 설명한다. 현재 M28 구현은 **1/8 작업 묶음, 12.5%**다.

| 작업 묶음 | 현재 상태 | 다음 종료 조건 |
| --- | --- | --- |
| M28-W01 | **완료 — Host parser·target 1/1·실제 HCI 6/6 PASS** | exact `78078a42…` 증거와 정적 candidate/runtime HCI 분리 유지 |
| M28-W02 | **착수 — per-link slot·handle·event 기반** | 고정 2-slot, generation handle, link별 상태·stale event Host/target 계약 |
| M28-W03~W08 | **미착수** | W02 기반 위에서 순서대로 구현·검증 |

W01 protocol은 `M28CAP/1`이며 128-bit nonce, Core/board/NCS/Zephyr full revision, Host Kconfig,
HCI version·64-byte supported commands·8-byte LE features와 controller 자원 상한을 고정 순서로
출력한다. Host parser는 noise·중복·누락·순서 변경·stale nonce·wrong revision·timeout과 raw HCI
불일치를 모두 거부한다. exact `78078a42…`의 target build와 실제 HCI는 각각 PASS했으며 서로 다른
증거로 유지한다. 상세 값과 hash는 [132번 기록](<04_검증 기록/132_M28_W01_실제_HCI_capability_완료.md>)에 있다.

## 2. 현재 확인된 지원성 결정 항목

아래는 고정 NCS v3.4.0 source를 읽은 결과이며 새 NU54DK 실기 결과가 아니다.
SDK를 바꾸거나 controller/profile을 바꾸면 해당 판정과 관련 회귀 범위를 다시 확인한다.

| 대상 | 확인된 사실 | 구현 전에 결정할 사항 |
| --- | --- | --- |
| M29 signed write | Zephyr host `BT_SIGNING`은 `DEPRECATED` | 호환성 수요·보안 경계에 따라 legacy 선택 기능으로 제공할지 범위 개정을 할지 결정. 자동 제외하지 않음 |
| M29 EATT | Zephyr host `BT_EATT`는 `EXPERIMENTAL` | 실험적 상태 표시, 적용 peer/profile과 추가 오류·상호운용 기준을 정한 뒤 공개 지원 여부 결정 |
| M31 방향탐지 | 기본 SDC의 CTE 송신은 AoA 지원·AoD 미지원. 전체 RX/IQ 경로 지원을 뜻하지 않음 | 송신·수신·안테나 전환을 분리해 controller/profile 적용성 판정. 대체 Zephyr LL은 별도 후보이지 검증 완료 대안이 아님 |
| M32 공존 | 802.15.4/ESB와 BLE 병행시험에는 동작하는 단독 radio 경로가 먼저 필요 | M32 안에서 최소 검증용 기반·단독 TX/RX를 확보하고, M38/M39는 공개 API·예제·일반 제품화 확장으로 연결 |

정적 근거는 NCS checkout의 `zephyr/subsys/bluetooth/host/Kconfig` (`BT_SIGNING`),
`zephyr/subsys/bluetooth/host/Kconfig.gatt` (`BT_EATT`),
`nrf/subsys/bluetooth/controller/Kconfig`와 `nrfxlib/softdevice_controller/README.rst`다.
고정 환경은 [CI lock](../tools/ci/ncs-3.4.0.lock.json)을 따른다.
[Nordic SDC v3.4.0 지원 명세](https://github.com/nrfconnect/sdk-nrfxlib/blob/v3.4.0/softdevice_controller/README.rst)를
함께 확인하며, 다른 버전의 웹 문서로 고정 SDK의 판정을 덮어쓰지 않는다.

## 3. 기존 구현과 신규 작업의 구분

| 단계 | 유지·회귀할 기존 기능 | 신규 설계·검증할 범위 |
| --- | --- | --- |
| M28 | 단일 링크 GAP, 기존 PHY 갱신·MTU 교환, 광고·스캔·연결 수명주기 | per-link handle/event·GATT/security 상태, multi-role/link, 확장·주기 광고·PAwR, privacy·지원 link control |
| M29 | 기존 GATT server/client·read/write/notify/indicate | long/reliable·descriptor/cache·CoC, 별도 정책을 정한 signed write/EATT |
| M30 | 기존 IO capability·LE Secure Connections·pairing/bond API와 BAS/DIS/HID keyboard | OOB·key 정책·migration·추가 profile, 최소 BLE DFU·서명·복구 |

연결 수 Kconfig만 늘려 multi-link 구현으로 처리하지 않는다. 기존 singleton 사용 Sketch의
동작과 오류 의미를 보존하는 방법을 정하고, 각 연결의 소유권·버퍼·해제·재접속 상태를 검증한다.
이 표의 기존 기능은 원래 검증 범위의 재사용 대상이지 신규 조합의 PASS가 아니다.

## 4. M28~M33 실행 묶음과 후속 인계

| 단계 | 구현·검증 순서 | 다음 단계에 넘길 산출물 |
| --- | --- | --- |
| M28 | 지원 원장 → per-link 계약 → GAP/link/privacy 확장 → 다중 peer HIL | 고정 capability/profile·연결/자원 한계·회귀 목록 |
| M29 | GATT/CoC → signed write/EATT 정책 적용 → 오류·상호운용 | client/server·cache·credit·실험/legacy 제약과 시험 근거 |
| M30 | 보안/profile → 최소 boot/layout·서명·BLE update → 실패 복구 | M34~M36이 재사용할 key 식별·소유권·저장 형식·layout·migration·rollback 계약 |
| M31-A | ISO/CIS/BIS 기반 → 채택한 LC3·LE Audio profile → audio HIL | ISO buffer·latency·선택 audio profile의 검증 경계 |
| M31-B | DF 송수신·controller 적용성 → RF fixture → 적용 가능한 CTE/IQ 경로 | 지원/미지원·조건부 기능과 controller별 제약, 적용 RF 근거 |
| M31-C | Connected ACL·CS 보안 → 거리 보정·반복성·상호운용 | 연결·보안·거리 오차·peer별 측정 근거 |
| M32 | 최소 radio/profile·단독 TX/RX → Mesh → 선택 조합 공존·복구 | M38~M41이 재사용할 backend·자원 소유권·허용 조합·부하 한계 |
| M33 | 필수 기능 회귀·지원표 → package/설치 → 범위 확인·공개 | exact source·자산·지원/제약·상호운용·qualification 적용성 |

M31-A/B/C는 **M31 내부 작업 ID**다. 하나를 완료해 M31 전체 완료로 계산하지 않는다.
M30 최소 DFU에서는 고정 layout·신뢰키·초기 설치·BLE 갱신·전원 차단 복구와 Arduino 제공 형태를
먼저 결정한다. 현재 `--no-sysbuild` build·native HEX upload를 그대로 MCUboot 지원으로 간주하지
않으며, 기본 loaderless 경로는 유지한다. M36은 다중 layout/transport와 hardening 확장이다.

M42 시작 전에는 사용할 Matter transport, Thread 선택 시 M40의 network 근거, M32의 적용 공존
조합, update 경로, RAM/RRAM·저장소 예산과 개발용/생산용 credential 정책을 연결한다.
NU54DK의 외장 flash 미탑재와 factory-data partition 적용성은 설계 입력이며 Matter 불가능 판정이 아니다.

## 5. 장비와 정량 판정 기준

### 장비 확보 상태

현재 **NU54DK 2개와 독립 DAP/UART 2경로는 2026-09-12 W01에서 확인**했다. M28 필수 3개 중
한 개와 packet trace는 미확인이며, 과거 v0.4.0 시험으로 나머지 장비까지 확보됐다고 판단하지 않는다.

| 시험군 | 계획상 필요한 구성 | 착수 시 확인할 사항 |
| --- | --- | --- |
| BLE 기본·multi-link | 최소 NU54DK 3개와 packet trace, Android/iOS/Windows/Linux peer | 실제 보드 수·역할, OS/version·어댑터·peer 기능별 적용성 |
| ISO/LE Audio | 채택 profile을 송수신할 peer와 해당 audio 입력·출력/측정 수단 | codec/profile, clock·buffer 조건, 측정 가능한 loss·latency·jitter |
| Direction Finding | 지원 판정된 controller와 역할별 antenna array/switch·IQ 수집 구성 | NU54DK 단독으로 되는 역할과 추가 RF 구성이 필요한 역할 구분 |
| Channel Sounding | CS 지원 peer, 통제 거리 또는 RF 감쇠 조건·보정 데이터 | 실제 거리 기준·환경·방향·cross-vendor peer 확보 |
| Mesh/coexistence | topology별 노드, power-cycle 수단, BLE/802.15.4/ESB traffic 관측 | 역할별 노드 수, 허용 동시 조합·부하, starvation 측정 방법 |

Android/iOS/Linux 항목은 **BLE 상대 장치 상호운용**이며 Arduino Core 개발·설치 host 지원을
Windows 외 OS로 확대하는 약속이 아니다. Peer 자체 미지원 기능은 근거를 남기고 해당 칸을
비적용으로 분리한다. 필요한 장비가 없는 필수 시험은 `NOT RUN`이지 PASS 또는 자동 제외가 아니다.

### 실행 전에 고정할 합격표

아래 값은 아직 **미확정**이다. 임의 숫자를 제품 보증으로 채우지 않고, 선택 profile과 장비가
결정되면 P05에서 숫자·단위·계산식·측정 수단을 채운다. 빈칸이나 `미확정`이 남은 해당 시험은
정식 PASS 판정에 사용할 수 없다. `장시간`, `안정적`, `저지연`만으로 합격 기준을 대신하지 않는다.

| 시험군 | 반드시 고정할 입력 | 수치·판정 항목 |
| --- | --- | --- |
| GAP/multi-link | 연결 수·역할·PHY·MTU/DLE·interval·전송률·환경 | reconnect 반복 수·timeout, 요청/실제 연속 시간, 송수신 분모·허용 loss/중복/순서 오류, 자원 복구 기준 |
| GATT/CoC/EATT | value/MTU·channel/credit 수·동시 부하·malformed 입력 | payload 일치, 오류 종류·횟수, 최대 서비스 지연·복구 timeout, leak 판정 |
| Security/DFU | IO/OOB·key 정책·서명·image/layout·중단 주입 지점 | 거부해야 할 입력·예상 오류, 전원 차단 반복 수·부팅/복구 timeout, rollback·데이터 보존 기준 |
| ISO/Audio | codec/profile·SDU·buffer·clock·부하 | loss 분모·허용률, latency/jitter 통계와 상한·측정 오차, underrun/overrun·복구 시간 |
| DF/CS | 역할·controller·안테나·거리·보정·환경 | sample 수·유효률, 오차 통계/상한·반복성, 보안 실패·연결 끊김 복구 기준 |
| Mesh/coexistence | topology·model·동시 조합·각 protocol 부하 | 전달률·서비스 지연 상한·starvation 판정, power-cycle 수·복구 timeout·soak 시간 |

각 test ID에는 최대 실행 시간·반복 수·오류 중단 조건·진단 후 동일 조건 재검증 횟수도 고정한다.
실패는 원인·수정·동일 조건 재검증을 연결하며 무한 재시도로 통과를 만들지 않는다.
통신 손실, audio jitter, 거리 오차의 허용치는 기능별 기준이며 모든 주변장치 조합이나 정밀
계측 품질을 일괄 보증하지 않는다. v0.4.0의 범위 제외는 그대로 보존한다.

## 6. 결과·공개 규칙

- M28의 P01·P03·P05·P06, P02 정적 원장과 W01 실제 HCI를 완료했다. W01만 완료한 현재 상태는
  1/8이며 W02~W08, 전체 M28과 M29~M33을 완료 처리하지 않는다.
- 구현·Host·build·실기·상호운용·공개 결과를 분리하고 exact source/profile·조건·raw log를 연결한다.
- 적용 가능한 필수 기능은 증거가 있어야 완료한다. 기능 제외·보증 범위 축소·SDK 교체가 필요하면
  별도 범위 결정으로 기록하고, 조용히 삭제하거나 성공으로 바꾸지 않는다.
- 문서상의 기능 계획과 Bluetooth/Matter 제품 인증 취득은 별개다.
- v0.4.0·v0.4.1 공개 승인은 v0.5.0 공개 승인이 아니다. M33에서 exact 결과·자산 기준으로 공개 범위를 확정한다.
- 다음 작업 보고에는 완료 범위·현재 항목·남은 항목과 **해당 작업의 분모**를 적는다.
  P 준비 체크, M28~M33의 6개 마일스톤, v0.4.0의 T13 분모 58을 섞지 않는다.
