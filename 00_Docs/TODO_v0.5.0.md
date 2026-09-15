# v0.5.0 실행 계획 — 전체 Bluetooth 기능·NCS 예제·다중 Host

현재 설치·지원 배포는 **v0.4.1 하나**이며 v0.4.0 M27까지의 기능 기준선과 v0.4.1 설치기
유지보수는 완료했다. 이 문서는 다음 제품선의 진행 상태·남은 작업과 판정 산출물을 관리한다.
**M28은 W01~W08·9개 test ID, M29와 M30은 각각 W01~W08·10개 test ID를 완료했다.
M30-W08 `M30-POWER-01`은 네 지점 × 3회 실제 전원 차단 12/12를 통과했고 HOST-W01~HOST-W03도
완료했다. M31-W01·W02는 구현 진행 중이며 완료 0/8, M32·M33은 미착수**다. M28~M30 완료는 v0.5.0 공개, mobile/desktop 전체 상호운용 또는
Bluetooth qualification 완료가 아니다. 현재 v0.4.1 사용자 지원과 후속 개발은 별개다.

| 정보 | 단일 원본 |
| --- | --- |
| M28~M45 순서·전체 상태 | [제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>) |
| BLE 기능군별 목표·완료 조건 | [경쟁 마일스톤](<01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>) |
| v0.5.0 착수 체크·결정 상태 | 이 문서 |
| 재개 복구·Adafruit 개선 과제의 배치 | [개정 실행 순서](<01_아두이노 코어 설계/18_문서_전면검토와_개선_마일스톤.md>) |
| M28 API·자원·시험 계약 | [M28 착수 계약](<01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>) |
| M28 기계 판정 원본 | [`m28-ble-readiness.json`](../variants/nu54dk/m28-ble-readiness.json) |
| M29 API·정책·자원·시험 계약 | [M29 착수 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>) |
| M29 기계 판정 원본 | [`m29-ble-readiness.json`](../variants/nu54dk/m29-ble-readiness.json) |
| M30 보안·OOB·profile·DFU 계약 | [M30 착수 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>) |
| M30 기계 판정 원본 | [`m30-ble-readiness.json`](../variants/nu54dk/m30-ble-readiness.json) |
| M31 실행 TODO | [M31 TODO](TODO_M31.md) |
| M32 최신 LE·Mesh·공존 TODO | [M32 TODO](TODO_M32.md) |
| M33 전체 예제·상호운용·공개 TODO | [M33 TODO](TODO_M33.md) |
| 기능별 upstream·제공 경로·예제·검증 | [전체 Bluetooth 기능 실행 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>) |
| v0.5.0 Windows·Ubuntu·macOS Host 계약 | [다중 Host 지원 착수 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>) |
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
| M29 W07 3보드·회귀·Windows와 W08 완료 | [149번 기록](<04_검증 기록/149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>) |
| M30 W01 capability | [152번 기록](<04_검증 기록/152_M30_W01_capability_실기_완료.md>) |
| M30 W02 link별 security·pairing | [153번 기록](<04_검증 기록/153_M30_W02_link별_security와_IO_5종_완료.md>) |
| M30 W03 유선 OOB·bond/privacy·NFC adapter | [154번 기록](<04_검증 기록/154_M30_W03_유선_OOB_bond_privacy_NFC_adapter_완료.md>) |
| M30 W04 일곱 BLE profile | [155번 기록](<04_검증 기록/155_M30_W04_7개_BLE_profile_완료.md>) |
| M30 W05 MCUboot layout·서명 | [156번 기록](<04_검증 기록/156_M30_W05_MCUboot_layout_signing_완료.md>) |
| M30 W06 secure BLE DFU·negative·rollback | [157번 기록](<04_검증 기록/157_M30_W06_secure_BLE_DFU_negative_rollback_완료.md>) |
| M30 W07 세 보드 secure multi-link | [158번 기록](<04_검증 기록/158_M30_W07_3보드_secure_multi_link_완료.md>) |
| M30 W08 전원 HIL 주입 직전 준비 | [159번 기록](<04_검증 기록/159_M30_W08_전원_HIL_주입_직전_준비.md>) |
| M30 W08 실제 전원 HIL과 M30 완료 | [161번 기록](<04_검증 기록/161_M30_W08_실제_전원_HIL과_M30_완료.md>) |

## 1. 다음 착수 순서

