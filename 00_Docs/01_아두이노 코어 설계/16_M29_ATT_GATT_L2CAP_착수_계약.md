# M29 ATT/GATT·L2CAP 착수 계약

| 항목 | 고정값 |
| --- | --- |
| 대상 릴리즈 | `v0.5.0` |
| 마지막 실제 HIL Core | `a964ae205e237d90149f6d2c0eb0ec6492492a33` |
| 기준 NCS | `v3.4.0` / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| 기준 Zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| 기준 board | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 기준 toolchain | Windows bundle `dcbdc366a1` |
| stable 지원 릴리즈 | `v0.4.1`; 공개 RC는 [v0.5.0 TODO](../TODO_v0.5.0.md) 참조 |
| M29 상태 | **W01~W08 8/8·test ID 10/10 완료** |
| 기계 원장 | [`m29-ble-readiness.json`](../../variants/nu54dk/m29-ble-readiness.json) |

W07-C의 두 보드 SIGN/EATT, W07-D/E의 세 보드 `M29-MULTI-01`·`M29-REG-01`, Windows/Intel
GATT 상호운용과 W08 예제·문서·회귀를 완료했다. 이 문서의 공개 API 목표는 v0.5.0 개발 계약이며,
설치·지원 v0.4.1의 기능 확대를 뜻하지 않는다. W07-C까지는
[147번 기록](<../04_검증 기록/147_M29_W07_Signed_Write_EATT_HIL_준비.md>), 최종 결과는
[149번 기록](<../04_검증 기록/149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>)을 따른다.

## 1. 목표와 완료 의미

M29는 M28의 generation 기반 2-link 수명 위에 ATT/GATT long·reliable operation,
descriptor·authorization·read multiple, Service Changed·database hash·robust caching과 LE Credit
Based Channel을 고정 자원으로 구현한다. 기존 `BLEDevice`, `BLEConnection`, `BLEService`,
`BLECharacteristic`, `BLEClient`와 인자 없는 GATT client 호출은 유지한다.

M29 완료는 아래 열 개 test ID의 Host·target·실기 증거가 모두 PASS하고 W01~W08이 완료됐다는
뜻이다. 이것만으로 v0.5.0 공개, Bluetooth qualification, 모든 OS·어댑터 조합 지원 또는 EATT의
안정 API 승격을 주장하지 않는다.

## 2. 고정 SDK capability와 제품 정책

고정 NCS source의 API·Kconfig 존재는 구현 후보일 뿐 실제 NU54DK 지원 PASS가 아니다. W01 target
capability image와 이후 peer negotiation·RF HIL을 분리한다.

| 기능 | 고정 source 상태 | M29 제품 정책 |
| --- | --- | --- |
| Long read/write | `bt_gatt_read` 연속 offset과 `bt_gatt_write` long procedure 제공 | 기본 공개 안정 API로 구현 |
| Prepare/execute·reliable write | server prepare flag와 client long write 경로 제공 | link별 고정 transaction으로 기본 공개 |
| Read Multiple | `BT_GATT_READ_MULTIPLE` 기본 활성화 | 최대 4 handle의 bounded API로 공개 |
| Service Changed·GATT caching | `BT_GATT_SERVICE_CHANGED`, `BT_GATT_CACHING` 제공 | database revision·hash·cache invalidation을 명시해 공개 |
| LE CoC | `BT_L2CAP_DYNAMIC_CHANNEL` 제공 | 기본 공개, LE Credit Based Channel 2개로 제한 |
| Signed Write | `BT_SIGNING`이 `DEPRECATED` 선택 | 기본 OFF인 `legacy opt-in`; CSRK·counter 영속성과 replay 거부 없이는 지원 판정 금지 |
| EATT | `BT_EATT`와 기반 ECRED가 `EXPERIMENTAL` | 기본 OFF인 `experimental opt-in`; 안정 GATT와 지원 등급·증거 분리 |

Signed Write와 EATT를 조용히 제외하지 않는다. 두 기능은 명시적 build profile에서 구현·시험하되
기본 BLE profile에 deprecated/experimental 의존성을 강제로 넣지 않는다. EATT operation은
unenhanced·enhanced bearer 선택 실패를 구분하며 암호화와 peer 지원을 먼저 확인한다.

