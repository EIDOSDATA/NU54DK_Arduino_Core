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
| `m15_auto.py` | identity·GRTC·Settings·WDT·timed System OFF 자동 검증 | 공식 Ubuntu CI artifact, NU54DK, CMSIS-DAP V2 UART |
| `m15_system_off.py` | UART ARM 뒤 System OFF와 SW0 wake 검증 | NU54DK, CMSIS-DAP V2 UART, SW0 한 번 누름 |
| `test_m7_*.py` | 실제 장치 없이 HIL protocol/parser를 검증 | 없음 |
| `test_m14_pin_hil.py` | M14 수동 동작 protocol·증적의 fail-closed 경계를 검증 | 없음 |
| `test_m15_auto.py` | M15 자동 protocol과 Linux producer/Windows consumer provenance를 검증 | 없음 |
| `test_m15_system_off.py` | M15 ARM·무응답 시간·wake protocol과 증적 경계를 검증 | 없음 |

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
$CoreRoot = "C:\Users\eidos\GitHub\NU54DK_Arduino_Core"
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
$CoreRoot = "C:\Users\eidos\GitHub\NU54DK_Arduino_Core"
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

## M15 System OFF wake HIL 준비

M15 HIL은 `SW0`/P1.13 한 번 누르기만 수동으로 남겨 둡니다. image는 부팅만으로
System OFF에 진입하지 않으며, runner가 UART `READY`를 확인하고 정확한 `ARM` 명령을 보낸
뒤에만 원자적 버튼 wake 진입을 요청합니다. `REQUEST`와 `ENTERING`은 진입 완료나 PASS가
아니며, runner는 `ENTERING` 요청 이후 2초가 지난 다음 `M15 PRESS NOW`를 출력합니다.
이 안내 전에 버튼을 누른 결과, 다른 GPIO 또는
`LOW_POWER_WAKE`가 아닌 reset 원인, 누락·중복 token은 PASS로 인정하지 않습니다.

버튼 HIL도 같은 공식 CI artifact의 build record와 image를 사용합니다. 로컬에서 image를 다시
빌드하지 않습니다.

```powershell
$CoreRoot = "C:\Users\eidos\GitHub\NU54DK_Arduino_Core"
$ArtifactRoot = "<다운로드해 압축을 푼 m12-zephyr-build artifact>"
$WakeHex = Join-Path $ArtifactRoot `
  "twister\nrf54l15dk_nrf54l15_cpuapp_nu54dk\zephyr_gnu\nucode.m15.wake\m15_wake\zephyr\zephyr.hex"
```

실제 버튼 시험은 M15 변경을 commit한 exact source에서 다음과 같이 실행합니다. 여러 보드가
연결될 수 있으므로 `--board-id`는 필수이며 기본 probe UID로 대체하지 않습니다. 기존 증적은
`--overwrite-evidence` 없이는 덮어쓰지 않습니다.

```powershell
$Commit = git -C $CoreRoot rev-parse HEAD
& $Python -I "$CoreRoot\tests\hil\nu54dk\m15_system_off.py" `
  --hex $WakeHex `
  --board-id "<시험할 CMSIS-DAP UID>" `
  --expected-core-revision $Commit `
  --acknowledge-button-wake `
  --evidence "$CoreRoot\build\m15\hil\m15-system-off.evidence.json"
```

현재 단계에서는 위 runner와 image까지만 준비하며 버튼 결과를 완료로 기록하지 않습니다.
실기에서 `M15 PRESS NOW` 뒤 SW0을 눌러 최종 `NUCODE_M15_SYSTEM_OFF_PASS`가 나타나고 exact
image·revision·transcript SHA-256 증적이 생성된 뒤에만 버튼 wake 항목을 완료할 수 있습니다.

구체적인 실행 명령과 이미 검증한 결과는
[M6 기준선](<../../../00_Docs/04_검증 기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md>),
[M7 기준선](<../../../00_Docs/04_검증 기록/07_M7_Wire_SPI_ADC_PWM_기준선.md>) 및
[M8 기준선](<../../../00_Docs/04_검증 기록/08_M8_업로드와_디버그_기준선.md>),
[M14 기준선](<../../../00_Docs/04_검증 기록/16_M14_Core_API와_Variant_기준선.md>)을 따릅니다.