### 2026-09-16 재배치

사용자 목표는 **고정 NCS v3.4.0에서 nRF54L15가 할 수 있는 Bluetooth 기능과 예제를 NU54DK의
Arduino 환경에서 사용할 수 있게 하는 것**이다. 구현 방식은 wrapper/direct/profile/template 중
기능에 맞게 정하고 upstream sample·역할·test ID를 전수 추적한다. 계획 문서 작성은 구현 완료에 포함하지 않는다.

| 트랙 | 작업 분모·현재 완료 | 다음 구현과 역할 |
| --- | --- | --- |
| M31 | **0/8** | W01 전체 sample 원장·capability → W02 ISO → W03 전체 Audio profile; W04 DF·W05 CS → W06~W08 통합·마감 |
| M32 | **0/12** | W01~W05 최신 LE/Nordic, W06~W08 Mesh/1.1/DFU, W09~W10 단독 radio/공존, W11~W12 회귀·마감 |
| M33 | **0/8** | W01~W04 catalog·GATT/beacon·ecosystem·HCI/DTM, W05~W06 예제/통합, W07~W08 Host·RC·공개 |
| Host | **3/8** | HOST-W04 Ubuntu prerequisite·path·권한부터 시작; HOST-W05~HOST-W08은 별도 잔여 |

M31/M32·독립적인 M32-A·M33 예제 준비·Host 작업은 추가 외장 장치 확보를 기다리지 않고 진행한다.
M31 8/8과 HOST-W04~HOST-W06 완료는 독립 집계하며 v0.5.0 공개에서 M33이 결합한다.
사용자가 보드 3개 연결을 확인했다. 실제 mapping은 재검증하며, 정밀 RF·음질·거리/각도 보정은
필수 gate 밖으로 변경한다. 보드 기반 실제 데이터·보안·복구 검증은 계속 필수다.

### 최종 사용자 결정 — 구현과 실물 검증의 책임

| 범위 | 개발에서 반드시 완료할 일 | 실제 운용·실물 검증과 v0.5.0 gate |
| --- | --- | --- |
| Apple/Google 등 외부 ecosystem/peer | 동작 가능한 기능·예제·설정·credential 입력 경로·자동 가능한 unit/negative/build 검사 | 사용자가 추후 수행. 미실행 NOT RUN은 개발·공개 차단 아님; 검증된 상호운용 주장은 금지 |
| 마이크·스피커·외장 장치 | 실제 연결해 사용할 API·설정·예제·연결 안내와 가능한 자동 검사; 합성 보드 경로 검증 | 외부 장치의 실제 운용·호환성은 사용자 후속. 개발·공개 차단 아님 |
| DF 원시 IQ | 기본 SDC TX와 Zephyr LL RX 후보 구분, 배열 없이 수신 구성 조사·build·적용 가능한 2보드 HIL | 장비 대기가 아닌 소프트웨어 지원성/기능 판정. 각도 산출·실제 안테나 전환은 별도 외장 경로 |
| Ubuntu/macOS 사용자 Host | prerequisite·launcher/resolver·설치/업로드 도구·자동 가능한 검사와 재현 가능한 검증 절차 | 최종 릴리스 단계에서 사용자가 실물 검증. 중간 개발은 차단하지 않되 최종 Host 지원 gate는 유지 |

세 보드의 USB 접근·명확한 mapping을 전제로 추가 부품 연결을 중간 선행조건으로 요구하지 않는다.
이는 지원되는 기능의 실제 자동 HIL이나 결함 수정을 면제하는 결정이 아니다. 사용자 후속 실기,
기술적 미지원, 미해결 결함을 다른 상태로 기록한다. 상세 원본은 [전체 기능 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)이다.

### 보존하는 M28~M30 기준선

