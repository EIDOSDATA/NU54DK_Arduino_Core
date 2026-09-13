# M29-W03 long/reliable write 완료

| 항목 | 결과 |
| --- | --- |
| 작업일 | 2026-09-13 |
| 구현 Core | `8629611e78f753409468f3b9943fa250c2ab1139` |
| 최종 실기 Core | `babba5a1bf306e69b6900df26711ea316fa5dc12` |
| NCS / Zephyr | `99553055607b…` / `bf801e4e3d19…` |
| board / toolchain | `fe65f2f0880b…` / `dcbdc366a1` |
| production GATT Host | **15개 시나리오 PASS** |
| W03 parser / source 계약 | **11/11 / 6/6 PASS** |
| target build | **peripheral·central 2/2 PASS, warning 0** |
| Arduino 예제 build | **M29 group 4/4 PASS** |
| 실제 2보드 reliable write | **MTU 247, 512 byte write/read-back 100/100 PASS** |
| M29 진행률 | **W03 완료, 3/8** |

## 1. 구현 범위

응답이 있는 `BLEClient.write()`는 최대 512 byte의 고정 buffer를 사용해 Zephyr long write
procedure를 시작한다. `writeWithoutResponse()`는 단일 ATT command이므로 기존 MTU-3 상한을
유지한다. 상세 characteristic event에는 generation 기반 `BLEConnectionHandle`을 포함해 두 link의
write 결과를 구분하고 stale callback을 사용자 event로 승격하지 않는다.

Server에는 link별 한 개, 전체 두 개의 고정 `PrepareTransaction`을 추가했다. 각 transaction은
connection generation, 대상 characteristic, 512-byte staging buffer, 수신 범위를 소유한다.
Prepare 단계는 offset·길이·혼합 characteristic·누락 범위를 검사할 뿐 공개 value를 바꾸지 않는다.
Execute 성공에서만 staging value를 한 번 commit하며 cancel, execute without prepare, overflow,
stale generation과 disconnect 뒤 execute는 실패로 닫는다. `BLEDevice.end()`와 link disconnect는
해당 transaction을 회수한다.

BLE production profile은 ATT MTU 247, ACL 251 byte, ATT TX 4개와 prepare count 6개를 명시했다.
Heap fallback은 추가하지 않았고 M29 계약의 link당 한 transaction·value 512 byte 상한을 유지했다.

## 2. Host·target·예제 결과

Production GATT를 실제 링크하는 Host 실행은 기존 회귀를 포함한 15개 시나리오를 통과했다. W03
시나리오는 두 link transaction 분리, 512-byte atomic commit, cancel 뒤 value 불변, offset gap,
overflow, 다른 characteristic 혼합, stale generation, disconnect/end 회수를 확인한다. W03 source
계약 6개와 fixed protocol parser 11개는 noise·비 ASCII·누락·중복·재배치·stale nonce·wrong
revision·wrong role·수치 불일치·target FAIL을 거부한다.

Exact `babba5a1…` target은 `m29_ble_long_write_hil`의 peripheral·central role 2/2를 warning 없이
빌드했다. 같은 exact source에서 `ReliableWritePeripheral`·`ReliableWriteCentral`과 W02 두 예제를
Arduino CLI BLE profile로 4/4 compile했고 IDE example discovery도 PASS했다. 두 신규 예제는
시작 함수와 상세 callback의 connection/status를 확인하고 실패를 Serial에 명시적으로 출력한다.

로컬 전체 Host gate는 Windows Application Control이 시험용 임시 unsigned EXE와 fixture
`nrfutil` 실행을 `WinError 4551`로 차단해 완주하지 못했다. 기본 TEMP와 별도 ASCII TEMP에서 같은
정책 차단을 확인한 뒤 무한 재시도하지 않았다. W03 focused Host, production GATT, readiness,
build-matrix·profile·package example 계약은 각각 PASS했으며 전체 Linux Host 결과는 push한 exact
commit의 GitHub CI로 판정한다. 이 로컬 환경 실패를 제품 또는 W03 기능 PASS로 바꾸지 않는다.

## 3. 실제 두 보드 결과

