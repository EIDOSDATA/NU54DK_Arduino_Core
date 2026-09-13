# 현재 지원 상태와 다른 PC 개발 준비

**현재 설치·지원 버전은 v0.4.1 하나이며 v0.4.0의 T01~T25와 M28 W01~W08은 모두
완료됐습니다.** M28은 capability 6/6, Host·target, 2·3보드 9개 test ID를 실제 PASS했고
M29 ATT/GATT·L2CAP는 W07 2보드 SIGN/EATT HIL 완료, 6/8·test ID 8/10입니다. 이 문서는 완료한 시험을 재개하라는
지시가 아니라, 다른 PC에서 후속 개발에 필요한 저장소·도구·증거를 찾는 안내입니다.

## 먼저 확인할 문서

1. [작업 지침](../AGENTS.md): 변경·검증·보존 원칙
2. [v0.4.1 TODO](TODO_v0.4.1.md): 현재 지원·설치기 유지보수·공개 결과
3. [v0.5.0 착수 계획](TODO_v0.5.0.md): M28 완료 상태와 M29 이후 계획
4. [v0.4.0 완료 TODO](TODO_v0.4.0.md): T01~T25 결과·해결 상태·기능 지원 경계

| 추가로 필요한 내용 | 찾아갈 곳 |
| --- | --- |
| QDEC20/21 최종 지원 계약 | [124번 지원 범위 재확정](<04_검증 기록/124_T22전_QDEC_지원_범위_재확정.md>) |
| T13 S/U 실제 시험과 종료 상태 | [113번 S 종료](<04_검증 기록/113_T13_S_범위_종료와_U_준비.md>) · [115번 U 종료](<04_검증 기록/115_T13_U_UART00_완료와_T13_종료.md>) |
| 특정 실패·수정·재검증의 원본 | [검증 기록 목차](<04_검증 기록/README.md>) |
| 설계·설치·API 탐색 | [문서 안내](README.md) |
| M28 결과 | [M28 착수 계약](<01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>), [140번 완료 기록](<04_검증 기록/140_M28_W07_3보드_HIL과_W08_완료.md>) |
| M29 현재 개발 | [M29 착수 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>), [`m29-ble-readiness.json`](../variants/nu54dk/m29-ble-readiness.json)과 최신 사용자 요청 |

과거 기록의 “다음 실행”, `running` 표시, PC 절대 경로는 당시 상태입니다.
현재 명령·보드 연결·실행 중 프로세스의 근거로 사용하지 않습니다.

## 저장소와 도구 준비

원격은 `https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git`, 기본 개발 브랜치는 `main`입니다.
정식 v0.4.1 tag source와 현재 main HEAD는 목적이 다르므로 각각 확인합니다.

1. 실제 저장소의 branch·HEAD·미커밋 변경·submodule을 확인하고 기존 변경을 보존합니다.
2. 새 복제는 `git clone --recurse-submodules`를 사용합니다. 기존 checkout에서는 작업 상태를 확인한 뒤
   fetch·fast-forward·submodule 초기화를 수행합니다. 강제 reset/clean은 하지 않습니다.
3. [Windows 개발환경](<02_빌드 설계/09_Windows_개발환경_설정.md>)에 따라 없는 도구만 준비합니다.
4. 버전은 [CI lock](../tools/ci/ncs-3.4.0.lock.json)과 [prerequisite pins](../tools/nu54-prerequisites/pins.json)를 따릅니다.
5. Host compiler·linker와 target PATH를 분리하고, 고정 NCS CMake/Ninja를 사용합니다.
   SDK 설치 상태 파일과 이전 PC 절대 경로 cache를 복사해 검증 완료로 간주하지 않습니다.
6. `python -B tools/ci/run_m12_gate.py <gate>`로 작업에 해당하는 contract·docs·inventory·package·examples·host
   검사를 수행합니다. 이전 PC의 PASS와 이번 실행 결과를 구분합니다.

일반 Arduino 사용자라면 위 개발 도구 대신 [Boards Manager 설치](<02_빌드 설계/06_Boards_Manager_설치와_패키징.md>)를 사용합니다.

## M28-W01~W08 완료와 M29 인계점