M28 준비는 P01 기준선과 정적 지원 원장부터 시작했으며, API·자원·유한 시험 계약까지 고정했다.
M28-W01 capability부터 W08 문서·인계까지 완료했다. M29도 W01 capability, W02~W06
GATT·cache·CoC 구현, W07 두/세 보드 HIL·회귀·Windows 상호운용과 W08을 완료했다.
현재 개발 지점은 **M30 완료, M31-W01·W02 구현 진행 중**이다. M30-W01은 exact
`6254398c…`에서 parser 13/13, target 1/1과 실제 capability 7/7을 완료했다. M30-W02는 exact
`4f91e347…`에서 고정 link별 보안 상태와 pairing 응답을 구현하고 IO capability 5종을 각각
10회, 총 50/50 PASS했다. M30-W03은 유선 OOB 20/20·MITM 20/20, mismatch accept 0과
bonded reconnect 20/20·RPA rotation 3·metadata migration 1·stale key accept 0을 완료했다.
NFC adapter는 Host/target build를 통과했고 RF는 범위 결정대로 `NOT RUN`이다. M30-W04는
profile 7개와 서비스별 100 operation을 두 보드에서 payload·driver 오류 없이 완료했다. M30-W05는
별도 secure profile의 MCUboot dual-slot과 외부 ECDSA P-256 서명을 구현하고 signed boot 20/20,
unsigned·wrong-key image accept 0을 실제 한 보드에서 확인했다. M30-W06은 exact `df9ea2a3…`에서
인증 BLE update 10/10, hash mismatch·unconfirmed normal boot 0, negative 5종 × 20회와
invalid/rollback accept 0을 확인했다. M30-W07은 exact `d94f5ec3…`에서 세 role target 3/3과
동시 두 secure link, handle별 보안 연산 100회, cross-link/security/key-size 오류 0을 확인했다.
다중 Host
`HOST-W01` inventory, `HOST-W02` descriptor/resolver와 `HOST-W03` launcher도 완료했다.
P01~P06은 별도 전역
마일스톤이 아닌 준비 체크다. 코드 작성 전에는 영향을 받는 P02/P03 결정이, 각 물리 시험 전에는
해당 P04/P05 조건이 확정되어야 한다.
사용자 후속 외장 실기를 M31 또는 Host 구현·자동 검사의 선행조건으로 되돌리지 않는다.

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
| M29-W07 | **완료 — SIGN/EATT·3보드 MULTI/REG·Windows GATT PASS** | exact `c71ef4a2…`·`16eb8fce…`·`a964ae20…` 원본 증거 유지 |
| M29-W08 | **완료** | `MixedGattCocLinks`, 장문 target 분할, exact `ab3f85d3…` 3보드 재검증, 문서·지원표·M30 인계 |

### 현재 개발 지점: M30 완료, M31-W01·W02 진행 중

Exact `16eb8fce204f656beb6ed0a0d6f763cc7d492215`의 세 보드 `M29-MULTI-01`은 mixed DUT의
두 link 각각 GATT·CoC 1,000회와 cross-link/payload/drop 오류 0을 확인했다. 같은 revision의
`M29-REG-01`은 M19/M20/M21/M28 회귀 4/4·실패 0이다. exact
`a964ae205e237d90149f6d2c0eb0ec6492492a33`의 Windows/Intel GATT는 discovery, read, 두 write,
notify, indicate와 2회 재연결을 PASS했다. 원본 byte는 Base64 archive와 SHA-256 manifest로
보존한다. W08 분할·예제 반영 뒤 exact `ab3f85d3cb505f8f82865becfbd8bd0fe8511f27`로 세 role을
다시 build하고 같은 3보드 `M29-MULTI-01`을 재실행해 2-link와 오류 0을 재확인했다. M30-W01은
exact `6254398c1ea4e7320b1905014dce1c2a405a53fc` target과 고정 NU54DK 한 대에서 security/OOB/
profile/DFU capability 7/7, revision mismatch 0을 확인했다.
M30-W02는 exact `4f91e347e8e36e77c959de90def7d9c2622be30b`에서 Just Works L2 10회와
MITM 가능한 네 조합 L4 40회를 모두 통과했고, 예상 밖 인증 실패·cross-link 수용은 0이었다.
M30-W03은 exact `284254c7176fa0bf996137567952ae9d0ce5b4c0`에서 유선 OOB·MITM 20/20과
mismatch accept 0을, exact `83a4d11a20e6d16ed0db56382c20133f448cff91`에서 bond reconnect
20/20·RPA rotation 3·metadata migration 1·stale key accept 0을 확인했다. NFC adapter는
구현·Host/target build를 통과했지만 RF HIL은 범위 결정대로 `NOT RUN`이다. M30-W04는 exact
`d2a0b96888bd2f7c75d6ed02d46c0a3751e2d283`에서 BAS·DIS·HID keyboard/mouse/consumer-control,
HRS와 ESS catalog 7/7, 서비스별 100 operation과 payload/driver 오류 0을 두 보드에서 확인했다.
M30-W05는 exact `b16b44f405ee8617a675cae9f5dfcc027f03816a`에서 기본 loaderless profile을
보존한 별도 secure profile, MCUboot dual-slot과 저장소 밖 ECDSA P-256 키를 구현했다. 실제
signed boot 20/20, unsigned accept 0, wrong-key accept 0을 확인했으며 power cut은 실행하지 않았다.
M30-W06은 exact `df9ea2a3ee5111c350364a938409021d379810e2`에서 authenticated BLE SMP
update 10/10, negative 5종 × 20회, invalid image accept 0과 unconfirmed image의 confirmed v10
복귀를 확인했다. M30-W07은 exact `d94f5ec310e99611ab021854c43dd6d72031e825`에서 세 보드의
동시 두 secure link와 Peripheral/Mixed/Central의 handle별 보안 연산 총 400회, cross-link·security·
key-size 오류 0을 확인했다. M30-W08은 exact `ae5186f7790a748641fb04128c16156519ee1017`에서
네 주입 지점 × 3회 실제 전원 차단 12/12, recovery failure 0, invalid image boot 0을 확인했다.
Reset 대체와 mass erase는 없었다. 상세 결과와 60초 MCUboot 관찰 훅/Host timeout 경계 감사는
[161번 완료 기록](<04_검증 기록/161_M30_W08_실제_전원_HIL과_M30_완료.md>)에 보존한다.

