# NU54DK HIL 시험

이 디렉터리는 NU54DK 실물 보드가 필요한 host-side 시험만 관리합니다. 일반 host unit test나
Arduino compile test와 분리하며, 장치가 없는 CI에서 PASS로 추정하지 않습니다.

| 파일 | 역할 | 주요 fixture |
| --- | --- | --- |
| `m6_serial_echo.py` | pyOCD flash 후 UART READY·echo 검증 | NU54DK, CMSIS-DAP V2 UART |
| `m7_i2c_pmic.py` | BQ25186 고정 ID register의 읽기 전용 I2C 검증 | 보드 내장 PMIC |
| `m7_peripheral_hil.py` | SPI loopback·ADC·PWM token 검증 | 명시된 점퍼와 핀 fixture |
| `m8_upload.py` | manifest를 검증한 pyOCD/J-Link upload 반복 시험 | NU54DK debug probe |
| `m8_debug.py` | debug server와 Sketch source breakpoint 검증 | pyOCD 또는 J-Link |
| `m14_pin_hil.py` | 신규 LED output/readback과 버튼 pull·edge 검증 | NU54DK, CMSIS-DAP V2 UART, 사용자 버튼 동작 |
| `m15_auto.py` | identity·uptime·GRTC callback·Settings·WDT 비-System-OFF 자동 검증 | 공식 Ubuntu CI artifact, NU54DK, CMSIS-DAP V2 UART |
| `m15_system_off.py` | SWD 격리 뒤 timed GRTC→사용자 SW0 System OFF 결합 검증 | 공식 Ubuntu CI artifact, NU54DK, CMSIS-DAP V2 UART, debug-control SW1, 사용자 SW0 |
| `ac01_gpio_hil.py` | P2 loopback GPIO·pulse·shift와 SW0 자기구동 level IRQ·callback mask 자동 검증 | NU54DK 한 대, 같은 보드 P2.5↔P2.6 점퍼 한 가닥, CMSIS-DAP V2 UART |
| `ac02b_peripheral.py` | 동적 Serial1·Wire·SPI·PWM·ADC pair HIL과 exact 증적 생성 | NU54DK 두 대, 아래 4개 점퍼, 각 보드 USB/DAPLink UART |
| `m19_ble_gap.py` | GAP UUID/manufacturer filter·연결·재연결 자동 검증 | NU54DK 두 대, 각 보드 USB/DAPLink UART, 추가 배선 없음 |
| `m20_ble_gatt.py` | 범용 GATT read/write/notify/indicate·재발견 자동 검증 | NU54DK 두 대, 각 보드 USB/DAPLink UART, 추가 배선 없음 |
| `m21_ble_security.py` | pairing·bond 복원/삭제/repair와 BAS/DIS/HID protocol 자동 검증 | NU54DK 두 대, 각 보드 USB/DAPLink UART, 추가 배선 없음 |
| `ble_pair_hil_common.py` | M19~M21 exact image·두 UID·UART·evidence 공통 경계 | 직접 실행하지 않음 |
| `test_m7_*.py` | 실제 장치 없이 HIL protocol/parser를 검증 | 없음 |
| `test_m14_pin_hil.py` | M14 수동 동작 protocol·증적의 fail-closed 경계를 검증 | 없음 |
| `test_m15_auto.py` | M15 자동 protocol과 Linux producer/Windows consumer provenance를 검증 | 없음 |
| `test_m15_system_off.py` | M15 timed·button ARM, 무응답 시간과 결합 wake protocol·증적 경계를 검증 | 없음 |
| `test_ac01_gpio_hil.py` | AC-01 exact token 순서·범위·fixture·실패 경계를 검증 | 없음 |
| `test_ac02b_peripheral.py` | AC-02B nonce·순서·ADC 범위와 WIRING_REQUIRED gate를 검증 | 없음 |
| `../../host/test_m19_ble_gap_hil.py` | M19 pair protocol의 stale/reorder/FAIL 거부 경계를 검증 | 없음 |
| `../../host/test_m20_ble_gatt_hil.py` | M20 pair protocol의 stale/누락/reorder/FAIL 거부 경계를 검증 | 없음 |
| `../../host/test_m21_ble_security_hil.py` | M21 persistence·old-key·RF nonce binding·profile parser 경계를 검증 | 없음 |

## 실행 원칙