Runner는 두 board UID·MSD·target UART를 교차 확인하고 exact Core·board·application·공통 runner
digest와 HEX 옆 build record가 맞을 때만 UID 지정 sector flash를 수행했다. Peripheral READY와
광고를 확인한 뒤 central을 시작했으며 두 role은 같은 128-bit nonce와 full Core SHA를 사용했다.
외부 GPIO·전원 결선, mass erase/recover와 PMIC write는 사용하지 않았다. 세 번째 NU54DK는 이
2-link test ID에 필요하지 않아 flash하지 않았다.

| 판정 | 관측값 |
| --- | ---: |
| peripheral / central ATT MTU | 247 / 247 |
| central reliable write | 100 / 100 |
| central read-back | 100 / 100 |
| payload 길이 | 512 byte |
| payload corruption | 0 |
| partial commit | 0 |
| stale·cross-link event | 0 |
| callback context 오류 | 0 |

최종 원시 transcript와 구조화 증거는 다음 파일에 보존한다.

- [`m29-w03-long-write-evidence.json`](evidence/m29-w03-babba5a1-long-write/m29-w03-long-write-evidence.json)
- [`peripheral transcript`](evidence/m29-w03-babba5a1-long-write/m29-w03-long-write-evidence.peripheral.transcript.log)
- [`central transcript`](evidence/m29-w03-babba5a1-long-write/m29-w03-long-write-evidence.central.transcript.log)

## 4. 첫 실패, 원인 분류와 동일 조건 재검증

첫 exact `8629611e…` 실기는 peripheral READY 앞에 raw byte `0x1c`가 한 개 붙어 strict parser가
protocol 시작 전에 거부했다. Central transcript는 비어 있고 광고·연결·ATT는 시작되지 않았으므로
GPIO/RF/long write 실패가 아니라 flash/reset 직후 DAPLink target UART 시작 noise로 분류했다.
외부 결선이 없는 RF 시험이고 protocol 이전 실패여서 GPIO 연결성 검사나 CMSIS-DAP 주변장치·DMA·
GPIO/fault register 수집은 필요하지 않았다.

Firmware에 고정 `M29W03|1|READY?` 질의를 추가하고 runner가 flash 뒤 입력을 비운 다음 각 target에
질의를 한 번 보내 exact READY 한 줄을 받도록 고쳤다. 최종 parser의 noise·중복·누락 거부는
완화하지 않았다. 또한 W03 runner가 재사용하는 W02 공통 runner source까지 clean/digest 검증에
묶었다. Exact `babba5a1…`을 두 role로 다시 빌드하고 같은 두 보드·UART·MTU·반복 조건에서 한 번
실행해 위 수치로 PASS했다. 실패 원본은 삭제하거나 성공 로그로 덮어쓰지 않았다.

- [`첫 central transcript`](evidence/m29-w03-8629611e-long-write/m29-w03-long-write-evidence.central.transcript.log)
- [`첫 peripheral transcript`](evidence/m29-w03-8629611e-long-write/m29-w03-long-write-evidence.peripheral.transcript.log)

Target 준비 중 Unicode output path의 Kconfig MD5 처리, PowerShell 특수문자 argument와 role별
미사용 변수 `-Werror`도 각각 원인을 분리해 ASCII short build path와 source 교정 뒤 동일 target
2/2로 재검증했다. 이들은 flash 전 build 실패이며 실제 RF/ATT 실패로 세지 않는다.

## 5. 지원 판정 경계와 다음 작업

W03 결과는 512-byte long/reliable write, server prepare/execute atomic commit과 Host negative의
실제 근거다. W02의 long read 결과와 결합해 `M29-LONG-01`을 PASS로 닫고
`gatt_long_reliable` implementation을 PASS로 표시한다. 고정 SDK source의 API 존재는 계속
`candidate`이며 이 실기 결과와 같은 증거로 취급하지 않는다.

Actual-air malformed ATT injection, cross-vendor peer와 EATT bearer는 이 test ID의 범위가 아니다.
W04는 characteristic당 descriptor 4개, authorization과 4-handle read multiple을 link별 고정
상태로 구현하고 `M29-DESC-01`을 Host·target·두 보드에서 검증한다.