M30의 구현·장비 계약은 [M30 착수 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>)과
[`m30-ble-readiness.json`](../variants/nu54dk/m30-ble-readiness.json)을 따른다. [159번 준비 기록](<04_검증 기록/159_M30_W08_전원_HIL_주입_직전_준비.md>)과
[160번 재개 계획](<04_검증 기록/160_전체_문서_검토와_마일스톤_개정.md>)은 당시 상태의 역사적 근거로 유지한다.
다음 제품 작업은 [M31 TODO](TODO_M31.md)의 ISO·LE Audio·방향탐지·connected Channel Sounding
지원성·예제 구현과 보드 기반 자동 기능 검증이다.

M28과 M29 각 단계의 구현·시험 수치는 위 작업표와 해당 계약에서 확인한다.
시도별 실패·CMSIS-DAP 진단·수정·재검증 상세는 [140번](<04_검증 기록/140_M28_W07_3보드_HIL과_W08_완료.md>)과
[141~161번 검증 기록](<04_검증 기록/README.md>)에 보존하며 이 TODO에 중복하지 않는다.
정적 SDK `candidate`, Host 시험, target build와 실기 PASS는 서로 다른 증거다.

## 2. 현재 확인된 지원성 결정 항목

아래 표는 고정 NCS v3.4.0의 source 상태와 프로젝트의 결정·실기 결과를 구분한다.
SDK나 controller/profile을 바꾸면 해당 판정과 관련 회귀 범위를 다시 확인한다.