- 보드 target과 build manifest가 기대값과 일치해야 합니다.
- 일반 upload 경로에서는 mass erase나 recover를 사용하지 않습니다.
- PMIC 시험은 허용한 address/register의 읽기만 수행합니다.
- probe UID, COM port와 물리 fixture는 실행 인자로 명시하거나 안전한 자동 탐색 결과가 하나일
  때만 사용합니다.
- 실기 PASS는 해당 commit, artifact hash와 fixture 조건을 검증 기록에 연결합니다.
- M15 운영 절차에서는 고정된 NCS Ubuntu container를 사용하는 clean GitHub Actions build
  artifact만 사용합니다. 로컬 Windows build를 M15 검증 증적으로 대체하지 않습니다.

## M15 공식 CI artifact 계약

`m15_auto.py`와 `m15_system_off.py`의 운영 입력은
`.github/workflows/m12-reproducible-build.yml`이 exact commit에서 생성한
`m12-zephyr-build-<40자리 commit>` artifact입니다. artifact를 다운로드한 Windows checkout도
같은 commit이어야 하며 Core, M15 application, board package와 runner가 사용하는
`m14_pin_hil.py`, `m6_serial_echo.py`가 모두 clean이어야 합니다. Runner는 revision·source
digest와 HEX 실행 전후 불변성을 fail-closed로 검사하지만 GitHub run의 서명이나 attestation
자체를 확인하지는 않으므로 run ID와 artifact 이름은 검증 기록에 별도로 남깁니다.

Ubuntu producer는 checkout의 LF byte로 build record SHA-256을 만듭니다. Windows의 clean Git
checkout은 같은 commit이어도 CRLF byte를 가질 수 있으므로 M15 consumer만 Git `HEAD` blob의
canonical byte로 같은 digest를 재계산합니다. 이 처리는 dirty source를 허용하는 우회가 아닙니다.
runner는 먼저 관련 source와 board submodule의 clean 상태, exact Core·board revision, 고정
NCS/Zephyr revision과 target을 검증한 뒤 세 source digest가 모두 일치할 때만 flash합니다.
M14 로컬 build/HIL은 기존대로 실제 working-tree byte를 검증합니다.

비버튼 자동 HIL image는 artifact 안의 다음 경로를 사용합니다.

```powershell
Set-Location "<NU54DK_Arduino_Core 저장소 경로>"
$CoreRoot = (Get-Location).Path
$ArtifactRoot = "<다운로드해 압축을 푼 m12-zephyr-build artifact>"
$Python = "C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe"
$Commit = git -C $CoreRoot rev-parse HEAD
$AutoHex = Join-Path $ArtifactRoot `
  "twister\nrf54l15dk_nrf54l15_cpuapp_nu54dk\zephyr_gnu\nucode.m15.auto_hil\m15_hil\zephyr\zephyr.hex"

& $Python -I "$CoreRoot\tests\hil\nu54dk\m15_auto.py" `
  --hex $AutoHex `
  --board-id "<시험할 CMSIS-DAP UID>" `
  --expected-core-revision $Commit `
  --evidence "$CoreRoot\build\m15\hil\m15-auto.evidence.json"
