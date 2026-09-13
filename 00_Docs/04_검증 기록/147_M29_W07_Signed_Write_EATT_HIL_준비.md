# M29-W07 Signed Write·EATT HIL 준비

| 항목 | 현재 결과 |
| --- | --- |
| 작업일 | 2026-09-14 |
| 준비 기준 HEAD | `d425248b8063cfb4e816c12cab6dd62c88cae446` 이후 미커밋 W07 source |
| NCS / Zephyr | `99553055607b…` / `bf801e4e3d19…` |
| board / toolchain | `fe65f2f0880b…` / `dcbdc366a1` |
| W07 공개 계약 | **13/13 PASS** |
| strict Host parser | **14/14 PASS** |
| production GATT Host | **W07 3개 포함 전체 24개 시나리오 PASS** |
| Arduino M29 예제 | **14/14 PASS** |
| target build | **`fb03df6e…` 2/2와 광고 수정 source 2/2 PASS, warning 0** |
| 실제 `M29-SIGN-01` / `M29-EATT-01` | **NOT RUN / NOT RUN** |
| 실제 `M29-MULTI-01` / `M29-REG-01` | **NOT RUN / NOT RUN** |
| M29 진행률 | **6/8 유지** |

## 1. 구현한 정책과 공개 API

Signed Write는 Zephyr `BT_SIGNING`의 deprecated 상태를 숨기지 않고 기본 OFF의
`NUCODE_BLE_LegacySigning` 선택 library로 분리했다. Public characteristic property와
`BLEClient.writeSigned()`를 추가하되 기존 property·event enum ordinal과 무인자 API는 바꾸지
않았다. Bonded key record의 local/remote CSRK와 sign counter를 stack 전송·수신 완료 뒤
`bt_keys_store()`로 저장한다. 수신 측은 서명이 사용되는 L1 link에서만 이 처리를 적용해 암호화
EATT의 일반 Write Command를 sign counter 저장으로 오인하지 않는다. 정상 완료는 main thread
event 처리에서 저장하며, event queue가
포화돼 완료 record를 보존하지 못할 때도 counter를 즉시 저장한다. 이 fallback 저장마저 실패하면
link를 끊어 이후 signed operation을 계속하지 않는다.

EATT는 Zephyr experimental 상태를 표시하는 기본 OFF의 `NUCODE_BLE_EATT` 선택 library다.
암호화되지 않은 link에서는 bearer 연결을 거부하고 connection당 최대 2개만 연다. GATT read/write
overload는 `unenhanced` 또는 `enhanced` bearer를 명시하고, 상세 client event가 실제 선택 bearer를
돌려준다. 기존 GATT client의 link별 단일 pending operation 상한은 유지한다.

공개 예제는 다음 네 개다.

- `LegacySignedWritePeripheral`, `LegacySignedWriteCentral`
- `EattPeripheral`, `EattCentral`

각 예제는 deprecated/experimental 경고, security·discovery·write/read·bearer 연결 실패를 Serial로
출력한다. Callback 완료만 peer 적용 성공으로 표현하지 않는다.

## 2. 고정 HIL protocol과 parser

`tests/zephyr/m29_ble_signed_eatt_hil`의 두 role image는 `M29W07|1`만 출력한다. READY·BEGIN·결과·
END에 full Core revision, 128-bit nonce와 iteration을 붙인다. Signed 단계는 bond/CSRK 생성 뒤 20회
재부팅과 write를 반복하며 local/remote counter가 정확히 증가하는지 보고한다. Replay 단계는 실제
서명한 ATT PDU의 동일 byte를 두 번 RF로 보내 receiver 적용 횟수가 한 번인지 검사한다.

EATT 단계는 암호화 전 연결 거부, 암호화 뒤 bearer 2개, 상한 초과 거부를 확인한다. Production
enhanced read/write 뒤 두 실제 EATT L2CAP channel에서 bearer별 1,000 ATT Write Command를 보내고
peripheral이 sequence·checksum·bearer 분리를 검증한다. TX buffer는 4개 고정 pool이며 무한 재시도는
없다.