| 대상 | 고정 SDK의 상태 | 현재 결정·남은 사항 |
| --- | --- | --- |
| M29 Signed Write | Zephyr host `BT_SIGNING`은 `DEPRECATED` | 기본 OFF의 `NUCODE_BLE_LegacySigning`, legacy opt-in으로 구현. CSRK/counter 영속화·replay 거부와 통합 회귀 PASS |
| M29 EATT | Zephyr host `BT_EATT`는 `EXPERIMENTAL` | 기본 OFF의 `NUCODE_BLE_EATT`, experimental opt-in으로 구현. 암호화·2 bearer 부하와 통합 회귀 PASS; 안정 API로 승격하지 않음 |
| M31 방향탐지 | 기본 SDC의 CTE 송신은 AoA 지원·AoD 미지원. 전체 RX/IQ 경로 지원을 뜻하지 않음 | 송신·수신·안테나 전환을 분리해 controller/profile 적용성 판정. 대체 Zephyr LL은 별도 후보이지 검증 완료 대안이 아님 |
| M31 Audio 확장 | Host source에는 BAP/CAP 외 다수 역할/profile이 존재; sample의 nRF54L15 대상 여부는 개별 확인 필요 | PACS/ASCS·BASS·CSIP·PBP·VCP/VOCS/AICS·MICP·MCP/MCS·CCP/TBS·TMAP/GMAP/HAP/HAS를 W03에서 전수 구현/적용성 판정 |
| M32-A 최신 LE | 고정 SDC의 power/path loss·subrating·SCA·frame space·shorter interval·extended feature set 및 Nordic 확장 | M28의 기존 6개 capability PASS와 구분해 W01~W05에 신규 구현·예제·negative 배정 |
| M32-A EAD/coding·자원 | EAD Host source·광고 coding 설정, nRF54L15용 multi-set/identity 예제 존재 | EAD/coding은 적용 build·runtime 확인 전 candidate; 1 advertising set 기본값과 확장 preset 분리 |
| M32-B Mesh 1.1 | Remote Provisioning·SAR·Opcode Aggregator·Large Composition·Private Beacon/Proxy·Solicitation·Subnet Bridge source 존재 | node/model 역할·RRAM/RAM·BLOB/DFU/Distribution과 함께 W06~W08에서 검증 |
| M32 공존 | 802.15.4/ESB와 BLE 병행시험에는 동작하는 단독 radio 경로가 먼저 필요 | M32 안에서 최소 검증용 기반·단독 TX/RX를 확보하고, M38/M39는 공개 API·예제·일반 제품화 확장으로 연결 |
| M33 외부 ecosystem·진단 | Fast Pair·ANCS/AMS·HCI/DTM 예제별 peer/credential/transport 전제 존재 | template/direct 제공, 외부 행 NOT RUN 명시; BR/EDR·nRF54L15 비대상 nrf_dm는 비적용 근거 기록 |

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
| M30 | 보안/profile → 최소 boot/layout·서명·BLE update → 실패 복구 + HOST-W01~HOST-W03 | M34~M36이 재사용할 보안 계약과 Host 공통 backend·Windows 전용 가정 inventory |
| M31-A | ISO/CIS/BIS·combined/time sync → LC3·전체 Audio profile → 합성 데이터/제어 HIL | stream/buffer·codec·역할별 짝 예제·미지원/외부 I/O 미검증 행 |
| M31-B | controller 적용성 → CTE TX와 배열 없는 raw IQ 수신 후보 조사/build·적용 HIL; AoD 개별 판정 | TX/RX 증거 깊이, 고정 Zephyr LL 후보의 실제 결과, SDC AoD 미지원·각도/전환 후속 경로 |
| M31-C | Connected ACL·CS/RAS·raw 결과/거리 산출 → security/peer loss/recovery | 기능 동작 근거; 정밀 거리 보정·정확도는 필수 밖 |
| M32-A | power/path loss → timing/subrate → adv/EAD/identity/resource → Nordic LLPM/QoS/event | 새 자원 preset·실험적 opt-in·짝 예제·2/3보드 기능/negative |
| M32-B | Mesh 기본 → Mesh 1.1 → BLOB/Mesh DFU/Distribution | node/model·key/settings·transfer·복구, 내부 RRAM/배포자 한계와 M36 인계 |
| M32-C | 최소 radio/profile·802.15.4/ESB 단독 TX/RX → 선택 공존·복구 | MPSL ownership·loss/서비스 지연·M38/M39 공개 예제 인계 |
| M33 | GATT/beacon·ecosystem·HCI/DTM 예제 → 전체 parity·interop → HOST-W08/RC → 공개 | 누락 0 원장·예제 제공 범위·실행 증거·세 Host 지원/제약·qualification 적용성 |

M31-A/B/C는 **M31 내부 작업 ID**다. 하나를 완료해 M31 전체 완료로 계산하지 않는다.
M30 최소 DFU에서는 고정 layout·신뢰키·초기 설치·BLE 갱신·전원 차단 복구와 Arduino 제공 형태를
별도 `secure_ble_dfu` profile에 고정했다. 기본 `--no-sysbuild` build·native HEX upload를 그대로 MCUboot 지원으로 간주하지
않으며, 기본 loaderless 경로는 유지한다. M36은 다중 layout/transport와 hardening 확장이다.

M42 시작 전에는 사용할 Matter transport, Thread 선택 시 M40의 network 근거, M32의 적용 공존
조합, update 경로, RAM/RRAM·저장소 예산과 개발용/생산용 credential 정책을 연결한다.
NU54DK의 외장 flash 미탑재와 factory-data partition 적용성은 설계 입력이며 Matter 불가능 판정이 아니다.