```

이 자동 HIL은 System OFF에 진입하지 않습니다. Identity와 uptime, GRTC one-shot callback,
Settings의 reset 전후 유지, WDT feed·stop·expiry 경계까지만 검증합니다. 자동 transcript나
evidence를 timed GRTC wake 또는 사용자 버튼 wake PASS로 확대하지 않습니다.

## M14 신규 핀 HIL

`PIN_LED2`, `PIN_LED3`은 LOW/HIGH를 실제 GPIO에 기록한 뒤 raw readback이 같은지 자동
확인합니다. `PIN_BUTTON1`, `PIN_BUTTON2`, `PIN_BUTTON3`은 `INPUT_PULLUP`에서 뗀 상태
HIGH와 누른 상태 LOW를 확인하고 FALLING, RISING, CHANGE ISR을 순서대로 검증합니다.

화면의 Arduino 논리명과 보드의 사용자 버튼 표기는 다음과 같이 대응합니다. 회로도 내부의
부품 참조번호가 아니라 보드의 `SW0..3` 사용자 표기를 기준으로 조작합니다.

| Arduino 논리명 | DTS alias | 사용자 버튼 | nRF54L15 GPIO |
| --- | --- | --- | --- |
| `PIN_BUTTON0` | `sw0` | SW0 | P1.13 — M6에서 검증했으므로 M14 대상 제외 |
| `PIN_BUTTON1` | `sw1` | SW1 | P1.09 |
| `PIN_BUTTON2` | `sw2` | SW2 | P1.08 |
| `PIN_BUTTON3` | `sw3` | SW3 | P0.04 |

`PIN_LED1`은 `PIN_PWM0`과 동일한 물리 자원을 PWM이 소유하므로 이 digital HIL에서는
제외합니다. 해당 자원의 회귀 근거는 M7 `PIN_PWM0` 0/128/255 driver 시험입니다. 또한
`PIN_LED2`를 시험하는 동안에는 외부 debug session을 종료해 SWO와의 동시 소유를 피합니다.

보드 연결 전에는 **NCS v3.4.0 Toolchain terminal**에서 다음 production target
build-only를 실행합니다. 일반 PowerShell이라면 먼저 nRF Connect extension의 `Open terminal`로
고정 Toolchain 환경을 적용해야 합니다.

```powershell
Set-Location "<NU54DK_Arduino_Core 저장소 경로>"
$CoreRoot = (Get-Location).Path
$NcsRoot = "C:\ncs\v3.4.0"
$BoardRoot = "$CoreRoot\board_package\NU54DK_Zephyr_DTS"
$Python = "C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe"
$Build = "$env:TEMP\nu54dk-m14-pin-hil"

Push-Location $NcsRoot
& $Python -I -m west build -p always `
  -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d $Build `
  "$CoreRoot\tests\zephyr\m14_pin_hil" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DEXTRA_ZEPHYR_MODULES=$CoreRoot"
Pop-Location
```

실기는 CMSIS-DAP V2 target UART를 사용하는 다른 프로그램과 debug session을 모두 닫고
실행합니다. `--acknowledge-manual-actions`는 세 버튼을 화면 안내대로 직접 누르고 뗄 준비가
되었다는 명시적 승인입니다. 각 ACTION은 30초, 전체 transcript는 기본 520초 제한을 가지며,
기존 증적은 `--overwrite-evidence` 없이는 덮어쓰지 않습니다. Core HIL 관련 source와 보드
submodule이 clean하지 않거나, 현재 보드 checkout이 부모 commit의 gitlink와 다르거나, HEX 옆
build record가 기대 Core·보드 commit, NCS/Zephyr revision, NU54DK target과 다르면 flash 전에
실패합니다. build record의 Core 범위·M14 application·board tree SHA-256도 현재 source에서
CMake와 같은 방식으로 다시 계산하여 세 값이 모두 정확히 같아야 합니다.

```powershell
$Commit = git -C $CoreRoot rev-parse HEAD
& $Python -I "$CoreRoot\tests\hil\nu54dk\m14_pin_hil.py" `
  --hex "$Build\m14_pin_hil\zephyr\zephyr.hex" `
  --expected-core-revision $Commit `
  --acknowledge-manual-actions `
  --evidence "$CoreRoot\build\m14\hil\m14-pin-hil.evidence.json"