`tests/hil/nu54dk/m29_ble_signed_eatt.py`는 source clean·revision·build record·보드 UID/UART를 flash
전에 확인한다. Parser 14개는 정상 두 role 외에 ASCII/non-ASCII noise, 누락·중복·재배치,
wrong revision·stale nonce, counter rollback, replay accept, EATT shortfall, target FAIL과 END 뒤
추가 record를 fail-closed로 거부한다.

## 3. Host·target 준비 결과

W07 공개 계약 13/13, parser 14/14, M13 allowlist·canonical example 11/11(설치본 전용 1 skip),
M22 stable package 경계 7/7, readiness 8/8이 PASS했다. 전체 Host gate에서 W07 신규 예제를 후속
후보 집합에 반영하지 않은 1건은 수정 뒤 동일 시험 7/7 PASS했다. 임시 native EXE 일부는 첫 실행에
Windows Application Control `WinError 4551`로 17회 차단됐다. PAwR·TWIM 실패 module을 같은 source와
컴파일러로 개별 재실행해 모두 PASS했고 기능 회귀가 아닌 정책 판정 race로 분류했다. 공통 실행기는
4551에만 최대 30초 유한 재시도를 적용하고 다른 오류와 한도 소진은 그대로 실패하게 보강했다.
격리 TEMP에서 다시 실행한 전체 Host gate는 **1,106개 PASS, 조건부 2개 skip**으로 끝났다. W07 GATT
binary도 W07 3개를 포함한 전체 24개 production 시나리오가 PASS했다. 첫 실패는 소급 PASS로
바꾸지 않으며 exact commit CI에서 독립 확인한다.

Arduino M29 smoke의 첫 실행은 앞선 13개 예제가 PASS한 뒤 `EattCentral`에서 이 플랫폼의 최소
C++ runtime이 제공하지 않는 `<cstring>`을 사용해 compile 실패했다. 같은 C API를 명시하는
`<string.h>`로 교체하고 `EattCentral` 단독 build를 통과시킨 뒤 전체 그룹을 처음부터 다시 실행해
GATT·CoC 8개, GATT cache 2개, legacy signing 2개와 EATT 2개를 합친 **14/14 PASS**를 확인했다.
첫 실패 로그를 최종 PASS로 소급 변경하지 않는다.

고정 NCS v3.4.0에서 다음 두 build-only suite는 warning 없이 2/2 PASS했다.

- `nucode.m29.ble_signed_eatt_peripheral`
- `nucode.m29.ble_signed_eatt_central`

이 build는 dirty W07 source로 수행했으므로 정확한 물리 실행 identity가 아니다. 먼저 source·문서·
시험을 commit/push하고 exact commit CI를 확인한 뒤, 같은 commit을 새로 build해 HIL runner에
전달한다.

## 4. 첫 exact HIL 실패와 원인 분류

Exact `fb03df6e1220f77ca52b311ffb78de987a48aae0`의 Software Gates 7/7과 Reproducible
Builds 10/10을 확인하고 clean target 2/2를 만들었다. Peripheral
`54153603000528402aae46c5e8e3712a`/COM10과 central
`5415360300052840fcd47678fd7d106d`/COM13은 pyOCD sector flash, READY, CLEAR와 양쪽 warm reboot를
통과했다. 첫 `pair` session의 peripheral은 다음 record로 즉시 멈췄다.

```text
M29W07|1|FAIL|role=peripheral|mode=pair|stage=advertising_start|code=-122|iteration=0|...
```

Raw 기록은 `evidence/m29-w07-fb03df6e-signed-eatt/result.peripheral.transcript.log`와
`result.central.transcript.log`에 보존한다. Zephyr minimal libc의 `122`는 `EMSGSIZE`다. Legacy
광고 payload에 flags 3 byte, 128-bit service UUID field 18 byte와 company ID·128-bit nonce
manufacturer field 20 byte를 함께 넣어 **41/31 byte**가 됐다. Central callback은 이미 company ID와
exact nonce를 직접 검사하므로 service UUID 광고와 scan filter는 중복이었다.