M33의 사용자 경로 정리에 기존 API만 사용하는 ARF-04A 목적별 예제를 연결한다.
Buffered NUS·PWM pool·별도 편의 API는 M30/M33 필수 구현에 합치지 않고
[별도 개선 작업](<01_아두이노 코어 설계/18_문서_전면검토와_개선_마일스톤.md>)으로 검증한다.
BLE role-budget ARF-01은 M32-W04로 통합해 기본 2-link 및 확장 역할 preset과 한 번 검증한다.
후속 배포 버전은 착수 gate에서 확정하며 기존 M34~M45 제품선을 임의 재배치하지 않는다.

## 5. 장비와 정량 판정 기준

### 장비 확보 상태

**NU54DK 3개와 독립 DAP/UART 3경로를 2026-09-13 W07에서 확인**했다. M28 packet 분모는 세
UART와 수신측 GATT/periodic sequence·payload hash를 같은 nonce로 결합했다. 외부 sniffer와
Android/iOS/Linux cross-vendor matrix는 M28/M29 PASS에 포함하지 않는다. Windows/Intel은 M29의
기본 GATT 상호운용만 PASS했고 EATT·robust caching이나 모든 adapter 지원을 뜻하지 않는다.

| 시험군 | 계획상 필요한 구성 | 착수 시 확인할 사항 |
| --- | --- | --- |
| BLE 기본·multi-link | NU54DK 2~3개와 수신측 sequence/hash | probe SHA-256·serial·role·revision; OS peer는 별도 M33 행 |
| ISO/LE Audio | 2보드 송수신, 3보드 source/sink/assistant 또는 broadcast; 합성 PCM/LC3 | 실제 SDU·codec·제어·buffer/복구, 외부 microphone/speaker/codec는 별도 미검증 행 |
| Direction Finding | CTE TX 1보드; 기본 안테나의 raw IQ 수신 후보 조사/build 후 적용 가능한 2보드 | 기본 SDC RX 미제공·Zephyr LL RX build/runtime 미검증; 배열 유무만으로 수신 불가 판정 금지. 실제 각도와 전환은 별도 |
| Channel Sounding | CS initiator/reflector 2보드, 선택 3번째 peer | procedure/RAS·결과·보안·재연결 기능; 정밀 거리·방향 보정 요구 없음 |
| Mesh/coexistence | 승인 topology의 2~3노드, BLE/802.15.4/ESB traffic 관측 | 역할별 노드 수·단독 통신·조합·부하·서비스 지연; 새 power-loss 확장은 M36 후속이며 v0.5.0 추가 필수 gate 아님 |

사용자가 제외한 정밀 계측은 `out_of_scope_by_user_decision`, 사용자 후속 외장/상호운용 실기는
`NOT RUN`과 후속 책임·비차단 범위를 함께 기록한다. DF RX 후보의 build/runtime 미검증은
별도 기술 상태이며 장비 부족 또는 `UNSUPPORTED`로 자동 분류하지 않는다. 고정 controller의
실제 비지원은 근거와 함께 기록한다. 3보드 결과를 더 큰 topology의 PASS로 확대하지 않는다.

Android/iOS/Linux 항목은 **BLE 상대 장치 상호운용**이며 Arduino Core 개발·설치 Host matrix와
서로 다른 시험이다. v0.5.0의 Host 확대는 [별도 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)으로
Windows 10/11 x64, Ubuntu 24.04 이상 AMD64, macOS 26 이상 Apple Silicon을 다룬다. Peer 자체 미지원 기능은 근거를 남기고 해당 칸을
비적용으로 분리한다. 실제 외부 peer 시험은 사용자 후속·개발/공개 비차단이며 필수 Host 실기와
구분한다. Ubuntu/macOS Host 실기는 최종 릴리스 때 사용자 검증 전까지 `NOT RUN`으로 남긴다.

### 실행 전에 고정할 합격표

M28 GAP/multi-link 9개와 M29 ATT/GATT·L2CAP 10개 test ID를 모두 확정·실행했다.
M30은 [착수 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>)의 10개 test ID와 수치가 확정됐다.
M31~M33 TODO의 시험 ID·계획 기준은 구현 시 계약/기계 원장에 고정한다. W01에서 역할별
설정·하위 case·숫자·단위·계산식·관측 수단·최대 시간을 확정한 뒤 실행한다. 계획 수치는 성능
보증이나 실제 PASS가 아니다. `장시간`, `안정적`, `저지연`만으로 합격 기준을 대신하지 않는다.