## 3. 공개 API와 호환 계약

### 3.1 Link별 GATT client

- 기존 `BLEClient.discover()/read()/write()/writeWithoutResponse()/subscribe*()`는 local central
  link를 우선하는 기존 view를 유지한다.
- 신규 overload는 `BLEConnectionHandle`을 첫 인자로 받는다. 내부에는 M28의 두 connection slot과
  같은 generation을 가진 client context 두 개만 둔다.
- callback 상세 정보에는 connection handle, operation 종류, offset, 실제 길이, ATT 오류와 bearer
  종류를 복사한다. stale generation callback은 사용자에게 전달하지 않는다.
- link마다 비동기 operation 하나만 허용한다. 서로 다른 두 link의 operation은 동시에 진행할 수
  있고 같은 link의 두 번째 요청은 `busy`로 즉시 거부한다.

### 3.2 Long·reliable server와 descriptor

- characteristic value 최대 길이는 512 byte다. caller-owned buffer도 같은 상한을 적용한다.
- prepare transaction은 link당 하나, 최대 512 byte이며 offset coverage를 기록한다. 누락 구간,
  overflow, execute without prepare, cancel 뒤 execute와 다른 characteristic 혼합을 거부한다.
- commit은 전체 payload 검증 뒤 한 번에 수행한다. 실패한 transaction이 cached value를 부분 변경하면
  안 된다.
- characteristic당 descriptor는 최대 4개다. CCC는 내부 descriptor로 별도 계산한다.
- read/write authorization callback은 Bluetooth callback 문맥에서 bounded·non-blocking으로 실행하고
  결과만 main-thread event에 복사한다. callback에서 Arduino blocking API를 호출하지 않는다.
- notification·indication에는 link handle overload를 추가하고 기존 무인자 호출은 실제 subscribe한
  peripheral 우선 view를 유지한다.

### 3.3 Cache와 database migration

- server schema는 Bluetooth 시작 전에만 등록하는 기존 규칙을 유지한다.
- application이 명시하는 32-bit database revision과 실제 database hash를 함께 기록한다.
- bonded peer에는 Service Changed 범위를 보내고 client는 Service Changed 또는 database hash 변경 시
  해당 link cache를 폐기한 뒤 discovery를 다시 수행한다.
- cache record는 peer identity, database hash, handle 범위와 schema version을 포함한다. RPA 자체를
  영속 key로 사용하지 않는다.
- 잘못된 hash, 잘린 record, 미래 schema version과 다른 identity의 record는 fail-closed로 폐기한다.

### 3.4 LE CoC

- 공개 `BLEL2capChannelHandle`은 slot+generation opaque token이다. raw `bt_l2cap_chan *`를 노출하지
  않는다.
- 전체 channel은 2개, server는 1개, channel당 SDU 최대 512 byte, RX record 4개, 전체 TX buffer
  4개로 고정한다.
- accept/connect/send/disconnect와 RX/TX 완료를 `BLEDevice.poll()` main thread event로 전달한다.
- stack에 buffer ownership을 넘긴 뒤에는 callback 또는 disconnect 회수 전 재사용하지 않는다.
- credit 고갈은 정상 backpressure로 분류하고 queue 상한을 넘는 요청은 즉시 `busy`로 거부한다.
  이유 없는 재시도나 무한 대기는 허용하지 않는다.

## 4. 자원 상한

| 자원 | 상한 |
| --- | ---: |
| 동시 BLE link | 2: local central 1 + peripheral 1 |
| GATT client context | link당 1, 전체 2 |
| link당 pending GATT operation | 1 |
| characteristic value·long operation | 512 byte |
| prepare transaction | link당 1 |
| characteristic당 descriptor | 4 |
| read multiple handle | 4 |
| LE CoC server | 1 |
| 전체 LE CoC channel | 2 |
| CoC SDU | 512 byte |
| channel당 RX record | 4 |
| 전체 CoC TX buffer | 4 |
| EATT bearer | 연결당 최대 2, experimental profile만 |