결선·debug 경계를 먼저 확인했다. 두 CMSIS-DAP UID와 UART는 독립적으로 열렸고 flash·양방향 command·
reboot transcript가 정상이다. 실패 직후 peripheral을 CMSIS-DAP로 halt해 읽은 `CFSR=0`, `HFSR=0`은
CPU fault가 없음을 보였다. RADIO READY/END event와 STATE는 0으로 controller RF 동작 전에 API가
거부된 것과 일치했고 UARTE20/DMA register는 Serial 송신이 진행된 상태였다. GPIO register에도 fault
징후가 없었다. 캡처 뒤 core는 다시 실행시켰다.

수정은 중복 service UUID 광고·filter를 제거하고 exact manufacturer nonce 검사를 유지한다. Flags와
manufacturer field 합계 **23/31 byte**를 compile-time `static_assert`로 고정하고, clear·connectable·
nonce·name·start 실패 stage를 각각 분리했다. Source 계약을 추가한 뒤 W07 계약/parser/readiness
30/30과 수정 target 2/2 warning 0이 PASS했다. 이 dirty build는 실제 PASS로 승격하지 않고 새 exact
commit의 CI·clean build 뒤 동일 보드와 조건으로 다시 실행한다.

## 5. 두 번째 exact HIL 실패와 진단 강화

수정 commit `fbbb0d11e8ede7a141e6d1146ace88e6550935df`의 Software Gates 7/7과 새 clean
target 2/2 warning 0을 확인했다. 같은 두 보드를 UID로 다시 찾은 뒤 실행한 결과 광고·scan, 최초
pairing, 양쪽 bond 1개와 warm reboot 뒤 bond 복원까지 통과했다. 첫 Signed Write iteration의
재연결과 scan도 성공했지만 central discovery callback에서 다음과 같이 중단됐다.

```text
M29W07|1|FAIL|role=central|mode=sign|stage=discovery_result|code=0|iteration=1|...
```

Raw 기록은 `evidence/m29-w07-fbbb0d11-signed-eatt/result.peripheral.transcript.log`와
`result.central.transcript.log`에 보존한다. 두 DAP/UART가 계속 독립적으로 탐색되고 실제 광고·scan·
pairing을 완료했으므로 첫 실패의 payload·GPIO·RF 시작 문제는 재발하지 않았다. 실패 뒤 central을
CMSIS-DAP로 halt해 확인한 `CFSR=0`, `HFSR=0`과 정상 thread PC는 CPU fault가 없음을 보였다.
Application SRAM은 `mode=sign`, `phase=complete`, `session_finished=1`이었고 두 GATT client state가
해제돼 있었다. Peripheral도 같은 종료 상태와 유효했던 generation handle을 보존한 뒤 GATT link
state가 해제돼, discovery 도중 link teardown event가 먼저 전달됐을 가능성을 포함해 event 종류를
추가로 식별해야 한다. 캡처 뒤 두 core는 다시 실행시켰다.

기존 `discovery_result/code=0`은 `discovery_complete` 뒤 handle 상태 실패와 다른 GATT event 수신을
구분하지 못한다. Target을 `discovery_event/code=<BLEGattClientEvent ordinal>`과
`discovery_state/code=0`으로 분리하고 Host source 계약으로 고정했다. Exact `08a6512c…`의 같은
조건 재실기는 `discovery_event/code=17`을 출력했고, enum 17은 `signed_write_complete`다. Raw
기록은 `evidence/m29-w07-08a6512c-discovery-diagnostic/`에 보존한다.

따라서 discovery와 link teardown은 원인이 아니었다. Discovery 완료 callback에서
`BLEClient.writeSigned()`를 시작하기 전에 phase를 바꾸지 않아, 같은 `BLEDevice.poll()`에서 즉시
돌아온 완료 event를 아직 `discovering` phase가 잘못 거부한 target 상태기계 결함이다. 전용
`Phase::signing`을 추가하고 write 시작 전에 전환하며, 완료 event도 그 phase에서만 수락하도록
단일 수정했다. 이 실패를 SIGN/EATT PASS로 승격하지 않고 새 exact build로 동일 조건을 재검증한다.