```

화면에 `ACTION`이 출력될 때 지정된 버튼 하나만 누르거나 뗍니다. 모든 핀과 edge가
통과해야 `status: passed` JSON과 SHA-256으로 결합된 companion transcript가 생성됩니다.
timeout, target FAIL, 핀 ID·순서 불일치 또는 중복 token은 PASS 증적을 만들지 않습니다.

## AC-01 P2.5↔P2.6 GPIO loopback HIL

같은 NU54DK의 `PIN_GPIO0/P2.5`와 `PIN_GPIO1/P2.6`을 점퍼 한 가닥으로 연결합니다. 두 번째
보드와 외부 pull-up은 사용하지 않습니다. `OUTPUT_OPENDRAIN` release는 P2.6의
`INPUT_PULLUP`으로 확인합니다. P2에는 CPUAPP GPIOTE가 없으므로 두 connector pin은 interrupt를
지원하지 않습니다. Level IRQ와 callback mask는 SW0 P1.13을 input-connected open-drain으로
자기구동해 실제 GPIOTE20 event를 만들며, 시험 중 SW0를 누르면 안 됩니다. Runner는 다음 항목을
사용자 동작 없이 한 번에 검사합니다.

- open-drain LOW와 high-Z release
- level LOW/HIGH의 hold one-shot과 deassert 뒤 재무장
- `pulseIn()`, `pulseInLong()` 폭 범위와 timeout `0`
- `shiftOut()` 최종 bit와 `shiftIn()` 고정 LOW/HIGH byte
- 중첩 `noInterrupts()` 중 callback 억제, Zephyr heartbeat 진행, held level의 마지막 복원

두 보드가 연결된 환경에서 잘못된 target을 기록하지 않도록 `--board-id`를 필수로 받습니다.
Runner는 Core 관련 source, AC-01 application과 board submodule이 commit된 clean 상태인지 확인하고,
HEX 옆 build record의 Core·board revision, NCS/Zephyr revision과 세 source SHA-256이 현재 checkout과
exact 일치할 때만 flash합니다.

```powershell
Set-Location "<NU54DK_Arduino_Core 저장소 경로>"
$CoreRoot = (Get-Location).Path
$NcsRoot = "C:\ncs\v3.4.0"
$BoardRoot = "$CoreRoot\board_package\NU54DK_Zephyr_DTS"
$Python = "C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe"
$Build = "$env:TEMP\nu54dk-ac01-gpio-hil"

Push-Location $NcsRoot
& $Python -I -m west build -p always `
  -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d $Build `
  "$CoreRoot\tests\zephyr\ac01_hil" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DZEPHYR_EXTRA_MODULES=$CoreRoot"
Pop-Location

$Commit = git -C $CoreRoot rev-parse HEAD
& $Python -I "$CoreRoot\tests\hil\nu54dk\ac01_gpio_hil.py" `
  --hex "$Build\ac01_hil\zephyr\zephyr.hex" `
  --board-id "<시험할 CMSIS-DAP UID>" `
  --expected-core-revision $Commit `
  --acknowledge-loopback `
  --evidence "$CoreRoot\build\ac01\hil\ac01-gpio.evidence.json"
```

기존 evidence와 transcript는 `--overwrite-evidence` 없이는 덮어쓰지 않습니다. 이 HIL은
외부 저항, 두 보드 간 통신, logic analyzer나 오실로스코프 정확도 측정을 요구하지 않습니다.

## AC-02B 동적 주변장치 pair HIL

AC-02B는 Board A를 Arduino Core DUT, Board B를 direct Zephyr peer로 사용합니다. DUT는 공개
production API인 `Serial1.setPins()`, `Wire.setPins()`, `SPI.setPins()`,
`analogWriteFrequency()`, `analogWrite()`와 `analogRead()`를 직접 호출합니다. P1.12/A0는
먼저 ADC 입력으로 읽은 뒤 같은 run에서 transferable PWM20 출력으로 넘깁니다. Wire는 Board A의
온보드 BQ25186 `MASK_ID`를 읽기 전용으로 검증하고 peer의 I2C controller와 target은 모두
비활성화합니다. 따라서 현재 미지원인 Wire target/Wire1을 PASS로 확대하지 않습니다.

두 보드의 전원을 끈 상태에서 다음 점퍼를 모두 연결합니다. Board A의 SPI loopback 한 가닥을
제외한 나머지는 두 보드 사이 연결입니다.

| 번호 | Board A(DUT) | 방향 | Board B(peer) | 검증 |
| --- | --- | --- | --- | --- |
| 1 | GND | ↔ | GND | 공통 기준 전압 |
| 2 | P1.12 / A0 | ↔ | P2.5 / GPIO | peer ADC LOW·HIGH drive 후 DUT 1 kHz 25%·75% PWM capture |
| 3 | P2.2 / SPI00 MOSI | ↔ 같은 Board A의 P2.4 / SPI00 MISO | 해당 없음 | 4 MHz 40-byte local loopback |