heap 증가는 위 고정 storage를 대체하지 않는다. stack 내부 buffer가 부족하면 공개 오류와 진단
counter로 남기고 임의 heap fallback을 추가하지 않는다.

## 5. 작업 묶음

| 작업 | 내용 | 완료 gate |
| --- | --- | --- |
| M29-W01 | 고정 source capability·정책·자원·test protocol | readiness Host 시험, capability target build·실행 |
| M29-W02 | generation link별 GATT client와 long read | stale callback·2-link 병렬·512-byte read Host/target |
| M29-W03 | long/reliable write와 server prepare/execute | atomic commit·cancel·offset/overflow negative |
| M29-W04 | descriptor·authorization·read multiple·link별 notify/indicate | 권한·4-handle·두 link event 분리 |
| M29-W05 | Service Changed·database hash·robust cache migration | bond/reconnect·firmware migration·corrupt cache negative |
| M29-W06 | LE CoC 고정 channel·credit·buffer 수명 | 2-channel·512-byte SDU·starvation·회수 |
| M29-W07 | Signed Write legacy·EATT experimental·통합 HIL | replay·counter persistence·2 EATT bearer·3보드·cross-vendor |
| M29-W08 | 회귀·예제·지원표·문서·코드 재검토·CI | M29 10/10, 전체 gate·push commit CI PASS |

## 6. 고정 test ID

모든 protocol은 full revision과 128-bit nonce, role/image hash, 고정 BEGIN/RESULT/END record를
사용한다. parser는 noise·누락·중복·재배치·wrong revision·stale nonce·예상 밖 token·timeout과
target FAIL을 거부한다.

| Test ID | 보드 | 핵심 합격 조건 | timeout |
| --- | ---: | --- | ---: |
| `M29-CAP-01` | 1 | 고정 Kconfig/API 7군과 runtime Host 초기화·revision 일치 | 120초 |
| `M29-LONG-01` | 2 | MTU 247, 512-byte read/write 각 100회, loss·corrupt·partial commit 0 | 300초 |
| `M29-DESC-01` | 2 | descriptor 4개와 read-multiple 4 handle 각 100회, authorization 오판 0 | 300초 |
| `M29-CACHE-01` | 2 | database migration·bonded reconnect 20회, stale handle 사용 0 | 600초 |
| `M29-COC-01` | 2 | channel 2개, channel당 512-byte SDU 1,000개 양방향, loss·corrupt 0 | 600초 |
| `M29-NEG-01` | 2 | malformed/offset/execute/PSM/credit 오류군 각 20회 정확히 거부, 회수 실패 0 | 600초 |
| `M29-SIGN-01` | 2 | legacy profile CSRK·counter 재부팅 20회 유지, replay 수락 0 | 900초 |
| `M29-EATT-01` | 2 | 암호화 link, EATT bearer 2개, bearer별 operation 1,000회, 교착 0 | 900초 |
| `M29-MULTI-01` | 3 | mixed DUT의 두 link에서 GATT/CoC 동시 traffic 각 1,000회, 교차 event 0 | 900초 |
| `M29-REG-01` | 3 | M19~M21·M28 필수 BLE 회귀와 기존 Sketch API 동작 유지 | 1800초 |

수치 미달은 PASS가 아니다. 시험 실패 시 DAP/UART identity와 전원·필요한 GPIO 연결성을 먼저
확인하고, 연결이 정상이면 CMSIS-DAP으로 fault, SRAM state, queue·buffer·credit·ATT/L2CAP 오류
counter를 확보한다. 원인 분류, 단일 수정, 동일 조건 재검증 순서를 지키고 무한 재시도하지 않는다.

## 7. 장비와 완료 결과

NU54DK 3개와 독립 DAP/UART 3경로로 2보드 LONG/DESC/CACHE/COC/NEG/SIGN/EATT와 3보드
MULTI/REG를 실행했다. Windows 11의 Intel Bluetooth/WinRT peer로 기본 M20 GATT 상호운용도
확인했다. 외부 sniffer와 Android/iOS/Linux peer, Windows EATT·robust caching은 확인하지 않았으며
이 미확인 범위를 M29 PASS에 포함하지 않는다.

