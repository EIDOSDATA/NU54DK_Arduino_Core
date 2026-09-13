# v0.5.0 착수 계획 — BLE 확장과 지원 범위 판정

현재 설치·지원 배포는 **v0.4.1 하나**이며 v0.4.0 M27까지의 기능 기준선과 v0.4.1 설치기
유지보수는 완료했다. 이 문서는 다음 제품선의 진행 상태·남은 작업과 판정 산출물을 관리한다.
**M28은 M28-W01~W08과 9개 test ID를 완료했고 M29는 W07 2보드 HIL 완료, 6/8·test ID 8/10이다. M30~M33은
계획·구현 미착수**다. M28 완료는 v0.5.0 공개, mobile/desktop cross-vendor 상호운용 또는
Bluetooth qualification 완료가 아니다. 현재 v0.4.1 사용자 지원과 후속 개발은 별개다.

| 정보 | 단일 원본 |
| --- | --- |
| M28~M45 순서·전체 상태 | [제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>) |
| BLE 기능군별 목표·완료 조건 | [경쟁 마일스톤](<01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>) |
| v0.5.0 착수 체크·결정 상태 | 이 문서 |
| M28 API·자원·시험 계약 | [M28 착수 계약](<01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>) |
| M28 기계 판정 원본 | [`m28-ble-readiness.json`](../variants/nu54dk/m28-ble-readiness.json) |
| M29 API·정책·자원·시험 계약 | [M29 착수 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>) |
| M29 기계 판정 원본 | [`m29-ble-readiness.json`](../variants/nu54dk/m29-ble-readiness.json) |
| v0.4.0 완료·보존할 지원 계약 | [v0.4.0 완료 TODO](TODO_v0.4.0.md) |
| W01 실제 HCI·실패 분류·증거 | [132번 기록](<04_검증 기록/132_M28_W01_실제_HCI_capability_완료.md>) |
| W02 2-slot·generation 구현·검증 | [134번 기록](<04_검증 기록/134_M28_W02_2-slot_generation_link_기반.md>) |
| W03 확장 광고·스캔 구현·검증 | [135번 기록](<04_검증 기록/135_M28_W03_확장_광고와_스캔.md>) |
| W04 periodic·PAST 구현·검증 | [136번 기록](<04_검증 기록/136_M28_W04_periodic_sync_PAST.md>) |
| W05 PAwR 구현·검증 | [137번 기록](<04_검증 기록/137_M28_W05_PAwR_advertiser_scanner.md>) |
| W06 privacy·link control 구현·검증 | [138번 기록](<04_검증 기록/138_M28_W06_privacy_RPA_link_control.md>) |
| W07 HIL·W08 완료와 실패 진단 | [140번 기록](<04_검증 기록/140_M28_W07_3보드_HIL과_W08_완료.md>) |
| M29 W01 capability | [141번 기록](<04_검증 기록/141_M29_W01_ATT_GATT_L2CAP_capability.md>) |
| M29 W02 link별 long read | [142번 기록](<04_검증 기록/142_M29_W02_link별_GATT_long_read.md>) |
| M29 W03 long/reliable write | [143번 기록](<04_검증 기록/143_M29_W03_long_reliable_write.md>) |
| M29 W04 descriptor·authorization | [144번 기록](<04_검증 기록/144_M29_W04_descriptor_authorization_read_multiple.md>) |
| M29 W05 robust GATT cache | [145번 기록](<04_검증 기록/145_M29_W05_robust_GATT_cache_migration.md>) |
| M29 W06 LE CoC·negative | [146번 기록](<04_검증 기록/146_M29_W06_LE_CoC_credit_buffers.md>) |
| M29 W07 Signed Write·EATT 2보드 HIL | [147번 기록](<04_검증 기록/147_M29_W07_Signed_Write_EATT_HIL_준비.md>) |

## 1. 다음 착수 순서