| 구분 | 상태 |
| --- | --- |
| Capability image | `tests/zephyr/m28_ble_capability`, Host 필수 Kconfig assert, 5개 직접 HCI query와 광고 set·periodic list Host API 왕복 |
| Protocol·parser | `M28CAP/1`, full revision·128-bit nonce·고정 15줄; noise·중복·누락·stale·wrong revision·timeout fail-closed |
| Host 검증 | 신규 parser 시험 12개, readiness 7개 PASS |
| Target 검증 | exact `78078a42…`, 고정 NCS v3.4.0에서 `nucode.m28.ble_capability` 1/1 build-only PASS |
| 실제 HCI | **6/6 PASS** — source `candidate`와 runtime HCI PASS를 분리 |
| W02 link 기반 | central/peripheral 고정 2-slot, generation opaque handle, 상세 event, central 우선 legacy view |
| W02 검증·예제 | production Host 13개 시나리오·source 계약 5개·target 1/1 PASS, `MixedRoleLinks` 추가 |
| W03 확장 GAP | generation advertising set 1개, raw AD 255 byte, SID·TX power·periodic interval·PHY scan metadata |
| W03 검증·예제 | production Host 수명 시나리오 4개·정적 경계·target 1/1 PASS, `ExtendedAdvertising`·`ExtendedScanner` 추가 |
| W04 periodic·PAST | 1 advertiser·1 generation sync, 255-byte/8-entry report queue, link별 PAST sender/receiver |
| W04 검증·예제 | production Host 수명 시나리오 4개·정적 경계·target 1/1 PASS, periodic·PAST 예제 4개 추가 |
| W05 PAwR | 4 subevent × 4 response slot, 249-byte payload, 8-entry response queue |
| W05 검증·예제 | production Host 수명 시나리오 4개·정적 경계·target 1/1 PASS, `PawrAdvertiser`·`PawrScanner` 추가 |
| W06 privacy·제어 | RPA timeout/event, connection 주소와 identity 분리, link별 parameter·DLE·remote-info |
| W06 검증·예제 | production Host 수명 시나리오 5개·정적 경계·target 1/1 PASS, `PrivacyPeripheral`·`PerLinkControl` 추가 |
| W07 Host·target | `M28B2`·`M28B3` fail-closed parser 29/29, role/test target 14/14 PASS |
| W07 2보드 실기 | `ADV/PAWR/PRIV` 3/3과 기존 M19~M21 `REG` 3/3 PASS |
| W07 3보드 실기 | `LINK/PER/CTRL/SOAK` 4/4 PASS; 2-link 재연결 20회·1,000 sequence와 1,800초 soak 포함 |
| LINK 최종 수정 | role callback 검증, object recycle event, GATT `LINK_UP` 확인과 최대 3회 유한 재시도 |
| 확인 장비 | NU54DK·독립 DAP/UART 3경로; receiver-validated sequence trace 사용 |
| W08 | 현행 문서·지원 경계·readiness 원장·M29 인계 완료 |
| 다음 행동 | W07-D/E에서 세 보드 `M29-MULTI-01`·`M29-REG-01` HIL 실행 |

## M29-W01~W06 완료와 W07 2보드 HIL 상태

M29는 [착수 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>)에서 W01~W08,
10개 test ID와 고정 자원 상한을 정의했다. 현재 진행률은 **6/8**이며 정적 SDK candidate를 실제
구현·target·HIL PASS로 자동 승격하지 않는다. 독립 실기 증거가 있는 test ID만 별도로 PASS한다.

exact `d604642b…`의 `M29CAP/1` parser 16/16, target 1/1 warning 0과 실제 `M29-CAP-01`
capability 7/7이 PASS했다. 실제 실행은 GATT service와 LE CoC server·동적 PSM 등록까지이며,
이후 W07 exact `c71ef4a2…`에서 Signed Write와 EATT peer negotiation도 실제 PASS했다.

Signed Write는 기본 OFF인 deprecated legacy opt-in, EATT는 기본 OFF인 experimental opt-in으로
개발한다. 기본 GATT/LE CoC와 두 선택 profile의 결과를 분리한다. NU54DK 3개와 DAP/UART 3경로는
확보됐지만 외부 sniffer와 Android/iOS/Windows/Linux cross-vendor peer 적용성은 아직 미확인이다.
해당 실기 경계 전까지 Host·target·NU54DK 2·3보드 구현과 검증을 계속한다.