W01은 exact `d604642b…`에서 parser 16/16, target 1/1 warning 0과 실제 `M29-CAP-01`을 PASS했다.
동적 GATT service와 LE CoC server·PSM 등록을 실제 실행했고, W07 exact `c71ef4a2…`에서는
Signed Write/EATT peer negotiation과 부하까지 실행해 `M29-SIGN-01`·`M29-EATT-01`을 PASS했다.

W02는 exact `dacf6341…`에서 link별 고정 client context와 512-byte long read를 구현했다. 전체 Host
gate, W02 source 계약 6개·parser 11개와 target role 2/2가 PASS했고 두 NU54DK에서 MTU 247,
512-byte read 100/100, corrupt·stale 0과 main-thread callback을 확인했다.

W03은 exact `babba5a1…`에서 link별 prepare transaction과 512-byte reliable write를 구현했다.
Host production 15개 시나리오, source 계약 6개·parser 11개, target role 2/2가 PASS했고 두
NU54DK에서 MTU 247, 512-byte reliable write·read-back 100/100, corrupt·partial commit 0과
main-thread callback을 확인했다. 따라서 `M29-LONG-01`은 PASS다. 첫 실기에서 DAPLink reset 뒤
READY 앞에 raw `0x1c`가 붙은 시작 noise를 protocol 위반으로 거부했고, flash 뒤 입력을 비운 다음
고정 `M29W03|1|READY?` 질의에 응답하도록 수정해 동일 조건에서 PASS했다. 이 실패는 RF·GPIO·ATT
실패가 아니며 실패 transcript와 최종 증거를 모두 보존한다.

W04는 exact `068a1765…`에서 characteristic당 descriptor 4개, read/write authorization,
generation link별 descriptor cache와 4-handle Read Multiple, link 지정 notify/indicate를 구현했다.
Host production 17개 시나리오, source 계약 8개·parser 11개, target role 2/2와 Arduino BLE 예제
6개가 PASS했다. 두 NU54DK의 `M29-DESC-01`은 MTU 247, descriptor 4개, Read Multiple 100/100,
authorization 402회 중 허용 401·예상 거부 1·오판 0, corrupt·stale 0을 확인했다. 첫 실기는
예상 ATT `0x08`에 앞선 전역 `-EIO`를 target이 실패로 오판했으며, rejecting phase에서는 상세
GATT event의 ATT 값을 기다리도록 수정한 뒤 동일 조건 PASS했다. 제품의 오류 보고 의미를
축소하지 않았고 다른 phase의 전역 오류는 계속 즉시 실패한다.

W05는 exact `e587c4fe…`에서 bonded resolved identity, database hash, target UUID, schema version과
CRC를 결합한 4×84-byte 고정 cache를 구현했다. Service Changed와 hash 변경은 해당 generation
link handle을 먼저 폐기한 뒤 재탐색하며 손상·잘린·미래 schema·다른 identity record는 복원하지
않는다. Production Host 18개 시나리오, source 계약 9개·parser 14개, target role 2/2와 Arduino
BLE 예제 8개가 PASS했다. 두 NU54DK의 `M29-CACHE-01`은 bonded reconnect 20/20, database hash
read 24, cache restore 20, Service Changed 1, migration 1, corrupt cache 거부 1, stale handle 0을
확인했다. 첫 `8f1f167d…` 실기의 `-ENOTCONN`은 CMSIS-DAP/GDB에서 Zephyr property bit를 공개
enum으로 직접 cast해 write를 notify로 오인한 것으로 확정했고 `publicProperties()` 변환 뒤 같은
조건에서 PASS했다.

W06은 exact `767bb4af…`에서 generation opaque handle의 LE CoC server 1개·channel 2개,
512-byte SDU, channel당 RX record 4개와 전체 TX buffer 4개를 구현했다. Production Host 7개
시나리오, source 계약 7개·parser 12개와 target role 2/2 warning 0이 PASS했다. 두 NU54DK의
`M29-COC-01`·`M29-NEG-01`은 방향별 channel당 1,000 SDU, malformed·offset·execute·PSM·credit
각 20회 거부, payload/cross-channel·예상 밖 수락·resource recovery·stale accept 0을 확인했다.
첫 실행의 W06 광고 PSM과 공통 runner 기대값 불일치는 RF 시작 전에 fail-closed로 거부했고,
역할별 광고 field를 명시하도록 수정한 뒤 같은 조건에서 PASS했다.

