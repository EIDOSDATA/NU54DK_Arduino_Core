# M29-W04 descriptor·authorization·read multiple 완료

| 항목 | 결과 |
| --- | --- |
| 작업일 | 2026-09-13 |
| production 구현 Core | `34d24ea68c8e4dda4f5f0fedef10dfdd580fa25b` |
| 최종 실기 Core | `068a1765f74e39c83cbf6e9e2f54de467c923441` |
| NCS / Zephyr | `99553055607b…` / `bf801e4e3d19…` |
| board / toolchain | `fe65f2f0880b…` / `dcbdc366a1` |
| production GATT Host | **17개 시나리오 PASS** |
| W04 parser / source 계약 | **11/11 / 8/8 PASS** |
| target build | **peripheral·central 2/2 PASS, warning 0** |
| Arduino 예제 build | **M29 group 6/6 PASS** |
| 실제 2보드 `M29-DESC-01` | **descriptor 4개, 4-handle read multiple 100/100 PASS** |
| M29 진행률 | **W04 완료, 4/8** |

## 1. 구현 범위

`BLEDescriptor`는 최대 512 byte의 내부 또는 caller-owned 고정 buffer와 UUID·permission을
소유한다. `BLECharacteristic` 하나에는 최대 4개만 등록할 수 있으며 CCC는 내부 descriptor로
별도 계산한다. 같은 객체의 중복 소유, 같은 characteristic의 UUID 중복, 다섯 번째 descriptor,
등록 뒤 schema 변경과 잘못된 buffer는 실패로 닫는다. Zephyr attribute array와 UUID·owner 표도
service slot 안의 고정 storage만 사용하며 heap fallback을 추가하지 않았다.

Characteristic과 descriptor의 read/write authorization callback은 Bluetooth callback 문맥에서
동기로 판정한다. 요청에는 generation 기반 connection, 정확한 characteristic/descriptor owner,
operation, data·length·offset과 prepare/execute/command flag를 전달한다. 사용자 main-thread에는
허용·거부 결과와 descriptor write만 고정 GATT event queue를 통해 복사한다. Blocking Arduino API를
authorization callback에서 호출하는 것은 지원하지 않는다.

Client는 link context마다 remote descriptor 4개와 Read Multiple handle 4개를 고정 소유한다.
Descriptor discovery는 다음 characteristic declaration handle을 먼저 찾아 현재 characteristic의
범위를 확정한 다음 exact descriptor UUID를 찾으므로 뒤 characteristic의 같은 UUID를 잘못 가져오지
않는다. Disconnect·generation 변경과 operation 실패는 cache와 pending boundary를 폐기한다.
Read Multiple은 caller array를 내부 고정 storage로 복사하며 null, 1개·5개, 중복 handle과 service
범위 밖 handle을 거부한다.

`notify(connection)`·`indicate(connection)` overload는 exact generation link와 해당 CCC를 확인한다.
기존 무인자 호출은 실제 subscribe한 peripheral 우선 view를 유지한다. Notification payload는 비동기
완료까지 service slot의 고정 buffer가 소유해 stack-local 수명을 넘기지 않는다. 기존 public event
enum 값은 새 항목을 끝에 추가하고 Host `static_assert`로 고정했다.

## 2. Host·target·예제 결과

Production GATT Host는 기존 lifecycle과 W02/W03을 포함한 17개 시나리오를 통과했다. W04는
descriptor 등록·permission·동기 authorization와 지연 event, descriptor 객체 재사용 거부,
두 generation link의 exact notify/indicate, descriptor discovery 범위, 4-handle read multiple,
stale callback과 다섯 번째 remote descriptor 거부를 확인한다. Source 계약 8개와 parser 11개는
고정 자원·profile·target 결합과 noise·비 ASCII·누락·중복·재배치·wrong revision·stale nonce·
수치 불일치·target FAIL 거부를 검사했다.

Exact `068a1765…`의 `nucode.m29.ble_descriptor_peripheral`과
`nucode.m29.ble_descriptor_central`은 고정 NCS v3.4.0에서 2/2 build-only PASS, warning 0이었다.
`LongGattPeripheral`, `LongGattCentral`, `ReliableWritePeripheral`, `ReliableWriteCentral`,
`GattDescriptors`, `GattAuthorization` 여섯 예제도 Arduino CLI BLE profile로 compile했다. 두 신규
예제는 시작 실패와 상세 비동기 결과를 검사하고 Serial에 성공·실패를 명시한다.

로컬 전체 Host gate 첫 실행은 기존 R10 시험용 EXE를 Windows Application Control이
`WinError 4551`로 일시 차단해 중단됐다. 같은 R10 suite의 즉시 단독 재실행은 PASS했으며 제품
assertion·compile 실패가 아니었다. 보안 정책은 변경하지 않았고, 동일 작업 트리의 closure 전체
Host gate 재실행은 R10을 포함해 `M12_GATE_PASS=host`로 완료됐다. 일시 정책 실패를 W04
기능 PASS로 바꾸지 않는다.