W02 exact `dacf6341…`은 link마다 Zephyr async parameter와 512-byte read/write buffer를 고정
소유하고, 기존 무인자 API와 신규 generation handle overload를 함께 제공한다. 전체 Host gate,
W02 parser 11개, source 계약 6개와 target role 2/2가 PASS했다. 두 NU54DK의
peripheral/central 실제 HIL에서 ATT MTU 247, 512-byte long read 100/100, corrupt·stale 0과 main-thread
callback을 확인했다. `LongGattPeripheral`·`LongGattCentral`은 `v0.5.0` Arduino CI
group에서 BLE profile로 compile된다. 원본은
[142번 기록](<04_검증 기록/142_M29_W02_link별_GATT_long_read.md>)에 있다.

W03 exact `babba5a1…`은 link별 고정 prepare transaction과 512-byte 응답 write를 구현했다.
Prepare는 value를 변경하지 않고 execute 성공에서만 한 번 commit하며 cancel·offset·overflow·
characteristic 혼합·stale generation을 거부한다. Host production 15개 시나리오, source 계약
6개, parser 11개와 target role 2/2가 PASS했다. 두 NU54DK 실기에서 ATT MTU 247,
512-byte reliable write와 read-back 100/100, corrupt 0, partial commit 0을 확인해
`M29-LONG-01`을 PASS로 닫았다. `ReliableWritePeripheral`·`ReliableWriteCentral`은 `v0.5.0`
Arduino CI group에서 BLE profile로 compile된다. 첫 HIL에서 발견한 DAPLink UART 시작 noise와
명시적 READY 질의 수정·동일 조건 PASS 원본은
[143번 기록](<04_검증 기록/143_M29_W03_long_reliable_write.md>)에 있다.

W04 exact `068a1765…`는 characteristic당 descriptor 4개, 동기 authorization, link generation별
remote descriptor cache와 read multiple 4-handle, link 지정 notify/indicate를 구현했다. 비동기
notification payload는 전송 완료까지 고정 slot이 소유하고 기존 무인자 API·기존 event enum 값은
유지한다. Production Host 17개 시나리오, source 계약 8개, parser 11개, Arduino BLE 예제 6개와
target role 2/2가 PASS했다. 두 NU54DK 실기에서 ATT MTU 247, descriptor 4개, read multiple
4-handle 100/100, authorization 허용 401·예상 거부 1·오판 0, corrupt·stale 0을 확인해
`M29-DESC-01`을 닫았다. 첫 실행의 예상 ATT 거부 전역 error 오판과 수정 뒤 동일 조건 PASS 원본은
[144번 기록](<04_검증 기록/144_M29_W04_descriptor_authorization_read_multiple.md>)에 있다.

W05 exact `e587c4fe…`는 bonded resolved identity·database hash·target UUID·schema version·CRC를
결합한 4×84-byte 고정 cache와 Service Changed·hash 기반 재탐색을 구현했다. Production Host
18개 시나리오, source 9개, parser 14개, Arduino BLE 예제 8개와 target role 2/2가 PASS했다.
두 NU54DK 실기는 bonded reconnect 20/20, hash read 24, cache restore 20, Service Changed 1,
migration 1, corrupt cache 거부 1, stale handle 0을 확인해 `M29-CACHE-01`을 닫았다. 첫 실패는
CMSIS-DAP/GDB에서 Zephyr property bit 직접 cast가 write를 notify로 오인한 원인으로 확정했고,
명시 변환 뒤 동일 조건 PASS했다. 실패와 최종 원본은
[145번 기록](<04_검증 기록/145_M29_W05_robust_GATT_cache_migration.md>)에 있다.