W07-C는 exact `c71ef4a21465923760933f6b87ad7d92d9a95698`에서 Host 계약 17/17, parser 16/16,
target role 2/2 warning 0을 확인했다. 두 NU54DK의 단일 strict runner session은 Signed Write
20회와 각 warm reboot 사이의 counter 영속, 동일 signed ATT PDU replay 수락 0을 검증했다.
EATT는 암호화 전 거부, 암호화 뒤 bearer 2개와 상한 초과 거부, production enhanced read/write,
bearer별 1,000 SDU와 payload 오류·deadlock·starvation 0을 확인했다. 따라서
`M29-SIGN-01`·`M29-EATT-01`은 PASS다.

W07-D exact `16eb8fce204f656beb6ed0a0d6f763cc7d492215`의 세 NU54DK에서는 mixed DUT의 central
1-link와 peripheral 1-link를 동시에 유지했다. 두 link 각각 GATT 1,000회와 LE CoC 1,000회,
수신측 sequence 검증, cross-link event·payload 오류·dropped event 0을 확인해
`M29-MULTI-01`을 PASS했다. 같은 revision의 W07-E는 M19 GAP, M20 GATT, M21 security,
M28 extended advertising·PAwR·RPA·bonded reconnect를 세 보드에 순환 배치했고 4/4 회귀군,
실패 0으로 `M29-REG-01`을 PASS했다.

Windows/Intel 상호운용은 exact `a964ae205e237d90149f6d2c0eb0ec6492492a33` M20 peripheral에서
광고 service UUID, GATT service·characteristic·property, nonce read, response write,
write command, notification 2회, indication 1회와 connect/disconnect 2회를 확인했다. WinRT 객체
close와 실제 RF disconnect 사이의 측정 지연 3.05초를 반영해 두 round 사이를 5초로 고정했다.
Android/iOS/Linux와 Windows의 모든 adapter·고급 profile을 시험한 결과로 확대하지 않는다.

## 8. 개발 예제와 남은 예제

다음 15개 예제는 현재 개발 소스에 있으며 Arduino `v0.5.0` smoke group에서 검사한다.
설치·지원 v0.4.1의 30개 예제 목록과는 별개다.

| Library | 작성된 예제 | 범위 |
| --- | --- | --- |
| `NUCODE_BLE` | `LongGattPeripheral`, `LongGattCentral`, `ReliableWritePeripheral`, `ReliableWriteCentral` | 512-byte long/reliable operation |
| `NUCODE_BLE` | `GattDescriptors`, `GattAuthorization`, `L2capCocServer`, `L2capCocClient` | descriptor·권한·고정 2-channel CoC |
| `NUCODE_BLE` | `MixedGattCocLinks` | 같은 Sketch의 role 선택으로 3보드 mixed GATT·CoC 실행 |
| `NUCODE_BLE_Security` | `GattCachePeripheral`, `GattCacheCentral` | bond·database hash·cache |
| `NUCODE_BLE_LegacySigning` | `LegacySignedWritePeripheral`, `LegacySignedWriteCentral` | deprecated legacy opt-in 경고 포함 |
| `NUCODE_BLE_EATT` | `EattPeripheral`, `EattCentral` | experimental opt-in·암호화·최대 2 bearer |

`MixedGattCocLinks`는 peripheral·mixed·central role을 같은 source에서 선택하고, mixed 보드의 두
generation link를 별도 handle로 유지한다. 예제 파일은 [`libraries`](../../libraries) 아래 각
library의 `examples`가 단일 원본이다.

모든 예제는 시작 함수와 비동기 결과를 검사하고 runtime 실패를 Serial에 출력한다. callback-only
완료를 peer 수신 성공으로 과장하지 않는다.