Serial1은 Board A CMSIS-DAP의 x.1 보조 VCOM을 host가 exact echo하므로 보드 간 P0 배선이
필요하지 않습니다. Wire는 Board A 내부 P1.2/P1.3 bus의 BQ25186 주소 `0x6A`, register
`0x0C`를 100/400 kHz에서 no-STOP pointer write와 repeated-start 1-byte read로 읽고, 각
round에서 exact `0x41`을 요구합니다. PMIC data register는 쓰지 않습니다. 보드 간 I2C
배선과 외부 pull-up도 필요하지 않습니다. 첫 I2C transaction으로 BQ25186 기본 watchdog이
시작될 수 있습니다. peer P2.5는 ADC 단계에서는 push-pull output이며, 마지막 ADC LOW 응답
후 high-Z input으로 전환됩니다. P2에는 CPUAPP GPIOTE가 없으므로 PWM edge는 bounded polling으로
측정합니다. DUT는 그 응답 뒤 P1.12의 ADC ownership을 PWM20으로 넘기므로 두 보드가 동시에
선을 구동하지 않습니다.

배선 전에는 두 role image와 host parser까지만 준비합니다. NCS v3.4.0 Toolchain terminal에서
다음 두 production target을 각각 pristine build합니다.

```powershell
Set-Location "<NU54DK_Arduino_Core 저장소 경로>"
$CoreRoot = (Get-Location).Path
$NcsRoot = "C:\ncs\v3.4.0"
$BoardRoot = "$CoreRoot\board_package\NU54DK_Zephyr_DTS"
$Python = "C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe"
$DutBuild = "$env:TEMP\nu54dk-ac02b-hil-dut"
$PeerBuild = "$env:TEMP\nu54dk-ac02b-hil-peer"

Push-Location $NcsRoot
& $Python -I -m west build -p always `
  -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d $DutBuild `
  "$CoreRoot\tests\zephyr\ac02b_hil_dut" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DZEPHYR_EXTRA_MODULES=$CoreRoot"
& $Python -I -m west build -p always `
  -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d $PeerBuild `
  "$CoreRoot\tests\zephyr\ac02b_hil_peer" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DZEPHYR_EXTRA_MODULES=$CoreRoot"
Pop-Location

& $Python -I "$CoreRoot\tests\hil\nu54dk\test_ac02b_peripheral.py" -v
```

Runner에는 서로 다른 두 CMSIS-DAP UID가 필수입니다. 각 UID에서 DAPLink MSD와 COM을 함께
찾아 서로 다른 UID·MSD·COM인지 확인하고, role별 build record, Core·board revision, source
digest와 HEX SHA-256을 flash 전후에 exact 검증합니다. 아래 첫 실행처럼
`--acknowledge-wiring`을 생략하면 image와 장치 preflight 뒤 `WIRING_REQUIRED`와 종료 코드 3을
반환하며 **flash, start command, PASS evidence를 수행하지 않습니다**.

```powershell
$Commit = git -C $CoreRoot rev-parse HEAD
$DutHex = "$DutBuild\ac02b_hil_dut\zephyr\zephyr.hex"
$PeerHex = "$PeerBuild\ac02b_hil_peer\zephyr\zephyr.hex"

& $Python -I "$CoreRoot\tests\hil\nu54dk\ac02b_peripheral.py" `
  --dut-hex $DutHex --peer-hex $PeerHex `
  --dut-board-id "<Board A CMSIS-DAP UID>" `
  --peer-board-id "<Board B CMSIS-DAP UID>" `
  --expected-core-revision $Commit
```

점퍼 3개와 두 보드 USB를 확인한 마지막 단계에서만 다음 실제 실행을 허용합니다.

```powershell
& $Python -I "$CoreRoot\tests\hil\nu54dk\ac02b_peripheral.py" `
  --dut-hex $DutHex --peer-hex $PeerHex `
  --dut-board-id "<Board A CMSIS-DAP UID>" `
  --peer-board-id "<Board B CMSIS-DAP UID>" `
  --expected-core-revision $Commit `
  --acknowledge-wiring `
  --evidence "$CoreRoot\build\ac02b\hil\ac02b-peripheral.evidence.json"
```

host는 같은 128-bit nonce를 먼저 peer에 주입해 ADC/PWM fixture를 arm한 뒤 DUT를 시작합니다.
Serial1 end/rebegin 두 cycle, BQ25186 Wire 100/400 kHz repeated-start 두 cycle, SPI
interrupt mask와 4 MHz loopback, ADC 외부 LOW/HIGH 뒤 동일 선의 PWM 외부 polling 측정이 양쪽 exact token
순서로 모두 끝나야만 `status: passed` evidence를 만듭니다. timeout, stale nonce, role image
오배치, 한쪽 FAIL, token 누락·재배치 또는 ADC 범위 불일치는 PASS로 축소하지 않습니다.