W06 exact `767bb4af…`는 generation opaque handle을 사용하는 LE CoC server 1개·channel 2개,
512-byte SDU, channel당 RX record 4개와 전체 TX buffer 4개를 고정 자원으로 구현했다. Stack
callback은 payload를 복사하고 `BLEDevice.poll()`에서만 공개 callback을 호출하며 TX pool/credit
고갈은 `busy`로 분류한다. Production Host 7개 시나리오, source 7개, parser 12개, target role
2/2 warning 0과 `L2capCocServer`·`L2capCocClient` 예제 build가 PASS했다. 두 NU54DK에서 동시
2-channel·512-byte SDU를 방향별 channel당 1,000회 검증했고 malformed·offset·execute·PSM·credit
각 20회 거부, 예상 밖 수락·payload/cross-channel·stale·resource recovery 오류 0으로
`M29-COC-01`과 `M29-NEG-01`을 닫았다. 첫 runner protocol 불일치와 동일 조건 재검증 원본은
[146번 기록](<04_검증 기록/146_M29_W06_LE_CoC_credit_buffers.md>)에 있다.

W07은 기본 OFF의 `NUCODE_BLE_LegacySigning`·`NUCODE_BLE_EATT` 선택 library, 기존 ordinal을
보존한 Signed Write·bearer 지정 read/write 공개 API, 고정 두 EATT bearer를 구현했다. CSRK와
local/remote sign counter는 정상 완료에서 main thread가 저장하며 queue 포화 fallback도 counter를
저장하고 실패 시 link를 끊는다. Strict `M29W07|1` target·runner는 20회 재부팅 counter,
동일 signed ATT PDU replay 거부, 암호화 전 EATT 거부, 2 bearer별 1,000 operation을 판정한다.
Production Host 전체 24개 시나리오·W07 계약 17/17·parser 16/16와 target role 2/2는 PASS했다.
Windows Application Control 4551에만 최대 30초 유한 대기를 적용한 뒤 전체 Host 1,106개도
PASS(조건부 2개 skip)했다. Arduino M29 smoke는 `EattCentral`의 최소 C++ runtime 비호환
`<cstring>`을 `<string.h>`로 교체한 뒤 전체 14개 예제를 처음부터 다시 build해 14/14 PASS했다.
Exact `fb03df6e…` 첫 HIL은 flash·READY·CLEAR·reboot 뒤 41/31-byte legacy 광고를 `-EMSGSIZE`로
거부했다. DAP/UART와 CPU fault·RADIO 미시작을 확인하고 중복 128-bit service 광고·filter를 제거해
23/31-byte compile-time 상한으로 고쳤다. Exact `fbbb0d11…` clean target 2/2의 다음 HIL은 광고·
scan·pair·bond 재부팅 복원까지 성공한 뒤 첫 sign 재연결의 `discovery_result/code=0`에서 멈췄다.
DAP/UART와 CPU fault 0, 종료 SRAM을 확인한 뒤 GATT event 종류와 완료 뒤 handle 상태 실패를 서로
다른 stage/code로 남기도록 진단을 보강했다. Exact `08a6512c…` 재실기는 event 17
`signed_write_complete`를 식별했다. Write 시작 전 phase 전환 누락 때문에 같은 poll의 완료를
discovery 오류로 오분류한 target 상태기계 결함이므로 전용 `signing` phase를 추가했다. 새 exact
build로 같은 두 보드 SIGN/EATT와 세 보드 MULTI/REG를 실행한다. 실패 raw transcript와 준비 기록은
[147번 기록](<04_검증 기록/147_M29_W07_Signed_Write_EATT_HIL_준비.md>)에 있다.

Exact `80f8de79…`는 Signed Write와 counter 영속화 19/20을 연속 통과한 뒤 20회차 discovery의
전역 `ENOENT`에서 멈췄다. DAP/UART와 CPU fault 0을 확인했고, 중앙 target은 `discovering`에서만
전역 `ENOENT`를 소비한 뒤 generation link별 GATT `operation_failed/status`를 판정하도록 보강했다.
다른 phase·오류는 즉시 실패하며 20회 전체와 replay·EATT 완주 전에는 PASS로 승격하지 않는다.

Exact `890c3892…`는 17회 뒤 18회차의 실제 `unexpected_disconnect`를 잡았다. 두 장기 실패는
counter 값이 아니라 성공 link를 닫지 않고 양쪽 warm reboot를 반복한 종료 순서의 intermittent
teardown으로 분류했다. 각 결과 뒤 250ms 정착, central 정상 disconnect, 양쪽 disconnected 확인을
거쳐야 `END`를 내도록 수정했다. 재시도 추가가 아니라 다음 reboot 전 자원 회수 보장이다.

