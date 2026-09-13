# v0.5.0 착수 계획 — BLE 확장과 지원 범위 판정

현재 설치·지원 배포는 **v0.4.1 하나**이며 v0.4.0 M27까지의 기능 기준선과 v0.4.1 설치기
유지보수는 완료했다. 이 문서는 다음 제품선의 착수 순서와 판정 산출물을 정의한다.
**M28은 M28-W01~W08과 9개 test ID를 완료했고 M29는 W07 HIL 준비, 6/8이다. M30~M33은
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
| M29 W07 Signed Write·EATT HIL 준비 | [147번 기록](<04_검증 기록/147_M29_W07_Signed_Write_EATT_HIL_준비.md>) |

## 1. 다음 착수 순서

M28 준비는 P01 기준선과 정적 지원 원장부터 시작했으며, API·자원·유한 시험 계약까지 고정했다.
**M28-W01 capability, W02 고정 2-slot·generation handle, W03 확장 광고·스캔, W04
periodic·PAST, W05 PAwR, W06 privacy·link control, W07 두/세 보드 HIL과 W08 문서·인계를
완료했고, **M29-W01 capability, W02 link별 GATT long read, W03 long/reliable write, W04
descriptor·authorization·read multiple, W05 robust GATT cache와 W06 LE CoC를 완료했다.
W07 Signed Write·EATT 구현·Host parser·target 2/2까지 준비했고 두 exact HIL 실패를 진단 중이므로
현재 M29는 계속 **6/8**이다.
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

| 작업 묶음 | 현재 상태 | 다음 종료 조건 |
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
OFF다. W01은 고정 NCS capability image와 fail-closed protocol/parser를 구현·실행해야 완료된다.

| 작업 묶음 | 현재 상태 | 다음 종료 조건 |
| --- | --- | --- |
| M29-W01 | **완료 — parser 16/16·target 1/1·실제 capability 7/7 PASS** | exact `d604642b…` 증거와 peer-required 기능 분리 유지 |
| M29-W02 | **완료 — Host 전체 gate·target 2/2·2보드 long read 100/100 PASS** | exact `dacf6341…`, MTU 247·512 byte·corrupt/stale 0 증거 유지 |
| M29-W03 | **완료 — Host·target 2/2·2보드 reliable write 100/100 PASS** | exact `babba5a1…`, MTU 247·512 byte·corrupt/partial commit 0 증거 유지 |
| M29-W04 | **완료 — Host·target 2/2·2보드 descriptor/read multiple 100/100 PASS** | exact `068a1765…`, descriptor 4개·authorization 오판 0 증거 유지 |
| M29-W05 | **완료 — Host·target 2/2·2보드 cache migration PASS** | exact `e587c4fe…`, bonded reconnect 20·stale/corrupt accept 0 증거 유지 |
| M29-W06 | **완료 — Host·target 2/2·2보드 CoC/negative PASS** | exact `767bb4af…`, 2-channel·512 byte·각 방향 1,000 SDU·5 negative class·복구 오류 0 증거 유지 |
| M29-W07 | **진행 중 — Host 계약 12/12·parser 14/14·target 2/2 PASS** | exact commit 기준 `M29-SIGN/EATT/MULTI/REG-01` HIL과 증거 보존 |
| M29-W08 | 미착수 | 전체 회귀·예제·문서·지원 판정·CI와 M30 인계 |

M29-W02는 central/peripheral 두 link가 각각 discovery/read/write/subscription parameter와 512-byte
고정 buffer를 소유하도록 GATT client를 분리했다. 무인자 API는 central 우선 legacy view를
유지하고 handle overload와 상세 callback은 exact generation을 전달한다. long read는 ATT fragment를
종료 callback까지 누적하며 512 byte 초과, stale callback과 link 간 event 누출을 거부한다. 실제
production GATT Host 14개 시나리오, W02 source 6개와 parser 11개, exact target 2/2가 PASS했다.
두 NU54DK 실기는 MTU 247에서 512-byte read 100/100, corrupt 0, stale 0을 확인했다.
`LongGattPeripheral`·`LongGattCentral` 예제는 `v0.5.0` Arduino CI group에서 실제 BLE profile로
compile되며 Arduino IDE 예제 목록 계약에 포함된다.
W03은 응답 write의 512-byte 상한과 link별 고정 prepare transaction을 추가했다. Prepare 단계는
공개 value를 바꾸지 않고 execute 성공 시 한 번만 atomic commit하며 cancel·offset·overflow·다른
characteristic 혼합·stale generation은 거부한다. `ReliableWritePeripheral`과
`ReliableWriteCentral` 예제를 추가했고 production Host 15개 시나리오, W03 source 6개·parser
11개, exact target 2/2가 PASS했다. 두 NU54DK 실기는 MTU 247에서 512-byte reliable write
100/100, read-back 100/100, corrupt 0, partial commit 0을 확인해 `M29-LONG-01`을 PASS로 닫았다.
첫 HIL의 DAPLink UART 시작 byte `0x1c` 실패와 명시적 READY 질의로 고친 동일 조건 재검증은
[143번 기록](<04_검증 기록/143_M29_W03_long_reliable_write.md>)에 보존한다.