## M19/M20/M21 두 보드 BLE HIL

M19~M21은 RF로 통신하므로 P2.5↔P2.6 점퍼와 외부 저항을 사용하지 않습니다. 보드 두 대를
각각 USB에 연결해 전원, DAPLink flash와 UART를 확보합니다. Runner는 peripheral/central
DAPLink UID를 필수로 받아 UID·MSD·UART가 모두 다른지 확인하고, clean exact commit과 두 role
build record·HEX SHA-256을 검증한 뒤에만 flash합니다.

- M19: advertise, UUID/manufacturer filter, connect/disconnect/readvertise/reconnect
- M20: discovery, cached read, 두 write mode, notify/indicate, handle invalidation,
  reconnect 뒤 rediscovery/resubscribe
- M21: pairing, reboot 뒤 bond 복원, 삭제 뒤 old-key 재연결 거부와 repair,
  encrypted BAS/DIS/HID protocol

각 runner는 같은 nonce가 결합된 양쪽 FINAL token을 모두 확인해야 JSON PASS를 생성합니다.
M21은 128-bit nonce 전체를 Peripheral manufacturer data로 광고하고 Central이 이를 exact-match한
뒤에만 연결하므로 이름이 같은 stale 장치를 peer로 오인하지 않습니다.
한쪽 timeout/FAIL, stale nonce, token 누락·재배치, 같은 role HEX 또는 callback 문맥 오류는 PASS로
축소하지 않습니다. Build와 실행 명령, role image 경로는
[M19 검증 기록](<../../../00_Docs/04_검증 기록/23_M19_BLE_Core_GAP_검증.md>)과
[M20 검증 기록](<../../../00_Docs/04_검증 기록/24_M20_범용_GATT_검증.md>),
[M21 검증 기록](<../../../00_Docs/04_검증 기록/25_M21_BLE_보안과_표준_Profile_검증.md>)을 따릅니다.

## M15 System OFF 결합 HIL

System OFF는 자동 HIL과 분리한 단일 수동 session에서 두 단계로 검증합니다.

1. GRTC timed wake 뒤 `RESET_CLOCK` 확인
2. 다시 System OFF에 진입한 뒤 사용자 SW0/P1.13 wake와 `LOW_POWER_WAKE` 확인

두 단계는 같은 공식 CI artifact의 build record와 image를 사용합니다. 로컬에서 image를 다시
빌드하지 않습니다. Image는 부팅만으로 System OFF에 진입하지 않으며 runner가 UART 상태와
명시적 준비 token을 확인한 뒤에만 각 단계를 arm합니다.

### Debug-control SW1 설정

NU54DK에는 `DISABLE_SWD`와 `DISABLE_UART`를 함께 가진 온보드 debug-control 2연 `SW1`이
있습니다. 이 부품은 Arduino 사용자 버튼 `SW1`/P1.09와 **다른 물리 부품**입니다.

1. Image 기록과 UART 준비까지 debug-control `SW1`을 기존 상태로 둡니다.
2. Runner의 격리 안내가 나오면 `DISABLE_SWD` 쪽만 격리 위치로 전환합니다.
3. `DISABLE_UART` 쪽은 전환하지 않아 온보드 UART 연결을 유지합니다.
4. Timed 단계와 button 단계를 모두 마친 뒤 필요한 경우 `DISABLE_SWD`를 원래 위치로
   복원합니다.

Active SWD 상태에서 나타나는 `RESET_DEBUG`는 GRTC나 GPIO wake가 아닙니다. 이 원인의 즉시
wake는 결합 HIL PASS 또는 API FAIL로 판정하지 않으며, SWD가 격리되지 않은 실행은 완료 증거로
사용하지 않습니다.

```powershell
Set-Location "<NU54DK_Arduino_Core 저장소 경로>"
$CoreRoot = (Get-Location).Path
$ArtifactRoot = "<다운로드해 압축을 푼 m12-zephyr-build artifact>"
$WakeHex = Join-Path $ArtifactRoot `
  "twister\nrf54l15dk_nrf54l15_cpuapp_nu54dk\zephyr_gnu\nucode.m15.wake\m15_wake\zephyr\zephyr.hex"
