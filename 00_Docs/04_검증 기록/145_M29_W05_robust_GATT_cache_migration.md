# M29-W05 robust GATT cache migration 완료

> 이 기록의 진행률·미실행·다음 작업은 해당 W 단계 완료 당시의 상태입니다. 후속 W07-C의
> Signed Write·EATT 2보드 결과는 [147번 기록](147_M29_W07_Signed_Write_EATT_HIL_준비.md)에,
> 현재 작업과 남은 범위는 [v0.5.0 TODO](../TODO_v0.5.0.md)에 있습니다.

| 항목 | 결과 |
| --- | --- |
| 작업일 | 2026-09-13 |
| production 구현 Core | `8f1f167d26ba28c4ecb59e267a0c49db11a29a38` |
| 최종 실기 Core | `e587c4fe563df65f37eb6cb322b3c07386f69ffa` |
| NCS / Zephyr | `99553055607b…` / `bf801e4e3d19…` |
| board / toolchain | `fe65f2f0880b…` / `dcbdc366a1` |
| production GATT Host | **18개 시나리오 PASS** |
| W05 parser / source 계약 | **14/14 / 9/9 PASS** |
| target build | **peripheral·central 2/2 PASS, warning 0** |
| Arduino 예제 build | **M29 group 8/8 PASS** |
| 실제 2보드 `M29-CACHE-01` | **bonded reconnect 20/20, migration·corrupt negative PASS** |
| M29 진행률 | **W05 완료, 5/8** |

## 1. 구현 범위

`BLEGattDatabase`는 Bluetooth 시작 전 application의 32-bit database revision을 고정하고 실제
Zephyr database hash 16 byte를 조회한다. Client의 `discoverCached()`는 generation connection,
target service/characteristic UUID와 schema version을 받아 standard Service Changed CCC,
Client Supported Features와 Database Hash 절차를 순서대로 수행한다. 기존 `discover/read/write`와
무인자 API는 유지했다.

영속 cache는 84-byte record 4개뿐이다. Record는 version·length·schema, resolved bonded peer
identity, database hash, target UUID, service/characteristic/CCC handle, property와 CRC32를 포함한다.
RPA 자체, 다른 identity, 다른 hash·UUID·schema, 잘린 record, 미래 version과 손상 CRC는 복원하지
않는다. Service Changed를 받으면 해당 link의 handle을 먼저 지우고 record를 폐기한 뒤 hash read와
rediscovery를 시작한다. Cache miss·restore·invalidation·corrupt reject 통계와 상세 main-thread
event를 제공하며 heap fallback은 없다.

`GattCachePeripheral`과 `GattCacheCentral` 예제는 database revision, pairing/bonding,
`discoverCached()`와 Service Changed·cache restore·operation failure를 공개 API만으로 처리한다.
시작 함수와 비동기 실패를 검사해 Serial에 명시하며 callback-only 완료를 peer 성공으로 과장하지
않는다.

## 2. Host·target·예제 결과

Production GATT Host는 W02~W04 회귀와 W05 cache restore, Service Changed, corrupt record와
CCC 없는 read/write target을 포함한 18개 시나리오를 통과했다. 마지막 시나리오는 Zephyr
`BT_GATT_CHRC_*` bit를 공개 `BLEProperty` bit로 직접 cast하는 회귀를 실행 경로에서 차단한다.
Source 계약 9개와 parser 14개는 고정 storage·identity·CRC·profile, exact record 순서,
noise·비 ASCII·누락·중복·재배치·wrong revision·stale nonce·수치 불일치·target FAIL 거부를
검사했다.

Exact `e587c4fe…`의 `nucode.m29.ble_cache_peripheral`과
`nucode.m29.ble_cache_central`은 고정 NCS v3.4.0에서 2/2 build-only PASS, warning 0이었다.
M29의 Arduino BLE 예제 8개도 BLE profile로 compile됐다. Windows에서 활성화하지 않은 NCS
Python은 시스템 Python registry의 `_ctypes`를 잘못 선택할 수 있어 실패한 build 디렉터리를
격리했고, 고정 bundle의 Python home·PATH를 우선한 동일 source build에서 2/2 PASS했다. 이 host
환경 실패는 target 결과로 세지 않는다.

## 3. 실제 두 보드 결과

Runner는 두 board UID·MSD·target UART, clean exact Core·board·application·공통 runner digest와
HEX 옆 build record를 대조한 뒤 UID 지정 sector flash를 수행했다. 두 role의 bond·cache·session을
RESET하고 peripheral 광고를 확인한 뒤 central scan을 시작했다. 외부 GPIO·전원 결선,
mass erase/recover와 PMIC write는 사용하지 않았다. 세 번째 NU54DK는 이 2보드 test ID에 필요하지
않아 flash하지 않았다.

