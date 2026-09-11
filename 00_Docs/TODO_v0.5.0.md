# v0.5.0 착수 계획 — BLE 확장과 지원 범위 판정

현재 정식 배포는 **v0.4.0**이며 M27까지 완료했다. 이 문서는 다음 제품선의 착수 순서와
판정 산출물을 정의한다. **M28~M33은 모두 계획·구현 미착수**이며, 문서 정비를 구현 완료나
새 물리 PASS로 세지 않는다. 현재 사용자의 v0.4.0 시험과 후속 개발은 별개다.

| 정보 | 단일 원본 |
| --- | --- |
| M28~M45 순서·전체 상태 | [제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>) |
| BLE 기능군별 목표·완료 조건 | [경쟁 마일스톤](<01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>) |
| v0.5.0 착수 체크·결정 상태 | 이 문서 |
| v0.4.0 완료·보존할 지원 계약 | [v0.4.0 완료 TODO](TODO_v0.4.0.md) |
| 이번 계획 정비의 변경·검사 | [127번 기록](<04_검증 기록/127_후속_마일스톤_지원_경계와_착수_계획_정비.md>) |

## 1. 다음 착수 순서

다음 구현 요청을 받으면 **P01의 source·환경 확인부터 시작**하고, M28의 첫 산출물로 P02 지원
원장을 만든다. P01~P06은 별도 전역 마일스톤이 아닌 준비 체크다. 코드 작성 전에는 영향을 받는
P02/P03 결정이, 각 물리 시험 전에는 해당 P04/P05 조건이 확정되어야 한다.
M31 전용 장비가 미확보라는 이유로 독립적인 M28 문서·Host 작업까지 차단하지 않는다.

| 체크 | 상태 | 산출물·완료 조건 |
| --- | --- | --- |
| P01 기준선 확인 | 미착수 | 실제 Core/board/SDK/toolchain revision, branch·미커밋 변경, 재사용할 증거와 변경 영향 범위를 기록 |
| P02 기능 지원 원장 | 미착수 | nRF54L15·선택 controller·host Kconfig·HCI feature를 대조하고 지원/조건부/미지원/미판정과 근거를 기능·역할별 기록 |
| P03 공개 API·profile 경계 | 미착수 | 기존 API 회귀와 신규 API를 분리하고 per-link 상태·호환성, controller/profile별 자원·메모리·오류 계약을 결정 |
| P04 장비·상호운용 matrix | 미착수 | 시험별 보드 수·peer/OS/version·RF/audio 구성·측정 수단과 확보 상태를 기록 |
| P05 수치 합격 기준 | 미착수 | 아래 시험군별 입력·반복·시간·허용치·중단 조건·유한 진단 예산을 실행 전에 고정 |
| P06 실행 목록 고정 | 미착수 | P02~P05를 test ID·필수/조건부 범위·명령·증거 위치와 결합하고 M28부터 실행할 목록을 확정 |

P02의 정적 SDK 조사와 실제 HCI 조회는 다른 증거다. 보드 조회를 하지 않았으면 HCI 확인은
`NOT RUN`으로 남긴다. 미지원 판정에 controller 한계와 칩 자체 비적용을 혼동하지 않는다.
미판정 항목을 지원 또는 범위 제외로 자동 승격하지 않는다.

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

현재 장비 상태는 **미확인**이다. 과거 두 보드 시험이나 사용자의 현재 v0.4.0 테스트로 다음
장비가 모두 확보됐다고 판단하지 않는다. 이 문서는 구매·연결 변경 지시가 아니다.

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

- 이번 문서 작성으로 P01~P06 또는 M28~M33을 완료 처리하지 않는다.
- 구현·Host·build·실기·상호운용·공개 결과를 분리하고 exact source/profile·조건·raw log를 연결한다.
- 적용 가능한 필수 기능은 증거가 있어야 완료한다. 기능 제외·보증 범위 축소·SDK 교체가 필요하면
  별도 범위 결정으로 기록하고, 조용히 삭제하거나 성공으로 바꾸지 않는다.
- 문서상의 기능 계획과 Bluetooth/Matter 제품 인증 취득은 별개다.
- v0.4.0 공개 승인은 v0.5.0 공개 승인이 아니다. M33에서 exact 결과·자산 기준으로 공개 범위를 확정한다.
- 다음 작업 보고에는 완료 범위·현재 항목·남은 항목과 **해당 작업의 분모**를 적는다.
  P 준비 체크, M28~M33의 6개 마일스톤, v0.4.0의 T13 분모 58을 섞지 않는다.