```

실제 결합 시험은 M15 변경을 commit한 exact source에서 다음과 같이 실행합니다. 여러 보드가
연결될 수 있으므로 `--board-id`는 필수이며 기본 probe UID로 대체하지 않습니다. 기존 증적은
`--overwrite-evidence` 없이는 덮어쓰지 않습니다.

```powershell
$Commit = git -C $CoreRoot rev-parse HEAD
& $Python -I "$CoreRoot\tests\hil\nu54dk\m15_system_off.py" `
  --hex $WakeHex `
  --board-id "<시험할 CMSIS-DAP UID>" `
  --expected-core-revision $Commit `
  --acknowledge-interface-switch `
  --acknowledge-button-wake `
  --evidence "$CoreRoot\build\m15\hil\m15-system-off.evidence.json"
```

Runner는 먼저 timed GRTC 단계의 System OFF 무응답 구간과 `RESET_CLOCK`을 확인해야 합니다.
`TIMED READY` 안내에서 SWD만 격리한 뒤 `DISABLE_SWD_ONLY`를 입력하고, button 준비 안내에서는
사용자 SW0가 눌리지 않았음을 확인한 뒤 `SW0_RELEASED`를 입력합니다.
그 뒤에만 button 단계를 arm하고 `M15 PRESS NOW`를 출력합니다. 이 안내 전에 사용자
SW0/P1.13을 누른 결과, 다른 GPIO 또는 `LOW_POWER_WAKE`가 아닌 reset 원인, 누락·중복 token은
PASS로 인정하지 않습니다.

Core `c47239d954c45fd173d8d1393e3ea5c9c86e111a`의 공식 CI artifact로 한 SWD-only 격리
세션을 실행했습니다. Timed GRTC wake는 `2062 ms`와 exact cause `2048`, 사용자 SW0/P1.13
wake는 `20406 ms`와 exact cause `128`로 PASS했습니다. Exact image·revision·transcript
SHA-256은 [M15 기준선](<../../../00_Docs/04_검증 기록/17_M15_NU54DK_Board_System_기준선.md>)에
기록하며 M15 System OFF 항목은 완료 상태입니다.

구체적인 실행 명령과 이미 검증한 결과는
[M6 기준선](<../../../00_Docs/04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>),
[M7 기준선](<../../../00_Docs/04_검증 기록/07_M7_Wire_SPI_ADC_PWM_기준선.md>) 및
[M8 기준선](<../../../00_Docs/04_검증 기록/08_M8_업로드와_디버그_기준선.md>),
[M14 기준선](<../../../00_Docs/04_검증 기록/16_M14_Core_API와_Variant_기준선.md>) 및
[M15 기준선](<../../../00_Docs/04_검증 기록/17_M15_NU54DK_Board_System_기준선.md>)을 따릅니다.

## v0.4.0 M24~M26 무배선 온보드 gate

이 묶음은 외부 점퍼 없이 연결된 NU54DK 한 대와 DAP VCOM 두 포트를 사용합니다. 보드의
debug-control `DISABLE_SWD`가 격리 위치이면 USB와 COM이 보이더라도 flash가 `No ACK`로 실패할 수
있습니다. 사용자 버튼 SW1/P1.09와 혼동하지 말고 SWD 연결 상태를 먼저 확인합니다.

| 순서 | Runner | 실기 판정 범위 |
| --- | --- | --- |
| 1 | `m24_uarte_onboard.py` | UARTE20/21/22/30의 DAP VCOM 32-byte DMA 왕복 |
| 2 | `m24_twim_onboard.py` | TWIM20/21/22의 BQ25186 MASK_ID read-only |
| 3 | `m25_onboard.py` | 내부 VDD SAADC, EGU→DPPI→TIMER event 경로 |
| 4 | `m26_onboard.py` | TEMP, WDT30 configure/start/feed·의도한 reset과 reset cause |

먼저 [Windows 개발환경](<../../../00_Docs/02_빌드 설계/09_Windows_개발환경_설정.md>)의 NCS 환경을
적용하고 **현재 clean commit**에서 전체 `v0.4.0` group을 새 짧은 경로에 build합니다. 다른 commit의
기존 image는 runner가 거부하므로 예전 build root를 재사용하지 않습니다.

```powershell
$CoreRoot = (Get-Location).Path
$Python = 'C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe'
$PyOcd = 'C:\ncs\toolchains\dcbdc366a1\opt\bin\Scripts\pyocd.exe'
$BuildRoot = 'C:\nb\01' # 전체 8자 이하, 아직 없는 하위 경로
$EvidenceRoot = Join-Path $env:USERPROFILE 'Documents\NU54DK-evidence\v04-run01'
$ProbeId = '<시험할 CMSIS-DAP UID>'