Exact `23fa4a6e…`는 Signed Write 20/20·counter 20·replay 수락 0을 통과했고 EATT도 암호화·2 bearer·
enhanced read까지 진입했다. 응답형 enhanced write에 필요한 characteristic `write` property가
target schema에서 빠져 시작이 거부된 것으로 확정해 property와 driver error 보고를 추가했다.
Bearer별 1,000 operation 전에는 EATT PASS로 표시하지 않는다.

Exact `6b659002…`의 다음 실행은 sign 8회차 뒤 central warm reboot READY 앞 raw `0xfe`를 strict
runner가 거부했다. BLE나 target fault가 아니라 reset 순간 DAPLink UART framing 경계로 분류하고
원본을 보존했다. Runner는 양쪽 exact `REBOOTING` 뒤 1초 UART 정착·입력 경계 재설정·고정
`READY?` 질의를 수행하며, 질의 뒤 READY와 전체 결과 parser는 계속 noise를 fail-closed로 거부한다.

Exact `28c04448…`에서는 UART framing 재발 없이 sign 15회까지 통과했으나 16회차 연결이
`unexpected_disconnect/code=0`으로 끝났다. 양쪽 DAP/UART와 `CFSR=0`, `HFSR=0`을 확인했다.
기존 GAP 상세 event에 없는 실제 HCI reason은 W07 target의 추가 Zephyr connection observer가
atomic으로 보존하고 다음 exact 실행의 failure code로 출력한다.

Exact `f497d382…`은 reason 62(`0x3e`, connection establishment sync timeout)를 첫 sign 재연결에서
직접 확인했다. Target은 Signed Write 전 `connecting`/`discovering`에서 이 reason만 session당 2회
이내로 허용하고 `connection_recycled` 뒤 광고/scan을 재개한다. `RETRY` reason·순번·상한은 strict
parser가 검사하며 다른 disconnect와 상한 초과는 계속 즉시 실패한다.

Exact `08cc52d6…` 전체 실행은 제한된 `0x3e`를 네 session에서 복구한 뒤 Signed Write
20/20·counter 20·replay 수락 0을 통과했다. EATT 후반은 central `1000/739`, peripheral
`1000/734`에서 reason `0x08`로 끊겼고 양쪽 CPU fault register는 0이었다. 4-buffer 공유 window는
격리 EATT에서 204.859초가 걸렸으며, Zephyr EATT pending-send 경계에 맞춘 bearer별 고정
1-buffer/1-in-flight 수정은 같은 두 보드에서 105.391초에 `2000/2000`을 통과했다. 이 격리 결과는
공식 PASS로 올리지 않고 clean exact 전체 runner를 다시 실행했다.

Exact `c71ef4a21465923760933f6b87ad7d92d9a95698`의 clean target 2/2, warning 0 이미지로 두 보드
전체 runner를 실행해 연결 재시도 0, Signed Write 20/20, counter rollback 0, 동일 PDU replay 수락
0을 확인했다. EATT는 암호화 전 거부와 상한 초과 거부, bearer 2개에서 각각 1,000 SDU,
production enhanced read/write, payload 오류·deadlock·starvation 0으로 끝났다. 따라서
`M29-SIGN-01`·`M29-EATT-01`은 PASS이며 원본은
`evidence/m29-w07-c71ef4a2-signed-eatt/`에 있다. W07 전체와 M29 진행률은 세 보드
`M29-MULTI-01`·`M29-REG-01`이 `NOT RUN`이므로 **6/8**이다. 다음 작업은 W07-D/E이며 이번에는
사용자 중단 지시에 따라 착수하지 않는다.