| 판정 | 관측값 |
| --- | ---: |
| bonded peer | 1 |
| bonded reconnect | 20 / 20 |
| database hash read | 24 |
| cache save / restore | 4 / 20 |
| Service Changed event | 1 |
| cache invalidation | 2 |
| database migration | 1 |
| value handle migration | 19 → 21 |
| corrupt cache 거부 / 수락 | 1 / 0 |
| stale handle 사용 | 0 |
| callback context | PASS |

최종 원시 transcript와 구조화 증거는 다음 파일에 보존한다.

- [`m29-w05-cache-evidence.json`](evidence/m29-w05-e587c4fe-gatt-cache/m29-w05-cache-evidence.json)
- [`peripheral transcript`](evidence/m29-w05-e587c4fe-gatt-cache/m29-w05-cache-evidence.peripheral.transcript.log)
- [`central transcript`](evidence/m29-w05-e587c4fe-gatt-cache/m29-w05-cache-evidence.central.transcript.log)

## 4. 첫 실패, CMSIS-DAP 진단과 동일 조건 재검증

첫 exact `8f1f167d…` 실기는 peripheral 광고 뒤 central이
`FAIL|stage=gap_error|code=-128`을 출력했다. 보드 조합을 바꾼 두 번째 실행도 같은 단계와 코드로
실패해 특정 보드나 UART가 아닌 deterministic software 경로로 분류했다. 두 실행 모두 UID 지정
flash·UART·advertising이 성공했으므로 외부 GPIO가 없는 이 시험의 연결성 문제는 아니었다.

진단 image는 FAIL에 공개 `BLEError` ordinal을 추가했고 `ble_error=11`, 즉
`BLEError::not_connected`임을 확인했다. 이어 central에 CMSIS-DAP/GDB를 붙여
`recordError(not_connected)`에 hardware breakpoint를 걸었다. 호출 stack은
`recordError → failClient → failCache → startCacheDiscovery → progressGattCache → pollGatt →
Device::poll → loop`였고, target CCC 탐색 인자는 `start=20`, `end=19`, stage
`discovering_target_ccc`였다. Fault exception이나 DMA·GPIO 오류가 아니라 유효하지 않은 descriptor
범위를 제품 상태기가 생성한 것이다.

원격 target characteristic은 Zephyr에서 read+write property `0x0a`였다. 이를 공개
`BLEProperty`로 직접 cast하면 공개 enum의 notify bit `0x08`이 켜진 것으로 오인된다. Cache가
실제로는 없는 CCC를 마지막 value handle 뒤에서 찾으면서 위 역순 범위를 만들었다. 이미 존재하는
`publicProperties()` 명시 변환기를 사용하도록 수정하고, CCC 없는 read/write characteristic이
service 마지막 handle인 Host 실행시험을 추가했다. 최종 `e587c4fe…`를 같은 NCS·두 role·두 보드·
반복 조건에서 새 nonce로 실행해 위 수치로 PASS했다.

실패 transcript는 성공 로그로 덮어쓰지 않고 보존한다.

- [`첫 A/B central`](evidence/m29-w05-8f1f167d-cache-failure-ab/central.transcript.log) · [`peripheral`](evidence/m29-w05-8f1f167d-cache-failure-ab/peripheral.transcript.log)
- [`보드 교체 A/C central`](evidence/m29-w05-8f1f167d-cache-failure-ac/central.transcript.log) · [`peripheral`](evidence/m29-w05-8f1f167d-cache-failure-ac/peripheral.transcript.log)
- [`BLEError 진단 central`](evidence/m29-w05-8f1f167d-cache-diagnostic/central.transcript.log) · [`peripheral`](evidence/m29-w05-8f1f167d-cache-diagnostic/peripheral.transcript.log)

## 5. 지원 판정 경계와 다음 작업

이 결과로 `M29-CACHE-01`과 `gatt_service_changed_cache` implementation을 PASS로 닫는다. 고정
SDK source의 API·Kconfig 존재는 계속 `candidate`이며 구현·target·HIL과 같은 증거가 아니다.
이번 두 보드 결과는 한 central-peripheral link의 cache migration이며 3보드 동시 link 또는
cross-vendor OS cache 상호운용으로 확대하지 않는다.

다음 W06는 generation 기반 LE CoC server 1개·channel 2개, channel당 512-byte SDU·RX record
4개와 전체 TX buffer 4개를 고정 자원으로 구현한다. 2-channel 양방향 1,000 SDU, credit starvation,
잘못된 PSM/SDU와 disconnect 회수를 Host·target·두 보드 `M29-COC-01`·`M29-NEG-01`에서 검증한다.