M28 준비는 P01 기준선과 정적 지원 원장부터 시작했으며, API·자원·유한 시험 계약까지 고정했다.
M28-W01 capability부터 W08 문서·인계까지 완료했다. M29는 W01 capability, W02 link별
GATT long read, W03 long/reliable write, W04 descriptor·authorization·read multiple,
W05 robust GATT cache와 W06 LE CoC를 완료했다.
W07 Signed Write·EATT 구현·Host parser·target 2/2와 exact 2보드 SIGN/EATT HIL을 완료했다.
세 보드 MULTI/REG가 남아 현재 M29는 계속 **6/8**, test ID는 **8/10**이다.
P01~P06은 별도 전역
마일스톤이 아닌 준비 체크다. 코드 작성 전에는 영향을 받는 P02/P03 결정이, 각 물리 시험 전에는
해당 P04/P05 조건이 확정되어야 한다.
M31 전용 장비가 미확보라는 이유로 독립적인 M28 문서·Host 작업까지 차단하지 않는다.

| 체크 | 상태 | 산출물·완료 조건 |
| --- | --- | --- |
| P01 기준선 확인 | **M28 완료** | v0.4.1, Core/board/NCS/Zephyr lock과 현재 2-link source 계약 대조 완료 |
| P02 기능 지원 원장 | **M28 정적 완료 / W01 HCI 6/6 PASS** | 정적 `candidate`는 유지하고 실제 runtime HCI 판정만 별도 PASS |
| P03 공개 API·profile 경계 | **M28 완료** | 기존 singleton symbol 호환, generation handle, 역할별 1개·총 2-link 고정 자원 계약 확정 |
| P04 장비·상호운용 matrix | **M28 3보드·3 DAP/UART 확인** | receiver-validated packet sequence 사용, 외부 sniffer·OS peer 상호운용은 미검증 |
| P05 수치 합격 기준 | **M28 완료** | `M28-CAP-01`~`M28-SOAK-01`의 반복·분모·timeout·오류 기준 고정 |
| P06 실행 목록 고정 | **M28 완료** | `M28-W01`~`M28-W08`의 구현·검증 순서와 증거 경계 확정 |

P02의 정적 SDK 조사와 실제 HCI 조회는 다른 증거다. `M28-CAP-01`은 exact `78078a42…`에서
6개 기능군을 확인했지만, source 후보 자체와 W03~W08 implementation/RF HIL은 별도 상태다.
미지원 판정에 controller 한계와 칩 자체 비적용을 혼동하지 않고 미판정 항목을 자동 승격하지 않는다.

M28의 상세 상태·Kconfig·시험 수치는
[`m28-ble-readiness.json`](../variants/nu54dk/m28-ble-readiness.json)을 기계 원본으로 사용하고,
[M28 착수 계약](<01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>)에서 사람이
읽는 설계와 실행 순서를 설명한다. 현재 M28은 **8/8 작업 묶음, 100.0%**다.

| 작업 묶음 | 현재 상태 | 완료 근거·남은 조건 |
| --- | --- | --- |
| M28-W01 | **완료 — Host parser·target 1/1·실제 HCI 6/6 PASS** | exact `78078a42…` 증거와 정적 candidate/runtime HCI 분리 유지 |
| M28-W02 | **완료 — Host 계약·target 1/1 PASS** | 고정 central/peripheral slot, generation handle, 상세 event, stale callback·end 회수 |
| M28-W03 | **완료 — Host 계약·target 1/1 PASS** | generation set, 255-byte payload, SID/PHY scan metadata, 예제 2개 |
| M28-W04 | **완료 — Host 계약·target 1/1 PASS** | 1 sync, 255-byte report, PAST sender/receiver, 예제 4개 |
| M28-W05 | **완료 — Host 계약·target 1/1 PASS** | 4 subevent × 4 response slot, request/response window, 예제 2개 |
| M28-W06 | **완료 — Host 계약·target 1/1 PASS** | RPA timeout/event, identity, DLE·parameter·remote-info link 격리, 예제 2개 |
| M28-W07 | **완료 — parser 29/29·target 14/14·실기 9/9 PASS** | 2보드 REG/ADV/PAWR/PRIV, 3보드 LINK/PER/CTRL/SOAK exact evidence 보존 |
| M28-W08 | **완료** | 지원 경계·실패 진단·M29 인계와 기계 원장 정합화 |