Exact `80f8de79…`의 단일 수정 재검증은 pairing 뒤 Signed Write와 counter 영속화를 1~19회 연속
통과했다. 매회 central local counter와 peripheral remote counter가 같은 값으로 증가했고 양쪽 bond
1개와 callback main-thread 판정도 유지됐다. 20회차는 scan까지 통과한 뒤 central의 전역
`gap_error/code=-2`(`ENOENT`)에서 멈췄다. Raw 기록은
`evidence/m29-w07-80f8de79-signed-eatt/`에 보존한다. UID 기반 DAP/UART 재탐색은 정상이고
CMSIS-DAP의 `CFSR=0`, `HFSR=0`, 정상 thread PC로 CPU fault가 없음을 다시 확인했다.

GATT discovery의 `failClient(-ENOENT)`는 전역 BLE error와 link별 `operation_failed`를 함께
queue하며 전역 event가 먼저 전달될 수 있다. 현재 target은 전역 event에서 즉시 종료해 service
discovery miss인지 다른 link 오류인지 구분할 수 없다. Central의 `discovering` phase에서만 전역
`ENOENT`를 소비하고 뒤따르는 generation link별 GATT `operation_failed/status`로 판정하도록
진단 순서를 고정했다. 다른 phase와 다른 전역 오류는 계속 즉시 실패한다. 새 exact 실행에서
상세 실패가 재현되면 그 단계로 원인을 좁히고, 재현되지 않더라도 20회 전체와 replay·EATT가 끝나기
전에는 PASS로 승격하지 않는다.

Exact `890c3892…`의 상세 순서 실행은 1~17회를 통과한 뒤 18회차에서 link별
`unexpected_disconnect`를 직접 확인했다. 즉 앞선 20회차 `ENOENT`는 counter 값이나 Signed Write
payload 결함이 아니라, 성공한 연결을 정상 종료하지 않고 곧바로 양쪽 warm reboot를 반복해 이전
ACL 해제를 controller timeout에 맡긴 시험 종료 순서와 같은 intermittent link teardown 계열이다.
Raw 기록은 `evidence/m29-w07-890c3892-signed-eatt/`에 보존한다.

각 pair/sign/replay/EATT 결과 뒤 250ms 정착 시간을 두고 central만 generation handle로 정상
disconnect를 시작하며, 양쪽 target이 실제 `disconnected` event를 받은 뒤에만 `END`를 출력하도록
고쳤다. Peripheral은 임의로 동시 disconnect하지 않고 central의 종료를 기다린다. 결과를 출력한
phase에는 pair/EATT 완료 record가 반복되지 않도록 guard를 둔다. 이 변경은 재시도 횟수를 늘리는
것이 아니라 각 iteration의 Host/controller 자원을 다음 reboot 전에 유한하게 회수하는 수정이다.
Source 계약 12/12와 수정 target 2/2 warning 0을 확인했으며 새 exact commit으로 같은 전체 분모를
다시 실행한다.

Exact `23fa4a6e…` 재실기는 정상 disconnect 뒤 `END` 순서로 Signed Write **20/20**, central local
counter 20과 peripheral remote counter 20, replay 원본 1·재전송 1 중 replay 수락 0을 통과했다.
EATT도 암호화·bearer 2개·상한 초과 거부와 enhanced read까지 통과했으나 응답형 enhanced write
시작에서 `eatt_write_start/code=0`으로 멈췄다. Raw 기록은
`evidence/m29-w07-23fa4a6e-signed-eatt/`에 보존한다. CMSIS-DAP의 `CFSR=0`, `HFSR=0`과 정상
thread PC로 CPU fault가 없음을 재확인했다.