if ((Get-Command python.exe).Source -ne $Python) {
  throw 'NCS environment is required: pyocd.exe must select the bundled Python'
}
& $Python -I -c 'import sys, pyocd; print(sys.executable); print(pyocd.__version__, pyocd.__file__)'

& $Python tools\ci\run_zephyr_build.py `
  --workspace C:\ncs\v3.4.0 --outdir $BuildRoot --group v0.4.0 --jobs 4
if ($LASTEXITCODE -ne 0) { throw 'v0.4.0 build failed' }

$Runners = @('m24_uarte_onboard', 'm24_twim_onboard', 'm25_onboard', 'm26_onboard')
foreach ($Runner in $Runners) {
  & $Python "tests\hil\nu54dk\$Runner.py" `
    --repository $CoreRoot --build-root $BuildRoot --probe-id $ProbeId --pyocd $PyOcd `
    --evidence "$EvidenceRoot\$Runner.json"
  if ($LASTEXITCODE -ne 0) { throw "$Runner failed; later gates were not run" }
}
```

각 runner는 시작 시 clean source·board revision과 HEX hash를 기록하고 exact UID를 선택하며 mass erase/recover를
사용하지 않습니다. 실패하면 해당 시점에서 멈추며, 응답 없는 보드에서 PASS를 생성하지 않습니다.
Flash 종료 시에는 자동 reset/resume을 금지하고, 같은 probe를 다시 연결해 CPU reset·halt를 확인한
뒤 VCOM 두 포트의 초기 buffer를 비우고 명시적으로 resume합니다. 따라서 초기 reset transient는
앱이 READY를 보내기 전에만 제거됩니다. 시작 이후의 READY·측정 결과는 잡음을 허용하지 않습니다.
이 묶음의 PASS를 외부 SPI/TWIS·analog 정확도·audio·encoder·동시성·전력 검증으로 확대하지 않습니다.

TWIM과 M25 firmware는 유효 command 하나당 측정 결과 하나만 보내고 대기합니다. 결과에 다음
READY가 붙어 USB read 단위에 따라 성공·실패가 달라지지 않도록 한 flash당 단발 시험으로 합니다.
호스트는 완전한 frame 뒤에도 50 ms를 관찰하여 추가 byte를 거부합니다.

M26 protocol v2는 `READY → command → AR26 → WDT reset → RESET_READY → result request → NU26`
순서를 사용합니다. UART가 재초기화되기 전 reset 경계에서 transient byte가 관측됐으므로,
**AR26 검증 이후의 예상 reset 구간에서만** 최대 64바이트 prefix와 정확한 RESET_READY를
구분합니다. Prefix 원문·길이, 선택 VCOM, reset READY 대기 시간을 evidence schema v2에 남깁니다.
RESET_READY는 다른 VCOM·다른 marker·중복·후행 byte를 허용하지 않으며, 준비 신호 뒤 별도 request에
대한 NU26 결과는 여전히 정확한 32바이트·checksum·watchdog reset bit·retained TEMP를 요구합니다.
초기 READY, AR26, NU26에 잡음을 붙이거나 과거 protocol v1 진단을 새 PASS로 바꿀 수 없습니다.
이 검증은 reset 중 UART 신호가 깨끗하다는 전기적 보증을 포함하지 않습니다.

M25의 수동 SAADC 모드에서는 `start()`가 DMA를 준비하고, `ready` event 이후 `sample()`이 실제
변환을 요청합니다. `stop_timeout`이면 lease는 유지되며 `stop()`을 재시도해야 합니다. 내부 VDD
raw code를 교정된 전압이나 외부 채널 정확도 결과로 해석하지 않습니다.

현재 온보드 PASS와 exact JSON은 [교정·실기 재검증](<../../../00_Docs/04_검증 기록/41_M24_M26_온보드_protocol_교정과_실기_재검증.md>)을,
외부 fixture·최종 release 경계는 [M27 자동 준비·HOLD 기록](<../../../00_Docs/04_검증 기록/39_M27_v0.4.0_rc1_자동_준비와_HOLD.md>)을 따릅니다.