M29는 [M29 착수 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>)과
[`m29-ble-readiness.json`](../variants/nu54dk/m29-ble-readiness.json)을 기준으로 실행한다.
Signed Write는 deprecated legacy opt-in, EATT는 experimental opt-in이며 둘 다 기본 profile에서는
OFF다. W01은 고정 NCS capability image와 fail-closed protocol/parser의 실제 실행까지 완료했다.

| 작업 묶음 | 현재 상태 | 완료 근거·남은 조건 |
| --- | --- | --- |
| M29-W01 | **완료 — parser 16/16·target 1/1·실제 capability 7/7 PASS** | exact `d604642b…` 증거와 peer-required 기능 분리 유지 |
| M29-W02 | **완료 — Host 전체 gate·target 2/2·2보드 long read 100/100 PASS** | exact `dacf6341…`, MTU 247·512 byte·corrupt/stale 0 증거 유지 |
| M29-W03 | **완료 — Host·target 2/2·2보드 reliable write 100/100 PASS** | exact `babba5a1…`, MTU 247·512 byte·corrupt/partial commit 0 증거 유지 |
| M29-W04 | **완료 — Host·target 2/2·2보드 descriptor/read multiple 100/100 PASS** | exact `068a1765…`, descriptor 4개·authorization 오판 0 증거 유지 |
| M29-W05 | **완료 — Host·target 2/2·2보드 cache migration PASS** | exact `e587c4fe…`, bonded reconnect 20·stale/corrupt accept 0 증거 유지 |
| M29-W06 | **완료 — Host·target 2/2·2보드 CoC/negative PASS** | exact `767bb4af…`, 2-channel·512 byte·각 방향 1,000 SDU·5 negative class·복구 오류 0 증거 유지 |
| M29-W07 | **진행 중 — Host 계약 17/17·parser 16/16·target 2/2·SIGN/EATT PASS** | exact `c71ef4a2…` 2보드 증거 유지, 세 보드 `M29-MULTI/REG-01` 실행 |
| M29-W08 | 미착수 | 전체 회귀·예제·문서·지원 판정·CI와 M30 인계 |

### 현재 재개 지점: M29 W07-C 완료

Exact `c71ef4a21465923760933f6b87ad7d92d9a95698`의 clean target **2/2 PASS, warning 0**과
두 보드 전체 runner에서 `M29-SIGN-01`·`M29-EATT-01`을 완료했다.
Signed Write 20/20·warm reboot counter rollback 0·replay 수락 0, EATT 2 bearer × 1,000 SDU와
production enhanced read/write, payload 오류·deadlock·starvation 0, 연결 재시도 0이다.
[최종 result.json](<04_검증 기록/evidence/m29-w07-c71ef4a2-signed-eatt/result.json>)과 양쪽 raw transcript가 근거다.

**W07-D/E는 사용자 중단 경계에 따라 대기**하며 `M29-MULTI-01`·`M29-REG-01`은
`NOT RUN`이다. 현재 요청은 문서 전수 정비·commit/push이며 CI 확인은 뒤로 미룬다.
실기 재개 시 세 보드의 현재 연결·역할·image와 종료 조건을 확인하고, 두 시험 후 W08을 마감한다.
개발 인계와 도구 준비는 [HANDOFF](HANDOFF.md)를 따른다.