| 시험군 | 반드시 고정할 입력 | 수치·판정 항목 |
| --- | --- | --- |
| GAP/multi-link | 연결 수·역할·PHY·MTU/DLE·interval·전송률·환경 | reconnect 반복 수·timeout, 요청/실제 연속 시간, 송수신 분모·허용 loss/중복/순서 오류, 자원 복구 기준 |
| GATT/CoC/EATT | value/MTU·channel/credit 수·동시 부하·malformed 입력 | payload 일치, 오류 종류·횟수, 최대 서비스 지연·복구 timeout, leak 판정 |
| Security/DFU | IO/OOB·key 정책·서명·image/layout·중단 주입 지점 | 거부해야 할 입력·예상 오류, 전원 차단 반복 수·부팅/복구 timeout, rollback·데이터 보존 기준 |
| ISO/Audio | codec/profile·SDU·buffer·clock·부하 | loss 분모·허용률·sequence/payload·codec 완료·underrun/overrun·복구 시간; 관측 가능한 지연은 측정법과 함께 기록 |
| DF/CS | 역할·controller·CTE/CS procedure·결과 형식·환경 | command/결과 수·유효성·보안 실패·연결 복구; RF 각도/거리 절대 오차와 보정은 필수 밖 |
| Mesh/coexistence | topology·model·동시 조합·각 protocol 부하 | 전달률·서비스 지연 상한·starvation 판정, power-cycle 수·복구 timeout·soak 시간 |

각 test ID에는 최대 실행 시간·반복 수·오류 중단 조건·진단 후 동일 조건 재검증 횟수도 고정한다.
실패는 원인·수정·동일 조건 재검증을 연결하며 무한 재시도로 통과를 만들지 않는다.
통신 손실과 관측 가능한 software 지연·복구 허용치는 기능별 측정법과 함께 고정한다.
모든 주변장치 조합이나 정밀 RF·음질·거리/각도 계측 품질을 일괄 보증하지 않는다.
v0.4.0의 범위 제외는 그대로 보존한다.

## 6. 결과·공개 규칙

- M28·M29·M30의 capability·구현·Host·target·유한 HIL·문서 인계를 완료했다.
  M31~M33과 v0.5.0 공개는 완료 처리하지 않는다.
- 구현·Host·build·실기·상호운용·공개 결과를 분리하고 exact source/profile·조건·raw log를 연결한다.
- 적용 가능한 필수 기능은 증거가 있어야 완료한다. 기능 제외·보증 범위 축소·SDK 교체가 필요하면
  별도 범위 결정으로 기록하고, 조용히 삭제하거나 성공으로 바꾸지 않는다.
- 이번 문서 개정은 2026-09-16의 사용자 범위 결정이다. 정밀 RF/audio/거리/각도 계측 제외를 적용하고
  전체 NCS Bluetooth 기능·예제를 명시한 단계에 배치했다. M31-W01 inventory·readiness·
  capability parser/target 및 W02 CIS 개발 후보는 구현 중이며 clean 실기와 나머지 기능 gate가 잔여다.
- Apple/Google 및 외장 장치의 실제 운용·검증을 사용자 후속으로 확정한 결정은 v0.5.0 개발·공개
  gate에서 적용한다. 구현·예제·가능한 자동 검사는 필수이며, 사용자 후속 NOT RUN은 PASS가 아니다.
  원장의 구현 요구·검증 책임·개발/공개 차단 여부를 독립 필드로 구현해 이 구분을 검사한다.
- 문서상의 기능 계획과 Bluetooth/Matter 제품 인증 취득은 별개다.
- v0.4.0·v0.4.1 공개 승인은 v0.5.0 공개 승인이 아니다. M33에서 exact 결과·자산 기준으로 공개 범위를 확정한다.
- v0.5.0부터 세 Host 계열을 정식 범위로 공개하려면 지원표의 모든 OS 행에 clean 설치·전체 예제
  build·대표 upload/runtime·lifecycle 증거가 있어야 한다. 미래 OS는 자동 PASS로 올리지 않는다.
- 다음 작업 보고에는 완료 범위·현재 항목·남은 항목과 **해당 작업의 분모**를 적는다.
  P 준비 체크, M28~M33의 6개 마일스톤, v0.4.0의 T13 분모 58을 섞지 않는다.