## 3. 실제 두 보드 결과

Runner는 두 board UID·MSD·target UART, clean exact Core·board·application·공통 runner digest와
HEX 옆 build record를 대조한 뒤 UID 지정 sector flash를 수행했다. Peripheral READY와 광고를
확인한 뒤 central scan을 시작했고 두 role은 같은 128-bit nonce와 full Core SHA를 사용했다.
외부 GPIO·전원 결선, mass erase/recover와 PMIC write는 사용하지 않았다. 세 번째 NU54DK는
이 2보드 test ID에 필요하지 않아 flash하지 않았다.

| 판정 | 관측값 |
| --- | ---: |
| peripheral / central ATT MTU | 247 / 247 |
| 발견한 descriptor | 4 / 4 |
| Read Multiple handle | 4 |
| Read Multiple 반복 | 100 / 100 |
| 한 응답 payload | 16 byte |
| authorization 전체 / 허용 / 거부 | 402 / 401 / 1 |
| 예상 authorization 거부 확인 | 1 |
| authorization 오판 | 0 |
| descriptor write | 0 |
| payload corruption·stale event | 0 / 0 |
| callback context 오류 | 0 |

최종 원시 transcript와 구조화 증거는 다음 파일에 보존한다. Git의 줄바꿈 정규화 뒤 실제 파일
byte를 다시 해시해 evidence의 transcript size·SHA-256과 일치시켰다.

- [`m29-w04-descriptor-evidence.json`](evidence/m29-w04-068a1765-descriptor-authorization/m29-w04-descriptor-evidence.json)
- [`peripheral transcript`](evidence/m29-w04-068a1765-descriptor-authorization/m29-w04-descriptor-evidence.peripheral.transcript.log)
- [`central transcript`](evidence/m29-w04-068a1765-descriptor-authorization/m29-w04-descriptor-evidence.central.transcript.log)

## 4. 첫 실패, 원인 분류와 동일 조건 재검증

첫 exact `34d24ea6…` 실기는 광고·연결과 양쪽 MTU 247까지 성공한 뒤 central이
`FAIL|stage=gap_error|code=-5`를 출력했다. 이는 잘못된 write를 peripheral이 ATT authorization
error `0x08`로 정확히 거부하면서 Core가 상세 GATT `operation_failed`와 전역 BLE error `-EIO`를
모두 queue했는데, poll 순서상 전역 error가 먼저 전달되어 HIL target이 예상 거부를 실패로
오판한 것이다. RF link와 MTU가 이미 확인됐고 GPIO 결선이 없는 시험이며 fault·DMA·GPIO 오류가
아니므로 CMSIS-DAP register dump로 확대하지 않았다.

Central target은 `rejecting` phase의 `-EIO`만 보류하고 뒤따르는 상세 GATT event가 exact ATT
`0x08`인지 판정하도록 수정했다. 다른 phase와 다른 driver error는 계속 즉시 실패한다. 첫 수정의
`<cerrno>`는 이 freestanding NCS C++ 환경에 없어 target 2/2 build가 flash 전에 실패했고,
Zephyr가 제공하는 `<errno.h>`로 교정했다. 고정 Toolchain 환경 변수가 빠진 최초 build 시도와
full revision 오입력도 각각 configure 전·flash 전 fail-closed로 중단됐으며 보드 결과로 세지
않았다.

최종 `068a1765…`를 두 role로 다시 빌드하고 같은 두 보드·UART·MTU·반복 조건에서 새 nonce로
한 번 실행해 위 수치로 PASS했다. 첫 실패 transcript는 삭제하거나 성공 로그로 덮어쓰지 않았다.

- [`첫 peripheral transcript`](evidence/m29-w04-34d24ea6-descriptor-authorization-failure/m29-w04-descriptor-evidence.peripheral.transcript.log)
- [`첫 central transcript`](evidence/m29-w04-34d24ea6-descriptor-authorization-failure/m29-w04-descriptor-evidence.central.transcript.log)

## 5. 지원 판정 경계와 다음 작업

이 결과로 `M29-DESC-01`과 `gatt_read_multiple` implementation을 PASS로 닫는다. 고정 SDK source의
API·Kconfig 존재는 계속 `candidate`이며 실제 구현·target·HIL 결과와 같은 증거로 취급하지 않는다.
Link 지정 notify/indicate와 두 link event 분리는 Host에서 production source로 검증하고 target을
빌드했지만, 이번 2보드 실기는 한 central-peripheral link의 descriptor·authorization test다.
3보드 동시 두 link actual-air는 W07 `M29-MULTI-01`에서 별도로 검증하며 지금 PASS로 승격하지
않는다.

다음 W05는 Service Changed, database hash와 robust cache migration을 link별 고정 storage로
구현한다. Bonded reconnect 20회, stale handle 사용 0과 corrupt cache 수락 0을 Host·target·두
보드 `M29-CACHE-01`에서 검증한다.