M28과 M29 각 단계의 구현·시험 수치는 위 작업표와 해당 계약에서 확인한다.
시도별 실패·CMSIS-DAP 진단·수정·재검증 상세는 [140번](<04_검증 기록/140_M28_W07_3보드_HIL과_W08_완료.md>)과
[141~147번 검증 기록](<04_검증 기록/README.md>)에 보존하며 이 TODO에 중복하지 않는다.
정적 SDK `candidate`, Host 시험, target build와 실기 PASS는 서로 다른 증거다.

## 2. 현재 확인된 지원성 결정 항목

아래 표는 고정 NCS v3.4.0의 source 상태와 프로젝트의 결정·실기 결과를 구분한다.
SDK나 controller/profile을 바꾸면 해당 판정과 관련 회귀 범위를 다시 확인한다.

| 대상 | 고정 SDK의 상태 | 현재 결정·남은 사항 |
| --- | --- | --- |
| M29 Signed Write | Zephyr host `BT_SIGNING`은 `DEPRECATED` | 기본 OFF의 `NUCODE_BLE_LegacySigning`, legacy opt-in으로 구현. W07-C CSRK/counter 영속화·replay 거부 PASS; 통합·회귀와 최종 지원 판정 잔여 |
| M29 EATT | Zephyr host `BT_EATT`는 `EXPERIMENTAL` | 기본 OFF의 `NUCODE_BLE_EATT`, experimental opt-in으로 구현. W07-C 암호화·2 bearer 부하 PASS; 통합·회귀와 최종 지원 판정 잔여 |
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
| M28 | 단일 링크 GAP, 기존 PHY 갱신·MTU 교환, 광고·스캔·연결 수명주기 | per-link GAP handle/event/control, multi-role/link, 확장·주기 광고·PAwR, privacy |
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

**NU54DK 3개와 독립 DAP/UART 3경로를 2026-09-13 W07에서 확인**했다. M28 packet 분모는 세
UART와 수신측 GATT/periodic sequence·payload hash를 같은 nonce로 결합했다. 외부 sniffer와
Android/iOS/Windows/Linux cross-vendor matrix는 M28 PASS에 포함하지 않으며 후속 단계에서 판정한다.

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

M28 GAP/multi-link 값은 9개 test ID로 확정·실행했고, M29는 착수 계약·readiness의 10개
시험 ID 중 8개를 통과했다. M29의 남은 MULTI/REG 기준도 해당 계약을 따른다.
M30 이후의 수치는 아직 **미확정**이다. 임의 숫자를 제품 보증으로 채우지 않고, 선택 profile과 장비가 결정되면 P05에서
숫자·단위·계산식·측정 수단을 채운다. `장시간`, `안정적`, `저지연`만으로 합격 기준을 대신하지 않는다.

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

- M28의 P01~P06 준비, W01 실제 HCI, W02~W06 구현, W07 9개 실기와 W08 문서·인계를 완료했다.
  현재 상태는 8/8이며 M29~M33과 v0.5.0 공개는 완료 처리하지 않는다.
- 구현·Host·build·실기·상호운용·공개 결과를 분리하고 exact source/profile·조건·raw log를 연결한다.
- 적용 가능한 필수 기능은 증거가 있어야 완료한다. 기능 제외·보증 범위 축소·SDK 교체가 필요하면
  별도 범위 결정으로 기록하고, 조용히 삭제하거나 성공으로 바꾸지 않는다.
- 문서상의 기능 계획과 Bluetooth/Matter 제품 인증 취득은 별개다.
- v0.4.0·v0.4.1 공개 승인은 v0.5.0 공개 승인이 아니다. M33에서 exact 결과·자산 기준으로 공개 범위를 확정한다.
- 다음 작업 보고에는 완료 범위·현재 항목·남은 항목과 **해당 작업의 분모**를 적는다.
  P 준비 체크, M28~M33의 6개 마일스톤, v0.4.0의 T13 분모 58을 섞지 않는다.