실행기와 보드 조건은 [W07 HIL 안내](../tests/hil/nu54dk/README.md#m29-w07-두-보드-signed-writeeatt-hil), 구현·검증
경계는 [131번 준비 기록](<04_검증 기록/131_M28_W01_Capability_image와_Host_target_준비.md>)과
[132번 실제 HCI 완료 기록](<04_검증 기록/132_M28_W01_실제_HCI_capability_완료.md>)과
[134번 W02 기록](<04_검증 기록/134_M28_W02_2-slot_generation_link_기반.md>)과
[135번 W03 기록](<04_검증 기록/135_M28_W03_확장_광고와_스캔.md>)을 따른다.
[136번 W04 기록](<04_검증 기록/136_M28_W04_periodic_sync_PAST.md>),
[137번 W05 기록](<04_검증 기록/137_M28_W05_PAwR_advertiser_scanner.md>)과
[138번 W06 기록](<04_검증 기록/138_M28_W06_privacy_RPA_link_control.md>)도 함께 따른다.
[139번 W07 2보드 준비 기록](<04_검증 기록/139_M28_W07_2보드_HIL_자동화_준비.md>)은 fixed
protocol·runner·target build와 당시 아직 실행하지 않은 실기 경계를 보존한다. 현재 실제 결과,
CMSIS-DAP 진단과 W08 완료는
[140번 기록](<04_검증 기록/140_M28_W07_3보드_HIL과_W08_완료.md>)을 따른다.

## 보존 자료와 재생성 자료

| 자료 | 취급 방법 |
| --- | --- |
| 코드·문서·정규화 로그·raw 압축·SHA manifest | Git과 검증 기록의 evidence에서 확인·보존 |
| 이력 정리 전 source·공급 종료 자산 | [106번 archive 안내](<04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)에서 확인 |
| ELF/HEX·compile DB·SDK/build cache | 필요할 때 exact source로 재생성. 이전 로컬 경로가 현재 존재한다고 가정하지 않음 |
| Probe UID·COM·진행 중 세션 | 현재 PC에서 새로 식별. 원시 UID·인증 정보는 공개 문서에 기록하지 않음 |
| 기존 공개 package·release asset | 불변 보존. 문서 정비를 이유로 재생성·덮어쓰기하지 않음 |

## 새 실물 시험을 요청받았을 때만

문서·Host 검토에는 보드를 연결할 필요가 없습니다. 완료한 S/U 시험과 C05 1시간 soak는 재예약하지 않습니다.
새 실기가 필요한 경우 아래 준비를 따릅니다.

- 현재 USB/probe·exact UID hash·role·image를 대조합니다. COM 번호와 USB 순서를 이전 PC에서 가져오지 않습니다.
  USB 열거·SWD 응답·firmware READY는 서로 별개입니다.
- 실제 결선은 [커넥터 핀맵](<01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)과
  [해당 fixture 계약](../tests/hil/nu54dk/README.md)을 확인합니다. S는 17신호, U는 UART00 4신호로 서로 다릅니다.
- 보드 간 시험은 공통 GND·동일 I/O 전압·전원 레일 미연결·출력 충돌 방지 조건을 지킵니다.
  DAP UART·SWD 스위치와 추가 pull-up 조건은 fixture별 안내를 따릅니다.
- 사용자 확인을 받은 유지 결선에 임의 시간 만료를 적용하지 않습니다. 새 결선·USB/전원 변화나 오류는 실제로
  대조하고, 오류가 나면 GPIO 연결성 확인 후 CMSIS-DAP 레지스터로 원인을 분석합니다.
- 일반 S/U는 SWD 10 MHz·exact UID·배타 lock·sector flash·`auto_unlock=false`·controlled start를 사용합니다.
  자동 mass erase/recover·임의 보드 전환은 하지 않습니다.
- Firmware watchdog·명령 lease를 유지하고 양쪽 STOP·clock 해제·핀 반환을 확인합니다.
  상세 정책은 [작업 지침](../AGENTS.md)을 따릅니다.

## 현재 지원 범위

v0.4.1은 `standard`·`ble`·`fabric` profile, library 9개·예제 30개를 제공합니다.
QDEC20/21은 기본 정·역회전과 SAMPLE/REPORT event 경로를 공개 지원하며,
반복 manual `read()/clear`의 무손실 누산은 보증하지 않습니다.
반복 Serial personality handover·모든 주변장치 동시 조합·정밀 ADC/jitter/음질/신호 무결성도
보증 범위 밖입니다. 과거 FAIL·미실행을 공개 지원 결정만으로 PASS로 바꾸지 않습니다.