W04는 characteristic당 최대 4개의 고정 descriptor와 동기 read/write authorization을 추가했다.
판정 callback은 Bluetooth callback 문맥에서 bounded·non-blocking으로 실행하고 결과만 main-thread
event로 복사한다. Client descriptor cache와 discovery는 link generation별로 분리하며 다음
characteristic declaration을 먼저 찾아 현재 characteristic의 descriptor handle 범위를 고정한다.
Read Multiple은 caller handle을 link별 고정 4-entry storage로 복사하고, notification·indication은
generation handle overload와 비동기 전송용 고정 payload slot을 사용한다. 기존 무인자 API와 기존
event enum ordinal은 유지했다. Production Host 17개 시나리오, W04 source 8개·parser 11개,
Arduino BLE 예제 6개와 exact target 2/2가 PASS했다. 두 NU54DK 실기는 MTU 247, descriptor 4개,
4-handle read multiple 100/100, authorization 402회 중 허용 401·예상 거부 1, 오판·corrupt·stale 0으로
`M29-DESC-01`을 PASS로 닫았다. 첫 실기는 예상 ATT `0x08` 거부에 앞선 전역 `-EIO` event를 target이
실패로 오판했으며, 상세 GATT event에서만 exact ATT 값을 판정하도록 수정한 뒤 같은 조건에서
PASS했다. 원본과 결과는 [144번 기록](<04_검증 기록/144_M29_W04_descriptor_authorization_read_multiple.md>)에
보존한다.

W05는 bonded resolved identity·database hash·target UUID·schema version·CRC를 결합한
84-byte 고정 cache record 4개와 application database revision을 추가했다. Service Changed 또는
hash 변경은 해당 link의 handle을 먼저 폐기한 뒤 rediscovery하며 잘린·미래 schema·다른 identity·
손상 CRC record를 복원하지 않는다. `GattCachePeripheral`·`GattCacheCentral` 예제를 추가했고
production GATT Host 18개 시나리오, W05 source 9개·parser 14개, Arduino M29 예제 8개와 exact
target 2/2가 PASS했다. 두 NU54DK의 `M29-CACHE-01`은 bonded reconnect 20/20, hash read 24,
cache restore 20, Service Changed 1, migration 1, corrupt cache 거부 1, stale handle 0을 확인했다.
첫 실기의 `-ENOTCONN`은 CMSIS-DAP/GDB에서 Zephyr property bit를 공개 enum으로 직접 cast해
write를 notify로 오인한 것으로 확정했고 명시 변환 뒤 동일 조건 PASS했다. 원본과 최종 결과는
[145번 기록](<04_검증 기록/145_M29_W05_robust_GATT_cache_migration.md>)에 보존한다.

W06은 generation 기반 opaque channel handle과 server 1개·channel 2개·512-byte SDU·channel당
RX record 4개·전체 TX buffer 4개의 고정 자원을 추가했다. Stack callback payload는 복사한 뒤
`BLEDevice.poll()`에서만 공개 callback을 호출하고, credit/TX pool 고갈은 `busy`로 반환한다.
Production LE CoC Host 7개 시나리오, source 계약 7개·parser 12개, Arduino `L2capCocServer`·
`L2capCocClient` 예제와 exact target 2/2가 PASS했다. 두 NU54DK 실기는 2채널에서 512-byte SDU를
각 방향·채널당 1,000회 검증하고 malformed·offset·execute·PSM·credit 각 20회 거부, 예상 밖 수락·
payload/cross-channel·resource recovery·stale accept 0을 확인해 `M29-COC-01`과 `M29-NEG-01`을
닫았다. 첫 실행의 W06 전용 광고 PSM 필드와 공통 runner 계약 불일치는 transcript를 보존하고
역할별 기대 필드를 명시한 뒤 동일 조건에서 PASS했다. 결과는
[146번 기록](<04_검증 기록/146_M29_W06_LE_CoC_credit_buffers.md>)에 보존한다.