Target characteristic은 `read`, `write_without_response`, `authenticated_signed_write`만 선언했지만
EATT production 경로는 응답형 `BLEClient.write(..., enhanced)`를 호출했다. 공개 API가 property
계약에 따라 시작을 거부한 것이므로 controller/EATT bearer 결함이 아니다. `BLEProperty::write`를
명시적으로 추가하고 실패 record에도 `BLEDevice.lastDriverError()`를 남기도록 수정했다. Host source
계약 13/13 뒤 새 exact 전체 실행으로 bearer별 1,000 operation까지 확인한다.

Exact `6b659002…` 재실기는 수정한 EATT 경로에 도달하기 전 Signed Write 8회차 뒤 warm reboot의
central 자동 READY 첫 byte에 raw `0xfe`가 붙어 strict runner가 즉시 거부했다. 그 뒤 target은
SIGN 12회차까지 정상 출력했으므로 BLE link·CSRK counter·CPU fault가 아니라 reset 순간 DAPLink
UART framing 경계 문제로 분류한다. 실패 원본은
`evidence/m29-w07-6b659002-signed-eatt/`에 보존하며 성공 증거로 승격하지 않는다.

이는 143번 W03의 flash/reset 직후 raw `0x1c`와 같은 계열이지만 W07은 한 실행에서 warm reboot를
23회 수행하므로 reboot마다 재동기화가 필요하다. Runner는 양쪽 exact `REBOOTING`을 먼저 검증하고
1초 정착 뒤 reset 구간의 자동 READY와 framing byte를 protocol 증거 경계 밖에서 비운다. 그 다음
고정 `M29W07|1|READY?`를 각 target에 한 번 보내 exact READY 한 줄만 받는다. READY 질의 이후
noise·누락·중복·wrong revision 거부와 최종 transcript parser는 완화하지 않았다. Host source 계약
14/14·parser 14/14·readiness 8/8이 PASS했으며 새 exact commit으로 처음부터 재검증한다.

Exact `28c04448…` 재검증은 reboot마다 질의한 READY만 수집해 raw framing byte 문제가 재발하지
않았음을 확인했다. Signed Write 1~15회는 counter와 정상 disconnect를 통과했으나 16회차 연결이
`unexpected_disconnect/code=0`으로 끝났다. Raw 기록은
`evidence/m29-w07-28c04448-signed-eatt/`에 보존한다. 두 보드는 DAP/UART로 계속 식별됐고
CMSIS-DAP에서 양쪽 `CFSR=0`, `HFSR=0`과 정상 thread PC를 확인했으므로 CPU fault가 아니다.

기존 Core 상세 GAP event는 disconnect HCI reason을 노출하지 않아 target의 code가 기본값 0이었다.
W07 target에 추가 Zephyr connection observer를 등록해 callback의 실제 `reason`을 atomic으로
보존하고, main-thread의 `unexpected_disconnect/code=<reason>`에 연결한다. 다음 exact 실행은
재시도 목적이 아니라 timeout `0x08`, remote user termination `0x13` 등 원인 class를 직접
구분하기 위한 진단이다. Source 계약 15/15와 진단 target 2/2 warning 0을 확인했다.

## 6. 남은 유한 실행 순서

1. W07 준비 변경을 commit/push하고 exact GitHub Software·Reproducible Build CI를 확인한다.
2. Clean exact commit으로 Signed/EATT 두 role을 재빌드한다.
3. 두 보드 `M29-SIGN-01`과 `M29-EATT-01`을 한 runner session에서 실행한다.
4. 세 보드 mixed DUT의 두 link에서 GATT/CoC traffic 각 1,000회와 교차 event 0을 검증한다.
5. M19·M20·M21·M28 필수 BLE 회귀 네 그룹을 세 보드 장비 집합에서 실행한다.
6. 실패하면 DAP/UART·전압·RF/GPIO 연결성을 먼저 확인하고, 연결이 정상이면 CMSIS-DAP로
   주변장치·DMA·GPIO·오류 register와 SRAM 상태를 수집한다. 원인을 분류해 한 번 수정한 뒤 같은
   조건으로 재검증하며 무한 재시도하지 않는다.

현재 단계에서는 네 물리 test ID와 W07을 PASS로 표시하지 않는다. SDK source `candidate` 역시
구현·target·HIL PASS와 분리한다.