W07은 `NUCODE_BLE_LegacySigning`과 `NUCODE_BLE_EATT`를 별도 bundled library로 추가해 기본 BLE
profile을 바꾸지 않는다. Signed Write는 bonded CSRK와 local/remote sign counter를 저장하고,
정상 완료 event는 main thread에서 처리한다. Event queue 포화 시에는 counter rollback을 막기 위해
즉시 저장하며 저장 실패 시 link를 끊는다. EATT는 암호화된 link에서만 최대 2 bearer를 열고,
read/write overload가 unenhanced/enhanced bearer를 명시하며 상세 event가 실제 선택 bearer를
보고한다. 기존 enum ordinal과 무인자 API는 유지한다. 공개 예제 4개, W07 3개를 포함한 production
Host 전체 24개 시나리오, source 계약 12개, strict HIL parser 14개와 고정 NCS target role 2/2가
PASS했다. Windows Application Control의 첫 전체 실행 차단은 유한 4551 대기를 보강한 뒤 전체 Host
1,106개 PASS(조건부 2개 skip)로 재검증했다. Arduino M29 smoke는 `EattCentral`의 미지원
`<cstring>`을 `<string.h>`로 고친 뒤 GATT·CoC·cache·signing·EATT 예제 **14/14 PASS**로
처음부터 재검증했다. Exact `fb03df6e…`의 첫 HIL은 두 보드의 flash·READY·CLEAR·reboot 뒤 legacy
광고가 flags+128-bit service UUID+manufacturer nonce로 41/31 byte가 되어 `-EMSGSIZE`로 중단됐다.
CMSIS-DAP에서 CPU fault 0과 RADIO 미시작을 확인한 뒤 중복 service 광고·filter를 제거하고 exact
nonce 검사와 23/31 byte compile-time 상한을 유지했다. 수정 source 계약 30/30과 target 2/2는
PASS했다. Exact `fbbb0d11…` 재실기는 광고·scan·pair·bond 재부팅 복원까지 통과한 뒤 첫 sign
재연결의 `discovery_result/code=0`에서 멈췄다. DAP/UART와 `CFSR=0`, `HFSR=0`, 종료 SRAM을
확인했고 GATT event 종류와 discovery 완료 뒤 상태 실패를 분리해 보고하도록 target과 Host 계약을
보강했다. Exact `08a6512c…` 동일 조건 진단은 event 17 `signed_write_complete`를 잡아냈다.
Write 시작 전 `signing` phase 전환 누락으로 같은 poll의 완료 event를 discovery 오류로 오분류한
target 상태기계 결함이므로 전용 phase를 추가했다. 아직 완주하지 않았으므로
`M29-SIGN/EATT/MULTI/REG-01`은 계속 `NOT RUN`이다. 실패와 진단 경계는
[147번 기록](<04_검증 기록/147_M29_W07_Signed_Write_EATT_HIL_준비.md>)에 보존한다.

Exact `80f8de79…` 재검증은 Signed Write·counter persistence 19/20을 통과한 뒤 마지막 discovery의
전역 `ENOENT`에서 멈췄다. DAP/UART와 CPU fault 0을 재확인했고, `discovering` phase의 전역
`ENOENT`보다 뒤따르는 link별 GATT 실패 stage/status를 판정하도록 진단 순서를 보강했다. 전체
20회·replay·EATT 완주 전에는 부분 성공을 PASS로 승격하지 않는다.

Exact `890c3892…` 상세 실행은 17회 뒤 18회차 `unexpected_disconnect`를 확인해 두 장기 실패가
성공 link를 끊지 않은 채 양쪽 warm reboot를 반복한 종료 순서의 intermittent teardown임을
분류했다. 각 결과 뒤 central 정상 disconnect와 양쪽 `disconnected` 확인을 `END`보다 앞에 두어
다음 reboot 전에 link 자원을 회수하도록 수정했고 target 2/2 warning 0을 확인했다.

W01 protocol은 `M28CAP/1`이며 128-bit nonce, Core/board/NCS/Zephyr full revision, Host Kconfig,
HCI version·64-byte supported commands·8-byte LE features와 controller 자원 상한을 고정 순서로
출력한다. Host parser는 noise·중복·누락·순서 변경·stale nonce·wrong revision·timeout과 raw HCI
불일치를 모두 거부한다. exact `78078a42…`의 target build와 실제 HCI는 각각 PASS했으며 서로 다른
증거로 유지한다. 상세 값과 hash는 [132번 기록](<04_검증 기록/132_M28_W01_실제_HCI_capability_완료.md>)에 있다.

W02는 `CONFIG_BT_MAX_CONN=2`와 SDC peripheral count 1을 production profile에 적용하고 central 0,
peripheral 1의 역할 고정 slot을 구현했다. `BLEConnectionHandle`은 slot을 직접 공개하지 않고
generation을 결합하며, `BLEEventInfo`가 link handle과 local 역할을 main-thread callback에 전달한다.
기존 singleton과 기존 callback은 유지하며 handle 없는 link 제어는 central을 우선하고 없으면
peripheral을 선택하는 결정적 호환 view다. 실제 production source를 링크한 Host 13개 시나리오,
W02 source 계약 5개와 고정 NCS target 1/1 build가 PASS했다. RF·동시 2-link는 W07
`M28-LINK-01`에서 PASS했다.

W03은 generation이 포함된 `BLEAdvertisingSetHandle`과 고정 1-set storage를 추가했다. 확장 광고는
길이 255 byte 이하의 raw AD TLV만 받고, 확장 스캔 결과는 최대 255 byte payload와 SID·TX power·
periodic interval·primary/secondary PHY를 값으로 복사한다. 실제 production source를 링크한 Host
수명 시나리오 4개와 정적 경계 검사, `nucode.m28.ble_extended_contract` target 1/1 build가 warning
없이 PASS했다. `ExtendedAdvertising`과 `ExtendedScanner` 예제를 추가했으며 255-byte RF report
100개는 W07 `M28-ADV-01`에서 PASS했다.

W04는 기존 extended set에 결합하는 periodic advertiser와 generation 기반 한 개 sync를 추가했다.
Periodic report는 최대 255 byte를 고정 8-entry queue로 복사하고, PAST sender/receiver는 반드시
현재 generation connection handle을 받는다. 구독되지 않은 link의 이전 callback은 PAST sync로
승격하지 않는다. Production Host 수명 시나리오 4개·정적 계약과 고정 NCS target 1/1이 PASS했고
`PeriodicAdvertiser`·`PeriodicScanner`·`PastSender`·`PastReceiver` 예제를 추가했다. 3-node periodic report 1,000개와
PAST 20/20은 W07 `M28-PER-01`에서 PASS했다.

W05는 고정 4 subevent × 4 response slot과 249-byte payload 상한을 적용했다. Advertiser request와
response, scanner response는 callback의 controller buffer를 보존하지 않고 각각 고정 storage·8-entry
queue로 복사한다. 허용 범위를 벗어난 subevent·slot·offset·길이는 controller 호출 전에 거부한다.
Production Host 시나리오 4개·정적 계약과 고정 NCS의 `nucode.m28.ble_pawr_contract` target 1/1이
warning 없이 PASS했고 `PawrAdvertiser`·`PawrScanner` 예제를 추가했다. 실제 4 subevent × 4 slot
RF 판정은 W07 `M28-PAWR-01`에서 PASS했다.

W06은 local RPA timeout을 1~3600초로 제한하고 extended set의 RPA 만료를 generation event로
전달한다. Link 설정에 사용한 remote 주소와 해석된 peer identity를 분리하며 identity callback은
현재 active slot에만 적용한다. 실제 parameter snapshot, DLE 요청·송수신 값과 remote LL version·
8-byte feature도 handle별로 조회한다. Production Host 시나리오 5개·정적 계약과 고정 NCS의
`nucode.m28.privacy_control` target 1/1이 warning 없이 PASS했고 `PrivacyPeripheral`·
`PerLinkControl` 예제를 추가했다. Privacy/bond는 `M28-PRIV-01`, 두 link 동시 제어는
`M28-CTRL-01`에서 PASS했다.

W07은 `M28B2`와 `M28B3` fixed protocol을 사용한다. 두 parser 29개는 누락·중복·재배치·
stale nonce·잘못된 revision·수치 미달·예상 밖 token·target FAIL을 거부한다. 두 role target 2/2와
세 role target 3/3은 warning 없이 build됐다. 2보드 `ADV/PAWR/PRIV`, 기존 M19~M21 `REG`, 3보드
`LINK/PER/CTRL/SOAK`을 모두 실행해 9개 test ID가 PASS했다. LINK 재검증 과정에서 callback-only
재연결 오판을 발견해 실제 GATT `LINK_UP` 확인과 object recycle 동기화를 추가했으며 실패 transcript와
수정·동일 조건 재검증을 [140번 기록](<04_검증 기록/140_M28_W07_3보드_HIL과_W08_완료.md>)에
보존했다. 사용자용 예제 11개는 runtime 실패를 명시적으로 보고한다.

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

M28 GAP/multi-link 값은 9개 test ID로 확정·실행했다. 아래 나머지 마일스톤 값은 아직
**미확정**이다. 임의 숫자를 제품 보증으로 채우지 않고, 선택 profile과 장비가 결정되면 P05에서
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
